from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "02_id_mapping"
TRAIN_DIR = ROOT / "05_training"
EVAL_DIR = ROOT / "06_evaluation"

FORMULA_RE = re.compile(r"([A-Z][a-z]?)([0-9.]*)")

CANDIDATE_METABOLITES = {
    "cand_t2dec_p": {"formula": "C10H17O2", "charge": -1, "name": "trans-2-decenoate"},
    "cand_10h2da_p": {"formula": "C10H17O3", "charge": -1, "name": "10-hydroxy-trans-2-decenoate"},
    "cand_10h2da_coa_p": {"formula": "C31H48N7O18P3S", "charge": -4, "name": "10-hydroxy-trans-2-decenoyl-CoA"},
}

CANDIDATE_REACTIONS = [
    {
        "model_reaction_id": "CAND_T2DEC_THIOESTERASE_P",
        "reaction_name": "candidate trans-dec-2-enoyl-CoA thioesterase",
        "model_equation": "s_1507 + s_0809 --> cand_t2dec_p + s_0534 + s_0801",
        "stoichiometry": {"s_1507": -1, "s_0809": -1, "cand_t2dec_p": 1, "s_0534": 1, "s_0801": 1},
        "evidence_class": "10h2da_candidate_terminal",
    },
    {
        "model_reaction_id": "CAND_T2DEC_OMEGA_HYDROXYLASE_P",
        "reaction_name": "candidate trans-2-decenoate omega-hydroxylase",
        "model_equation": "cand_t2dec_p + s_1215 + s_1279 + s_0801 --> cand_10h2da_p + s_1211 + s_0809",
        "stoichiometry": {"cand_t2dec_p": -1, "s_1215": -1, "s_1279": -1, "s_0801": -1, "cand_10h2da_p": 1, "s_1211": 1, "s_0809": 1},
        "evidence_class": "10h2da_candidate_terminal",
    },
    {
        "model_reaction_id": "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P",
        "reaction_name": "candidate trans-dec-2-enoyl-CoA omega-hydroxylase",
        "model_equation": "s_1507 + s_1215 + s_1279 + s_0801 --> cand_10h2da_coa_p + s_1211 + s_0809",
        "stoichiometry": {"s_1507": -1, "s_1215": -1, "s_1279": -1, "s_0801": -1, "cand_10h2da_coa_p": 1, "s_1211": 1, "s_0809": 1},
        "evidence_class": "10h2da_candidate_terminal",
    },
    {
        "model_reaction_id": "CAND_10H2DA_COA_THIOESTERASE_P",
        "reaction_name": "candidate 10-hydroxy-trans-2-decenoyl-CoA thioesterase",
        "model_equation": "cand_10h2da_coa_p + s_0809 --> cand_10h2da_p + s_0534 + s_0801",
        "stoichiometry": {"cand_10h2da_coa_p": -1, "s_0809": -1, "cand_10h2da_p": 1, "s_0534": 1, "s_0801": 1},
        "evidence_class": "10h2da_candidate_terminal",
    },
]


def has_text(value: Any) -> bool:
    return str(value).strip().lower() not in {"", "nan", "none", "null"}


def split_values(value: Any) -> list[str]:
    if not has_text(value):
        return []
    values = []
    for chunk in str(value).replace(";", "|").split("|"):
        chunk = chunk.strip()
        if has_text(chunk):
            values.append(chunk)
    return values


def pct(num: int, den: int) -> float:
    return 0.0 if den == 0 else round(num / den * 100, 2)


def parse_formula(formula: str) -> dict[str, float] | None:
    text = str(formula).strip()
    if not text or any(char in text for char in "R()[]+-"):
        return None
    parts = FORMULA_RE.findall(text)
    if not parts or "".join(element + count for element, count in parts) != text:
        return None
    counts: dict[str, float] = {}
    for element, count_text in parts:
        count = float(count_text) if count_text else 1.0
        counts[element] = counts.get(element, 0.0) + count
    return counts


def add_scaled(target: dict[str, float], counts: dict[str, float], coeff: float) -> None:
    for element, count in counts.items():
        target[element] = target.get(element, 0.0) + coeff * count


def near_zero(value: float, tolerance: float = 1e-6) -> bool:
    return abs(value) <= tolerance


