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


def split_pipe(value: Any) -> list[str]:
    if not has_text(value):
        return []
    return [item.strip() for item in str(value).split("|") if has_text(item)]


def classify_metabolite(met_id: str, info: dict[str, dict[str, str]]) -> str:
    row = info.get(met_id, {})
    name = row.get("primary_name", "").lower()
    formula = row.get("formula", "")
    if met_id.startswith("sn_"):
        return "underground_template_metabolite_missing_formula"
    if "R" in formula or "X" in formula:
        return "generic_r_group_or_polymer_formula"
    if any(term in name for term in ["cytochrome", "thioredoxin", "ferredoxin", "protein", "trna", "enzyme"]):
        return "macromolecule_or_redox_carrier_formula"
    if not has_text(formula):
        return "missing_formula_no_local_mapping"
    return "other_formula_issue"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Balance Remediation Audit",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Reaction-Level Categories",
        "",
        "| Category | Reactions |",
        "|---|---:|",
    ]
    for key, value in payload["reaction_category_counts"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Metabolite Issue Categories", "", "| Category | Metabolites | Occurrences |", "|---|---:|---:|"])
    for row in payload["metabolite_issue_summary"]:
        lines.append(f"| {row['issue_category']} | {row['unique_metabolites']} | {row['occurrences']} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Most missing formulas come from `sn_*` underground/template metabolites. These should not be guessed into mass-balanced training labels without source structures. Many unparsable formulas contain generic R-groups or macromolecular redox carriers, which should be excluded from structure-sensitive training features or handled with curated carrier rules.",
            "",
            "## Outputs",
            "",
            "- `06_evaluation/phase2_balance_remediation_reaction_flags.csv`",
            "- `06_evaluation/phase2_balance_remediation_metabolite_issues.csv`",
            "- `06_evaluation/phase2_balance_remediation_audit.json`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    balance = pd.read_csv(EVAL_DIR / "phase2_reaction_balance_audit.csv", dtype=str).fillna("")
    compounds = pd.read_csv(MAP_DIR / "model_compound_seed_enriched.csv", dtype=str).fillna("")
    info = {row["model_metabolite_id"]: row for row in compounds.to_dict("records")}

    met_issue_counter: Counter[tuple[str, str]] = Counter()
    reaction_rows: list[dict[str, Any]] = []
    for row in balance.to_dict("records"):
        issue_mets = split_pipe(row["missing_formula_metabolites"]) + split_pipe(row["unparsable_formula_metabolites"])
        issue_categories = sorted({classify_metabolite(met_id, info) for met_id in issue_mets})
        for met_id in issue_mets:
            met_issue_counter[(met_id, classify_metabolite(met_id, info))] += 1
        if row["formula_balanced"] == "True" and row["charge_balanced"] == "True":
            action = "training_ready_mass_charge_balanced"
        elif issue_categories and all(cat in {"underground_template_metabolite_missing_formula", "generic_r_group_or_polymer_formula", "macromolecule_or_redox_carrier_formula"} for cat in issue_categories):
            action = "exclude_from_structure_sensitive_training_or_apply_curated_carrier_rules"
        elif has_text(row["missing_formula_metabolites"]):
            action = "requires_external_structure_mapping"
        else:
            action = "requires_manual_balance_review"
        reaction_rows.append(
            {
                "model_reaction_id": row["model_reaction_id"],
                "reaction_name": row["reaction_name"],
                "formula_balanced": row["formula_balanced"],
                "charge_balanced": row["charge_balanced"],
                "issue_categories": "|".join(issue_categories),
                "remediation_action": action,
                "missing_formula_metabolites": row["missing_formula_metabolites"],
                "unparsable_formula_metabolites": row["unparsable_formula_metabolites"],
                "element_imbalance": row["element_imbalance"],
                "charge_imbalance": row["charge_imbalance"],
            }
        )

    met_rows = []
    for (met_id, category), count in sorted(met_issue_counter.items(), key=lambda item: (-item[1], item[0][0])):
        row = info.get(met_id, {})
        met_rows.append(
            {
                "model_metabolite_id": met_id,
                "primary_name": row.get("primary_name", ""),
                "formula": row.get("formula", ""),
                "charge": row.get("charge", ""),
                "metanetx_id": row.get("metanetx_id", ""),
                "chebi_id": row.get("chebi_id", ""),
                "issue_category": category,
                "reaction_occurrences": count,
            }
        )

    summary_by_category: dict[str, dict[str, int]] = {}
    for item in met_rows:
        category = item["issue_category"]
        summary_by_category.setdefault(category, {"unique_metabolites": 0, "occurrences": 0})
        summary_by_category[category]["unique_metabolites"] += 1
        summary_by_category[category]["occurrences"] += int(item["reaction_occurrences"])
    met_summary = [{"issue_category": key, **value} for key, value in sorted(summary_by_category.items())]
    action_counts = dict(Counter(row["remediation_action"] for row in reaction_rows))

    write_csv(EVAL_DIR / "phase2_balance_remediation_reaction_flags.csv", reaction_rows, list(reaction_rows[0].keys()))
    write_csv(EVAL_DIR / "phase2_balance_remediation_metabolite_issues.csv", met_rows, list(met_rows[0].keys()))
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "reaction_category_counts": action_counts,
        "metabolite_issue_summary": met_summary,
    }
    (EVAL_DIR / "phase2_balance_remediation_audit.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_balance_remediation_audit.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_balance_remediation_audit.md")


if __name__ == "__main__":
    main()
