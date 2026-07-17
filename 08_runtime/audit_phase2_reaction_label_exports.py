from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "05_training"
EVAL_DIR = ROOT / "06_evaluation"


def has_text(value: Any) -> bool:
    return str(value).strip().lower() not in {"", "nan", "none", "null"}


def split_values(value: Any) -> list[str]:
    text = str(value).strip()
    if not has_text(text):
        return []
    out: list[str] = []
    for chunk in text.replace(";", "|").split("|"):
        chunk = chunk.strip()
        if has_text(chunk):
            out.append(chunk)
    return out


def pct(num: int, den: int) -> float:
    return 0.0 if den == 0 else num / den * 100


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def duplicate_rows(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    id_counts = Counter(df["model_reaction_id"])
    equation_counts = Counter(df["model_equation"])
    dup_ids = [
        {"model_reaction_id": key, "count": value}
        for key, value in sorted(id_counts.items())
        if value > 1
    ]
    dup_equations = [
        {"model_equation": key, "count": value, "groups": "|".join(sorted(set(df[df["model_equation"] == key]["export_group"])))[:500]}
        for key, value in sorted(equation_counts.items())
        if has_text(key) and value > 1
    ]
    return dup_ids, dup_equations


def coverage_by_group(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group, sub in df.groupby("export_group", sort=False):
        total = len(sub)
        with_gpr = int(sub["gpr"].map(has_text).sum())
        with_orfs = int(sub["orfs"].map(has_text).sum())
        with_enzyme_rows = int((pd.to_numeric(sub["enzyme_evidence_rows"], errors="coerce").fillna(0) > 0).sum())
        with_enzyme_ec = int(sub["enzyme_ec_numbers"].map(has_text).sum())
        with_external = int(sub["external_database_crossrefs_compact"].map(has_text).sum())
        with_rxndb = int(sub["rxndb_id"].map(has_text).sum())
        with_rxndb_ec = int(sub["rxndb_ec_number"].map(has_text).sum())
        rows.append(
            {
                "export_group": group,
                "rows": total,
                "with_gpr": with_gpr,
                "with_gpr_pct": round(pct(with_gpr, total), 2),
                "with_orfs": with_orfs,
                "with_orfs_pct": round(pct(with_orfs, total), 2),
                "with_enzyme_evidence_rows": with_enzyme_rows,
                "with_enzyme_evidence_rows_pct": round(pct(with_enzyme_rows, total), 2),
                "with_enzyme_ec_numbers": with_enzyme_ec,
                "with_enzyme_ec_numbers_pct": round(pct(with_enzyme_ec, total), 2),
                "with_external_database_crossrefs": with_external,
                "with_external_database_crossrefs_pct": round(pct(with_external, total), 2),
                "with_rxndb_provenance": with_rxndb,
                "with_rxndb_provenance_pct": round(pct(with_rxndb, total), 2),
                "with_rxndb_ec_number": with_rxndb_ec,
                "with_rxndb_ec_number_pct": round(pct(with_rxndb_ec, total), 2),
            }
        )
    return rows


def cross_pool_overlap(df: pd.DataFrame) -> list[dict[str, Any]]:
    by_equation: dict[str, set[str]] = defaultdict(set)
    by_external: dict[str, set[str]] = defaultdict(set)
    for row in df.to_dict("records"):
        if has_text(row["model_equation"]):
            by_equation[row["model_equation"]].add(row["export_group"])
        for xref in split_values(row["external_database_crossrefs_compact"]):
            by_external[xref].add(row["export_group"])
    rows: list[dict[str, Any]] = []
    for key, groups in by_equation.items():
        if len(groups) > 1:
            rows.append({"overlap_type": "exact_model_equation", "key": key, "groups": "|".join(sorted(groups))})
    for key, groups in by_external.items():
        if len(groups) > 1:
            rows.append({"overlap_type": "external_crossref", "key": key, "groups": "|".join(sorted(groups))})
    return rows


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Reaction Label Export QA",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Total rows | {payload['total_rows']} |",
        f"| Duplicate reaction IDs | {payload['duplicate_reaction_id_count']} |",
        f"| Duplicate model equations | {payload['duplicate_equation_count']} |",
        f"| Cross-pool overlap records | {payload['cross_pool_overlap_count']} |",
        "",
        "## Coverage By Export Group",
        "",
        "| Export group | Rows | GPR % | Enzyme evidence % | Enzyme EC % | External database xref % | RXNdb % | RXNdb EC % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["coverage_by_group"]:
        lines.append(
            f"| {row['export_group']} | {row['rows']} | {row['with_gpr_pct']:.2f} | {row['with_enzyme_evidence_rows_pct']:.2f} | {row['with_enzyme_ec_numbers_pct']:.2f} | {row['with_external_database_crossrefs_pct']:.2f} | {row['with_rxndb_provenance_pct']:.2f} | {row['with_rxndb_ec_number_pct']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Output Files",
            "",
            "- `06_evaluation/phase2_reaction_label_export_qa.json`",
            "- `06_evaluation/phase2_reaction_label_export_coverage.csv`",
            "- `06_evaluation/phase2_reaction_label_export_duplicate_ids.csv`",
            "- `06_evaluation/phase2_reaction_label_export_duplicate_equations.csv`",
            "- `06_evaluation/phase2_reaction_label_export_cross_pool_overlap.csv`",
            "",
            "## Interpretation",
            "",
            "Duplicate model equations are expected in compartment-specific or direction-specific model reactions, but they should be reviewed before creating ML splits. Cross-pool overlap records identify exact equations or external cross-references appearing in more than one export group.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    df = pd.read_csv(TRAIN_DIR / "reaction_all_label_export_groups.csv", dtype=str).fillna("")
    dup_ids, dup_equations = duplicate_rows(df)
    coverage = coverage_by_group(df)
    overlap = cross_pool_overlap(df)

    write_csv(EVAL_DIR / "phase2_reaction_label_export_coverage.csv", coverage, list(coverage[0].keys()))
    write_csv(EVAL_DIR / "phase2_reaction_label_export_duplicate_ids.csv", dup_ids, ["model_reaction_id", "count"])
    write_csv(EVAL_DIR / "phase2_reaction_label_export_duplicate_equations.csv", dup_equations, ["model_equation", "count", "groups"])
    write_csv(EVAL_DIR / "phase2_reaction_label_export_cross_pool_overlap.csv", overlap, ["overlap_type", "key", "groups"])

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_rows": len(df),
        "duplicate_reaction_id_count": len(dup_ids),
        "duplicate_equation_count": len(dup_equations),
        "cross_pool_overlap_count": len(overlap),
        "coverage_by_group": coverage,
    }
    (EVAL_DIR / "phase2_reaction_label_export_qa.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_reaction_label_export_qa.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_reaction_label_export_qa.md")


if __name__ == "__main__":
    main()
