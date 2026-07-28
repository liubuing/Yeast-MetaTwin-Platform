from __future__ import annotations

"""Multi-task enzyme-reaction prediction model.

Joint prediction architecture with shared ESM-2 encoder and three heads:
  - Head 1: EC number hierarchical classification
  - Head 2: kcat regression (log10 scale)
  - Head 3: FBA feasibility binary classification

Training uses uncertainty weighting to auto-balance task losses.
Supports multi-species data (EC/kcat heads use all species, FBA head per-species).
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
TRAINING_DIR = ROOT / "05_training"


class MultiTaskModelError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_training_labels(
    labels_dir: Path | None = None,
) -> dict[str, np.ndarray]:
    """Load pre-computed training labels for all three tasks.

    Expected files in labels_dir:
      - ec_labels.csv: columns [seq_id, ec_number, ec_class1, ec_class2, ec_class3, ec_class4]
      - kcat_labels.csv: columns [seq_id, substrate_id, log10_kcat, species]
      - fba_labels.csv: columns [seq_id, reaction_id, feasible, species]

    Returns:
        Dict with keys 'ec', 'kcat', 'fba', each containing structured arrays.
    """
    base = labels_dir or TRAINING_DIR
    result: dict[str, Any] = {}

    # EC labels
    ec_path = base / "ec_labels.csv"
    if ec_path.exists():
        rows = _read_csv(ec_path)
        result["ec"] = rows
    else:
        result["ec"] = []

    # kcat labels
    kcat_path = base / "kcat_labels.csv"
    if kcat_path.exists():
        rows = _read_csv(kcat_path)
        result["kcat"] = rows
    else:
        result["kcat"] = []

    # FBA labels
    fba_path = base / "fba_labels.csv"
    if fba_path.exists():
        rows = _read_csv(fba_path)
        result["fba"] = rows
    else:
        result["fba"] = []

    return result


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Model architecture (PyTorch)
# ---------------------------------------------------------------------------

def build_multitask_model(
    embed_dim: int = 1280,
    ec_classes: int = 400,
    hidden_dim: int = 512,
    dropout: float = 0.3,
    n_frozen_layers: int = 30,
):
    """Construct the multi-task model with shared encoder + 3 heads.

    Architecture:
        Shared: ESM-2 embedding (frozen) -> Projection MLP (1280 -> hidden_dim)
        Head 1 (EC): hidden_dim -> 256 -> ec_classes (hierarchical softmax approximated)
        Head 2 (kcat): hidden_dim -> 256 -> 1 (MSE on log10 kcat)
        Head 3 (FBA): hidden_dim -> 256 -> 1 (BCE feasibility)

    Returns:
        PyTorch nn.Module (MultiTaskPredictor).
    """
    try:
        import torch
        import torch.nn as nn
    except ImportError as exc:
        raise MultiTaskModelError(f"PyTorch required: {exc}") from exc

    class MultiTaskPredictor(nn.Module):
        def __init__(self):
            super().__init__()
            # Shared projection
            self.shared = nn.Sequential(
                nn.Linear(embed_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.GELU(),
                nn.Dropout(dropout),
            )

            # Head 1: EC classification
            self.ec_head = nn.Sequential(
                nn.Linear(hidden_dim, 256),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(256, ec_classes),
            )

            # Head 2: kcat regression
            self.kcat_head = nn.Sequential(
                nn.Linear(hidden_dim, 256),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(256, 1),
            )

            # Head 3: FBA feasibility
            self.fba_head = nn.Sequential(
                nn.Linear(hidden_dim, 256),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(256, 1),
            )

            # Learnable task weights (uncertainty weighting, Kendall et al. 2018)
            self.log_sigma_ec = nn.Parameter(torch.zeros(1))
            self.log_sigma_kcat = nn.Parameter(torch.zeros(1))
            self.log_sigma_fba = nn.Parameter(torch.zeros(1))

        def forward(self, x: "torch.Tensor") -> dict[str, "torch.Tensor"]:
            shared_repr = self.shared(x)
            return {
                "ec_logits": self.ec_head(shared_repr),
                "kcat_pred": self.kcat_head(shared_repr).squeeze(-1),
                "fba_logits": self.fba_head(shared_repr).squeeze(-1),
            }

        def compute_loss(
            self,
            outputs: dict[str, "torch.Tensor"],
            targets: dict[str, "torch.Tensor"],
            masks: dict[str, "torch.Tensor"],
        ) -> "torch.Tensor":
            """Compute uncertainty-weighted multi-task loss.

            Args:
                outputs: Model forward outputs.
                targets: Dict with 'ec' (long), 'kcat' (float), 'fba' (float).
                masks: Boolean masks indicating which samples have labels per task.
            """
            import torch.nn.functional as F

            loss = torch.tensor(0.0, device=next(self.parameters()).device)

            # EC loss (cross-entropy)
            if masks["ec"].any():
                ec_loss = F.cross_entropy(
                    outputs["ec_logits"][masks["ec"]],
                    targets["ec"][masks["ec"]],
                )
                precision_ec = torch.exp(-self.log_sigma_ec)
                loss = loss + precision_ec * ec_loss + self.log_sigma_ec

            # kcat loss (MSE on log10 scale)
            if masks["kcat"].any():
                kcat_loss = F.mse_loss(
                    outputs["kcat_pred"][masks["kcat"]],
                    targets["kcat"][masks["kcat"]],
                )
                precision_kcat = torch.exp(-self.log_sigma_kcat)
                loss = loss + precision_kcat * kcat_loss + self.log_sigma_kcat

            # FBA loss (binary cross-entropy)
            if masks["fba"].any():
                fba_loss = F.binary_cross_entropy_with_logits(
                    outputs["fba_logits"][masks["fba"]],
                    targets["fba"][masks["fba"]],
                )
                precision_fba = torch.exp(-self.log_sigma_fba)
                loss = loss + precision_fba * fba_loss + self.log_sigma_fba

            return loss

    return MultiTaskPredictor()


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train_multitask(
    embeddings: np.ndarray,
    labels: dict[str, list[dict[str, str]]],
    seq_id_to_idx: dict[str, int],
    ec_vocabulary: list[str],
    output_path: Path | None = None,
    device: str | None = None,
    epochs: int = 100,
    lr: float = 1e-3,
    batch_size: int = 64,
    val_fraction: float = 0.15,
    seed: int = 42,
) -> dict[str, Any]:
    """Train the multi-task model on pre-computed ESM-2 embeddings.

    Args:
        embeddings: [N, 1280] numpy array of ESM-2 embeddings.
        labels: Dict from load_training_labels().
        seq_id_to_idx: Mapping from sequence ID to embedding row index.
        ec_vocabulary: Sorted list of unique EC numbers (defines class indices).
        output_path: Where to save trained model state_dict.
        device: 'cpu' or 'cuda'.
        epochs: Training epochs.
        lr: Learning rate.
        batch_size: Mini-batch size.
        val_fraction: Fraction of data for validation.
        seed: Random seed.

    Returns:
        Training history dict with per-epoch losses and final metrics.
    """
    try:
        import torch
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        raise MultiTaskModelError(f"PyTorch required: {exc}") from exc

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    torch.manual_seed(seed)
    np.random.seed(seed)

    n_samples = embeddings.shape[0]
    ec_to_idx = {ec: i for i, ec in enumerate(ec_vocabulary)}

    # Build target tensors
    ec_targets = torch.full((n_samples,), -1, dtype=torch.long)
    kcat_targets = torch.full((n_samples,), 0.0, dtype=torch.float32)
    fba_targets = torch.full((n_samples,), 0.0, dtype=torch.float32)

    ec_mask = torch.zeros(n_samples, dtype=torch.bool)
    kcat_mask = torch.zeros(n_samples, dtype=torch.bool)
    fba_mask = torch.zeros(n_samples, dtype=torch.bool)

    # Fill EC labels
    for row in labels.get("ec", []):
        sid = row.get("seq_id", "")
        ec = row.get("ec_number", "")
        if sid in seq_id_to_idx and ec in ec_to_idx:
            idx = seq_id_to_idx[sid]
            ec_targets[idx] = ec_to_idx[ec]
            ec_mask[idx] = True

    # Fill kcat labels
    for row in labels.get("kcat", []):
        sid = row.get("seq_id", "")
        kcat_val = row.get("log10_kcat", "")
        if sid in seq_id_to_idx and kcat_val:
            idx = seq_id_to_idx[sid]
            kcat_targets[idx] = float(kcat_val)
            kcat_mask[idx] = True

    # Fill FBA labels
    for row in labels.get("fba", []):
        sid = row.get("seq_id", "")
        feasible = row.get("feasible", "0")
        if sid in seq_id_to_idx:
            idx = seq_id_to_idx[sid]
            fba_targets[idx] = float(feasible)
            fba_mask[idx] = True

    # Train/val split (deterministic)
    indices = np.arange(n_samples)
    rng = np.random.default_rng(seed)
    rng.shuffle(indices)
    n_val = int(n_samples * val_fraction)
    val_idx = indices[:n_val]
    train_idx = indices[n_val:]

    # Convert to tensors
    X = torch.from_numpy(embeddings).float()

    # Build model
    model = build_multitask_model(ec_classes=len(ec_vocabulary))
    model = model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    history: list[dict[str, float]] = []
    best_val_loss = float("inf")
    best_state = None

    print(f"Training multi-task model on {device}")
    print(f"  Samples: {n_samples} (train={len(train_idx)}, val={n_val})")
    print(f"  EC labels: {ec_mask.sum().item()}, kcat: {kcat_mask.sum().item()}, FBA: {fba_mask.sum().item()}")
    print(f"  EC classes: {len(ec_vocabulary)}")

    t0 = time.perf_counter()
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        n_batches = 0

        # Mini-batch training
        perm = torch.from_numpy(rng.permutation(train_idx)).long()
        for start in range(0, len(perm), batch_size):
            batch_idx = perm[start:start + batch_size].to(device)
            x_batch = X[batch_idx].to(device)

            targets = {
                "ec": ec_targets[batch_idx].to(device),
                "kcat": kcat_targets[batch_idx].to(device),
                "fba": fba_targets[batch_idx].to(device),
            }
            masks = {
                "ec": ec_mask[batch_idx].to(device),
                "kcat": kcat_mask[batch_idx].to(device),
                "fba": fba_mask[batch_idx].to(device),
            }

            optimizer.zero_grad()
            outputs = model(x_batch)
            loss = model.compute_loss(outputs, targets, masks)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        scheduler.step()
        avg_train_loss = epoch_loss / max(n_batches, 1)

        # Validation
        model.eval()
        with torch.no_grad():
            val_batch = torch.from_numpy(val_idx).long().to(device)
            x_val = X[val_batch].to(device)
            val_outputs = model(x_val)
            val_targets = {
                "ec": ec_targets[val_batch].to(device),
                "kcat": kcat_targets[val_batch].to(device),
                "fba": fba_targets[val_batch].to(device),
            }
            val_masks = {
                "ec": ec_mask[val_batch].to(device),
                "kcat": kcat_mask[val_batch].to(device),
                "fba": fba_mask[val_batch].to(device),
            }
            val_loss = model.compute_loss(val_outputs, val_targets, val_masks).item()

        history.append({"epoch": epoch + 1, "train_loss": avg_train_loss, "val_loss": val_loss})

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        if (epoch + 1) % 10 == 0 or epoch == 0:
            print(f"  Epoch {epoch + 1:3d}/{epochs}: train={avg_train_loss:.4f} val={val_loss:.4f}")

    elapsed = time.perf_counter() - t0
    print(f"Training complete in {elapsed:.1f}s. Best val loss: {best_val_loss:.4f}")

    # Save best model
    save_path = output_path or (MODELS_DIR / "multitask_v1.pt")
    save_path.parent.mkdir(parents=True, exist_ok=True)
    if best_state:
        torch.save(best_state, save_path)
        print(f"Model saved: {save_path}")

    # Save training config and history
    config = {
        "architecture": "multitask_esm2_shared_encoder",
        "embed_dim": 1280,
        "hidden_dim": 512,
        "ec_classes": len(ec_vocabulary),
        "epochs": epochs,
        "lr": lr,
        "batch_size": batch_size,
        "seed": seed,
        "n_samples": n_samples,
        "n_ec_labels": int(ec_mask.sum().item()),
        "n_kcat_labels": int(kcat_mask.sum().item()),
        "n_fba_labels": int(fba_mask.sum().item()),
        "best_val_loss": best_val_loss,
        "training_time_seconds": round(elapsed, 1),
        "device": device,
    }
    config_path = save_path.with_suffix(".config.json")
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    history_path = save_path.with_suffix(".history.json")
    history_path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")

    return {"config": config, "history": history, "model_path": str(save_path)}


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def predict(
    embeddings: np.ndarray,
    model_path: Path | None = None,
    ec_vocabulary: list[str] | None = None,
    device: str | None = None,
) -> dict[str, np.ndarray]:
    """Run inference on pre-computed embeddings.

    Returns:
        Dict with 'ec_probs' [N, C], 'kcat_pred' [N], 'fba_prob' [N].
    """
    try:
        import torch
        import torch.nn.functional as F
    except ImportError as exc:
        raise MultiTaskModelError(f"PyTorch required: {exc}") from exc

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    path = model_path or (MODELS_DIR / "multitask_v1.pt")
    if not path.exists():
        raise MultiTaskModelError(f"Model not found: {path}")

    # Load config to reconstruct architecture
    config_path = path.with_suffix(".config.json")
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        ec_classes = config["ec_classes"]
    else:
        ec_classes = len(ec_vocabulary) if ec_vocabulary else 400

    model = build_multitask_model(ec_classes=ec_classes)
    state = torch.load(path, map_location=device, weights_only=True)
    model.load_state_dict(state)
    model = model.to(device)
    model.eval()

    X = torch.from_numpy(embeddings).float().to(device)
    with torch.no_grad():
        outputs = model(X)

    return {
        "ec_probs": F.softmax(outputs["ec_logits"], dim=-1).cpu().numpy(),
        "kcat_pred": outputs["kcat_pred"].cpu().numpy(),
        "fba_prob": torch.sigmoid(outputs["fba_logits"]).cpu().numpy(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Multi-task enzyme-reaction prediction model.",
    )
    sub = parser.add_subparsers(dest="command")

    # train
    train_p = sub.add_parser("train", help="Train the multi-task model.")
    train_p.add_argument("--embeddings", type=Path, required=True,
                         help="Path to embeddings_matrix.npy")
    train_p.add_argument("--index", type=Path, required=True,
                         help="Path to embeddings_index.csv")
    train_p.add_argument("--labels-dir", type=Path, default=None,
                         help="Directory with ec_labels.csv, kcat_labels.csv, fba_labels.csv")
    train_p.add_argument("--output", type=Path, default=None,
                         help="Output model path (default: 03_models/multitask_v1.pt)")
    train_p.add_argument("--epochs", type=int, default=100)
    train_p.add_argument("--lr", type=float, default=1e-3)
    train_p.add_argument("--batch-size", type=int, default=64)
    train_p.add_argument("--device", type=str, default=None)
    train_p.add_argument("--seed", type=int, default=42)

    # predict
    pred_p = sub.add_parser("predict", help="Run inference.")
    pred_p.add_argument("--embeddings", type=Path, required=True)
    pred_p.add_argument("--model", type=Path, default=None)
    pred_p.add_argument("--output", type=Path, required=True,
                        help="Output predictions as .npz")
    pred_p.add_argument("--device", type=str, default=None)

    args = parser.parse_args()

    if args.command == "train":
        # Load embeddings
        embeddings = np.load(args.embeddings)
        index = _read_csv(args.index)
        seq_id_to_idx = {row["seq_id"]: i for i, row in enumerate(index)}

        # Load labels
        labels = load_training_labels(args.labels_dir)

        # Build EC vocabulary from labels
        ec_set = set()
        for row in labels.get("ec", []):
            ec = row.get("ec_number", "")
            if ec:
                ec_set.add(ec)
        ec_vocabulary = sorted(ec_set)

        if not ec_vocabulary:
            print("WARNING: No EC labels found. EC head will have 0 classes.", file=sys.stderr)
            ec_vocabulary = ["0.0.0.0"]  # Placeholder

        try:
            result = train_multitask(
                embeddings=embeddings,
                labels=labels,
                seq_id_to_idx=seq_id_to_idx,
                ec_vocabulary=ec_vocabulary,
                output_path=args.output,
                device=args.device,
                epochs=args.epochs,
                lr=args.lr,
                batch_size=args.batch_size,
                seed=args.seed,
            )
        except MultiTaskModelError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        print(json.dumps(result["config"], indent=2, ensure_ascii=False))
        return 0

    elif args.command == "predict":
        embeddings = np.load(args.embeddings)
        try:
            preds = predict(embeddings, model_path=args.model, device=args.device)
        except MultiTaskModelError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        np.savez_compressed(
            args.output,
            ec_probs=preds["ec_probs"],
            kcat_pred=preds["kcat_pred"],
            fba_prob=preds["fba_prob"],
        )
        print(f"Predictions saved: {args.output}")
        print(f"  EC probs: {preds['ec_probs'].shape}")
        print(f"  kcat pred: {preds['kcat_pred'].shape}")
        print(f"  FBA prob: {preds['fba_prob'].shape}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
