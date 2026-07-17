from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(load_deployment_config()["source_project_dir"])
EVAL_DIR = ROOT / "06_evaluation"

REQUIRED_ASSETS = [
    {"plugin": "CLEAN", "capability": "pretrained_ec_inference", "asset_type": "pretrained_checkpoint", "path": SOURCE / "data/pretrained/split0.pth", "required": True},
    {"plugin": "CLEAN", "capability": "pretrained_ec_inference", "asset_type": "pretrained_checkpoint", "path": SOURCE / "data/pretrained/split1.pth", "required": True},
    {"plugin": "CLEAN", "capability": "pretrained_ec_inference", "asset_type": "pretrained_checkpoint", "path": SOURCE / "data/pretrained/split2.pth", "required": True},
    {"plugin": "CLEAN", "capability": "pretrained_ec_inference", "asset_type": "pretrained_embedding", "path": SOURCE / "data/pretrained/70.pt", "required": True},
    {"plugin": "CLEAN", "capability": "pretrained_ec_inference", "asset_type": "distance_map", "path": SOURCE / "data/distance_map/split0_esm.pkl", "required": True},
    {"plugin": "CLEAN", "capability": "pretrained_ec_inference", "asset_type": "google_drive_download_attempt", "path": ROOT / "04_prediction_plugins/CLEAN/downloads/clean_pretrained_google_drive_download.bin", "required": False},
    {"plugin": "UniKP", "capability": "training_raw_data", "asset_type": "kcat_training_json", "path": SOURCE / "Code/kcatkm_prediction/UniKP/Kcat_combination_0918_wildtype_mutant.json", "required": True},
    {"plugin": "UniKP", "capability": "training_raw_data", "asset_type": "km_test_pickle", "path": SOURCE / "Code/kcatkm_prediction/UniKP/Km/Km_test_11722.pkl", "required": True},
    {"plugin": "UniKP", "capability": "training_raw_data", "asset_type": "kcat_km_samples", "path": SOURCE / "Code/kcatkm_prediction/UniKP/Kcat_Km/kcat_km_samples.xlsx", "required": True},
    {"plugin": "UniKP", "capability": "deployed_training_data", "asset_type": "kcat_training_json", "path": ROOT / "04_prediction_plugins/UniKP/datasets/Kcat_combination_0918_wildtype_mutant.json", "required": True},
    {"plugin": "UniKP", "capability": "deployed_training_data", "asset_type": "km_test_pickle", "path": ROOT / "04_prediction_plugins/UniKP/datasets/Km_test_11722.pkl", "required": True},
    {"plugin": "UniKP", "capability": "pretrained_kinetic_inference", "asset_type": "unikp_kcat_model", "path": ROOT / "04_prediction_plugins/UniKP/models/UniKP for kcat.pkl", "required": True},
    {"plugin": "UniKP", "capability": "pretrained_kinetic_inference", "asset_type": "unikp_km_model", "path": ROOT / "04_prediction_plugins/UniKP/models/UniKP for Km.pkl", "required": True},
    {"plugin": "UniKP", "capability": "pretrained_kinetic_inference", "asset_type": "unikp_kcat_km_model", "path": ROOT / "04_prediction_plugins/UniKP/models/UniKP for kcat_Km.pkl", "required": True},
    {"plugin": "UniKP", "capability": "pretrained_kinetic_inference", "asset_type": "prot_t5_model", "path": ROOT / "04_prediction_plugins/UniKP/models/prot_t5_xl_uniref50", "required": True},
    {"plugin": "UniKP", "capability": "pretrained_kinetic_inference", "asset_type": "smiles_transformer_vocab", "path": ROOT / "04_prediction_plugins/UniKP/models/vocab.pkl", "required": True},
    {"plugin": "UniKP", "capability": "pretrained_kinetic_inference", "asset_type": "smiles_transformer_weights", "path": ROOT / "04_prediction_plugins/UniKP/models/trfm_12_23000.pkl", "required": True},
    {"plugin": "DLKcat", "capability": "legacy_training_input", "asset_type": "compounds_input", "path": SOURCE / "Code/kcatkm_prediction/DLKcat/input/compounds", "required": True},
    {"plugin": "DLKcat", "capability": "legacy_training_input", "asset_type": "proteins_input", "path": SOURCE / "Code/kcatkm_prediction/DLKcat/input/proteins", "required": True},
    {"plugin": "DLKcat", "capability": "legacy_training_input", "asset_type": "regression_input", "path": SOURCE / "Code/kcatkm_prediction/DLKcat/input/regression", "required": True},
    {"plugin": "DLKcat", "capability": "training_raw_data", "asset_type": "kcat_json_wildtype_mutant", "path": ROOT / "04_prediction_plugins/DLKcat/data/Kcat_combination_0918_wildtype_mutant.json", "required": True},
    {"plugin": "DLKcat", "capability": "training_raw_data", "asset_type": "kcat_json", "path": ROOT / "04_prediction_plugins/DLKcat/data/Kcat_combination_0918.json", "required": True},
    {"plugin": "DLKcat", "capability": "training_raw_data", "asset_type": "kcat_tsv", "path": ROOT / "04_prediction_plugins/DLKcat/data/Kcat_combination_41559.tsv", "required": True},
    {"plugin": "DLKcat", "capability": "example_inference_io", "asset_type": "example_input", "path": ROOT / "04_prediction_plugins/DLKcat/example/input.tsv", "required": True},
    {"plugin": "DLKcat", "capability": "example_inference_io", "asset_type": "example_output", "path": ROOT / "04_prediction_plugins/DLKcat/example/output.tsv", "required": True},
]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Plugin Asset Readiness",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Summary",
        "",
        "| Plugin | Capability | Required | Present | Missing | Status |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in payload["capability_summary"]:
        lines.append(f"| {row['plugin']} | {row['capability']} | {row['required']} | {row['present']} | {row['missing']} | {row['status']} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Readiness is capability-specific. Downloaded inference or raw-data assets do not imply full plugin readiness if companion language models, legacy inputs, or compatible runtime versions are missing.",
            "",
            "## Output",
            "",
            "- `06_evaluation/phase2_plugin_asset_readiness.csv`",
            "- `06_evaluation/phase2_plugin_asset_readiness.json`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = []
    for item in REQUIRED_ASSETS:
        path = item["path"]
        exists = path.exists()
        rows.append(
            {
                "plugin": item["plugin"],
                "capability": item["capability"],
                "asset_type": item["asset_type"],
                "path": str(path),
                "required": item["required"],
                "exists": exists,
                "is_file": path.is_file() if exists else False,
                "is_dir": path.is_dir() if exists else False,
                "size_bytes": path.stat().st_size if exists and path.is_file() else "",
                "status": "present" if exists else "missing",
            }
        )
    summary = []
    for key in sorted({(row["plugin"], row["capability"]) for row in rows}):
        plugin, capability = key
        sub = [row for row in rows if row["plugin"] == plugin and row["capability"] == capability and row["required"]]
        present = sum(1 for row in sub if row["exists"])
        missing = len(sub) - present
        summary.append({"plugin": plugin, "capability": capability, "required": len(sub), "present": present, "missing": missing, "status": "ready" if missing == 0 else "blocked_missing_assets"})
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "capability_summary": summary, "assets": rows}
    write_csv(EVAL_DIR / "phase2_plugin_asset_readiness.csv", rows, list(rows[0].keys()))
    (EVAL_DIR / "phase2_plugin_asset_readiness.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_plugin_asset_readiness.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_plugin_asset_readiness.md")


if __name__ == "__main__":
    main()
