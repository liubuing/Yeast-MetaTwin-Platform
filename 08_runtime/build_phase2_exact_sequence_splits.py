from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "09_configs" / "deployment_config.json"
TRAIN_DIR = ROOT / "05_training"
EVAL_DIR = ROOT / "06_evaluation"


POOLS = {
    "reference_only": TRAIN_DIR / "split_definitions_reference_only.csv",
    "reference_plus_candidate_no_overlap": TRAIN_DIR / "split_definitions_reference_plus_candidate_no_overlap.csv",
}


def load_config() -> dict[str, Any]:
    return load_deployment_config()


def parse_fasta(path: Path) -> dict[str, str]:
    sequences: dict[str, str] = {}
    current_id = ""
    chunks: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_id:
                    sequences[current_id] = "".join(chunks)
                current_id = line[1:].split()[0]
                chunks = []
            else:
                chunks.append(line)
    if current_id:
        sequences[current_id] = "".join(chunks)
    return sequences


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_bucket(key: str) -> int:
    return int(sha256_text(key)[:12], 16) % 100


def assign_split(key: str) -> str:
    bucket = stable_bucket(key)
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "dev"
    return "test"


def split_pipe(value: Any) -> list[str]:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return []
    return [item.strip() for item in text.split("|") if item.strip() and item.strip().lower() != "nogene"]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def exact_sequence_key(row: dict[str, Any], sequences: dict[str, str]) -> tuple[str, str, str, int, int]:
    orfs = split_pipe(row.get("orfs", ""))
    sequence_hashes = sorted({sha256_text(sequences[orf]) for orf in orfs if orf in sequences and sequences[orf]})
    if sequence_hashes:
        joined = "|".join(sequence_hashes)
        return "exact_sequence_set", "seqset:" + sha256_text(joined), joined, len(orfs), len(sequence_hashes)
    equation = str(row.get("model_equation", "")).strip()
    if equation:
        return "fallback_equation", "equation:" + equation, "", len(orfs), 0
    return "fallback_reaction_id", "reaction_id:" + str(row["model_reaction_id"]), "", len(orfs), 0


def build_pool(pool_name: str, path: Path, sequences: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    df = pd.read_csv(path, dtype=str).fillna("")
    rows: list[dict[str, Any]] = []
    group_to_splits: dict[str, set[str]] = defaultdict(set)
    fallback_counts: Counter[str] = Counter()
    missing_rows: list[dict[str, Any]] = []
    for row in df.to_dict("records"):
        key_type, key, sequence_hashes, orf_count, sequence_count = exact_sequence_key(row, sequences)
        split = assign_split(key)
        group_to_splits[key].add(split)
        fallback_counts[key_type] += 1
        out = dict(row)
        out["exact_sequence_split_pool"] = pool_name
        out["exact_sequence_split_key_type"] = key_type
        out["exact_sequence_split_key"] = key
        out["exact_sequence_hashes"] = sequence_hashes
        out["orf_count_for_sequence_split"] = orf_count
        out["matched_sequence_count_for_split"] = sequence_count
        out["exact_sequence_split_hash_bucket"] = stable_bucket(key)
        out["exact_sequence_split"] = split
        rows.append(out)
        if key_type.startswith("fallback"):
            missing_rows.append(
                {
                    "pool": pool_name,
                    "model_reaction_id": row["model_reaction_id"],
                    "reaction_uid": row["reaction_uid"],
                    "fallback_reason": key_type,
                    "orfs": row.get("orfs", ""),
                    "model_equation": row.get("model_equation", ""),
                }
            )
    crossing = {key: sorted(values) for key, values in group_to_splits.items() if len(values) > 1}
    counts = Counter(row["exact_sequence_split"] for row in rows)
    summary = {
        "pool": pool_name,
        "source_file": str(path.relative_to(ROOT)),
        "rows": len(rows),
        "split_counts": dict(counts),
        "key_type_counts": dict(fallback_counts),
        "sequence_split_key_count": len(group_to_splits),
        "sequence_split_keys_crossing_splits": len(crossing),
        "fallback_rows": sum(count for key, count in fallback_counts.items() if key.startswith("fallback")),
    }
    return rows, summary, missing_rows


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Exact-Sequence Split Definitions",
        "",
        f"Generated: {payload['generated_at']}",
        f"FASTA source: `{payload['fasta_source']}`",
        "",
        "## Split Counts",
        "",
        "| Pool | Rows | Train | Dev | Test | Exact-sequence keys | Crossing keys | Fallback rows |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in payload["pool_summaries"]:
        counts = summary["split_counts"]
        lines.append(
            f"| {summary['pool']} | {summary['rows']} | {counts.get('train', 0)} | {counts.get('dev', 0)} | {counts.get('test', 0)} | {summary['sequence_split_key_count']} | {summary['sequence_split_keys_crossing_splits']} | {summary['fallback_rows']} |"
        )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `05_training/exact_sequence_split_reference_only.csv`",
            "- `05_training/exact_sequence_split_reference_plus_candidate_no_overlap.csv`",
            "- `06_evaluation/phase2_exact_sequence_split_fallback_rows.csv`",
            "- `06_evaluation/phase2_exact_sequence_splits.json`",
            "",
            "## Rule",
            "",
            "The split key is the sorted set of SHA256 protein sequence hashes for ORFs attached to a reaction. Reactions without matched ORF sequences fall back to exact equation, then reaction ID. This prevents identical protein sequence sets from crossing train/dev/test, but it is not a homolog-cluster split.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    config = load_config()
    source_project = Path(config["source_project_dir"])
    fasta = source_project / "Data" / "Saccharomyces_cerevisiae.fasta"
    sequences = parse_fasta(fasta)
    summaries: list[dict[str, Any]] = []
    all_fallback_rows: list[dict[str, Any]] = []
    outputs: dict[str, str] = {}
    for pool_name, path in POOLS.items():
        rows, summary, fallback_rows = build_pool(pool_name, path, sequences)
        out = TRAIN_DIR / f"exact_sequence_split_{pool_name}.csv"
        write_csv(out, rows, list(rows[0].keys()))
        summaries.append(summary)
        all_fallback_rows.extend(fallback_rows)
        outputs[pool_name] = str(out.relative_to(ROOT))
    if all_fallback_rows:
        write_csv(EVAL_DIR / "phase2_exact_sequence_split_fallback_rows.csv", all_fallback_rows, list(all_fallback_rows[0].keys()))
    else:
        write_csv(EVAL_DIR / "phase2_exact_sequence_split_fallback_rows.csv", [], ["pool", "model_reaction_id", "reaction_uid", "fallback_reason", "orfs", "model_equation"])
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "fasta_source": str(fasta),
        "fasta_sequences": len(sequences),
        "method": "SHA256(sorted protein sequence hash set) % 100, train <80, dev 80-89, test >=90",
        "outputs": outputs,
        "pool_summaries": summaries,
    }
    (EVAL_DIR / "phase2_exact_sequence_splits.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_exact_sequence_splits.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_exact_sequence_splits.md")


if __name__ == "__main__":
    main()
