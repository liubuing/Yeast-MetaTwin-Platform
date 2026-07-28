from __future__ import annotations

"""Cross-species metabolic prediction workflow CLI.

Unified entry point that orchestrates the full prediction pipeline:
  1. Load species GEM + validate FBA
  2. Encode enzyme candidates with ESM-2
  3. Run multi-task prediction (EC + kcat + FBA feasibility)
  4. Apply omics constraints (condition-specific)
  5. Rank candidates with active learning acquisition
  6. Generate prioritized report

Supports --species, --condition, --acquisition modes and --dry-run.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs"
REPORTS_DIR = ROOT / "07_reports"


class WorkflowError(RuntimeError):
    pass


def run_workflow(
    species: str,
    target_metabolite: str | None = None,
    condition: str | None = None,
    expression_path: Path | None = None,
    constraint_method: str = "gimme",
    acquisition_method: str = "ei",
    fasta_path: Path | None = None,
    embeddings_path: Path | None = None,
    ensemble_dir: Path | None = None,
    top_k: int = 20,
    biomass_fraction: float = 0.10,
    output_dir: Path | None = None,
    dry_run: bool = False,
    device: str | None = None,
) -> dict[str, Any]:
    """Execute the full cross-species prediction workflow.

    Args:
        species: Species ID (yeast, ecoli, cglutamicum).
        target_metabolite: Target compound metabolite ID for demand analysis.
        condition: Expression condition name (if expression_path provided).
        expression_path: Path to expression matrix CSV.
        constraint_method: 'gimme' or 'imat'.
        acquisition_method: 'ei' or 'bald'.
        fasta_path: FASTA with candidate enzyme sequences (for ESM-2 encoding).
        embeddings_path: Pre-computed embeddings .npy (skip encoding if provided).
        ensemble_dir: Trained ensemble directory.
        top_k: Number of top candidates to report.
        biomass_fraction: Minimum biomass constraint.
        output_dir: Workflow output directory.
        dry_run: Validate inputs and print plan without executing.
        device: Compute device.

    Returns:
        Workflow result dict with all stage outputs.
    """
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_id = f"{species}_{timestamp.replace(':', '-').replace('+', '_')}"
    out_dir = output_dir or (RUNS_DIR / run_id)

    workflow_result: dict[str, Any] = {
        "workflow": "cross_species_metabolic_prediction",
        "version": "1.0.0",
        "run_id": run_id,
        "timestamp": timestamp,
        "species": species,
        "target_metabolite": target_metabolite,
        "condition": condition,
        "constraint_method": constraint_method,
        "acquisition_method": acquisition_method,
        "dry_run": dry_run,
        "stages": {},
    }

    # --- Stage 0: Validate inputs ---
    print(f"[Stage 0] Validating inputs for species='{species}'...")
    from species_profile import SpeciesProfileError, load_species_profile, list_species

    available = list_species()
    if species not in available:
        raise WorkflowError(f"Unknown species '{species}'. Available: {available}")

    profile = load_species_profile(species)
    workflow_result["species_profile"] = {
        "organism": profile["organism_name"],
        "taxonomy_id": profile["taxonomy_id"],
        "gem_format": profile["gem"]["format"],
        "biomass_reaction": profile["biomass_reaction"],
    }

    if dry_run:
        print("  [DRY RUN] Input validation passed. Stages that would execute:")
        stages = ["load_gem", "fba_feasibility"]
        if fasta_path:
            stages.append("esm2_encode")
        if embeddings_path or fasta_path:
            stages.append("multitask_predict")
        if expression_path:
            stages.append("omics_constrain")
        if ensemble_dir:
            stages.append("acquisition")
        stages.append("report")
        for i, s in enumerate(stages, 1):
            print(f"    {i}. {s}")
        workflow_result["stages"]["plan"] = stages
        return workflow_result

    # --- Stage 1: Load GEM ---
    print(f"\n[Stage 1] Loading GEM for {species}...")
    from load_gem_multispecies import GEMLoadError, load_gem, inject_demand_reaction, fba_with_biomass_floor

    try:
        model, profile = load_gem(species)
    except (GEMLoadError, SpeciesProfileError) as exc:
        raise WorkflowError(f"GEM loading failed: {exc}") from exc

    gem_stats = profile["_gem_stats"]
    workflow_result["stages"]["load_gem"] = gem_stats
    print(f"  {gem_stats['n_reactions']} reactions, FBA={gem_stats['fba_objective_value']:.6f}")

    # --- Stage 2: FBA feasibility ---
    if target_metabolite:
        print(f"\n[Stage 2] FBA feasibility for {target_metabolite}...")
        try:
            dm_id = inject_demand_reaction(model, target_metabolite)
            fba_result = fba_with_biomass_floor(model, dm_id, biomass_fraction)
            workflow_result["stages"]["fba_feasibility"] = fba_result
            print(f"  Max demand flux: {fba_result['max_demand_flux']} (status={fba_result['status']})")
        except GEMLoadError as exc:
            workflow_result["stages"]["fba_feasibility"] = {"error": str(exc)}
            print(f"  WARNING: {exc}")
    else:
        print("\n[Stage 2] Skipped (no target metabolite specified).")

    # --- Stage 3: ESM-2 encoding ---
    import numpy as np

    embeddings = None
    if embeddings_path and embeddings_path.exists():
        print(f"\n[Stage 3] Loading pre-computed embeddings from {embeddings_path}...")
        embeddings = np.load(embeddings_path)
        workflow_result["stages"]["esm2_encode"] = {
            "source": "precomputed",
            "shape": list(embeddings.shape),
        }
        print(f"  Loaded: {embeddings.shape}")
    elif fasta_path and fasta_path.exists():
        print(f"\n[Stage 3] Encoding sequences from {fasta_path}...")
        from esm2_encode import ESM2EncoderError, encode_fasta
        try:
            embeddings, index = encode_fasta(fasta_path, device=device)
            workflow_result["stages"]["esm2_encode"] = {
                "source": "computed",
                "n_sequences": len(index),
                "shape": list(embeddings.shape),
            }
        except ESM2EncoderError as exc:
            workflow_result["stages"]["esm2_encode"] = {"error": str(exc)}
            print(f"  WARNING: ESM-2 encoding failed: {exc}")
    else:
        print("\n[Stage 3] Skipped (no FASTA or embeddings provided).")

    # --- Stage 4: Multi-task prediction ---
    if embeddings is not None:
        print(f"\n[Stage 4] Running multi-task prediction...")
        from multitask_model import MultiTaskModelError, predict
        try:
            preds = predict(embeddings, device=device)
            workflow_result["stages"]["multitask_predict"] = {
                "n_candidates": int(embeddings.shape[0]),
                "fba_prob_range": [round(float(preds["fba_prob"].min()), 4), round(float(preds["fba_prob"].max()), 4)],
                "kcat_pred_range": [round(float(preds["kcat_pred"].min()), 4), round(float(preds["kcat_pred"].max()), 4)],
            }
            print(f"  Predicted {embeddings.shape[0]} candidates.")
        except MultiTaskModelError as exc:
            workflow_result["stages"]["multitask_predict"] = {"error": str(exc)}
            print(f"  WARNING: {exc}")
    else:
        print("\n[Stage 4] Skipped (no embeddings available).")

    # --- Stage 5: Omics constraints ---
    if expression_path and expression_path.exists():
        print(f"\n[Stage 5] Applying {constraint_method} constraints...")
        from omics_constrain import OmicsConstraintError, condition_specific_fba, load_expression_matrix
        try:
            gene_ids, conditions, expr_matrix = load_expression_matrix(expression_path)
            # Filter to specific condition if requested
            if condition and condition in conditions:
                cond_idx = conditions.index(condition)
                conditions = [condition]
                expr_matrix = expr_matrix[:, cond_idx:cond_idx + 1]

            results = condition_specific_fba(
                model=model,
                expression_matrix=expr_matrix,
                gene_ids=gene_ids,
                conditions=conditions,
                method=constraint_method,
                demand_metabolite=target_metabolite,
                biomass_fraction=biomass_fraction,
            )
            workflow_result["stages"]["omics_constrain"] = {
                "method": constraint_method,
                "n_conditions": len(conditions),
                "results": results,
            }
        except OmicsConstraintError as exc:
            workflow_result["stages"]["omics_constrain"] = {"error": str(exc)}
            print(f"  WARNING: {exc}")
    else:
        print("\n[Stage 5] Skipped (no expression data).")

    # --- Stage 6: Active learning acquisition ---
    if embeddings is not None and ensemble_dir and Path(ensemble_dir).exists():
        print(f"\n[Stage 6] Running acquisition ({acquisition_method})...")
        from acquisition import AcquisitionError, run_acquisition_round
        try:
            acq_result = run_acquisition_round(
                embeddings=embeddings,
                ensemble_dir=Path(ensemble_dir),
                method=acquisition_method,
                top_k=top_k,
                output_dir=out_dir / "acquisition",
                device=device,
            )
            workflow_result["stages"]["acquisition"] = {
                "method": acquisition_method,
                "top_k": top_k,
                "candidates": acq_result["candidates"],
                "summary": acq_result["summary_stats"],
            }
        except (AcquisitionError, Exception) as exc:
            workflow_result["stages"]["acquisition"] = {"error": str(exc)}
            print(f"  WARNING: {exc}")
    else:
        print("\n[Stage 6] Skipped (no ensemble or embeddings).")

    # --- Stage 7: Save results ---
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "workflow_result.json"
    result_path.write_text(json.dumps(workflow_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n[Done] Results: {result_path}")

    return workflow_result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-species metabolic prediction workflow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python cross_species_workflow.py --species yeast --target s_1234 --dry-run\n"
            "  python cross_species_workflow.py --species ecoli --embeddings emb.npy --acquisition ei\n"
            "  python cross_species_workflow.py --species yeast --expression expr.csv --method gimme\n"
        ),
    )
    parser.add_argument("--species", type=str, required=True,
                        help="Species ID (yeast, ecoli, cglutamicum).")
    parser.add_argument("--target", type=str, default=None,
                        help="Target metabolite ID for demand analysis.")
    parser.add_argument("--condition", type=str, default=None,
                        help="Specific condition name from expression matrix.")
    parser.add_argument("--expression", type=Path, default=None,
                        help="Expression matrix CSV for omics constraints.")
    parser.add_argument("--method", type=str, default="gimme",
                        choices=["gimme", "imat"],
                        help="Omics constraint method.")
    parser.add_argument("--acquisition", type=str, default="ei",
                        choices=["ei", "bald"],
                        help="Acquisition function for candidate ranking.")
    parser.add_argument("--fasta", type=Path, default=None,
                        help="FASTA file for ESM-2 encoding.")
    parser.add_argument("--embeddings", type=Path, default=None,
                        help="Pre-computed embeddings .npy.")
    parser.add_argument("--ensemble-dir", type=Path, default=None,
                        help="Trained ensemble directory.")
    parser.add_argument("--top-k", type=int, default=20,
                        help="Number of top candidates to select.")
    parser.add_argument("--biomass-fraction", type=float, default=0.10,
                        help="Minimum biomass fraction constraint.")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory for workflow results.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate inputs and print execution plan.")
    parser.add_argument("--device", type=str, default=None,
                        choices=["cpu", "cuda"],
                        help="Compute device.")
    args = parser.parse_args()

    t0 = time.perf_counter()
    try:
        result = run_workflow(
            species=args.species,
            target_metabolite=args.target,
            condition=args.condition,
            expression_path=args.expression,
            constraint_method=args.method,
            acquisition_method=args.acquisition,
            fasta_path=args.fasta,
            embeddings_path=args.embeddings,
            ensemble_dir=args.ensemble_dir,
            top_k=args.top_k,
            biomass_fraction=args.biomass_fraction,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            device=args.device,
        )
    except WorkflowError as exc:
        print(f"WORKFLOW ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"UNEXPECTED ERROR: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - t0
    print(f"\nTotal workflow time: {elapsed:.1f}s")

    if args.dry_run:
        return 0

    # Print summary
    stages_completed = [k for k, v in result.get("stages", {}).items() if "error" not in v]
    stages_failed = [k for k, v in result.get("stages", {}).items() if "error" in v]
    print(f"Stages completed: {len(stages_completed)} | Failed: {len(stages_failed)}")
    if stages_failed:
        print(f"  Failed stages: {', '.join(stages_failed)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
