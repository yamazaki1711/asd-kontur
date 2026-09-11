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


class AssistantConversationCreate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)


class AssistantConversationView(ApiModel):
    conversation_id: UUID
    workspace_id: UUID
    title: str
    created_at: datetime
    latest_mode: Literal["Tender", "Support", "Audit", "Restoration"] | None
    message_count: int


class AssistantQuestionRequest(ApiModel):
    mode: Literal["Tender", "Support", "Audit", "Restoration"]
    question: str = Field(min_length=2, max_length=8000)


class AssistantTurnView(ApiModel):
    turn_id: UUID
    conversation_id: UUID
    ordinal: int
    mode: Literal["Tender", "Support", "Audit", "Restoration"]
    question: str
    state: str
    failure_code: str | None
    project_definition_id: UUID | None
    project_definition_version: int | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AssistantMessageView(ApiModel):
    message_id: UUID
    conversation_id: UUID
    turn_id: UUID
    ordinal: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[dict[str, Any]]
    action_proposals: list[dict[str, Any]]
    created_at: datetime


class AssistantCancelRequest(ApiModel):
    confirmation: Literal["STOP_ASSISTANT_RESPONSE"]


class ConstructionConsultantConversationCreate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)


class ConstructionConsultantConversationView(ApiModel):
    conversation_id: UUID
    title: str
    created_at: datetime
    message_count: int


class ConstructionConsultantMessageView(ApiModel):
    message_id: UUID
    conversation_id: UUID
    request_id: UUID | None
    ordinal: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[dict[str, Any]]
    model_identity: str | None
    model_profile_version: str | None
    created_at: datetime


class ConstructionConsultantQuestionRequest(ApiModel):
    request_id: UUID
    question: str = Field(min_length=2, max_length=8000)


class ConstructionConsultantAnswerView(ApiModel):
    user_message: ConstructionConsultantMessageView
    assistant_message: ConstructionConsultantMessageView
    evidence_statuses: list[str]


class PilotResultView(ApiModel):
    result_id: UUID
    version: int
    mode: Literal["Tender", "Support", "Audit", "Restoration"]
    workspace_id: UUID
    workspace_name: str
    project_definition_id: str
    project_definition_version: int
    matrix_id: str
    matrix_version: int
    project_status: str
    project_fields: dict[str, Any]
    summary: dict[str, Any]
    items: list[dict[str, Any]]
    source_manifest: list[dict[str, Any]]
    unresolved_questions: list[str]
    available_exports: list[str]
    normative_notice: str
    status: str
    fingerprint: str
    formed_at: str | None = None
    exports: list[dict[str, Any]] = Field(default_factory=list)
    reviewed_item_count: int = 0


class PilotResultItemReviewRequest(ApiModel):
    action: Literal["accepted", "corrected", "excluded", "status_changed", "commented"]
    resolved_fields: dict[str, Any] | None = None
    comment: str = Field(min_length=3, max_length=2000)

    def model_post_init(self, __context: Any) -> None:
        del __context
        requires_fields = self.action in {"corrected", "status_changed"}
        if requires_fields != (self.resolved_fields is not None):
            raise ValueError("corrected or status action requires resolved_fields")
        if self.action == "status_changed" and "status" not in (self.resolved_fields or {}):
            raise ValueError("status action requires status")


class PilotExportRequest(ApiModel):
    export_kind: Literal[
        "disagreement_protocol",
        "contract_changes",
        "requirement_matrix",
        "id_package",
        "register",
        "audit_report",
        "recovery_plan",
        "recovered_drafts",
        "workspace_results",
    ]
    output_format: Literal["docx", "pdf", "zip"]


class PilotExportView(ApiModel):
    export_id: UUID
    version: int
    export_kind: str
    output_format: str
    media_type: str
    size_bytes: int
    content_digest: str
    export_fingerprint: str


class TrialReadinessRequest(ApiModel):
    criteria: dict[str, bool]
    pilot_thresholds: dict[str, Any]
    external_receipts: list[dict[str, Any]]
    user_blockers: list[str] = Field(default_factory=list)
    rollback_target: str = Field(min_length=7, max_length=512)


class TrialReadinessView(ApiModel):
    decision_id: UUID
    version: int
    deployed_commit: str
    status: Literal["trial_ready", "blocked"]
    criteria: dict[str, bool]
    pilot_thresholds: dict[str, Any]
    external_receipts: list[dict[str, Any]]
    user_blockers: list[str]
    rollback_target: str
    decision_fingerprint: str
    decided_by_identity_id: str
    decided_at: datetime


class ProjectUnderstandingView(ApiModel):
    materialization: dict[str, Any] = Field(default_factory=dict)
    reconciliation: dict[str, Any]
    project_definition: dict[str, Any]
    page_roles: list[dict[str, Any]]
    work_packages: list[dict[str, Any]]
    matrix: dict[str, Any]
    normative_profile: dict[str, Any] | None
    defects: list[dict[str, Any]]
    evidence_index: dict[str, dict[str, Any]]
    candidates: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    structure_nodes: list[dict[str, Any]] = Field(default_factory=list)
    review_decisions: list[dict[str, Any]] = Field(default_factory=list)
    intake_summary: dict[str, Any] = Field(default_factory=dict)
    semantic_coverage: list[dict[str, Any]] = Field(default_factory=list)
    authority_layers: dict[str, str]


