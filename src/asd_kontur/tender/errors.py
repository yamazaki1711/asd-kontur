"""Stable errors for the WP-12 Tender slice."""

from __future__ import annotations

from enum import StrEnum


class TenderErrorCode(StrEnum):
    INVALID_SCOPE = "TENDER_INVALID_SCOPE"
    INVALID_STATE = "TENDER_INVALID_STATE"
    CONCURRENCY_CONFLICT = "TENDER_CONCURRENCY_CONFLICT"
    IDEMPOTENCY_CONFLICT = "TENDER_IDEMPOTENCY_CONFLICT"
    CORPUS_INCOMPLETE = "TENDER_CORPUS_INCOMPLETE"
    PROVENANCE_INCOMPLETE = "TENDER_PROVENANCE_INCOMPLETE"
    APPLICABILITY_INDETERMINATE = "TENDER_APPLICABILITY_INDETERMINATE"
    AUTHORITY_DENIED = "TENDER_AUTHORITY_DENIED"
    MATERIAL_BLOCKER = "TENDER_MATERIAL_BLOCKER"
    WORKSPACE_FENCED = "TENDER_WORKSPACE_FENCED"
    SCOPE_VIOLATION = "TENDER_SCOPE_VIOLATION"
    OUTPUT_INCOMPLETE = "TENDER_OUTPUT_INCOMPLETE"


class TenderError(RuntimeError):
    """A content-minimal, stable Tender failure."""

    def __init__(self, code: TenderErrorCode, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(f"{code.value}: {safe_message}")
