from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


SCHEMA_VERSION = "1.0.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PMID_RE = re.compile(r"^\d{1,10}$")
RHEA_RE = re.compile(r"^RHEA:\d+$")
UNIPROT_RE = re.compile(r"^[A-Z0-9]{6,10}$")


class ReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class EvidenceGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


def sha256_snapshot(raw_snapshot: bytes) -> str:
    if not raw_snapshot:
        raise ValueError("raw evidence snapshot cannot be empty")
    return hashlib.sha256(raw_snapshot).hexdigest()


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    candidate_id: str
    source_database: str
    database_version: str
    source_accession: str
    source_url: str
    snapshot_sha256: str
    automated_grade: EvidenceGrade
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    pmid: str | None = None
    rhea_id: str | None = None
    uniprot_accession: str | None = None
    final_grade: EvidenceGrade | None = None
    reviewer: str | None = None
    reviewed_at: str | None = None
    review_note: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        required = (
            self.evidence_id,
            self.candidate_id,
            self.source_database,
            self.database_version,
            self.source_accession,
            self.source_url,
        )
        if any(not value.strip() for value in required):
            raise ValueError("evidence identifiers, database version, accession, and URL are required")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported evidence schema_version: {self.schema_version}")
        if not SHA256_RE.fullmatch(self.snapshot_sha256):
            raise ValueError("snapshot_sha256 must be a lowercase SHA-256 digest")
        if self.pmid and not PMID_RE.fullmatch(self.pmid):
            raise ValueError("invalid PMID")
        if self.rhea_id and not RHEA_RE.fullmatch(self.rhea_id):
            raise ValueError("Rhea identifiers must use RHEA:<digits>")
        if self.uniprot_accession and not UNIPROT_RE.fullmatch(self.uniprot_accession):
            raise ValueError("invalid UniProt accession")
        if self.automated_grade in {EvidenceGrade.A, EvidenceGrade.B}:
            raise ValueError("automated evidence grading is limited to C, D, or E")
        if self.final_grade in {EvidenceGrade.A, EvidenceGrade.B}:
            if self.review_status != ReviewStatus.APPROVED or not (self.reviewer and self.reviewed_at and self.review_note):
                raise ValueError("A/B evidence requires approved manual review with reviewer, timestamp, and note")
        if self.review_status == ReviewStatus.APPROVED and not (self.reviewer and self.reviewed_at and self.review_note):
            raise ValueError("approved evidence requires reviewer, timestamp, and note")
        if self.final_grade is not None and self.review_status != ReviewStatus.APPROVED:
            raise ValueError("final_grade is only valid after approved manual review")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["automated_grade"] = self.automated_grade.value
        value["review_status"] = self.review_status.value
        value["final_grade"] = self.final_grade.value if self.final_grade else None
        return value
