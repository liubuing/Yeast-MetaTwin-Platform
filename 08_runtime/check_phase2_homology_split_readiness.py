from __future__ import annotations

import json
import shutil
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "09_configs" / "deployment_config.json"
MAP_DIR = ROOT / "02_id_mapping"
TRAIN_DIR = ROOT / "05_training"
EVAL_DIR = ROOT / "06_evaluation"
LOCAL_MMSEQS = ROOT / "tools" / "mmseqs2" / "mmseqs" / "bin" / "mmseqs.exe"


def load_config() -> dict[str, Any]:
    return load_deployment_config()


def parse_fasta_headers(path: Path) -> set[str]:
    ids: set[str] = set()
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.startswith(">"):
                token = line[1:].strip().split()[0]
                ids.add(token)
                for part in token.replace("|", " ").split():
                    ids.add(part)
    return ids


def split_pipe(value: Any) -> set[str]:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return set()
    return {item.strip() for item in text.split("|") if item.strip()}


def pool_orf_coverage(path: Path, fasta_ids: set[str]) -> dict[str, Any]:
    df = pd.read_csv(path, dtype=str).fillna("")
    row_has_orf = df["orfs"].map(lambda value: bool(split_pipe(value)))
    all_orfs = set().union(*(split_pipe(value) for value in df["orfs"])) if len(df) else set()
    matched = all_orfs & fasta_ids
    return {
        "path": str(path.relative_to(ROOT)),
        "rows": len(df),
        "rows_with_orfs": int(row_has_orf.sum()),
        "unique_orfs": len(all_orfs),
        "unique_orfs_in_fasta": len(matched),
        "unique_orfs_missing_fasta": len(all_orfs - fasta_ids),
        "missing_orfs": sorted(all_orfs - fasta_ids),
    }


def write_missing_orfs(path: Path, coverage: dict[str, dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pool", "orf_id"])
        writer.writeheader()
        for pool, item in coverage.items():
            for orf in item.get("missing_orfs", []):
                writer.writerow({"pool": pool, "orf_id": orf})


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Homology Split Readiness",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Tool Availability",
        "",
        "| Tool | Available | Path |",
        "|---|---:|---|",
    ]
    for tool, status in payload["tools"].items():
        lines.append(f"| {tool} | {status['available']} | `{status['path']}` |")
    lines.extend(
        [
            "",
            "## FASTA Assets",
            "",
            "| FASTA | Exists | Header IDs |",
            "|---|---:|---:|",
        ]
    )
    for item in payload["fasta_assets"]:
        lines.append(f"| `{item['path']}` | {item['exists']} | {item['header_id_count']} |")
    lines.extend(
        [
            "",
            "## ORF Coverage By Pool",
            "",
            "| Pool | Rows | Rows with ORFs | Unique ORFs | ORFs in FASTA | ORFs missing FASTA |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for pool, coverage in payload["pool_orf_coverage"].items():
        lines.append(
            f"| {pool} | {coverage['rows']} | {coverage['rows_with_orfs']} | {coverage['unique_orfs']} | {coverage['unique_orfs_in_fasta']} | {coverage['unique_orfs_missing_fasta']} |"
        )
    lines.extend(
        [
            "",
            "## Status",
            "",
            f"Homology-cold split ready: `{payload['homology_split_ready']}`",
            "",
            "A homology-cold split requires a clustering tool such as MMseqs2 or CD-HIT plus sequence coverage for the ORFs in the target split pool. Current deterministic splits remain structural exact-equation splits until clustering is available.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    config = load_config()
    source_project = Path(config["source_project_dir"])
    fasta_candidates = [
        source_project / "Data" / "Saccharomyces_cerevisiae.fasta",
        source_project / "Code" / "ECnumber_prediction" / "CLEAN" / "data" / "Saccharomyces_cerevisiae.fasta",
        source_project / "audit" / "clean_unique_sequences.fasta",
    ]
    fasta_assets = []
    combined_ids: set[str] = set()
    for path in fasta_candidates:
        exists = path.exists()
        ids = parse_fasta_headers(path) if exists else set()
        combined_ids.update(ids)
        fasta_assets.append({"path": str(path), "exists": exists, "header_id_count": len(ids)})

    mmseqs_path = shutil.which("mmseqs") or (str(LOCAL_MMSEQS) if LOCAL_MMSEQS.exists() else "")
    tools = {
        "mmseqs": {"available": bool(mmseqs_path), "path": mmseqs_path},
        "cd-hit": {"available": shutil.which("cd-hit") is not None, "path": shutil.which("cd-hit") or ""},
        "cd-hit-est": {"available": shutil.which("cd-hit-est") is not None, "path": shutil.which("cd-hit-est") or ""},
    }
    pools = {
        "reference_only": TRAIN_DIR / "split_definitions_reference_only.csv",
        "reference_plus_candidate_no_overlap": TRAIN_DIR / "split_definitions_reference_plus_candidate_no_overlap.csv",
    }
    coverage = {name: pool_orf_coverage(path, combined_ids) for name, path in pools.items()}
    write_missing_orfs(EVAL_DIR / "phase2_homology_split_missing_orfs.csv", coverage)
    tool_ready = tools["mmseqs"]["available"] or tools["cd-hit"]["available"]
    sequence_ready = any(item["header_id_count"] > 0 for item in fasta_assets)
    homology_ready = bool(tool_ready and sequence_ready)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tools": tools,
        "fasta_assets": fasta_assets,
        "combined_fasta_header_id_count": len(combined_ids),
        "pool_orf_coverage": coverage,
        "homology_split_ready": homology_ready,
        "blocking_reason": "Missing MMseqs2/CD-HIT executable on PATH" if not tool_ready else "",
        "missing_orf_output": "06_evaluation/phase2_homology_split_missing_orfs.csv",
    }
    (EVAL_DIR / "phase2_homology_split_readiness.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_homology_split_readiness.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_homology_split_readiness.md")


if __name__ == "__main__":
    main()
