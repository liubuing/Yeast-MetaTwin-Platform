from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import pickle
import platform
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .catalog import FIXED_SMOKE_INPUTS, PLUGIN_SPECS, UNMANAGED_PLUGINS, AssetSpec, PackageSpec, PluginSpec
from .schema import PluginInput, RunStatus


SCHEMA_VERSION = "1.0.0"
REGISTRY_FIELDS = (
    "plugin",
    "plugin_version",
    "schema_version",
    "capability",
    "entrypoint",
    "status",
    "gate_exit_code",
    "gate_level",
    "required_assets_json",
    "missing_assets_json",
    "invalid_assets_json",
    "asset_sha256_json",
    "runtime_versions_json",
    "detail",
)


@dataclass(frozen=True)
class AssetCheck:
    path: str
    status: str
    sha256: str | None = None
    detail: str = ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_asset(plugin_root: Path, spec: AssetSpec, calculate_hashes: bool = False) -> AssetCheck:
    path = plugin_root / spec.relative_path
    if not path.exists():
        return AssetCheck(spec.relative_path, "missing")
    if spec.kind == "directory":
        if not path.is_dir():
            return AssetCheck(spec.relative_path, "invalid", detail="expected directory")
        missing_children = [child for child in spec.required_children if not (path / child).is_file()]
        if missing_children:
            return AssetCheck(spec.relative_path, "invalid", detail="missing children: " + ",".join(missing_children))
        return AssetCheck(spec.relative_path, "valid")
    if not path.is_file():
        return AssetCheck(spec.relative_path, "invalid", detail="expected file")
    if path.stat().st_size < spec.min_size_bytes:
        return AssetCheck(spec.relative_path, "invalid", detail=f"size {path.stat().st_size} < {spec.min_size_bytes}")
    observed = sha256_file(path) if calculate_hashes or spec.expected_sha256 else None
    if spec.expected_sha256 and observed != spec.expected_sha256:
        return AssetCheck(spec.relative_path, "invalid", observed, "sha256 mismatch")
    return AssetCheck(spec.relative_path, "valid", observed)


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for token in value.split("."):
        digits = "".join(character for character in token if character.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def check_packages(packages: tuple[PackageSpec, ...]) -> tuple[dict[str, str], list[str]]:
    versions: dict[str, str] = {"python": platform.python_version(), "executable": sys.executable}
    errors: list[str] = []
    for package in packages:
        try:
            version = importlib.metadata.version(package.distribution)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"missing package: {package.distribution}")
            continue
        versions[package.distribution] = version
        parsed = _version_tuple(version)
        if package.minimum and parsed < package.minimum:
            errors.append(f"{package.distribution} {version} < {'.'.join(map(str, package.minimum))}")
        if package.maximum_exclusive and parsed >= package.maximum_exclusive:
            errors.append(f"{package.distribution} {version} >= {'.'.join(map(str, package.maximum_exclusive))}")
    return versions, errors


def compatibility_probe(spec: PluginSpec, plugin_root: Path) -> tuple[list[str], list[str]]:
    if spec.name == "DLKcat":
        try:
            from .dlkcat import predict

            result = predict(PluginInput(**FIXED_SMOKE_INPUTS["DLKcat"]), plugin_root)
            return ([] if result.status == RunStatus.READY else list(result.messages)), []
        except Exception as exc:
            return [f"compatibility probe: {type(exc).__name__}: {exc}"], []
    if spec.name != "UniKP":
        return [], []
    errors: list[str] = []
    compatibility_warnings: list[str] = []
    code_dir = plugin_root / "UniKP" / "code"
    models_dir = plugin_root / "UniKP" / "models"
    if str(code_dir) not in sys.path:
        sys.path.insert(0, str(code_dir))
    try:
        import __main__
        import build_vocab
        import torch

        setattr(__main__, "WordVocab", build_vocab.WordVocab)
        torch.load(models_dir / "trfm_12_23000.pkl", map_location="cpu")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for filename in ("vocab.pkl", "UniKP for kcat.pkl", "UniKP for Km.pkl", "UniKP for kcat_Km.pkl"):
                with (models_dir / filename).open("rb") as handle:
                    loaded = pickle.load(handle)
                if filename.startswith("UniKP") and not hasattr(loaded, "predict"):
                    errors.append(f"{filename} has no predict method")
            if any("unpickle estimator" in str(item.message) for item in caught):
                runtime_version = importlib.metadata.version("scikit-learn")
                compatibility_warnings.append(
                    f"model pickle was serialized by scikit-learn 0.24.2 and is running under {runtime_version}"
                )
        config = json.loads((models_dir / "prot_t5_xl_uniref50" / "config.json").read_text(encoding="utf-8"))
        if config.get("model_type") != "t5" or config.get("d_model") != 1024:
            errors.append("ProtT5 config is incompatible with UniKP feature dimensions")
    except Exception as exc:
        errors.append(f"compatibility probe: {type(exc).__name__}: {exc}")
    return errors, sorted(set(compatibility_warnings))


