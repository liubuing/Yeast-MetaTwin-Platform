from __future__ import annotations

import csv
import json
import math
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "06_evaluation"
REPORT_DIR = ROOT / "07_reports"
RUNTIME_DIR = ROOT / "08_runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

import predict_10h2da_unikp_and_evidence_matrix as unikp_run  # noqa: E402
import __main__  # noqa: E402

setattr(__main__, "WordVocab", unikp_run.build_vocab.WordVocab)


EXTERNAL_ACCESSION_LIMIT = 12
HYDROXYLASE_REACTIONS = {"CAND_T2DEC_OMEGA_HYDROXYLASE_P", "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P"}
CURATED_EXTERNAL_CANDIDATES = [
    {"entry": "B8QHP1", "gene_names": "cyp52M1", "protein_names": "Cytochrome P450 52-M1; fatty acid omega-hydroxylase", "ec_number": "1.14.14.80", "organism": "Starmerella bombicola", "tier": "D_enzyme_family_only", "note": "CYP52 yeast fatty-acid omega-hydroxylase evidence record"},
    {"entry": "Q9Y8G7", "gene_names": "cyp505", "protein_names": "Bifunctional cytochrome P450/NADPH--P450 reductase; P450foxy; fatty acid omega-hydroxylase", "ec_number": "1.14.14.1", "organism": "Fusarium oxysporum", "tier": "D_enzyme_family_only", "note": "self-sufficient fungal P450/P450 reductase evidence record"},
    {"entry": "Q6NT55", "gene_names": "CYP4F22", "protein_names": "Ultra-long-chain fatty acid omega-hydroxylase; Cytochrome P450 4F22", "ec_number": "1.14.14.177", "organism": "Homo sapiens", "tier": "D_enzyme_family_only", "note": "fatty-acid omega-hydroxylase evidence record"},
    {"entry": "Q08477", "gene_names": "CYP4F3", "protein_names": "Cytochrome P450 4F3; 20-hydroxyeicosatetraenoic acid synthase", "ec_number": "1.14.14.1", "organism": "Homo sapiens", "tier": "D_enzyme_family_only", "note": "CYP4F fatty-acid hydroxylation evidence record"},
    {"entry": "P78329", "gene_names": "CYP4F2", "protein_names": "Cytochrome P450 4F2; 20-hydroxyeicosatetraenoic acid synthase", "ec_number": "1.14.14.1", "organism": "Homo sapiens", "tier": "D_enzyme_family_only", "note": "CYP4F fatty-acid hydroxylation evidence record"},
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def all_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return fields


def text_of(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(key, "")) for key in ["gene_names", "protein_names", "ec_number", "entry", "organism", "substrate_name"]).lower()


def classify_family(row: dict[str, Any]) -> tuple[str, str, int]:
    text = text_of(row)
    reaction_id = row.get("candidate_reaction_id", "")
    if reaction_id in HYDROXYLASE_REACTIONS:
        if any(term in text for term in ["cyclophilin", "ppiase", "rotamase", "transcription factor", "cytochrome c", "p450 reductase", "nadph--cytochrome p450 reductase"]):
            return "weak_name_or_cofactor_hit", "name/cofactor hit is not a terminal hydroxylase family", 1
        if any(term in text for term in ["cyp52", "cytochrome p450 52", "fatty acid omega", "omega-hydroxylase", "omega monooxygenase", "long-chain fatty acid omega"]):
            return "preferred_omega_hydroxylase", "fatty-acid omega-hydroxylase/P450 family", 5
        if any(term in text for term in ["p450", "cytochrome p450", "cyp4", "cyp51", "cyp56", "cyp61"]):
            return "plausible_p450_or_cyp", "P450/CYP family but exact C10 substrate unvalidated", 4
        if any(term in text for term in ["monooxygenase", "hydroxylase", "oxygenase", "epoxidase", "fmo1", "coq6", "scs7", "sur2"]):
            return "plausible_oxygenase", "oxygenase/hydroxylase family support", 3
        return "low_specificity_oxygenase_hit", "oxygenase query hit but family specificity is weak", 2
    if "thioesterase" in text or "acyl-coenzyme a thioester" in text or "acyl-coa thioester" in text or "pte1" in text or "tes1" in text:
        if any(term in text for term in ["tes1", "pte1", "peroxisomal acyl-coenzyme a thioester hydrolase", "long-chain acyl-coa thioesterase"]):
            return "preferred_acyl_coa_thioesterase", "TES1/PTE1-like acyl-CoA thioesterase", 5
        if any(term in text for term in ["eat1", "acetyl-coa hydrolase", "probable thioesterase", "palmitoyl-protein hydrolase", "acyl-protein thioesterase"]):
            return "plausible_thioesterase", "thioesterase-like enzyme but exact substrate unvalidated", 4
        if "ubiquitin" in text or "deubiquitinating" in text:
            return "weak_ubiquitin_thioesterase", "ubiquitin/protein thioesterase, weak fit for acyl-CoA release", 1
        return "generic_thioesterase", "thioesterase-class support", 3
    return "weak_family_match", "family does not cleanly match terminal reaction", 1


