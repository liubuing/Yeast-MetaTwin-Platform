from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "05_training"
EVAL_DIR = ROOT / "06_evaluation"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Split-Ready Reaction Pools",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Counts",
        "",
        "| Pool | Count | File |",
        "|---|---:|---|",
    ]
    for pool, count in payload["pool_counts"].items():
        lines.append(f"| {pool} | {count} | `{payload['files'][pool]}` |")
    lines.extend(
        [
            "",
            "## Rule",
            "",
            "The split-ready candidate pool excludes candidate reactions whose exact model equation also appears in the first-pass reference label pool. These overlap rows are exported separately for review and should not be used in naive train/test splits.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    all_rows = pd.read_csv(TRAIN_DIR / "reaction_all_label_export_groups.csv", dtype=str).fillna("")
    overlap = pd.read_csv(EVAL_DIR / "phase2_reaction_label_export_cross_pool_overlap.csv", dtype=str).fillna("")
    overlap_equations = set(overlap.loc[overlap["overlap_type"] == "exact_model_equation", "key"])

    reference = all_rows[all_rows["export_group"] == "first_pass_reference_label"]
    candidate = all_rows[all_rows["export_group"] == "candidate_extension_evidence"]
    candidate_overlap = candidate[candidate["model_equation"].isin(overlap_equations)]
    candidate_clean = candidate[~candidate["model_equation"].isin(overlap_equations)]
    model_context = all_rows[all_rows["export_group"] == "model_context_only"]
    excluded = all_rows[all_rows["export_group"] == "excluded_review_required"]
    split_ready = pd.concat([reference, candidate_clean], ignore_index=True)

    fieldnames = list(all_rows.columns)
    files = {
        "reference_labels": "05_training/split_ready_reference_labels.csv",
        "candidate_extension_no_reference_overlap": "05_training/split_ready_candidate_extension_no_reference_overlap.csv",
        "candidate_reference_overlap_review": "05_training/split_ready_candidate_reference_overlap_review.csv",
        "reference_plus_candidate_no_overlap": "05_training/split_ready_reference_plus_candidate_no_overlap.csv",
        "model_context_only": "05_training/split_ready_model_context_only.csv",
        "excluded_review_required": "05_training/split_ready_excluded_review_required.csv",
    }
    write_csv(ROOT / files["reference_labels"], reference.to_dict("records"), fieldnames)
    write_csv(ROOT / files["candidate_extension_no_reference_overlap"], candidate_clean.to_dict("records"), fieldnames)
    write_csv(ROOT / files["candidate_reference_overlap_review"], candidate_overlap.to_dict("records"), fieldnames)
    write_csv(ROOT / files["reference_plus_candidate_no_overlap"], split_ready.to_dict("records"), fieldnames)
    write_csv(ROOT / files["model_context_only"], model_context.to_dict("records"), fieldnames)
    write_csv(ROOT / files["excluded_review_required"], excluded.to_dict("records"), fieldnames)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "overlap_equation_count": len(overlap_equations),
        "pool_counts": {
            "reference_labels": len(reference),
            "candidate_extension_no_reference_overlap": len(candidate_clean),
            "candidate_reference_overlap_review": len(candidate_overlap),
            "reference_plus_candidate_no_overlap": len(split_ready),
            "model_context_only": len(model_context),
            "excluded_review_required": len(excluded),
        },
        "training_role_counts_in_reference_plus_candidate_no_overlap": dict(Counter(split_ready["training_role"])),
        "files": files,
    }
    (EVAL_DIR / "phase2_split_ready_reaction_pools.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_split_ready_reaction_pools.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_split_ready_reaction_pools.md")


if __name__ == "__main__":
    main()