def audit_plugin(spec: PluginSpec, plugin_root: Path, deep_smoke: bool = False, calculate_hashes: bool = False) -> list[dict[str, Any]]:
    checks = [check_asset(plugin_root, asset, calculate_hashes) for asset in spec.required_assets]
    missing = [check.path for check in checks if check.status == "missing"]
    invalid = [f"{check.path}: {check.detail}" for check in checks if check.status == "invalid"]
    hashes = {check.path: check.sha256 for check in checks if check.sha256}
    versions, package_errors = check_packages(spec.packages)
    smoke_error = ""
    try:
        fixed_input = PluginInput(**FIXED_SMOKE_INPUTS[spec.name])
    except Exception as exc:
        smoke_error = f"fixed input invalid: {type(exc).__name__}: {exc}"

    probe_errors: list[str] = []
    probe_warnings: list[str] = []
    if not missing and not invalid and not package_errors and not smoke_error:
        probe_errors, probe_warnings = compatibility_probe(spec, plugin_root)
    deep_result = None
    if deep_smoke and spec.name in {"DLKcat", "UniKP"} and not (missing or invalid or package_errors or smoke_error or probe_errors):
        if spec.name == "DLKcat":
            from .dlkcat import predict
        else:
            from .unikp import predict

        deep_result = predict(fixed_input, plugin_root)
        if deep_result.status != RunStatus.READY:
            probe_errors.extend(deep_result.messages or ("deep smoke returned no prediction",))

    blockers = missing + invalid + package_errors + ([smoke_error] if smoke_error else []) + probe_errors
    status = RunStatus.BLOCKED if blockers else RunStatus.READY
    detail = "; ".join(blockers) if blockers else "asset, runtime, fixed-input compatibility gate passed"
    if deep_result is not None and deep_result.status == RunStatus.READY:
        detail = "asset, runtime, and fixed-input inference smoke gate passed"
    if probe_warnings:
        detail += "; warning: " + " | ".join(probe_warnings)
    rows = []
    for capability in spec.capabilities:
        capability_status = status
        capability_detail = detail
        gate_level = "compatibility_smoke"
        if deep_result is not None:
            if capability == fixed_input.capability:
                gate_level = "inference_smoke"
            else:
                capability_detail = "asset, runtime, fixed-input feature pipeline, and capability model-load probe passed"
                if probe_warnings:
                    capability_detail += "; warning: " + " | ".join(probe_warnings)
        rows.append(
            {
            "plugin": spec.name,
            "plugin_version": spec.plugin_version,
            "schema_version": SCHEMA_VERSION,
            "capability": capability,
            "entrypoint": f"plugin_runtime.{spec.name.lower()}:predict" if spec.name in {"DLKcat", "UniKP"} else "",
            "status": capability_status.value,
            "gate_exit_code": 0 if capability_status == RunStatus.READY else 1,
            "gate_level": gate_level,
            "required_assets_json": json.dumps([asset.relative_path for asset in spec.required_assets], separators=(",", ":")),
            "missing_assets_json": json.dumps(missing, separators=(",", ":")),
            "invalid_assets_json": json.dumps(invalid, separators=(",", ":")),
            "asset_sha256_json": json.dumps(hashes, sort_keys=True, separators=(",", ":")),
            "runtime_versions_json": json.dumps(versions, sort_keys=True, separators=(",", ":")),
            "detail": capability_detail,
        }
        )
    return rows


