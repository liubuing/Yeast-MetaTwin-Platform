from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from executors import EXECUTORS

from provenance import collect_provenance

from workflow import (
    BLOCKED_STAGES,
    SCHEMA_PATH,
    WORKFLOW_ROOT,
    WorkflowValidationError,
    instantiate,
    load_json,
    portable_path,
    project_root,
    sha256_file,
    utc_now,
    validate_config_path,
    workspace_cache_valid,
)


EXIT_INVALID = 2
EXIT_BLOCKED = 3
EXIT_NOT_READY = 4
BLOCKER_REASONS = {
    "model_feasibility": "COBRA model or executor dependency is unavailable",
    "reaction_evidence": "no verified reaction-evidence model manifest is available",
    "kinetic_prediction": "third-party predictor assets plus target enzyme sequences are not declared through a generic adapter",
    "external_evidence": "external source access and a target-agnostic evidence collector are not registered",
    "engineering_feasibility": "no target-agnostic engineering feasibility executor is registered",
    "construct_design": "no target-agnostic construct design executor is registered",
}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def command_validate(args: argparse.Namespace) -> int:
    config = validate_config_path(args.config.resolve())
    emit({"command": "validate", "status": "completed", "target_id": config["target"]["target_id"], "schema": SCHEMA_PATH.name})
    return 0


def command_instantiate(args: argparse.Namespace) -> int:
    root = project_root(args.project_root)
    target_dir = instantiate(args.config, args.output_dir, root)
    emit({"command": "instantiate", "status": "completed", "workspace": portable_path(target_dir, root)})
    return 0


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{stamp}-{uuid.uuid4().hex[:8]}"


def plugin_readiness(config: dict[str, Any], root: Path) -> tuple[bool, str]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    requested = {
        (request["plugin"], request["capability"])
        for pair in config.get("prediction_pairs", [])
        for request in pair.get("prediction_plugins", [])
    }
    if not requested:
        return True, "no prediction plugins requested"
    registry_path = root / "09_configs" / "prediction_plugins.csv"
    if not registry_path.is_file():
        return False, "plugin registry is missing"
    with registry_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    indexed = {(row["plugin"], row["capability"]): row for row in rows}
    failures = []
    for key in sorted(requested):
        row = indexed.get(key)
        if row is None:
            failures.append(f"{key[0]}:{key[1]} is absent")
        elif row.get("status") != "ready":
            failures.append(f"{key[0]}:{key[1]} is {row.get('status')}")
        elif not row.get("entrypoint"):
            failures.append(f"{key[0]}:{key[1]} has no entrypoint")
        else:
            module_name, _, attribute = row["entrypoint"].partition(":")
            try:
                module = importlib.import_module(module_name)
                getattr(module, attribute)
            except (ImportError, AttributeError) as exc:
                failures.append(f"{key[0]}:{key[1]} entrypoint cannot import: {exc}")
    return not failures, "; ".join(failures) if failures else f"{len(requested)} requested plugin capabilities are ready"


