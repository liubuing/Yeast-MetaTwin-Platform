from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "06_evaluation"
REPORT_DIR = ROOT / "07_reports"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def p450_module(row: dict[str, str]) -> dict[str, str]:
    system = row["p450_system_type"]
    p450 = row["p450_entry"]
    if system == "fungal_cyp52_microsomal_p450":
        return {
            "p450_expression_module": f"express {p450} as ER-associated fungal CYP52 omega-hydroxylase",
            "redox_module": "test yeast NCP1/CPR1 support first; keep cognate CPR as fallback if available",
            "localization_module": "ER/microsomal context preferred; avoid forcing peroxisomal import in first pass",
            "p450_construct_risk": "medium",
        }
    if system == "self_sufficient_cyp505":
        return {
            "p450_expression_module": f"express {p450} as self-sufficient CYP505/P450foxy-style hydroxylase",
            "redox_module": "no separate CPR module in first pass; internal reductase domain is the design advantage",
            "localization_module": "cytosolic or native soluble/fungal context first; monitor whether substrate access limits activity",
            "p450_construct_risk": "medium",
        }
    if system == "heterologous_microsomal_p450":
        return {
            "p450_expression_module": f"express {p450} as heterologous microsomal P450 secondary screen",
            "redox_module": "requires CPR engineering; compare yeast NCP1/CPR1 support with cognate reductase if available",
            "localization_module": "ER/microsomal context required; membrane expression and redox coupling are major risks",
            "p450_construct_risk": "high",
        }
    if system == "endogenous_or_yeast_cyp_keyword_hit":
        return {
            "p450_expression_module": f"use endogenous yeast CYP candidate {p450} only as low-expression-risk exploratory arm",
            "redox_module": "native yeast redox context likely sufficient if any activity exists",
            "localization_module": "retain native localization; activity rather than expression is the main uncertainty",
            "p450_construct_risk": "medium_high_activity_risk",
        }
    return {
        "p450_expression_module": f"deprioritized hydroxylase candidate {p450}",
        "redox_module": "not prioritized",
        "localization_module": "not prioritized",
        "p450_construct_risk": "high",
    }


def thioesterase_module(row: dict[str, str]) -> dict[str, str]:
    entries = [row["step1_entry"], row["step2_entry"]]
    families = [row["step1_family"], row["step2_family"]]
    pairs = list(zip(entries, families))
    thio = next(((entry, family) for entry, family in pairs if "thioesterase" in family), ("", ""))
    entry, family = thio
    if entry == "P41903":
        return {
            "thioesterase_module": "use TES1/PTE1 as primary acyl-CoA thioesterase candidate",
            "thioesterase_rationale": "native peroxisomal long-chain acyl-CoA thioesterase; best endogenous family fit",
            "thioesterase_risk": "medium_compartment_and_substrate_specificity",
        }
    if family == "plausible_thioesterase":
        return {
            "thioesterase_module": f"screen {entry} as secondary thioesterase candidate",
            "thioesterase_rationale": "thioesterase-like annotation but exact 10H2DA precursor substrate is unvalidated",
            "thioesterase_risk": "medium_high_specificity_risk",
        }
    return {
        "thioesterase_module": f"avoid relying on {entry} unless primary thioesterases fail",
        "thioesterase_rationale": "weak or generic thioesterase family fit",
        "thioesterase_risk": "high_specificity_risk",
    }


def route_modules(row: dict[str, str]) -> dict[str, str]:
    if row["route"] == "free_acid_route":
        return {
            "route_module": "free-acid route: release trans-2-decenoate before omega-hydroxylation",
            "precursor_support_module": "maintain decanoate -> decanoyl-CoA -> trans-dec-2-enoyl-CoA support through FAA2/POX1/FOX2 context",
            "expected_intermediates_to_monitor": "trans-dec-2-enoyl-CoA; trans-2-decenoic acid; 10H2DA",
            "route_specific_risk": "free acid availability and P450 substrate access may improve, but thioesterase must release the unsaturated acid first",
        }
    return {
        "route_module": "CoA-bound route: hydroxylate trans-dec-2-enoyl-CoA then hydrolyze 10H2DA-CoA",
        "precursor_support_module": "maintain decanoate -> decanoyl-CoA -> trans-dec-2-enoyl-CoA support through FAA2/POX1/FOX2 context",
        "expected_intermediates_to_monitor": "trans-dec-2-enoyl-CoA; 10-hydroxy-trans-2-decenoyl-CoA; 10H2DA",
        "route_specific_risk": "CoA substrate is less proven for many omega-hydroxylases; thioesterase must accept hydroxylated CoA product",
    }