def build_registry(plugin_root: Path, deep_smoke: bool = False, calculate_hashes: bool = False) -> list[dict[str, Any]]:
    rows = [row for spec in PLUGIN_SPECS for row in audit_plugin(spec, plugin_root, deep_smoke, calculate_hashes)]
    try:
        cobra_version = importlib.metadata.version("cobra")
        cobra_status, cobra_detail = RunStatus.READY.value, "COBRApy dependency and generic FBA executor are integrated"
    except importlib.metadata.PackageNotFoundError:
        cobra_version = ""
        cobra_status, cobra_detail = RunStatus.BLOCKED.value, "missing package: cobra"
    rows.append({
        "plugin": "COBRApy", "plugin_version": cobra_version or "unavailable", "schema_version": SCHEMA_VERSION,
        "capability": "fba_execution", "entrypoint": "plugin_runtime.cobra_fba:CobraFbaExecutor",
        "status": cobra_status, "gate_exit_code": 0 if cobra_status == RunStatus.READY.value else 1,
        "gate_level": "dependency_and_entrypoint", "required_assets_json": "[]", "missing_assets_json": "[]",
        "invalid_assets_json": "[]", "asset_sha256_json": "{}",
        "runtime_versions_json": json.dumps({"python": platform.python_version(), "cobra": cobra_version}, sort_keys=True),
        "detail": cobra_detail,
    })
    for name, capability, detail in UNMANAGED_PLUGINS:
        rows.append(
            {
                "plugin": name,
                "plugin_version": "unmanaged",
                "schema_version": SCHEMA_VERSION,
                "capability": capability,
                "entrypoint": "",
                "status": RunStatus.UNSUPPORTED.value,
                "gate_exit_code": 1,
                "gate_level": "not_integrated",
                "required_assets_json": "[]",
                "missing_assets_json": "[]",
                "invalid_assets_json": "[]",
                "asset_sha256_json": "{}",
                "runtime_versions_json": "{}",
                "detail": detail,
            }
        )
    return rows


def write_registry(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def gate_exit_code(rows: list[dict[str, Any]], selected_plugins: set[str] | None = None) -> int:
    selected = [row for row in rows if selected_plugins is None or row["plugin"] in selected_plugins]
    return 0 if selected and all(row["status"] == RunStatus.READY.value for row in selected) else 1


def main(argv: list[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parents[1]
    default_registry = Path(__file__).resolve().parents[2] / "09_configs" / "prediction_plugins.csv"
    parser = argparse.ArgumentParser(description="Audit prediction plugin assets and generate the machine-readable registry.")
    parser.add_argument("--plugin-root", type=Path, default=default_root)
    parser.add_argument("--registry", type=Path, default=default_registry)
    parser.add_argument("--plugin", action="append", choices=[spec.name for spec in PLUGIN_SPECS])
    parser.add_argument("--deep-smoke", action="store_true")
    parser.add_argument("--hash-assets", action="store_true")
    parser.add_argument("--merge-selected", action="store_true", help="replace only --plugin rows in an existing registry")
    args = parser.parse_args(argv)

    rows = build_registry(args.plugin_root, args.deep_smoke, args.hash_assets)
    if args.merge_selected:
        if not args.plugin:
            parser.error("--merge-selected requires at least one --plugin")
        selected_names = set(args.plugin)
        replacements = [row for row in rows if row["plugin"] in selected_names]
        retained: list[dict[str, Any]] = []
        if args.registry.is_file():
            with args.registry.open("r", encoding="utf-8", newline="") as handle:
                retained = [row for row in csv.DictReader(handle) if row["plugin"] not in selected_names]
        rows = retained + replacements
    write_registry(args.registry, rows)
    selected = set(args.plugin) if args.plugin else {spec.name for spec in PLUGIN_SPECS}
    summary = [
        {key: row[key] for key in ("plugin", "capability", "status", "gate_exit_code", "detail")}
        for row in rows
        if row["plugin"] in selected
    ]
    print(json.dumps(summary, indent=2))
    return gate_exit_code(rows, selected)


if __name__ == "__main__":
    raise SystemExit(main())
