"""PostgreSQL repository for the additive official NTD seed canon."""

# ruff: noqa: E501 -- SQL clauses remain readable and auditable.

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from asd_kontur.domain import deterministic_uuid, uuid7
from asd_kontur.harness.models import digest_of

from .manifest import PracticeGuideNtdSeedManifest
from .models import (
    AcquisitionReceipt,
    ApplicabilityPredicate,
    NormativeActivationDecision,
    NormativeApplicabilityDecision,
    NormativeArtifact,
    NormativeCorpusManifest,
    NormativeEditionRelationship,
    NormativeProvisionCandidate,
    NormativeProvisionVersion,
    OfficialProviderHealthReceipt,
    PracticeNtdAlignment,
    RuleNormativeProvisionEvidence,
)
from .rules import (
    NormativeRuleCandidate,
    RuleActivationDecision,
    RuleQualificationDecision,
)


class NtdPersistenceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RegisteredNormativeDocument:
    normative_document_id: UUID
    duplicate: bool


@dataclass(frozen=True, slots=True)
class NormativeDocumentRegistration:
    stable_identity_key: str
    designation_namespace: str
    stable_designation: str
    title: str
    issuer: str
    jurisdiction: str
    document_class: str
    created_by_identity_id: str


@dataclass(frozen=True, slots=True)
class RegisteredNormativeEdition:
    normative_edition_id: UUID
    duplicate: bool
    edition_fingerprint: str


@dataclass(frozen=True, slots=True)
class NormativeEditionRegistration:
    normative_document_id: UUID
    edition_label: str
    source_version_id: UUID
    official_catalog_id: str
    official_catalog_url: str
    approval_metadata: dict[str, object]
    effective_from: date | None
    effective_to: date | None
    retrieved_at: datetime
    admitted_by_identity_id: str

    @property
    def fingerprint(self) -> str:
        # Retrieval wall clock and actor are receipt metadata, not edition semantics.
        return digest_of(
            {
                "schema": "normative-edition-registration-v2",
                "normative_document_id": self.normative_document_id,
                "edition_label": self.edition_label,
                "source_version_id": self.source_version_id,
                "official_catalog_id": self.official_catalog_id,
                "official_catalog_url": self.official_catalog_url,
                "approval_metadata": json.loads(
                    json.dumps(self.approval_metadata, ensure_ascii=False, sort_keys=True)
                ),
                "effective_from": self.effective_from,
                "effective_to": self.effective_to,
            }
        )


class NtdRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def register_seed_manifest(
        self,
        manifest: PracticeGuideNtdSeedManifest,
        *,
        created_by_identity_id: str,
        created_at: datetime,
    ) -> tuple[UUID, bool]:
        manifest_id = deterministic_uuid(
            f"ntd-seed-manifest:{manifest.practice_guide_edition_id}:{manifest.profile_version}"
        )
        with Session(self._engine) as session, session.begin():
            existing = (
                session.execute(
                    sa.text(
                        "SELECT seed_manifest_id,version FROM platform.ntd_seed_manifests "
                        "WHERE manifest_fingerprint=:fingerprint"
                    ),
                    {"fingerprint": manifest.fingerprint},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return UUID(str(existing["seed_manifest_id"])), True
            latest_version = session.execute(
                sa.text(
                    "SELECT max(version) FROM platform.ntd_seed_manifests "
                    "WHERE seed_manifest_id=:id"
                ),
                {"id": manifest_id},
            ).scalar_one()
            version = int(latest_version or 0) + 1
            session.execute(
                sa.text(
                    "INSERT INTO platform.ntd_seed_manifests "
                    "(seed_manifest_id,version,profile_version,practice_guide_edition_id,"
                    "source_version_id,page_numbers,raw_mention_count,identity_count,"
                    "manifest_fingerprint,supersedes_version,created_by_identity_id,created_at) "
                    "VALUES (:id,:version,:profile,:edition,:source,:pages,:mentions,:identities,"
                    ":fingerprint,:supersedes,:actor,:created)"
                ),
                {
                    "id": manifest_id,
                    "version": version,
                    "profile": manifest.profile_version,
                    "edition": manifest.practice_guide_edition_id,
                    "source": manifest.source_version_id,
                    "pages": list(page for page, _ in manifest.page_counts),
                    "mentions": manifest.raw_mention_count,
                    "identities": manifest.identity_count,
                    "fingerprint": manifest.fingerprint,
                    "supersedes": version - 1 if version > 1 else None,
                    "actor": created_by_identity_id,
                    "created": created_at,
                },
            )
            for reference in manifest.references:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.practice_guide_normative_references "
                        "(practice_guide_reference_id,seed_manifest_id,seed_manifest_version,"
                        "practice_guide_edition_id,source_version_id,pdf_page,region,"
                        "occurrence_ordinal,raw_designation,raw_title,raw_context,"
                        "normalized_designation,stable_identity_key,document_kind,printed_edition,"
                        "extraction_method,extraction_receipt_digest,source_fragment_digest,"
                        "verification_status) VALUES "
                        "(:id,:manifest,:version,:guide_edition,:source,:page,:region,:ordinal,"
                        ":raw,:title,:context,:normalized,:identity,:kind,:printed_edition,:method,"
                        ":receipt,:fragment,:status)"
                    ),
                    {
                        "id": reference.reference_id,
                        "manifest": manifest_id,
                        "version": version,
                        "guide_edition": reference.practice_guide_edition_id,
                        "source": reference.source_version_id,
                        "page": reference.pdf_page,
                        "region": list(reference.region),
                        "ordinal": reference.occurrence_ordinal,
                        "raw": reference.raw_designation,
                        "title": reference.raw_title,
                        "context": reference.raw_context,
                        "normalized": reference.normalized.normalized_designation,
                        "identity": reference.normalized.stable_identity_key,
                        "kind": reference.normalized.document_kind.value,
                        "printed_edition": reference.normalized.printed_edition,
                        "method": reference.extraction_method,
                        "receipt": reference.extraction_receipt_digest,
                        "fragment": reference.source_fragment_digest,
                        "status": reference.verification_status,
                    },
                )
        return manifest_id, False

    def seed_manifest_version(self, manifest_id: UUID, fingerprint: str) -> int:
        with Session(self._engine) as session:
            version = session.execute(
                sa.text(
                    "SELECT version FROM platform.ntd_seed_manifests "
                    "WHERE seed_manifest_id=:id AND manifest_fingerprint=:fingerprint"
                ),
                {"id": manifest_id, "fingerprint": fingerprint},
            ).scalar_one_or_none()
        if version is None:
            raise NtdPersistenceError(
                "NTD_SEED_MANIFEST_NOT_REGISTERED", "Exact seed manifest was not registered."
            )
        return int(version)

    def register_document(
        self, registration: NormativeDocumentRegistration
    ) -> RegisteredNormativeDocument:
        document_id = deterministic_uuid(f"normative-document:{registration.stable_identity_key}")
        with Session(self._engine) as session, session.begin():
            existing = (
                session.execute(
                    sa.text(
                        "SELECT normative_document_id,title,document_class FROM platform.normative_documents "
                        "WHERE designation_namespace=:namespace AND designation=:designation "
                        "AND issuer=:issuer AND jurisdiction=:jurisdiction"
                    ),
                    {
                        "namespace": registration.designation_namespace,
                        "designation": registration.stable_designation,
                        "issuer": registration.issuer,
                        "jurisdiction": registration.jurisdiction,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if (
                    existing["title"] != registration.title
                    or existing["document_class"] != registration.document_class
                ):
                    raise NtdPersistenceError(
                        "NORMATIVE_DOCUMENT_IDENTITY_CONFLICT",
                        "Stable normative identity was reused with conflicting metadata.",
                    )
                return RegisteredNormativeDocument(
                    UUID(str(existing["normative_document_id"])), True
                )
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_documents "
                    "(normative_document_id,designation_namespace,designation,title,issuer,"
                    "jurisdiction,document_class,created_by_identity_id) "
                    "VALUES (:id,:namespace,:designation,:title,:issuer,:jurisdiction,:class,:actor)"
                ),
                {
                    "id": document_id,
                    "namespace": registration.designation_namespace,
                    "designation": registration.stable_designation,
                    "title": registration.title,
                    "issuer": registration.issuer,
                    "jurisdiction": registration.jurisdiction,
                    "class": registration.document_class,
                    "actor": registration.created_by_identity_id,
                },
            )
        return RegisteredNormativeDocument(document_id, False)

    def register_edition(
        self, registration: NormativeEditionRegistration
    ) -> RegisteredNormativeEdition:
        fingerprint = registration.fingerprint
        edition_id = deterministic_uuid(
            f"normative-edition:{registration.normative_document_id}:"
            f"{registration.official_catalog_id}:{registration.source_version_id}:{fingerprint}"
        )
        with Session(self._engine) as session, session.begin():
            existing_source = (
                session.execute(
                    sa.text(
                        "SELECT normative_edition_id,edition_fingerprint,normative_document_id,"
                        "edition_label,official_catalog_id,official_catalog_url,approval_metadata,"
                        "effective_from,effective_to FROM platform.normative_editions "
                        "WHERE source_version_id=:source"
                    ),
                    {"source": registration.source_version_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing_source is not None:
                semantic_match = (
                    UUID(str(existing_source["normative_document_id"]))
                    == registration.normative_document_id
                    and existing_source["edition_label"] == registration.edition_label
                    and existing_source["official_catalog_id"] == registration.official_catalog_id
                    and existing_source["official_catalog_url"] == registration.official_catalog_url
                    and dict(existing_source["approval_metadata"] or {})
                    == json.loads(
                        json.dumps(
                            registration.approval_metadata,
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                    and existing_source["effective_from"] == registration.effective_from
                    and existing_source["effective_to"] == registration.effective_to
                )
                if not semantic_match:
                    mismatch_fields = tuple(
                        name
                        for name, matches in (
                            (
                                "normative_document_id",
                                UUID(str(existing_source["normative_document_id"]))
                                == registration.normative_document_id,
                            ),
                            (
                                "edition_label",
                                existing_source["edition_label"] == registration.edition_label,
                            ),
                            (
                                "official_catalog_id",
                                existing_source["official_catalog_id"]
                                == registration.official_catalog_id,
                            ),
                            (
                                "official_catalog_url",
                                existing_source["official_catalog_url"]
                                == registration.official_catalog_url,
                            ),
                            (
                                "approval_metadata",
                                dict(existing_source["approval_metadata"] or {})
                                == json.loads(
                                    json.dumps(
                                        registration.approval_metadata,
                                        ensure_ascii=False,
                                        sort_keys=True,
                                    )
                                ),
                            ),
                            (
                                "effective_from",
                                existing_source["effective_from"] == registration.effective_from,
                            ),
                            (
                                "effective_to",
                                existing_source["effective_to"] == registration.effective_to,
                            ),
                        )
                        if not matches
                    )
                    raise NtdPersistenceError(
                        "NORMATIVE_EDITION_PROVENANCE_CONFLICT",
                        "A SourceVersion is already pinned to different edition metadata: "
                        + ",".join(mismatch_fields),
                    )
                return RegisteredNormativeEdition(
                    UUID(str(existing_source["normative_edition_id"])),
                    True,
                    str(existing_source["edition_fingerprint"]),
                )
            same_label = (
                session.execute(
                    sa.text(
                        "SELECT normative_edition_id,source_version_id FROM platform.normative_editions "
                        "WHERE normative_document_id=:document AND edition_label=:label"
                    ),
                    {
                        "document": registration.normative_document_id,
                        "label": registration.edition_label,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if same_label is not None:
                raise NtdPersistenceError(
                    "NORMATIVE_EDITION_DIGEST_CONFLICT",
                    "The official edition label already points to another SourceVersion.",
                )
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_editions "
                    "(normative_edition_id,normative_document_id,edition_label,source_version_id,"
                    "effective_from,effective_to,official_catalog_id,official_catalog_url,"
                    "approval_metadata,retrieved_at,edition_fingerprint,admitted_by_identity_id) "
                    "VALUES (:id,:document,:label,:source,:from_date,:to_date,:catalog_id,"
                    ":catalog_url,CAST(:approval AS jsonb),:retrieved,:fingerprint,:actor)"
                ),
                {
                    "id": edition_id,
                    "document": registration.normative_document_id,
                    "label": registration.edition_label,
                    "source": registration.source_version_id,
                    "from_date": registration.effective_from,
                    "to_date": registration.effective_to,
                    "catalog_id": registration.official_catalog_id,
                    "catalog_url": registration.official_catalog_url,
                    "approval": json.dumps(registration.approval_metadata, ensure_ascii=False),
                    "retrieved": registration.retrieved_at,
                    "fingerprint": fingerprint,
                    "actor": registration.admitted_by_identity_id,
                },
            )
        return RegisteredNormativeEdition(edition_id, False, fingerprint)

    def register_artifact(self, artifact: NormativeArtifact, *, registered_at: datetime) -> bool:
        with Session(self._engine) as session, session.begin():
            existing = (
                session.execute(
                    sa.text(
                        "SELECT normative_artifact_id,content_digest FROM platform.normative_artifacts "
                        "WHERE source_version_id=:source"
                    ),
                    {"source": artifact.source_version_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if existing["content_digest"] != artifact.content_digest:
                    raise NtdPersistenceError(
                        "NORMATIVE_ARTIFACT_DIGEST_CONFLICT",
                        "Artifact SourceVersion has conflicting bytes.",
                    )
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_artifacts "
                    "(normative_artifact_id,normative_edition_id,source_version_id,"
                    "official_catalog_id,official_url,filename,media_type,size_bytes,"
                    "content_digest,relation_to_edition,retrieval_metadata_digest,registered_at) "
                    "VALUES (:id,:edition,:source,:catalog,:url,:filename,:media,:size,:digest,"
                    ":relation,:metadata,:registered)"
                ),
                {
                    "id": artifact.normative_artifact_id,
                    "edition": artifact.normative_edition_id,
                    "source": artifact.source_version_id,
                    "catalog": artifact.official_catalog_id,
                    "url": artifact.official_url,
                    "filename": artifact.filename,
                    "media": artifact.media_type,
                    "size": artifact.size_bytes,
                    "digest": artifact.content_digest,
                    "relation": artifact.relation_to_edition,
                    "metadata": artifact.retrieval_metadata_digest,
                    "registered": registered_at,
                },
            )
        return False

    def record_acquisition_receipt(
        self,
        receipt: AcquisitionReceipt,
        *,
        practice_guide_reference_id: UUID | None,
    ) -> bool:
        metadata = receipt.http_metadata
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT acquisition_receipt_id FROM platform.ntd_catalogue_query_receipts "
                    "WHERE receipt_fingerprint=:fingerprint"
                ),
                {"fingerprint": receipt.fingerprint},
            ).scalar_one_or_none()
            if existing is not None:
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.ntd_catalogue_query_receipts "
                    "(acquisition_receipt_id,practice_guide_reference_id,previous_receipt_id,"
                    "normalized_query,official_endpoint,requested_at,returned_catalog_ids,"
                    "selected_catalog_id,selection_reason,rejected_candidates,artifact_url,"
                    "http_status,content_type,etag,last_modified,byte_length,content_digest,"
                    "parser_version,terminal_status,failure_code,receipt_fingerprint) VALUES "
                    "(:id,:reference,:previous,:query,:endpoint,:requested,:returned,:selected,"
                    ":reason,CAST(:rejected AS jsonb),:artifact,:status,:content_type,:etag,"
                    ":last_modified,:bytes,:digest,:parser,:terminal,:failure,:fingerprint)"
                ),
                {
                    "id": receipt.receipt_id,
                    "reference": practice_guide_reference_id,
                    "previous": receipt.previous_receipt_id,
                    "query": receipt.normalized_query,
                    "endpoint": receipt.official_endpoint,
                    "requested": receipt.requested_at,
                    "returned": list(receipt.returned_catalog_ids),
                    "selected": receipt.selected_catalog_id,
                    "reason": receipt.selection_reason,
                    "rejected": json.dumps(receipt.rejected_candidates, ensure_ascii=False),
                    "artifact": receipt.artifact_url,
                    "status": metadata.status_code if metadata else None,
                    "content_type": metadata.content_type if metadata else None,
                    "etag": metadata.etag if metadata else None,
                    "last_modified": metadata.last_modified if metadata else None,
                    "bytes": metadata.byte_length if metadata else None,
                    "digest": receipt.content_digest,
                    "parser": receipt.parser_version,
                    "terminal": receipt.terminal_status.value,
                    "failure": receipt.failure_code,
                    "fingerprint": receipt.fingerprint,
                },
            )
        return False

    def register_relationship(
        self, relationship: NormativeEditionRelationship, *, recorded_at: datetime
    ) -> bool:
        fingerprint = digest_of(relationship)
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT relationship_id FROM platform.normative_edition_relationships "
                    "WHERE relationship_fingerprint=:fingerprint"
                ),
                {"fingerprint": fingerprint},
            ).scalar_one_or_none()
            if existing is not None:
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_edition_relationships "
                    "(relationship_id,from_edition_id,to_edition_id,relation_kind,"
                    "official_evidence_ref,source_locator_id,verification_status,"
                    "relationship_fingerprint,recorded_at) VALUES "
                    "(:id,:from_id,:to_id,:kind,:evidence,:locator,:status,:fingerprint,:recorded)"
                ),
                {
                    "id": relationship.relationship_id,
                    "from_id": relationship.from_edition_id,
                    "to_id": relationship.to_edition_id,
                    "kind": relationship.relation_kind.value,
                    "evidence": relationship.official_evidence_ref,
                    "locator": relationship.source_locator_id,
                    "status": relationship.verification_status,
                    "fingerprint": fingerprint,
                    "recorded": recorded_at,
                },
            )
        return False

    def record_reference_resolution(
        self,
        *,
        reference_id: UUID,
        acquisition_receipt_id: UUID,
        resolution_status: str,
        decision_reason: str,
        uncertainty_codes: tuple[str, ...],
        decided_at: datetime,
        normative_document_id: UUID | None = None,
        mentioned_edition_id: UUID | None = None,
        current_official_edition_id: UUID | None = None,
        as_of_edition_id: UUID | None = None,
        conflict_status: str | None = None,
        version: int = 1,
    ) -> UUID:
        decision_id = deterministic_uuid(f"practice-guide-ntd-resolution:{reference_id}")
        payload = {
            "decision_id": str(decision_id),
            "version": version,
            "reference_id": str(reference_id),
            "acquisition_receipt_id": str(acquisition_receipt_id),
            "resolution_status": resolution_status,
            "normative_document_id": str(normative_document_id) if normative_document_id else None,
            "mentioned_edition_id": str(mentioned_edition_id) if mentioned_edition_id else None,
            "current_official_edition_id": (
                str(current_official_edition_id) if current_official_edition_id else None
            ),
            "as_of_edition_id": str(as_of_edition_id) if as_of_edition_id else None,
            "conflict_status": conflict_status,
            "uncertainty_codes": uncertainty_codes,
            "decision_reason": decision_reason,
            "decided_at": decided_at,
        }
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_ntd_resolution_decisions "
                    "(resolution_decision_id,version,practice_guide_reference_id,"
                    "acquisition_receipt_id,resolution_status,normative_document_id,"
                    "mentioned_edition_id,current_official_edition_id,as_of_edition_id,"
                    "conflict_status,uncertainty_codes,decision_reason,supersedes_version,"
                    "decision_fingerprint,decided_at) VALUES "
                    "(:id,:version,:reference,:receipt,:status,:document,:mentioned,:current,"
                    ":as_of,:conflict,:uncertainties,:reason,:supersedes,:fingerprint,:decided)"
                ),
                {
                    "id": decision_id,
                    "version": version,
                    "reference": reference_id,
                    "receipt": acquisition_receipt_id,
                    "status": resolution_status,
                    "document": normative_document_id,
                    "mentioned": mentioned_edition_id,
                    "current": current_official_edition_id,
                    "as_of": as_of_edition_id,
                    "conflict": conflict_status,
                    "uncertainties": list(uncertainty_codes),
                    "reason": decision_reason,
                    "supersedes": version - 1 if version > 1 else None,
                    "fingerprint": digest_of(payload),
                    "decided": decided_at,
                },
            )
        return decision_id

    def record_gap(
        self,
        *,
        stable_identity_key: str,
        gap_code: str,
        blocker_scope: str,
        evidence_refs: tuple[str, ...],
        recorded_at: datetime,
        version: int = 1,
    ) -> UUID:
        gap_id = new_gap_identity(stable_identity_key, gap_code)
        payload = {
            "gap_id": str(gap_id),
            "version": version,
            "stable_identity_key": stable_identity_key,
            "gap_code": gap_code,
            "blocker_scope": blocker_scope,
            "evidence_refs": evidence_refs,
            "status": "open",
            "recorded_at": recorded_at,
        }
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO platform.ntd_gaps "
                    "(normative_gap_id,version,stable_identity_key,gap_code,blocker_scope,"
                    "evidence_refs,status,supersedes_version,gap_fingerprint,recorded_at) "
                    "VALUES (:id,:version,:identity,:code,:scope,CAST(:evidence AS jsonb),'open',"
                    ":supersedes,:fingerprint,:recorded)"
                ),
                {
                    "id": gap_id,
                    "version": version,
                    "identity": stable_identity_key,
                    "code": gap_code,
                    "scope": blocker_scope,
                    "evidence": json.dumps(evidence_refs),
                    "supersedes": version - 1 if version > 1 else None,
                    "fingerprint": digest_of(payload),
                    "recorded": recorded_at,
                },
            )
        return gap_id

    def register_provision_candidate(self, candidate: NormativeProvisionCandidate) -> bool:
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT content_digest FROM platform.normative_provision_candidates "
                    "WHERE provision_candidate_id=:id AND candidate_version=:version"
                ),
                {"id": candidate.candidate_id, "version": candidate.candidate_version},
            ).scalar_one_or_none()
            if existing is not None:
                if existing != candidate.content_digest:
                    raise NtdPersistenceError(
                        "NORMATIVE_PROVISION_CANDIDATE_CONFLICT",
                        "Candidate identity was reused for different text.",
                    )
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_provision_candidates "
                    "(provision_candidate_id,candidate_version,normative_edition_id,"
                    "source_version_id,structural_path,provision_kind,page_number,region,"
                    "verbatim_text,extraction_method,extraction_profile_version,content_digest,"
                    "model_provenance) VALUES "
                    "(:id,:version,:edition,:source,:path,:kind,:page,:region,:text,:method,"
                    ":profile,:digest,CAST(:model AS jsonb))"
                ),
                {
                    "id": candidate.candidate_id,
                    "version": candidate.candidate_version,
                    "edition": candidate.normative_edition_id,
                    "source": candidate.source_version_id,
                    "path": candidate.structural_path,
                    "kind": candidate.provision_kind.value,
                    "page": candidate.page_number,
                    "region": list(candidate.region) if candidate.region else None,
                    "text": candidate.verbatim_text,
                    "method": candidate.extraction_method,
                    "profile": candidate.extraction_profile_version,
                    "digest": candidate.content_digest,
                    "model": json.dumps(candidate.model_provenance, ensure_ascii=False),
                },
            )
        return False

    def register_structural_unit_for_candidate(
        self, candidate: NormativeProvisionCandidate
    ) -> UUID:
        if candidate.page_number is None or candidate.region is None:
            raise NtdPersistenceError(
                "NORMATIVE_PROVISION_LOCATOR_MISSING",
                "A canonical structural unit requires exact page/region evidence.",
            )
        locator_id = deterministic_uuid(
            f"ntd-source-locator:{candidate.source_version_id}:{candidate.page_number}:"
            f"{candidate.structural_path}:{candidate.content_digest}"
        )
        structural_id = deterministic_uuid(
            f"ntd-structural-unit:{candidate.normative_edition_id}:{candidate.structural_path}:"
            f"{candidate.content_digest}"
        )
        locator_key = f"page={candidate.page_number};region=" + ",".join(
            f"{value:.12f}" for value in candidate.region
        )
        fragment_method = {
            "native_pdf_layout": "native_pdf_layout",
            "native_html_structure": "native_html_structure",
            "ocr_region": "polza_public_ntd_page",
            "vlm_bounded_region": "polza_public_ntd_page",
        }[candidate.extraction_method]
        exact_number = (
            candidate.structural_path.rsplit(":", maxsplit=1)[-1]
            if "/clause:" in candidate.structural_path
            else None
        )
        fragment_fingerprint = digest_of(
            {
                "schema": "ntd-candidate-structural-fragment-v1",
                "structural_unit_id": structural_id,
                "source_version_id": candidate.source_version_id,
                "source_locator_ids": [locator_id],
                "exact_number": exact_number,
                "raw_text": candidate.verbatim_text,
                "source_fragment_digest": candidate.content_digest,
                "extraction_method": fragment_method,
                "extraction_profile_version": candidate.extraction_profile_version,
            }
        )
        fragment_id = deterministic_uuid(
            f"ntd-structural-fragment:{structural_id}:{fragment_fingerprint}"
        )
        with Session(self._engine) as session, session.begin():
            existing = (
                session.execute(
                    sa.text(
                        "SELECT structural_unit_id,content_digest FROM platform.structural_units "
                        "WHERE normative_edition_id=:edition AND structural_path=:path"
                    ),
                    {"edition": candidate.normative_edition_id, "path": candidate.structural_path},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if existing["content_digest"] != candidate.content_digest:
                    raise NtdPersistenceError(
                        "NORMATIVE_STRUCTURAL_PATH_CONFLICT",
                        "An edition structural path already has different exact text.",
                    )
                structural_id = UUID(str(existing["structural_unit_id"]))
            session.execute(
                sa.text(
                    "INSERT INTO platform.source_locators "
                    "(source_locator_id,source_version_id,locator_kind,locator_key,"
                    "locator_value,fragment_digest) VALUES "
                    "(:id,:source,'page_region',:key,CAST(:value AS jsonb),:digest) "
                    "ON CONFLICT (source_locator_id) DO NOTHING"
                ),
                {
                    "id": locator_id,
                    "source": candidate.source_version_id,
                    "key": locator_key,
                    "value": json.dumps(
                        {"page": candidate.page_number, "region": candidate.region}
                    ),
                    "digest": candidate.content_digest,
                },
            )
            unit_type = (
                "definition_scope"
                if candidate.provision_kind.value == "definition"
                else candidate.provision_kind.value
            )
            if existing is None:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.structural_units "
                        "(structural_unit_id,normative_edition_id,parent_structural_unit_id,unit_type,"
                        "structural_path,ordinal,source_locator_id,normalized_text,content_digest) "
                        "VALUES (:id,:edition,NULL,:type,:path,0,:locator,:text,:digest)"
                    ),
                    {
                        "id": structural_id,
                        "edition": candidate.normative_edition_id,
                        "type": unit_type,
                        "path": candidate.structural_path,
                        "locator": locator_id,
                        "text": candidate.verbatim_text,
                        "digest": candidate.content_digest,
                    },
                )
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_structural_fragments "
                    "(structural_fragment_id,structural_unit_id,source_version_id,"
                    "source_locator_ids,exact_heading,exact_number,raw_text,"
                    "normalized_search_text,source_fragment_digest,extraction_method,"
                    "extraction_profile_version,extraction_lineage,fragment_fingerprint,"
                    "recorded_at) VALUES "
                    "(:id,:structural,:source,:locators,NULL,:number,:raw,:normalized,:digest,"
                    ":method,:profile,CAST(:lineage AS jsonb),:fingerprint,CURRENT_TIMESTAMP) "
                    "ON CONFLICT (structural_fragment_id) DO NOTHING"
                ),
                {
                    "id": fragment_id,
                    "structural": structural_id,
                    "source": candidate.source_version_id,
                    "locators": [locator_id],
                    "number": exact_number,
                    "raw": candidate.verbatim_text,
                    "normalized": candidate.verbatim_text,
                    "digest": candidate.content_digest,
                    "method": fragment_method,
                    "profile": candidate.extraction_profile_version,
                    "lineage": json.dumps(
                        {
                            "candidate_id": str(candidate.candidate_id),
                            "candidate_version": candidate.candidate_version,
                            "model_provenance": candidate.model_provenance,
                        },
                        ensure_ascii=False,
                    ),
                    "fingerprint": fragment_fingerprint,
                },
            )
        return structural_id

    def publish_provision(
        self,
        provision: NormativeProvisionVersion,
        *,
        structural_unit_id: UUID,
        supersedes_version: int | None = None,
    ) -> bool:
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT semantic_fingerprint FROM platform.normative_provision_versions "
                    "WHERE normative_provision_id=:id AND version=:version"
                ),
                {"id": provision.provision_id, "version": provision.version},
            ).scalar_one_or_none()
            if existing is not None:
                if existing != provision.semantic_fingerprint:
                    raise NtdPersistenceError(
                        "NORMATIVE_PROVISION_VERSION_CONFLICT",
                        "Provision version identity was reused with different semantics.",
                    )
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_provision_versions "
                    "(normative_provision_id,version,provision_candidate_id,candidate_version,"
                    "normative_edition_id,source_version_id,structural_unit_id,structural_path,"
                    "provision_kind,page_number,region,verbatim_text,content_digest,"
                    "semantic_fingerprint,verification_status,verification_decision_ref,"
                    "verified_by_identity_id,verified_at,supersedes_version) VALUES "
                    "(:id,:version,:candidate,:candidate_version,:edition,:source,:structural,"
                    ":path,:kind,:page,:region,:text,:digest,:semantic,:status,:decision,"
                    ":verifier,:verified,:supersedes)"
                ),
                {
                    "id": provision.provision_id,
                    "version": provision.version,
                    "candidate": provision.candidate_id,
                    "candidate_version": provision.candidate_version,
                    "edition": provision.normative_edition_id,
                    "source": provision.source_version_id,
                    "structural": structural_unit_id,
                    "path": provision.structural_path,
                    "kind": provision.provision_kind.value,
                    "page": provision.page_number,
                    "region": list(provision.region) if provision.region else None,
                    "text": provision.verbatim_text,
                    "digest": provision.content_digest,
                    "semantic": provision.semantic_fingerprint,
                    "status": provision.verification_status.value,
                    "decision": provision.verification_decision_ref,
                    "verifier": provision.verified_by_identity_id,
                    "verified": provision.verified_at,
                    "supersedes": supersedes_version,
                },
            )
        return False

    def record_activation(self, decision: NormativeActivationDecision) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_activation_decisions "
                    "(activation_decision_id,version,normative_document_id,selected_edition_id,"
                    "as_of,status,authority_reference,evidence_refs,supersedes_version,"
                    "decision_fingerprint,decided_at) VALUES "
                    "(:id,:version,:document,:edition,:as_of,:status,:authority,CAST(:evidence AS jsonb),"
                    ":supersedes,:fingerprint,:decided)"
                ),
                {
                    "id": decision.decision_id,
                    "version": decision.decision_version,
                    "document": decision.normative_document_id,
                    "edition": decision.selected_edition_id,
                    "as_of": decision.as_of,
                    "status": decision.status,
                    "authority": decision.authority_reference,
                    "evidence": json.dumps(decision.evidence_refs),
                    "supersedes": decision.supersedes_decision_version,
                    "fingerprint": digest_of(decision),
                    "decided": decision.decided_at,
                },
            )

    def record_applicability(self, decision: NormativeApplicabilityDecision) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_applicability_decisions "
                    "(applicability_decision_id,version,normative_edition_id,scope_kind,scope_ref,"
                    "as_of,applicability_status,predicate,evidence_refs,decided_by_identity_id,"
                    "decision_fingerprint,decided_at) VALUES "
                    "(:id,:version,:edition,:scope,:scope_ref,:as_of,:status,CAST(:predicate AS jsonb),"
                    "CAST(:evidence AS jsonb),:actor,:fingerprint,:decided)"
                ),
                {
                    "id": decision.decision_id,
                    "version": decision.decision_version,
                    "edition": decision.normative_edition_id,
                    "scope": decision.scope_kind,
                    "scope_ref": decision.scope_ref,
                    "as_of": decision.as_of,
                    "status": decision.applicability_status,
                    "predicate": json.dumps(decision.predicate, ensure_ascii=False),
                    "evidence": json.dumps(decision.evidence_refs),
                    "actor": decision.decided_by_identity_id,
                    "fingerprint": digest_of(decision),
                    "decided": decision.decided_at,
                },
            )

    def record_alignment(self, alignment: PracticeNtdAlignment) -> None:
        with Session(self._engine) as session, session.begin():
            fingerprint = digest_of(alignment)
            existing = session.execute(
                sa.text(
                    "SELECT alignment_fingerprint FROM platform.practice_ntd_alignments "
                    "WHERE alignment_id=:id AND version=:version"
                ),
                {"id": alignment.alignment_id, "version": alignment.alignment_version},
            ).scalar_one_or_none()
            if existing is not None:
                if existing != fingerprint:
                    raise NtdPersistenceError(
                        "PRACTICE_NTD_ALIGNMENT_VERSION_CONFLICT",
                        "Alignment version identity was reused with different semantics.",
                    )
                return
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_ntd_alignments "
                    "(alignment_id,version,practice_guide_reference_id,guidance_unit_id,"
                    "guidance_unit_version,normative_document_id,normative_edition_id,"
                    "normative_provision_id,normative_provision_version,alignment_status,as_of,"
                    "evidence_refs,decision_ref,supersedes_version,alignment_fingerprint,decided_at) "
                    "VALUES (:id,:version,:reference,:guidance,:guidance_version,:document,:edition,"
                    ":provision,:provision_version,:status,:as_of,CAST(:evidence AS jsonb),:decision,"
                    ":supersedes,:fingerprint,:decided)"
                ),
                {
                    "id": alignment.alignment_id,
                    "version": alignment.alignment_version,
                    "reference": alignment.practice_guide_reference_id,
                    "guidance": alignment.guidance_unit_id,
                    "guidance_version": alignment.guidance_unit_version,
                    "document": alignment.normative_document_id,
                    "edition": alignment.normative_edition_id,
                    "provision": alignment.provision_id,
                    "provision_version": alignment.provision_version,
                    "status": alignment.status.value,
                    "as_of": alignment.as_of,
                    "evidence": json.dumps(alignment.evidence_refs),
                    "decision": alignment.decision_ref,
                    "supersedes": alignment.alignment_version - 1
                    if alignment.alignment_version > 1
                    else None,
                    "fingerprint": fingerprint,
                    "decided": alignment.decided_at,
                },
            )

    def resolve_edition_as_of(self, normative_document_id: UUID, as_of: date) -> UUID | None:
        """Resolve only explicit activation decisions, never inferred mutable latest."""

        with Session(self._engine) as session:
            rows = (
                session.execute(
                    sa.text(
                        "SELECT selected_edition_id FROM platform.normative_activation_decisions "
                        "WHERE normative_document_id=:document AND as_of<=:as_of AND status='active' "
                        "ORDER BY as_of DESC,version DESC LIMIT 2"
                    ),
                    {"document": normative_document_id, "as_of": as_of},
                )
                .scalars()
                .all()
            )
        if not rows:
            return None
        if len(rows) > 1 and rows[0] != rows[1]:
            # Multiple historical decisions are allowed; ordering explicitly selects the latest
            # decision at or before as_of, not a mutable edition flag.
            return UUID(str(rows[0]))
        return UUID(str(rows[0]))

    def canonical_snapshot(self) -> dict[str, object]:
        with Session(self._engine) as session:
            counts = {
                table: int(
                    session.execute(sa.text(f"SELECT count(*) FROM platform.{table}")).scalar_one()
                )
                for table in (
                    "normative_documents",
                    "normative_editions",
                    "normative_artifacts",
                    "normative_edition_relationships",
                    "normative_provision_versions",
                    "normative_activation_decisions",
                    "normative_applicability_decisions",
                    "ntd_gaps",
                    "ntd_conflicts",
                    "practice_ntd_alignments",
                )
            }
            digests = session.execute(
                sa.text(
                    "SELECT coalesce(array_agg(value ORDER BY value),'{}') FROM ("
                    "SELECT edition_fingerprint AS value FROM platform.normative_editions "
                    "WHERE edition_fingerprint IS NOT NULL UNION ALL "
                    "SELECT semantic_fingerprint FROM platform.normative_provision_versions "
                    "WHERE verification_status='verified' UNION ALL "
                    "SELECT gap_fingerprint FROM platform.ntd_gaps UNION ALL "
                    "SELECT conflict_fingerprint FROM platform.ntd_conflicts) fingerprints"
                )
            ).scalar_one()
        payload: dict[str, object] = {"counts": counts, "digests": list(digests)}
        return {**payload, "semantic_fingerprint": digest_of(payload)}

    def insert_seed_outcome(
        self,
        *,
        seed_manifest_id: UUID,
        seed_manifest_version: int,
        stable_identity_key: str,
        normalized_designation: str,
        terminal_status: str,
        terminal_receipt_id: UUID,
        recorded_at: datetime,
        normative_document_id: UUID | None = None,
        normative_edition_id: UUID | None = None,
    ) -> None:
        payload = {
            "seed_manifest_id": str(seed_manifest_id),
            "seed_manifest_version": seed_manifest_version,
            "stable_identity_key": stable_identity_key,
            "normalized_designation": normalized_designation,
            "terminal_status": terminal_status,
            "terminal_receipt_id": str(terminal_receipt_id),
            "normative_document_id": str(normative_document_id) if normative_document_id else None,
            "normative_edition_id": str(normative_edition_id) if normative_edition_id else None,
        }
        with Session(self._engine) as session, session.begin():
            try:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.normative_seed_outcomes "
                        "(seed_manifest_id,seed_manifest_version,stable_identity_key,"
                        "normalized_designation,normative_document_id,normative_edition_id,"
                        "terminal_status,terminal_receipt_id,outcome_fingerprint,recorded_at) "
                        "VALUES (:manifest,:version,:identity,:designation,:document,:edition,"
                        ":status,:receipt,:fingerprint,:recorded)"
                    ),
                    {
                        "manifest": seed_manifest_id,
                        "version": seed_manifest_version,
                        "identity": stable_identity_key,
                        "designation": normalized_designation,
                        "document": normative_document_id,
                        "edition": normative_edition_id,
                        "status": terminal_status,
                        "receipt": terminal_receipt_id,
                        "fingerprint": digest_of(payload),
                        "recorded": recorded_at,
                    },
                )
            except IntegrityError as exc:
                raise NtdPersistenceError(
                    "NORMATIVE_SEED_OUTCOME_CONFLICT",
                    "A bounded seed identity already has a terminal outcome.",
                ) from exc

    def record_provider_health(self, receipt: OfficialProviderHealthReceipt) -> bool:
        with Session(self._engine) as session, session.begin():
            existing = session.scalar(
                sa.text(
                    "SELECT provider_health_receipt_id FROM "
                    "platform.official_provider_health_receipts WHERE receipt_fingerprint=:value"
                ),
                {"value": receipt.fingerprint},
            )
            if existing is not None:
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.official_provider_health_receipts "
                    "(provider_health_receipt_id,provider,endpoint,transport_profile,checked_at,"
                    "access_status,http_status,response_digest,failure_code,diagnostic,"
                    "receipt_fingerprint) "
                    "VALUES (:id,:provider,:endpoint,:transport,:checked,:status,:http_status,"
                    ":digest,:failure,CAST(:diagnostic AS jsonb),:fingerprint)"
                ),
                {
                    "id": receipt.receipt_id,
                    "provider": receipt.provider.value,
                    "endpoint": receipt.endpoint,
                    "transport": receipt.transport_profile,
                    "checked": receipt.checked_at,
                    "status": receipt.status.value,
                    "http_status": receipt.http_status,
                    "digest": receipt.response_digest,
                    "failure": receipt.failure_code,
                    "diagnostic": json.dumps(receipt.diagnostic or {}, sort_keys=True),
                    "fingerprint": receipt.fingerprint,
                },
            )
        return False

    def register_corpus_manifest(self, manifest: NormativeCorpusManifest) -> bool:
        with Session(self._engine) as session, session.begin():
            existing = session.scalar(
                sa.text(
                    "SELECT normative_corpus_manifest_id FROM platform.normative_corpus_manifests "
                    "WHERE manifest_fingerprint=:fingerprint"
                ),
                {"fingerprint": manifest.fingerprint},
            )
            if existing is not None:
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_corpus_manifests "
                    "(normative_corpus_manifest_id,version,corpus_key,provider,official_query,"
                    "official_query_endpoints,denominator,parser_version,manifest_fingerprint,"
                    "supersedes_version,created_at) VALUES (:id,:version,:key,:provider,:query,"
                    ":endpoints,:denominator,:parser,:fingerprint,:supersedes,:created)"
                ),
                {
                    "id": manifest.manifest_id,
                    "version": manifest.version,
                    "key": manifest.corpus_key,
                    "provider": manifest.provider.value,
                    "query": manifest.query,
                    "endpoints": list(manifest.query_endpoints),
                    "denominator": manifest.denominator,
                    "parser": manifest.parser_version,
                    "fingerprint": manifest.fingerprint,
                    "supersedes": manifest.version - 1 if manifest.version > 1 else None,
                    "created": manifest.created_at,
                },
            )
            for member in manifest.members:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.normative_corpus_members "
                        "(normative_corpus_manifest_id,manifest_version,corpus_member_id,ordinal,"
                        "stable_identity_key,designation,title,official_catalog_id,official_catalog_url,"
                        "edition_status,replaces_designation,replaced_by_designation,scope_text,"
                        "official_metadata,acquisition_status,metadata_digest) VALUES "
                        "(:manifest,:version,:member,"
                        ":ordinal,:identity,:designation,:title,:catalog_id,:catalog_url,:status,"
                        ":replaces,:replaced_by,:scope,CAST(:metadata AS jsonb),:acquisition,:digest)"
                    ),
                    {
                        "manifest": manifest.manifest_id,
                        "version": manifest.version,
                        "member": member.member_id,
                        "ordinal": member.ordinal,
                        "identity": member.stable_identity_key,
                        "designation": member.designation,
                        "title": member.title,
                        "catalog_id": member.catalog_id,
                        "catalog_url": member.catalog_url,
                        "status": member.status.value,
                        "replaces": member.replaces_designation,
                        "replaced_by": member.replaced_by_designation,
                        "scope": member.scope_text,
                        "metadata": json.dumps(member.official_metadata, sort_keys=True),
                        "acquisition": member.acquisition_status.value,
                        "digest": member.metadata_digest,
                    },
                )
        return False

    def register_applicability_predicate(
        self,
        predicate: ApplicabilityPredicate,
        *,
        qualified_by_identity_id: str,
        qualification_decision_ref: str,
        qualified_at: datetime,
    ) -> bool:
        with Session(self._engine) as session, session.begin():
            existing = (
                session.execute(
                    sa.text(
                        "SELECT applicability_predicate_id,version,normative_provision_id,"
                        "normative_provision_version FROM "
                        "platform.normative_applicability_predicates "
                        "WHERE semantic_fingerprint=:fingerprint"
                    ),
                    {"fingerprint": predicate.semantic_fingerprint},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if (
                    int(existing["version"]) != predicate.version
                    or UUID(str(existing["normative_provision_id"])) != predicate.provision_id
                    or int(existing["normative_provision_version"]) != predicate.provision_version
                ):
                    raise NtdPersistenceError(
                        "NORMATIVE_APPLICABILITY_IDENTITY_CONFLICT",
                        "Applicability fingerprint is already bound to another exact provision.",
                    )
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_applicability_predicates "
                    "(applicability_predicate_id,version,normative_provision_id,"
                    "normative_provision_version,predicate,required_inputs,exclusions,"
                    "semantic_fingerprint,supersedes_version,qualified_by_identity_id,"
                    "qualification_decision_ref,qualified_at) VALUES (:id,:version,:provision,"
                    ":provision_version,CAST(:predicate AS jsonb),:required,CAST(:exclusions AS jsonb),"
                    ":fingerprint,:supersedes,:actor,:decision,:qualified)"
                ),
                {
                    "id": predicate.predicate_id,
                    "version": predicate.version,
                    "provision": predicate.provision_id,
                    "provision_version": predicate.provision_version,
                    "predicate": json.dumps(predicate.predicate, sort_keys=True),
                    "required": list(predicate.required_inputs),
                    "exclusions": json.dumps(predicate.exclusions, sort_keys=True),
                    "fingerprint": predicate.semantic_fingerprint,
                    "supersedes": predicate.version - 1 if predicate.version > 1 else None,
                    "actor": qualified_by_identity_id,
                    "decision": qualification_decision_ref,
                    "qualified": qualified_at,
                },
            )
        return False

    def link_rule_to_verified_provision(self, evidence: RuleNormativeProvisionEvidence) -> bool:
        """Attach exact normative lineage without promoting or activating the rule."""

        with Session(self._engine) as session, session.begin():
            existing = session.scalar(
                sa.text(
                    "SELECT rule_normative_evidence_id FROM "
                    "platform.rule_normative_provision_evidence WHERE rule_version_id=:rule "
                    "AND normative_provision_id=:provision AND "
                    "normative_provision_version=:provision_version"
                ),
                {
                    "rule": evidence.rule_version_id,
                    "provision": evidence.normative_provision_id,
                    "provision_version": evidence.normative_provision_version,
                },
            )
            if existing is not None:
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.rule_normative_provision_evidence "
                    "(rule_normative_evidence_id,rule_version_id,normative_provision_id,"
                    "normative_provision_version,normative_edition_id,source_version_id,"
                    "source_locator_id,applicability_predicate_id,applicability_predicate_version,"
                    "qualification_decision_ref,evidence_digest,recorded_at) VALUES "
                    "(:id,:rule,:provision,:provision_version,:edition,:source,:locator,"
                    ":predicate,:predicate_version,:decision,:digest,:recorded)"
                ),
                {
                    "id": evidence.evidence_id,
                    "rule": evidence.rule_version_id,
                    "provision": evidence.normative_provision_id,
                    "provision_version": evidence.normative_provision_version,
                    "edition": evidence.normative_edition_id,
                    "source": evidence.source_version_id,
                    "locator": evidence.source_locator_id,
                    "predicate": evidence.applicability_predicate_id,
                    "predicate_version": evidence.applicability_predicate_version,
                    "decision": evidence.qualification_decision_ref,
                    "digest": evidence.evidence_digest,
                    "recorded": evidence.recorded_at,
                },
            )
        return False

    def register_rule_candidate(
        self,
        candidate: NormativeRuleCandidate,
        *,
        created_by_identity_id: str,
        created_at: datetime,
    ) -> bool:
        """Persist an immutable candidate only when its exact provision is verified."""

        with Session(self._engine) as session, session.begin():
            evidence = (
                session.execute(
                    sa.text(
                        "SELECT p.verification_status,p.normative_edition_id,p.source_version_id,"
                        "p.structural_path,p.verbatim_text FROM platform.normative_provision_versions p "
                        "WHERE p.normative_provision_id=:provision AND p.version=:version"
                    ),
                    {
                        "provision": candidate.normative_provision_id,
                        "version": candidate.normative_provision_version,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if evidence is None or str(evidence["verification_status"]) != "verified":
                raise NtdPersistenceError(
                    "RULE_CANDIDATE_REQUIRES_VERIFIED_PROVISION",
                    "RuleCandidate cannot be registered without an exact verified provision.",
                )
            if (
                UUID(str(evidence["normative_edition_id"])) != candidate.normative_edition_id
                or UUID(str(evidence["source_version_id"])) != candidate.source_version_id
                or str(evidence["structural_path"]) != candidate.structural_path
                or str(evidence["verbatim_text"]) != candidate.verbatim_text
            ):
                raise NtdPersistenceError(
                    "RULE_CANDIDATE_PROVENANCE_MISMATCH",
                    "RuleCandidate evidence does not match the verified provision.",
                )
            existing = session.scalar(
                sa.text(
                    "SELECT normative_rule_candidate_id FROM platform.normative_rule_candidates "
                    "WHERE semantic_fingerprint=:fingerprint"
                ),
                {"fingerprint": candidate.semantic_fingerprint},
            )
            if existing is not None:
                if UUID(str(existing)) != candidate.candidate_id:
                    raise NtdPersistenceError(
                        "RULE_CANDIDATE_IDENTITY_CONFLICT",
                        "Candidate fingerprint is bound to another deterministic identity.",
                    )
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_rule_candidates "
                    "(normative_rule_candidate_id,version,normative_document_id,normative_edition_id,"
                    "source_version_id,normative_provision_id,normative_provision_version,"
                    "source_locator_id,structural_path,verbatim_text,verbatim_digest,deontic_type,"
                    "actor,regulated_object,required_action,applicability_predicate,conditions,"
                    "exceptions,output_contract,semantic_evidence_bindings,"
                    "interpretation_profile_version,semantic_fingerprint,created_by_identity_id,"
                    "created_at,supersedes_version) VALUES (:id,:version,:document,:edition,:source,"
                    ":provision,:provision_version,:locator,:path,:verbatim,:digest,:deontic,"
                    "CAST(:actor AS jsonb),CAST(:object AS jsonb),CAST(:action AS jsonb),"
                    "CAST(:predicate AS jsonb),CAST(:conditions AS jsonb),CAST(:exceptions AS jsonb),"
                    "CAST(:output AS jsonb),CAST(:bindings AS jsonb),:profile,:fingerprint,:created_by,"
                    ":created_at,:supersedes)"
                ),
                {
                    "id": candidate.candidate_id,
                    "version": candidate.version,
                    "document": candidate.normative_document_id,
                    "edition": candidate.normative_edition_id,
                    "source": candidate.source_version_id,
                    "provision": candidate.normative_provision_id,
                    "provision_version": candidate.normative_provision_version,
                    "locator": candidate.source_locator_id,
                    "path": candidate.structural_path,
                    "verbatim": candidate.verbatim_text,
                    "digest": candidate.verbatim_digest,
                    "deontic": candidate.deontic_type.value,
                    "actor": json.dumps(candidate.actor, sort_keys=True),
                    "object": json.dumps(candidate.regulated_object, sort_keys=True),
                    "action": json.dumps(candidate.required_action, sort_keys=True),
                    "predicate": json.dumps(candidate.applicability_predicate, sort_keys=True),
                    "conditions": json.dumps(candidate.conditions, sort_keys=True),
                    "exceptions": json.dumps(candidate.exceptions, sort_keys=True),
                    "output": json.dumps(candidate.output_contract, sort_keys=True),
                    "bindings": json.dumps(
                        [
                            {"field": item.field, "source_quotes": item.source_quotes}
                            for item in candidate.evidence_bindings
                        ],
                        sort_keys=True,
                    ),
                    "profile": candidate.interpretation_profile_version,
                    "fingerprint": candidate.semantic_fingerprint,
                    "created_by": created_by_identity_id,
                    "created_at": created_at,
                    "supersedes": candidate.version - 1 if candidate.version > 1 else None,
                },
            )
        return False

    def record_rule_qualification(
        self,
        decision: RuleQualificationDecision,
        *,
        qualified_by_identity_id: str,
        qualification_decision_ref: str,
        decided_at: datetime,
    ) -> bool:
        with Session(self._engine) as session, session.begin():
            existing = session.scalar(
                sa.text(
                    "SELECT qualification_decision_id FROM "
                    "platform.normative_rule_qualification_decisions "
                    "WHERE decision_fingerprint=:fingerprint"
                ),
                {"fingerprint": decision.decision_fingerprint},
            )
            if existing is not None:
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_rule_qualification_decisions "
                    "(qualification_decision_id,version,normative_rule_candidate_id,"
                    "normative_rule_candidate_version,status,gate_results,"
                    "qualification_profile_version,test_manifest_digest,decision_fingerprint,"
                    "qualified_by_identity_id,qualification_decision_ref,decided_at,supersedes_version) "
                    "VALUES (:id,:version,:candidate,:candidate_version,:status,CAST(:gates AS jsonb),"
                    ":profile,:tests,:fingerprint,:actor,:decision,:decided_at,:supersedes)"
                ),
                {
                    "id": decision.decision_id,
                    "version": decision.version,
                    "candidate": decision.candidate_id,
                    "candidate_version": decision.candidate_version,
                    "status": decision.status.value,
                    "gates": json.dumps(decision.gate_results, sort_keys=True),
                    "profile": decision.qualification_profile_version,
                    "tests": decision.test_manifest_digest,
                    "fingerprint": decision.decision_fingerprint,
                    "actor": qualified_by_identity_id,
                    "decision": qualification_decision_ref,
                    "decided_at": decided_at,
                    "supersedes": decision.version - 1 if decision.version > 1 else None,
                },
            )
        return False

    def record_rule_activation_outcome(
        self,
        decision: RuleActivationDecision,
        *,
        rule_version_id: UUID | None,
        edition_activation_decision: tuple[UUID, int] | None,
        authority_identity_id: str | None,
        authority_decision_ref: str,
        decided_at: datetime,
    ) -> bool:
        if decision.status.value == "active" and (
            rule_version_id is None
            or edition_activation_decision is None
            or authority_identity_id is None
        ):
            raise NtdPersistenceError(
                "RULE_ACTIVATION_AUTHORITY_MISSING",
                "Active outcome requires exact RuleVersion, edition decision and authority.",
            )
        with Session(self._engine) as session, session.begin():
            existing = session.scalar(
                sa.text(
                    "SELECT rule_activation_outcome_id FROM "
                    "platform.normative_rule_activation_outcomes "
                    "WHERE decision_fingerprint=:fingerprint"
                ),
                {"fingerprint": decision.decision_fingerprint},
            )
            if existing is not None:
                return True
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_rule_activation_outcomes "
                    "(rule_activation_outcome_id,version,normative_rule_candidate_id,"
                    "normative_rule_candidate_version,qualification_decision_id,"
                    "qualification_decision_version,rule_version_id,edition_activation_decision_id,"
                    "edition_activation_decision_version,status,reason_code,edition_activation_status,"
                    "rule_lifecycle_status,decision_fingerprint,authority_identity_id,"
                    "authority_decision_ref,decided_at,supersedes_version) VALUES "
                    "(:id,:version,:candidate,:candidate_version,:qualification,1,:rule,:edition_decision,"
                    ":edition_decision_version,:status,:reason,:edition_status,:rule_status,:fingerprint,"
                    ":authority,:authority_ref,:decided_at,:supersedes)"
                ),
                {
                    "id": decision.decision_id,
                    "version": decision.version,
                    "candidate": decision.candidate_id,
                    "candidate_version": decision.candidate_version,
                    "qualification": decision.qualification_decision_id,
                    "rule": rule_version_id,
                    "edition_decision": edition_activation_decision[0]
                    if edition_activation_decision
                    else None,
                    "edition_decision_version": edition_activation_decision[1]
                    if edition_activation_decision
                    else None,
                    "status": decision.status.value,
                    "reason": decision.reason_code,
                    "edition_status": decision.edition_activation_status,
                    "rule_status": decision.rule_lifecycle_status,
                    "fingerprint": decision.decision_fingerprint,
                    "authority": authority_identity_id,
                    "authority_ref": authority_decision_ref,
                    "decided_at": decided_at,
                    "supersedes": decision.version - 1 if decision.version > 1 else None,
                },
            )
        return False


def new_gap_identity(stable_identity_key: str, gap_code: str) -> UUID:
    return deterministic_uuid(f"ntd-gap:{stable_identity_key}:{gap_code}")


def new_receipt_identity() -> UUID:
    return uuid7()
