from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


WORKFLOW_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_ROOT = WORKFLOW_ROOT.parent
SCHEMA_PATH = WORKFLOW_ROOT / "configs" / "target_workflow.schema.json"
MANIFEST_SCHEMA_PATH = WORKFLOW_ROOT / "configs" / "workflow_manifest.schema.json"
BLOCKED_STAGES = (
    "model_feasibility",
    "reaction_evidence",
    "kinetic_prediction",
    "external_evidence",
    "engineering_feasibility",
    "construct_design",
)


class WorkflowValidationError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def project_root(explicit: Path | None = None) -> Path:
    return (explicit or Path(os.environ.get("METATWIN_PROJECT_ROOT", DEFAULT_PROJECT_ROOT))).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise WorkflowValidationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowValidationError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowValidationError(f"JSON document must be an object: {path}")
    return value


def validation_errors(config: dict[str, Any]) -> list[str]:
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(config), key=lambda item: list(item.absolute_path))
    ]

    compounds = [row.get("compound_id") for row in config.get("compounds", []) if isinstance(row, dict)]
    reactions = [row.get("reaction_id") for row in config.get("candidate_reactions", []) if isinstance(row, dict)]
    for label, values in (("compound_id", compounds), ("reaction_id", reactions)):
        duplicates = sorted({value for value in values if value is not None and values.count(value) > 1})
        errors.extend(f"duplicate {label}: {value}" for value in duplicates)
    known_compounds, known_reactions = set(compounds), set(reactions)
    for route in config.get("routes", []):
        if isinstance(route, dict):
            for reaction_id in route.get("reaction_ids", []):
                if reaction_id not in known_reactions:
                    errors.append(f"route {route.get('route_id')} references unknown reaction {reaction_id}")
    for pair in config.get("prediction_pairs", []):
        if isinstance(pair, dict):
            if pair.get("reaction_id") not in known_reactions:
                errors.append(f"prediction pair references unknown reaction {pair.get('reaction_id')}")
            if pair.get("substrate_compound_id") not in known_compounds:
                errors.append(f"prediction pair references unknown compound {pair.get('substrate_compound_id')}")
    return errors


def validate_config_path(config_path: Path) -> dict[str, Any]:
    config = load_json(config_path)
    errors = validation_errors(config)
    if errors:
        raise WorkflowValidationError("invalid target workflow config:\n" + "\n".join(f"- {item}" for item in errors))
    return config


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def render_readme(config: dict[str, Any]) -> str:
    target = config["target"]
    return (
        f"# Target Workflow: {target['target_name']}\n\n"
        f"Target ID: `{target['target_id']}`\n\n"
        "This workspace contains declared inputs only. It does not contain prediction results.\n\n"
        "## Generated Inputs\n\n"
        "- `inputs/compounds.csv`\n- `inputs/candidate_reactions.csv`\n- `inputs/routes.csv`\n"
        "- `inputs/prediction_pairs.csv`\n- `inputs/enzyme_search_terms.json`\n"
    )


def instantiate(config_path: Path, output_dir: Path | None = None, root: Path | None = None) -> Path:
    config_path = config_path.resolve()
    config = validate_config_path(config_path)
    root = project_root(root)
    target_dir = (output_dir or WORKFLOW_ROOT / "targets" / config["target"]["target_id"]).resolve()
    for directory in ("inputs", "outputs", "reports"):
        (target_dir / directory).mkdir(parents=True, exist_ok=True)
    artifacts = {
        "inputs/compounds.csv": (config["compounds"], ["compound_id", "name", "role", "formula", "charge", "smiles", "smiles_source", "model_metabolite_id"]),
        "inputs/candidate_reactions.csv": (config["candidate_reactions"], ["reaction_id", "name", "equation", "stoichiometry", "enzyme_ec_numbers", "reaction_role", "evidence_scope", "balance_expected"]),
        "inputs/routes.csv": (config["routes"], ["route_id", "name", "reaction_ids", "objective_metabolite_id", "route_risk_note"]),
        "inputs/prediction_pairs.csv": (config["prediction_pairs"], ["reaction_id", "enzyme_source", "substrate_compound_id", "sequence_source", "sequence", "sequence_path", "prediction_plugins"]),
    }
    generated_paths: list[Path] = []
    for relative, (rows, fields) in artifacts.items():
        write_csv(target_dir / relative, rows, fields)
        generated_paths.append(target_dir / relative)
    generated_payloads = {
        target_dir / "inputs" / "enzyme_search_terms.json": json.dumps(config["enzyme_search"], indent=2, ensure_ascii=False) + "\n",
        target_dir / "target_workflow_config.json": json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        target_dir / "README.md": render_readme(config),
    }
    for path, content in generated_payloads.items():
        path.write_text(content, encoding="utf-8")
        generated_paths.append(path)
    output_files = sorted(generated_paths)
    manifest = {
        "manifest_version": "1.0",
        "generated_at": utc_now(),
        "target_id": config["target"]["target_id"],
        "config": {"path": portable_path(config_path, root), "sha256": sha256_file(config_path)},
        "workspace": portable_path(target_dir, root),
        "counts": {
            "compounds": len(config["compounds"]), "candidate_reactions": len(config["candidate_reactions"]),
            "routes": len(config["routes"]), "prediction_pairs": len(config["prediction_pairs"]),
        },
        "outputs": [{"path": path.relative_to(target_dir).as_posix(), "sha256": sha256_file(path)} for path in output_files],
        "claims": {"contains_predictions": False, "contains_fba_results": False, "evidence_status": "declared_inputs_only"},
    }
    manifest_schema = load_json(MANIFEST_SCHEMA_PATH)
    manifest_errors = list(Draft202012Validator(manifest_schema).iter_errors(manifest))
    if manifest_errors:
        raise WorkflowValidationError(f"generated invalid workflow manifest: {manifest_errors[0].message}")
    (target_dir / "workflow_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target_dir


def workspace_cache_valid(target_dir: Path, config_hash: str) -> bool:
    manifest_path = target_dir / "workflow_manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = load_json(manifest_path)
        if manifest.get("config", {}).get("sha256") != config_hash:
            return False
        for artifact in manifest.get("outputs", []):
            path = target_dir / artifact["path"]
            if not path.is_file() or sha256_file(path) != artifact["sha256"]:
                return False
    except (KeyError, OSError, TypeError, WorkflowValidationError):
        return False
    return True
