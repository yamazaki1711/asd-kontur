"""Typed immutable contracts for permanent normative platform knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from asd_kontur.harness.models import digest_of

NORMATIVE_AUTHORITY_LAYER = "normative_authority"
PERMANENT_NTD_RETENTION_CLASS = "permanent_platform_core"


class AcquisitionTerminalStatus(StrEnum):
    RESOLVED_EXACT = "resolved_exact"
    RESOLVED_SUPERSEDED = "resolved_superseded"
    AMBIGUOUS_OFFICIAL_RECORDS = "ambiguous_official_records"
    OFFICIAL_METADATA_ONLY = "official_metadata_only"
    OFFICIAL_ARTIFACT_UNAVAILABLE = "official_artifact_unavailable"
    OFFICIAL_ACCESS_BLOCKED = "official_access_blocked"
    NOT_FOUND_OFFICIAL = "not_found_official"
    EXACT_EDITION_NOT_FOUND = "exact_edition_not_found"
    EDITION_CONFLICT = "edition_conflict"
    SUPERSESSION_UNRESOLVED = "supersession_unresolved"
    DOWNLOAD_FAILED = "download_failed"
    ARTIFACT_INVALID = "artifact_invalid"
    PARSE_PARTIAL = "parse_partial"
    PARSED_VERIFIED = "parsed_verified"
    BLOCKED_DETERMINISTIC_FAILURE = "blocked_deterministic_failure"


class EditionRelationshipKind(StrEnum):
    SUPERSEDES = "supersedes"
    SUPERSEDED_BY = "superseded_by"
    AMENDS = "amends"
    AMENDED_BY = "amended_by"
    REPLACES = "replaces"
    DERIVED_FROM = "derived_from"
    EFFECTIVE_FROM = "effective_from"
    EFFECTIVE_TO = "effective_to"
    UNKNOWN_RELATION = "unknown_relation"


class NormativeProvisionKind(StrEnum):
    SECTION = "section"
    CLAUSE = "clause"
    SUBCLAUSE = "subclause"
    TABLE = "table"
    APPENDIX = "appendix"
    FORM = "form"
    DEFINITION = "definition"
    OTHER = "other"


class ProvisionVerificationStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


class PracticeNtdAlignmentStatus(StrEnum):
    CONFIRMED_BY_NTD = "confirmed_by_ntd"
    PRACTICE_ONLY = "practice_only"
    NORMATIVE_CONFLICT = "normative_conflict"
    EDITION_WARNING = "edition_warning"
    UNRESOLVED = "unresolved"


class OfficialProvider(StrEnum):
    GOVERNMENT_PORTAL = "government_portal"
    OFFICIAL_LEGAL_PUBLICATION = "official_legal_publication"
    ROSSTANDART_FUND = "rosstandart_fund"
    MINSTROY_CATALOGUE = "minstroy_catalogue"


class ProviderAccessStatus(StrEnum):
    AVAILABLE = "available"
    ACCESS_BLOCKED = "access_blocked"
    NETWORK_UNAVAILABLE = "network_unavailable"
    TLS_VERIFICATION_FAILED = "tls_verification_failed"
    PROXY_MISCONFIGURED = "proxy_misconfigured"
    HTTP_ACCESS_DENIED = "http_access_denied"
    AUTHENTICATION_REQUIRED = "authentication_required"
    LICENSE_RESTRICTED = "license_restricted"
    ARTIFACT_UNAVAILABLE = "artifact_unavailable"
    UNEXPECTED_MIME = "unexpected_mime"
    INVALID_BYTES = "invalid_bytes"
    UNSUPPORTED_VIEWER_PROTOCOL = "unsupported_viewer_protocol"
    PARSER_FAILURE = "parser_failure"
    INVALID_RESPONSE = "invalid_response"


class CorpusMemberStatus(StrEnum):
    ACTIVE = "active"
    REPLACED = "replaced"
    CANCELLED = "cancelled"
    NOT_EFFECTIVE_IN_RF = "not_effective_in_rf"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OfficialProviderHealthReceipt:
    receipt_id: UUID
    provider: OfficialProvider
    endpoint: str
    transport_profile: str
    checked_at: datetime
    status: ProviderAccessStatus
    http_status: int | None
    response_digest: str | None
    failure_code: str | None
    diagnostic: dict[str, Any] | None = None

    @property
    def fingerprint(self) -> str:
        # Receipt identity deliberately includes ``checked_at``. Provider health is an
        # observation, not a semantic corpus snapshot.
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class NormativeCorpusMember:
    member_id: UUID
    ordinal: int
    stable_identity_key: str
    designation: str
    title: str
    catalog_id: str
    catalog_url: str
    status: CorpusMemberStatus
    replaces_designation: str | None
    replaced_by_designation: str | None
    scope_text: str | None
    official_metadata: dict[str, Any]
    acquisition_status: AcquisitionTerminalStatus
    metadata_digest: str


@dataclass(frozen=True, slots=True)
class NormativeCorpusManifest:
    manifest_id: UUID
    version: int
    corpus_key: str
    query: str
    provider: OfficialProvider
    query_endpoints: tuple[str, ...]
    denominator: int
    members: tuple[NormativeCorpusMember, ...]
    parser_version: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.version < 1 or self.denominator < 1:
            raise ValueError("Normative corpus manifest requires a positive denominator")
        if self.denominator != len(self.members):
            raise ValueError("Normative corpus denominator must equal exact member count")
        if tuple(member.ordinal for member in self.members) != tuple(
            range(1, self.denominator + 1)
        ):
            raise ValueError("Normative corpus ordinals must be contiguous")
        catalog_ids = [member.catalog_id for member in self.members]
        if len(catalog_ids) != len(set(catalog_ids)):
            raise ValueError("Normative corpus contains duplicate official catalog records")

    @property
    def fingerprint(self) -> str:
        # Run identities and wall-clock acquisition metadata must not make the same
        # official denominator appear semantically different on a later retrieval.
        # Member UUIDs are likewise storage identities; the official catalog identity
        # and normalized semantic fields define the manifest.
        return digest_of(
            {
                "fingerprint_schema": "normative_corpus_manifest_semantic_v1",
                "version": self.version,
                "corpus_key": self.corpus_key,
                "query": self.query,
                "provider": self.provider,
                "query_endpoints": self.query_endpoints,
                "denominator": self.denominator,
                "parser_version": self.parser_version,
                "members": [
                    {
                        "ordinal": member.ordinal,
                        "stable_identity_key": member.stable_identity_key,
                        "designation": member.designation,
                        "title": member.title,
                        "catalog_id": member.catalog_id,
                        "catalog_url": member.catalog_url,
                        "status": member.status,
                        "replaces_designation": member.replaces_designation,
                        "replaced_by_designation": member.replaced_by_designation,
                        "scope_text": member.scope_text,
                        "official_metadata": member.official_metadata,
                        "acquisition_status": member.acquisition_status,
                        "metadata_digest": member.metadata_digest,
                    }
                    for member in self.members
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class ApplicabilityPredicate:
    predicate_id: UUID
    version: int
    provision_id: UUID
    provision_version: int
    predicate: dict[str, Any]
    required_inputs: tuple[str, ...]
    exclusions: tuple[dict[str, Any], ...]
    semantic_fingerprint: str

    def __post_init__(self) -> None:
        expected = self.compute_fingerprint(
            provision_id=self.provision_id,
            provision_version=self.provision_version,
            predicate=self.predicate,
            required_inputs=self.required_inputs,
            exclusions=self.exclusions,
        )
        if self.version < 1 or self.provision_version < 1 or self.semantic_fingerprint != expected:
            raise ValueError("Applicability predicate semantic fingerprint is invalid")

    @staticmethod
    def compute_fingerprint(
        *,
        provision_id: UUID,
        provision_version: int,
        predicate: dict[str, Any],
        required_inputs: tuple[str, ...],
        exclusions: tuple[dict[str, Any], ...],
    ) -> str:
        return digest_of(
            {
                "fingerprint_schema": "normative_applicability_predicate_v1",
                "provision_id": provision_id,
                "provision_version": provision_version,
                "predicate": predicate,
                "required_inputs": sorted(required_inputs),
                "exclusions": exclusions,
            }
        )


@dataclass(frozen=True, slots=True)
class ApplicablePdRdNormativeProfile:
    profile_id: UUID
    version: int
    workspace_id: UUID
    project_definition_id: UUID
    project_definition_version: int
    applicable_on: date | None
    input_fingerprint: str
    corpus_denominator: dict[str, Any]
    normative_edition_ids: tuple[UUID, ...]
    rule_version_ids: tuple[UUID, ...]
    required_pd_sections: tuple[dict[str, Any], ...]
    expected_rd_sets: tuple[dict[str, Any], ...]
    formatting_requirements: tuple[dict[str, Any], ...]
    unresolved_inputs: tuple[str, ...]
    gaps: tuple[dict[str, Any], ...]
    completeness_status: str
    semantic_fingerprint: str


@dataclass(frozen=True, slots=True)
class RuleNormativeProvisionEvidence:
    evidence_id: UUID
    rule_version_id: UUID
    normative_provision_id: UUID
    normative_provision_version: int
    normative_edition_id: UUID
    source_version_id: UUID
    source_locator_id: UUID
    applicability_predicate_id: UUID
    applicability_predicate_version: int
    qualification_decision_ref: str
    evidence_digest: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if self.normative_provision_version < 1 or self.applicability_predicate_version < 1:
            raise ValueError("Rule normative evidence versions must be positive")
        if not self.qualification_decision_ref or not self.evidence_digest.startswith("sha256:"):
            raise ValueError("Rule normative evidence requires exact qualification lineage")


@dataclass(frozen=True, slots=True)
class OfficialHttpMetadata:
    request_url: str
    final_url: str
    status_code: int
    content_type: str | None
    etag: str | None
    last_modified: str | None
    byte_length: int
    retrieved_at: datetime
    redirect_chain: tuple[str, ...] = ()
    response_headers: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.request_url.startswith("https://") or not self.final_url.startswith("https://"):
            raise ValueError("Official transport requires HTTPS")
        if self.status_code < 100 or self.status_code > 599 or self.byte_length < 0:
            raise ValueError("Official HTTP metadata is invalid")


@dataclass(frozen=True, slots=True)
class CatalogueCandidate:
    catalog_id: str
    catalog_url: str
    title: str
    matched_designation: str
    catalogue_artifact_urls: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OfficialCatalogueRecord:
    catalog_id: str
    catalog_url: str
    title: str
    published_at: date | None
    approving_authority: str | None
    approval_reference: str | None
    effective_from: date | None
    effective_to: date | None
    status_text: str | None
    artifact_urls: tuple[str, ...]
    metadata: OfficialHttpMetadata
    metadata_digest: str

    def __post_init__(self) -> None:
        if not self.catalog_id or not self.title or not self.metadata_digest.startswith("sha256:"):
            raise ValueError("Official catalogue record requires identity and digest")


@dataclass(frozen=True, slots=True)
class AcquisitionReceipt:
    receipt_id: UUID
    normalized_query: str
    official_endpoint: str
    requested_at: datetime
    returned_catalog_ids: tuple[str, ...]
    selected_catalog_id: str | None
    selection_reason: str | None
    rejected_candidates: tuple[dict[str, str], ...]
    artifact_url: str | None
    http_metadata: OfficialHttpMetadata | None
    content_digest: str | None
    parser_version: str
    terminal_status: AcquisitionTerminalStatus
    failure_code: str | None
    previous_receipt_id: UUID | None = None

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class NormativeArtifact:
    normative_artifact_id: UUID
    normative_edition_id: UUID
    source_version_id: UUID
    official_catalog_id: str
    official_url: str
    filename: str
    media_type: str
    size_bytes: int
    content_digest: str
    relation_to_edition: str
    retrieval_metadata_digest: str

    def __post_init__(self) -> None:
        if self.size_bytes < 1 or not self.content_digest.startswith("sha256:"):
            raise ValueError("Normative artifact requires non-empty exact bytes")
        if not self.official_url.startswith("https://"):
            raise ValueError("Normative artifact must use an official HTTPS locator")


@dataclass(frozen=True, slots=True)
class NormativeEditionRelationship:
    relationship_id: UUID
    from_edition_id: UUID
    to_edition_id: UUID
    relation_kind: EditionRelationshipKind
    official_evidence_ref: str
    source_locator_id: UUID | None
    verification_status: str

    def __post_init__(self) -> None:
        if self.from_edition_id == self.to_edition_id:
            raise ValueError("An edition cannot relate to itself")
        if not self.official_evidence_ref.strip():
            raise ValueError("Edition relationship requires official evidence")


@dataclass(frozen=True, slots=True)
class NormativeProvisionCandidate:
    candidate_id: UUID
    candidate_version: int
    normative_edition_id: UUID
    source_version_id: UUID
    structural_path: str
    provision_kind: NormativeProvisionKind
    page_number: int | None
    region: tuple[float, float, float, float] | None
    verbatim_text: str
    extraction_method: str
    extraction_profile_version: str
    content_digest: str
    model_provenance: dict[str, Any] | None

    def __post_init__(self) -> None:
        if self.candidate_version < 1 or not self.structural_path or not self.verbatim_text:
            raise ValueError("Normative provision candidate is incomplete")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("Normative provision candidate requires a content digest")
        _validate_region(self.page_number, self.region)


@dataclass(frozen=True, slots=True)
class NormativeProvisionVersion:
    provision_id: UUID
    version: int
    candidate_id: UUID
    candidate_version: int
    normative_edition_id: UUID
    source_version_id: UUID
    structural_path: str
    provision_kind: NormativeProvisionKind
    page_number: int | None
    region: tuple[float, float, float, float] | None
    verbatim_text: str
    content_digest: str
    semantic_fingerprint: str
    verification_status: ProvisionVerificationStatus
    verification_decision_ref: str
    verified_by_identity_id: str
    verified_at: datetime

    def __post_init__(self) -> None:
        if self.version < 1 or self.candidate_version < 1:
            raise ValueError("Normative provision versions must be positive")
        if self.verification_status is ProvisionVerificationStatus.VERIFIED and (
            not self.structural_path
            or not self.verbatim_text
            or not self.content_digest.startswith("sha256:")
            or not self.semantic_fingerprint.startswith("sha256:")
            or not self.verification_decision_ref
        ):
            raise ValueError("Verified normative provision requires exact evidence")
        _validate_region(self.page_number, self.region)


@dataclass(frozen=True, slots=True)
class NormativeActivationDecision:
    decision_id: UUID
    decision_version: int
    normative_document_id: UUID
    selected_edition_id: UUID
    as_of: date
    status: str
    authority_reference: str
    evidence_refs: tuple[str, ...]
    supersedes_decision_version: int | None
    decided_at: datetime

    def __post_init__(self) -> None:
        if self.decision_version < 1 or not self.authority_reference or not self.evidence_refs:
            raise ValueError("Normative activation requires explicit versioned authority")
        if (self.decision_version == 1) != (self.supersedes_decision_version is None):
            raise ValueError("Normative activation decision lineage is invalid")


@dataclass(frozen=True, slots=True)
class NormativeApplicabilityDecision:
    decision_id: UUID
    decision_version: int
    normative_edition_id: UUID
    scope_kind: str
    scope_ref: str | None
    as_of: date
    applicability_status: str
    predicate: dict[str, Any]
    evidence_refs: tuple[str, ...]
    decided_by_identity_id: str
    decided_at: datetime

    def __post_init__(self) -> None:
        if self.decision_version < 1 or not self.scope_kind or not self.applicability_status:
            raise ValueError("Applicability decision is incomplete")
        if not self.evidence_refs:
            raise ValueError("Applicability cannot be inferred without evidence")


@dataclass(frozen=True, slots=True)
class PracticeNtdAlignment:
    alignment_id: UUID
    alignment_version: int
    practice_guide_reference_id: UUID
    guidance_unit_id: UUID | None
    guidance_unit_version: int | None
    normative_document_id: UUID | None
    normative_edition_id: UUID | None
    provision_id: UUID | None
    provision_version: int | None
    status: PracticeNtdAlignmentStatus
    as_of: date
    evidence_refs: tuple[str, ...]
    decision_ref: str
    decided_at: datetime

    def __post_init__(self) -> None:
        if self.alignment_version < 1 or not self.decision_ref:
            raise ValueError("Practice/NTD alignment requires a versioned decision")
        if self.status is PracticeNtdAlignmentStatus.CONFIRMED_BY_NTD and (
            self.normative_edition_id is None or self.provision_id is None
        ):
            raise ValueError("Confirmed alignment requires an exact verified provision")


@dataclass(frozen=True, slots=True)
class NtdBackupManifest:
    backup_manifest_id: UUID
    version: int
    seed_manifest_fingerprint: str
    source_versions: tuple[tuple[UUID, str], ...]
    edition_fingerprints: tuple[tuple[UUID, str], ...]
    provision_fingerprints: tuple[tuple[UUID, int, str], ...]
    activation_decision_refs: tuple[tuple[UUID, int], ...]
    rule_candidate_fingerprints: tuple[tuple[UUID, int, str], ...]
    rule_qualification_fingerprints: tuple[tuple[UUID, int, str], ...]
    rule_activation_fingerprints: tuple[tuple[UUID, int, str], ...]
    gap_fingerprints: tuple[str, ...]
    conflict_fingerprints: tuple[str, ...]
    projection_profile_version: str
    canonical_semantic_fingerprint: str
    created_at: datetime

    def __post_init__(self) -> None:
        digests = (
            self.seed_manifest_fingerprint,
            self.canonical_semantic_fingerprint,
            *(value for _, value in self.source_versions),
            *(value for _, value in self.edition_fingerprints),
            *(value for _, _, value in self.provision_fingerprints),
            *(value for _, _, value in self.rule_candidate_fingerprints),
            *(value for _, _, value in self.rule_qualification_fingerprints),
            *(value for _, _, value in self.rule_activation_fingerprints),
        )
        if self.version < 1 or any(not value.startswith("sha256:") for value in digests):
            raise ValueError("NTD backup manifest requires pinned integrity digests")


def _validate_region(
    page_number: int | None, region: tuple[float, float, float, float] | None
) -> None:
    if (page_number is None) != (region is None):
        raise ValueError("Page and region locators must be supplied together")
    if region is not None:
        x0, y0, x1, y1 = region
        if page_number is None or page_number < 1 or not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("Normalized normative provision locator is invalid")
