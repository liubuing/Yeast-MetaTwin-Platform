from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "06_evaluation"
REPORT_DIR = ROOT / "07_reports"

QUERIES = [
    {
        "candidate_reaction_id": "CAND_T2DEC_OMEGA_HYDROXYLASE_P",
        "reaction_role": "free_acid_omega_hydroxylation",
        "exact_terms": ["10-hydroxy-trans-2-decenoic acid", "10-hydroxy-2-decenoic acid", "10H2DA", "10-HDA"],
        "near_terms": ["trans-2-decenoic acid", "2-decenoic acid", "decenoic acid", "decanoic acid"],
        "family_terms": ["omega hydroxylase", "omega-hydroxylase", "cytochrome P450", "CYP52", "fatty acid hydroxylase"],
    },
    {
        "candidate_reaction_id": "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P",
        "reaction_role": "coa_bound_omega_hydroxylation",
        "exact_terms": ["10-hydroxy-trans-2-decenoyl-CoA", "10-hydroxy-2-decenoyl-CoA"],
        "near_terms": ["trans-dec-2-enoyl-CoA", "dec-2-enoyl-CoA", "decenoyl-CoA", "decanoyl-CoA"],
        "family_terms": ["omega hydroxylase", "omega-hydroxylase", "cytochrome P450", "CYP52", "fatty acyl-CoA hydroxylase"],
    },
    {
        "candidate_reaction_id": "CAND_T2DEC_THIOESTERASE_P",
        "reaction_role": "enoyl_coa_thioesterase_release",
        "exact_terms": ["trans-dec-2-enoyl-CoA thioesterase", "trans-2-decenoyl-CoA thioesterase"],
        "near_terms": ["decenoyl-CoA thioesterase", "decanoyl-CoA thioesterase", "acyl-CoA thioesterase", "enoyl-CoA thioesterase"],
        "family_terms": ["thioesterase", "acyl-CoA hydrolase", "TES1"],
    },
    {
        "candidate_reaction_id": "CAND_10H2DA_COA_THIOESTERASE_P",
        "reaction_role": "hydroxy_enoyl_coa_thioesterase_release",
        "exact_terms": ["10-hydroxy-trans-2-decenoyl-CoA thioesterase", "10-hydroxy-2-decenoyl-CoA thioesterase"],
        "near_terms": ["hydroxy decenoyl-CoA thioesterase", "hydroxy acyl-CoA thioesterase", "decanoyl-CoA thioesterase"],
        "family_terms": ["thioesterase", "acyl-CoA hydrolase", "TES1"],
    },
]


def fetch_text(url: str, timeout: int = 30) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Yeast-MetaTwin evidence audit"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def evidence_tier(text: str, query: dict[str, Any]) -> str:
    low = text.lower()
    exact = any(term.lower() in low for term in query["exact_terms"])
    near = any(term.lower() in low for term in query["near_terms"])
    family = any(term.lower() in low for term in query["family_terms"])
    role = query["reaction_role"]
    if "omega_hydroxylation" in role:
        role_specific = any(term in low for term in ["omega", "hydroxylase", "monooxygenase", "cytochrome p450", "cyp52", "hydroxylation"])
    elif "thioesterase" in role:
        role_specific = any(term in low for term in ["thioesterase", "acyl-coa hydrolase", "enoyl-coa hydrolase"])
    else:
        role_specific = False
    if exact and role_specific and ("reaction" in low or "catalytic" in low or "activity" in low or "enzyme" in low):
        return "A_exact_substrate_or_reaction_candidate"
    if exact:
        return "B_exact_compound_context_no_enzyme_specificity"
    if near and family:
        return "C_near_substrate_enzyme_family"
    if family:
        return "D_enzyme_family_only"
    if near:
        return "D_near_substrate_only"
    return "E_keyword_context_only"


def search_uniprot(query: dict[str, Any]) -> list[dict[str, Any]]:
    terms = query["exact_terms"] + query["near_terms"] + query["family_terms"]
    search = " OR ".join(f'"{term}"' for term in terms)
    url = "https://rest.uniprot.org/uniprotkb/search?" + urllib.parse.urlencode(
        {
            "query": search,
            "format": "json",
            "size": "10",
            "fields": "accession,id,protein_name,gene_names,organism_name,cc_catalytic_activity,ec",
        }
    )
    status, text = fetch_text(url)
    records = []
    if status != 200:
        return [error_record(query, "UniProt", url, status, text)]
    data = json.loads(text)
    for item in data.get("results", []):
        record_text = json.dumps(item, ensure_ascii=False)
        records.append(base_record(query, "UniProt", url, evidence_tier(record_text, query), record_text[:3000]))
    return records


def search_rhea(query: dict[str, Any]) -> list[dict[str, Any]]:
    terms = query["exact_terms"] + query["near_terms"]
    records = []
    for term in terms[:6]:
        url = "https://www.rhea-db.org/rhea?" + urllib.parse.urlencode({"query": term, "columns": "rhea-id,equation,ec", "format": "tsv"})
        status, text = fetch_text(url)
        if status != 200:
            records.append(error_record(query, "Rhea", url, status, text))
            continue
        lines = [line for line in text.splitlines() if line.strip()]
        for line in lines[1:11]:
            records.append(base_record(query, "Rhea", url, evidence_tier(line, query), line[:3000]))
        time.sleep(0.2)
    return records


