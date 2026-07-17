from __future__ import annotations

import json
import sys
from typing import Any

import cobra
from cobra.flux_analysis import flux_variability_analysis, pfba

import test_10h2da_candidate_extension_fba as extension


TOLERANCE = 1e-8
TARGET_DEMAND = "DM_CAND_10H2DA_P"


def add_biomass_floor(model: cobra.Model, reaction_id: str, floor: float) -> None:
    biomass = model.reactions.get_by_id(reaction_id)
    model.add_cons_vars(model.problem.Constraint(biomass.flux_expression, lb=floor, name="10h2da_validation_biomass_floor"))


def maximize_target(model: cobra.Model, biomass_id: str, biomass_floor: float | None = None) -> tuple[cobra.Model, Any]:
    work = model.copy()
    if biomass_floor is not None:
        add_biomass_floor(work, biomass_id, biomass_floor)
    work.objective = TARGET_DEMAND
    return work, work.optimize()


def restricted_medium(model: cobra.Model, exchange_id: str | None) -> cobra.Model:
    work = model.copy()
    medium = dict(work.medium)
    if exchange_id:
        if exchange_id not in work.reactions:
            raise ValueError(f"Configured exchange is absent from model: {exchange_id}")
        medium.pop(exchange_id, None)
    work.medium = medium
    return work


def run_validation() -> dict[str, Any]:
    deployment = extension.load_config()
    target_config = extension.load_target_config()
    model = cobra.io.load_yaml_model(deployment["models"]["yeast_metatwin"])
    model.solver = deployment["runtime"].get("default_solver", "glpk")

    configured_compounds = {row["model_metabolite_id"]: row for row in target_config["compounds"]}
    precursor = configured_compounds["s_1507"]
    model_precursor = model.metabolites.get_by_id("s_1507")
    definition_errors = []
    if (precursor["formula"], precursor["charge"]) != (model_precursor.formula, model_precursor.charge):
        definition_errors.append("configured s_1507 formula/charge does not match the source model")
    if target_config["target"]["formula"] != configured_compounds["cand_10h2da_p"]["formula"]:
        definition_errors.append("target formula does not match cand_10h2da_p")

    extension.add_combined_route(model, target_config)
    candidate_ids = [row["reaction_id"] for row in target_config["candidate_reactions"]]
    balances = {}
    for reaction_id in candidate_ids:
        imbalance = model.reactions.get_by_id(reaction_id).check_mass_balance()
        balances[reaction_id] = imbalance
        if imbalance:
            definition_errors.append(f"{reaction_id} imbalance: {imbalance}")

    fba_config = target_config.get("fba_validation", {})
    biomass = extension.resolve_biomass_reaction(model, fba_config.get("biomass_reaction_id"))
    growth_model = model.copy()
    growth_model.objective = biomass.id
    growth_solution = growth_model.optimize()
    growth_max = float(growth_solution.objective_value) if growth_solution.status == "optimal" else 0.0
    biomass_floor = growth_max * float(fba_config.get("biomass_floor_fraction", 0.1))

    target_model, target_solution = maximize_target(model, biomass.id, biomass_floor)
    target_max = float(target_solution.objective_value) if target_solution.status == "optimal" else 0.0
    failures = list(definition_errors)
    warnings = []
    if growth_solution.status != "optimal" or growth_max <= TOLERANCE:
        failures.append("native biomass objective is not feasible")
    if target_solution.status != "optimal" or target_max <= TOLERANCE:
        failures.append("10H2DA demand is not feasible with the configured biomass floor")

    pfba_solution = pfba(target_model, fraction_of_optimum=1.0)
    pfba_target = float(pfba_solution.fluxes[TARGET_DEMAND])
    if abs(pfba_target - target_max) > 1e-6:
        failures.append(f"pFBA target flux {pfba_target} does not preserve FBA optimum {target_max}")

    fva = flux_variability_analysis(target_model, reaction_list=[TARGET_DEMAND, *candidate_ids], fraction_of_optimum=0.9, processes=1)
    demand_fva = {key: float(value) for key, value in fva.loc[TARGET_DEMAND].to_dict().items()}
    if demand_fva["minimum"] < 0.9 * target_max - 1e-6:
        failures.append("FVA demand minimum does not satisfy the requested 90% optimum")

    no_carbon_model = restricted_medium(model, fba_config.get("carbon_exchange_id"))
    _, no_carbon_solution = maximize_target(no_carbon_model, biomass.id)
    no_carbon_flux = float(no_carbon_solution.objective_value or 0.0) if no_carbon_solution.status == "optimal" else 0.0
    if no_carbon_flux > TOLERANCE:
        failures.append(f"10H2DA demand persists without the configured carbon source: {no_carbon_flux}")

    no_oxygen_model = restricted_medium(model, fba_config.get("oxygen_exchange_id"))
    _, no_oxygen_solution = maximize_target(no_oxygen_model, biomass.id)
    no_oxygen_flux = float(no_oxygen_solution.objective_value or 0.0) if no_oxygen_solution.status == "optimal" else 0.0
    if no_oxygen_flux > TOLERANCE:
        warnings.append(
            "Closing oxygen exchange does not create an anoxic model: catalase reactions r_0255/r_0256 can regenerate molecular oxygen from model-supplied peroxide. "
            f"The resulting 10H2DA demand is {no_oxygen_flux}; do not interpret this sensitivity as anaerobic biochemical feasibility."
        )

    closed_model = model.copy()
    closed_model.medium = {}
    _, closed_solution = maximize_target(closed_model, biomass.id)
    closed_flux = float(closed_solution.objective_value or 0.0) if closed_solution.status == "optimal" else 0.0
    if closed_flux > TOLERANCE:
        failures.append(f"10H2DA demand persists with all exchanges closed, indicating an unbounded source/cycle: {closed_flux}")

    carbon_exchange_id = fba_config.get("carbon_exchange_id")
    carbon_flux = abs(float(target_solution.fluxes[carbon_exchange_id])) if carbon_exchange_id else 0.0
    molar_yield = target_max / carbon_flux if carbon_flux > TOLERANCE else None
    return {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
        "protonation_assumption": target_config.get("protonation_assumption"),
        "biomass_reaction_id": biomass.id,
        "native_growth_max": growth_max,
        "biomass_floor": biomass_floor,
        "candidate_reaction_balance": balances,
        "fba_target_max": target_max,
        "pfba_target_flux": pfba_target,
        "fva_target_demand": demand_fva,
        "condition_sensitivity": {
            "no_configured_carbon_target_max": no_carbon_flux,
            "no_oxygen_target_max": no_oxygen_flux,
            "all_exchanges_closed_target_max": closed_flux,
        },
        "molar_target_per_carbon_source": molar_yield,
        "gene_knockout": {
            "status": "not_applicable",
            "reason": "Candidate reactions have no evidence-backed GPR assignments in current assets; assigning genes for knockout validation would invent evidence.",
        },
    }


def main() -> None:
    try:
        result = run_validation()
    except Exception as exc:
        print(json.dumps({"passed": False, "failures": [f"{type(exc).__name__}: {exc}"]}, indent=2))
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
