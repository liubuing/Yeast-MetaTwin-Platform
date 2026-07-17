from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "09_configs" / "deployment_config.json"
TRAIN_DIR = ROOT / "05_training"
EVAL_DIR = ROOT / "06_evaluation"
LOCAL_MMSEQS = ROOT / "tools" / "mmseqs2" / "mmseqs" / "bin" / "mmseqs.exe"

POOLS = {
    "reference_only": TRAIN_DIR / "split_definitions_reference_only.csv",
    "reference_plus_candidate_no_overlap": TRAIN_DIR / "split_definitions_reference_plus_candidate_no_overlap.csv",
}
MIN_SEQ_IDS = [0.3, 0.5, 0.7, 0.9]
COVERAGE = 0.8
COV_MODE = 0


def load_config() -> dict[str, Any]:
    return load_deployment_config()


def mmseqs_path() -> str:
    path = os.environ.get("METATWIN_MMSEQS") or shutil.which("mmseqs") or (str(LOCAL_MMSEQS) if LOCAL_MMSEQS.exists() else "")
    if not path:
        raise FileNotFoundError("MMseqs2 executable not found; set METATWIN_MMSEQS")
    return path


def parse_fasta(path: Path) -> dict[str, str]:
    sequences: dict[str, str] = {}
    current_id = ""
    chunks: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_id:
                    sequences[current_id] = "".join(chunks)
                current_id = line[1:].split()[0]
                chunks = []
            else:
                chunks.append(line)
    if current_id:
        sequences[current_id] = "".join(chunks)
    return sequences


def split_pipe(value: Any) -> list[str]:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return []
    return [item.strip() for item in text.split("|") if item.strip() and item.strip().lower() != "nogene"]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_bucket(key: str) -> int:
    return int(sha256_text(key)[:12], 16) % 100


def assign_split(key: str) -> str:
    bucket = stable_bucket(key)
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "dev"
    return "test"


def collect_orfs() -> set[str]:
    orfs: set[str] = set()
    for path in POOLS.values():
        df = pd.read_csv(path, dtype=str).fillna("")
        for value in df["orfs"]:
            orfs.update(split_pipe(value))
    return orfs


def write_fasta(path: Path, orfs: set[str], sequences: dict[str, str]) -> tuple[int, int]:
    written = 0
    missing = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for orf in sorted(orfs):
            seq = sequences.get(orf, "")
            if not seq:
                missing += 1
                continue
            handle.write(f">{orf}\n")
            for i in range(0, len(seq), 80):
                handle.write(seq[i : i + 80] + "\n")
            written += 1
    return written, missing


