from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import cobra
from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "09_configs" / "deployment_config.json"
OUT_DIR = ROOT / "02_id_mapping"
EVAL_DIR = ROOT / "06_evaluation"


def load_config() -> dict[str, Any]:
    return load_deployment_config()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_compounds(model: cobra.Model) -> list[dict[str, Any]]:
    rows = []
    for idx, met in enumerate(sorted(model.metabolites, key=lambda item: item.id), start=1):
        rows.append(
            {
                "compound_uid": f"MODEL_CMPD:{idx:07d}",
                "model_metabolite_id": met.id,
                "primary_name": met.name or met.id,
                "formula": met.formula or "",
                "charge": met.charge if met.charge is not None else "",
                "compartment": met.compartment or "",
                "smiles": "",
                "inchikey": "",
                "kegg_id": "",
                "chebi_id": "",
                "metanetx_id": "",
                "source_database": "Yeast-MetaTwin",
                "source_record_id": met.id,
                "confidence_level": "model",
                "notes": "Extracted from Yeast-MetaTwin model; external IDs to be filled by mapping phase.",
            }
        )
    return rows


def build_reactions(model: cobra.Model, compound_uid_by_id: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for idx, rxn in enumerate(sorted(model.reactions, key=lambda item: item.id), start=1):
        reactants = [met for met, coeff in rxn.metabolites.items() if coeff < 0]
        products = [met for met, coeff in rxn.metabolites.items() if coeff > 0]
        stoich = {met.id: coeff for met, coeff in sorted(rxn.metabolites.items(), key=lambda item: item[0].id)}
        if rxn.lower_bound < 0 and rxn.upper_bound > 0:
            direction = "reversible"
        elif rxn.upper_bound <= 0:
            direction = "reverse"
        else:
            direction = "forward"
        rows.append(
            {
                "reaction_uid": f"MODEL_RXN:{idx:07d}",
                "model_reaction_id": rxn.id,
                "primary_name": rxn.name or rxn.id,
                "equation": rxn.reaction,
                "reactant_compound_uids": "|".join(compound_uid_by_id.get(met.id, met.id) for met in sorted(reactants, key=lambda item: item.id)),
                "product_compound_uids": "|".join(compound_uid_by_id.get(met.id, met.id) for met in sorted(products, key=lambda item: item.id)),
                "stoichiometry_json": json.dumps(stoich, sort_keys=True),
                "direction": direction,
                "lower_bound": rxn.lower_bound,
                "upper_bound": rxn.upper_bound,
                "genes": "|".join(sorted((gene.name or gene.id) for gene in rxn.genes)),
                "orfs": "|".join(sorted(gene.id for gene in rxn.genes)),
                "gpr": rxn.gene_reaction_rule,
                "is_underground_rxn_prefix": rxn.id.startswith("rxn"),
                "source_database": "Yeast-MetaTwin",
                "source_record_id": rxn.id,
                "evidence_type": "model",
                "confidence_score": "",
                "notes": "Extracted from Yeast-MetaTwin model.",
            }
        )
    return rows


def build_enzyme_evidence(model: cobra.Model, reaction_uid_by_id: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    idx = 1
    for rxn in sorted(model.reactions, key=lambda item: item.id):
        for gene in sorted(rxn.genes, key=lambda item: item.id):
            rows.append(
                {
                    "enzyme_uid": f"MODEL_ENZ:{idx:07d}",
                    "protein_id": "",
                    "gene_symbol": gene.name or "",
                    "orf_id": gene.id,
                    "organism": "Saccharomyces cerevisiae",
                    "ec_numbers": "",
                    "reaction_uid": reaction_uid_by_id.get(rxn.id, ""),
                    "model_reaction_id": rxn.id,
                    "evidence_source": "Yeast-MetaTwin GPR",
                    "evidence_record_id": f"{rxn.id}:{gene.id}",
                    "prediction_model": "",
                    "prediction_score": "",
                    "evidence_type": "model_gpr",
                    "confidence_level": "high" if not rxn.id.startswith("rxn") else "medium",
                    "notes": "Model GPR evidence; underground rxn* assignments should be reviewed before training use.",
                }
            )
            idx += 1
    return rows


def render_report(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 2 Seed Table Build",
            "",
            f"Generated: {payload['generated_at']}",
            "",
            "## Outputs",
            "",
            f"- `02_id_mapping/model_compound_seed.csv`: {payload['compound_rows']} rows",
            f"- `02_id_mapping/model_reaction_seed.csv`: {payload['reaction_rows']} rows",
            f"- `02_id_mapping/model_enzyme_evidence_seed.csv`: {payload['enzyme_evidence_rows']} rows",
            "",
            "## Notes",
            "",
            "These seed tables are extracted from Yeast-MetaTwin and use internal stable IDs. External database IDs, SMILES, InChIKey, EC numbers, and curated evidence should be filled in subsequent normalization steps.",
        ]
    ) + "\n"


def main() -> None:
    config = load_config()
    model = cobra.io.load_yaml_model(config["models"]["yeast_metatwin"])
    compounds = build_compounds(model)
    compound_uid_by_id = {row["model_metabolite_id"]: row["compound_uid"] for row in compounds}
    reactions = build_reactions(model, compound_uid_by_id)
    reaction_uid_by_id = {row["model_reaction_id"]: row["reaction_uid"] for row in reactions}
    enzyme_evidence = build_enzyme_evidence(model, reaction_uid_by_id)

    write_csv(
        OUT_DIR / "model_compound_seed.csv",
        compounds,
        [
            "compound_uid", "model_metabolite_id", "primary_name", "formula", "charge", "compartment", "smiles", "inchikey",
            "kegg_id", "chebi_id", "metanetx_id", "source_database", "source_record_id", "confidence_level", "notes",
        ],
    )
    write_csv(
        OUT_DIR / "model_reaction_seed.csv",
        reactions,
        [
            "reaction_uid", "model_reaction_id", "primary_name", "equation", "reactant_compound_uids", "product_compound_uids",
            "stoichiometry_json", "direction", "lower_bound", "upper_bound", "genes", "orfs", "gpr", "is_underground_rxn_prefix",
            "source_database", "source_record_id", "evidence_type", "confidence_score", "notes",
        ],
    )
    write_csv(
        OUT_DIR / "model_enzyme_evidence_seed.csv",
        enzyme_evidence,
        [
            "enzyme_uid", "protein_id", "gene_symbol", "orf_id", "organism", "ec_numbers", "reaction_uid", "model_reaction_id",
            "evidence_source", "evidence_record_id", "prediction_model", "prediction_score", "evidence_type", "confidence_level", "notes",
        ],
    )

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "compound_rows": len(compounds),
        "reaction_rows": len(reactions),
        "enzyme_evidence_rows": len(enzyme_evidence),
    }
    EVAL_DIR.mkdir(exist_ok=True)
    (EVAL_DIR / "phase2_seed_table_build.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_seed_table_build.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_seed_table_build.md")


if __name__ == "__main__":
    main()