def engineering_score(row: dict[str, Any]) -> float:
    _, _, sanity = classify_family(row)
    score = sanity * 2.0
    score += float(row.get("unikp_log10_kcat_Km", 0.0))
    score += float(row.get("pu_reference_likeness_score", 0.0))
    score += min(float(row.get("best_candidate_fba_flux", 0.0)), 0.4)
    if str(row.get("candidate_origin", "")).startswith("external_uniprot"):
        score += 1.0
    tier = row.get("external_evidence_tier", "")
    if tier.startswith("B_"):
        score += 0.7
    elif tier.startswith("C_"):
        score += 0.4
    elif tier.startswith("D_"):
        score += 0.2
    return score


def annotate_rows(rows: list[dict[str, Any]], origin: str) -> list[dict[str, Any]]:
    annotated = []
    for row in rows:
        out = dict(row)
        out["candidate_origin"] = out.get("candidate_origin", origin)
        family, reason, sanity = classify_family(out)
        out["enzyme_family_sanity_class"] = family
        out["enzyme_family_sanity_reason"] = reason
        out["enzyme_family_sanity_score"] = sanity
        out["engineering_priority_score"] = engineering_score(out)
        annotated.append(out)
    return annotated


def extract_name(value: dict[str, Any]) -> str:
    try:
        return value["value"]
    except Exception:
        return ""


def parse_uniprot_record(record_text: str) -> dict[str, Any] | None:
    try:
        record = json.loads(record_text)
    except json.JSONDecodeError:
        return None
    accession = record.get("primaryAccession", "")
    if not accession:
        return None
    organism = record.get("organism", {}).get("scientificName", "")
    genes = []
    for gene in record.get("genes", []):
        name = gene.get("geneName", {}).get("value", "")
        if name:
            genes.append(name)
    protein_desc = record.get("proteinDescription", {})
    names = []
    rec_name = protein_desc.get("recommendedName", {}).get("fullName", {})
    if rec_name:
        names.append(extract_name(rec_name))
    for alt in protein_desc.get("alternativeNames", []):
        full = alt.get("fullName", {})
        if full:
            names.append(extract_name(full))
    ec_numbers = []
    for block in [protein_desc.get("recommendedName", {})] + protein_desc.get("alternativeNames", []):
        for ec in block.get("ecNumbers", []):
            value = ec.get("value", "")
            if value and value not in ec_numbers:
                ec_numbers.append(value)
    return {
        "entry": accession,
        "orf": accession,
        "gene_names": " ".join(genes),
        "protein_names": "; ".join(name for name in names if name),
        "ec_number": "; ".join(ec_numbers),
        "organism": organism,
    }


