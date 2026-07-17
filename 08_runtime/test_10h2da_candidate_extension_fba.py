from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import cobra
from cobra.util.solver import linear_reaction_coefficients
from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "09_configs" / "deployment_config.json"
TARGET_CONFIG = ROOT / "10_generic_target_workflow" / "examples" / "target_workflow_10h2da_reference.json"
REPORT_DIR = ROOT / "07_reports"
EVAL_DIR = ROOT / "06_evaluation"


KEY_REACTIONS = [
    "r_0399",
    "r_0120",
    "r_0844",
    "r_2248",
    "r_2266",
    "rxn1937",
    "CAND_T2DEC_THIOESTERASE_P",
    "CAND_T2DEC_OMEGA_HYDROXYLASE_P",
    "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P",
    "CAND_10H2DA_COA_THIOESTERASE_P",
    "DM_CAND_10H2DA_P",
    "DM_CAND_T2DEC_P",
    "DM_s_1507",
]


def load_config() -> dict[str, Any]:
    return load_deployment_config()


def load_target_config() -> dict[str, Any]:
    return json.loads(TARGET_CONFIG.read_text(encoding="utf-8"))


def add_metabolite(model: cobra.Model, met_id: str, name: str, formula: str, charge: int, compartment: str) -> cobra.Metabolite:
    if met_id in model.metabolites:
        met = model.metabolites.get_by_id(met_id)
        if (met.formula, met.charge, met.compartment) != (formula, charge, compartment):
            raise ValueError(f"Conflicting definition for {met_id}: {(met.formula, met.charge, met.compartment)} != {(formula, charge, compartment)}")
        return met
    met = cobra.Metabolite(met_id, name=name, formula=formula, charge=charge, compartment=compartment)
    model.add_metabolites([met])
    return met


def add_reaction(model: cobra.Model, rxn_id: str, name: str, stoich: dict[str, float], lower: float = 0.0, upper: float = 1000.0) -> cobra.Reaction:
    if rxn_id in model.reactions:
        return model.reactions.get_by_id(rxn_id)
    rxn = cobra.Reaction(rxn_id)
    rxn.name = name
    rxn.lower_bound = lower
    rxn.upper_bound = upper
    rxn.add_metabolites({model.metabolites.get_by_id(met_id): coeff for met_id, coeff in stoich.items()})
    model.add_reactions([rxn])
    return rxn


def add_candidate_metabolites(model: cobra.Model, target_config: dict[str, Any] | None = None) -> None:
    target_config = target_config or load_target_config()
    compartment = target_config["target"]["compartment"]
    for compound in target_config["compounds"]:
        met_id = compound["model_metabolite_id"]
        if not met_id.startswith("cand_"):
            continue
        add_metabolite(model, met_id, compound["name"], compound["formula"], compound["charge"], compartment)


def add_demands(model: cobra.Model) -> None:
    add_reaction(model, "DM_s_1507", "demand trans-dec-2-enoyl-CoA", {"s_1507": -1})
    add_reaction(model, "DM_CAND_T2DEC_P", "demand trans-2-decenoate", {"cand_t2dec_p": -1})
    add_reaction(model, "DM_CAND_10H2DA_P", "demand 10-hydroxy-trans-2-decenoate", {"cand_10h2da_p": -1})


def add_configured_reactions(model: cobra.Model, reaction_ids: list[str], target_config: dict[str, Any] | None = None) -> None:
    target_config = target_config or load_target_config()
    definitions = {row["reaction_id"]: row for row in target_config["candidate_reactions"]}
    for reaction_id in reaction_ids:
        row = definitions[reaction_id]
        add_reaction(model, reaction_id, row["name"], row["stoichiometry"])


def add_route(model: cobra.Model, route_id: str, target_config: dict[str, Any] | None = None) -> None:
    target_config = target_config or load_target_config()
    add_candidate_metabolites(model, target_config)
    route = next(row for row in target_config["routes"] if row["route_id"] == route_id)
    add_configured_reactions(model, route["reaction_ids"], target_config)
    add_demands(model)


def add_free_acid_route(model: cobra.Model, target_config: dict[str, Any] | None = None) -> None:
    add_route(model, "free_acid_route", target_config)