def reaction_evidence_readiness(root: Path) -> tuple[bool, str]:
    schema_path = root / "03_models" / "reaction_evidence_model_manifest.schema.json"
    try:
        schema = load_json(schema_path)
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return False, f"reaction-evidence manifest schema invalid: {exc}"
    errors = []
    verified_versions = set()
    expected_versions = {"phase2_reaction_evidence_baseline_v1", "phase2_reaction_evidence_pu_v2"}
    manifest_paths = sorted((root / "03_models").glob("*reaction_evidence*_manifest_v2.json"))
    for manifest_path in manifest_paths:
        try:
            manifest = load_json(manifest_path)
            validation = list(Draft202012Validator(schema).iter_errors(manifest))
            if validation:
                errors.append(f"{manifest_path.name}: {validation[0].message}")
                continue
            records = [manifest["artifact"], manifest["model_card"], *manifest["data_artifacts"], *manifest["source_artifacts"], *manifest["code_artifacts"], manifest["runtime"]["reproduction_spec"]]
            for record in records:
                path = (root / record["path"]).resolve()
                if not path.is_relative_to(root.resolve()):
                    raise WorkflowValidationError(f"declared path escapes project root: {record['path']}")
                if not path.is_file():
                    raise WorkflowValidationError(f"declared file is missing: {record['path']}")
                if path.stat().st_size != record["bytes"]:
                    raise WorkflowValidationError(f"byte-size mismatch: {record['path']}")
                if sha256_file(path) != record["sha256"]:
                    raise WorkflowValidationError(f"SHA256 mismatch: {record['path']}")
            verified_versions.add(manifest["model_version"])
        except (KeyError, OSError, WorkflowValidationError) as exc:
            errors.append(f"{manifest_path.name}: {exc}")
    missing = sorted(expected_versions - verified_versions)
    if missing:
        errors.append(f"missing verified model versions: {', '.join(missing)}")
    if errors:
        return False, "; ".join(errors)
    return True, f"verified {len(verified_versions)} versioned reaction-evidence manifests without deserialization"


def stage_readiness(config: dict[str, Any], root: Path) -> dict[str, tuple[bool, str]]:
    readiness = {}
    for stage in BLOCKED_STAGES:
        if not stage_configured(stage, config):
            readiness[stage] = (True, "stage is not configured")
        elif stage in EXECUTORS:
            result = EXECUTORS[stage].readiness(config, root)
            if stage == "model_feasibility":
                registry_config = {"prediction_pairs": [{"prediction_plugins": [{"plugin": "COBRApy", "capability": "fba_execution"}]}]}
                registry_ready, registry_detail = plugin_readiness(registry_config, root)
                readiness[stage] = (result.ready and registry_ready, f"{result.detail}; {registry_detail}")
            else:
                readiness[stage] = (result.ready, result.detail)
        elif stage == "reaction_evidence":
            readiness[stage] = reaction_evidence_readiness(root)
        else:
            readiness[stage] = (False, BLOCKER_REASONS[stage])
    return readiness


def stage_configured(stage: str, config: dict[str, Any]) -> bool:
    if stage == "model_feasibility":
        return "fba_validation" in config
    if stage == "reaction_evidence":
        return bool(config.get("reaction_evidence", {}).get("enabled", False))
    if stage == "kinetic_prediction":
        return bool(config.get("prediction_pairs"))
    if stage == "external_evidence":
        return "external_evidence" in config
    if stage == "engineering_feasibility":
        layers = config.get("engineering_layers", {})
        return bool(layers.get("family_sanity_filter", {}).get("enabled") or layers.get("specialized_feasibility_layers") or layers.get("feasibility_rules"))
    if stage == "construct_design":
        return bool(config.get("engineering_layers", {}).get("construct_design", {}).get("enabled"))
    return False


