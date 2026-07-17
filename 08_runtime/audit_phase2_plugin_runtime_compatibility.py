from __future__ import annotations

import csv
import json
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "06_evaluation"
UNIKP_CODE = ROOT / "04_prediction_plugins" / "UniKP" / "code"

CHECKS = [
    {"plugin": "UniKP", "asset": "trfm_12_23000.pkl", "path": ROOT / "04_prediction_plugins/UniKP/models/trfm_12_23000.pkl", "check": "torch_load_required"},
    {"plugin": "UniKP", "asset": "vocab.pkl", "path": ROOT / "04_prediction_plugins/UniKP/models/vocab.pkl", "check": "pickle_load"},
    {"plugin": "UniKP", "asset": "UniKP for kcat.pkl", "path": ROOT / "04_prediction_plugins/UniKP/models/UniKP for kcat.pkl", "check": "pickle_load"},
    {"plugin": "UniKP", "asset": "UniKP for Km.pkl", "path": ROOT / "04_prediction_plugins/UniKP/models/UniKP for Km.pkl", "check": "pickle_load"},
    {"plugin": "UniKP", "asset": "UniKP for kcat_Km.pkl", "path": ROOT / "04_prediction_plugins/UniKP/models/UniKP for kcat_Km.pkl", "check": "pickle_load"},
    {"plugin": "UniKP", "asset": "prot_t5_xl_uniref50", "path": ROOT / "04_prediction_plugins/UniKP/models/prot_t5_xl_uniref50", "check": "prot_t5_encoder_load"},
]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def check_asset(item: dict[str, Any]) -> dict[str, Any]:
    path = item["path"]
    row = {"plugin": item["plugin"], "asset": item["asset"], "path": str(path), "exists": path.exists(), "check": item["check"], "runtime_status": "not_checked", "detail": ""}
    if not path.exists():
        row["runtime_status"] = "missing"
        return row
    try:
        if item["check"] == "pickle_load":
            if item["asset"] == "vocab.pkl" and str(UNIKP_CODE) not in sys.path:
                sys.path.insert(0, str(UNIKP_CODE))
                import __main__
                import build_vocab

                setattr(__main__, "WordVocab", build_vocab.WordVocab)
            with path.open("rb") as handle:
                obj = pickle.load(handle)
            row["runtime_status"] = "load_ok"
            row["detail"] = str(type(obj))
        elif item["check"] == "torch_load_required":
            import torch

            obj = torch.load(path, map_location="cpu")
            row["runtime_status"] = "load_ok"
            row["detail"] = str(type(obj))
        elif item["check"] == "prot_t5_encoder_load":
            from transformers import T5Config, T5EncoderModel, T5Tokenizer

            tokenizer = T5Tokenizer.from_pretrained(str(path), local_files_only=True, legacy=True, use_fast=False)
            config = T5Config.from_pretrained(str(path), local_files_only=True)
            model = T5EncoderModel.from_pretrained(str(path), local_files_only=True)
            row["runtime_status"] = "load_ok"
            row["detail"] = f"{type(model).__name__}; vocab_size={tokenizer.vocab_size}; d_model={config.d_model}; layers={config.num_layers}; params={sum(v.numel() for v in model.parameters())}"
    except Exception as exc:
        row["runtime_status"] = "load_failed"
        row["detail"] = f"{type(exc).__name__}: {exc}"[:2000]
    return row


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Plugin Runtime Compatibility",
        "",
        f"Generated: {payload['generated_at']}",
        f"Python: `{payload['python']}`",
        f"Executable: `{payload['executable']}`",
        "",
        "| Plugin | Asset | Exists | Runtime status | Detail |",
        "|---|---|---:|---|---|",
    ]
    for row in payload["checks"]:
        detail = row["detail"].replace("|", "/")[:300]
        lines.append(f"| {row['plugin']} | {row['asset']} | {row['exists']} | {row['runtime_status']} | {detail} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Asset presence is not full biological validation. This report verifies that downloaded UniKP local assets, including the ProtT5 encoder dependency, load in the selected runtime. Complete UniKP prediction still requires end-to-end feature generation on target sequence/SMILES pairs.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = [check_asset(item) for item in CHECKS]
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "python": sys.version, "executable": sys.executable, "checks": rows}
    write_csv(EVAL_DIR / "phase2_plugin_runtime_compatibility.csv", rows, list(rows[0].keys()))
    (EVAL_DIR / "phase2_plugin_runtime_compatibility.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_plugin_runtime_compatibility.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_plugin_runtime_compatibility.md")


if __name__ == "__main__":
    main()
