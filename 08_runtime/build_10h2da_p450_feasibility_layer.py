from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "06_evaluation"
REPORT_DIR = ROOT / "07_reports"

HYDROXYLASE_REACTIONS = {"CAND_T2DEC_OMEGA_HYDROXYLASE_P", "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def all_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return fields


def txt(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(k, "")) for k in ["entry", "gene_names", "protein_names", "ec_number", "organism", "external_panel_note", "enzyme_family_sanity_class"]).lower()


def p450_system(row: dict[str, Any]) -> dict[str, Any]:
    text = txt(row)
    organism = row.get("organism", "")
    origin = row.get("candidate_origin", "")
    if "p450foxy" in text or "cyp505" in text or "bifunctional cytochrome p450/nadph" in text:
        return {
            "p450_system_type": "self_sufficient_cyp505",
            "redox_partner_requirement": "internal_reductase_domain",
            "redox_partner_score": 5,
            "localization_expectation": "soluble_or_less_membrane_constrained_than_classic_microsomal_p450",
            "expression_risk": "medium",
            "expression_risk_score": 4,
            "system_rationale": "CYP505/P450foxy-like enzymes include a fused reductase domain, reducing CPR compatibility risk.",
        }
    if "cyp52" in text or "cytochrome p450 52" in text:
        return {
            "p450_system_type": "fungal_cyp52_microsomal_p450",
            "redox_partner_requirement": "requires_cpr_or_compatible_yeast_p450_reductase",
            "redox_partner_score": 4,
            "localization_expectation": "ER_membrane_associated_P450_likely",
            "expression_risk": "medium",
            "expression_risk_score": 4,
            "system_rationale": "Fungal/yeast CYP52 fatty-acid hydroxylases are closer to yeast expression context but still need redox partner handling.",
        }
    if "cytochrome p450" in text or "cyp4" in text or "cyp51" in text or "cyp56" in text or "cyp61" in text:
        if origin.startswith("external"):
            return {
                "p450_system_type": "heterologous_microsomal_p450",
                "redox_partner_requirement": "requires_cpr_or_cognate_reductase_engineering",
                "redox_partner_score": 2,
                "localization_expectation": "ER_membrane_associated_P450_likely",
                "expression_risk": "high",
                "expression_risk_score": 2,
                "system_rationale": "Animal microsomal P450s may express in yeast but redox coupling, membrane insertion, and activity transfer are higher-risk.",
            }
        return {
            "p450_system_type": "endogenous_or_yeast_cyp_keyword_hit",
            "redox_partner_requirement": "native_yeast_redox_context_possible_but_terminal_activity_unvalidated",
            "redox_partner_score": 3,
            "localization_expectation": "native_localization_if_endogenous",
            "expression_risk": "medium",
            "expression_risk_score": 3,
            "system_rationale": "Endogenous CYP/P450-related hit lowers expression risk but does not establish fatty-acid omega-hydroxylation.",
        }
    if any(term in text for term in ["monooxygenase", "hydroxylase", "oxygenase", "fmo", "coq6", "scs7"]):
        return {
            "p450_system_type": "non_p450_oxygenase_or_hydroxylase",
            "redox_partner_requirement": "enzyme_specific_redox_requirement_unknown",
            "redox_partner_score": 2,
            "localization_expectation": "enzyme_specific_or_unknown",
            "expression_risk": "medium_high",
            "expression_risk_score": 2,
            "system_rationale": "Oxygenase family hit but not a clear fatty-acid omega-hydroxylating P450 system.",
        }
    return {
        "p450_system_type": "weak_or_non_hydroxylase_hit",
        "redox_partner_requirement": "not_prioritized",
        "redox_partner_score": 0,
        "localization_expectation": "not_prioritized",
        "expression_risk": "high",
        "expression_risk_score": 0,
        "system_rationale": "Not a convincing P450/oxygenase system for terminal 10H2DA hydroxylation.",
    }


def substrate_fit(row: dict[str, Any]) -> dict[str, Any]:
    text = txt(row)
    substrate = row.get("substrate_name", "").lower()
    if "cyp52" in text or "fatty acid omega" in text or "omega-hydroxylase" in text or "omega monooxygenase" in text:
        score = 5
        rationale = "fatty-acid omega-hydroxylase family aligns with terminal C10 hydroxylation need"
    elif "lauric acid" in text or "long-chain fatty acid" in text or "20-hydroxyeicosatetraenoic" in text:
        score = 4
        rationale = "fatty-acid hydroxylation scope is relevant but exact C10 unsaturated substrate is unvalidated"
    elif "sterol" in text or "ubiquinone" in text or "sphingolipid" in text:
        score = 2
        rationale = "oxygenase chemistry exists but native substrate class is distant from free/CoA C10 acids"
    else:
        score = 1
        rationale = "substrate class support is weak"
    if "coa" in substrate and score >= 4:
        rationale += "; CoA-bound substrate adds uncertainty because many omega-hydroxylase records are free-fatty-acid oriented"
        score = max(score - 1, 1)
    return {"substrate_fit_score": score, "substrate_fit_rationale": rationale}