def command_run(args: argparse.Namespace) -> int:
    root = project_root(args.project_root)
    config_path = args.config.resolve()
    config = validate_config_path(config_path)
    config_hash = sha256_file(config_path)
    runs_root = (args.runs_dir or Path(os.environ.get("METATWIN_RUNS_DIR", root / "runs"))).resolve()
    run_id = args.run_id or new_run_id()
    run_dir = runs_root / run_id
    state_path, log_path = run_dir / "state.json", run_dir / "events.jsonl"
    if run_dir.exists() and not args.resume:
        raise WorkflowValidationError(f"run already exists; pass --resume: {run_id}")
    previous = load_json(state_path) if args.resume and state_path.exists() else None
    if args.resume and previous is None:
        raise WorkflowValidationError(f"cannot resume missing run: {run_id}")
    if previous and previous.get("input", {}).get("sha256") != config_hash:
        raise WorkflowValidationError("resume rejected: configuration hash changed")
    run_dir.mkdir(parents=True, exist_ok=True)
    environment_path = run_dir / "environment.json"
    write_json(environment_path, collect_provenance(root, {"workflow_config": config_path}))
    target_dir = (args.output_dir or WORKFLOW_ROOT / "targets" / config["target"]["target_id"]).resolve()
    state: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "dry_run": args.dry_run,
        "started_at": previous.get("started_at", utc_now()) if previous else utc_now(),
        "updated_at": utc_now(),
        "input": {"path": portable_path(config_path, root), "sha256": config_hash},
        "workspace": portable_path(target_dir, root),
        "stages": [],
    }
    readiness = stage_readiness(config, root)

    def record(name: str, status: str, detail: str) -> None:
        event = {"at": utc_now(), "run_id": run_id, "stage": name, "status": status, "detail": detail}
        state["stages"].append(event)
        state["updated_at"] = event["at"]
        write_json(state_path, state)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    if args.dry_run:
        record("validate", "planned", "configuration will be validated against the canonical schema")
        record("instantiate", "planned", f"declared inputs will be materialized at {portable_path(target_dir, root)}")
        for stage in BLOCKED_STAGES:
            ready, detail = readiness[stage]
            status = "planned_skipped" if not stage_configured(stage, config) else ("planned" if ready else "planned_blocked")
            record(stage, status, detail)
        state["status"] = "dry_run_completed"
        exit_code = 0
    else:
        old_completed = {item["stage"] for item in (previous or {}).get("stages", []) if item.get("status") in {"completed", "cached"}}
        record("validate", "cached" if "validate" in old_completed else "completed", "canonical schema and semantic references valid")
        if "instantiate" in old_completed and workspace_cache_valid(target_dir, config_hash):
            record("instantiate", "cached", "resumed from matching input and output hashes")
        else:
            instantiate(config_path, target_dir, root)
            record("instantiate", "completed", "declared input workspace generated")
        blocked_stages = []
        generated_run_files: list[Path] = []
        for stage in BLOCKED_STAGES:
            if not stage_configured(stage, config):
                record(stage, "skipped", "stage is not configured")
                continue
            ready, detail = readiness[stage]
            if not ready or stage not in EXECUTORS:
                blocked_stages.append(stage)
                record(stage, "blocked", detail)
                continue
            result = EXECUTORS[stage].execute(config, root, run_dir / "artifacts" / stage)
            generated_run_files.extend(sorted((run_dir / "artifacts" / stage).glob("*.json")))
            record(stage, result.get("status", "completed"), f"{result['executor']} finished")
        state["status"] = "blocked" if blocked_stages else "completed"
        exit_code = EXIT_BLOCKED if blocked_stages else 0
    state["finished_at"] = utc_now()
    state["updated_at"] = state["finished_at"]
    write_json(state_path, state)
    files = [state_path, log_path, environment_path, *locals().get("generated_run_files", [])]
    manifest = {
        "manifest_version": "1.0",
        "run_id": run_id,
        "status": state["status"],
        "input": state["input"],
        "artifacts": [{"path": path.relative_to(run_dir).as_posix(), "sha256": sha256_file(path)} for path in files],
        "workspace_manifest": portable_path(target_dir / "workflow_manifest.json", root) if not args.dry_run else None,
        "claims": {
            "contains_predictions": any(path.name == "kinetic_predictions.json" and json.loads(path.read_text(encoding="utf-8"))["result_counts"]["ready"] > 0 for path in files),
            "contains_fba_results": any(path.name == "fba_results.json" for path in files),
        },
    }
    write_json(run_dir / "manifest.json", manifest)
    emit({"command": "run", "run_id": run_id, "status": state["status"], "run_dir": portable_path(run_dir, root)})
    return exit_code


