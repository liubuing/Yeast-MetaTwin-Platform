from __future__ import annotations

import csv
import json
import math
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


def load_rxndb(source_project: Path) -> tuple[dict[str, Any], str]:
    candidates = [
        source_project / "Data_retrosynthesis" / "not_lipid" / "top50_0.3_add_no_ec_re" / "RXNdb_all_top50_0.3.json",
        source_project / "Data_retrosynthesis" / "not_lipid" / "top50_0.3_re" / "RXNdb_all_top50_0.3.json",
        source_project / "Data_retrosynthesis" / "yeast8_recovery" / "top50_0.3" / "RXNdb_all_top50_0.3.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), str(path)
    raise FileNotFoundError("No RXNdb_all_top50_0.3.json candidate found")


def join_value(value: Any) -> str:
    if is_blank(value):
        return ""
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:2000]
    return str(value)


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null"}:
        return True
    return False


def build_rows(rxndb: dict[str, Any], rxndb_source: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    crossrefs = pd.read_csv(MAP_DIR / "model_reaction_crossrefs.csv", dtype=str).fillna("")
    underground = crossrefs[crossrefs["is_underground_rxn_prefix"].astype(str) == "True"]
    rows: list[dict[str, Any]] = []
    mapped = 0
    with_template = 0
    with_basic = 0
    with_final = 0
    with_ec = 0
    for _, row in underground.iterrows():
        rid = row["model_reaction_id"]
        record = rxndb.get(rid)
        if record:
            mapped += 1
            with_template += int(not is_blank(record.get("templateID")))
            with_basic += int(not is_blank(record.get("rxn_smiles_basic")))
            with_final += int(not is_blank(record.get("rxn_smiles_final")))
            with_ec += int(not is_blank(record.get("EC number")))
        else:
            record = {}
        rows.append(
            {
                "reaction_uid": row["reaction_uid"],
                "model_reaction_id": rid,
                "reaction_name": row["reaction_name"],
                "model_equation": row["model_equation"],
                "rxndb_direct_match": bool(record),
                "rxndb_source": rxndb_source if record else "",
                "rxndb_id": rid if record else "",
                "ec_number": join_value(record.get("EC number")),
                "template_id": join_value(record.get("templateID")),
                "template_substrate": join_value(record.get("templateSubstrate")),
                "reactant_smile": join_value(record.get("reactant_smile")),
                "product_smile": join_value(record.get("productsmile")),
                "rxn_smiles_basic": join_value(record.get("rxn_smiles_basic")),
                "rxn_smiles_final": join_value(record.get("rxn_smiles_final")),
                "similarity": join_value(record.get("similarity")),
                "rule": join_value(record.get("rule"))[:2000],
                "provenance_status": "rxndb_direct_match" if record else "missing_in_selected_rxndb",
                "notes": "Direct top-level RXNdb key matched model rxn* ID." if record else "No direct key match in selected RXNdb file.",
            }
        )
    summary = {
        "underground_rows": len(underground),
        "rxndb_direct_matches": mapped,
        "with_template_id": with_template,
        "with_rxn_smiles_basic": with_basic,
        "with_rxn_smiles_final": with_final,
        "with_ec_number": with_ec,
        "missing_direct_match": len(underground) - mapped,
        "rxndb_source": rxndb_source,
        "rxndb_total_records": len(rxndb),
    }
    return rows, summary


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    s = payload["summary"]
    underground_rows = max(int(s["underground_rows"]), 1)
    direct_pct = int(s["rxndb_direct_matches"]) / underground_rows * 100
    ec_pct = int(s["with_ec_number"]) / underground_rows * 100
    return "\n".join(
        [
            "# Phase 2 Underground rxn* Provenance Mapping",
            "",
            f"Generated: {payload['generated_at']}",
            f"RXNdb source: `{s['rxndb_source']}`",
            "",
            "## Coverage",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Underground rxn* model reactions | {s['underground_rows']} |",
            f"| RXNdb direct matches | {s['rxndb_direct_matches']} ({direct_pct:.2f}%) |",
            f"| Missing direct matches | {s['missing_direct_match']} |",
            f"| RXNdb total records | {s['rxndb_total_records']} |",
            f"| With template ID | {s['with_template_id']} |",
            f"| With rxn_smiles_basic | {s['with_rxn_smiles_basic']} |",
            f"| With rxn_smiles_final | {s['with_rxn_smiles_final']} |",
            f"| With EC number | {s['with_ec_number']} ({ec_pct:.2f}%) |",
            "",
            "## Output",
            "",
            "- `02_id_mapping/model_underground_rxn_provenance.csv`",
            "",
            "## Interpretation",
            "",
            "A direct match means the model `rxn*` ID exists as a top-level key in the selected RXNdb file. This provides retrosynthesis provenance fields such as template ID, EC number, reaction SMILES, and similarity scores. These are still prediction/provenance records, not curated biochemical validation.",
        ]
    ) + "\n"


def main() -> None:
    config = load_config()
    source_project = Path(config["source_project_dir"])
    rxndb, source = load_rxndb(source_project)
    rows, summary = build_rows(rxndb, source)
    out = MAP_DIR / "model_underground_rxn_provenance.csv"
    write_csv(out, rows)
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "summary": summary, "output": str(out)}
    (EVAL_DIR / "phase2_rxn_provenance.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_rxn_provenance.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_rxn_provenance.md")


if __name__ == "__main__":
    main()
