"""Immutable lifecycle values shared by services and persistence adapters."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

import rfc8785


class LifecycleState(StrEnum):
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    FREEZING = "FREEZING"
    FROZEN = "FROZEN"
    FINALIZING = "FINALIZING"
    FINALIZED = "FINALIZED"
    EXPORTING = "EXPORTING"
    EXPORTED = "EXPORTED"
    ARCHIVING = "ARCHIVING"
    ARCHIVED = "ARCHIVED"
    CLOSED = "CLOSED"
    REOPENING = "REOPENING"
    RESET_PLANNING = "RESET_PLANNING"
    RESET_AUTHORIZED = "RESET_AUTHORIZED"
    PURGING = "PURGING"
    VERIFYING_RESET = "VERIFYING_RESET"
    RESET_VERIFIED = "RESET_VERIFIED"
    DESTROYING = "DESTROYING"
    DESTROYED = "DESTROYED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    QUARANTINED = "QUARANTINED"


class Mode(StrEnum):
    TENDER = "Tender"
    SUPPORT = "Support"
    AUDIT = "Audit"
    RESTORATION = "Restoration"


class AssuranceClass(StrEnum):
    DEVELOPMENT_DISPOSABLE = "development/disposable"
    PRODUCTION = "production"


class AdapterOutcome(StrEnum):
    DELETED = "deleted"
    ALREADY_ABSENT = "already_absent"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    RESIDUE_DETECTED = "residue_detected"


class VerificationOutcome(StrEnum):
    VERIFIED = "verified"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class AdapterHealth(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class Authority:
    identity_id: str
    identity_kind: str
    capabilities: frozenset[str] = frozenset()

    @property
    def is_human(self) -> bool:
        return self.identity_kind == "human"


@dataclass(frozen=True, slots=True)
class ExactVersionReference:
    key: str
    version: str

    def __post_init__(self) -> None:
        if not self.key or not self.version or self.version.lower() == "latest":
            raise ValueError("an exact non-latest key/version reference is required")


@dataclass(frozen=True, slots=True)
class RetentionProfile:
    reference: ExactVersionReference
    environment: str
    data_classes: frozenset[str]
    complete: bool
    production_approved: bool
    retained_on_reset: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Basis:
    registry: ExactVersionReference
    code: str
    evidence_refs: tuple[str, ...]
    effective_until: datetime


@dataclass(frozen=True, slots=True)
class ModeExecutionConfiguration:
    mode_execution_id: UUID
    mode: Mode
    process_definition: ExactVersionReference
    rule_set: ExactVersionReference
    policy_assignment: ExactVersionReference
    authority_profile: ExactVersionReference
    input_contract: ExactVersionReference
    output_contract: ExactVersionReference
    purpose: str


@dataclass(frozen=True, slots=True)
class StorageAdapterDefinition:
    adapter_key: str
    adapter_version: str
    storage_class: str
    data_plane: str
    scope: str
    required: bool
    inventory_capable: bool
    purge_capable: bool
    residue_verification_capable: bool
    destroy_capable: bool
    receipt_schema_version: str
    health: AdapterHealth = AdapterHealth.AVAILABLE


@dataclass(frozen=True, slots=True)
class InventoryItem:
    item_id: str
    workspace_id: UUID
    media_type: str
    size_bytes: int
    digest: str


@dataclass(frozen=True, slots=True)
class DeletionItem:
    adapter_key: str
    item_id: str
    action: str


@dataclass(frozen=True, slots=True)
class DeletionPlan:
    plan_id: UUID
    plan_version: int
    operation_kind: str
    organization_id: UUID
    workspace_id: UUID
    lifecycle_version: int
    workspace_revision: int
    retention_profile: ExactVersionReference
    basis: Basis
    legal_hold_checked_at: datetime
    inventory_digest: str
    adapter_registry: ExactVersionReference
    items: tuple[DeletionItem, ...]
    expected_residue_classes: tuple[str, ...]
    requester_identity_id: str
    dry_run_completed: bool
    expires_at: datetime
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        if self.operation_kind not in {"reset", "destroy"}:
            raise ValueError("operation_kind must be reset or destroy")
        payload = {
            item.name: getattr(self, item.name) for item in fields(self) if item.name != "digest"
        }
        canonical = rfc8785.dumps(_jsonable(payload))
        object.__setattr__(self, "digest", "sha256:" + hashlib.sha256(canonical).hexdigest())


@dataclass(frozen=True, slots=True)
class DestructiveAuthorization:
    authorization_id: UUID
    plan_id: UUID
    plan_digest: str
    requester_identity_id: str
    confirmer_identity_id: str
    executor_identity_id: str
    verifier_identity_id: str
    authorized_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AdapterReceipt:
    receipt_id: UUID
    adapter_key: str
    item_id: str
    outcome: AdapterOutcome
    before_count: int
    after_count: int
    operation_id: UUID
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class ResidualScan:
    scan_id: UUID
    adapter_key: str
    methods: tuple[str, ...]
    outcome: VerificationOutcome
    found_count: int
    foreign_workspace_count: int
    allowed_residue_classes: tuple[str, ...]
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class RecoveryCheckpoint:
    checkpoint_id: UUID
    operation_id: UUID
    plan_digest: str
    failed_operation: str
    affected_adapters: tuple[str, ...]
    completed_effects: tuple[str, ...]
    pending_items: tuple[str, ...]
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class DestructionAttestation:
    attestation_id: UUID
    version: int
    workspace_id: UUID
    lifecycle_revision: int
    plan_id: UUID
    plan_digest: str
    retention_profile: ExactVersionReference
    basis_registry: ExactVersionReference
    basis_code: str
    legal_hold_check_ids: tuple[UUID, ...]
    requester_identity_id: str
    confirmer_identity_id: str
    executor_identity_id: str
    verifier_identity_id: str
    adapter_registry: ExactVersionReference
    receipt_ids: tuple[UUID, ...]
    scan_ids: tuple[UUID, ...]
    aggregate_deleted_count: int
    aggregate_residue_count: int
    residue_classes: tuple[str, ...]
    platform_integrity_before: str
    platform_integrity_after: str
    verified_at: datetime
    assurance_class: AssuranceClass
    outcome: VerificationOutcome

    def to_content_free_dict(self) -> dict[str, Any]:
        result = cast(dict[str, Any], _jsonable(asdict(self)))
        result["attestation_version"] = result.pop("version")
        return result


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (UUID, datetime, StrEnum)):
        return str(value)
    return value