def controls(row: dict[str, str]) -> dict[str, str]:
    p450 = row["p450_entry"]
    thio = row["step1_entry"] if row["step1_family"].endswith("thioesterase") else row["step2_entry"]
    return {
        "minimal_negative_controls": "empty vector; thioesterase-only; P450-only; no precursor feed or no precursor boost",
        "positive_or_process_controls": "verify precursor pool via trans-dec-2-enoyl-CoA/trans-2-decenoate readout before interpreting 10H2DA absence",
        "construct_comparison_controls": f"compare {p450}+{thio} against {p450}-only and {thio}-only to separate hydroxylation from hydrolysis limits",
        "primary_readout": "LC-MS or equivalent targeted assay for 10H2DA plus route intermediates; do not use growth/FBA flux alone as success readout",
    }


def priority_tier(row: dict[str, str], module: dict[str, str]) -> str:
    score = float(row["combined_design_feasibility_score"])
    risk = module["p450_construct_risk"]
    if score >= 24 and risk == "medium":
        return "tier1_build_first"
    if score >= 22 and risk in {"medium", "medium_high_activity_risk"}:
        return "tier2_parallel_or_followup"
    if score >= 20:
        return "tier3_secondary_screen"
    return "tier4_deprioritize"


def build_rows() -> list[dict[str, Any]]:
    designs = read_csv(EVAL_DIR / "10h2da_p450_design_recommendations.csv")
    rows = []
    seen = set()
    for idx, design in enumerate(designs, start=1):
        p450 = p450_module(design)
        thio = thioesterase_module(design)
        route = route_modules(design)
        control = controls(design)
        key = (design["route"], design["p450_entry"], design["step1_entry"], design["step2_entry"])
        if key in seen:
            continue
        seen.add(key)
        row = {
            "construct_design_id": f"10H2DA_DESIGN_{idx:03d}",
            "route": design["route"],
            "p450_entry": design["p450_entry"],
            "p450_system_type": design["p450_system_type"],
            "redox_partner_requirement": design["redox_partner_requirement"],
            "thioesterase_entry": design["step1_entry"] if "thioesterase" in design["step1_family"] else design["step2_entry"],
            "combined_design_feasibility_score": design["combined_design_feasibility_score"],
            "recommended_p450_action": design["recommended_p450_action"],
        }
        row.update(p450)
        row.update(thio)
        row.update(route)
        row.update(control)
        row["construct_priority_tier"] = priority_tier(design, p450)
        rows.append(row)
    rows.sort(key=lambda row: (row["construct_priority_tier"], -float(row["combined_design_feasibility_score"])))
    return rows


def render_report(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# 10H2DA Construct and Redox Design Matrix",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Scope",
        "",
        "This report translates P450-adjusted route rankings into construct-level design choices: P450 module, redox partner handling, thioesterase module, route readouts, and controls. It is a design checklist, not an experimental protocol.",
        "",
        "## Outputs",
        "",
        "- `06_evaluation/10h2da_construct_design_matrix.csv`",
        "",
        "## Tier 1 Designs",
        "",
        "| Design | Route | P450 | Redox module | Thioesterase | Score |",
        "|---|---|---|---|---|---:|",
    ]
    for row in [r for r in rows if r["construct_priority_tier"] == "tier1_build_first"][:8]:
        lines.append(f"| {row['construct_design_id']} | {row['route']} | {row['p450_entry']} | {row['redox_module']} | {row['thioesterase_entry']} | {float(row['combined_design_feasibility_score']):.3f} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Build-first designs favor fungal/yeast CYP52M1 with TES1/PTE1 because this combination balances substrate-family relevance, yeast-compatible expression context, and endogenous thioesterase support. CYP505/P450foxy designs remain valuable follow-ups because self-sufficiency reduces CPR uncertainty even when raw route score is lower.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = build_rows()
    write_csv(EVAL_DIR / "10h2da_construct_design_matrix.csv", rows, list(rows[0].keys()))
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "construct_design_rows": len(rows),
        "tier_counts": {tier: sum(1 for row in rows if row["construct_priority_tier"] == tier) for tier in sorted({row["construct_priority_tier"] for row in rows})},
        "outputs": ["06_evaluation/10h2da_construct_design_matrix.csv", "07_reports/10H2DA_construct_design_matrix.md"],
    }
    (EVAL_DIR / "10h2da_construct_design_manifest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORT_DIR / "10H2DA_construct_design_matrix.md").write_text(render_report(payload, rows), encoding="utf-8")
    print(REPORT_DIR / "10H2DA_construct_design_matrix.md")


if __name__ == "__main__":
    main()
