from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[1]
SOURCE_REPOSITORY = "https://github.com/Luo-SynBioLab/UniKP"
SOURCE_COMMIT = "3ad5576aaa2c8c0dd0e0b6c283c1d365ab23c6ea"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

DATASETS = (
    {
        "capability": "kcat_prediction",
        "path": "datasets/Kcat_combination_0918_wildtype_mutant.json",
        "source_role": "training_dataset",
        "overlap_evidence": "code/UniKP_kcat.py:124-170 loads this dataset and fits ExtraTreesRegressor",
    },
    {
        "capability": "km_prediction",
        "path": "datasets/Km_test_11722.pkl",
        "source_role": "training_and_internal_random_split_dataset",
        "overlap_evidence": "code/UniKP_Km.py:107-137 loads this dataset and performs a random train/test split",
    },
)

ASSETS = (
    "models/UniKP for kcat.pkl",
    "models/UniKP for Km.pkl",
    "models/UniKP for kcat_Km.pkl",
    "models/vocab.pkl",
    "models/trfm_12_23000.pkl",
    "models/prot_t5_xl_uniref50/config.json",
    "models/prot_t5_xl_uniref50/spiece.model",
    "models/prot_t5_xl_uniref50/pytorch_model.bin",
)

REQUIRED_PACKAGES = ("numpy", "pandas", "scikit-learn", "torch", "transformers", "sentencepiece")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_record(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    return {
        "path": relative_path,
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def package_versions() -> tuple[dict[str, str | None], list[str]]:
    versions: dict[str, str | None] = {}
    blockers: list[str] = []
    for package in REQUIRED_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
            blockers.append(f"missing runtime package: {package}")
    return versions, blockers


def build_manifests(
    inference_smoke_status: str = "not_run",
    inference_smoke_detail: str = "No successful end-to-end fixed-input inference result was supplied",
) -> tuple[dict[str, Any], dict[str, Any]]:
    if inference_smoke_status not in {"passed", "blocked", "not_run"}:
        raise ValueError("invalid inference_smoke_status")
    generated_at = datetime.now(timezone.utc).isoformat()
    datasets = []
    for spec in DATASETS:
        record = dict(spec)
        record.update(asset_record(spec["path"]))
        record["source_repository"] = SOURCE_REPOSITORY
        record["source_commit"] = SOURCE_COMMIT
        record["license"] = "GPL-3.0 claimed by upstream README; repository has no LICENSE file"
        record["license_verified"] = False
        record["training_overlap"] = True
        record["independent_benchmark_eligible"] = False
        datasets.append(record)

    benchmark_blockers = [
        "all locally available labeled datasets are used by upstream UniKP training/internal split code",
        "no independently sourced, versioned holdout dataset is present",
        "dataset redistribution license is not established by a repository LICENSE file",
    ]
    benchmark = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "plugin": "UniKP",
        "status": "blocked",
        "independent": False,
        "metrics_published": False,
        "metrics": {},
        "blockers": benchmark_blockers,
        "source": {
            "repository": SOURCE_REPOSITORY,
            "commit": SOURCE_COMMIT,
            "paper_doi": "10.1038/s41467-023-44113-1",
        },
        "datasets": datasets,
    }

    assets = [asset_record(path) for path in ASSETS]
    versions, runtime_blockers = package_versions()
    missing_assets = [record["path"] for record in assets if not record["exists"]]
    readiness_blockers = benchmark_blockers + runtime_blockers
    readiness_blockers.extend(f"missing asset: {path}" for path in missing_assets)
    if inference_smoke_status != "passed":
        readiness_blockers.append(f"inference smoke {inference_smoke_status}: {inference_smoke_detail}")
    readiness = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "plugin": "UniKP",
        "status": "blocked" if readiness_blockers else "ready",
        "inference_gate": "passed" if not runtime_blockers and not missing_assets and inference_smoke_status == "passed" else "blocked",
        "inference_smoke": {"status": inference_smoke_status, "detail": inference_smoke_detail},
        "benchmark_gate": "blocked",
        "blockers": readiness_blockers,
        "runtime": {"python": platform.python_version(), "executable": sys.executable, "packages": versions},
        "assets": assets,
        "output_contract": {
            "ood_field": "applicability.ood",
            "truncation_fields": ["transforms[].truncated", "transforms[].strategy"],
            "tree_member_interval_field": "uncertainty.tree_member_interval_log10",
            "tree_member_count_field": "uncertainty.tree_member_count",
            "tree_interval_calibrated": False,
        },
        "benchmark_manifest": "benchmark_manifest.json",
        "benchmark_manifest_sha256": None,
    }
    return benchmark, readiness


def write_manifests(
    benchmark_path: Path,
    readiness_path: Path,
    inference_smoke_status: str = "not_run",
    inference_smoke_detail: str = "No successful end-to-end fixed-input inference result was supplied",
) -> tuple[dict[str, Any], dict[str, Any]]:
    benchmark, readiness = build_manifests(inference_smoke_status, inference_smoke_detail)
    benchmark_path.write_text(json.dumps(benchmark, indent=2) + "\n", encoding="utf-8")
    readiness["benchmark_manifest_sha256"] = sha256_file(benchmark_path)
    readiness_path.write_text(json.dumps(readiness, indent=2) + "\n", encoding="utf-8")
    return benchmark, readiness


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest["status"] == "blocked" and manifest.get("metrics"):
        raise ValueError("blocked manifests cannot publish metrics")
    for record in manifest.get("datasets", []) + manifest.get("assets", []):
        digest = record.get("sha256")
        if record.get("exists") and not (isinstance(digest, str) and SHA256_PATTERN.fullmatch(digest)):
            raise ValueError(f"missing or invalid sha256 for {record['path']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit UniKP benchmark independence and inference readiness.")
    parser.add_argument("--benchmark-manifest", type=Path, default=ROOT / "benchmark_manifest.json")
    parser.add_argument("--readiness-manifest", type=Path, default=ROOT / "readiness_manifest.json")
    parser.add_argument("--inference-smoke-status", choices=("passed", "blocked", "not_run"), default="not_run")
    parser.add_argument("--inference-smoke-detail", default="No successful end-to-end fixed-input inference result was supplied")
    args = parser.parse_args(argv)
    benchmark, readiness = write_manifests(
        args.benchmark_manifest,
        args.readiness_manifest,
        args.inference_smoke_status,
        args.inference_smoke_detail,
    )
    validate_manifest(benchmark)
    validate_manifest(readiness)
    print(json.dumps({"benchmark": benchmark["status"], "readiness": readiness["status"], "blockers": readiness["blockers"]}, indent=2))
    return 0 if benchmark["status"] == readiness["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
