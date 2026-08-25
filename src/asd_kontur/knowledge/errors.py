"""Stable, typed failures for knowledge operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class KnowledgeErrorCode(StrEnum):
    ACCESS_DENIED = "knowledge.access_denied"
    SCOPE_VIOLATION = "knowledge.scope_violation"
    OBJECT_STORE_UNAVAILABLE = "knowledge.object_store_unavailable"
    OBJECT_WRITE_FAILED = "knowledge.object_write_failed"
    RECONCILIATION_REQUIRED = "knowledge.reconciliation_required"
    DIGEST_CONFLICT = "knowledge.digest_conflict"
    LOCATOR_CONFLICT = "knowledge.locator_conflict"
    VERSION_CONFLICT = "knowledge.version_conflict"
    EVIDENCE_MISSING = "knowledge.evidence_missing"
    EDITION_AMBIGUOUS = "knowledge.edition_ambiguous"
    KNOWLEDGE_INCOMPLETE = "knowledge.incomplete"
    INDEX_UNAVAILABLE = "knowledge.index_unavailable"
    RULE_NOT_ACTIVE = "knowledge.rule_not_active"
    RULE_SET_NOT_PINNED = "knowledge.rule_set_not_pinned"
    AUTHORITY_DENIED = "knowledge.authority_denied"
    INVALID_TRANSITION = "knowledge.invalid_transition"
    PROMOTION_BLOCKED = "knowledge.promotion_blocked"
    CONTRACT_VERSION_UNSUPPORTED = "knowledge.contract_version_unsupported"
    RETENTION_CLASS_INVALID = "knowledge.retention_class_invalid"


@dataclass
class KnowledgeError(Exception):
    code: KnowledgeErrorCode
    safe_message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.safe_message}"
