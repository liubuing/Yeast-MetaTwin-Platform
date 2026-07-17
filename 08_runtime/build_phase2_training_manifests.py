from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "05_training"
EVAL_DIR = ROOT / "06_evaluation"


INPUTS = {
    "reference_only": TRAIN_DIR / "split_definitions_reference_only.csv",
    "reference_plus_candidate_no_overlap": TRAIN_DIR / "split_definitions_reference_plus_candidate_no_overlap.csv",
    "exact_sequence_reference_only": TRAIN_DIR / "exact_sequence_split_reference_only.csv",
    "exact_sequence_reference_plus_candidate_no_overlap": TRAIN_DIR / "exact_sequence_split_reference_plus_candidate_no_overlap.csv",
    "mmseqs_homology_reference_only": TRAIN_DIR / "homology_split_reference_only.csv",
    "mmseqs_homology_reference_plus_candidate_no_overlap": TRAIN_DIR / "homology_split_reference_plus_candidate_no_overlap.csv",
}


SUPPORTING_INPUTS = [
    TRAIN_DIR / "split_ready_candidate_reference_overlap_review.csv",
    TRAIN_DIR / "split_ready_model_context_only.csv",
    TRAIN_DIR / "split_ready_excluded_review_required.csv",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_profile(path: Path) -> dict[str, Any]:
    df = pd.read_csv(path, dtype=str).fillna("")
    profile: dict[str, Any] = {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
    }
    if "split" in df.columns:
        profile["split_counts"] = dict(Counter(df["split"]))
    if "exact_sequence_split" in df.columns:
        profile["exact_sequence_split_counts"] = dict(Counter(df["exact_sequence_split"]))
    if "exact_sequence_split_key_type" in df.columns:
        profile["exact_sequence_split_key_type_counts"] = dict(Counter(df["exact_sequence_split_key_type"]))
    if "homology_split" in df.columns:
        profile["homology_split_counts"] = dict(Counter(df["homology_split"]))
    if "homology_split_key_type" in df.columns:
        profile["homology_split_key_type_counts"] = dict(Counter(df["homology_split_key_type"]))
    if "training_role" in df.columns:
        profile["training_role_counts"] = dict(Counter(df["training_role"]))
    if "export_group" in df.columns:
        profile["export_group_counts"] = dict(Counter(df["export_group"]))
    return profile


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Training Manifests",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Primary Inputs",
        "",
        "| Manifest | Rows | Columns | Train | Dev | Test | Exact train | Exact dev | Exact test | Homology train | Homology dev | Homology test | File |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, profile in payload["primary_inputs"].items():
        counts = profile.get("split_counts", {})
        exact_counts = profile.get("exact_sequence_split_counts", {})
        homology_counts = profile.get("homology_split_counts", {})
        lines.append(
            f"| {name} | {profile['rows']} | {profile['columns']} | {counts.get('train', 0)} | {counts.get('dev', 0)} | {counts.get('test', 0)} | {exact_counts.get('train', 0)} | {exact_counts.get('dev', 0)} | {exact_counts.get('test', 0)} | {homology_counts.get('train', 0)} | {homology_counts.get('dev', 0)} | {homology_counts.get('test', 0)} | `{profile['path']}` |"
        )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `05_training/training_manifest_reference_only.json`",
            "- `05_training/training_manifest_reference_plus_candidate_no_overlap.json`",
            "- `05_training/training_manifest_exact_sequence_reference_only.json`",
            "- `05_training/training_manifest_exact_sequence_reference_plus_candidate_no_overlap.json`",
            "- `05_training/training_manifest_mmseqs_homology_reference_only.json`",
            "- `05_training/training_manifest_mmseqs_homology_reference_plus_candidate_no_overlap.json`",
            "- `05_training/training_manifest_index.csv`",
            "- `06_evaluation/phase2_training_manifests.md`",
            "",
            "## Rule",
            "",
            "The manifest records immutable file hashes, row counts, columns, split distributions, and training-role distributions for the current training inputs. Regenerate it whenever any upstream training CSV changes.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    primary = {name: csv_profile(path) for name, path in INPUTS.items()}
    supporting = {path.stem: csv_profile(path) for path in SUPPORTING_INPUTS}
    generated_at = datetime.now().isoformat(timespec="seconds")

    manifest_rows: list[dict[str, Any]] = []
    for name, profile in primary.items():
        payload = {
            "generated_at": generated_at,
            "manifest_name": name,
            "primary_input": profile,
            "supporting_inputs": supporting,
            "notes": [
                "This manifest describes data files only; it is not a trained model artifact.",
                "reference_plus_candidate_no_overlap includes prediction-provenance candidate reactions and should be used intentionally.",
            ],
        }
        out = TRAIN_DIR / f"training_manifest_{name}.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest_rows.append(
            {
                "manifest_name": name,
                "manifest_path": str(out.relative_to(ROOT)),
                "primary_input_path": profile["path"],
                "primary_input_sha256": profile["sha256"],
                "rows": profile["rows"],
                "columns": profile["columns"],
                "train_rows": profile.get("split_counts", {}).get("train", 0),
                "dev_rows": profile.get("split_counts", {}).get("dev", 0),
                "test_rows": profile.get("split_counts", {}).get("test", 0),
                "exact_sequence_train_rows": profile.get("exact_sequence_split_counts", {}).get("train", 0),
                "exact_sequence_dev_rows": profile.get("exact_sequence_split_counts", {}).get("dev", 0),
                "exact_sequence_test_rows": profile.get("exact_sequence_split_counts", {}).get("test", 0),
                "homology_train_rows": profile.get("homology_split_counts", {}).get("train", 0),
                "homology_dev_rows": profile.get("homology_split_counts", {}).get("dev", 0),
                "homology_test_rows": profile.get("homology_split_counts", {}).get("test", 0),
            }
        )
    write_csv(TRAIN_DIR / "training_manifest_index.csv", manifest_rows)
    report_payload = {"generated_at": generated_at, "primary_inputs": primary, "supporting_inputs": supporting}
    (EVAL_DIR / "phase2_training_manifests.json").write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_training_manifests.md").write_text(render_report(report_payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_training_manifests.md")


if __name__ == "__main__":
    main()
