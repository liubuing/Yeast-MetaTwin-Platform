from __future__ import annotations

"""Transcriptomics/proteomics constraint layer for condition-specific FBA.

Implements GIMME and iMAT algorithms to constrain genome-scale metabolic
models with gene expression data, enabling condition-specific flux predictions.

Includes pseudo-GPR inference for underground reactions (rxn*) that lack
native gene-protein-reaction associations, using metabolite-neighborhood
co-expression correlation.
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATABASES_DIR = ROOT / "01_databases"
MODELS_DIR = ROOT / "03_models"


class OmicsConstraintError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Expression data loading
# ---------------------------------------------------------------------------

def load_expression_matrix(
    path: Path,
    gene_id_column: str = "gene_id",
) -> tuple[list[str], list[str], np.ndarray]:
    """Load a gene expression matrix from CSV.

    Expected format: rows = genes, columns = conditions.
    First column is gene identifier, remaining columns are condition expression values (TPM/FPKM).

    Args:
        path: Path to expression CSV.
        gene_id_column: Name of the gene ID column.

    Returns:
        Tuple of (gene_ids, condition_names, expression_matrix [n_genes, n_conditions]).
    """
    if not path.exists():
        raise OmicsConstraintError(f"Expression matrix not found: {path}")

    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        if gene_id_column not in fieldnames:
            raise OmicsConstraintError(
                f"Column '{gene_id_column}' not found. Available: {fieldnames}"
            )
        conditions = [c for c in fieldnames if c != gene_id_column]
        gene_ids: list[str] = []
        rows: list[list[float]] = []

        for row in reader:
            gene_ids.append(row[gene_id_column])
            values = []
            for cond in conditions:
                try:
                    values.append(float(row.get(cond, 0) or 0))
                except ValueError:
                    values.append(0.0)
            rows.append(values)

    matrix = np.array(rows, dtype=np.float64)
    return gene_ids, conditions, matrix


# ---------------------------------------------------------------------------
# GIMME algorithm
# ---------------------------------------------------------------------------

def apply_gimme(
    model: Any,
    expression: dict[str, float],
    threshold: float | None = None,
    threshold_percentile: float = 25.0,
) -> Any:
    """Apply GIMME (Gene Inactivity Moderated by Metabolism and Expression).

    Penalizes flux through reactions associated with lowly-expressed genes.
    The objective is modified to: maximize original_obj - penalty * sum(low_expr_fluxes).

    Args:
        model: COBRApy model (modified in place within a context).
        expression: Dict mapping gene_id -> expression value (TPM).
        threshold: Absolute expression threshold. If None, uses percentile.
        threshold_percentile: Percentile of expression values to use as threshold.

    Returns:
        Modified model (use within `with model:` context for safety).

    Reference: Becker & Palsson 2008, PNAS.
    """
    try:
        import cobra
    except ImportError as exc:
        raise OmicsConstraintError(f"COBRApy required: {exc}") from exc

    # Determine threshold
    expr_values = np.array(list(expression.values()))
    if threshold is None:
        threshold = float(np.percentile(expr_values, threshold_percentile))

    # Identify lowly-expressed genes
    low_genes = {g for g, v in expression.items() if v < threshold}

    # Penalize reactions with low-expression GPRs
    penalty_coefficients: dict[str, float] = {}
    for reaction in model.reactions:
        if not reaction.gene_reaction_rule:
            continue
        genes_in_rxn = {g.id for g in reaction.genes}
        # If ALL genes in the reaction are lowly expressed, penalize
        if genes_in_rxn and genes_in_rxn.issubset(low_genes):
            # Penalty proportional to how far below threshold
            max_expr = max(expression.get(g, 0) for g in genes_in_rxn)
            penalty = max(0, threshold - max_expr) / max(threshold, 1e-10)
            penalty_coefficients[reaction.id] = penalty

    # Modify objective: original - weighted penalties
    original_obj = model.objective.expression
    penalty_expr = sum(
        coeff * model.reactions.get_by_id(rxn_id).forward_variable
        for rxn_id, coeff in penalty_coefficients.items()
        if rxn_id in model.reactions
    )

    model.objective = original_obj - 0.001 * penalty_expr

    # Store metadata
    model._gimme_info = {
        "threshold": threshold,
        "threshold_percentile": threshold_percentile,
        "n_low_genes": len(low_genes),
        "n_penalized_reactions": len(penalty_coefficients),
        "total_genes_in_expression": len(expression),
    }

    return model


# ---------------------------------------------------------------------------
# iMAT algorithm
# ---------------------------------------------------------------------------

def apply_imat(
    model: Any,
    expression: dict[str, float],
    high_threshold: float | None = None,
    low_threshold: float | None = None,
    high_percentile: float = 75.0,
    low_percentile: float = 25.0,
) -> Any:
    """Apply iMAT (Integrative Metabolic Analysis Tool).

    Forces reactions with highly-expressed genes to carry flux,
    and minimizes flux through reactions with lowly-expressed genes.

    Args:
        model: COBRApy model.
        expression: Dict mapping gene_id -> expression value.
        high_threshold: Absolute threshold for "high" expression.
        low_threshold: Absolute threshold for "low" expression.
        high_percentile: Percentile for high threshold (if not absolute).
        low_percentile: Percentile for low threshold (if not absolute).

    Returns:
        Modified model with iMAT constraints applied.

    Reference: Shlomi et al. 2008, Molecular Systems Biology.
    """
    try:
        import cobra
    except ImportError as exc:
        raise OmicsConstraintError(f"COBRApy required: {exc}") from exc

    expr_values = np.array(list(expression.values()))
    if high_threshold is None:
        high_threshold = float(np.percentile(expr_values, high_percentile))
    if low_threshold is None:
        low_threshold = float(np.percentile(expr_values, low_percentile))

    high_genes = {g for g, v in expression.items() if v >= high_threshold}
    low_genes = {g for g, v in expression.items() if v < low_threshold}

    # Classify reactions
    high_reactions: list[str] = []
    low_reactions: list[str] = []

    for reaction in model.reactions:
        if not reaction.gene_reaction_rule:
            continue
        genes_in_rxn = {g.id for g in reaction.genes}
        if not genes_in_rxn:
            continue

        # iMAT logic: reaction is "high" if ANY gene is highly expressed (OR logic)
        if genes_in_rxn & high_genes:
            high_reactions.append(reaction.id)
        # Reaction is "low" if ALL genes are lowly expressed (AND logic)
        elif genes_in_rxn.issubset(low_genes):
            low_reactions.append(reaction.id)

    # Set constraints: force high reactions to carry minimum flux
    # Use a small epsilon to avoid over-constraining
    min_flux_fraction = 0.01
    for rxn_id in high_reactions:
        rxn = model.reactions.get_by_id(rxn_id)
        # Only constrain if reaction can carry forward flux
        if rxn.upper_bound > 0:
            rxn.lower_bound = max(rxn.lower_bound, min_flux_fraction)

    # Minimize flux through low reactions via objective modification
    original_obj = model.objective.expression
    low_penalty = sum(
        model.reactions.get_by_id(rxn_id).forward_variable
        for rxn_id in low_reactions
        if rxn_id in model.reactions
    )
    model.objective = original_obj - 0.01 * low_penalty

    model._imat_info = {
        "high_threshold": high_threshold,
        "low_threshold": low_threshold,
        "n_high_genes": len(high_genes),
        "n_low_genes": len(low_genes),
        "n_high_reactions": len(high_reactions),
        "n_low_reactions": len(low_reactions),
    }

    return model


# ---------------------------------------------------------------------------
# Pseudo-GPR inference for underground reactions
# ---------------------------------------------------------------------------

def infer_pseudo_gpr(
    model: Any,
    expression_matrix: np.ndarray,
    gene_ids: list[str],
    correlation_threshold: float = 0.7,
    max_neighbors: int = 10,
) -> dict[str, list[str]]:
    """Infer pseudo-GPR associations for reactions lacking native GPR rules.

    Strategy: For each reaction without GPR, find metabolite neighbors
    (other reactions sharing substrates/products), collect their associated
    genes, and retain genes with high co-expression correlation.

    Args:
        model: COBRApy model.
        expression_matrix: [n_genes, n_conditions] expression data.
        gene_ids: Gene ID list matching expression_matrix rows.
        correlation_threshold: Minimum Pearson correlation to assign a gene.
        max_neighbors: Maximum number of neighbor reactions to consider.

    Returns:
        Dict mapping reaction_id -> list of inferred gene IDs.
    """
    gene_id_to_idx = {g: i for i, g in enumerate(gene_ids)}

    # Pre-compute gene-gene correlation matrix (only for genes in model)
    model_gene_ids = [g.id for g in model.genes if g.id in gene_id_to_idx]
    if len(model_gene_ids) < 2:
        return {}

    model_gene_indices = [gene_id_to_idx[g] for g in model_gene_ids]
    expr_subset = expression_matrix[model_gene_indices, :]

    # Compute correlation matrix
    if expr_subset.shape[1] < 3:
        # Not enough conditions for meaningful correlation
        return {}

    # Standardize for Pearson correlation
    means = expr_subset.mean(axis=1, keepdims=True)
    stds = expr_subset.std(axis=1, keepdims=True)
    stds[stds == 0] = 1.0
    standardized = (expr_subset - means) / stds
    corr_matrix = (standardized @ standardized.T) / expr_subset.shape[1]

    gene_to_corr_idx = {g: i for i, g in enumerate(model_gene_ids)}

    # Build metabolite -> reactions index
    met_to_rxns: dict[str, list[str]] = {}
    for rxn in model.reactions:
        for met in rxn.metabolites:
            met_to_rxns.setdefault(met.id, []).append(rxn.id)

    # Infer pseudo-GPR for reactions without native GPR
    pseudo_gpr: dict[str, list[str]] = {}
    reactions_without_gpr = [r for r in model.reactions if not r.gene_reaction_rule]

    for rxn in reactions_without_gpr:
        # Find neighbor reactions (sharing metabolites)
        neighbor_rxn_ids: set[str] = set()
        for met in rxn.metabolites:
            for other_id in met_to_rxns.get(met.id, []):
                if other_id != rxn.id:
                    neighbor_rxn_ids.add(other_id)
            if len(neighbor_rxn_ids) >= max_neighbors * 3:
                break

        # Collect genes from neighbors
        neighbor_genes: set[str] = set()
        for other_id in list(neighbor_rxn_ids)[:max_neighbors]:
            other_rxn = model.reactions.get_by_id(other_id)
            for gene in other_rxn.genes:
                neighbor_genes.add(gene.id)

        if not neighbor_genes:
            continue

        # Filter by co-expression correlation
        # Use mean correlation with all neighbor genes as score
        candidate_genes: list[tuple[str, float]] = []
        for gene_id in neighbor_genes:
            if gene_id not in gene_to_corr_idx:
                continue
            corr_idx = gene_to_corr_idx[gene_id]
            # Mean correlation with other neighbor genes
            other_indices = [
                gene_to_corr_idx[g] for g in neighbor_genes
                if g != gene_id and g in gene_to_corr_idx
            ]
            if not other_indices:
                continue
            mean_corr = float(np.mean(corr_matrix[corr_idx, other_indices]))
            if mean_corr >= correlation_threshold:
                candidate_genes.append((gene_id, mean_corr))

        if candidate_genes:
            # Sort by correlation, take top genes
            candidate_genes.sort(key=lambda x: -x[1])
            pseudo_gpr[rxn.id] = [g for g, _ in candidate_genes[:5]]

    return pseudo_gpr


def apply_pseudo_gpr_to_model(
    model: Any,
    pseudo_gpr: dict[str, list[str]],
) -> int:
    """Apply inferred pseudo-GPR rules to the model.

    Modifies reactions in place, adding GPR rules marked as inferred.

    Args:
        model: COBRApy model.
        pseudo_gpr: Dict from infer_pseudo_gpr().

    Returns:
        Number of reactions updated.
    """
    updated = 0
    for rxn_id, gene_ids in pseudo_gpr.items():
        if rxn_id not in model.reactions:
            continue
        rxn = model.reactions.get_by_id(rxn_id)
        if rxn.gene_reaction_rule:
            continue  # Don't overwrite native GPR

        # Build OR rule (any inferred gene can catalyze)
        gpr_rule = " or ".join(gene_ids)
        try:
            rxn.gene_reaction_rule = gpr_rule
            rxn.annotation["pseudo_gpr"] = "inferred_coexpression"
            rxn.annotation["pseudo_gpr_genes"] = ",".join(gene_ids)
            updated += 1
        except Exception:
            pass  # Skip if GPR parsing fails

    return updated


# ---------------------------------------------------------------------------
# Condition-specific FBA analysis
# ---------------------------------------------------------------------------

def condition_specific_fba(
    model: Any,
    expression_matrix: np.ndarray,
    gene_ids: list[str],
    conditions: list[str],
    method: str = "gimme",
    demand_metabolite: str | None = None,
    biomass_fraction: float = 0.10,
    use_pseudo_gpr: bool = True,
    correlation_threshold: float = 0.7,
) -> list[dict[str, Any]]:
    """Run FBA under multiple conditions with omics constraints.

    Args:
        model: COBRApy model (unconstrained baseline).
        expression_matrix: [n_genes, n_conditions] expression data.
        gene_ids: Gene IDs matching matrix rows.
        conditions: Condition names matching matrix columns.
        method: 'gimme' or 'imat'.
        demand_metabolite: If set, inject demand reaction and maximize.
        biomass_fraction: Minimum biomass fraction constraint.
        use_pseudo_gpr: Whether to infer pseudo-GPR for underground reactions.
        correlation_threshold: Threshold for pseudo-GPR inference.

    Returns:
        List of per-condition result dicts.
    """
    try:
        import cobra
    except ImportError as exc:
        raise OmicsConstraintError(f"COBRApy required: {exc}") from exc

    results: list[dict[str, Any]] = []

    # Optionally infer pseudo-GPR once (condition-independent)
    pseudo_gpr: dict[str, list[str]] = {}
    if use_pseudo_gpr:
        print("Inferring pseudo-GPR for underground reactions...")
        pseudo_gpr = infer_pseudo_gpr(
            model, expression_matrix, gene_ids,
            correlation_threshold=correlation_threshold,
        )
        n_updated = apply_pseudo_gpr_to_model(model, pseudo_gpr)
        print(f"  Assigned pseudo-GPR to {n_updated} reactions "
              f"(coverage: {n_updated}/{len([r for r in model.reactions if not r.gene_reaction_rule])} without native GPR)")

    # Get wild-type biomass for reference
    wt_solution = model.optimize()
    wt_biomass = wt_solution.objective_value if wt_solution.status == "optimal" else 0.0

    for cond_idx, condition in enumerate(conditions):
        # Build expression dict for this condition
        expr_dict = {
            gene_ids[i]: float(expression_matrix[i, cond_idx])
            for i in range(len(gene_ids))
        }

        with model:
            # Apply constraint method
            if method == "gimme":
                apply_gimme(model, expr_dict)
            elif method == "imat":
                apply_imat(model, expr_dict)
            else:
                raise OmicsConstraintError(f"Unknown method: {method}. Use 'gimme' or 'imat'.")

            # Enforce biomass floor
            for rxn in model.reactions:
                if "biomass" in rxn.id.lower():
                    rxn.lower_bound = max(rxn.lower_bound, biomass_fraction * wt_biomass)
                    break

            # Optionally maximize demand
            if demand_metabolite and demand_metabolite in model.metabolites:
                dm_id = f"DM_{demand_metabolite}_{condition}"
                dm = cobra.Reaction(dm_id)
                dm.lower_bound = 0
                dm.upper_bound = 1000
                dm.add_metabolites({model.metabolites.get_by_id(demand_metabolite): -1.0})
                model.add_reactions([dm])
                model.objective = dm_id

            sol = model.optimize()

            result: dict[str, Any] = {
                "condition": condition,
                "method": method,
                "status": sol.status,
                "objective_value": round(sol.objective_value, 6) if sol.status == "optimal" else None,
                "wt_biomass": round(wt_biomass, 6),
                "biomass_fraction_enforced": biomass_fraction,
            }

            if demand_metabolite:
                result["demand_metabolite"] = demand_metabolite
                result["max_demand_flux"] = round(sol.fluxes.get(dm_id, 0), 6) if sol.status == "optimal" else 0.0

            # Attach constraint info
            if hasattr(model, "_gimme_info"):
                result["constraint_info"] = model._gimme_info
            elif hasattr(model, "_imat_info"):
                result["constraint_info"] = model._imat_info

            results.append(result)

        print(f"  {condition}: status={sol.status}, obj={sol.objective_value:.6f}" if sol.status == "optimal" else f"  {condition}: {sol.status}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Condition-specific FBA with omics constraints (GIMME/iMAT).",
    )
    parser.add_argument("--species", type=str, default="yeast",
                        help="Species ID for GEM loading.")
    parser.add_argument("--expression", type=Path, required=True,
                        help="Expression matrix CSV (genes x conditions).")
    parser.add_argument("--method", type=str, default="gimme",
                        choices=["gimme", "imat"],
                        help="Constraint method.")
    parser.add_argument("--demand", type=str, default=None,
                        help="Metabolite ID for demand reaction analysis.")
    parser.add_argument("--biomass-fraction", type=float, default=0.10,
                        help="Minimum biomass fraction (default: 0.10).")
    parser.add_argument("--no-pseudo-gpr", action="store_true",
                        help="Disable pseudo-GPR inference.")
    parser.add_argument("--correlation-threshold", type=float, default=0.7,
                        help="Pearson correlation threshold for pseudo-GPR.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output results JSON path.")
    args = parser.parse_args()

    # Load GEM
    from load_gem_multispecies import GEMLoadError, load_gem
    try:
        model, profile = load_gem(args.species)
    except (GEMLoadError, Exception) as exc:
        print(f"ERROR loading GEM: {exc}", file=sys.stderr)
        return 1

    # Load expression
    try:
        gene_ids, conditions, expr_matrix = load_expression_matrix(args.expression)
    except OmicsConstraintError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Expression: {len(gene_ids)} genes x {len(conditions)} conditions")
    print(f"Method: {args.method} | Pseudo-GPR: {not args.no_pseudo_gpr}")

    # Run condition-specific FBA
    t0 = time.perf_counter()
    try:
        results = condition_specific_fba(
            model=model,
            expression_matrix=expr_matrix,
            gene_ids=gene_ids,
            conditions=conditions,
            method=args.method,
            demand_metabolite=args.demand,
            biomass_fraction=args.biomass_fraction,
            use_pseudo_gpr=not args.no_pseudo_gpr,
            correlation_threshold=args.correlation_threshold,
        )
    except OmicsConstraintError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - t0
    print(f"\nCompleted {len(results)} conditions in {elapsed:.1f}s")

    # Output
    output_payload = {
        "species": args.species,
        "method": args.method,
        "n_conditions": len(conditions),
        "conditions": conditions,
        "demand_metabolite": args.demand,
        "biomass_fraction": args.biomass_fraction,
        "pseudo_gpr_enabled": not args.no_pseudo_gpr,
        "correlation_threshold": args.correlation_threshold,
        "results": results,
        "runtime_seconds": round(elapsed, 2),
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(output_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Results: {args.output}")
    else:
        print(json.dumps(output_payload, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
