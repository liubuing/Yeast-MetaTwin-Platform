from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "08_runtime"))

from enrich_compound_structures_v2 import Candidate, enrich, select_candidate  # noqa: E402


def parses(value: str) -> bool:
    return bool(value) and value != "INVALID"


def test_unique_stable_id_candidate_is_promoted_with_provenance() -> None:
    rows = [{
        "compound_uid": "C1", "model_metabolite_id": "M1", "primary_name": "unknown",
        "formula": "C2H6O", "smiles": "", "metanetx_id": "MNXM1", "chebi_id": "", "kegg_id": "",
    }]
    indices = {key: {} for key in ("ymdb", "mnx", "chebi", "kegg", "pubchem", "name")}
    indices["mnx"]["MNXM1"] = [Candidate("CCO", "MetaNetX", "MNXM1", "local.csv", "exact_metanetx_id", "high", "C2H6O")]
    enriched, provenance, methods = enrich(rows, indices, {}, parses)
    assert enriched[0]["smiles"] == "CCO"
    assert provenance[0]["decision"] == "mapped"
    assert methods["exact_metanetx_id"] == 1


def test_structure_and_formula_conflicts_are_not_promoted() -> None:
    candidates = [
        Candidate("CCO", "db", "1", "a", "exact", "high", "C2H6O"),
        Candidate("COC", "db", "1", "a", "exact", "high", "C2H6O"),
    ]
    chosen, reason, _ = select_candidate(candidates, "C2H6O", parses)
    assert chosen is None and reason == "multiple_structures_for_key"
    chosen, reason, _ = select_candidate(candidates[:1], "C3H8O", parses)
    assert chosen is None and reason == "formula_conflict"


def test_invalid_local_structure_is_never_promoted() -> None:
    chosen, reason, count = select_candidate(
        [Candidate("INVALID", "db", "1", "a", "exact", "high")], "", parses
    )
    assert chosen is None
    assert reason == "no_parseable_local_structure"
    assert count == 0