def search_pubmed(query: dict[str, Any]) -> list[dict[str, Any]]:
    terms = query["exact_terms"] + [" ".join([query["near_terms"][0], query["family_terms"][0]])]
    records = []
    for term in terms[:5]:
        esearch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "term": term, "retmode": "json", "retmax": "5"})
        status, text = fetch_text(esearch)
        if status != 200:
            records.append(error_record(query, "PubMed", esearch, status, text))
            continue
        ids = json.loads(text).get("esearchresult", {}).get("idlist", [])
        if not ids:
            continue
        esummary = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
        s2, t2 = fetch_text(esummary)
        if s2 != 200:
            records.append(error_record(query, "PubMed", esummary, s2, t2))
            continue
        data = json.loads(t2).get("result", {})
        for pmid in ids:
            item = data.get(pmid, {})
            text_record = json.dumps(item, ensure_ascii=False)
            records.append(base_record(query, "PubMed", esummary, evidence_tier(text_record, query), text_record[:3000]))
        time.sleep(0.2)
    return records


def base_record(query: dict[str, Any], source: str, url: str, tier: str, record: str) -> dict[str, Any]:
    return {
        "candidate_reaction_id": query["candidate_reaction_id"],
        "reaction_role": query["reaction_role"],
        "source": source,
        "evidence_tier": tier,
        "url": url,
        "record": record.replace("\r", " ").replace("\n", " "),
    }


def error_record(query: dict[str, Any], source: str, url: str, status: int, text: str) -> dict[str, Any]:
    return base_record(query, source, url, "Z_query_error", f"status={status}; {text[:1000]}")


def verdict_for(candidate: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    order = [
        "A_exact_substrate_or_reaction_candidate",
        "B_exact_compound_context_no_enzyme_specificity",
        "C_near_substrate_enzyme_family",
        "D_enzyme_family_only",
        "D_near_substrate_only",
        "E_keyword_context_only",
        "Z_query_error",
    ]
    subset = [row for row in rows if row["candidate_reaction_id"] == candidate]
    tiers = {row["evidence_tier"] for row in subset}
    best = next((tier for tier in order if tier in tiers), "no_external_record_found")
    if best.startswith("A"):
        action = "candidate_can_be_promoted_after_manual_curation"
    elif best.startswith("B") or best.startswith("C"):
        action = "candidate_supported_for_prioritization_not_curated_promotion"
    elif best.startswith("D") or best.startswith("E"):
        action = "enzyme_class_or_keyword_support_only"
    else:
        action = "no_usable_external_support"
    return {"candidate_reaction_id": candidate, "best_evidence_tier": best, "records": len(subset), "recommended_action": action}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# 10H2DA External Evidence Supplement",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Evidence Tier Definitions",
        "",
        "| Tier | Meaning |",
        "|---|---|",
        "| A | Exact substrate or exact reaction candidate with enzyme/reaction context |",
        "| B | Exact target compound context but no enzyme-specific terminal reaction |",
        "| C | Near substrate plus enzyme-family evidence |",
        "| D | Enzyme-family-only or near-substrate-only evidence |",
        "| E | Weak keyword context only |",
        "| Z | Query error |",
        "",
        "## Candidate Verdicts",
        "",
        "| Candidate | Best tier | Records | Recommended action |",
        "|---|---|---:|---|",
    ]
    for row in payload["candidate_verdicts"]:
        lines.append(f"| {row['candidate_reaction_id']} | {row['best_evidence_tier']} | {row['records']} | {row['recommended_action']} |")
    lines.extend(["", "## Source Counts", "", "| Source | Records |", "|---|---:|"])
    for source, count in payload["source_counts"].items():
        lines.append(f"| {source} | {count} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "External records are kept separate from model/FBA/PU evidence. Only tier A should be considered for curated reaction promotion after manual review. Lower tiers are prioritization evidence only.",
            "",
            "## Outputs",
            "",
            "- `06_evaluation/10h2da_external_evidence_records.csv`",
            "- `06_evaluation/10h2da_external_evidence_verdicts.csv`",
            "- `06_evaluation/10h2da_external_evidence_supplement.json`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    rows: list[dict[str, Any]] = []
    for query in QUERIES:
        rows.extend(search_uniprot(query))
        rows.extend(search_rhea(query))
        rows.extend(search_pubmed(query))
    verdicts = [verdict_for(query["candidate_reaction_id"], rows) for query in QUERIES]
    source_counts = {source: sum(1 for row in rows if row["source"] == source) for source in sorted({row["source"] for row in rows})}
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_verdicts": verdicts,
        "source_counts": source_counts,
        "record_count": len(rows),
    }
    write_csv(EVAL_DIR / "10h2da_external_evidence_records.csv", rows, ["candidate_reaction_id", "reaction_role", "source", "evidence_tier", "url", "record"])
    write_csv(EVAL_DIR / "10h2da_external_evidence_verdicts.csv", verdicts, ["candidate_reaction_id", "best_evidence_tier", "records", "recommended_action"])
    (EVAL_DIR / "10h2da_external_evidence_supplement.json").write_text(json.dumps({**payload, "records": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORT_DIR / "10H2DA_external_evidence_supplement.md").write_text(render_report(payload), encoding="utf-8")
    print(REPORT_DIR / "10H2DA_external_evidence_supplement.md")


if __name__ == "__main__":
    main()
