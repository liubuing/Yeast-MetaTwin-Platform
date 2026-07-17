from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "08_runtime"))
import build_10h2da_validation_artifact as artifact  # noqa: E402


def test_stable_identifier_extraction() -> None:
    record = {"source": "UniProt", "record": json.dumps({"primaryAccession": "B8QHP1", "comments": [{"id": "RHEA:56748"}]})}
    assert artifact._stable_ids(record) == {"uniprot_accession": "B8QHP1", "pmid": "", "rhea_id": "RHEA:56748"}
    pubmed = {"source": "PubMed", "record": json.dumps({"uid": "40468562"})}
    assert artifact._stable_ids(pubmed)["pmid"] == "40468562"


def test_builder_refuses_existing_output(tmp_path: Path) -> None:
    with pytest.raises(FileExistsError):
        artifact.build(tmp_path)
