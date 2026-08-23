"""Typed shared acquisition and corpus values used by every operating mode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from asd_kontur.harness.models import digest_of


class SourceMedium(StrEnum):
    PAPER = "paper"
    DIGITAL = "digital"
    UNKNOWN = "unknown"


class CustodyClaim(StrEnum):
    ORIGINAL = "original"
    COPY = "copy"
    UNVERIFIED = "unverified"


class Composition(StrEnum):
    NATIVE = "native"
    RASTER = "raster"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class PageRoute(StrEnum):
    NATIVE = "native"
    DETERMINISTIC = "deterministic"
    LOCAL_VLM = "local_vlm"
    EXTERNAL_ELIGIBLE = "external_eligible"
    DEFERRED = "deferred"
    BLOCKED = "blocked"


class ReceiptStatus(StrEnum):
    VALIDATED = "validated"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class BoundaryDisposition(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class CorpusOutcome(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    UNRESOLVED = "unresolved"
    PROVIDER_FAILED = "provider_failed"
    RECOVERY_REQUIRED = "recovery_required"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class CorpusScope:
    organization_id: UUID
    workspace_id: UUID


@dataclass(frozen=True, slots=True)
class CollectionScope:
    scope: CorpusScope
    collection_scope_id: UUID
    version: int
    included_locations: tuple[str, ...]
    included_media: tuple[str, ...]
    completeness_claim: str
    authority_profile_version: str

    def __post_init__(self) -> None:
        if self.version < 1 or not self.included_locations:
            raise ValueError("Collection scope needs a positive version and an explicit location")
        if self.authority_profile_version.lower() == "latest":
            raise ValueError("Collection scope must pin an exact authority profile")


@dataclass(frozen=True, slots=True)
class CollectionMission:
    scope: CorpusScope
    collection_mission_id: UUID
    mode_execution_id: UUID
    collection_scope_id: UUID
    collection_scope_version: int
    collector_identity_id: str
    started_at: datetime
    state: str = "collecting"


@dataclass(frozen=True, slots=True)
class PhysicalLocation:
    physical_location_id: UUID
    kind: str
    locator: str
    authority: CustodyClaim


@dataclass(frozen=True, slots=True)
class MediaSource:
    media_source_id: UUID
    medium: SourceMedium
    device_or_container_ref: str
    readable: bool


@dataclass(frozen=True, slots=True)
class CollectionSource:
    collection_source_id: UUID
    mission_id: UUID
    physical_location_id: UUID
    media_source_id: UUID
    custody_claim: CustodyClaim
    acquired_at: datetime


@dataclass(frozen=True, slots=True)
class AcquisitionBatch:
    scope: CorpusScope
    acquisition_batch_id: UUID
    mission_id: UUID
    source_id: UUID
    idempotency_key: str
    acquired_by: str
    acquired_at: datetime


@dataclass(frozen=True, slots=True)
class CollectedItem:
    scope: CorpusScope
    collected_item_id: UUID
    acquisition_batch_id: UUID
    physical_object_id: UUID
    physical_object_version: int
    original_locator: str
    size_bytes: int
    media_type: str
    digest: str
    readable: bool
    completeness_claim: str

    def __post_init__(self) -> None:
        if self.size_bytes < 0 or self.physical_object_version < 1:
            raise ValueError("Collected item size/version is invalid")
        if not self.digest.startswith("sha256:"):
            raise ValueError("Collected item requires a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class CustodyReceipt:
    receipt_id: UUID
    item_id: UUID
    actor_identity_id: str
    method: str
    observed_digest: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class PageInspection:
    page_number: int
    width_points: float
    height_points: float
    rotation: int
    native_text_characters: int
    raster_objects: int
    readable: bool = True

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("Page locators are one-based")
        if self.width_points <= 0 or self.height_points <= 0:
            raise ValueError("Page box must be positive")

    @property
    def composition(self) -> Composition:
        if not self.readable:
            return Composition.UNKNOWN
        if self.native_text_characters > 0 and self.raster_objects > 0:
            return Composition.MIXED
        if self.native_text_characters > 0:
            return Composition.NATIVE
        if self.raster_objects > 0:
            return Composition.RASTER
        return Composition.UNKNOWN


@dataclass(frozen=True, slots=True)
class PhysicalObjectInspection:
    scope: CorpusScope
    inspection_id: UUID
    physical_object_id: UUID
    physical_object_version: int
    digest: str
    size_bytes: int
    media_type: str
    encrypted: bool
    readable: bool
    page_count: int
    pages: tuple[PageInspection, ...]
    embedded_attachment_count: int
    signature_claim_count: int
    inspection_profile_version: str
    inspected_at: datetime
    error_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.page_count < 0 or self.size_bytes < 0:
            raise ValueError("Inspection counts cannot be negative")
        if self.pages and tuple(page.page_number for page in self.pages) != tuple(
            range(1, self.page_count + 1)
        ):
            raise ValueError("Page inventory must be complete, ordered, and one-based")
        if self.inspection_profile_version.lower() == "latest":
            raise ValueError("Inspection profile must be exact")

    @property
    def raster_ratio(self) -> float:
        if not self.pages:
            return 0.0
        raster = sum(
            page.composition in {Composition.RASTER, Composition.MIXED} for page in self.pages
        )
        return raster / len(self.pages)


@dataclass(frozen=True, slots=True)
class ResourcePolicy:
    policy_version: str
    max_local_pages: int
    max_local_bytes: int
    max_pages_per_shard: int
    max_raster_pages_per_shard: int
    max_total_cost_units: int
    external_egress_allowed: bool
    external_provider_qualified: bool

    def __post_init__(self) -> None:
        numbers = (
            self.max_local_pages,
            self.max_local_bytes,
            self.max_pages_per_shard,
            self.max_raster_pages_per_shard,
            self.max_total_cost_units,
        )
        if self.policy_version.lower() == "latest" or any(number <= 0 for number in numbers):
            raise ValueError("Resource policy needs exact version and positive development limits")


@dataclass(frozen=True, slots=True)
class PagePlan:
    page_number: int
    route: PageRoute
    reason_code: str
    estimated_cost_units: int


@dataclass(frozen=True, slots=True)
class ProcessingShard:
    shard_id: UUID
    plan_id: UUID
    ordinal: int
    page_numbers: tuple[int, ...]
    context_overlap_pages: tuple[int, ...]
    route: PageRoute
    expected_output_contract: str

    def __post_init__(self) -> None:
        if self.ordinal < 1 or not self.page_numbers:
            raise ValueError("Shard ordinal/pages are required")
        if len(set(self.page_numbers)) != len(self.page_numbers):
            raise ValueError("A shard cannot contain duplicate pages")
        if not set(self.context_overlap_pages).issubset(self.page_numbers):
            raise ValueError("Overlap context must be part of the exact shard page list")


@dataclass(frozen=True, slots=True)
class ProcessingPlan:
    scope: CorpusScope
    processing_plan_id: UUID
    version: int
    inspection_id: UUID
    purpose: str
    classification: str
    policy_version: str
    page_plans: tuple[PagePlan, ...]
    shards: tuple[ProcessingShard, ...]
    estimated_cost_units: int
    estimated_seconds: int
    state: CorpusOutcome

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class ProcessingReceipt:
    scope: CorpusScope
    receipt_id: UUID
    plan_id: UUID
    plan_version: int
    shard_id: UUID
    page_number: int
    attempt_id: UUID
    idempotency_key: str
    status: ReceiptStatus
    result_digest: str | None
    validation_codes: tuple[str, ...]
    recorded_at: datetime
    context_only: bool = False

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("Receipt page must be one-based")
        if self.status is ReceiptStatus.VALIDATED and self.result_digest is None:
            raise ValueError("Validated receipt needs a result digest")


@dataclass(frozen=True, slots=True)
class BoundaryCandidate:
    scope: CorpusScope
    boundary_candidate_id: UUID
    container_source_version_id: UUID
    start_page: int
    end_page: int
    proposed_document_type: str
    method: str
    confidence: float | None
    evidence_receipt_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class BoundaryValidation:
    boundary_candidate_id: UUID
    disposition: BoundaryDisposition
    validator_version: str
    failure_codes: tuple[str, ...]
    authority_decision_ref: str | None


@dataclass(frozen=True, slots=True)
class LogicalDocumentOccurrence:
    scope: CorpusScope
    occurrence_id: UUID
    source_artifact_id: UUID
    source_version_id: UUID
    container_source_version_id: UUID
    start_page: int
    end_page: int
    boundary_validation_id: UUID


@dataclass(frozen=True, slots=True)
class CorpusReconciliation:
    scope: CorpusScope
    reconciliation_id: UUID
    plan_id: UUID
    plan_version: int
    expected_pages: tuple[int, ...]
    validated_pages: tuple[int, ...]
    failed_pages: tuple[int, ...]
    unknown_pages: tuple[int, ...]
    duplicate_pages: tuple[int, ...]
    unresolved_segments: tuple[tuple[int, int], ...]
    accepted_occurrence_ids: tuple[UUID, ...]
    outcome: CorpusOutcome
    receipt_fingerprint: str


@dataclass(frozen=True, slots=True)
class UnresolvedCorpusItem:
    item_id: UUID
    reason_code: str
    affected_locator: str
    blocking: bool


@dataclass(frozen=True, slots=True)
class CorpusCoverage:
    discovered_objects: int
    admitted_objects: int
    expected_pages: int
    readable_pages: int
    validated_pages: int
    accepted_logical_documents: int
    unresolved_items: int
    denominator_version: str


@dataclass(frozen=True, slots=True)
class PhysicalObjectRef:
    physical_object_id: UUID
    physical_object_version: int

    def __post_init__(self) -> None:
        if self.physical_object_version < 1:
            raise ValueError("Physical object reference requires an exact positive version")


@dataclass(frozen=True, slots=True)
class CorpusSnapshot:
    scope: CorpusScope
    corpus_snapshot_id: UUID
    version: int
    collection_scope_id: UUID
    collection_scope_version: int
    physical_objects: tuple[PhysicalObjectRef, ...]
    page_inventory: tuple[tuple[UUID, int], ...]
    logical_occurrence_ids: tuple[UUID, ...]
    duplicate_groups: tuple[tuple[PhysicalObjectRef, ...], ...]
    conflicting_version_ids: tuple[UUID, ...]
    unresolved_items: tuple[UnresolvedCorpusItem, ...]
    coverage: CorpusCoverage
    reconciliation_ids: tuple[UUID, ...]
    rule_set_version_id: UUID
    created_at: datetime
    outcome: CorpusOutcome

    def __post_init__(self) -> None:
        coverage = self.coverage
        if self.version < 1 or self.collection_scope_version < 1:
            raise ValueError("Corpus snapshot versions must be positive")
        if not self.reconciliation_ids:
            raise ValueError("Corpus snapshot requires exact reconciliation evidence")
        if coverage.admitted_objects > coverage.discovered_objects:
            raise ValueError("Admitted objects cannot exceed discovered objects")
        if coverage.readable_pages > coverage.expected_pages:
            raise ValueError("Readable pages cannot exceed expected pages")
        if coverage.validated_pages > coverage.readable_pages:
            raise ValueError("Validated pages cannot exceed readable pages")
        if coverage.discovered_objects != len(self.physical_objects):
            raise ValueError("Snapshot physical-object inventory does not match coverage")
        if coverage.expected_pages != len(self.page_inventory):
            raise ValueError("Snapshot page inventory does not match coverage")
        if coverage.accepted_logical_documents != len(self.logical_occurrence_ids):
            raise ValueError("Snapshot logical-document inventory does not match coverage")
        if coverage.unresolved_items != len(self.unresolved_items):
            raise ValueError("Snapshot unresolved inventory does not match coverage")
        if self.outcome is CorpusOutcome.COMPLETE and self.unresolved_items:
            raise ValueError("A complete corpus snapshot cannot contain unresolved items")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)
