from __future__ import annotations

import argparse
import json
from pathlib import Path

from reaction_evidence_ml_utils import load_joblib_verified, verify_model_artifact


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a phase 2 reaction-evidence model against its manifest.")
    parser.add_argument("manifest", type=Path, help="Model manifest JSON path")
    parser.add_argument(
        "--trusted-load",
        action="store_true",
        help="After hash verification, deserialize the artifact. Use only for an artifact from a trusted source.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relative_model_path = manifest.get("artifact", {}).get("path")
    if not relative_model_path:
        raise ValueError("manifest does not contain artifact.path")
    model_path = (ROOT / relative_model_path).resolve()
    if not model_path.is_relative_to(ROOT.resolve()):
        raise ValueError("artifact path escapes the deployment root")
    verify_model_artifact(model_path, manifest_path)
    result = {"status": "verified", "artifact": str(model_path.relative_to(ROOT)), "deserialized": False}
    if args.trusted_load:
        load_joblib_verified(model_path, manifest_path, ["model_version"])
        result["deserialized"] = True
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
