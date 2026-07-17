from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERIC_RUNTIME = ROOT / "10_generic_target_workflow" / "runtime"
CONFIG = ROOT / "10_generic_target_workflow" / "examples" / "target_workflow_10h2da_reference.json"
LOCAL_EVIDENCE = ROOT / "06_evaluation" / "10h2da_external_evidence_supplement.json"
if str(GENERIC_RUNTIME) not in sys.path:
    sys.path.insert(0, str(GENERIC_RUNTIME))

from executors import CobraFbaExecutor  # noqa: E402


def _stable_ids(record: dict[str, Any]) -> dict[str, str]:
    raw = record.get("record", "")
    accession = ""
    pmid = ""
    rhea = ""
    try:
        parsed = json.loads(raw)
        accession = str(parsed.get("primaryAccession", ""))
        pmid = str(parsed.get("uid", "")) if record.get("source") == "PubMed" else ""
    except (TypeError, json.JSONDecodeError):
        pass
    if not accession:
        match = re.search(r'"primaryAccession"\s*:\s*"([A-Z0-9]+)"', raw)
        accession = match.group(1) if match else ""
    if not pmid:
        match = re.search(r'"uid"\s*:\s*"(\d+)"', raw)
        pmid = match.group(1) if match and record.get("source") == "PubMed" else ""
    match = re.search(r"RHEA:(\d+)", raw)
    rhea = f"RHEA:{match.group(1)}" if match else ""
    return {"uniprot_accession": accession, "pmid": pmid, "rhea_id": rhea}


def structured_evidence(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    source = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    seen = set()
    for record in source.get("records", []):
        ids = _stable_ids(record)
        if not any(ids.values()):
            continue
        key = (record["candidate_reaction_id"], record["source"], *ids.values())
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "candidate_reaction_id": record["candidate_reaction_id"],
            "source": record["source"],
            "evidence_tier": record["evidence_tier"],
            **ids,
            "exact_terminal_reaction": "no",
            "manual_review_status": "pending",
            "review_note": "",
        })
    return rows


def render_review_template(rows: list[dict[str, str]]) -> str:
    candidates = sorted({row["candidate_reaction_id"] for row in rows})
    lines = [
        "# 10H2DA Terminal Evidence Manual Review",
        "",
        "Computational status: stoichiometry and model feasibility are separate from enzymatic validation.",
        "No candidate may be promoted until an exact substrate, product, direction, enzyme and assay are reviewed.",
        "",
        "| Candidate | Reviewer | Date | Accession/PMID/Rhea checked | Exact reaction? | Assay supports activity? | Decision | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for candidate in candidates:
        lines.append(f"| {candidate} |  |  |  | no | no | blocked |  |")
    lines.extend([
        "",
        "## Sign-off",
        "",
        "Reviewer: ",
        "",
        "Review date: ",
        "",
        "Decision: blocked / accepted_for_prioritization / exact_enzyme_validated",
        "",
        "Rationale: ",
    ])
    return "\n".join(lines) + "\n"


def build(output_dir: Path, config_path: Path = CONFIG, evidence_path: Path = LOCAL_EVIDENCE) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    fba = CobraFbaExecutor().execute(config, ROOT, output_dir / "model_feasibility")
    evidence = structured_evidence(evidence_path)
    exact = [row for row in evidence if row["exact_terminal_reaction"] == "yes"]
    artifact = {
        "schema_version": "1.0",
        "target_id": config["target"]["target_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "claims": {
            "stoichiometric_feasibility": "reported_per_route",
            "model_feasibility": "reported_per_route",
            "enzymatic_validation": "blocked" if not exact else "manual_review_required",
        },
        "model_analysis": fba,
        "external_evidence": {
            "source": str(evidence_path.relative_to(ROOT)) if evidence_path.is_relative_to(ROOT) else evidence_path.name,
            "stable_identifier_records": len(evidence),
            "exact_terminal_reaction_records": len(exact),
            "status": "blocked" if not exact else "manual_review_required",
            "reason": "no exact external terminal-reaction evidence with enzyme specificity" if not exact else "exact candidates require manual verification",
        },
        "experimental_blockers": [
            "exact substrate-specific omega-hydroxylase activity has not been demonstrated",
            "exact hydroxy-enoyl-CoA thioesterase activity has not been demonstrated",
            "in vivo 10H2DA production, titre, yield and oxygen response require measurement",
        ],
    }
    (output_dir / "validation_artifact.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    fields = ["candidate_reaction_id", "source", "evidence_tier", "uniprot_accession", "pmid", "rhea_id", "exact_terminal_reaction", "manual_review_status", "review_note"]
    with (output_dir / "evidence_accessions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(evidence)
    (output_dir / "manual_review.md").write_text(render_review_template(evidence), encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a non-destructive 10H2DA validation artifact")
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory; existing paths are refused")
    args = parser.parse_args()
    artifact = build(args.output_dir.resolve())
    print(json.dumps({"output_dir": str(args.output_dir.resolve()), "enzymatic_validation": artifact["claims"]["enzymatic_validation"]}))


if __name__ == "__main__":
    main()
