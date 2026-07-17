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
EVAL_DIR = ROOT / "06_evaluation"


def has_text(value: Any) -> bool:
    return str(value).strip().lower() not in {"", "nan", "none", "null"}


def classify(row: pd.Series, provenance: dict[str, dict[str, str]]) -> tuple[str, str, str, bool]:
    rid = row["model_reaction_id"]
    is_underground = str(row["is_underground_rxn_prefix"]) == "True"
    has_external = row["crossref_status"] == "has_external_crossref"
    prov = provenance.get(rid, {})
    has_rxndb = prov.get("rxndb_direct_match") == "True"
    has_ec = has_text(prov.get("ec_number", ""))

    if is_underground and has_rxndb:
        status = "underground_rxndb_provenance"
        tier = "prediction_provenance"
        training_role = "candidate_label_with_review"
        usable = False
    elif is_underground:
        status = "underground_no_selected_rxndb_match"
        tier = "review_required"
        training_role = "exclude_until_provenance_resolved"
        usable = False
    elif has_external:
        status = "curated_or_database_crossreferenced"
        tier = "external_crossref"
        training_role = "preferred_reference_label"
        usable = True
    else:
        status = "model_reaction_without_external_crossref"
        tier = "model_only"
        training_role = "supporting_model_context"
        usable = False

    if is_underground and has_rxndb and has_ec:
        training_role = "candidate_label_with_ec_and_review"
    return status, tier, training_role, usable


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Reaction Confidence Flags",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for key, value in payload["status_counts"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Tier Counts",
            "",
            "| Tier | Count |",
            "|---|---:|",
        ]
    )
    for key, value in payload["tier_counts"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Output",
            "",
            "- `02_id_mapping/model_reaction_confidence_flags.csv`",
            "",
            "## Interpretation",
            "",
            "Use `preferred_reference_label` rows as the first-pass curated training/reference pool. Use underground RXNdb rows as candidate pathway-extension evidence only after manual or additional database review. Rows marked `exclude_until_provenance_resolved` should not be used as labels.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    crossrefs = pd.read_csv(MAP_DIR / "model_reaction_crossrefs.csv", dtype=str).fillna("")
    prov_df = pd.read_csv(MAP_DIR / "model_underground_rxn_provenance.csv", dtype=str).fillna("")
    provenance = {row["model_reaction_id"]: row for row in prov_df.to_dict("records")}

    rows: list[dict[str, Any]] = []
    for _, row in crossrefs.iterrows():
        prov = provenance.get(row["model_reaction_id"], {})
        status, tier, training_role, usable = classify(row, provenance)
        rows.append(
            {
                "reaction_uid": row["reaction_uid"],
                "model_reaction_id": row["model_reaction_id"],
                "reaction_name": row["reaction_name"],
                "model_equation": row["model_equation"],
                "is_underground_rxn_prefix": row["is_underground_rxn_prefix"],
                "crossref_status": row["crossref_status"],
                "metanetx_reaction_id": row["metanetx_reaction_id"],
                "kegg_reaction_id": row["kegg_reaction_id"],
                "bigg_reaction_id": row["bigg_reaction_id"],
                "sbo_id": row["sbo_id"],
                "rxndb_direct_match": prov.get("rxndb_direct_match", ""),
                "rxndb_id": prov.get("rxndb_id", ""),
                "rxndb_template_id": prov.get("template_id", ""),
                "rxndb_ec_number": prov.get("ec_number", ""),
                "rxndb_similarity": prov.get("similarity", ""),
                "confidence_status": status,
                "evidence_tier": tier,
                "training_role": training_role,
                "usable_as_first_pass_training_label": usable,
            }
        )

    out = MAP_DIR / "model_reaction_confidence_flags.csv"
    write_csv(out, rows)
    status_counts = Counter(row["confidence_status"] for row in rows)
    tier_counts = Counter(row["evidence_tier"] for row in rows)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "row_count": len(rows),
        "status_counts": dict(status_counts),
        "tier_counts": dict(tier_counts),
        "output": str(out),
    }
    (EVAL_DIR / "phase2_reaction_confidence_flags.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_reaction_confidence_flags.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_reaction_confidence_flags.md")


if __name__ == "__main__":
    main()
