from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "09_configs" / "deployment_config.json"
MAP_DIR = ROOT / "02_id_mapping"
EVAL_DIR = ROOT / "06_evaluation"


def load_config() -> dict[str, Any]:
    return load_deployment_config()


def clean_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def first_existing(row: pd.Series, columns: list[str]) -> str:
    for column in columns:
        if column in row.index:
            value = clean_value(row[column])
            if value:
                return value
    return ""


def enrich_compounds(source_project: Path) -> dict[str, Any]:
    seed_path = MAP_DIR / "model_compound_seed.csv"
    final_path = source_project / "Data" / "yeast-GEM-final.csv"
    seed = pd.read_csv(seed_path, dtype=str).fillna("")
    final = pd.read_csv(final_path, dtype=str).fillna("")

    final_by_id = {clean_value(row["REPLACEMENT ID"]): row for _, row in final.iterrows() if clean_value(row.get("REPLACEMENT ID"))}
    enriched_rows = []
    mapped = 0
    for _, row in seed.iterrows():
        out = row.to_dict()
        model_id = out["model_metabolite_id"]
        source = final_by_id.get(model_id)
        if source is not None:
            mapped += 1
            out["smiles"] = first_existing(source, ["standard_smiles", "SMILES"])
            out["inchikey"] = first_existing(source, ["inchikey0"])
            out["kegg_id"] = first_existing(source, ["kegg_id"])
            out["chebi_id"] = first_existing(source, ["chebi_id"])
            out["metanetx_id"] = first_existing(source, ["MNXM_ID", "metMetaNetXID_new"])
            out["mapping_source"] = "yeast-GEM-final.csv"
        else:
            out["mapping_source"] = ""
        enriched_rows.append(out)

    out_path = MAP_DIR / "model_compound_seed_enriched.csv"
    pd.DataFrame(enriched_rows).to_csv(out_path, index=False, encoding="utf-8")
    df = pd.DataFrame(enriched_rows)
    return {
        "rows": len(df),
        "mapped_by_model_id": mapped,
        "smiles_nonempty": int((df["smiles"].astype(str).str.len() > 0).sum()),
        "inchikey_nonempty": int((df["inchikey"].astype(str).str.len() > 0).sum()),
        "kegg_nonempty": int((df["kegg_id"].astype(str).str.len() > 0).sum()),
        "chebi_nonempty": int((df["chebi_id"].astype(str).str.len() > 0).sum()),
        "metanetx_nonempty": int((df["metanetx_id"].astype(str).str.len() > 0).sum()),
        "output": str(out_path),
    }


def enrich_enzyme_evidence(source_project: Path) -> dict[str, Any]:
    seed_path = MAP_DIR / "model_enzyme_evidence_seed.csv"
    uniprot_path = source_project / "Data" / "database" / "uniprot" / "uniprotkb_organism_id_559292_2023_11_08.tsv"
    seed = pd.read_csv(seed_path, dtype=str).fillna("")
    uniprot = pd.read_csv(uniprot_path, sep="\t", dtype=str).fillna("")

    by_orf: dict[str, dict[str, str]] = {}
    for _, row in uniprot.iterrows():
        genes = clean_value(row.get("Gene Names"))
        entry = clean_value(row.get("Entry"))
        ec = clean_value(row.get("EC number"))
        protein_names = clean_value(row.get("Protein names"))
        for token in genes.replace(";", " ").split():
            if token.startswith("Y") and len(token) >= 7:
                by_orf.setdefault(token, {"Entry": entry, "EC number": ec, "Protein names": protein_names})

    enriched_rows = []
    mapped = 0
    ec_nonempty = 0
    for _, row in seed.iterrows():
        out = row.to_dict()
        source = by_orf.get(out["orf_id"])
        if source:
            mapped += 1
            out["protein_id"] = source["Entry"]
            out["ec_numbers"] = source["EC number"].replace("; ", "|").replace(";", "|")
            out["protein_names"] = source["Protein names"]
            out["mapping_source"] = "UniProt yeast TSV"
            if out["ec_numbers"]:
                ec_nonempty += 1
        else:
            out["protein_names"] = ""
            out["mapping_source"] = ""
        enriched_rows.append(out)

    out_path = MAP_DIR / "model_enzyme_evidence_seed_enriched.csv"
    pd.DataFrame(enriched_rows).to_csv(out_path, index=False, encoding="utf-8")
    unique_orfs = seed["orf_id"].nunique()
    mapped_orfs = len({row["orf_id"] for row in enriched_rows if row.get("protein_id")})
    return {
        "rows": len(enriched_rows),
        "unique_orfs": int(unique_orfs),
        "mapped_rows_by_orf": mapped,
        "mapped_unique_orfs": mapped_orfs,
        "ec_nonempty_rows": ec_nonempty,
        "output": str(out_path),
    }


def render_report(payload: dict[str, Any]) -> str:
    c = payload["compound_enrichment"]
    e = payload["enzyme_enrichment"]
    return "\n".join(
        [
            "# Phase 2 Mapping Enrichment",
            "",
            f"Generated: {payload['generated_at']}",
            "",
            "## Compound Enrichment",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Rows | {c['rows']} |",
            f"| Mapped by model metabolite ID | {c['mapped_by_model_id']} |",
            f"| SMILES non-empty | {c['smiles_nonempty']} |",
            f"| InChIKey non-empty | {c['inchikey_nonempty']} |",
            f"| KEGG ID non-empty | {c['kegg_nonempty']} |",
            f"| ChEBI ID non-empty | {c['chebi_nonempty']} |",
            f"| MetaNetX ID non-empty | {c['metanetx_nonempty']} |",
            "",
            "## Enzyme Evidence Enrichment",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Rows | {e['rows']} |",
            f"| Unique ORFs | {e['unique_orfs']} |",
            f"| Mapped rows by ORF | {e['mapped_rows_by_orf']} |",
            f"| Mapped unique ORFs | {e['mapped_unique_orfs']} |",
            f"| EC non-empty rows | {e['ec_nonempty_rows']} |",
            "",
            "## Outputs",
            "",
            f"- `{Path(c['output']).relative_to(ROOT)}`",
            f"- `{Path(e['output']).relative_to(ROOT)}`",
            "",
            "## Notes",
            "",
            "Compound mapping currently uses model metabolite IDs from `yeast-GEM-final.csv`; this covers model metabolites with existing curated mappings. Enzyme mapping currently uses ORF matches from the local yeast UniProt TSV. The next step is cross-database structure mapping for unmapped compounds and curated reaction cross-references.",
        ]
    ) + "\n"


def main() -> None:
    config = load_config()
    source_project = Path(config["source_project_dir"])
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "compound_enrichment": enrich_compounds(source_project),
        "enzyme_enrichment": enrich_enzyme_evidence(source_project),
    }
    EVAL_DIR.mkdir(exist_ok=True)
    (EVAL_DIR / "phase2_mapping_enrichment.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_mapping_enrichment.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_mapping_enrichment.md")


if __name__ == "__main__":
    main()
