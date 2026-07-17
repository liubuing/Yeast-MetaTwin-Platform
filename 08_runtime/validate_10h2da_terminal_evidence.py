from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(load_deployment_config()["source_project_dir"])
EVAL_DIR = ROOT / "06_evaluation"
REPORT_DIR = ROOT / "07_reports"

ASSETS = {
    "uniprot_yeast": SOURCE / "Data/database/uniprot/uniprotkb_organism_id_559292_2023_11_08.tsv",
    "uniprot_reaction_smiles": SOURCE / "Data/database/uniprot/uniprot_reaction_smiles.csv",
    "kegg_compound": SOURCE / "Data/database/kegg_compound.txt",
    "ymdb": SOURCE / "Data/database/ymdb/ymdb.csv",
    "chebi_smiles": SOURCE / "Data/database/chebi_id_smiles.csv",
    "mnx_reaction_smile": SOURCE / "Data/database/MNXreaction_smile.csv",
}

TERMS = [
    "10-hydroxy-trans-2-decenoic",
    "10-hydroxy-2-decenoic",
    "10h2da",
    "hydroxy-trans-2-decen",
    "trans-2-deceno",
    "2-decenoate",
    "dec-2-enoyl",
    "omega-hydroxylase",
    "omega hydroxylase",
    "cyp52",
    "cytochrome p450",
    "acyl-coa thioesterase",
    "enoyl-coa thioesterase",
    "thioesterase",
]

CANDIDATES = [
    {
        "candidate_reaction_id": "CAND_T2DEC_THIOESTERASE_P",
        "required_activity": "trans-dec-2-enoyl-CoA thioesterase",
        "ec_hint": "3.1.2.-|3.1.2.2",
        "local_model_support": "TES1 supports decanoyl-CoA thioesterase, not exact trans-dec-2-enoyl-CoA release",
    },
    {
        "candidate_reaction_id": "CAND_T2DEC_OMEGA_HYDROXYLASE_P",
        "required_activity": "trans-2-decenoate omega-hydroxylase",
        "ec_hint": "1.14.-.-|1.14.14.-",
        "local_model_support": "no native exact enzyme found",
    },
    {
        "candidate_reaction_id": "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P",
        "required_activity": "trans-dec-2-enoyl-CoA omega-hydroxylase",
        "ec_hint": "1.14.-.-|1.14.14.-",
        "local_model_support": "no native exact enzyme found",
    },
    {
        "candidate_reaction_id": "CAND_10H2DA_COA_THIOESTERASE_P",
        "required_activity": "10-hydroxy-trans-2-decenoyl-CoA thioesterase",
        "ec_hint": "3.1.2.-|3.1.2.2",
        "local_model_support": "TES1 enzyme class plausible, exact substrate unvalidated",
    },
]


def has_text(value: Any) -> bool:
    return str(value).strip().lower() not in {"", "nan", "none", "null"}


def row_text(row: dict[str, Any]) -> str:
    return " | ".join(str(value) for value in row.values() if has_text(value))


def search_table(asset_name: str, path: Path, sep: str, chunksize: int = 50000) -> list[dict[str, Any]]:
    if not path.exists():
        return [{"asset": asset_name, "term": "", "match_type": "asset_missing", "record": str(path)}]
    matches: list[dict[str, Any]] = []
    try:
        reader = pd.read_csv(path, dtype=str, sep=sep, chunksize=chunksize, on_bad_lines="skip").fillna("")
    except Exception as exc:
        return [{"asset": asset_name, "term": "", "match_type": "read_error", "record": f"{type(exc).__name__}: {exc}"}]
    for chunk in reader:
        for row in chunk.fillna("").to_dict("records"):
            text = row_text(row).lower()
            hit_terms = [term for term in TERMS if term in text]
            if hit_terms:
                matches.append(
                    {
                        "asset": asset_name,
                        "term": "|".join(hit_terms),
                        "match_type": "text_match",
                        "record": row_text(row)[:2000],
                    }
                )
                if len(matches) >= 500:
                    return matches
    return matches


def yeast_terminal_candidates() -> list[dict[str, Any]]:
    path = ASSETS["uniprot_yeast"]
    df = pd.read_csv(path, dtype=str, sep="\t").fillna("")
    rows = []
    terms = ["thioester", "cytochrome p450", "monooxygenase", "hydroxylase", "cyp"]
    for row in df.to_dict("records"):
        text = row_text(row).lower()
        if any(term in text for term in terms):
            rows.append(
                {
                    "entry": row.get("Entry", ""),
                    "gene_names": row.get("Gene Names", ""),
                    "protein_names": row.get("Protein names", ""),
                    "ec_number": row.get("EC number", ""),
                    "terminal_relevance": relevance(row),
                }
            )
    return rows