def command_verify_release(args: argparse.Namespace) -> int:
    root = project_root(args.project_root)
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "passed" if passed else "failed", "detail": detail})

    try:
        schema = load_json(SCHEMA_PATH)
        Draft202012Validator.check_schema(schema)
        check("canonical_schema", schema.get("$schema", "").endswith("2020-12/schema"), SCHEMA_PATH.name)
    except Exception as exc:  # readiness must report all failures in one document
        check("canonical_schema", False, str(exc))
    formal_schemas = [
        path
        for path in root.rglob("*schema*.json")
        if '"$schema"' in path.read_text(encoding="utf-8", errors="ignore")
        and "target-workflow" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    check("single_formal_contract", formal_schemas == [SCHEMA_PATH], f"found {len(formal_schemas)} formal target-workflow schema(s)")
    configs = [
        WORKFLOW_ROOT / "configs" / "target_workflow_template.json",
        *sorted((WORKFLOW_ROOT / "examples").glob("target_workflow_*.json")),
    ]
    config_errors = []
    for path in configs:
        try:
            validate_config_path(path)
        except WorkflowValidationError as exc:
            config_errors.append(f"{path.name}: {exc}")
    check("shipped_configs", not config_errors, "; ".join(config_errors) if config_errors else f"validated {len(configs)} configs")
    required = [root / "requirements-generic.txt", root / "requirements-dev.txt", root / ".github" / "workflows" / "generic-workflow-ci.yml"]
    missing = [portable_path(path, root) for path in required if not path.is_file()]
    check("release_infrastructure", not missing, f"missing: {', '.join(missing)}" if missing else "dependencies and CI present")
    sample_path = WORKFLOW_ROOT / "examples" / "target_workflow_lactate_dry_run.json"
    sample_config = validate_config_path(sample_path)
    execution = stage_readiness(sample_config, root)
    blockers = [{"stage": stage, "reason": detail} for stage, (ready, detail) in execution.items() if stage_configured(stage, sample_config) and not ready]
    smoke_error = None
    if not blockers:
        try:
            with tempfile.TemporaryDirectory() as directory:
                artifact_root = Path(directory)
                for stage in BLOCKED_STAGES:
                    if stage_configured(stage, sample_config):
                        EXECUTORS[stage].execute(sample_config, root, artifact_root / stage)
        except Exception as exc:
            smoke_error = f"{type(exc).__name__}: {exc}"
    check("complete_reference_workflow_smoke", not blockers and smoke_error is None, smoke_error or f"completed all configured stages for {sample_path.name}")
    core_ready = all(item["status"] == "passed" for item in checks)
    execution_ready = not blockers and smoke_error is None
    report = {
        "gate": "generic-workflow-release",
        "status": "ready" if core_ready and execution_ready else "blocked",
        "checked_at": utc_now(),
        "core_contract_ready": core_ready,
        "execution_ready": execution_ready,
        "checks": checks,
        "blocked_capabilities": blockers,
    }
    report_path = (args.report or root / "readiness-generic-workflow.json").resolve()
    write_json(report_path, report)
    emit({"command": "verify-release", "status": report["status"], "report": portable_path(report_path, root)})
    return 0 if core_ready and execution_ready else EXIT_NOT_READY


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="metatwin-workflow", description="Generic target workflow CLI")
    subparsers = result.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--config", required=True, type=Path)
    validate.set_defaults(handler=command_validate)
    create = subparsers.add_parser("instantiate")
    create.add_argument("--config", required=True, type=Path)
    create.add_argument("--output-dir", type=Path)
    create.add_argument("--project-root", type=Path)
    create.set_defaults(handler=command_instantiate)
    run = subparsers.add_parser("run")
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--output-dir", type=Path)
    run.add_argument("--runs-dir", type=Path)
    run.add_argument("--project-root", type=Path)
    run.add_argument("--run-id")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--resume", action="store_true")
    run.set_defaults(handler=command_run)
    verify = subparsers.add_parser("verify-release")
    verify.add_argument("--project-root", type=Path)
    verify.add_argument("--report", type=Path)
    verify.set_defaults(handler=command_verify_release)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except WorkflowValidationError as exc:
        emit({"command": args.command, "status": "failed", "error": str(exc)})
        return EXIT_INVALID
    except Exception as exc:
        emit({"command": args.command, "status": "failed", "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
