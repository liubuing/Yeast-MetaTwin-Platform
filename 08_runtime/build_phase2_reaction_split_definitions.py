from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "05_training"
EVAL_DIR = ROOT / "06_evaluation"


POOLS = {
    "reference_only": TRAIN_DIR / "split_ready_reference_labels.csv",
    "reference_plus_candidate_no_overlap": TRAIN_DIR / "split_ready_reference_plus_candidate_no_overlap.csv",
}


def has_text(value: Any) -> bool:
    return str(value).strip().lower() not in {"", "nan", "none", "null"}


def stable_bucket(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % 100


def assign_split(key: str) -> str:
    bucket = stable_bucket(key)
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "dev"
    return "test"


def split_key(row: dict[str, Any]) -> str:
    equation = str(row.get("model_equation", "")).strip()
    if has_text(equation):
        return "equation:" + equation
    return "reaction_id:" + str(row["model_reaction_id"])


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_pool(pool_name: str, path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    df = pd.read_csv(path, dtype=str).fillna("")
    rows: list[dict[str, Any]] = []
    key_to_splits: dict[str, set[str]] = defaultdict(set)
    for row in df.to_dict("records"):
        key = split_key(row)
        split = assign_split(key)
        key_to_splits[key].add(split)
        row = dict(row)
        row["split_pool"] = pool_name
        row["split_key"] = key
        row["split_hash_bucket"] = stable_bucket(key)
        row["split"] = split
        rows.append(row)
    crossing = {key: sorted(values) for key, values in key_to_splits.items() if len(values) > 1}
    counts = Counter(row["split"] for row in rows)
    role_counts = Counter((row["split"], row["training_role"]) for row in rows)
    summary = {
        "pool": pool_name,
        "source_file": str(path.relative_to(ROOT)),
        "rows": len(rows),
        "split_counts": dict(counts),
        "training_role_by_split": {f"{split}:{role}": count for (split, role), count in sorted(role_counts.items())},
        "split_key_count": len(key_to_splits),
        "split_keys_crossing_splits": len(crossing),
    }
    return rows, summary


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Reaction Split Definitions",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Split Counts",
        "",
        "| Pool | Rows | Train | Dev | Test | Split keys crossing splits |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for summary in payload["pool_summaries"]:
        counts = summary["split_counts"]
        lines.append(
            f"| {summary['pool']} | {summary['rows']} | {counts.get('train', 0)} | {counts.get('dev', 0)} | {counts.get('test', 0)} | {summary['split_keys_crossing_splits']} |"
        )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `05_training/split_definitions_reference_only.csv`",
            "- `05_training/split_definitions_reference_plus_candidate_no_overlap.csv`",
            "- `06_evaluation/phase2_reaction_split_definitions.json`",
            "",
            "## Rule",
            "",
            "Splits are deterministic SHA256 hash assignments over exact model equation when available, falling back to model reaction ID. The target ratio is 80/10/10 for train/dev/test. This is a structural split definition, not a homology-cold split.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    summaries: list[dict[str, Any]] = []
    output_files: dict[str, str] = {}
    for pool_name, path in POOLS.items():
        rows, summary = build_pool(pool_name, path)
        out = TRAIN_DIR / f"split_definitions_{pool_name}.csv"
        write_csv(out, rows, list(rows[0].keys()))
        summaries.append(summary)
        output_files[pool_name] = str(out.relative_to(ROOT))
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": "sha256(split_key) % 100, train <80, dev 80-89, test >=90",
        "split_key_rule": "exact model equation if present, otherwise model reaction ID",
        "output_files": output_files,
        "pool_summaries": summaries,
    }
    (EVAL_DIR / "phase2_reaction_split_definitions.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_reaction_split_definitions.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_reaction_split_definitions.md")


if __name__ == "__main__":
    main()
