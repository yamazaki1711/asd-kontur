"""Evidence-bound values for industrial document understanding.

The module contains workspace candidates and deterministic decisions only.  It
does not define a second ProjectDefinition or WorkRequirementMatrix authority;
accepted values are assembled into the existing construction harness types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from asd_kontur.harness.models import digest_of

UNDERSTANDING_PROFILE_VERSION = "industrial-document-understanding-v0.1"
PAGE_HEALTH_PROFILE_VERSION = "page-health-v0.1"
NATIVE_LAYOUT_PROFILE_VERSION = "native-layout-v0.1"
OCR_ROUTING_PROFILE_VERSION = "ocr-routing-v0.1"
CLASSIFICATION_PROFILE_VERSION = "document-page-role-v0.1"
PROJECT_EXTRACTION_PROFILE_VERSION = "project-definition-extraction-v0.1"
WORK_EXTRACTION_PROFILE_VERSION = "work-quantity-material-extraction-v0.1"


class PageHealthKind(StrEnum):
    BORN_DIGITAL = "born_digital_text"
    RASTER_ONLY = "raster_only_scan"
    MIXED = "mixed_text_raster"
    EXISTING_OCR = "existing_ocr_layer"
    DAMAGED_ENCODING = "damaged_or_unreadable_encoding"
    TABLE_HEAVY = "table_heavy"
    DRAWING = "drawing_or_scheme"
    BLANK = "blank_or_technical_separator"
    PASSWORD_PROTECTED = "password_or_encryption"
    RENDER_FAILURE = "render_failure"


class OcrRoute(StrEnum):
    NOT_REQUIRED = "not_required"
    QWEN_VISION = "qwen3_8_vision"
    APPLE_VISION = "apple_vision_accurate"
    TESSERACT = "tesseract_rus_eng"
    VLM_REQUIRED = "vlm_required"
    BLOCKED = "blocked"


class DocumentRole(StrEnum):
    EXPLANATORY_NOTE = "explanatory_note"
    PROJECT_DOCUMENTATION = "project_documentation"
    WORKING_DOCUMENTATION = "working_documentation"
    BILL_OF_QUANTITIES = "bill_of_quantities"
    LOCAL_ESTIMATE = "local_estimate"
    OBJECT_ESTIMATE = "object_estimate"
    CONSOLIDATED_ESTIMATE = "consolidated_estimate"
    SPECIFICATION = "specification"
    CONTRACT = "contract"
    CUSTOMER_REGULATION = "customer_regulation"
    NORMATIVE_REFERENCE_LIST = "normative_reference_list"
    EXECUTIVE_DOCUMENTATION = "executive_documentation"
    DRAWING_OR_SCHEME = "drawing_or_scheme"
    CORRESPONDENCE_ADMINISTRATIVE = "correspondence_administrative"
    UNKNOWN = "unknown"


class CandidateDecision(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    NEEDS_EVIDENCE = "needs_evidence"


class MappingStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class ReconciliationDefectKind(StrEnum):
    PROJECT_WORK_MISSING_IN_ESTIMATE = "project_work_missing_in_estimate"
    QUANTITY_MISMATCH = "quantity_mismatch"
    PROJECT_MATERIAL_MISSING_IN_ESTIMATE = "project_material_missing_in_estimate"
    ESTIMATE_POSITION_UNSUPPORTED_BY_PROJECT = "estimate_position_unsupported_by_project"
    INCOMPATIBLE_UNITS = "incompatible_units"
    AMBIGUOUS_SOURCE_MATCH = "ambiguous_source_match"
    DRAWING_INTELLIGENCE_REQUIRED = "drawing_intelligence_required"
    NORMATIVE_AUTHORITY_UNAVAILABLE = "normative_authority_unavailable"
    RULE_COVERAGE_UNAVAILABLE = "rule_coverage_unavailable"


@dataclass(frozen=True, slots=True)
class ExactLocator:
    source_version_id: UUID
    source_locator_id: UUID
    document_id: UUID
    document_version: int
    page_number: int
    region: tuple[float, float, float, float]
    evidence_digest: str
    cell: str | None = None

    def __post_init__(self) -> None:
        x0, y0, x1, y1 = self.region
        if self.document_version < 1 or self.page_number < 1:
            raise ValueError("locator versions and pages are one-based")
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("locator region must be normalized and non-empty")
        if not self.evidence_digest.startswith("sha256:"):
            raise ValueError("locator requires exact evidence digest")


@dataclass(frozen=True, slots=True)
class PageHealthAnalysis:
    page_health_id: UUID
    page_number: int
    primary_kind: PageHealthKind
    signals: tuple[str, ...]
    text_character_count: int
    replacement_character_ratio: Decimal
    image_count: int
    rotation_degrees: int
    width_points: Decimal
    height_points: Decimal
    route: OcrRoute
    profile_version: str
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.page_number < 1 or self.profile_version.lower() == "latest":
            raise ValueError("page health requires exact profile and one-based page")
        payload = {
            "page_health_id": self.page_health_id,
            "page_number": self.page_number,
            "primary_kind": self.primary_kind,
            "signals": self.signals,
            "text_character_count": self.text_character_count,
            "replacement_character_ratio": self.replacement_character_ratio,
            "image_count": self.image_count,
            "rotation_degrees": self.rotation_degrees,
            "width_points": self.width_points,
            "height_points": self.height_points,
            "route": self.route,
            "profile_version": self.profile_version,
        }
        object.__setattr__(self, "fingerprint", digest_of(payload))


@dataclass(frozen=True, slots=True)
class LayoutElement:
    element_id: UUID
    kind: str
    raw_text: str
    normalized_text: str
    reading_order: int
    locator: ExactLocator
    font_name: str | None = None
    font_size: Decimal | None = None
    rotation_degrees: int = 0
    row_index: int | None = None
    column_index: int | None = None


@dataclass(frozen=True, slots=True)
class RoleCandidate:
    candidate_id: UUID
    role: DocumentRole
    scope: str
    score: Decimal
    signal_codes: tuple[str, ...]
    locators: tuple[ExactLocator, ...]
    extraction_profile_version: str
    model_attempt_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.locators or not Decimal("0") <= self.score <= Decimal("1"):
            raise ValueError("role candidate requires bounded score and evidence")


@dataclass(frozen=True, slots=True)
class RoleDecision:
    decision_id: UUID
    decision_version: int
    scope: str
    selected_roles: tuple[DocumentRole, ...]
    candidate_ids: tuple[UUID, ...]
    decision_code: str
    validator_version: str
    locators: tuple[ExactLocator, ...]

    def __post_init__(self) -> None:
        if self.decision_version < 1 or not self.selected_roles or not self.locators:
            raise ValueError("role decision requires selected evidence-bound roles")


@dataclass(frozen=True, slots=True)
class ProjectFieldCandidate:
    candidate_id: UUID
    field_key: str
    raw_value: str
    normalized_value: str
    value_type: str
    locator: ExactLocator
    extraction_method: str
    uncertainty_codes: tuple[str, ...]
    status: CandidateDecision = CandidateDecision.CANDIDATE


@dataclass(frozen=True, slots=True)
class WorkTypeCandidate:
    candidate_id: UUID
    raw_name: str
    normalized_name: str
    scope_key: str
    locator: ExactLocator
    source_role: DocumentRole
    canonical_mapping_status: MappingStatus = MappingStatus.UNRESOLVED
    canonical_work_type_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class QuantityCandidate:
    candidate_id: UUID
    work_candidate_id: UUID
    raw_value: str
    parsed_value: Decimal | None
    raw_unit: str
    normalized_value: Decimal | None
    normalized_unit: str | None
    conversion_rule_version: str | None
    scope_key: str
    locator: ExactLocator
    status: CandidateDecision


@dataclass(frozen=True, slots=True)
class MaterialCandidate:
    candidate_id: UUID
    work_candidate_id: UUID
    raw_name: str
    normalized_name: str
    raw_quantity: str | None
    parsed_quantity: Decimal | None
    raw_unit: str | None
    normalized_unit: str | None
    locator: ExactLocator
    status: CandidateDecision


@dataclass(frozen=True, slots=True)
class EstimatePositionCandidate:
    candidate_id: UUID
    raw_position: str
    normalized_description: str
    raw_quantity: str | None
    parsed_quantity: Decimal | None
    raw_unit: str | None
    locator: ExactLocator


@dataclass(frozen=True, slots=True)
class ReconciliationDefect:
    defect_id: UUID
    kind: ReconciliationDefectKind
    subject_identity: str
    related_identity: str | None
    evidence_locators: tuple[ExactLocator, ...]
    parameters: dict[str, Any]
    blocking: bool


@dataclass(frozen=True, slots=True)
class WorkTypeCatalogImport:
    catalog_id: UUID
    version: int
    source_identity: str
    source_version: str
    source_digest: str
    provenance: dict[str, Any]
    status: str


@dataclass(frozen=True, slots=True)
class ProjectUnderstandingSnapshot:
    run_id: UUID | None
    run_version: int | None
    status: str
    document_count: int
    page_count: int
    page_health_counts: dict[str, int]
    route_counts: dict[str, int]
    page_roles: tuple[dict[str, Any], ...]
    project_definition: dict[str, Any] | None
    project_fields: tuple[dict[str, Any], ...]
    structure_nodes: tuple[dict[str, Any], ...]
    work_types: tuple[dict[str, Any], ...]
    quantities: tuple[dict[str, Any], ...]
    materials: tuple[dict[str, Any], ...]
    work_packages: tuple[dict[str, Any], ...]
    matrix: dict[str, Any] | None
    defects: tuple[dict[str, Any], ...]
    gaps: tuple[str, ...]
    structural_fingerprint: str | None
