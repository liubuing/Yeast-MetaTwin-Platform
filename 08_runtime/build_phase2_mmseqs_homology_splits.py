from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
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
TOOLS_DIR = ROOT / "tools"
LOCAL_MMSEQS = TOOLS_DIR / "mmseqs2" / "mmseqs" / "bin" / "mmseqs.exe"

POOLS = {
    "reference_only": TRAIN_DIR / "split_definitions_reference_only.csv",
    "reference_plus_candidate_no_overlap": TRAIN_DIR / "split_definitions_reference_plus_candidate_no_overlap.csv",
}

MIN_SEQ_ID = 0.3
COVERAGE = 0.8
COV_MODE = 0


def load_config() -> dict[str, Any]:
    return load_deployment_config()


def mmseqs_path() -> str:
    path = os.environ.get("METATWIN_MMSEQS") or shutil.which("mmseqs") or (str(LOCAL_MMSEQS) if LOCAL_MMSEQS.exists() else "")
    if not path:
        raise FileNotFoundError("MMseqs2 executable not found")
    return path


def mmseqs_command(args: list[str]) -> list[str]:
    return [mmseqs_path(), *args]


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


def split_pipe(value: Any) -> list[str]:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return []
    return [item.strip() for item in text.split("|") if item.strip() and item.strip().lower() != "nogene"]


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


def collect_orfs() -> set[str]:
    orfs: set[str] = set()
    for path in POOLS.values():
        df = pd.read_csv(path, dtype=str).fillna("")
        for value in df["orfs"]:
            orfs.update(split_pipe(value))
    return orfs


def write_fasta(path: Path, orfs: set[str], sequences: dict[str, str]) -> tuple[int, int]:
    written = 0
    missing = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for orf in sorted(orfs):
            seq = sequences.get(orf, "")
            if not seq:
                missing += 1
                continue
            handle.write(f">{orf}\n")
            for i in range(0, len(seq), 80):
                handle.write(seq[i : i + 80] + "\n")
            written += 1
    return written, missing


