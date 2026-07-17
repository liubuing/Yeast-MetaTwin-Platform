from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import cobra
import pandas as pd
from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "09_configs" / "deployment_config.json"
MAP_DIR = ROOT / "02_id_mapping"
EVAL_DIR = ROOT / "06_evaluation"


def load_config() -> dict[str, Any]:
    return load_deployment_config()


def as_pipe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return str(value)


def load_mnx_reactions(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, sep="\t", dtype=str).fillna("")
    return {row["ID"]: row.to_dict() for _, row in df.iterrows() if row.get("ID")}


def build_crossrefs(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = Path(config["source_project_dir"])
    model = cobra.io.load_yaml_model(config["models"]["yeast_metatwin"])
    reaction_seed = pd.read_csv(MAP_DIR / "model_reaction_seed.csv", dtype=str).fillna("")
    reaction_uid_by_id = dict(zip(reaction_seed["model_reaction_id"], reaction_seed["reaction_uid"]))
    mnx = load_mnx_reactions(source / "Data" / "database" / "MNX_reac_prop.tsv")

    rows: list[dict[str, Any]] = []
    for rxn in sorted(model.reactions, key=lambda item: item.id):
        ann = rxn.annotation or {}
        mnx_id = as_pipe(ann.get("metanetx.reaction"))
        mnx_primary = mnx_id.split("|")[0] if mnx_id else ""
        mnx_row = mnx.get(mnx_primary, {}) if mnx_primary else {}
        kegg_reaction = as_pipe(ann.get("kegg.reaction"))
        kegg_pathway = as_pipe(ann.get("kegg.pathway"))
        bigg = as_pipe(ann.get("bigg.reaction"))
        sbo = as_pipe(ann.get("sbo"))
        rows.append(
            {
                "reaction_uid": reaction_uid_by_id.get(rxn.id, ""),
                "model_reaction_id": rxn.id,
                "reaction_name": rxn.name or rxn.id,
                "is_underground_rxn_prefix": rxn.id.startswith("rxn"),
                "model_equation": rxn.reaction,
                "metanetx_reaction_id": mnx_id,
                "kegg_reaction_id": kegg_reaction,
                "kegg_pathway_ids": kegg_pathway,
                "bigg_reaction_id": bigg,
                "sbo_id": sbo,
                "mnx_equation": mnx_row.get("mnx_equation", ""),
                "mnx_reference": mnx_row.get("reference", ""),
                "mnx_classifs": mnx_row.get("classifs", ""),
                "mnx_is_balanced": mnx_row.get("is_balanced", ""),
                "mnx_is_transport": mnx_row.get("is_transport", ""),
                "crossref_status": crossref_status(rxn.id, mnx_id, kegg_reaction, bigg),
                "notes": "rxn* underground reactions require RXNdb/retrosynthesis mapping" if rxn.id.startswith("rxn") and not mnx_id else "",
            }
        )

    summary = {
        "rows": len(rows),
        "underground_rxn_prefix": sum(1 for row in rows if row["is_underground_rxn_prefix"]),
        "metanetx_nonempty": sum(1 for row in rows if row["metanetx_reaction_id"]),
        "metanetx_with_property_match": sum(1 for row in rows if row["mnx_equation"]),
        "kegg_reaction_nonempty": sum(1 for row in rows if row["kegg_reaction_id"]),
        "kegg_pathway_nonempty": sum(1 for row in rows if row["kegg_pathway_ids"]),
        "bigg_nonempty": sum(1 for row in rows if row["bigg_reaction_id"]),
        "sbo_nonempty": sum(1 for row in rows if row["sbo_id"]),
        "underground_without_crossref": sum(
            1 for row in rows if row["is_underground_rxn_prefix"] and row["crossref_status"] == "no_external_crossref"
        ),
    }
    return rows, summary


def crossref_status(model_reaction_id: str, mnx_id: str, kegg_reaction: str, bigg: str) -> str:
    if mnx_id or kegg_reaction or bigg:
        return "has_external_crossref"
    if model_reaction_id.startswith("rxn"):
        return "no_external_crossref"
    return "model_only_no_external_crossref"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    s = payload["summary"]
    return "\n".join(
        [
            "# Phase 2 Reaction Cross-Reference Build",
            "",
            f"Generated: {payload['generated_at']}",
            "",
            "## Coverage",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Total model reactions | {s['rows']} |",
            f"| Underground rxn* reactions | {s['underground_rxn_prefix']} |",
            f"| MetaNetX cross-reference non-empty | {s['metanetx_nonempty']} |",
            f"| MetaNetX property match | {s['metanetx_with_property_match']} |",
            f"| KEGG reaction non-empty | {s['kegg_reaction_nonempty']} |",
            f"| KEGG pathway non-empty | {s['kegg_pathway_nonempty']} |",
            f"| BiGG reaction non-empty | {s['bigg_nonempty']} |",
            f"| SBO non-empty | {s['sbo_nonempty']} |",
            f"| Underground rxn* without external cross-reference | {s['underground_without_crossref']} |",
            "",
            "## Output",
            "",
            "- `02_id_mapping/model_reaction_crossrefs.csv`",
            "",
            "## Notes",
            "",
            "This cross-reference table uses existing model annotations first. Most underground `rxn*` reactions do not carry direct annotation and require a later RXNdb/retrosynthesis mapping pass using reaction signatures or provenance records.",
        ]
    ) + "\n"


def main() -> None:
    config = load_config()
    rows, summary = build_crossrefs(config)
    out = MAP_DIR / "model_reaction_crossrefs.csv"
    write_csv(out, rows)
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "summary": summary, "output": str(out)}
    (EVAL_DIR / "phase2_reaction_crossrefs.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_reaction_crossrefs.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_reaction_crossrefs.md")


if __name__ == "__main__":
    main()
