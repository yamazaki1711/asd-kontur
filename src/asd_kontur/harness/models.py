"""Immutable values for provider execution, rendering, Candidates, and validation."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import rfc8785


class Route(StrEnum):
    NATIVE_ONLY = "native_only"
    LOCAL_OCR = "local_ocr"
    LOCAL_VLM = "local_vlm"
    AUTHORIZED_EXTERNAL_VLM = "authorized_external_vlm"
    NO_EXECUTION = "no_execution"


class ProviderState(StrEnum):
    ACCEPTED = "accepted"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class CandidateStatus(StrEnum):
    UNVERIFIED = "unverified"
    VALIDATING = "validating"
    REPAIR_PLANNED = "repair_planned"
    VALIDATED_CANDIDATE = "validated_candidate"
    UNRESOLVED_UNCERTAINTY = "unresolved_uncertainty"
    REJECTED_EXTRACTION = "rejected_extraction"
    PROVIDER_MODEL_FAILURE = "provider_model_failure"


class Repairability(StrEnum):
    TARGETED_REPAIR = "targeted_repair"
    HUMAN_REQUIRED = "human_required"
    NOT_REPAIRABLE = "not_repairable"


@dataclass(frozen=True, slots=True)
class Scope:
    organization_id: UUID
    workspace_id: UUID


@dataclass(frozen=True, slots=True)
class Locator:
    source_version_id: UUID
    locator_id: UUID
    page: int
    region: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page locators are one-based")
        if self.region is not None:
            x1, y1, x2, y2 = self.region
            if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                raise ValueError("normalized region must be within the page")


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    provider_key: str
    provider_version: str
    model_key: str
    model_revision: str
    execution_format: str
    quantization: str
    runtime_version: str
    execution_profile: str
    prompt_version: str
    schema_version: str
    preprocessing_version: str
    rendering_version: str
    verification_policy_version: str

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class ExecutionBudget:
    budget_key: str
    version: str
    max_attempts: int
    max_repairs: int
    timeout_seconds: float
    token_limit: int
    page_limit: int
    payload_bytes: int
    no_progress_limit: int
    provider_switch_allowed: bool
    cost_limit: str
    environment: str = "development"

    def __post_init__(self) -> None:
        if self.environment == "production":
            raise ValueError("production numerical budgets require approved policy evidence")
        if min(self.max_attempts, self.max_repairs, self.token_limit, self.page_limit) < 0:
            raise ValueError("budget values cannot be negative")
        if self.timeout_seconds <= 0 or self.payload_bytes <= 0 or self.no_progress_limit < 1:
            raise ValueError("budget thresholds must be positive")


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    request_id: UUID
    attempt_id: UUID
    scope: Scope
    source_version_id: UUID
    source_digest: str
    locators: tuple[Locator, ...]
    purpose: str
    purpose_version: str
    classification: str
    route: Route
    identity: ExecutionIdentity
    rule_set_version: str
    authorization_id: UUID
    policy_versions: tuple[str, ...]
    budget: ExecutionBudget
    idempotency_key: str
    correlation_id: UUID
    causation_id: UUID
    parent_attempt_id: UUID | None = None
    payload_digest: str = ""
    request_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.locators or any(
            item.source_version_id != self.source_version_id for item in self.locators
        ):
            raise ValueError("all authorized locators must belong to the exact SourceVersion")
        if not self.idempotency_key:
            raise ValueError("idempotency key is required")
        if any(
            value.lower() == "latest" for value in (*self.policy_versions, self.rule_set_version)
        ):
            raise ValueError("persisted requests require exact versions")
        payload = {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if item.name != "request_digest"
        }
        object.__setattr__(self, "request_digest", digest_of(payload))


@dataclass(frozen=True, slots=True)
class ProviderExecutionResult:
    execution_id: UUID
    request_id: UUID
    attempt_id: UUID
    scope: Scope
    identity: ExecutionIdentity
    state: ProviderState
    finish_reason: str
    request_digest: str
    response_digest: str
    structured_payload: dict[str, Any] | None
    received_at: datetime
    raw_artifact_ref: str | None = None


@dataclass(frozen=True, slots=True)
class RenderArtifact:
    render_id: UUID
    scope: Scope
    source_version_id: UUID
    locator: Locator
    source_digest: str
    renderer: str
    renderer_version: str
    profile_version: str
    page_box: tuple[float, float, float, float]
    source_rotation: int
    applied_rotation: int
    dpi: int
    pixel_width: int
    pixel_height: int
    color_space: str
    image_format: str
    preprocessing_version: str
    source_to_render: tuple[float, ...]
    render_to_source: tuple[float, ...]
    render_digest: str
    parent_render_id: UUID | None = None
    crop: tuple[float, float, float, float] | None = None
    overlap: int = 0
    padding: int = 0

    def __post_init__(self) -> None:
        if len(self.source_to_render) != 9 or len(self.render_to_source) != 9:
            raise ValueError("render lineage requires reversible 3x3 transforms")
        if self.locator.source_version_id != self.source_version_id or self.dpi <= 0:
            raise ValueError("render lineage does not match its source")


@dataclass(frozen=True, slots=True)
class FieldCandidate:
    field_path: str
    value_type: str
    value: Any
    source_locators: tuple[Locator, ...]
    evidence_refs: tuple[str, ...]
    unit: str | None = None
    uncertainty_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateVersion:
    candidate_id: UUID
    version: int
    scope: Scope
    purpose: str
    origin: str
    fields: tuple[FieldCandidate, ...]
    status: CandidateStatus
    source_version_id: UUID
    attempt_id: UUID | None
    parent_version: int | None = None
    validation_refs: tuple[str, ...] = ()
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        if self.version < 1 or not self.fields:
            raise ValueError("CandidateVersion requires a positive version and fields")
        if self.status == CandidateStatus.VALIDATED_CANDIDATE:
            if not self.validation_refs:
                raise ValueError("validated Candidate requires exact validation references")
            if any(not item.source_locators for item in self.fields):
                raise ValueError("every material Candidate field requires source locators")
        object.__setattr__(
            self,
            "digest",
            digest_of(
                {
                    item.name: getattr(self, item.name)
                    for item in fields(self)
                    if item.name != "digest"
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class ValidationFailure:
    code: str
    validator_key: str
    validator_version: str
    field_path: str
    severity: str
    source_locators: tuple[Locator, ...]
    evidence_refs: tuple[str, ...]
    repairability: Repairability
    blocking: bool
    parameters: tuple[tuple[str, str], ...] = ()

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


def digest_of(value: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(_jsonable(value))).hexdigest()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (UUID, date, datetime, StrEnum)):
        return str(value)
    return value
