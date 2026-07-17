from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import cobra
from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "09_configs" / "deployment_config.json"
EVAL_DIR = ROOT / "06_evaluation"


def load_config() -> dict[str, Any]:
    return load_deployment_config()


def check_path(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    return {
        "path": path_text,
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
        "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
    }


def summarize_model(model_path: str, solver: str) -> dict[str, Any]:
    path_info = check_path(model_path)
    if not path_info["exists"]:
        return {"path_info": path_info, "load_ok": False, "error": "model file missing"}

    try:
        model = cobra.io.load_yaml_model(model_path)
        model.solver = solver
        solution = model.optimize()
        return {
            "path_info": path_info,
            "load_ok": True,
            "model_id": model.id,
            "reactions": len(model.reactions),
            "metabolites": len(model.metabolites),
            "genes": len(model.genes),
            "rxn_prefix_reactions": sum(rxn.id.startswith("rxn") for rxn in model.reactions),
            "fba_status": solution.status,
            "objective_value": float(solution.objective_value) if solution.objective_value is not None else None,
        }
    except Exception as exc:
        return {"path_info": path_info, "load_ok": False, "error": f"{type(exc).__name__}: {exc}"}


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 1 Deployment Verification",
        "",
        f"Generated: {payload['generated_at']}",
        f"Deployment: {payload['deployment_name']}",
        f"Version: {payload['version']}",
        "",
        "## Model Checks",
        "",
        "| Model | Exists | Load OK | Reactions | Metabolites | Genes | rxn* | FBA status | Objective |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for name, row in payload["models"].items():
        obj = row.get("objective_value")
        obj_text = "" if obj is None else f"{obj:.6g}"
        lines.append(
            f"| {name} | {row['path_info']['exists']} | {row.get('load_ok', False)} | "
            f"{row.get('reactions', '')} | {row.get('metabolites', '')} | {row.get('genes', '')} | "
            f"{row.get('rxn_prefix_reactions', '')} | {row.get('fba_status', '')} | {obj_text} |"
        )
    lines.extend(["", "## Audit Output Checks", "", "| Output | Exists | Size bytes |", "|---|---:|---:|"])
    for name, row in payload["audit_outputs"].items():
        lines.append(f"| {name} | {row['exists']} | {row.get('size_bytes', '')} |")

    lines.extend(["", "## Verdict", ""])
    if payload["phase1_pass"]:
        lines.append("Phase 1 deployment check passed. The integrated deployment can load the baseline and expanded models and access existing audit outputs.")
    else:
        lines.append("Phase 1 deployment check failed. Review missing paths or model load errors in the JSON report.")
    return "\n".join(lines) + "\n"


def main() -> None:
    config = load_config()
    solver = config["runtime"].get("default_solver", "glpk")
    model_payload = {name: summarize_model(path, solver) for name, path in config["models"].items() if name != "yeast_metatwin_lipid"}
    audit_payload = {name: check_path(path) for name, path in config["audit_outputs"].items()}
    phase1_pass = all(row.get("load_ok") for row in model_payload.values()) and all(row["exists"] for row in audit_payload.values())

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "deployment_name": config["deployment_name"],
        "version": config["version"],
        "models": model_payload,
        "audit_outputs": audit_payload,
        "phase1_pass": phase1_pass,
    }
    EVAL_DIR.mkdir(exist_ok=True)
    (EVAL_DIR / "phase1_deployment_verification.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase1_deployment_verification.md").write_text(render_markdown(payload), encoding="utf-8")
    print(EVAL_DIR / "phase1_deployment_verification.md")


if __name__ == "__main__":
    main()