def run_mmseqs(input_fasta: Path, min_seq_id: float) -> Path:
    executable = mmseqs_path()
    tag = str(min_seq_id).replace(".", "_")
    run_root = Path(tempfile.gettempdir()) / "metatwin" / f"mmseqs_sensitivity_{tag}" / f"run_{os.getpid()}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    run_root.mkdir(parents=True, exist_ok=True)
    run_input = run_root / "reaction_split_orfs.fasta"
    shutil.copyfile(input_fasta, run_input)
    run_db = run_root / "input_db"
    run_cluster = run_root / "cluster_db"
    run_tmp = run_root / "tmp"
    run_cluster_tsv = run_root / "cluster.tsv"
    commands = [
        [executable, "createdb", str(run_input), str(run_db)],
        [
            executable,
            "cluster",
            str(run_db),
            str(run_cluster),
            str(run_tmp),
            "--min-seq-id",
            str(min_seq_id),
            "-c",
            str(COVERAGE),
            "--cov-mode",
            str(COV_MODE),
            "--threads",
            "4",
        ],
        [executable, "createtsv", str(run_db), str(run_db), str(run_cluster), str(run_cluster_tsv), "--threads", "4"],
    ]
    logs = []
    for cmd in commands:
        result = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=False)
        logs.append({"command": cmd, "returncode": result.returncode, "stdout": result.stdout[-5000:], "stderr": result.stderr[-5000:]})
        if result.returncode != 0:
            raise RuntimeError(f"MMseqs2 failed at min_seq_id={min_seq_id}: {' '.join(cmd)}")
    log_path = EVAL_DIR / f"phase2_mmseqs_threshold_{tag}_runlog.json"
    log_path.write_text(json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8")
    return run_cluster_tsv


def read_clusters(path: Path) -> dict[str, str]:
    member_to_rep: dict[str, str] = {}
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                rep, member = parts[0], parts[1]
                member_to_rep[member] = rep
                member_to_rep.setdefault(rep, rep)
    return member_to_rep


def reaction_key(row: dict[str, Any], member_to_rep: dict[str, str]) -> tuple[str, str]:
    reps = sorted({member_to_rep[orf] for orf in split_pipe(row.get("orfs", "")) if orf in member_to_rep})
    if reps:
        return "mmseqs_cluster_set", "cluster_set:" + sha256_text("|".join(reps))
    equation = str(row.get("model_equation", "")).strip()
    if equation:
        return "fallback_equation", "equation:" + equation
    return "fallback_reaction_id", "reaction_id:" + str(row["model_reaction_id"])


def summarize_pool(pool: str, path: Path, member_to_rep: dict[str, str], min_seq_id: float, cluster_count: int) -> dict[str, Any]:
    df = pd.read_csv(path, dtype=str).fillna("")
    key_to_splits: dict[str, set[str]] = defaultdict(set)
    split_counts: Counter[str] = Counter()
    key_type_counts: Counter[str] = Counter()
    for row in df.to_dict("records"):
        key_type, key = reaction_key(row, member_to_rep)
        split = assign_split(key)
        key_to_splits[key].add(split)
        split_counts[split] += 1
        key_type_counts[key_type] += 1
    return {
        "min_seq_id": min_seq_id,
        "coverage": COVERAGE,
        "cov_mode": COV_MODE,
        "pool": pool,
        "mmseqs_clusters": cluster_count,
        "rows": len(df),
        "train": split_counts.get("train", 0),
        "dev": split_counts.get("dev", 0),
        "test": split_counts.get("test", 0),
        "homology_keys": len(key_to_splits),
        "crossing_keys": sum(1 for splits in key_to_splits.values() if len(splits) > 1),
        "cluster_set_rows": key_type_counts.get("mmseqs_cluster_set", 0),
        "fallback_rows": key_type_counts.get("fallback_equation", 0) + key_type_counts.get("fallback_reaction_id", 0),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_report(rows: list[dict[str, Any]], generated_at: str, fasta_written: int, fasta_missing: int) -> str:
    lines = [
        "# Phase 2 MMseqs2 Threshold Sensitivity",
        "",
        f"Generated: {generated_at}",
        "",
        "## Input",
        "",
        f"- FASTA sequences written: {fasta_written}",
        f"- ORFs missing sequence: {fasta_missing}",
        f"- Coverage: {COVERAGE}",
        f"- Coverage mode: {COV_MODE}",
        "",
        "## Results",
        "",
        "| min_seq_id | Pool | Clusters | Rows | Train | Dev | Test | Homology keys | Crossing keys | Fallback rows |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['min_seq_id']} | {row['pool']} | {row['mmseqs_clusters']} | {row['rows']} | {row['train']} | {row['dev']} | {row['test']} | {row['homology_keys']} | {row['crossing_keys']} | {row['fallback_rows']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Lower `min_seq_id` values create broader clusters and stricter homology separation. Higher values create more clusters and are closer to exact-sequence splitting. All rows here are summaries; the currently materialized homology split remains the 0.3 identity / 0.8 coverage split.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    config = load_config()
    source_project = Path(config["source_project_dir"])
    sequences = parse_fasta(source_project / "Data" / "Saccharomyces_cerevisiae.fasta")
    orfs = collect_orfs()
    out_dir = TRAIN_DIR / "mmseqs_threshold_sensitivity"
    out_dir.mkdir(parents=True, exist_ok=True)
    input_fasta = out_dir / "reaction_split_orfs.fasta"
    fasta_written, fasta_missing = write_fasta(input_fasta, orfs, sequences)
    rows: list[dict[str, Any]] = []
    for min_seq_id in MIN_SEQ_IDS:
        cluster_tsv = run_mmseqs(input_fasta, min_seq_id)
        member_to_rep = read_clusters(cluster_tsv)
        cluster_count = len(set(member_to_rep.values()))
        for pool, path in POOLS.items():
            rows.append(summarize_pool(pool, path, member_to_rep, min_seq_id, cluster_count))
    write_csv(EVAL_DIR / "phase2_mmseqs_threshold_sensitivity.csv", rows)
    generated_at = datetime.now().isoformat(timespec="seconds")
    payload = {
        "generated_at": generated_at,
        "min_seq_ids": MIN_SEQ_IDS,
        "coverage": COVERAGE,
        "cov_mode": COV_MODE,
        "fasta_sequences_written": fasta_written,
        "orfs_missing_sequence": fasta_missing,
        "rows": rows,
    }
    (EVAL_DIR / "phase2_mmseqs_threshold_sensitivity.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_mmseqs_threshold_sensitivity.md").write_text(render_report(rows, generated_at, fasta_written, fasta_missing), encoding="utf-8")
    print(EVAL_DIR / "phase2_mmseqs_threshold_sensitivity.md")


if __name__ == "__main__":
    main()