def compact_imbalance(values: dict[str, float]) -> str:
    keep = {key: round(value, 6) for key, value in sorted(values.items()) if not near_zero(value)}
    return json.dumps(keep, sort_keys=True)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_metabolite_info() -> dict[str, dict[str, Any]]:
    compounds = pd.read_csv(MAP_DIR / "model_compound_seed_enriched.csv", dtype=str).fillna("")
    info = {
        row["model_metabolite_id"]: {
            "formula": row["formula"],
            "charge": int(float(row["charge"])) if has_text(row["charge"]) else None,
            "name": row["primary_name"],
        }
        for row in compounds.to_dict("records")
    }
    info.update(CANDIDATE_METABOLITES)
    return info


def balance_row(row: dict[str, Any], met_info: dict[str, dict[str, Any]], source: str) -> dict[str, Any]:
    stoich = row.get("stoichiometry")
    if stoich is None:
        stoich = json.loads(row.get("stoichiometry_json", "{}"))
    element_delta: dict[str, float] = {}
    charge_delta = 0.0
    missing_formula = []
    unparsable_formula = []
    missing_charge = []
    for met_id, coeff_raw in stoich.items():
        coeff = float(coeff_raw)
        met = met_info.get(met_id, {})
        formula = met.get("formula", "")
        charge = met.get("charge")
        counts = parse_formula(formula)
        if not has_text(formula):
            missing_formula.append(met_id)
        elif counts is None:
            unparsable_formula.append(met_id)
        else:
            add_scaled(element_delta, counts, coeff)
        if charge is None:
            missing_charge.append(met_id)
        else:
            charge_delta += coeff * float(charge)
    formula_balanced = not missing_formula and not unparsable_formula and all(near_zero(value) for value in element_delta.values())
    charge_balanced = not missing_charge and near_zero(charge_delta)
    return {
        "source": source,
        "model_reaction_id": row["model_reaction_id"],
        "reaction_name": row.get("reaction_name", row.get("primary_name", "")),
        "model_equation": row.get("model_equation", row.get("equation", "")),
        "formula_balanced": formula_balanced,
        "charge_balanced": charge_balanced,
        "missing_formula_metabolites": "|".join(missing_formula),
        "unparsable_formula_metabolites": "|".join(unparsable_formula),
        "missing_charge_metabolites": "|".join(missing_charge),
        "element_imbalance": compact_imbalance(element_delta),
        "charge_imbalance": round(charge_delta, 6),
    }