def host_fit(row: dict[str, Any]) -> dict[str, Any]:
    organism = row.get("organism", "").lower()
    text = txt(row)
    if "saccharomyces cerevisiae" in organism:
        return {"host_context_class": "native_yeast", "host_context_score": 5, "host_context_rationale": "native S. cerevisiae sequence, but activity may not match terminal hydroxylation"}
    if any(term in organism for term in ["starmerella", "candida", "yeast"]):
        return {"host_context_class": "yeast_or_close_fungal_external", "host_context_score": 5, "host_context_rationale": "yeast/fungal origin is favorable for heterologous expression in S. cerevisiae"}
    if "fusarium" in organism or "fung" in organism or "cyp505" in text:
        return {"host_context_class": "fungal_external", "host_context_score": 4, "host_context_rationale": "fungal origin is more plausible than mammalian P450 for yeast engineering"}
    if "homo sapiens" in organism or "oryctolagus" in organism or "rabbit" in organism:
        return {"host_context_class": "mammalian_external", "host_context_score": 2, "host_context_rationale": "mammalian microsomal P450 expression and CPR coupling in yeast are higher-risk"}
    return {"host_context_class": "distant_or_unknown_external", "host_context_score": 2, "host_context_rationale": "host compatibility is uncertain"}


def classify_action(row: dict[str, Any]) -> str:
    system = row["p450_system_type"]
    host = row["host_context_class"]
    substrate = int(row["substrate_fit_score"])
    score = float(row["p450_engineering_feasibility_score"])
    if system == "self_sufficient_cyp505" and score >= 13:
        return "high_priority_test_self_sufficient_p450"
    if system == "fungal_cyp52_microsomal_p450" and score >= 13:
        return "high_priority_test_with_yeast_cpr_or_cognate_cpr"
    if host == "mammalian_external" and substrate >= 4:
        return "secondary_priority_high_activity_but_expression_risk"
    if system.startswith("endogenous"):
        return "low_expression_risk_but_activity_validation_required"
    if score >= 10:
        return "secondary_priority_screen"
    return "deprioritize_or_keep_as_background_evidence"


def score_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out.update(p450_system(row))
    out.update(substrate_fit(row))
    out.update(host_fit(row))
    family_score = float(out.get("enzyme_family_sanity_score", 0.0))
    unikp_score = float(out.get("unikp_log10_kcat_Km", 0.0))
    redox_score = float(out["redox_partner_score"])
    expression_score = float(out["expression_risk_score"])
    substrate_score = float(out["substrate_fit_score"])
    host_score = float(out["host_context_score"])
    out["p450_engineering_feasibility_score"] = round(family_score + unikp_score + redox_score + expression_score + substrate_score + host_score, 6)
    out["recommended_p450_action"] = classify_action(out)
    return out


