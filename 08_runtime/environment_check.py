from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from deployment_config import DeploymentConfigError, load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
PROVENANCE_RUNTIME = ROOT / "10_generic_target_workflow" / "runtime"
sys.path.insert(0, str(PROVENANCE_RUNTIME))
from provenance import collect_provenance  # noqa: E402


def verify_asset_checksums(checksum_file: Path) -> list[dict[str, object]]:
    import hashlib

    results = []
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        expected, relative = line.split("  ", 1)
        path = ROOT / Path(relative)
        digest = hashlib.sha256()
        if path.is_file():
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            actual = digest.hexdigest()
        else:
            actual = None
        results.append({"path": relative, "exists": path.is_file(), "expected": expected, "actual": actual, "valid": actual == expected})
    return results


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Record and validate the MetaTwin runtime environment")
    result.add_argument("--output", type=Path, help="write the JSON report to this path")
    result.add_argument("--verify-assets", action="store_true", help="verify assets/checksums.sha256")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        config = load_deployment_config()
    except DeploymentConfigError as exc:
        print(json.dumps({"status": "invalid_config", "error": str(exc)}))
        return 2
    sources = {"deployment_config": Path(config["config_path"])}
    sources.update({f"model:{name}": Path(path) for name, path in config["models"].items()})
    report = collect_provenance(Path(config["base_dir"]), sources)
    report["configuration"] = {
        "version": config.get("version"),
        "source_project_available": Path(config["source_project_dir"]).is_dir(),
        "models_available": {name: Path(path).is_file() for name, path in config["models"].items()},
    }
    exit_code = 0
    if args.verify_assets:
        checksum_file = ROOT / "assets" / "checksums.sha256"
        checks = verify_asset_checksums(checksum_file) if checksum_file.is_file() else []
        report["asset_checks"] = checks
        if not checks or not all(item["valid"] for item in checks):
            exit_code = 3
    report["status"] = "ok" if exit_code == 0 else "failed"
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