def run_mmseqs(input_fasta: Path, cluster_prefix: Path, tmp_dir: Path) -> Path:
    exe = mmseqs_path()
    run_root = Path(tempfile.gettempdir()) / "metatwin" / "mmseqs_homology" / f"run_{os.getpid()}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    run_root.mkdir(parents=True, exist_ok=True)
    run_input = run_root / "reaction_split_orfs.fasta"
    shutil.copyfile(input_fasta, run_input)
    run_db = run_root / "input_db"
    run_cluster = run_root / "cluster_db"
    run_tmp = run_root / "tmp"
    run_cluster_tsv = run_root / "cluster.tsv"
    input_arg = str(run_input)
    db_arg = str(run_db)
    cluster_arg = str(run_cluster)
    tmp_arg = str(run_tmp)
    tsv_arg = str(run_cluster_tsv)
    commands = [
        mmseqs_command(["createdb", input_arg, db_arg]),
        mmseqs_command([
            "cluster",
            db_arg,
            cluster_arg,
            tmp_arg,
            "--min-seq-id",
            str(MIN_SEQ_ID),
            "-c",
            str(COVERAGE),
            "--cov-mode",
            str(COV_MODE),
            "--threads",
            "4",
        ]),
        mmseqs_command(["createtsv", db_arg, db_arg, cluster_arg, tsv_arg, "--threads", "4"]),
    ]
    logs = []
    for cmd in commands:
        result = subprocess.run(cmd, cwd=str(run_root), text=True, capture_output=True, check=False)
        logs.append({"command": cmd, "returncode": result.returncode, "stdout": result.stdout[-10000:], "stderr": result.stderr[-10000:]})
        if result.returncode != 0:
            (EVAL_DIR / "phase2_mmseqs_homology_split_runlog.json").write_text(json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8")
            raise RuntimeError(f"MMseqs2 command failed with code {result.returncode}: {' '.join(cmd)}")
    (EVAL_DIR / "phase2_mmseqs_homology_split_runlog.json").write_text(json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8")
    cluster_tsv = Path(str(cluster_prefix) + "_cluster.tsv")
    shutil.copyfile(run_cluster_tsv, cluster_tsv)
    return cluster_tsv


def read_clusters(path: Path) -> dict[str, str]:
    member_to_rep: dict[str, str] = {}
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            rep, member = parts[0], parts[1]
            member_to_rep[member] = rep
            member_to_rep.setdefault(rep, rep)
    return member_to_rep


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def reaction_cluster_key(row: dict[str, Any], member_to_rep: dict[str, str]) -> tuple[str, str, str, int, int]:
    orfs = split_pipe(row.get("orfs", ""))
    reps = sorted({member_to_rep[orf] for orf in orfs if orf in member_to_rep})
    if reps:
        joined = "|".join(reps)
        return "mmseqs_cluster_set", "cluster_set:" + sha256_text(joined), joined, len(orfs), len(reps)
    equation = str(row.get("model_equation", "")).strip()
    if equation:
        return "fallback_equation", "equation:" + equation, "", len(orfs), 0
    return "fallback_reaction_id", "reaction_id:" + str(row["model_reaction_id"]), "", len(orfs), 0


def build_pool(pool_name: str, path: Path, member_to_rep: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    df = pd.read_csv(path, dtype=str).fillna("")
    rows: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []
    key_to_splits: dict[str, set[str]] = defaultdict(set)
    key_type_counts: Counter[str] = Counter()
    for row in df.to_dict("records"):
        key_type, key, reps, orf_count, rep_count = reaction_cluster_key(row, member_to_rep)
        split = assign_split(key)
        key_to_splits[key].add(split)
        key_type_counts[key_type] += 1
        out = dict(row)
        out["homology_split_pool"] = pool_name
        out["homology_split_key_type"] = key_type
        out["homology_split_key"] = key
        out["mmseqs_cluster_representatives"] = reps
        out["orf_count_for_homology_split"] = orf_count
        out["cluster_rep_count_for_split"] = rep_count
        out["homology_split_hash_bucket"] = stable_bucket(key)
        out["homology_split"] = split
        rows.append(out)
        if key_type.startswith("fallback"):
            fallback_rows.append(
                {
                    "pool": pool_name,
                    "model_reaction_id": row["model_reaction_id"],
                    "reaction_uid": row["reaction_uid"],
                    "fallback_reason": key_type,
                    "orfs": row.get("orfs", ""),
                    "model_equation": row.get("model_equation", ""),
                }
            )
    crossing = {key: sorted(values) for key, values in key_to_splits.items() if len(values) > 1}
    counts = Counter(row["homology_split"] for row in rows)
    summary = {
        "pool": pool_name,
        "rows": len(rows),
        "split_counts": dict(counts),
        "key_type_counts": dict(key_type_counts),
        "homology_split_key_count": len(key_to_splits),
        "homology_split_keys_crossing_splits": len(crossing),
        "fallback_rows": sum(count for key, count in key_type_counts.items() if key.startswith("fallback")),
    }
    return rows, summary, fallback_rows


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 MMseqs2 Homology Split Definitions",
        "",
        f"Generated: {payload['generated_at']}",
        f"MMseqs2: `{payload['mmseqs_path']}`",
        f"FASTA source: `{payload['fasta_source']}`",
        "",
        "## Clustering",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Input ORFs | {payload['input_orfs']} |",
        f"| FASTA sequences written | {payload['fasta_sequences_written']} |",
        f"| ORFs missing sequence | {payload['orfs_missing_sequence']} |",
        f"| MMseqs2 clusters | {payload['mmseqs_cluster_count']} |",
        "",
        "## Split Counts",
        "",
        "| Pool | Rows | Train | Dev | Test | Homology keys | Crossing keys | Fallback rows |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in payload["pool_summaries"]:
        counts = summary["split_counts"]
        lines.append(
            f"| {summary['pool']} | {summary['rows']} | {counts.get('train', 0)} | {counts.get('dev', 0)} | {counts.get('test', 0)} | {summary['homology_split_key_count']} | {summary['homology_split_keys_crossing_splits']} | {summary['fallback_rows']} |"
        )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `05_training/homology_split_reference_only.csv`",
            "- `05_training/homology_split_reference_plus_candidate_no_overlap.csv`",
            "- `06_evaluation/phase2_mmseqs_homology_split_fallback_rows.csv`",
            "- `06_evaluation/phase2_mmseqs_homology_splits.json`",
            "",
            "## Rule",
            "",
            "MMseqs2 clusters ORF protein sequences, then reactions are split by the sorted set of cluster representatives attached to each reaction. Reactions without clusterable ORFs fall back to exact equation. This is a homology-aware split over available yeast ORF sequences, not an experimental validation split.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    config = load_config()
    source_project = Path(config["source_project_dir"])
    fasta_source = source_project / "Data" / "Saccharomyces_cerevisiae.fasta"
    sequences = parse_fasta(fasta_source)
    orfs = collect_orfs()

    cluster_dir = TRAIN_DIR / "mmseqs_homology_clusters"
    tmp_dir = cluster_dir / "tmp"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    input_fasta = cluster_dir / "reaction_split_orfs.fasta"
    written, missing = write_fasta(input_fasta, orfs, sequences)
    cluster_prefix = cluster_dir / f"yeast_orf_minid{str(MIN_SEQ_ID).replace('.', '_')}_cov{str(COVERAGE).replace('.', '_')}"
    cluster_tsv = run_mmseqs(input_fasta, cluster_prefix, tmp_dir)
    member_to_rep = read_clusters(cluster_tsv)
    cluster_count = len(set(member_to_rep.values()))

    summaries: list[dict[str, Any]] = []
    all_fallback: list[dict[str, Any]] = []
    outputs: dict[str, str] = {}
    for pool_name, path in POOLS.items():
        rows, summary, fallback = build_pool(pool_name, path, member_to_rep)
        out = TRAIN_DIR / f"homology_split_{pool_name}.csv"
        write_csv(out, rows, list(rows[0].keys()))
        summaries.append(summary)
        all_fallback.extend(fallback)
        outputs[pool_name] = str(out.relative_to(ROOT))
    if all_fallback:
        write_csv(EVAL_DIR / "phase2_mmseqs_homology_split_fallback_rows.csv", all_fallback, list(all_fallback[0].keys()))
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mmseqs_path": mmseqs_path(),
        "fasta_source": str(fasta_source),
        "input_orfs": len(orfs),
        "fasta_sequences_written": written,
        "orfs_missing_sequence": missing,
        "min_seq_id": MIN_SEQ_ID,
        "coverage": COVERAGE,
        "cov_mode": COV_MODE,
        "cluster_tsv": str(cluster_tsv.relative_to(ROOT)),
        "mmseqs_cluster_count": cluster_count,
        "outputs": outputs,
        "pool_summaries": summaries,
    }
    (EVAL_DIR / "phase2_mmseqs_homology_splits.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_mmseqs_homology_splits.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_mmseqs_homology_splits.md")


if __name__ == "__main__":
    main()