def design_recommendations(p450_rows: list[dict[str, Any]], engineering_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    thioesterases = [row for row in engineering_rows if row["candidate_reaction_id"] in {"CAND_T2DEC_THIOESTERASE_P", "CAND_10H2DA_COA_THIOESTERASE_P"}]
    thioesterases.sort(key=lambda row: -float(row.get("engineering_priority_score", 0.0)))
    free_thio = [row for row in thioesterases if row["candidate_reaction_id"] == "CAND_T2DEC_THIOESTERASE_P"][:5]
    coa_thio = [row for row in thioesterases if row["candidate_reaction_id"] == "CAND_10H2DA_COA_THIOESTERASE_P"][:5]
    free_p450 = [row for row in p450_rows if row["candidate_reaction_id"] == "CAND_T2DEC_OMEGA_HYDROXYLASE_P"][:8]
    coa_p450 = [row for row in p450_rows if row["candidate_reaction_id"] == "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P"][:8]
    output = []
    for route, p450_candidates, thio_candidates, p450_step in [
        ("free_acid_route", free_p450, free_thio, "step2"),
        ("coa_bound_route", coa_p450, coa_thio, "step1"),
    ]:
        for p450 in p450_candidates:
            for thio in thio_candidates:
                if p450_step == "step1":
                    step1 = p450
                    step2 = thio
                else:
                    step1 = thio
                    step2 = p450
                mean_priority = (float(step1.get("engineering_priority_score", 0.0)) + float(step2.get("engineering_priority_score", 0.0))) / 2.0
                combined = mean_priority + 0.5 * float(p450["p450_engineering_feasibility_score"])
                output.append(
                    {
                        "route": route,
                        "step1_reaction": step1["candidate_reaction_id"],
                        "step1_entry": step1["entry"],
                        "step1_origin": step1.get("candidate_origin", ""),
                        "step1_family": step1.get("enzyme_family_sanity_class", ""),
                        "step2_reaction": step2["candidate_reaction_id"],
                        "step2_entry": step2["entry"],
                        "step2_origin": step2.get("candidate_origin", ""),
                        "step2_family": step2.get("enzyme_family_sanity_class", ""),
                        "mean_engineering_priority_score": round(mean_priority, 6),
                        "route_risk_note": "external hydroxylase requires heterologous expression and redox partner handling" if str(p450.get("candidate_origin", "")).startswith("external") else "endogenous hydroxylase remains activity-limited",
                        "p450_entry": p450["entry"],
                        "p450_system_type": p450["p450_system_type"],
                        "redox_partner_requirement": p450["redox_partner_requirement"],
                        "host_context_class": p450["host_context_class"],
                        "substrate_fit_score": p450["substrate_fit_score"],
                        "p450_engineering_feasibility_score": p450["p450_engineering_feasibility_score"],
                        "recommended_p450_action": p450["recommended_p450_action"],
                        "combined_design_feasibility_score": round(combined, 6),
                    }
                )
    output.sort(key=lambda row: -float(row["combined_design_feasibility_score"]))
    return output


def render_report(payload: dict[str, Any], p450_rows: list[dict[str, Any]], designs: list[dict[str, Any]]) -> str:
    lines = [
        "# 10H2DA P450 Engineering Feasibility Layer",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Scope",
        "",
        "This layer separates kinetic prioritization from P450 engineering feasibility. It evaluates redox partner requirements, likely expression risk, host compatibility, and substrate-family fit for hydroxylase candidates.",
        "",
        "## Outputs",
        "",
        "- `06_evaluation/10h2da_p450_engineering_feasibility_matrix.csv`",
        "- `06_evaluation/10h2da_p450_design_recommendations.csv`",
        "",
        "## Top P450/Hydroxylase Candidates",
        "",
        "| Entry | Reaction | Origin | Organism | System | Redox | Substrate fit | Feasibility | Action |",
        "|---|---|---|---|---|---|---:|---:|---|",
    ]
    for row in p450_rows[:12]:
        lines.append(
            f"| {row['entry']} | {row['candidate_reaction_id']} | {row['candidate_origin']} | {row.get('organism', '')} | {row['p450_system_type']} | {row['redox_partner_requirement']} | {row['substrate_fit_score']} | {float(row['p450_engineering_feasibility_score']):.3f} | {row['recommended_p450_action']} |"
        )
    lines.extend(["", "## Top Designs After P450 Feasibility", "", "| Route | P450 | System | Thioesterase/Partner | Combined score | Action |", "|---|---|---|---|---:|---|"])
    for row in designs[:10]:
        partner = row["step2_entry"] if row["step1_entry"] == row["p450_entry"] else row["step1_entry"]
        lines.append(f"| {row['route']} | {row['p450_entry']} | {row['p450_system_type']} | {partner} | {float(row['combined_design_feasibility_score']):.3f} | {row['recommended_p450_action']} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "CYP505/P450foxy and fungal/yeast CYP52 candidates receive higher feasibility because they reduce either redox-coupling or host-expression risk. Mammalian CYP4 candidates can remain useful secondary screens, but their high UniKP or family scores should not be read as lower engineering risk.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    engineering = read_csv(EVAL_DIR / "10h2da_engineering_candidate_matrix.csv")
    hydroxylase_rows = [score_row(row) for row in engineering if row["candidate_reaction_id"] in HYDROXYLASE_REACTIONS]
    hydroxylase_rows.sort(key=lambda row: -float(row["p450_engineering_feasibility_score"]))
    write_csv(EVAL_DIR / "10h2da_p450_engineering_feasibility_matrix.csv", hydroxylase_rows, all_fieldnames(hydroxylase_rows))

    designs = design_recommendations(hydroxylase_rows, engineering)
    write_csv(EVAL_DIR / "10h2da_p450_design_recommendations.csv", designs, all_fieldnames(designs))

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "hydroxylase_rows": len(hydroxylase_rows),
        "design_rows": len(designs),
        "outputs": [
            "06_evaluation/10h2da_p450_engineering_feasibility_matrix.csv",
            "06_evaluation/10h2da_p450_design_recommendations.csv",
            "07_reports/10H2DA_p450_engineering_feasibility.md",
        ],
    }
    (EVAL_DIR / "10h2da_p450_engineering_feasibility_manifest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORT_DIR / "10H2DA_p450_engineering_feasibility.md").write_text(render_report(payload, hydroxylase_rows, designs), encoding="utf-8")
    print(REPORT_DIR / "10H2DA_p450_engineering_feasibility.md")


if __name__ == "__main__":
    main()
