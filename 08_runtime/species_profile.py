from __future__ import annotations

"""Species profile loader and validator.

Loads species-specific configuration from 09_configs/species/*.json,
validates against the JSON Schema, and provides a unified interface
for cross-organism metabolic prediction.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SPECIES_DIR = ROOT / "09_configs" / "species"
SCHEMA_PATH = SPECIES_DIR / "species_profile.schema.json"


class SpeciesProfileError(ValueError):
    pass


def _load_schema() -> dict[str, Any]:
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpeciesProfileError(f"cannot read species schema: {exc}") from exc


def load_species_profile(
    species_id: str,
    species_dir: Path | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """Load and optionally validate a species profile by its ID.

    Args:
        species_id: Machine-readable species identifier (e.g. 'yeast', 'ecoli').
        species_dir: Override directory for species configs.
        validate: Whether to validate against JSON Schema.

    Returns:
        Parsed species profile dict with resolved paths.

    Raises:
        SpeciesProfileError: If file missing, invalid JSON, or schema violation.
    """
    base = species_dir or SPECIES_DIR
    profile_path = base / f"{species_id}.json"
    if not profile_path.exists():
        available = sorted(p.stem for p in base.glob("*.json") if p.stem != "species_profile.schema")
        raise SpeciesProfileError(
            f"species profile '{species_id}' not found at {profile_path}. "
            f"Available: {', '.join(available)}"
        )
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpeciesProfileError(f"cannot read species profile {profile_path}: {exc}") from exc

    if validate:
        schema = _load_schema()
        try:
            jsonschema.Draft202012Validator(schema).validate(profile)
        except jsonschema.ValidationError as exc:
            raise SpeciesProfileError(
                f"species profile '{species_id}' failed schema validation: {exc.message}"
            ) from exc

    # Resolve GEM path relative to project root
    gem_path = Path(profile["gem"]["path"])
    if not gem_path.is_absolute():
        profile["gem"]["path_resolved"] = str((ROOT / gem_path).resolve())
    else:
        profile["gem"]["path_resolved"] = str(gem_path)

    profile["_profile_path"] = str(profile_path)
    return profile


def list_species(species_dir: Path | None = None) -> list[str]:
    """Return sorted list of available species IDs."""
    base = species_dir or SPECIES_DIR
    return sorted(
        p.stem for p in base.glob("*.json")
        if p.stem not in ("species_profile.schema",)
        and not p.stem.endswith(".schema")
    )


def get_cofactor_set(profile: dict[str, Any]) -> set[str]:
    """Extract cofactor whitelist as a set for fast lookup."""
    return set(profile.get("cofactor_whitelist", []))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load and validate species profiles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--species",
        type=str,
        default=None,
        help="Species ID to load (e.g. yeast, ecoli, cglutamicum). Omit to list all.",
    )
    parser.add_argument(
        "--species-dir",
        type=Path,
        default=None,
        help="Override species config directory.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip JSON Schema validation.",
    )
    args = parser.parse_args()

    if args.species is None:
        species = list_species(args.species_dir)
        print(f"Available species ({len(species)}):")
        for sid in species:
            print(f"  - {sid}")
        return 0

    try:
        profile = load_species_profile(
            args.species,
            species_dir=args.species_dir,
            validate=not args.no_validate,
        )
    except SpeciesProfileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(profile, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
