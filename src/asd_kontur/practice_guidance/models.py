"""Typed values for evidence-bound methodological-guide ingestion.

These values deliberately have no ``workspace_id``. A practice guide is a
platform source, but it is neither NTD nor an authority for project facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from asd_kontur.harness.models import digest_of


class GuideAuthorityLayer(StrEnum):
    METHODOLOGICAL_GUIDANCE = "methodological_guidance"


class GuideContentKind(StrEnum):
    NATIVE_TEXT = "native_text"
    RASTER_IMAGE = "raster_image"
    MIXED = "mixed"
    BLANK_OR_TECHNICAL = "blank_or_technical"


class GuidanceKind(StrEnum):
    ID_WORKFLOW_GUIDANCE = "id_workflow_guidance"
    DOCUMENT_FORM_GUIDANCE = "document_form_guidance"
    FORM_FIELD_GUIDANCE = "form_field_guidance"
    COMPLETION_INSTRUCTION = "completion_instruction"
    REQUIRED_INPUT_GUIDANCE = "required_input_guidance"
    EVIDENCE_REQUIREMENT_GUIDANCE = "evidence_requirement_guidance"
    SIGNER_ROLE_GUIDANCE = "signer_role_guidance"
    COMMON_ERROR = "common_error"
    GOOD_PRACTICE_ASSERTION = "good_practice_assertion"
    VISUAL_INSTRUCTION = "visual_instruction"
    EXAMPLE_REFERENCE = "example_reference"
    CROSS_REFERENCE = "cross_reference"
    GUIDE_NTD_RELEVANCE_ASSERTION = "guide_ntd_relevance_assertion"


class NormativeReferenceResolutionState(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class VerificationDisposition(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT = "insufficient"
    MODEL_FAILED = "model_failed"


class GuideTerminalState(StrEnum):
    VERIFIED = "verified"
    PARTIAL_WITH_GAPS = "partial_with_gaps"
    NO_METHODOLOGICAL_CONTENT = "no_methodological_content"
    UNRESOLVED = "unresolved"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    MODEL_FAILED = "model_failed"
    TECHNICALLY_BLOCKED = "technically_blocked"


class GuidanceIssueState(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class CandidateTerminalStatus(StrEnum):
    SUPPORTED = "supported"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"
    INSUFFICIENT = "insufficient"
    MODEL_FAILED = "model_failed"


@dataclass(frozen=True, slots=True)
class GuidanceCuratorAuthority:
    identity_id: str
    is_human: bool
    capabilities: frozenset[str]

    def require_publication(self) -> None:
        if not self.is_human or "methodological_guidance.publish" not in self.capabilities:
            raise PermissionError(
                "Publishing canonical methodological guidance requires qualified human authority"
            )

    def require_conflict_recording(self) -> None:
        if not self.is_human or "methodological_guidance.conflict.record" not in self.capabilities:
            raise PermissionError(
                "Recording a guidance/authority conflict requires qualified human authority"
            )


@dataclass(frozen=True, slots=True)
class GuideLocator:
    page_number: int
    region: tuple[float, float, float, float]
    coordinate_space: str = "normalized_page"

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("Guide page locators are one-based")
        x0, y0, x1, y1 = self.region
        if self.coordinate_space != "normalized_page":
            raise ValueError("Only normalized page locators are canonical")
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("Guide region must be inside the normalized page")

    @property
    def key(self) -> str:
        values = ",".join(f"{value:.6f}" for value in self.region)
        return f"page:{self.page_number}:region:{values}"


@dataclass(frozen=True, slots=True)
class GuideSourceRow:
    """A deterministic source table row; no model-generated geometry is accepted."""

    source_row_id: UUID
    parent_candidate_id: UUID
    parent_candidate_version: int
    source_version_id: UUID
    page_number: int
    row_ordinal: int
    locator: GuideLocator
    printed_ntd: str
    work_or_rd_sections: str
    id_note: str
    layout_profile_version: str
    extraction_digest: str
    parent_failed_receipt_digest: str

    def __post_init__(self) -> None:
        if (
            self.page_number != self.locator.page_number
            or self.row_ordinal < 1
            or self.parent_candidate_version < 1
        ):
            raise ValueError("Guide source-row identity and locator must agree")
        if not self.printed_ntd.strip() or not self.id_note.strip():
            raise ValueError("Every guide NTD source row requires its NTD and ID-note columns")
        if not self.layout_profile_version:
            raise ValueError("Guide source row requires an exact layout profile")
        if not self.extraction_digest.startswith("sha256:"):
            raise ValueError("Guide source row requires immutable extraction evidence")
        if not self.parent_failed_receipt_digest.startswith("sha256:"):
            raise ValueError("Guide source row requires failed-page receipt lineage")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class NormativeReferenceCandidate:
    reference_candidate_id: UUID
    printed_identifier: str
    printed_title: str | None
    resolution_state: NormativeReferenceResolutionState
    uncertainty_code: str
    normative_document_id: UUID | None = None
    normative_edition_id: UUID | None = None

    def __post_init__(self) -> None:
        linked = self.normative_document_id is not None and self.normative_edition_id is not None
        if self.resolution_state is NormativeReferenceResolutionState.RESOLVED:
            if not linked:
                raise ValueError("Resolved NTD references require document and edition identities")
        elif self.normative_document_id is not None or self.normative_edition_id is not None:
            raise ValueError("Unresolved NTD references cannot retain a partial canonical link")
        if not self.printed_identifier.strip() or not self.uncertainty_code:
            raise ValueError("NTD reference candidates preserve an exact printed identifier")

    @property
    def identity_fingerprint(self) -> str:
        return digest_of(
            {
                "reference_candidate_id": self.reference_candidate_id,
                "printed_identifier": self.printed_identifier,
                "printed_title": self.printed_title,
            }
        )

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class GuideNtdRelevanceAssertion:
    assertion_id: UUID
    candidate_id: UUID
    parent_candidate_version: int
    source_row_id: UUID
    source_version_id: UUID
    locator: GuideLocator
    printed_identifier: str
    printed_title: str | None
    work_or_rd_sections: str
    id_note: str
    relevance_summary: str
    document_or_form_type: str | None
    workflow_stage: str | None
    applicability_conditions: tuple[str, ...]
    uncertainty_codes: tuple[str, ...]
    normative_reference: NormativeReferenceCandidate
    model_profile_fingerprint: str

    def __post_init__(self) -> None:
        if self.parent_candidate_version < 1:
            raise ValueError("Guide NTD assertion requires parent CandidateVersion lineage")
        if not all(
            value.strip()
            for value in (
                self.printed_identifier,
                self.id_note,
                self.relevance_summary,
            )
        ):
            raise ValueError("Guide NTD assertions require complete source-row semantics")
        if not self.model_profile_fingerprint.startswith("sha256:"):
            raise ValueError("Guide NTD assertions require exact model provenance")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class GuidePageManifest:
    source_version_id: UUID
    page_number: int
    page_digest: str
    width_points: float
    height_points: float
    rotation: int
    native_text_characters: int
    image_count: int
    content_kind: GuideContentKind
    render_required: bool
    previous_page: int | None
    next_page: int | None
    technical_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.page_number < 1 or self.width_points <= 0 or self.height_points <= 0:
            raise ValueError("Page manifest has an invalid page box or number")
        if not self.page_digest.startswith("sha256:"):
            raise ValueError("Page manifest requires a SHA-256 digest")
        if self.native_text_characters < 0 or self.image_count < 0:
            raise ValueError("Page manifest counts cannot be negative")
        if self.previous_page not in {None, self.page_number - 1}:
            raise ValueError("Previous-page lineage is not contiguous")
        if self.next_page not in {None, self.page_number + 1}:
            raise ValueError("Next-page lineage is not contiguous")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class GuideExecutionProfile:
    provider: str
    model_identity: str
    model_revision: str
    model_digest: str
    execution_format: str
    quantization: str
    runtime_version: str
    execution_profile: str
    prompt_version: str
    schema_version: str
    preprocessing_version: str
    renderer_version: str
    verification_policy_version: str
    deterministic_decoding: bool

    def __post_init__(self) -> None:
        exact = (
            self.provider,
            self.model_identity,
            self.model_revision,
            self.model_digest,
            self.execution_format,
            self.quantization,
            self.runtime_version,
            self.execution_profile,
            self.prompt_version,
            self.schema_version,
            self.preprocessing_version,
            self.renderer_version,
            self.verification_policy_version,
        )
        if any(not item or item.lower() == "latest" for item in exact):
            raise ValueError("Every guide execution profile component must be exact")
        if not self.model_digest.startswith("sha256:"):
            raise ValueError("The model profile requires an immutable digest")
        if self.quantization not in {"8bit", "bf16"}:
            raise ValueError("Practice-guide ingestion permits exact 8-bit or BF16 profiles only")
        if not self.deterministic_decoding:
            raise ValueError("Guide ingestion requires deterministic decoding")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class GuidanceCandidateVersion:
    candidate_id: UUID
    version: int
    source_version_id: UUID
    locator: GuideLocator
    kind: GuidanceKind
    section: str
    topic: str
    document_or_form_type: str | None
    workflow_stage: str | None
    field_or_element: str | None
    instruction: str
    required_inputs: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    author_role_claims: tuple[str, ...]
    common_error: str | None
    recommended_practice: str | None
    visual_example_locator: GuideLocator | None
    applicability_conditions: tuple[str, ...]
    limitations: tuple[str, ...]
    uncertainties: tuple[str, ...]
    model_profile_fingerprint: str
    parent_version: int | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("CandidateVersion starts at one")
        if self.parent_version is not None and self.parent_version >= self.version:
            raise ValueError("Candidate parent version must precede the new version")
        if not self.instruction.strip():
            raise ValueError("A guidance candidate cannot contain an empty instruction")
        if not self.model_profile_fingerprint.startswith("sha256:"):
            raise ValueError("Candidate requires exact model provenance")
        if (
            self.visual_example_locator is not None
            and self.visual_example_locator.page_number != self.locator.page_number
            and self.kind is GuidanceKind.VISUAL_INSTRUCTION
        ):
            raise ValueError("Visual instruction locator must identify its evidence page")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class GuideValidationFailure:
    failure_code: str
    validator_version: str
    candidate_id: UUID
    candidate_version: int
    field_path: str
    blocking: bool
    repairable: bool
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GuidanceVerification:
    verification_id: UUID
    candidate_id: UUID
    candidate_version: int
    disposition: VerificationDisposition
    source_version_id: UUID
    locator: GuideLocator
    model_profile_fingerprint: str
    verification_prompt_version: str
    result_digest: str
    failures: tuple[GuideValidationFailure, ...]
    verified_at: datetime

    def __post_init__(self) -> None:
        if not self.result_digest.startswith("sha256:"):
            raise ValueError("Verification requires an immutable result digest")
        if self.disposition is VerificationDisposition.SUPPORTED and any(
            failure.blocking for failure in self.failures
        ):
            raise ValueError("A supported candidate cannot retain blocking failures")


@dataclass(frozen=True, slots=True)
class GuidanceConflict:
    conflict_id: UUID
    guidance_unit_id: UUID
    guidance_unit_version: int
    conflicting_authority_layer: str
    conflicting_subject_ref: str
    conflict_type: str
    uncertainty_ref: str
    state: GuidanceIssueState = GuidanceIssueState.OPEN
    decision_ref: str | None = None

    def __post_init__(self) -> None:
        if self.guidance_unit_version < 1:
            raise ValueError("Guidance conflict requires an exact positive unit version")
        if self.conflicting_authority_layer == GuideAuthorityLayer.METHODOLOGICAL_GUIDANCE:
            raise ValueError("Cross-authority conflict must identify another authority layer")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class GuidanceUncertainty:
    uncertainty_id: UUID
    guidance_unit_id: UUID
    guidance_unit_version: int
    uncertainty_code: str
    content_minimal_parameters: dict[str, Any]
    state: GuidanceIssueState = GuidanceIssueState.OPEN

    def __post_init__(self) -> None:
        if self.guidance_unit_version < 1 or not self.uncertainty_code:
            raise ValueError("Guidance uncertainty requires exact identity and code")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class CoverageManifest:
    coverage_manifest_id: UUID
    practice_guide_edition_id: UUID
    ingestion_run_id: UUID
    version: int
    publication_status: str
    expected_page_count: int
    terminal_page_count: int
    page_state_counts: dict[str, int]
    candidate_state_counts: dict[str, int]
    guidance_unit_count: int
    gap_count: int
    conflict_count: int
    reconciliation_fingerprint: str
    manifest_fingerprint: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if self.version < 1 or self.expected_page_count < 1:
            raise ValueError("CoverageManifest requires positive versions and page count")
        if self.terminal_page_count != self.expected_page_count:
            raise ValueError("CoverageManifest requires every page identity to be terminal")
        if self.publication_status not in {"complete", "partial_with_explicit_gaps"}:
            raise ValueError("CoverageManifest publication status is invalid")
        if min(self.guidance_unit_count, self.gap_count, self.conflict_count) < 0:
            raise ValueError("CoverageManifest counts cannot be negative")
        if not self.reconciliation_fingerprint.startswith("sha256:"):
            raise ValueError("CoverageManifest requires reconciliation lineage")
        if not self.manifest_fingerprint.startswith("sha256:"):
            raise ValueError("CoverageManifest requires an immutable fingerprint")


@dataclass(frozen=True, slots=True)
class GuidanceGap:
    guidance_gap_id: UUID
    coverage_manifest_id: UUID
    source_version_id: UUID
    page_number: int
    candidate_id: UUID | None
    candidate_version: int | None
    gap_code: str
    terminal_state: GuideTerminalState
    topic: str | None
    document_or_form_type: str | None
    field_or_element: str | None
    searchable_text: str
    content_minimal_parameters: dict[str, Any]
    gap_fingerprint: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if self.page_number < 1 or not self.gap_code or not self.searchable_text.strip():
            raise ValueError("GuidanceGap requires a page, code and searchable context")
        if (self.candidate_id is None) != (self.candidate_version is None):
            raise ValueError("GuidanceGap CandidateVersion identity must be complete")
        if self.terminal_state not in {
            GuideTerminalState.PARTIAL_WITH_GAPS,
            GuideTerminalState.INSUFFICIENT_EVIDENCE,
            GuideTerminalState.MODEL_FAILED,
            GuideTerminalState.TECHNICALLY_BLOCKED,
        }:
            raise ValueError("GuidanceGap requires a gap-bearing terminal page state")
        if not self.gap_fingerprint.startswith("sha256:"):
            raise ValueError("GuidanceGap requires an immutable fingerprint")


@dataclass(frozen=True, slots=True)
class GuidePageTerminalReceipt:
    ingestion_run_id: UUID
    source_version_id: UUID
    page_number: int
    state: GuideTerminalState
    pass_a_attempt_id: UUID | None
    pass_b_attempt_id: UUID | None
    candidate_count: int
    verified_count: int
    unresolved_count: int
    receipt_digest: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("Terminal receipts use one-based pages")
        if min(self.candidate_count, self.verified_count, self.unresolved_count) < 0:
            raise ValueError("Terminal receipt counts cannot be negative")
        if self.verified_count > self.candidate_count:
            raise ValueError("Verified receipt candidates exceed the candidate total")
        if self.state is GuideTerminalState.VERIFIED and self.verified_count == 0:
            raise ValueError("Verified pages require at least one verified guidance unit")
        if self.state is GuideTerminalState.PARTIAL_WITH_GAPS and (
            self.verified_count == 0 or self.unresolved_count == 0
        ):
            raise ValueError("Partial pages require both verified guidance and explicit gaps")
        if self.state is GuideTerminalState.NO_METHODOLOGICAL_CONTENT and self.candidate_count:
            raise ValueError("No-content pages cannot retain candidates")
        if self.state is GuideTerminalState.INSUFFICIENT_EVIDENCE and self.unresolved_count == 0:
            raise ValueError("Insufficient-evidence pages require unresolved candidates")
        if not self.receipt_digest.startswith("sha256:"):
            raise ValueError("Terminal receipt requires a digest")


@dataclass(frozen=True, slots=True)
class GuideIngestionReconciliation:
    ingestion_run_id: UUID
    expected_pages: int
    terminal_pages: tuple[int, ...]
    verified_pages: tuple[int, ...]
    partial_pages: tuple[int, ...]
    no_content_pages: tuple[int, ...]
    unresolved_pages: tuple[int, ...]
    insufficient_pages: tuple[int, ...]
    failed_pages: tuple[int, ...]
    blocked_pages: tuple[int, ...]
    complete: bool
    fingerprint: str


def reconcile_page_receipts(
    ingestion_run_id: UUID,
    expected_pages: int,
    receipts: tuple[GuidePageTerminalReceipt, ...],
) -> GuideIngestionReconciliation:
    if expected_pages < 1:
        raise ValueError("Expected page count must be positive")
    if any(receipt.ingestion_run_id != ingestion_run_id for receipt in receipts):
        raise ValueError("Cross-run receipts cannot be reconciled")
    pages = [receipt.page_number for receipt in receipts]
    if len(pages) != len(set(pages)):
        raise ValueError("Duplicate page terminal receipt")
    if any(page > expected_pages for page in pages):
        raise ValueError("Terminal receipt is outside the source page count")
    by_state = {
        state: tuple(sorted(r.page_number for r in receipts if r.state is state))
        for state in GuideTerminalState
    }
    terminal = tuple(sorted(pages))
    complete = terminal == tuple(range(1, expected_pages + 1))
    payload = {
        "ingestion_run_id": str(ingestion_run_id),
        "expected_pages": expected_pages,
        "terminal_pages": terminal,
        "states": {state.value: by_state[state] for state in GuideTerminalState},
        "complete": complete,
    }
    return GuideIngestionReconciliation(
        ingestion_run_id=ingestion_run_id,
        expected_pages=expected_pages,
        terminal_pages=terminal,
        verified_pages=by_state[GuideTerminalState.VERIFIED],
        partial_pages=by_state[GuideTerminalState.PARTIAL_WITH_GAPS],
        no_content_pages=by_state[GuideTerminalState.NO_METHODOLOGICAL_CONTENT],
        unresolved_pages=by_state[GuideTerminalState.UNRESOLVED],
        insufficient_pages=by_state[GuideTerminalState.INSUFFICIENT_EVIDENCE],
        failed_pages=by_state[GuideTerminalState.MODEL_FAILED],
        blocked_pages=by_state[GuideTerminalState.TECHNICALLY_BLOCKED],
        complete=complete,
        fingerprint=digest_of(payload),
    )
