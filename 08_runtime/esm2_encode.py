from __future__ import annotations

"""ESM-2 protein sequence encoder for cross-species enzyme representation.

Provides a unified embedding layer that encodes enzyme sequences into
1280-dimensional vectors using ESM-2 (650M parameters). Embeddings are
species-agnostic, enabling transfer across yeast, E. coli, and C. glutamicum.

Supports:
- Single sequence encoding
- Batch encoding from FASTA files
- Cached embedding storage (.npy + index .csv)
- GPU inference with gradient checkpointing for 8GB VRAM
"""

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EMBED_CACHE_DIR = ROOT / "03_models" / "esm2_embeddings"

# ESM-2 model configuration
ESM2_MODEL_NAME = "esm2_t33_650M_UR50D"
EMBED_DIM = 1280
MAX_SEQ_LEN = 1022  # ESM-2 max token length (excluding BOS/EOS)


class ESM2EncoderError(RuntimeError):
    pass


def _get_device() -> str:
    """Determine best available device."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def _load_esm2_model(device: str = "cpu"):
    """Load ESM-2 model and alphabet. Lazy import to avoid hard dependency."""
    try:
        import esm
        import torch
    except ImportError as exc:
        raise ESM2EncoderError(
            "ESM-2 requires 'fair-esm' and 'torch'. Install with:\n"
            "  pip install fair-esm torch\n"
            f"Original error: {exc}"
        ) from exc

    model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
    model = model.to(device)
    model.eval()

    # Enable gradient checkpointing for memory efficiency on 8GB GPUs
    if device == "cuda":
        try:
            model.gradient_checkpointing_enable()
        except AttributeError:
            pass  # Older versions may not support this

    return model, alphabet


def encode_sequence(
    sequence: str,
    model: Any = None,
    alphabet: Any = None,
    device: str = "cpu",
    truncate: bool = True,
) -> np.ndarray:
    """Encode a single protein sequence to a 1280-dim embedding.

    Uses mean pooling over all residue representations (excluding special tokens).

    Args:
        sequence: Amino acid sequence (single-letter codes).
        model: Pre-loaded ESM-2 model (loads if None).
        alphabet: Pre-loaded alphabet (loads if None).
        device: 'cpu' or 'cuda'.
        truncate: Whether to truncate sequences > 1022 residues.

    Returns:
        numpy array of shape (1280,).
    """
    import torch

    if model is None or alphabet is None:
        model, alphabet = _load_esm2_model(device)

    seq = sequence.strip().upper()
    if len(seq) > MAX_SEQ_LEN:
        if not truncate:
            raise ESM2EncoderError(
                f"Sequence length {len(seq)} exceeds ESM-2 max ({MAX_SEQ_LEN})."
            )
        seq = seq[:MAX_SEQ_LEN]

    batch_converter = alphabet.get_batch_converter()
    _, _, tokens = batch_converter([("seq", seq)])
    tokens = tokens.to(device)

    with torch.no_grad():
        results = model(tokens, repr_layers=[33], return_contacts=False)

    # Mean pooling over sequence positions (exclude BOS=0, EOS=last)
    representations = results["representations"][33]
    seq_len = len(seq)
    embedding = representations[0, 1:seq_len + 1, :].mean(dim=0)

    return embedding.cpu().numpy().astype(np.float32)


def encode_fasta(
    fasta_path: Path,
    output_dir: Path | None = None,
    device: str | None = None,
    batch_size: int = 1,
    use_cache: bool = True,
) -> tuple[np.ndarray, list[dict[str, str]]]:
    """Encode all sequences in a FASTA file.

    Args:
        fasta_path: Path to input FASTA file.
        output_dir: Directory for cached embeddings (default: 03_models/esm2_embeddings/).
        device: Device override (auto-detect if None).
        batch_size: Sequences per batch (1 recommended for 8GB VRAM).
        use_cache: Skip sequences already in cache.

    Returns:
        Tuple of (embeddings array [N, 1280], index list of dicts with id/seq_hash).
    """
    import torch

    if device is None:
        device = _get_device()

    cache_dir = output_dir or EMBED_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Parse FASTA
    sequences = _parse_fasta(fasta_path)
    if not sequences:
        raise ESM2EncoderError(f"No sequences found in {fasta_path}")

    print(f"Encoding {len(sequences)} sequences with ESM-2 on {device}...")
    model, alphabet = _load_esm2_model(device)

    embeddings = np.zeros((len(sequences), EMBED_DIM), dtype=np.float32)
    index: list[dict[str, str]] = []

    t0 = time.perf_counter()
    for i, (seq_id, seq) in enumerate(sequences):
        seq_hash = hashlib.sha256(seq.encode()).hexdigest()[:16]
        cache_file = cache_dir / f"{seq_id}_{seq_hash}.npy"

        if use_cache and cache_file.exists():
            embeddings[i] = np.load(cache_file)
        else:
            emb = encode_sequence(seq, model=model, alphabet=alphabet, device=device)
            embeddings[i] = emb
            if use_cache:
                np.save(cache_file, emb)

        index.append({
            "seq_id": seq_id,
            "seq_hash": seq_hash,
            "seq_length": str(len(seq)),
            "cache_file": str(cache_file.name),
        })

        if (i + 1) % 50 == 0 or i == len(sequences) - 1:
            elapsed = time.perf_counter() - t0
            rate = (i + 1) / elapsed
            print(f"  [{i + 1}/{len(sequences)}] {rate:.1f} seq/s")

    # Save consolidated outputs
    np.save(cache_dir / "embeddings_matrix.npy", embeddings)
    _write_index_csv(cache_dir / "embeddings_index.csv", index)

    elapsed_total = time.perf_counter() - t0
    print(f"Done. {len(sequences)} embeddings in {elapsed_total:.1f}s "
          f"({len(sequences) / elapsed_total:.1f} seq/s)")
    print(f"Matrix: {cache_dir / 'embeddings_matrix.npy'}")
    print(f"Index:  {cache_dir / 'embeddings_index.csv'}")

    return embeddings, index


def _parse_fasta(fasta_path: Path) -> list[tuple[str, str]]:
    """Parse FASTA file into list of (id, sequence) tuples."""
    sequences: list[tuple[str, str]] = []
    current_id = ""
    current_seq: list[str] = []

    with open(fasta_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(">"):
                if current_id and current_seq:
                    sequences.append((current_id, "".join(current_seq)))
                current_id = line[1:].split()[0]
                current_seq = []
            elif line:
                current_seq.append(line)

    if current_id and current_seq:
        sequences.append((current_id, "".join(current_seq)))

    return sequences


def _write_index_csv(path: Path, index: list[dict[str, str]]) -> None:
    """Write embedding index CSV."""
    if not index:
        return
    fieldnames = list(index[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(index)


def get_cached_embeddings(
    cache_dir: Path | None = None,
) -> tuple[np.ndarray, list[dict[str, str]]] | None:
    """Load previously computed embeddings from cache if available.

    Returns:
        Tuple of (matrix, index) or None if cache doesn't exist.
    """
    cache = cache_dir or EMBED_CACHE_DIR
    matrix_path = cache / "embeddings_matrix.npy"
    index_path = cache / "embeddings_index.csv"

    if not matrix_path.exists() or not index_path.exists():
        return None

    matrix = np.load(matrix_path)
    index: list[dict[str, str]] = []
    with open(index_path, encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            index.append(dict(row))

    return matrix, index


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Encode protein sequences with ESM-2 (650M).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python esm2_encode.py --fasta enzymes.fasta\n"
            "  python esm2_encode.py --fasta enzymes.fasta --device cuda --batch-size 1\n"
            "  python esm2_encode.py --check-cache\n"
        ),
    )
    parser.add_argument(
        "--fasta",
        type=Path,
        default=None,
        help="Input FASTA file with enzyme sequences.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for embeddings (default: 03_models/esm2_embeddings/).",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["cpu", "cuda"],
        help="Compute device (auto-detect if omitted).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Sequences per batch (default: 1, recommended for 8GB VRAM).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable per-sequence caching.",
    )
    parser.add_argument(
        "--check-cache",
        action="store_true",
        help="Check existing cache status and exit.",
    )
    args = parser.parse_args()

    if args.check_cache:
        result = get_cached_embeddings(args.output_dir)
        if result is None:
            print("No cached embeddings found.")
            return 1
        matrix, index = result
        print(f"Cached embeddings: {matrix.shape[0]} sequences, dim={matrix.shape[1]}")
        print(f"Matrix size: {matrix.nbytes / 1024 / 1024:.1f} MB")
        return 0

    if args.fasta is None:
        parser.error("--fasta is required unless --check-cache is used.")

    if not args.fasta.exists():
        print(f"ERROR: FASTA file not found: {args.fasta}", file=sys.stderr)
        return 1

    try:
        encode_fasta(
            fasta_path=args.fasta,
            output_dir=args.output_dir,
            device=args.device,
            batch_size=args.batch_size,
            use_cache=not args.no_cache,
        )
    except ESM2EncoderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