class ProjectCandidateReviewRequest(ApiModel):
    candidate_kind: Literal["project_field", "work_type", "quantity", "material"]
    candidate_id: UUID
    candidate_version: int = Field(ge=1)
    action: Literal["confirmed", "rejected", "corrected"]
    resolved_value: Any | None = None
    reason: str = Field(min_length=3, max_length=1000)

    def model_post_init(self, __context: Any) -> None:
        del __context
        if (self.action == "corrected") != (self.resolved_value is not None):
            raise ValueError("corrected action requires resolved_value")


class ProjectCandidateReviewView(ApiModel):
    review_decision_id: UUID
    decision_version: int
    action: str
    decision_digest: str


class SupportProductionView(ApiModel):
    workspace_id: UUID
    matrix: dict[str, Any] | None
    requirements: list[dict[str, Any]]
    package: dict[str, Any] | None
    package_history: list[dict[str, Any]] = Field(default_factory=list)
    book_history: list[dict[str, Any]] = Field(default_factory=list)
    register_history: list[dict[str, Any]] = Field(default_factory=list)
    readiness_history: list[dict[str, Any]] = Field(default_factory=list)
    books: list[dict[str, Any]] = Field(default_factory=list)
    memberships: list[dict[str, Any]] = Field(default_factory=list)
    registers: list[dict[str, Any]] = Field(default_factory=list)
    readiness: dict[str, Any] | None = None
    field_resolutions: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[str]
    authority_layers: dict[str, str]


class FormIdPackageRequest(ApiModel):
    work_package_id: UUID


class StartGenerationRequest(ApiModel):
    membership_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=200)


class GenerationStartView(ApiModel):
    job_id: UUID
    generation_run_id: UUID | None = None
    state: str
    duplicate: bool


class ReviewGeneratedCandidateRequest(ApiModel):
    outcome: Literal["approved", "rejected", "needs_correction"]


class PackageBackupManifestView(ApiModel):
    backup_manifest_id: UUID
    fingerprint: str
    latest_package: dict[str, Any]
    packages: list[dict[str, Any]]
    books: list[dict[str, Any]]
    memberships: list[dict[str, Any]]
    registers: list[dict[str, Any]]
    readiness: list[dict[str, Any]]
    generation_runs: list[dict[str, Any]]
    generated_candidates: list[dict[str, Any]]
    print_validations: list[dict[str, Any]]
    reviews: list[dict[str, Any]]
    finalized_documents: list[dict[str, Any]]
    terminal_receipts: list[dict[str, Any]]


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
    ntd_inventory: dict[str, Any]
    projection_states: dict[str, Any]
    last_verified_backup_at: datetime | None
    semantic_fingerprints: dict[str, Any]
    memory_data_defect: bool
    knowledge_ready: bool
    blockers: list[str]


class NtdSeedResolutionView(ApiModel):
    provider: str
    status: str
    failure_code: str | None
    official_record_url: str | None
    official_record_digest: str | None
    observations: list[str]


class NtdRuleDecisionView(ApiModel):
    rule_candidate_id: UUID
    candidate_version: int
    deontic_type: str
    qualification_status: str
    qualification_gates: list[list[Any]]
    activation_status: str
    activation_reason: str
    rule_version_id: UUID | None
    rule_lifecycle_status: str | None


class NtdVerifiedProvisionView(ApiModel):
    provision_id: UUID
    version: int
    source_version_id: UUID
    structural_path: str
    page_number: int
    locators: list[dict[str, Any]]
    verbatim_text: str
    content_digest: str
    verification_decision_ref: str
    edition_activation_status: str
    rules: list[NtdRuleDecisionView]
    alignments: list[dict[str, Any]]


class NtdSeedArtifactView(ApiModel):
    artifact_id: UUID
    document_id: UUID
    edition_id: UUID
    designation: str
    title: str
    edition_label: str
    official_url: str
    content_digest: str
    media_type: str
    size_bytes: int
    page_count: int
    native_page_count: int
    polza_routed_page_count: int
    blocked_page_count: int
    native_complete_page_count: int
    recovered_page_count: int
    external_candidate_page_count: int
    verified_provision_count: int
    practice_alignment_count: int
    qualified_rule_count: int
    verified_provisions: list[NtdVerifiedProvisionView]


class NtdSeedIdentityView(ApiModel):
    stable_identity: str
    printed_designations: list[str]
    identity_status: str
    resolutions: list[NtdSeedResolutionView]
    artifacts: list[NtdSeedArtifactView]


class NtdSeedStatusView(ApiModel):
    schema_version: str
    logical_manifest_fingerprint: str
    counts: dict[str, int]
    identities: list[NtdSeedIdentityView]
    complete: bool


class DeploymentStatusView(ApiModel):
    source_commit: str
    runtime_profile: str
    deployed_at: str | None
    frontend_build_digest: str | None
    openapi_digest: str | None
    migration_head: str


class CapabilityStatusView(ApiModel):
    contract_version: str
    slice: str
    implemented: list[str]
    blockers: list[str]
    trial_ready: bool
    construction_consultant_quality_ready: bool
    domain_harness_ready: bool
    oks_ready: bool
    product_ready: bool
    deployment: DeploymentStatusView


class HealthView(ApiModel):
    status: Literal["live", "ready", "not_ready"]
    checks: dict[str, str] = Field(default_factory=dict)
