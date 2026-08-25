"""Versioned API transport schemas; domain packages never import these values."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorDetail(ApiModel):
    code: str
    message: str
    correlation_id: UUID
    parameters: dict[str, str] = Field(default_factory=dict)


class ErrorEnvelope(ApiModel):
    error: ErrorDetail


class LoginRequest(ApiModel):
    username: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class SessionView(ApiModel):
    owner_identity_id: str
    username: str
    profile: str
    absolute_expires_at: datetime


class WorkspaceCreate(ApiModel):
    display_name: str = Field(min_length=3, max_length=200)


class WorkspaceView(ApiModel):
    organization_id: UUID
    workspace_id: UUID
    construction_object_id: UUID
    display_name: str
    lifecycle_state: str
    lifecycle_version: int
    workspace_revision: int
    write_fenced: bool
    created_at: datetime


class ResetPrepareRequest(ApiModel):
    confirmation: Literal["PREPARE_WORKSPACE_RESET"]


class ResetChallengeView(ApiModel):
    challenge_id: UUID
    workspace_id: UUID
    target_lifecycle_version: int
    confirmation_text: str
    expires_at: datetime
    assurance_profile: Literal["development_single_owner_confirmation"]


class ResetExecuteRequest(ApiModel):
    challenge_id: UUID
    confirmation_text: str = Field(min_length=20, max_length=512)


class ResetReceiptView(ApiModel):
    reset_receipt_id: UUID
    workspace_id: UUID
    outcome: Literal["verified", "reconciliation_required"]
    deleted_relation_row_count: int
    deleted_object_count: int
    archive_package_digest: str
    platform_fingerprint_before: str
    platform_fingerprint_after: str
    completed_at: datetime


class UploadBatchView(ApiModel):
    intake_manifest_id: UUID
    manifest_digest: str
    accepted_document_ids: list[UUID]
    duplicate_document_ids: list[UUID]
    rejected_count: int
    job_ids: list[UUID]


class DocumentView(ApiModel):
    organization_id: UUID
    workspace_id: UUID
    document_id: UUID
    version: int
    prior_versions: list[int]
    job_ids: list[UUID]
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
    capability_gaps: list[str]
    recorded_at: datetime


class DocumentPage(ApiModel):
    items: list[DocumentView]
    next_cursor: str | None


class JobView(ApiModel):
    organization_id: UUID
    workspace_id: UUID
    job_id: UUID
    job_kind: str
    state: str
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


class JobCancellationRequest(ApiModel):
    confirmation: Literal["CANCEL_JOB"]


class EvidenceLocatorView(ApiModel):
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


class EvidencePanelView(ApiModel):
    locator: EvidenceLocatorView
    candidate_fact_status: str
    authority_type: str
    rule_version: str | None
    practice_release: str | None
    normative_edition: str | None
    uncertainty: list[str]
    conflicts: list[str]
    quarantined: bool


class ModeView(ApiModel):
    mode: str
    purpose: str
    available_inputs: list[str]
    execution_id: UUID | None
    execution_state: str | None
    matrix_version_id: UUID | None
    bounded_results: dict[str, Any]
    missing_capabilities: list[str]
    gaps: list[str]
    readiness: str


class KnowledgeStatusView(ApiModel):
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
    projection_states: dict[str, Any]
    last_verified_backup_at: datetime | None
    semantic_fingerprints: dict[str, Any]
    memory_data_defect: bool
    knowledge_ready: bool
    blockers: list[str]


class CapabilityStatusView(ApiModel):
    contract_version: str
    slice: str
    implemented: list[str]
    blockers: list[str]
    trial_ready: bool
    oks_ready: bool
    product_ready: bool


class HealthView(ApiModel):
    status: Literal["live", "ready", "not_ready"]
    checks: dict[str, str] = Field(default_factory=dict)
