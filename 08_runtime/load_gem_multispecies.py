from __future__ import annotations

"""Multi-species GEM loader with unified FBA interface.

Loads genome-scale metabolic models for any configured species,
validates FBA feasibility, and provides a consistent API for
demand-reaction injection and flux analysis.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import cobra

from species_profile import ROOT, SpeciesProfileError, load_species_profile


class GEMLoadError(RuntimeError):
    pass


_FORMAT_READERS = {
    "yml": cobra.io.load_yaml_model,
    "yaml": cobra.io.load_yaml_model,
    "xml": cobra.io.read_sbml_model,
    "json": cobra.io.load_json_model,
    "mat": cobra.io.load_matlab_model,
}


def load_gem(
    species_id: str,
    solver: str | None = None,
    species_dir: Path | None = None,
) -> tuple[cobra.Model, dict[str, Any]]:
    """Load a GEM for the given species and verify FBA feasibility.

    Args:
        species_id: Species identifier matching a profile in 09_configs/species/.
        solver: Override solver (default: from species profile).
        species_dir: Override species config directory.

    Returns:
        Tuple of (cobra.Model, species_profile_dict).

    Raises:
        GEMLoadError: If GEM file missing, unreadable, or FBA infeasible.
        SpeciesProfileError: If species profile invalid.
    """
    profile = load_species_profile(species_id, species_dir=species_dir)
    gem_info = profile["gem"]
    gem_path = Path(profile["gem"]["path_resolved"])
    fmt = gem_info["format"]

    if not gem_path.exists():
        raise GEMLoadError(
            f"GEM file not found: {gem_path}\n"
            f"Species '{species_id}' expects {fmt.upper()} at {gem_info['path']}"
        )

    reader = _FORMAT_READERS.get(fmt)
    if reader is None:
        raise GEMLoadError(f"Unsupported GEM format: {fmt}")

    t0 = time.perf_counter()
    try:
        model = reader(str(gem_path))
    except Exception as exc:
        raise GEMLoadError(f"failed to load GEM {gem_path}: {exc}") from exc
    load_time = time.perf_counter() - t0

    # Set solver
    solver_name = solver or profile.get("solver", "glpk")
    try:
        model.solver = solver_name
    except Exception:
        pass  # Fall back to default if requested solver unavailable

    # Set biomass objective
    biomass_id = profile["biomass_reaction"]
    if biomass_id in model.reactions:
        model.objective = biomass_id
    else:
        # Try to find a biomass-like reaction
        biomass_candidates = [r for r in model.reactions if "biomass" in r.id.lower()]
        if biomass_candidates:
            model.objective = biomass_candidates[0].id
            biomass_id = biomass_candidates[0].id
        else:
            raise GEMLoadError(
                f"Biomass reaction '{biomass_id}' not found in {species_id} GEM "
                f"and no alternative identified."
            )

    # Verify FBA feasibility
    solution = model.optimize()
    if solution.status != "optimal":
        raise GEMLoadError(
            f"FBA infeasible for {species_id} (status={solution.status}). "
            f"Check GEM integrity."
        )

    profile["_gem_stats"] = {
        "n_reactions": len(model.reactions),
        "n_metabolites": len(model.metabolites),
        "n_genes": len(model.genes),
        "fba_objective_value": solution.objective_value,
        "fba_status": solution.status,
        "load_time_seconds": round(load_time, 3),
        "solver_used": model.solver.interface.__name__.split(".")[-1],
        "biomass_reaction_used": biomass_id,
    }

    return model, profile


def inject_demand_reaction(
    model: cobra.Model,
    metabolite_id: str,
    lb: float = 0.0,
    ub: float = 1000.0,
    reaction_id: str | None = None,
) -> str:
    """Add a demand reaction for a target metabolite and return its ID.

    Args:
        model: COBRApy model (modified in place).
        metabolite_id: Metabolite to create demand for.
        lb: Lower bound of demand reaction.
        ub: Upper bound of demand reaction.
        reaction_id: Custom ID (default: DM_<metabolite_id>).

    Returns:
        The demand reaction ID.
    """
    if metabolite_id not in model.metabolites:
        raise GEMLoadError(f"Metabolite '{metabolite_id}' not in model.")

    rxn_id = reaction_id or f"DM_{metabolite_id}"
    if rxn_id in model.reactions:
        return rxn_id

    demand = cobra.Reaction(rxn_id)
    demand.name = f"Demand for {metabolite_id}"
    demand.lower_bound = lb
    demand.upper_bound = ub
    demand.add_metabolites({model.metabolites.get_by_id(metabolite_id): -1.0})
    model.add_reactions([demand])
    return rxn_id


def fba_with_biomass_floor(
    model: cobra.Model,
    demand_rxn_id: str,
    biomass_fraction: float = 0.10,
) -> dict[str, Any]:
    """Maximize demand flux subject to a minimum biomass constraint.

    Args:
        model: COBRApy model with demand reaction already injected.
        demand_rxn_id: ID of the demand reaction to maximize.
        biomass_fraction: Minimum fraction of wild-type biomass (0-1).

    Returns:
        Dict with max_demand_flux, biomass_value, status.
    """
    # Get wild-type biomass
    wt_biomass = model.optimize().objective_value
    if wt_biomass <= 0:
        return {"status": "infeasible_wt", "max_demand_flux": 0.0, "biomass_value": 0.0}

    # Find biomass reaction
    biomass_rxn = model.reactions.get_by_id(model.objective.name if hasattr(model.objective, "name") else str(model.objective.expression).split()[0])

    # Constrain biomass to minimum fraction
    with model:
        # Set biomass lower bound
        for rxn in model.reactions:
            if "biomass" in rxn.id.lower() or rxn.id == model.objective.name:
                rxn.lower_bound = biomass_fraction * wt_biomass
                break

        # Maximize demand
        model.objective = demand_rxn_id
        sol = model.optimize()

        if sol.status != "optimal":
            return {
                "status": sol.status,
                "max_demand_flux": 0.0,
                "biomass_value": biomass_fraction * wt_biomass,
                "wt_biomass": wt_biomass,
            }

        demand_flux = sol.fluxes[demand_rxn_id]
        return {
            "status": "optimal",
            "max_demand_flux": round(demand_flux, 6),
            "biomass_value": round(sol.objective_value, 6),
            "wt_biomass": round(wt_biomass, 6),
            "biomass_fraction_enforced": biomass_fraction,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load and validate a species GEM, optionally run FBA checks.",
    )
    parser.add_argument(
        "--species",
        type=str,
        required=True,
        help="Species ID (e.g. yeast, ecoli, cglutamicum).",
    )
    parser.add_argument(
        "--solver",
        type=str,
        default=None,
        help="Override solver (glpk, gurobi, cplex).",
    )
    parser.add_argument(
        "--demand",
        type=str,
        default=None,
        help="Metabolite ID to inject a demand reaction for.",
    )
    parser.add_argument(
        "--biomass-fraction",
        type=float,
        default=0.10,
        help="Minimum biomass fraction for constrained FBA (default: 0.10).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write results JSON to this path.",
    )
    args = parser.parse_args()

    try:
        model, profile = load_gem(args.species, solver=args.solver)
    except (GEMLoadError, SpeciesProfileError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    stats = profile["_gem_stats"]
    print(f"Loaded {args.species}: {stats['n_reactions']} reactions, "
          f"{stats['n_metabolites']} metabolites, {stats['n_genes']} genes")
    print(f"FBA objective ({stats['biomass_reaction_used']}): {stats['fba_objective_value']:.6f} h^-1")
    print(f"Solver: {stats['solver_used']} | Load time: {stats['load_time_seconds']}s")

    result: dict[str, Any] = {"species": args.species, "gem_stats": stats}

    if args.demand:
        try:
            dm_id = inject_demand_reaction(model, args.demand)
            fba_result = fba_with_biomass_floor(model, dm_id, args.biomass_fraction)
            result["demand_analysis"] = {
                "metabolite": args.demand,
                "demand_reaction": dm_id,
                **fba_result,
            }
            print(f"\nDemand analysis for {args.demand}:")
            print(f"  Max flux: {fba_result['max_demand_flux']}")
            print(f"  Status: {fba_result['status']}")
        except GEMLoadError as exc:
            print(f"ERROR (demand): {exc}", file=sys.stderr)
            return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nResults written to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