def relevance(row: dict[str, Any]) -> str:
    text = row_text(row).lower()
    if "thioester" in text:
        return "possible_thioesterase_class_support"
    if "cytochrome p450" in text or "cyp" in text or "monooxygenase" in text or "hydroxylase" in text:
        return "possible_oxygenase_class_support"
    return "general_terminal_enzyme_keyword"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# 10H2DA Terminal Evidence Validation",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Candidate Verdicts",
        "",
        "| Candidate | Verdict | Reason |",
        "|---|---|---|",
    ]
    for row in payload["candidate_verdicts"]:
        lines.append(f"| {row['candidate_reaction_id']} | {row['validation_verdict']} | {row['reason']} |")
    lines.extend(["", "## Search Summary", "", "| Asset | Matches |", "|---|---:|"])
    for asset, count in payload["asset_match_counts"].items():
        lines.append(f"| {asset} | {count} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Local database search finds enzyme-class support for thioesterase and oxygenase terms, but no direct curated local record proves the exact 10H2DA terminal reactions. The terminal reactions therefore remain FBA-feasible, mass/charge-balanced hypotheses, not curated validated reactions.",
            "",
            "## Outputs",
            "",
            "- `06_evaluation/10h2da_terminal_evidence_matches.csv`",
            "- `06_evaluation/10h2da_terminal_yeast_enzyme_candidates.csv`",
            "- `06_evaluation/10h2da_terminal_validation_verdicts.csv`",
            "- `06_evaluation/10h2da_terminal_evidence_validation.json`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    all_matches: list[dict[str, Any]] = []
    for asset, path in ASSETS.items():
        sep = "\t" if path.suffix in {".tsv", ".txt"} else ","
        all_matches.extend(search_table(asset, path, sep))
    enzyme_rows = yeast_terminal_candidates()
    direct_10h2da = [row for row in all_matches if any(term in row["term"] for term in ["10h2da", "10-hydroxy-trans-2-decenoic", "10-hydroxy-2-decenoic"])]
    thio_hits = [row for row in enzyme_rows if row["terminal_relevance"] == "possible_thioesterase_class_support"]
    oxy_hits = [row for row in enzyme_rows if row["terminal_relevance"] == "possible_oxygenase_class_support"]

    verdicts = []
    for candidate in CANDIDATES:
        if direct_10h2da:
            verdict = "direct_local_name_evidence_found_review_required"
            reason = "Direct target-name match exists locally, but reaction/enzyme specificity still requires manual review."
        elif "THIOESTERASE" in candidate["candidate_reaction_id"] and thio_hits:
            verdict = "enzyme_class_support_only"
            reason = "Yeast UniProt contains thioesterase-class entries, but no exact 10H2DA substrate record was found."
        elif "HYDROXYLASE" in candidate["candidate_reaction_id"] and oxy_hits:
            verdict = "enzyme_class_support_only"
            reason = "Yeast UniProt contains oxygenase/hydroxylase/P450-class entries, but no exact omega-hydroxylation record for this substrate was found."
        else:
            verdict = "no_direct_local_validation"
            reason = "No local direct evidence found for the exact terminal chemistry."
        verdicts.append({**candidate, "validation_verdict": verdict, "reason": reason})

    asset_counts = {asset: sum(1 for row in all_matches if row["asset"] == asset and row["match_type"] == "text_match") for asset in ASSETS}
    write_csv(EVAL_DIR / "10h2da_terminal_evidence_matches.csv", all_matches, ["asset", "term", "match_type", "record"])
    write_csv(EVAL_DIR / "10h2da_terminal_yeast_enzyme_candidates.csv", enzyme_rows, ["entry", "gene_names", "protein_names", "ec_number", "terminal_relevance"])
    write_csv(EVAL_DIR / "10h2da_terminal_validation_verdicts.csv", verdicts, list(verdicts[0].keys()))
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "asset_match_counts": asset_counts,
        "direct_10h2da_match_count": len(direct_10h2da),
        "yeast_terminal_enzyme_candidate_count": len(enzyme_rows),
        "candidate_verdicts": verdicts,
    }
    (EVAL_DIR / "10h2da_terminal_evidence_validation.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORT_DIR / "10H2DA_terminal_evidence_validation.md").write_text(render_report(payload), encoding="utf-8")
    print(REPORT_DIR / "10H2DA_terminal_evidence_validation.md")


if __name__ == "__main__":
    main()