def build_balance_audit(met_info: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    seed = pd.read_csv(MAP_DIR / "model_reaction_seed.csv", dtype=str).fillna("")
    rows = [balance_row(row, met_info, "Yeast-MetaTwin") for row in seed.to_dict("records")]
    rows.extend(balance_row(row, met_info, "10H2DA_candidate") for row in CANDIDATE_REACTIONS)
    return rows


def build_feature_label_quality(labels: pd.DataFrame, compounds: pd.DataFrame) -> list[dict[str, Any]]:
    stoich_by_rxn = {row["model_reaction_id"]: json.loads(row["stoichiometry_json"] or "{}") for row in labels.to_dict("records")}
    compound_by_id = {row["model_metabolite_id"]: row for row in compounds.to_dict("records")}
    rows = []
    for group, sub in labels.groupby("export_group", sort=False):
        total = len(sub)
        with_equation = int(sub["model_equation"].map(has_text).sum())
        with_stoich = int(sub["stoichiometry_json"].map(has_text).sum())
        with_gpr = int(sub["gpr"].map(has_text).sum())
        with_orfs = int(sub["orfs"].map(has_text).sum())
        with_ec = int(sub["enzyme_ec_numbers"].map(has_text).sum())
        with_xref = int(sub["external_database_crossrefs_compact"].map(has_text).sum())
        with_rxndb = int(sub["rxndb_id"].map(has_text).sum())
        reaction_with_all_smiles = 0
        reaction_with_all_inchikey = 0
        for row in sub.to_dict("records"):
            mets = list(stoich_by_rxn.get(row["model_reaction_id"], {}).keys())
            if mets and all(has_text(compound_by_id.get(met, {}).get("smiles", "")) for met in mets):
                reaction_with_all_smiles += 1
            if mets and all(has_text(compound_by_id.get(met, {}).get("inchikey", "")) for met in mets):
                reaction_with_all_inchikey += 1
        rows.append(
            {
                "export_group": group,
                "rows": total,
                "with_equation_pct": pct(with_equation, total),
                "with_stoichiometry_pct": pct(with_stoich, total),
                "with_all_reactant_product_smiles_pct": pct(reaction_with_all_smiles, total),
                "with_all_reactant_product_inchikey_pct": pct(reaction_with_all_inchikey, total),
                "with_gpr_pct": pct(with_gpr, total),
                "with_orfs_pct": pct(with_orfs, total),
                "with_enzyme_ec_pct": pct(with_ec, total),
                "with_external_xref_pct": pct(with_xref, total),
                "with_rxndb_pct": pct(with_rxndb, total),
            }
        )
    return rows


def build_negative_candidates(labels: pd.DataFrame, balance: pd.DataFrame) -> list[dict[str, Any]]:
    balance_by_id = {row["model_reaction_id"]: row for row in balance.to_dict("records") if row["source"] == "Yeast-MetaTwin"}
    rows = []
    for row in labels.to_dict("records"):
        if row["export_group"] != "model_context_only":
            continue
        if has_text(row["external_database_crossrefs_compact"]) or has_text(row["rxndb_id"]):
            continue
        bal = balance_by_id.get(row["model_reaction_id"], {})
        if str(bal.get("formula_balanced", "False")) != "True" or str(bal.get("charge_balanced", "False")) != "True":
            continue
        rows.append(
            {
                "model_reaction_id": row["model_reaction_id"],
                "reaction_name": row["reaction_name"],
                "model_equation": row["model_equation"],
                "negative_sample_role": "candidate_unlabeled_hard_negative",
                "reason": "model context only; no external database/RXNdb provenance; formula and charge balanced",
                "gpr": row["gpr"],
                "orfs": row["orfs"],
                "enzyme_ec_numbers": row["enzyme_ec_numbers"],
            }
        )
    return rows


def build_validation_matrix(labels: pd.DataFrame, balance: pd.DataFrame) -> list[dict[str, Any]]:
    balance_by_id = {row["model_reaction_id"]: row for row in balance.to_dict("records") if row["source"] == "Yeast-MetaTwin"}
    rows = []
    for row in labels.to_dict("records"):
        bal = balance_by_id.get(row["model_reaction_id"], {})
        evidence = []
        if has_text(row["external_database_crossrefs_compact"]):
            evidence.append("external_database_crossref")
        if has_text(row["rxndb_id"]):
            evidence.append("rxndb_prediction_provenance")
        if has_text(row["enzyme_ec_numbers"]):
            evidence.append("enzyme_ec")
        if has_text(row["gpr"]):
            evidence.append("model_gpr")
        if str(bal.get("formula_balanced", "False")) == "True" and str(bal.get("charge_balanced", "False")) == "True":
            evidence.append("mass_charge_balanced")
        if row["export_group"] in {"first_pass_reference_label", "candidate_extension_evidence", "excluded_review_required"}:
            rows.append(
                {
                    "model_reaction_id": row["model_reaction_id"],
                    "reaction_name": row["reaction_name"],
                    "export_group": row["export_group"],
                    "evidence_tier": row["evidence_tier"],
                    "evidence_items": "|".join(evidence),
                    "external_database_crossrefs": row["external_database_crossrefs_compact"],
                    "rxndb_id": row["rxndb_id"],
                    "rxndb_ec_number": row["rxndb_ec_number"],
                    "enzyme_ec_numbers": row["enzyme_ec_numbers"],
                    "formula_balanced": bal.get("formula_balanced", ""),
                    "charge_balanced": bal.get("charge_balanced", ""),
                    "validation_action": validation_action(row, evidence),
                }
            )
    for row in CANDIDATE_REACTIONS:
        bal = next(item for item in balance.to_dict("records") if item["model_reaction_id"] == row["model_reaction_id"])
        rows.append(
            {
                "model_reaction_id": row["model_reaction_id"],
                "reaction_name": row["reaction_name"],
                "export_group": "10h2da_candidate_terminal",
                "evidence_tier": "hypothesis_after_fba_feasibility",
                "evidence_items": "mass_charge_balanced|fba_feasible_after_candidate_addition",
                "external_database_crossrefs": "",
                "rxndb_id": "",
                "rxndb_ec_number": "",
                "enzyme_ec_numbers": "",
                "formula_balanced": bal["formula_balanced"],
                "charge_balanced": bal["charge_balanced"],
                "validation_action": "find enzyme/database evidence before promoting to curated label",
            }
        )
    return rows


def validation_action(row: dict[str, Any], evidence: list[str]) -> str:
    if row["export_group"] == "first_pass_reference_label" and "mass_charge_balanced" in evidence:
        return "usable as positive reference label"
    if row["export_group"] == "candidate_extension_evidence":
        return "review RXNdb provenance and balance before positive-label promotion"
    if row["export_group"] == "excluded_review_required":
        return "exclude until provenance is resolved"
    return "review"


def summarize_balance(balance: pd.DataFrame) -> dict[str, Any]:
    model_rows = balance[balance["source"] == "Yeast-MetaTwin"]
    candidate_rows = balance[balance["source"] == "10H2DA_candidate"]
    return {
        "model_reactions_checked": len(model_rows),
        "model_formula_balanced": int(model_rows["formula_balanced"].sum()),
        "model_charge_balanced": int(model_rows["charge_balanced"].sum()),
        "candidate_reactions_checked": len(candidate_rows),
        "candidate_formula_balanced": int(candidate_rows["formula_balanced"].sum()),
        "candidate_charge_balanced": int(candidate_rows["charge_balanced"].sum()),
        "missing_formula_rows": int(model_rows["missing_formula_metabolites"].map(has_text).sum()),
        "unparsable_formula_rows": int(model_rows["unparsable_formula_metabolites"].map(has_text).sum()),
    }


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Training Readiness Audit",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Balance Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in payload["balance_summary"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Feature And Label Quality", "", "| Export group | Rows | Equation % | Stoich % | All SMILES % | GPR % | ORF % | EC % | External xref % | RXNdb % |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for row in payload["feature_label_quality"]:
        lines.append(
            f"| {row['export_group']} | {row['rows']} | {row['with_equation_pct']:.2f} | {row['with_stoichiometry_pct']:.2f} | {row['with_all_reactant_product_smiles_pct']:.2f} | {row['with_gpr_pct']:.2f} | {row['with_orfs_pct']:.2f} | {row['with_enzyme_ec_pct']:.2f} | {row['with_external_xref_pct']:.2f} | {row['with_rxndb_pct']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Negative Sample Design",
            "",
            f"Candidate unlabeled hard negatives: {payload['negative_candidate_count']}",
            "",
            "These rows are not true negatives. They are balanced, model-context reactions without external/RXNdb provenance and can be used as candidate hard negatives only with conservative weighting or positive-unlabeled learning.",
            "",
            "## Validation Matrix",
            "",
            f"Validation matrix rows: {payload['validation_matrix_count']}",
            "",
            "The matrix separates curated references, RXNdb-backed candidates, unresolved exclusions, and 10H2DA terminal hypotheses so they do not collapse into one training label type.",
            "",
            "## Output Files",
            "",
            "- `06_evaluation/phase2_training_readiness_audit.json`",
            "- `06_evaluation/phase2_reaction_balance_audit.csv`",
            "- `06_evaluation/phase2_feature_label_quality.csv`",
            "- `05_training/reaction_negative_sample_candidates.csv`",
            "- `06_evaluation/phase2_candidate_validation_matrix.csv`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    labels = pd.read_csv(TRAIN_DIR / "reaction_all_label_export_groups.csv", dtype=str).fillna("")
    compounds = pd.read_csv(MAP_DIR / "model_compound_seed_enriched.csv", dtype=str).fillna("")
    met_info = load_metabolite_info()
    balance_rows = build_balance_audit(met_info)
    balance_df = pd.DataFrame(balance_rows)
    feature_rows = build_feature_label_quality(labels, compounds)
    negative_rows = build_negative_candidates(labels, balance_df)
    validation_rows = build_validation_matrix(labels, balance_df)

    write_csv(EVAL_DIR / "phase2_reaction_balance_audit.csv", balance_rows, list(balance_rows[0].keys()))
    write_csv(EVAL_DIR / "phase2_feature_label_quality.csv", feature_rows, list(feature_rows[0].keys()))
    write_csv(
        TRAIN_DIR / "reaction_negative_sample_candidates.csv",
        negative_rows,
        ["model_reaction_id", "reaction_name", "model_equation", "negative_sample_role", "reason", "gpr", "orfs", "enzyme_ec_numbers"],
    )
    write_csv(EVAL_DIR / "phase2_candidate_validation_matrix.csv", validation_rows, list(validation_rows[0].keys()))

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "label_export_group_counts": dict(Counter(labels["export_group"])),
        "balance_summary": summarize_balance(balance_df),
        "feature_label_quality": feature_rows,
        "negative_candidate_count": len(negative_rows),
        "validation_matrix_count": len(validation_rows),
    }
    (EVAL_DIR / "phase2_training_readiness_audit.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_training_readiness_audit.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_training_readiness_audit.md")


if __name__ == "__main__":
    main()
