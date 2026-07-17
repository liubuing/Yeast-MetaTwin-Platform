from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from data_quality_gate import load_smiles_parser, run_gate


ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "02_id_mapping"
EVAL_DIR = ROOT / "06_evaluation"
INPUT = MAP_DIR / "model_compound_seed_enriched.csv"
OUTPUT = MAP_DIR / "model_compound_seed_enriched_v2.csv"
PROVENANCE = MAP_DIR / "model_compound_structure_enrichment_v2_provenance.csv"
MANUAL_REVIEW = MAP_DIR / "model_compound_structure_manual_review_v2.csv"
REPORT_JSON = EVAL_DIR / "phase2_compound_structure_enrichment_v2.json"
REPORT_MD = EVAL_DIR / "phase2_compound_structure_enrichment_v2.md"
GATE_DIR = EVAL_DIR / "data_quality_gate_enriched_v2"
GATE_CONFIG = GATE_DIR / "data_quality_gate_enriched_v2.json"
YMDB_RE = re.compile(r"YMDB\d{5}", re.IGNORECASE)
PUBCHEM_RE = re.compile(r"pubchem\.compound/(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class Candidate:
    structure: str
    source_database: str
    source_record_id: str
    source_file: str
    method: str
    confidence: str
    formula: str = ""


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize_name(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def normalize_chebi(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return f"CHEBI:{digits}" if digits else ""


def add(index: dict[str, list[Candidate]], key: str, candidate: Candidate) -> None:
    if key and candidate.structure:
        index[key].append(candidate)


def select_candidate(
    candidates: Iterable[Candidate], target_formula: str, parse_structure
) -> tuple[Candidate | None, str, int]:
    parseable = [candidate for candidate in candidates if parse_structure(candidate.structure)]
    compatible = [
        candidate for candidate in parseable
        if not target_formula or not candidate.formula or candidate.formula == target_formula
    ]
    if parseable and not compatible:
        return None, "formula_conflict", len(parseable)
    structures = {candidate.structure for candidate in compatible}
    if len(structures) > 1:
        return None, "multiple_structures_for_key", len(compatible)
    if not compatible:
        return None, "no_parseable_local_structure", 0
    return compatible[0], "mapped", len(compatible)


def source_roots() -> list[Path]:
    parent = ROOT.parent
    roots = [parent / "Yeast-MetaTwin-zenodo", parent / "Yeast-MetaTwin"]
    return [root for root in roots if root.exists()]


def first_asset(roots: list[Path], relative: str) -> Path:
    for root in roots:
        path = root / relative
        if path.exists():
            return path
    raise FileNotFoundError(relative)


def load_model_xrefs(roots: list[Path]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    path = first_asset(roots, "Data/yeast-GEM-final.csv")
    pubchem: dict[str, list[str]] = defaultdict(list)
    ymdb: dict[str, list[str]] = defaultdict(list)
    for row in read_csv(path):
        model_id = row.get("REPLACEMENT ID", "")
        miriam = row.get("MIRIAM", "")
        pubchem[model_id].extend(PUBCHEM_RE.findall(miriam))
        ymdb[model_id].extend(YMDB_RE.findall(miriam.upper()))
    return pubchem, ymdb


def build_indices(rows: list[dict[str, str]], roots: list[Path], parse_structure):
    indices: dict[str, dict[str, list[Candidate]]] = {
        key: defaultdict(list) for key in ("ymdb", "mnx", "chebi", "kegg", "pubchem", "name")
    }
    assets: list[str] = []

    ymdb_path = first_asset(roots, "Data/database/ymdb/ymdb.csv")
    assets.append(str(ymdb_path))
    for row in read_csv(ymdb_path):
        candidate = Candidate(row["SMILES"], "YMDB", row["ID"], str(ymdb_path), "exact_ymdb_id", "high")
        add(indices["ymdb"], row["ID"].upper(), candidate)
        add(indices["name"], normalize_name(row["NAME"]), Candidate(
            row["SMILES"], "YMDB", row["ID"], str(ymdb_path), "unique_normalized_name", "medium"
        ))

    kegg_path = first_asset(roots, "Data/database/kegg_compound.txt")
    assets.append(str(kegg_path))
    for row in read_csv(kegg_path, "\t"):
        candidate = Candidate(
            row.get("SMILES", ""), "KEGG", row.get("KEGG", ""), str(kegg_path),
            "exact_kegg_id", "high", row.get("Formula", "")
        )
        add(indices["kegg"], row.get("KEGG", ""), candidate)

    for filename, id_column in (("chebi_id_smiles.csv", "ChEBI ID"), ("chebi_second_id_smiles.csv", "Secondary ChEBI ID")):
        path = first_asset(roots, f"Data/database/{filename}")
        assets.append(str(path))
        for row in read_csv(path):
            record_id = normalize_chebi(row.get(id_column, ""))
            add(indices["chebi"], record_id, Candidate(
                row.get("SMILES", ""), "ChEBI", record_id, str(path), "exact_chebi_id", "high"
            ))

    names_path = first_asset(roots, "Data/yeast_gem_smiles.json")
    assets.append(str(names_path))
    names = json.loads(names_path.read_text(encoding="utf-8"))
    for name, structure in names.items():
        add(indices["name"], normalize_name(name), Candidate(
            structure, "Yeast-GEM", name, str(names_path), "unique_normalized_name", "medium"
        ))

    target_mnx = {row.get("metanetx_id", "") for row in rows if row.get("metanetx_id")}
    depr_path = first_asset(roots, "Data/database/mnx_chem_depr.tsv")
    assets.append(str(depr_path))
    replacements: dict[str, set[str]] = defaultdict(set)
    with depr_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("deprecated_ID") in target_mnx:
                replacements[row["deprecated_ID"]].add(row["ID"])
    replacement_to_deprecated: dict[str, list[str]] = defaultdict(list)
    for deprecated_id, replacement_ids in replacements.items():
        for replacement_id in replacement_ids:
            replacement_to_deprecated[replacement_id].append(deprecated_id)

    mnx_path = first_asset(roots, "Data/database/MNXmetabolite_smile.csv")
    assets.append(str(mnx_path))
    with mnx_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("MNX_ID") in target_mnx:
                add(indices["mnx"], row["MNX_ID"], Candidate(
                    row.get("SMILES", ""), "MetaNetX", row["MNX_ID"], str(mnx_path),
                    "exact_metanetx_id", "high", row.get("formula", "")
                ))
            for deprecated_id in replacement_to_deprecated.get(row.get("MNX_ID", ""), []):
                add(indices["mnx"], deprecated_id, Candidate(
                    row.get("SMILES", ""), "MetaNetX", f"{deprecated_id}->{row['MNX_ID']}",
                    f"{depr_path}|{mnx_path}", "exact_metanetx_deprecated_redirect", "high",
                    row.get("formula", "")
                ))

    pubchem_xrefs, _ = load_model_xrefs(roots)
    target_cids = {cid for values in pubchem_xrefs.values() for cid in values}
    sdf_path = first_asset(roots, "Data/database/ChEBI_complete_3star.sdf")
    assets.append(str(sdf_path))
    if target_cids:
        properties: dict[str, str] = {}
        current_property = ""
        with sdf_path.open(encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
                line = raw_line.rstrip("\r\n")
                if line == "$$$$":
                    cids = re.findall(r"CID:\s*(\d+)", properties.get("PubChem Database Links", ""))
                    for cid in set(cids) & target_cids:
                        add(indices["pubchem"], cid, Candidate(
                            properties.get("SMILES", ""), "PubChem/ChEBI", cid, str(sdf_path),
                            "exact_pubchem_cid_via_chebi_sdf", "high"
                        ))
                    properties, current_property = {}, ""
                elif line.startswith("> <") and line.endswith(">"):
                    current_property = line[3:-1]
                    properties[current_property] = ""
                elif current_property and line:
                    properties[current_property] += ("\n" if properties[current_property] else "") + line

    return indices, assets, pubchem_xrefs


def enrich(rows: list[dict[str, str]], indices, pubchem_xrefs, parse_structure):
    output_rows: list[dict[str, str]] = []
    provenance: list[dict[str, str]] = []
    methods = Counter()
    for original in rows:
        row = dict(original)
        structure = row.get("smiles", "")
        if structure and parse_structure(structure):
            output_rows.append(row)
            continue

        ymdb_ids = sorted(set(YMDB_RE.findall(row.get("primary_name", "").upper())))
        stable_tiers = [
            ("exact_ymdb_id", [candidate for key in ymdb_ids for candidate in indices["ymdb"].get(key, [])], "|".join(ymdb_ids)),
            ("exact_metanetx_id", indices["mnx"].get(row.get("metanetx_id", ""), []), row.get("metanetx_id", "")),
            ("exact_chebi_id", indices["chebi"].get(normalize_chebi(row.get("chebi_id", "")), []), normalize_chebi(row.get("chebi_id", ""))),
            ("exact_kegg_id", indices["kegg"].get(row.get("kegg_id", ""), []), row.get("kegg_id", "")),
            ("exact_pubchem_cid_via_chebi_sdf", [candidate for cid in pubchem_xrefs.get(row["model_metabolite_id"], []) for candidate in indices["pubchem"].get(cid, [])], "|".join(pubchem_xrefs.get(row["model_metabolite_id"], []))),
            ("unique_normalized_name", indices["name"].get(normalize_name(row.get("primary_name", "")), []), normalize_name(row.get("primary_name", ""))),
        ]
        attempted = []
        decision = "unresolved"
        reason = "local_key_space_exhausted"
        chosen = None
        candidate_count = 0
        matched_key = ""
        for method, candidates, key in stable_tiers:
            attempted.append(method)
            if not candidates:
                continue
            chosen, reason, candidate_count = select_candidate(candidates, row.get("formula", ""), parse_structure)
            matched_key = key
            if chosen:
                decision = "mapped"
                break
            if reason in {"formula_conflict", "multiple_structures_for_key"}:
                decision = "manual_review"
                break

        if chosen:
            row["smiles"] = chosen.structure
            row["mapping_source"] = chosen.source_file
            row["confidence_level"] = chosen.confidence
            row["structure_mapping_method_v2"] = chosen.method
            if chosen.source_database == "YMDB":
                row["ymdb_id"] = chosen.source_record_id
            methods[chosen.method] += 1
        output_rows.append(row)
        provenance.append({
            "compound_uid": row.get("compound_uid", ""),
            "model_metabolite_id": row.get("model_metabolite_id", ""),
            "primary_name": row.get("primary_name", ""),
            "formula": row.get("formula", ""),
            "previous_structure_status": "parse_failed" if structure else "missing",
            "decision": decision,
            "reason": reason,
            "matched_key": matched_key,
            "source_database": chosen.source_database if chosen else "",
            "source_record_id": chosen.source_record_id if chosen else "",
            "source_file": chosen.source_file if chosen else "",
            "method": chosen.method if chosen else "",
            "confidence_level": chosen.confidence if chosen else "",
            "candidate_count": str(candidate_count),
            "attempted_key_spaces": "|".join(attempted),
        })
    return output_rows, provenance, methods


def audit_key_spaces(rows, indices, pubchem_xrefs, parse_structure) -> dict[str, dict[str, int]]:
    audit = {
        method: {"rows_with_key": 0, "rows_with_local_candidate": 0, "rows_with_parseable_candidate": 0}
        for method in (
            "exact_ymdb_id", "exact_metanetx_id", "exact_chebi_id", "exact_kegg_id",
            "exact_pubchem_cid_via_chebi_sdf", "unique_normalized_name",
        )
    }
    for row in rows:
        if row.get("smiles") and parse_structure(row["smiles"]):
            continue
        ymdb_ids = sorted(set(YMDB_RE.findall(row.get("primary_name", "").upper())))
        pubchem_ids = pubchem_xrefs.get(row["model_metabolite_id"], [])
        definitions = {
            "exact_ymdb_id": (ymdb_ids, [candidate for key in ymdb_ids for candidate in indices["ymdb"].get(key, [])]),
            "exact_metanetx_id": ([row.get("metanetx_id", "")], indices["mnx"].get(row.get("metanetx_id", ""), [])),
            "exact_chebi_id": ([normalize_chebi(row.get("chebi_id", ""))], indices["chebi"].get(normalize_chebi(row.get("chebi_id", "")), [])),
            "exact_kegg_id": ([row.get("kegg_id", "")], indices["kegg"].get(row.get("kegg_id", ""), [])),
            "exact_pubchem_cid_via_chebi_sdf": (pubchem_ids, [candidate for cid in pubchem_ids for candidate in indices["pubchem"].get(cid, [])]),
            "unique_normalized_name": ([normalize_name(row.get("primary_name", ""))], indices["name"].get(normalize_name(row.get("primary_name", "")), [])),
        }
        for method, (keys, candidates) in definitions.items():
            if any(keys):
                audit[method]["rows_with_key"] += 1
            if candidates:
                audit[method]["rows_with_local_candidate"] += 1
            if any(parse_structure(candidate.structure) for candidate in candidates):
                audit[method]["rows_with_parseable_candidate"] += 1
    return audit


def render_report(payload: dict) -> str:
    before, after = payload["baseline_counts"], payload["v2_counts"]
    method_lines = [f"| {key} | {value} |" for key, value in payload["new_mappings_by_method"].items()]
    key_lines = [
        f"| {method} | {counts['rows_with_key']} | {counts['rows_with_local_candidate']} | {counts['rows_with_parseable_candidate']} |"
        for method, counts in payload["key_space_coverage"].items()
    ]
    reason_lines = [f"| {reason} | {count} |" for reason, count in payload["remaining_decisions_by_reason"].items()]
    return "\n".join([
        "# Compound Structure Enrichment v2", "", f"Generated: {payload['generated_at']}", "",
        "## Net change", "", "| Metric | Baseline | v2 | Delta |", "|---|---:|---:|---:|",
        f"| Parseable structures | {before['structures_parseable']} | {after['structures_parseable']} | +{after['structures_parseable'] - before['structures_parseable']} |",
        f"| Unresolved structures | {before['structures_unresolved']} | {after['structures_unresolved']} | {after['structures_unresolved'] - before['structures_unresolved']} |",
        f"| Missing structures | {before['structures_missing']} | {after['structures_missing']} | {after['structures_missing'] - before['structures_missing']} |",
        f"| Parse failures | {before['structures_parse_failed']} | {after['structures_parse_failed']} | {after['structures_parse_failed'] - before['structures_parse_failed']} |",
        "", "## New mappings", "", "| Deterministic method | Rows |", "|---|---:|", *method_lines,
        "", f"Manual review conflicts: {payload['manual_review_rows']}",
        f"Still unresolved after local exhaustion: {payload['unresolved_after_exhaustion']}",
        "", "## Exhausted key spaces", "",
        "For every previously unresolved row the pipeline attempted, in order: exact YMDB IDs embedded in model names; exact MetaNetX IDs; exact ChEBI primary/secondary IDs; exact KEGG IDs; exact PubChem CIDs through the local ChEBI SDF; and unique normalized names in local Yeast-GEM/YMDB tables. Formula disagreements and one-key/multiple-structure results were retained as manual review and were not promoted.",
        "", "| Key space | Rows carrying key | Local candidate rows | Parseable candidate rows |", "|---|---:|---:|---:|", *key_lines,
        "", f"All {payload['unresolved_after_exhaustion']} unresolved rows traversed all six spaces without an admissible candidate; the reason table separates absent candidates from locally present but unparsable structures. The {payload['manual_review_rows']} `manual_review` rows stopped at the first deterministic conflict.",
        "", "| Remaining decision reason | Rows |", "|---|---:|", *reason_lines,
        "", "## Outputs", "",
        "- `02_id_mapping/model_compound_seed_enriched_v2.csv`",
        "- `02_id_mapping/model_compound_structure_enrichment_v2_provenance.csv`",
        "- `02_id_mapping/model_compound_structure_manual_review_v2.csv`",
        "- `06_evaluation/data_quality_gate_enriched_v2/summary.json`", "",
    ])


def main() -> None:
    rows = read_csv(INPUT)
    parser_name, parse_structure = load_smiles_parser()
    if parser_name == "unavailable":
        raise RuntimeError("pysmiles is required so unvalidated structures are never promoted")
    roots = source_roots()
    indices, assets, pubchem_xrefs = build_indices(rows, roots, parse_structure)
    output_rows, provenance, methods = enrich(rows, indices, pubchem_xrefs, parse_structure)
    key_space_coverage = audit_key_spaces(rows, indices, pubchem_xrefs, parse_structure)

    output_fields = list(rows[0]) + [field for field in ("ymdb_id", "pubchem_cid", "structure_mapping_method_v2") if field not in rows[0]]
    provenance_fields = [
        "compound_uid", "model_metabolite_id", "primary_name", "formula", "previous_structure_status",
        "decision", "reason", "matched_key", "source_database", "source_record_id", "source_file",
        "method", "confidence_level", "candidate_count", "attempted_key_spaces",
    ]
    write_csv(OUTPUT, output_rows, output_fields)
    write_csv(PROVENANCE, provenance, provenance_fields)
    write_csv(MANUAL_REVIEW, [row for row in provenance if row["decision"] == "manual_review"], provenance_fields)

    baseline_config = json.loads((ROOT / "09_configs" / "data_quality_gate.json").read_text(encoding="utf-8"))
    baseline_summary, _ = run_gate(ROOT, ROOT / "09_configs" / "data_quality_gate.json", EVAL_DIR / "data_quality_gate_enriched_v1_baseline")
    GATE_DIR.mkdir(parents=True, exist_ok=True)
    baseline_config["inputs"]["compounds_csv"] = "02_id_mapping/model_compound_seed_enriched_v2.csv"
    GATE_CONFIG.write_text(json.dumps(baseline_config, indent=2) + "\n", encoding="utf-8")
    v2_summary, _ = run_gate(ROOT, GATE_CONFIG, GATE_DIR)
    payload = {
        "schema_version": "2.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": str(INPUT), "output": str(OUTPUT), "parser": parser_name,
        "local_roots": [str(root) for root in roots], "local_assets_scanned": assets,
        "baseline_counts": baseline_summary["counts"], "v2_counts": v2_summary["counts"],
        "net_unresolved_reduction": baseline_summary["counts"]["structures_unresolved"] - v2_summary["counts"]["structures_unresolved"],
        "new_mappings": sum(methods.values()), "new_mappings_by_method": dict(sorted(methods.items())),
        "manual_review_rows": sum(row["decision"] == "manual_review" for row in provenance),
        "unresolved_after_exhaustion": sum(row["decision"] == "unresolved" for row in provenance),
        "key_space_coverage": key_space_coverage,
        "remaining_decisions_by_reason": dict(sorted(Counter(
            row["reason"] for row in provenance if row["decision"] != "mapped"
        ).items())),
        "provenance_rows": len(provenance), "gate_status": v2_summary["status"],
    }
    REPORT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_MD.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "net_unresolved_reduction": payload["net_unresolved_reduction"], "v2_counts": payload["v2_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
