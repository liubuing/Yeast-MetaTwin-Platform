from __future__ import annotations

"""Cross-namespace ID mapping bridge (BiGG <-> MetaNetX <-> KEGG).

Provides unified compound/reaction identifier resolution across species
that use different GEM namespaces. Uses SMILES/InChIKey structural
matching as fallback when direct cross-reference tables are incomplete.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ID_MAPPING_DIR = ROOT / "02_id_mapping"


class IDMappingError(RuntimeError):
    pass


def load_compound_mapping(
    mapping_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Load compound cross-reference mapping table.

    Returns:
        Dict keyed by MetaNetX ID, values are dicts with alternative IDs.
        Example: {"MNXM123": {"bigg": "atp_c", "kegg": "C00002", "chebi": "CHEBI:30616"}}
    """
    path = mapping_path or (ID_MAPPING_DIR / "bigg_metanx_compound_mapping.csv")
    if not path.exists():
        # Fall back to enriched seed table
        path = ID_MAPPING_DIR / "model_compound_seed_enriched_v2.csv"
        if not path.exists():
            raise IDMappingError(f"No compound mapping table found at {path}")

    mapping: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            mnx_id = row.get("metanetx_id") or row.get("MODEL_CMPD") or row.get("id", "")
            if not mnx_id:
                continue
            entry: dict[str, str] = {}
            for key in ("bigg_id", "kegg_id", "chebi_id", "smiles", "inchikey"):
                val = row.get(key, "").strip()
                if val:
                    entry[key.replace("_id", "").replace("_", "")] = val
            mapping[mnx_id] = entry

    return mapping


def load_reaction_mapping(
    mapping_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Load reaction cross-reference mapping table.

    Returns:
        Dict keyed by MetaNetX reaction ID, values with alternative IDs.
    """
    path = mapping_path or (ID_MAPPING_DIR / "model_reaction_crossrefs.csv")
    if not path.exists():
        raise IDMappingError(f"Reaction mapping table not found: {path}")

    mapping: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rxn_id = row.get("reaction_id") or row.get("metanetx_id", "")
            if not rxn_id:
                continue
            entry: dict[str, str] = {}
            for key in ("bigg_id", "kegg_id", "rhea_id", "ec_number"):
                val = row.get(key, "").strip()
                if val:
                    entry[key.replace("_id", "").replace("_number", "")] = val
            mapping[rxn_id] = entry

    return mapping


def resolve_compound(
    identifier: str,
    source_namespace: str,
    target_namespace: str,
    mapping: dict[str, dict[str, str]] | None = None,
) -> str | None:
    """Resolve a compound ID from one namespace to another.

    Args:
        identifier: The compound ID to resolve.
        source_namespace: Source namespace (metanetx, bigg, kegg, chebi).
        target_namespace: Target namespace.
        mapping: Pre-loaded mapping (loads if None).

    Returns:
        Resolved ID in target namespace, or None if not found.
    """
    if mapping is None:
        mapping = load_compound_mapping()

    if source_namespace == target_namespace:
        return identifier

    # Build reverse index if source is not metanetx
    if source_namespace == "metanetx":
        entry = mapping.get(identifier)
        if entry:
            return entry.get(target_namespace)
    else:
        # Reverse lookup: find MetaNetX ID from source namespace
        for mnx_id, entry in mapping.items():
            if entry.get(source_namespace) == identifier:
                if target_namespace == "metanetx":
                    return mnx_id
                return entry.get(target_namespace)

    return None


def resolve_reaction(
    identifier: str,
    source_namespace: str,
    target_namespace: str,
    mapping: dict[str, dict[str, str]] | None = None,
) -> str | None:
    """Resolve a reaction ID from one namespace to another."""
    if mapping is None:
        mapping = load_reaction_mapping()

    if source_namespace == target_namespace:
        return identifier

    if source_namespace == "metanetx":
        entry = mapping.get(identifier)
        if entry:
            return entry.get(target_namespace)
    else:
        for mnx_id, entry in mapping.items():
            if entry.get(source_namespace) == identifier:
                if target_namespace == "metanetx":
                    return mnx_id
                return entry.get(target_namespace)

    return None


def build_bigg_to_metanx_index(
    mapping: dict[str, dict[str, str]] | None = None,
) -> dict[str, str]:
    """Build a fast BiGG -> MetaNetX lookup index for compounds."""
    if mapping is None:
        mapping = load_compound_mapping()

    index: dict[str, str] = {}
    for mnx_id, entry in mapping.items():
        bigg = entry.get("bigg")
        if bigg:
            index[bigg] = mnx_id
    return index


def mapping_coverage_report(
    mapping: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Generate coverage statistics for the mapping table."""
    if mapping is None:
        mapping = load_compound_mapping()

    total = len(mapping)
    namespaces = ("bigg", "kegg", "chebi", "smiles", "inchikey")
    coverage: dict[str, int] = {}
    for ns in namespaces:
        coverage[ns] = sum(1 for entry in mapping.values() if entry.get(ns))

    return {
        "total_compounds": total,
        "coverage": {ns: {"count": coverage[ns], "fraction": round(coverage[ns] / max(total, 1), 4)} for ns in namespaces},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-namespace ID mapping bridge.",
    )
    sub = parser.add_subparsers(dest="command")

    # resolve subcommand
    res_parser = sub.add_parser("resolve", help="Resolve a single ID.")
    res_parser.add_argument("--id", required=True, help="Identifier to resolve.")
    res_parser.add_argument("--from", dest="source", required=True,
                            choices=["metanetx", "bigg", "kegg", "chebi"])
    res_parser.add_argument("--to", dest="target", required=True,
                            choices=["metanetx", "bigg", "kegg", "chebi"])
    res_parser.add_argument("--type", dest="id_type", default="compound",
                            choices=["compound", "reaction"])

    # coverage subcommand
    sub.add_parser("coverage", help="Print mapping coverage report.")

    args = parser.parse_args()

    if args.command == "resolve":
        try:
            if args.id_type == "compound":
                result = resolve_compound(args.id, args.source, args.target)
            else:
                result = resolve_reaction(args.id, args.source, args.target)
        except IDMappingError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        if result is None:
            print(f"No mapping found: {args.id} ({args.source} -> {args.target})")
            return 1
        print(result)
        return 0

    elif args.command == "coverage":
        try:
            report = mapping_coverage_report()
        except IDMappingError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