def add_coa_bound_route(model: cobra.Model, target_config: dict[str, Any] | None = None) -> None:
    add_route(model, "coa_bound_route", target_config)


def add_combined_route(model: cobra.Model, target_config: dict[str, Any] | None = None) -> None:
    target_config = target_config or load_target_config()
    add_candidate_metabolites(model, target_config)
    add_configured_reactions(model, [reaction_id for route in target_config["routes"] for reaction_id in route["reaction_ids"]], target_config)
    add_demands(model)


def resolve_biomass_reaction(model: cobra.Model, override: str | None = None) -> cobra.Reaction:
    if override:
        if override not in model.reactions:
            raise ValueError(f"Configured biomass reaction is absent from model: {override}")
        return model.reactions.get_by_id(override)
    objective_reactions = [reaction for reaction, coefficient in linear_reaction_coefficients(model).items() if coefficient]
    if len(objective_reactions) != 1:
        ids = [reaction.id for reaction in objective_reactions]
        raise ValueError(f"Model objective must resolve to exactly one biomass reaction or use biomass_reaction_id override; found {ids}")
    return objective_reactions[0]


def optimize_objective(model: cobra.Model, objective_id: str, biomass_floor: float | None = None, biomass_reaction_id: str | None = None) -> dict[str, Any]:
    work = model.copy()
    if biomass_floor is not None:
        biomass = resolve_biomass_reaction(work, biomass_reaction_id)
        constraint = work.problem.Constraint(biomass.flux_expression, lb=biomass_floor, name="10h2da_biomass_floor")
        work.add_cons_vars(constraint)
    work.objective = objective_id
    sol = work.optimize()
    fluxes = {}
    if sol.status == "optimal":
        for rid in KEY_REACTIONS:
            if rid in work.reactions:
                value = sol.fluxes.get(rid, 0.0)
                if abs(value) > 1e-9:
                    fluxes[rid] = float(value)
    return {
        "objective_id": objective_id,
        "biomass_reaction_id": biomass_reaction_id,
        "biomass_floor": biomass_floor,
        "status": sol.status,
        "objective_value": float(sol.objective_value) if sol.objective_value is not None else None,
        "nonzero_key_fluxes": fluxes,
    }


def model_summary(model: cobra.Model, biomass_reaction_id: str | None = None) -> dict[str, Any]:
    biomass = resolve_biomass_reaction(model, biomass_reaction_id)
    work = model.copy()
    work.objective = biomass.id
    native = work.optimize()
    objective_reactions = [rxn.id for rxn, coeff in linear_reaction_coefficients(model).items() if coeff]
    return {
        "native_status": native.status,
        "native_objective_value": float(native.objective_value) if native.objective_value is not None else None,
        "native_objective_reactions": objective_reactions,
        "biomass_reaction_id": biomass.id,
    }


