"""Transport-neutral immutable Product Application Spine values."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

JsonValue = dict[str, Any]


class JobKind(StrEnum):
    DOCUMENT_ADMISSION = "DOCUMENT_ADMISSION"
    DOCUMENT_HASH = "DOCUMENT_HASH"
    PDF_INVENTORY = "PDF_INVENTORY"
    NATIVE_TEXT_EXTRACTION = "NATIVE_TEXT_EXTRACTION"
    DOCUMENT_FORMAT_INVENTORY = "DOCUMENT_FORMAT_INVENTORY"
    PDF_PAGE_HEALTH_ANALYSIS = "PDF_PAGE_HEALTH_ANALYSIS"
    NATIVE_LAYOUT_EXTRACTION = "NATIVE_LAYOUT_EXTRACTION"
    OCR_ROUTING = "OCR_ROUTING"
    OCR_EXTRACTION = "OCR_EXTRACTION"
    DOCUMENT_PAGE_CLASSIFICATION = "DOCUMENT_PAGE_CLASSIFICATION"
    DOCUMENT_AGGREGATION = "DOCUMENT_AGGREGATION"
    PROJECT_DEFINITION_EXTRACTION = "PROJECT_DEFINITION_EXTRACTION"
    WORK_QUANTITY_MATERIAL_EXTRACTION = "WORK_QUANTITY_MATERIAL_EXTRACTION"
    WORK_PACKAGE_ASSEMBLY = "WORK_PACKAGE_ASSEMBLY"
    REQUIREMENT_MATRIX_ASSEMBLY = "REQUIREMENT_MATRIX_ASSEMBLY"
    PROJECT_UNDERSTANDING_RECONCILIATION = "PROJECT_UNDERSTANDING_RECONCILIATION"
    PROJECT_STRUCTURE_RECONCILIATION = "PROJECT_STRUCTURE_RECONCILIATION"
    ID_DOCUMENT_GENERATION = "ID_DOCUMENT_GENERATION"
    EVIDENCE_INDEX_UPDATE = "EVIDENCE_INDEX_UPDATE"
    WORKSPACE_RESET_RECONCILIATION = "WORKSPACE_RESET_RECONCILIATION"


class JobState(StrEnum):
    QUEUED = "queued"
    PAUSED = "paused"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class ModeName(StrEnum):
    TENDER = "Tender"
    SUPPORT = "Support"
    AUDIT = "Audit"
    RESTORATION = "Restoration"


@dataclass(frozen=True, slots=True)
class SessionPrincipal:
    owner_identity_id: str
    username: str
    session_digest: str
    csrf_digest: str
    profile: str
    absolute_expires_at: datetime


@dataclass(frozen=True, slots=True)
class SessionTokens:
    session_token: str
    csrf_token: str
    principal: SessionPrincipal


@dataclass(frozen=True, slots=True)
class WorkspaceSummary:
    organization_id: UUID
    workspace_id: UUID
    construction_object_id: UUID
    display_name: str
    lifecycle_state: str
    lifecycle_version: int
    workspace_revision: int
    write_fenced: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    organization_id: UUID
    workspace_id: UUID
    document_id: UUID
    version: int
    prior_versions: tuple[int, ...]
    job_ids: tuple[UUID, ...]
    source_artifact_id: UUID | None
    source_version_id: UUID | None
    safe_display_name: str
    relative_path: str
    media_type: str
    size_bytes: int
    content_digest: str
    page_count: int | None
    admission_status: str
    extraction_status: str
    capability_gaps: tuple[str, ...]
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class BatchRegistration:
    intake_manifest_id: UUID
    manifest_digest: str
    accepted_document_ids: tuple[UUID, ...]
    duplicate_document_ids: tuple[UUID, ...]
    rejected_count: int
    job_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class JobSummary:
    organization_id: UUID
    workspace_id: UUID
    job_id: UUID
    job_kind: JobKind
    state: JobState
    priority: int
    attempt_count: int
    max_attempts: int
    cancellation_state: str
    typed_failure_code: str | None
    terminal_receipt_id: UUID | None
    created_at: datetime
    started_at: datetime | None
    heartbeat_at: datetime | None
    completed_at: datetime | None
    lease_expires_at: datetime | None
    lease_expired: bool
    progress_current: int | None
    progress_total: int | None
    progress_message_code: str | None
    progress_recorded_at: datetime | None


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    organization_id: UUID
    workspace_id: UUID
    job_id: UUID
    job_kind: JobKind
    input_manifest: JsonValue
    input_digest: str
    attempt_number: int
    lease_generation: int
    cancellation_state: str


@dataclass(frozen=True, slots=True)
class JobProgress:
    job_id: UUID
    sequence: int
    event_type: str
    current: int | None
    total: int | None
    safe_message_code: str
    terminal: bool
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class PageLocator:
    document_id: UUID
    document_version: int
    source_version_id: UUID
    source_locator_id: UUID
    page_number: int
    region: tuple[float, float, float, float]
    width_points: float
    height_points: float
    rotation_degrees: int
    evidence_digest: str
    extraction_method: str


@dataclass(frozen=True, slots=True)
class EvidencePanel:
    locator: PageLocator
    candidate_fact_status: str
    authority_type: str
    rule_version: str | None
    practice_release: str | None
    normative_edition: str | None
    uncertainty: tuple[str, ...]
    conflicts: tuple[str, ...]
    quarantined: bool


@dataclass(frozen=True, slots=True)
class ModeWorkspaceView:
    mode: ModeName
    purpose: str
    available_inputs: tuple[str, ...]
    execution_id: UUID | None
    execution_state: str | None
    matrix_version_id: UUID | None
    bounded_results: JsonValue
    missing_capabilities: tuple[str, ...]
    gaps: tuple[str, ...]
    readiness: str


@dataclass(frozen=True, slots=True)
class KnowledgeStatus:
    practice_guide_count: int
    practice_edition_count: int
    active_practice_release_count: int
    source_guidance_count: int
    active_intelligence_count: int
    active_playbook_count: int
    active_gap_count: int
    conflict_count: int
    quarantine_count: int
    normative_identity_count: int
    verified_normative_edition_count: int
    verified_normative_provision_count: int
    rule_version_count: int
    ntd_inventory: JsonValue
    projection_states: JsonValue
    last_verified_backup_at: datetime | None
    semantic_fingerprints: JsonValue
    memory_data_defect: bool
    knowledge_ready: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResetChallenge:
    challenge_id: UUID
    workspace_id: UUID
    target_lifecycle_version: int
    confirmation_text: str
    expires_at: datetime
    assurance_profile: str


@dataclass(frozen=True, slots=True)
class ResetReceipt:
    reset_receipt_id: UUID
    workspace_id: UUID
    outcome: str
    deleted_relation_row_count: int
    deleted_object_count: int
    archive_package_digest: str
    platform_fingerprint_before: str
    platform_fingerprint_after: str
    completed_at: datetime


def semantic_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        default=str,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def encode_cursor(*parts: object) -> str:
    raw = json.dumps(parts, default=str, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, expected_parts: int) -> tuple[str, ...]:
    try:
        padding = "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(cursor + padding))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid stable cursor") from exc
    if not isinstance(value, list) or len(value) != expected_parts:
        raise ValueError("invalid stable cursor shape")
    return tuple(str(part) for part in value)
