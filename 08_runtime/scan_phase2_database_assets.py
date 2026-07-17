from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "09_configs" / "deployment_config.json"
OUT_DIR = ROOT / "01_databases"
EVAL_DIR = ROOT / "06_evaluation"

TEXT_SUFFIXES = {".csv", ".tsv", ".txt", ".list"}
STRUCTURE_SUFFIXES = {".sdf"}
TABLE_SUFFIXES = {".xlsx"}
JSON_SUFFIXES = {".json"}


def load_config() -> dict[str, Any]:
    return load_deployment_config()


def count_lines(path: Path, limit: int = 1_000_000) -> int | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for idx, _line in enumerate(handle, start=1):
                if idx >= limit:
                    return idx
            return idx if "idx" in locals() else 0
    except Exception:
        return None


def sample_header(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.readline().strip()[:500]
    except Exception:
        return None


def classify_asset(path: Path, source_root: Path) -> str:
    lower = str(path.relative_to(source_root)).lower()
    name = path.name.lower()
    if "data_retrosynthesis" in lower or "retrosys" in name or "rxndb" in name:
        return "Retrosynthesis"
    if "mnx" in name or "metanetx" in lower:
        return "MetaNetX"
    if "chebi" in name:
        return "ChEBI"
    if "kegg" in name:
        return "KEGG"
    if "uniprot" in lower:
        return "UniProt"
    if "ymdb" in lower:
        return "YMDB"
    if "data\\model" in lower or "data/model" in lower or "yeast-gem" in name or "yeast_gem" in name:
        return "Model"
    return "Other"


def inspect_asset(path: Path, source_root: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    row: dict[str, Any] = {
        "database_guess": classify_asset(path, source_root),
        "relative_path": str(path.relative_to(source_root)),
        "absolute_path": str(path),
        "suffix": suffix,
        "size_bytes": path.stat().st_size,
        "line_count_sampled": None,
        "header_sample": None,
        "notes": "",
    }
    if suffix in TEXT_SUFFIXES:
        row["line_count_sampled"] = count_lines(path)
        row["header_sample"] = sample_header(path)
    elif suffix in JSON_SUFFIXES:
        row["notes"] = "JSON asset; not deeply loaded in phase2 scan to avoid expensive reads."
    elif suffix in STRUCTURE_SUFFIXES:
        row["notes"] = "Structure file; parse with RDKit/OpenBabel in later phase."
    elif suffix in TABLE_SUFFIXES:
        row["notes"] = "Excel table; inspect with pandas/openpyxl in later phase."
    return row


def find_assets(source_project: Path) -> list[Path]:
    roots = [source_project / "Data" / "database", source_project / "Data_retrosynthesis", source_project / "Data"]
    suffixes = TEXT_SUFFIXES | STRUCTURE_SUFFIXES | TABLE_SUFFIXES | JSON_SUFFIXES
    paths: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes:
                paths[str(path)] = path
    return sorted(paths.values(), key=lambda p: str(p).lower())


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def is_key_asset(row: dict[str, Any]) -> bool:
    rel = row["relative_path"].replace("\\", "/").lower()
    name = Path(rel).name
    if row["database_guess"] in {"ChEBI", "KEGG", "MetaNetX", "UniProt", "YMDB"}:
        return True
    if rel in {
        "data/yeast-gem-final.csv",
        "data/yeast_gem_smiles.json",
        "data/pathway_enzyme.list",
        "data/saccharomyces_cerevisiae.fasta",
    }:
        return True
    if name.startswith("retrosys_smiles_calculate_similarity_filter") or name.startswith("rxndb_all"):
        return True
    return False


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Database Asset Scan",
        "",
        f"Generated: {payload['generated_at']}",
        f"Source project: `{payload['source_project_dir']}`",
        "",
        "## Summary By Database Guess",
        "",
        "| Database | Files | Total size MB |",
        "|---|---:|---:|",
    ]
    for db, item in sorted(payload["summary"].items()):
        lines.append(f"| {db} | {item['files']} | {item['size_bytes'] / 1024 / 1024:.2f} |")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `01_databases/phase2_database_asset_inventory.csv`",
            "- `06_evaluation/phase2_database_asset_scan.json`",
            "",
            "## Notes",
            "",
            "This scan is intentionally lightweight. Large retrosynthesis JSON files are recorded but not deeply parsed. Phase 2 normalization should next build compound and reaction mapping tables using the schemas in `02_id_mapping`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    config = load_config()
    source_project = Path(config["source_project_dir"])
    rows = [inspect_asset(path, source_project) for path in find_assets(source_project)]
    summary: dict[str, dict[str, int]] = {}
    for row in rows:
        item = summary.setdefault(row["database_guess"], {"files": 0, "size_bytes": 0})
        item["files"] += 1
        item["size_bytes"] += int(row["size_bytes"])

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_project_dir": str(source_project),
        "asset_count": len(rows),
        "summary": summary,
    }
    OUT_DIR.mkdir(exist_ok=True)
    EVAL_DIR.mkdir(exist_ok=True)
    write_csv(OUT_DIR / "phase2_database_asset_inventory.csv", rows)
    write_csv(OUT_DIR / "phase2_key_database_assets.csv", [row for row in rows if is_key_asset(row)])
    (EVAL_DIR / "phase2_database_asset_scan.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_database_asset_scan.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_database_asset_scan.md")


if __name__ == "__main__":
    main()
