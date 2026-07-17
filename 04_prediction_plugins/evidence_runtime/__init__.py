"""Structured, review-gated external evidence records."""

from .schema import EvidenceGrade, EvidenceRecord, ReviewStatus, sha256_snapshot

SCHEMA_VERSION = "1.0.0"

__all__ = ["EvidenceGrade", "EvidenceRecord", "ReviewStatus", "SCHEMA_VERSION", "sha256_snapshot"]