def run_scenario(base_model: cobra.Model, name: str, route: str, target_config: dict[str, Any] | None = None) -> dict[str, Any]:
    target_config = target_config or load_target_config()
    model = base_model.copy()
    add_candidate_metabolites(model, target_config)
    add_demands(model)
    if route == "free_acid":
        add_free_acid_route(model, target_config)
    elif route == "coa_bound":
        add_coa_bound_route(model, target_config)
    elif route == "combined":
        add_combined_route(model, target_config)

    fba_config = target_config.get("fba_validation", {})
    biomass_reaction_id = resolve_biomass_reaction(model, fba_config.get("biomass_reaction_id")).id
    native = model_summary(model, biomass_reaction_id)
    biomass_floor = None
    if native["native_status"] == "optimal" and native["native_objective_value"]:
        biomass_floor = native["native_objective_value"] * float(fba_config.get("biomass_floor_fraction", 0.1))

    checks = [
        optimize_objective(model, "DM_s_1507"),
        optimize_objective(model, "DM_CAND_T2DEC_P"),
        optimize_objective(model, "DM_CAND_10H2DA_P"),
    ]
    if biomass_floor is not None:
        checks.extend(
            [
                optimize_objective(model, "DM_s_1507", biomass_floor, biomass_reaction_id),
                optimize_objective(model, "DM_CAND_T2DEC_P", biomass_floor, biomass_reaction_id),
                optimize_objective(model, "DM_CAND_10H2DA_P", biomass_floor, biomass_reaction_id),
            ]
        )
    return {
        "scenario": name,
        "route": route,
        "model_reactions": len(model.reactions),
        "model_metabolites": len(model.metabolites),
        "native": native,
        "checks": checks,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def flatten_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for scenario in payload["scenarios"]:
        for check in scenario["checks"]:
            rows.append(
                {
                    "scenario": scenario["scenario"],
                    "route": scenario["route"],
                    "objective_id": check["objective_id"],
                    "biomass_floor": "" if check["biomass_floor"] is None else check["biomass_floor"],
                    "status": check["status"],
                    "objective_value": check["objective_value"],
                    "nonzero_key_fluxes_json": json.dumps(check["nonzero_key_fluxes"], sort_keys=True),
                }
            )
    return rows


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# 10H2DA Candidate Extension FBA",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Candidate Reactions",
        "",
        "| ID | Equation | Interpretation |",
        "|---|---|---|",
        "| CAND_T2DEC_THIOESTERASE_P | trans-dec-2-enoyl-CoA + H2O -> trans-2-decenoate + CoA + H+ | TES1-like terminal hydrolysis candidate |",
        "| CAND_T2DEC_OMEGA_HYDROXYLASE_P | trans-2-decenoate + NADPH + O2 + H+ -> 10H2DA + NADP+ + H2O | free-acid omega hydroxylation candidate |",
        "| CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | trans-dec-2-enoyl-CoA + NADPH + O2 + H+ -> 10-hydroxy-trans-2-decenoyl-CoA + NADP+ + H2O | CoA-bound omega hydroxylation candidate |",
        "| CAND_10H2DA_COA_THIOESTERASE_P | 10-hydroxy-trans-2-decenoyl-CoA + H2O -> 10H2DA + CoA + H+ | hydroxylated thioester hydrolysis candidate |",
        "",
        "## FBA Results",
        "",
        "| Scenario | Objective | Biomass floor | Status | Max flux | Key fluxes |",
        "|---|---|---:|---|---:|---|",
    ]
    for row in flatten_results(payload):
        value = row["objective_value"]
        value_text = "" if value is None else f"{float(value):.6g}"
        floor = row["biomass_floor"]
        floor_text = "" if floor == "" else f"{float(floor):.6g}"
        lines.append(
            f"| {row['scenario']} | {row['objective_id']} | {floor_text} | {row['status']} | {value_text} | `{row['nonzero_key_fluxes_json']}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This is a feasibility test, not proof of enzyme specificity. A positive 10H2DA demand flux means the current metabolic network can supply precursors and cofactors after adding the stated candidate terminal reactions. The terminal reactions still require external enzyme/database/experimental validation before they should be treated as curated model reactions.",
            "",
            "## Output Files",
            "",
            "- `06_evaluation/10h2da_candidate_extension_fba.json`",
            "- `06_evaluation/10h2da_candidate_extension_fba.csv`",
            "- `07_reports/10H2DA_candidate_extension_fba.md`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    config = load_config()
    target_config = load_target_config()
    model = cobra.io.load_yaml_model(config["models"]["yeast_metatwin"])
    model.solver = config["runtime"].get("default_solver", "glpk")
    scenarios = [
        run_scenario(model, "target_demand_only", "none", target_config),
        run_scenario(model, "free_acid_terminal_route", "free_acid", target_config),
        run_scenario(model, "coa_bound_terminal_route", "coa_bound", target_config),
        run_scenario(model, "combined_terminal_routes", "combined", target_config),
    ]
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model_path": config["models"]["yeast_metatwin"],
        "scenarios": scenarios,
    }
    EVAL_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    (EVAL_DIR / "10h2da_candidate_extension_fba.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(
        EVAL_DIR / "10h2da_candidate_extension_fba.csv",
        flatten_results(payload),
        ["scenario", "route", "objective_id", "biomass_floor", "status", "objective_value", "nonzero_key_fluxes_json"],
    )
    (REPORT_DIR / "10H2DA_candidate_extension_fba.md").write_text(render_report(payload), encoding="utf-8")
    print(REPORT_DIR / "10H2DA_candidate_extension_fba.md")


if __name__ == "__main__":
    main()
