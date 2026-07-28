from __future__ import annotations

"""Active learning acquisition module for enzyme-reaction prioritization.

Implements uncertainty-aware candidate selection using Deep Ensembles,
with Expected Improvement (EI) and BALD acquisition functions.
Provides a closed-loop protocol for iterative experimental validation.
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
MODELS_DIR = ROOT / "03_models"
RUNS_DIR = ROOT / "runs"


class AcquisitionError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Deep Ensemble uncertainty estimation
# ---------------------------------------------------------------------------

def train_ensemble(
    embeddings: np.ndarray,
    labels: dict[str, list[dict[str, str]]],
    seq_id_to_idx: dict[str, int],
    ec_vocabulary: list[str],
    n_members: int = 5,
    epochs: int = 80,
    lr: float = 1e-3,
    batch_size: int = 64,
    output_dir: Path | None = None,
    device: str | None = None,
) -> list[Path]:
    """Train a Deep Ensemble of multi-task models with different seeds.

    Each member is trained with a different random seed, producing
    diverse predictions whose disagreement estimates epistemic uncertainty.

    Args:
        embeddings: [N, 1280] ESM-2 embeddings.
        labels: Training labels dict.
        seq_id_to_idx: Sequence ID to embedding index mapping.
        ec_vocabulary: EC class vocabulary.
        n_members: Number of ensemble members (default: 5).
        epochs: Training epochs per member.
        lr: Learning rate.
        batch_size: Batch size.
        output_dir: Directory for ensemble model files.
        device: Compute device.

    Returns:
        List of paths to saved ensemble member state_dicts.
    """
    from multitask_model import MultiTaskModelError, train_multitask

    out_dir = output_dir or (MODELS_DIR / "ensemble")
    out_dir.mkdir(parents=True, exist_ok=True)

    member_paths: list[Path] = []
    seeds = [42, 123, 456, 789, 1024][:n_members]

    print(f"Training Deep Ensemble ({n_members} members)...")
    for i, seed in enumerate(seeds):
        print(f"\n--- Member {i + 1}/{n_members} (seed={seed}) ---")
        member_path = out_dir / f"ensemble_member_{i}.pt"

        try:
            train_multitask(
                embeddings=embeddings,
                labels=labels,
                seq_id_to_idx=seq_id_to_idx,
                ec_vocabulary=ec_vocabulary,
                output_path=member_path,
                device=device,
                epochs=epochs,
                lr=lr,
                batch_size=batch_size,
                seed=seed,
            )
            member_paths.append(member_path)
        except MultiTaskModelError as exc:
            print(f"WARNING: Member {i} failed: {exc}", file=sys.stderr)

    # Save ensemble manifest
    manifest = {
        "n_members": len(member_paths),
        "seeds": seeds[:len(member_paths)],
        "member_paths": [str(p) for p in member_paths],
        "architecture": "multitask_esm2_shared_encoder",
    }
    manifest_path = out_dir / "ensemble_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nEnsemble complete: {len(member_paths)} members saved to {out_dir}")

    return member_paths


def ensemble_predict(
    embeddings: np.ndarray,
    ensemble_dir: Path | None = None,
    ec_vocabulary: list[str] | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    """Run inference with all ensemble members and compute uncertainty.

    Returns:
        Dict with:
          - 'fba_prob_mean': [N] mean feasibility probability
          - 'fba_prob_std': [N] std deviation (epistemic uncertainty)
          - 'kcat_pred_mean': [N] mean kcat prediction
          - 'kcat_pred_std': [N] std deviation
          - 'ec_probs_mean': [N, C] mean EC class probabilities
          - 'ec_entropy': [N] predictive entropy over EC classes
    """
    from multitask_model import MultiTaskModelError, predict

    ens_dir = ensemble_dir or (MODELS_DIR / "ensemble")
    manifest_path = ens_dir / "ensemble_manifest.json"
    if not manifest_path.exists():
        raise AcquisitionError(f"Ensemble manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    member_paths = [Path(p) for p in manifest["member_paths"]]

    if not member_paths:
        raise AcquisitionError("No ensemble members found.")

    # Collect predictions from all members
    all_fba_probs: list[np.ndarray] = []
    all_kcat_preds: list[np.ndarray] = []
    all_ec_probs: list[np.ndarray] = []

    for path in member_paths:
        if not path.exists():
            continue
        preds = predict(embeddings, model_path=path, ec_vocabulary=ec_vocabulary, device=device)
        all_fba_probs.append(preds["fba_prob"])
        all_kcat_preds.append(preds["kcat_pred"])
        all_ec_probs.append(preds["ec_probs"])

    if not all_fba_probs:
        raise AcquisitionError("No valid ensemble members could be loaded.")

    fba_stack = np.stack(all_fba_probs)  # [M, N]
    kcat_stack = np.stack(all_kcat_preds)  # [M, N]
    ec_stack = np.stack(all_ec_probs)  # [M, N, C]

    # Compute statistics
    fba_mean = fba_stack.mean(axis=0)
    fba_std = fba_stack.std(axis=0)
    kcat_mean = kcat_stack.mean(axis=0)
    kcat_std = kcat_stack.std(axis=0)
    ec_mean = ec_stack.mean(axis=0)

    # Predictive entropy for EC (total uncertainty)
    ec_entropy = -np.sum(ec_mean * np.log(ec_mean + 1e-10), axis=-1)

    # BALD: mutual information = total entropy - expected entropy
    member_entropies = -np.sum(ec_stack * np.log(ec_stack + 1e-10), axis=-1)  # [M, N]
    expected_entropy = member_entropies.mean(axis=0)
    bald_scores = ec_entropy - expected_entropy

    return {
        "fba_prob_mean": fba_mean,
        "fba_prob_std": fba_std,
        "kcat_pred_mean": kcat_mean,
        "kcat_pred_std": kcat_std,
        "ec_probs_mean": ec_mean,
        "ec_entropy": ec_entropy,
        "bald_scores": bald_scores,
        "n_members": len(all_fba_probs),
    }


# ---------------------------------------------------------------------------
# Acquisition functions
# ---------------------------------------------------------------------------

def acquisition_expected_improvement(
    mean_scores: np.ndarray,
    std_scores: np.ndarray,
    best_so_far: float,
    xi: float = 0.01,
) -> np.ndarray:
    """Expected Improvement acquisition function.

    Prioritizes candidates that are predicted to be good AND uncertain.
    EI(x) = (mu(x) - f_best - xi) * Phi(Z) + sigma(x) * phi(Z)

    Args:
        mean_scores: [N] predicted mean scores (higher = better).
        std_scores: [N] prediction uncertainty (std).
        best_so_far: Best observed score so far.
        xi: Exploration-exploitation trade-off parameter.

    Returns:
        [N] EI scores.
    """
    from scipy.stats import norm

    # Avoid division by zero
    safe_std = np.maximum(std_scores, 1e-10)
    z = (mean_scores - best_so_far - xi) / safe_std
    ei = (mean_scores - best_so_far - xi) * norm.cdf(z) + safe_std * norm.pdf(z)
    ei[std_scores < 1e-10] = 0.0  # No uncertainty = no improvement expected
    return ei


def acquisition_bald(
    bald_scores: np.ndarray,
) -> np.ndarray:
    """BALD (Bayesian Active Learning by Disagreement).

    Prioritizes candidates where ensemble members disagree most.
    Simply returns the pre-computed BALD scores (mutual information).

    Args:
        bald_scores: [N] mutual information from ensemble_predict().

    Returns:
        [N] BALD scores (same as input, for API consistency).
    """
    return bald_scores


def select_candidates(
    ensemble_results: dict[str, Any],
    method: str = "ei",
    top_k: int = 20,
    exclude_indices: set[int] | None = None,
    best_fba_so_far: float = 0.0,
) -> list[dict[str, Any]]:
    """Select top-k candidates for experimental validation.

    Args:
        ensemble_results: Output from ensemble_predict().
        method: 'ei' (Expected Improvement) or 'bald' (maximum disagreement).
        top_k: Number of candidates to select.
        exclude_indices: Indices already validated (to exclude).
        best_fba_so_far: Best FBA probability observed so far (for EI).

    Returns:
        List of dicts with 'index', 'score', 'fba_prob', 'fba_std', 'kcat_pred'.
    """
    n = len(ensemble_results["fba_prob_mean"])
    exclude = exclude_indices or set()

    if method == "ei":
        scores = acquisition_expected_improvement(
            ensemble_results["fba_prob_mean"],
            ensemble_results["fba_prob_std"],
            best_so_far=best_fba_so_far,
        )
    elif method == "bald":
        scores = acquisition_bald(ensemble_results["bald_scores"])
    else:
        raise AcquisitionError(f"Unknown acquisition method: {method}. Use 'ei' or 'bald'.")

    # Mask excluded indices
    scores_masked = scores.copy()
    for idx in exclude:
        if 0 <= idx < n:
            scores_masked[idx] = -np.inf

    # Select top-k
    top_indices = np.argsort(scores_masked)[::-1][:top_k]

    candidates: list[dict[str, Any]] = []
    for rank, idx in enumerate(top_indices):
        if scores_masked[idx] == -np.inf:
            break
        candidates.append({
            "rank": rank + 1,
            "index": int(idx),
            "acquisition_score": round(float(scores[idx]), 6),
            "fba_prob_mean": round(float(ensemble_results["fba_prob_mean"][idx]), 4),
            "fba_prob_std": round(float(ensemble_results["fba_prob_std"][idx]), 4),
            "kcat_pred_mean": round(float(ensemble_results["kcat_pred_mean"][idx]), 4),
            "kcat_pred_std": round(float(ensemble_results["kcat_pred_std"][idx]), 4),
            "ec_entropy": round(float(ensemble_results["ec_entropy"][idx]), 4),
        })

    return candidates


# ---------------------------------------------------------------------------
# Active learning loop protocol
# ---------------------------------------------------------------------------

def run_acquisition_round(
    embeddings: np.ndarray,
    ensemble_dir: Path | None = None,
    method: str = "ei",
    top_k: int = 20,
    round_number: int = 1,
    previous_selections: list[int] | None = None,
    output_dir: Path | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    """Execute one round of active learning candidate selection.

    Args:
        embeddings: [N, 1280] ESM-2 embeddings for all candidates.
        ensemble_dir: Directory with trained ensemble.
        method: Acquisition function ('ei' or 'bald').
        top_k: Candidates to select.
        round_number: Current round (for logging).
        previous_selections: Indices selected in prior rounds.
        output_dir: Where to save round results.
        device: Compute device.

    Returns:
        Round result dict with candidates and metadata.
    """
    out_dir = output_dir or (RUNS_DIR / "active_learning")
    out_dir.mkdir(parents=True, exist_ok=True)

    exclude = set(previous_selections or [])

    print(f"Active Learning Round {round_number}")
    print(f"  Method: {method} | Top-k: {top_k} | Excluded: {len(exclude)}")

    # Ensemble inference
    t0 = time.perf_counter()
    ensemble_results = ensemble_predict(embeddings, ensemble_dir=ensemble_dir, device=device)
    inference_time = time.perf_counter() - t0
    print(f"  Ensemble inference: {inference_time:.1f}s ({ensemble_results['n_members']} members)")

    # Select candidates
    candidates = select_candidates(
        ensemble_results,
        method=method,
        top_k=top_k,
        exclude_indices=exclude,
    )

    round_result = {
        "round": round_number,
        "method": method,
        "top_k": top_k,
        "n_total_candidates": len(embeddings),
        "n_excluded": len(exclude),
        "n_members": ensemble_results["n_members"],
        "inference_time_seconds": round(inference_time, 2),
        "candidates": candidates,
        "summary_stats": {
            "mean_fba_prob": round(float(np.mean([c["fba_prob_mean"] for c in candidates])), 4),
            "mean_uncertainty": round(float(np.mean([c["fba_prob_std"] for c in candidates])), 4),
            "score_range": [
                round(float(candidates[-1]["acquisition_score"]), 6) if candidates else 0,
                round(float(candidates[0]["acquisition_score"]), 6) if candidates else 0,
            ],
        },
    }

    # Save round result
    round_path = out_dir / f"acquisition_round_{round_number:03d}.json"
    round_path.write_text(json.dumps(round_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  Saved: {round_path}")
    print(f"  Top candidate: idx={candidates[0]['index']}, score={candidates[0]['acquisition_score']:.4f}" if candidates else "  No candidates selected.")

    return round_result


def simulate_active_learning(
    embeddings: np.ndarray,
    true_labels: np.ndarray,
    ensemble_dir: Path | None = None,
    method: str = "ei",
    n_rounds: int = 5,
    candidates_per_round: int = 20,
    output_dir: Path | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    """Simulate active learning loop using held-out ground truth.

    Demonstrates that active selection converges faster than random.

    Args:
        embeddings: [N, 1280] embeddings.
        true_labels: [N] binary ground truth (1 = truly feasible).
        ensemble_dir: Trained ensemble directory.
        method: Acquisition function.
        n_rounds: Number of simulated rounds.
        candidates_per_round: Candidates selected per round.
        output_dir: Output directory.
        device: Compute device.

    Returns:
        Simulation results with per-round precision curves.
    """
    out_dir = output_dir or (RUNS_DIR / "active_learning_simulation")
    out_dir.mkdir(parents=True, exist_ok=True)

    n_total = len(true_labels)
    selected: list[int] = []
    round_results: list[dict[str, Any]] = []

    # Also track random baseline
    rng = np.random.default_rng(0)
    random_order = rng.permutation(n_total).tolist()
    random_precision_curve: list[float] = []

    print(f"Simulating active learning: {n_rounds} rounds x {candidates_per_round} candidates")
    print(f"  Ground truth: {true_labels.sum()}/{n_total} positives")

    for round_num in range(1, n_rounds + 1):
        # Active selection
        round_result = run_acquisition_round(
            embeddings=embeddings,
            ensemble_dir=ensemble_dir,
            method=method,
            top_k=candidates_per_round,
            round_number=round_num,
            previous_selections=selected,
            output_dir=out_dir,
            device=device,
        )

        new_indices = [c["index"] for c in round_result["candidates"]]
        selected.extend(new_indices)

        # Compute precision@k for this round
        round_labels = true_labels[new_indices]
        cumulative_precision = true_labels[selected].sum() / len(selected)
        round_precision = round_labels.sum() / max(len(round_labels), 1)

        round_result["simulation_metrics"] = {
            "round_precision": round(float(round_precision), 4),
            "cumulative_precision": round(float(cumulative_precision), 4),
            "cumulative_recall": round(float(true_labels[selected].sum() / max(true_labels.sum(), 1)), 4),
        }
        round_results.append(round_result)

        # Random baseline precision at same sample size
        random_selected = random_order[:len(selected)]
        random_precision = true_labels[random_selected].sum() / len(random_selected)
        random_precision_curve.append(round(float(random_precision), 4))

        print(f"  Round {round_num}: precision={round_precision:.3f}, "
              f"cumulative={cumulative_precision:.3f}, "
              f"random_baseline={random_precision:.3f}")

    # Final comparison
    active_final_precision = true_labels[selected].sum() / len(selected)
    random_final_precision = random_precision_curve[-1] if random_precision_curve else 0
    improvement = (active_final_precision - random_final_precision) / max(random_final_precision, 1e-10)

    simulation_summary = {
        "method": method,
        "n_rounds": n_rounds,
        "candidates_per_round": candidates_per_round,
        "total_selected": len(selected),
        "active_final_precision": round(float(active_final_precision), 4),
        "random_final_precision": round(float(random_final_precision), 4),
        "relative_improvement": round(float(improvement), 4),
        "random_precision_curve": random_precision_curve,
        "rounds": round_results,
    }

    summary_path = out_dir / "simulation_summary.json"
    summary_path.write_text(json.dumps(simulation_summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nSimulation complete. Active vs Random improvement: {improvement * 100:.1f}%")
    print(f"Summary: {summary_path}")

    return simulation_summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Active learning acquisition for enzyme-reaction prioritization.",
    )
    sub = parser.add_subparsers(dest="command")

    # train-ensemble
    te_p = sub.add_parser("train-ensemble", help="Train Deep Ensemble.")
    te_p.add_argument("--embeddings", type=Path, required=True)
    te_p.add_argument("--index", type=Path, required=True)
    te_p.add_argument("--labels-dir", type=Path, default=None)
    te_p.add_argument("--n-members", type=int, default=5)
    te_p.add_argument("--epochs", type=int, default=80)
    te_p.add_argument("--output-dir", type=Path, default=None)
    te_p.add_argument("--device", type=str, default=None)

    # select
    sel_p = sub.add_parser("select", help="Run one acquisition round.")
    sel_p.add_argument("--embeddings", type=Path, required=True)
    sel_p.add_argument("--ensemble-dir", type=Path, default=None)
    sel_p.add_argument("--method", type=str, default="ei", choices=["ei", "bald"])
    sel_p.add_argument("--top-k", type=int, default=20)
    sel_p.add_argument("--round", type=int, default=1)
    sel_p.add_argument("--output-dir", type=Path, default=None)
    sel_p.add_argument("--device", type=str, default=None)

    # simulate
    sim_p = sub.add_parser("simulate", help="Simulate active learning loop.")
    sim_p.add_argument("--embeddings", type=Path, required=True)
    sim_p.add_argument("--true-labels", type=Path, required=True,
                       help="CSV with 'index' and 'label' columns.")
    sim_p.add_argument("--ensemble-dir", type=Path, default=None)
    sim_p.add_argument("--method", type=str, default="ei", choices=["ei", "bald"])
    sim_p.add_argument("--n-rounds", type=int, default=5)
    sim_p.add_argument("--candidates-per-round", type=int, default=20)
    sim_p.add_argument("--output-dir", type=Path, default=None)
    sim_p.add_argument("--device", type=str, default=None)

    args = parser.parse_args()

    if args.command == "train-ensemble":
        embeddings = np.load(args.embeddings)
        with open(args.index, encoding="utf-8-sig", newline="") as fh:
            index = list(csv.DictReader(fh))
        seq_id_to_idx = {row["seq_id"]: i for i, row in enumerate(index)}

        from multitask_model import load_training_labels
        labels = load_training_labels(args.labels_dir)
        ec_set = set()
        for row in labels.get("ec", []):
            ec = row.get("ec_number", "")
            if ec:
                ec_set.add(ec)
        ec_vocabulary = sorted(ec_set) or ["0.0.0.0"]

        try:
            train_ensemble(
                embeddings=embeddings,
                labels=labels,
                seq_id_to_idx=seq_id_to_idx,
                ec_vocabulary=ec_vocabulary,
                n_members=args.n_members,
                epochs=args.epochs,
                output_dir=args.output_dir,
                device=args.device,
            )
        except (AcquisitionError, Exception) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0

    elif args.command == "select":
        embeddings = np.load(args.embeddings)
        try:
            result = run_acquisition_round(
                embeddings=embeddings,
                ensemble_dir=args.ensemble_dir,
                method=args.method,
                top_k=args.top_k,
                round_number=args.round,
                output_dir=args.output_dir,
                device=args.device,
            )
        except (AcquisitionError, Exception) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result["summary_stats"], indent=2))
        return 0

    elif args.command == "simulate":
        embeddings = np.load(args.embeddings)
        # Load true labels
        true_labels = np.zeros(len(embeddings), dtype=np.float32)
        with open(args.true_labels, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                idx = int(row["index"])
                true_labels[idx] = float(row["label"])

        try:
            simulate_active_learning(
                embeddings=embeddings,
                true_labels=true_labels,
                ensemble_dir=args.ensemble_dir,
                method=args.method,
                n_rounds=args.n_rounds,
                candidates_per_round=args.candidates_per_round,
                output_dir=args.output_dir,
                device=args.device,
            )
        except (AcquisitionError, Exception) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