def fetch_fasta_sequence(accession: str) -> str:
    url = f"https://rest.uniprot.org/uniprotkb/{accession}.fasta"
    with urllib.request.urlopen(url, timeout=60) as response:
        text = response.read().decode("utf-8")
    return "".join(line.strip() for line in text.splitlines() if line and not line.startswith(">"))


def collect_external_hydroxylase_inputs() -> list[dict[str, Any]]:
    records = read_csv(EVAL_DIR / "10h2da_external_evidence_records.csv")
    reactions = {row["model_reaction_id"]: row for row in read_csv(EVAL_DIR / "10h2da_terminal_candidate_pu_v2_scores.csv")}
    collected: dict[tuple[str, str], dict[str, Any]] = {}
    for row in records:
        reaction_id = row.get("candidate_reaction_id", "")
        if reaction_id not in HYDROXYLASE_REACTIONS or row.get("source") != "UniProt":
            continue
        parsed = parse_uniprot_record(row.get("record", ""))
        if not parsed:
            continue
        protein_text = f"{parsed['gene_names']} {parsed['protein_names']} {parsed['ec_number']} {parsed['organism']}".lower()
        if not any(term in protein_text for term in ["omega", "fatty acid", "p450", "cyp", "monooxygenase", "hydroxylase"]):
            continue
        key = (reaction_id, parsed["entry"])
        if key in collected:
            continue
        substrate_key, _ = unikp_run.REACTION_SUBSTRATES[reaction_id]
        substrate = unikp_run.SUBSTRATES[substrate_key]
        collected[key] = {
            "candidate_reaction_id": reaction_id,
            "reaction_name": reactions[reaction_id]["reaction_name"],
            "entry": parsed["entry"],
            "orf": parsed["orf"],
            "gene_names": parsed["gene_names"],
            "protein_names": parsed["protein_names"],
            "ec_number": parsed["ec_number"],
            "organism": parsed["organism"],
            "terminal_relevance": "external_omega_hydroxylase_support",
            "substrate_name": substrate["name"],
            "substrate_smiles": substrate["smiles"],
            "substrate_smiles_source": substrate["smiles_source"],
            "candidate_origin": "external_uniprot",
            "external_sequence_source": f"UniProtKB {parsed['entry']} FASTA",
            "external_evidence_tier": row.get("evidence_tier", "D_enzyme_family_only"),
        }
        if len(collected) >= EXTERNAL_ACCESSION_LIMIT * len(HYDROXYLASE_REACTIONS):
            break
    for curated in CURATED_EXTERNAL_CANDIDATES:
        for reaction_id in HYDROXYLASE_REACTIONS:
            key = (reaction_id, curated["entry"])
            if key in collected:
                continue
            substrate_key, _ = unikp_run.REACTION_SUBSTRATES[reaction_id]
            substrate = unikp_run.SUBSTRATES[substrate_key]
            collected[key] = {
                "candidate_reaction_id": reaction_id,
                "reaction_name": reactions[reaction_id]["reaction_name"],
                "entry": curated["entry"],
                "orf": curated["entry"],
                "gene_names": curated["gene_names"],
                "protein_names": curated["protein_names"],
                "ec_number": curated["ec_number"],
                "organism": curated["organism"],
                "terminal_relevance": "external_omega_hydroxylase_support",
                "substrate_name": substrate["name"],
                "substrate_smiles": substrate["smiles"],
                "substrate_smiles_source": substrate["smiles_source"],
                "candidate_origin": "external_uniprot_curated_panel",
                "external_sequence_source": f"UniProtKB {curated['entry']} FASTA",
                "external_evidence_tier": curated["tier"],
                "external_panel_note": curated["note"],
            }
    inputs = list(collected.values())
    for item in inputs:
        sequence = fetch_fasta_sequence(item["entry"])
        item["sequence"] = sequence
        item["sequence_length"] = len(sequence)
    return inputs


