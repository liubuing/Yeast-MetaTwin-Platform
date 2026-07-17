from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "02_id_mapping"
TRAIN_DIR = ROOT / "05_training"
EVAL_DIR = ROOT / "06_evaluation"


def split_values(value: Any) -> list[str]:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return []
    values: list[str] = []
    for chunk in text.replace(";", "|").split("|"):
        chunk = chunk.strip()
        if chunk and chunk.lower() not in {"nan", "none", "null"}:
            values.append(chunk)
    return values


def compact_join(values: list[str]) -> str:
    return "|".join(sorted(set(v for v in values if v)))


def aggregate_enzyme_evidence() -> dict[str, dict[str, Any]]:
    enzymes = pd.read_csv(MAP_DIR / "model_enzyme_evidence_seed_enriched.csv", dtype=str).fillna("")
    grouped: dict[str, dict[str, Any]] = {}
    for rid, group in enzymes.groupby("model_reaction_id", sort=False):
        grouped[rid] = {
            "enzyme_evidence_rows": len(group),
            "protein_ids": compact_join(group["protein_id"].tolist()),
            "orfs": compact_join(group["orf_id"].tolist()),
            "gene_symbols": compact_join(group["gene_symbol"].tolist()),
            "enzyme_ec_numbers": compact_join([ec for value in group["ec_numbers"].tolist() for ec in split_values(value)]),
            "enzyme_confidence_levels": compact_join(group["confidence_level"].tolist()),
        }
    return grouped


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_rows() -> list[dict[str, Any]]:
    confidence = pd.read_csv(MAP_DIR / "model_reaction_confidence_flags.csv", dtype=str).fillna("")
    seed = pd.read_csv(MAP_DIR / "model_reaction_seed.csv", dtype=str).fillna("")
    seed_by_id = {row["model_reaction_id"]: row for row in seed.to_dict("records")}
    enzyme_by_rxn = aggregate_enzyme_evidence()

    rows: list[dict[str, Any]] = []
    for row in confidence.to_dict("records"):
        rid = row["model_reaction_id"]
        seed_row = seed_by_id.get(rid, {})
        enz = enzyme_by_rxn.get(rid, {})
        role = row["training_role"]
        if role == "preferred_reference_label":
            export_group = "first_pass_reference_label"
            label_source = "external_database_crossref"
        elif role in {"candidate_label_with_review", "candidate_label_with_ec_and_review"}:
            export_group = "candidate_extension_evidence"
            label_source = "rxndb_prediction_provenance"
        elif role == "exclude_until_provenance_resolved":
            export_group = "excluded_review_required"
            label_source = "unresolved_underground_reaction"
        else:
            export_group = "model_context_only"
            label_source = "model_without_external_crossref"

        database_xrefs = compact_join(
            split_values(row.get("metanetx_reaction_id", ""))
            + split_values(row.get("kegg_reaction_id", ""))
            + split_values(row.get("bigg_reaction_id", ""))
        )
        all_xrefs = compact_join(
            split_values(row.get("metanetx_reaction_id", ""))
            + split_values(row.get("kegg_reaction_id", ""))
            + split_values(row.get("bigg_reaction_id", ""))
            + split_values(row.get("sbo_id", ""))
        )
        rows.append(
            {
                "reaction_uid": row["reaction_uid"],
                "model_reaction_id": rid,
                "reaction_name": row["reaction_name"],
                "model_equation": row["model_equation"],
                "direction": seed_row.get("direction", ""),
                "lower_bound": seed_row.get("lower_bound", ""),
                "upper_bound": seed_row.get("upper_bound", ""),
                "reactant_compound_uids": seed_row.get("reactant_compound_uids", ""),
                "product_compound_uids": seed_row.get("product_compound_uids", ""),
                "stoichiometry_json": seed_row.get("stoichiometry_json", ""),
                "genes": seed_row.get("genes", ""),
                "orfs": seed_row.get("orfs", ""),
                "gpr": seed_row.get("gpr", ""),
                "enzyme_evidence_rows": enz.get("enzyme_evidence_rows", 0),
                "enzyme_protein_ids": enz.get("protein_ids", ""),
                "enzyme_orfs": enz.get("orfs", ""),
                "enzyme_gene_symbols": enz.get("gene_symbols", ""),
                "enzyme_ec_numbers": enz.get("enzyme_ec_numbers", ""),
                "enzyme_confidence_levels": enz.get("enzyme_confidence_levels", ""),
                "metanetx_reaction_id": row.get("metanetx_reaction_id", ""),
                "kegg_reaction_id": row.get("kegg_reaction_id", ""),
                "bigg_reaction_id": row.get("bigg_reaction_id", ""),
                "sbo_id": row.get("sbo_id", ""),
                "external_database_crossrefs_compact": database_xrefs,
                "all_crossrefs_compact": all_xrefs,
                "rxndb_id": row.get("rxndb_id", ""),
                "rxndb_template_id": row.get("rxndb_template_id", ""),
                "rxndb_ec_number": row.get("rxndb_ec_number", ""),
                "rxndb_similarity": row.get("rxndb_similarity", ""),
                "confidence_status": row["confidence_status"],
                "evidence_tier": row["evidence_tier"],
                "training_role": role,
                "export_group": export_group,
                "label_source": label_source,
                "usable_as_first_pass_training_label": row["usable_as_first_pass_training_label"],
            }
        )
    return rows


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Reaction Label Exports",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Export Counts",
        "",
        "| Export group | Count | File |",
        "|---|---:|---|",
    ]
    for group, count in payload["export_group_counts"].items():
        file_name = payload["files_by_group"].get(group, "")
        lines.append(f"| {group} | {count} | `{file_name}` |")
    lines.extend(
        [
            "",
            "## Rule",
            "",
            "- `first_pass_reference_label`: external database cross-referenced reactions; use as the initial reference label pool.",
            "- `candidate_extension_evidence`: underground reactions with RXNdb provenance; use for pathway extension candidates after review.",
            "- `model_context_only`: model reactions without external reaction cross-reference; use for simulation context, not labels.",
            "- `excluded_review_required`: unresolved underground reactions; exclude from training labels.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = build_rows()
    fieldnames = list(rows[0].keys())
    files_by_group = {
        "first_pass_reference_label": "05_training/reaction_first_pass_reference_labels.csv",
        "candidate_extension_evidence": "05_training/reaction_candidate_extension_evidence.csv",
        "model_context_only": "05_training/reaction_model_context_only.csv",
        "excluded_review_required": "05_training/reaction_excluded_review_required.csv",
    }
    for group, relative in files_by_group.items():
        write_csv(ROOT / relative, [row for row in rows if row["export_group"] == group], fieldnames)
    write_csv(TRAIN_DIR / "reaction_all_label_export_groups.csv", rows, fieldnames)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_reactions": len(rows),
        "export_group_counts": dict(Counter(row["export_group"] for row in rows)),
        "training_role_counts": dict(Counter(row["training_role"] for row in rows)),
        "files_by_group": files_by_group,
        "all_groups_file": "05_training/reaction_all_label_export_groups.csv",
    }
    (EVAL_DIR / "phase2_reaction_label_exports.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_reaction_label_exports.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_reaction_label_exports.md")


if __name__ == "__main__":
    main()