def external_predictions_to_matrix(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pu = {row["model_reaction_id"]: row for row in read_csv(EVAL_DIR / "10h2da_terminal_candidate_pu_v2_scores.csv")}
    local = {row["candidate_reaction_id"]: row for row in read_csv(EVAL_DIR / "10h2da_terminal_validation_verdicts.csv")}
    fba = unikp_run.best_flux_by_reaction()
    rows = []
    for row in predictions:
        reaction_id = row["candidate_reaction_id"]
        rows.append(
            {
                "candidate_reaction_id": reaction_id,
                "reaction_name": row["reaction_name"],
                "entry": row["entry"],
                "orf": row["orf"],
                "gene_names": row["gene_names"],
                "protein_names": row["protein_names"],
                "ec_number": row["ec_number"],
                "organism": row["organism"],
                "substrate_name": row["substrate_name"],
                "substrate_smiles_source": row["substrate_smiles_source"],
                "pu_reference_likeness_score": pu[reaction_id]["pu_reference_likeness_score"],
                "external_evidence_tier": row.get("external_evidence_tier", "D_enzyme_family_only"),
                "local_validation_verdict": local[reaction_id]["validation_verdict"],
                "local_model_support": "external enzyme candidate; not native S. cerevisiae support",
                "local_validation_reason": local[reaction_id]["reason"],
                "best_candidate_fba_flux": fba.get(reaction_id, 0.0),
                "unikp_log10_kcat": row["unikp_log10_kcat"],
                "unikp_pred_kcat": row["unikp_pred_kcat"],
                "unikp_log10_Km": row["unikp_log10_Km"],
                "unikp_pred_Km": row["unikp_pred_Km"],
                "unikp_log10_kcat_Km": row["unikp_log10_kcat_Km"],
                "unikp_pred_kcat_Km": row["unikp_pred_kcat_Km"],
                "candidate_origin": row.get("candidate_origin", "external_uniprot"),
                "external_sequence_source": row.get("external_sequence_source", ""),
                "external_panel_note": row.get("external_panel_note", ""),
            }
        )
    return rows


def design_rows(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    designs = []
    free_thio = [r for r in matrix if r["candidate_reaction_id"] == "CAND_T2DEC_THIOESTERASE_P"]
    free_hyd = [r for r in matrix if r["candidate_reaction_id"] == "CAND_T2DEC_OMEGA_HYDROXYLASE_P"]
    coa_hyd = [r for r in matrix if r["candidate_reaction_id"] == "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P"]
    coa_thio = [r for r in matrix if r["candidate_reaction_id"] == "CAND_10H2DA_COA_THIOESTERASE_P"]
    for route, first, second in [("free_acid_route", free_thio[:5], free_hyd[:5]), ("coa_bound_route", coa_hyd[:5], coa_thio[:5])]:
        for a in first:
            for b in second:
                score = (float(a["engineering_priority_score"]) + float(b["engineering_priority_score"])) / 2.0
                designs.append(
                    {
                        "route": route,
                        "step1_reaction": a["candidate_reaction_id"],
                        "step1_entry": a["entry"],
                        "step1_origin": a["candidate_origin"],
                        "step1_family": a["enzyme_family_sanity_class"],
                        "step2_reaction": b["candidate_reaction_id"],
                        "step2_entry": b["entry"],
                        "step2_origin": b["candidate_origin"],
                        "step2_family": b["enzyme_family_sanity_class"],
                        "mean_engineering_priority_score": score,
                        "route_risk_note": "external hydroxylase requires heterologous expression and redox partner handling" if any(str(origin).startswith("external_uniprot") for origin in [a["candidate_origin"], b["candidate_origin"]]) else "endogenous-only design remains weakly validated",
                    }
                )
    designs.sort(key=lambda row: -float(row["mean_engineering_priority_score"]))
    return designs


def render_report(payload: dict[str, Any], matrix: list[dict[str, Any]], designs: list[dict[str, Any]]) -> str:
    lines = [
        "# 10H2DA Engineering Candidate Prioritization",
        "",
        f"Generated: {payload['generated_at']}",
        f"Python: `{payload['python']}`",
        f"Executable: `{payload['executable']}`",
        "",
        "## Scope",
        "",
        "This report adds enzyme-family sanity filtering and external omega-hydroxylase candidates to the UniKP terminal evidence matrix. External enzyme candidates are engineering options, not native S. cerevisiae model evidence.",
        "",
        "## Outputs",
        "",
        "- `06_evaluation/10h2da_external_omega_hydroxylase_unikp_predictions.csv`",
        "- `06_evaluation/10h2da_engineering_candidate_matrix.csv`",
        "- `06_evaluation/10h2da_pathway_design_candidates.csv`",
        "",
        "## Top Engineering Candidates By Reaction",
        "",
    ]
    for reaction_id in unikp_run.REACTION_SUBSTRATES:
        subset = [row for row in matrix if row["candidate_reaction_id"] == reaction_id][:6]
        lines.extend([f"### {reaction_id}", "", "| Entry | Origin | Organism | Family class | log10 kcat/Km | Priority | Protein |", "|---|---|---|---|---:|---:|---|"])
        for row in subset:
            protein = row["protein_names"].replace("|", "/")[:70]
            organism = row.get("organism", "S. cerevisiae") or "S. cerevisiae"
            lines.append(f"| {row['entry']} | {row['candidate_origin']} | {organism} | {row['enzyme_family_sanity_class']} | {float(row['unikp_log10_kcat_Km']):.3f} | {float(row['engineering_priority_score']):.3f} | {protein} |")
        lines.append("")
    lines.extend(["## Top Pathway Designs", "", "| Route | Step 1 | Step 2 | Mean priority | Risk note |", "|---|---|---|---:|---|"])
    for row in designs[:10]:
        lines.append(f"| {row['route']} | {row['step1_entry']} ({row['step1_family']}) | {row['step2_entry']} ({row['step2_family']}) | {float(row['mean_engineering_priority_score']):.3f} | {row['route_risk_note']} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The highest engineering-priority scores favor true fatty-acid omega-hydroxylase/P450 candidates over weak endogenous keyword hits. Endogenous thioesterases remain useful route components, but exact terminal chemistry still needs biochemical validation.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    endogenous = read_csv(EVAL_DIR / "10h2da_terminal_enzyme_evidence_matrix.csv")
    for row in endogenous:
        row.setdefault("organism", "Saccharomyces cerevisiae")
    external_inputs = collect_external_hydroxylase_inputs()
    external_predictions = unikp_run.predict_unikp(external_inputs)
    external_matrix = external_predictions_to_matrix(external_predictions)
    annotated = annotate_rows(endogenous, "endogenous_s_cerevisiae") + annotate_rows(external_matrix, "external_uniprot")
    annotated.sort(key=lambda row: (row["candidate_reaction_id"], -float(row["engineering_priority_score"]), -float(row["unikp_log10_kcat_Km"])))
    designs = design_rows(annotated)

    external_pred_fields = [key for key in all_fieldnames(external_predictions) if key != "substrate_smiles"] + ["substrate_smiles"]
    write_csv(EVAL_DIR / "10h2da_external_omega_hydroxylase_unikp_predictions.csv", external_predictions, external_pred_fields)
    write_csv(EVAL_DIR / "10h2da_engineering_candidate_matrix.csv", annotated, all_fieldnames(annotated))
    write_csv(EVAL_DIR / "10h2da_pathway_design_candidates.csv", designs, list(designs[0].keys()))
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version,
        "executable": sys.executable,
        "endogenous_rows": len(endogenous),
        "external_rows": len(external_matrix),
        "combined_rows": len(annotated),
        "design_rows": len(designs),
    }
    (EVAL_DIR / "10h2da_engineering_candidate_prioritization_manifest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORT_DIR / "10H2DA_engineering_candidate_prioritization.md").write_text(render_report(payload, annotated, designs), encoding="utf-8")
    print(REPORT_DIR / "10H2DA_engineering_candidate_prioritization.md")


if __name__ == "__main__":
    main()
