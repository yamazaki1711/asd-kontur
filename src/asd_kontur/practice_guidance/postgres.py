"""Narrow PostgreSQL writes for practice-guide ingestion and publication."""

# ruff: noqa: E501 -- SQL fragments retain readable clause boundaries.

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7
from asd_kontur.harness.models import digest_of

from .models import (
    CoverageManifest,
    GuidanceCandidateVersion,
    GuidanceConflict,
    GuidanceCuratorAuthority,
    GuidanceGap,
    GuidanceVerification,
    GuideExecutionProfile,
    GuideIngestionReconciliation,
    GuideNtdRelevanceAssertion,
    GuidePageManifest,
    GuidePageTerminalReceipt,
    GuideSourceRow,
    GuideValidationFailure,
    NormativeReferenceCandidate,
    NormativeReferenceResolutionState,
    VerificationDisposition,
)

if TYPE_CHECKING:
    from .pipeline import PassAFailedCandidate


class PracticeGuideRepository:
    """Explicit application port; arbitrary SQL is not exposed to callers."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def register_guide_edition(
        self,
        *,
        guide_key: str,
        title: str,
        edition_label: str,
        source_artifact_id: UUID,
        source_version_id: UUID,
        source_digest: str,
        page_count: int,
        provenance: dict[str, object],
        actor_identity_id: str,
    ) -> tuple[UUID, UUID]:
        guide_id, edition_id = uuid7(), uuid7()
        provenance_digest = digest_of(provenance)
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT practice_guide_id FROM platform.practice_guides WHERE guide_key=:key"
                ),
                {"key": guide_key},
            ).scalar_one_or_none()
            if existing is None:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.practice_guides "
                        "(practice_guide_id,source_artifact_id,guide_key,title,authority_layer,status,created_by_identity_id,created_at) "
                        "VALUES (:id,:artifact,:key,:title,'methodological_guidance','active',:actor,:now)"
                    ),
                    {
                        "id": guide_id,
                        "artifact": source_artifact_id,
                        "key": guide_key,
                        "title": title,
                        "actor": actor_identity_id,
                        "now": datetime.now(UTC),
                    },
                )
            else:
                guide_id = UUID(str(existing))
            existing_edition = (
                session.execute(
                    sa.text(
                        "SELECT practice_guide_edition_id,source_digest,page_count,provenance_digest "
                        "FROM platform.practice_guide_editions "
                        "WHERE practice_guide_id=:guide AND edition_label=:label"
                    ),
                    {"guide": guide_id, "label": edition_label},
                )
                .mappings()
                .one_or_none()
            )
            if existing_edition is not None:
                if (
                    str(existing_edition["source_digest"]) != source_digest
                    or int(existing_edition["page_count"]) != page_count
                    or str(existing_edition["provenance_digest"]) != provenance_digest
                ):
                    raise ValueError("PracticeGuideEdition identity conflicts with source bytes")
                return guide_id, UUID(str(existing_edition["practice_guide_edition_id"]))
            ordinal = int(
                session.execute(
                    sa.text(
                        "SELECT COALESCE(max(edition_ordinal),0)+1 FROM platform.practice_guide_editions "
                        "WHERE practice_guide_id=:guide"
                    ),
                    {"guide": guide_id},
                ).scalar_one()
            )
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_editions "
                    "(practice_guide_edition_id,practice_guide_id,edition_ordinal,edition_label,source_version_id,"
                    "source_digest,page_count,status,provenance_payload,provenance_digest,"
                    "admitted_by_identity_id,admitted_at) VALUES "
                    "(:id,:guide,:ordinal,:label,:source,:digest,:pages,'admitted',"
                    "CAST(:provenance_payload AS jsonb),:provenance,:actor,:now)"
                ),
                {
                    "id": edition_id,
                    "guide": guide_id,
                    "ordinal": ordinal,
                    "label": edition_label,
                    "source": source_version_id,
                    "digest": source_digest,
                    "pages": page_count,
                    "provenance_payload": json.dumps(provenance, ensure_ascii=False),
                    "provenance": provenance_digest,
                    "actor": actor_identity_id,
                    "now": datetime.now(UTC),
                },
            )
            edition_state_fingerprint = digest_of(
                {
                    "edition_id": str(edition_id),
                    "sequence": 1,
                    "state": "admitted",
                    "reason": "source.accepted",
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_edition_states "
                    "(practice_guide_edition_state_id,practice_guide_edition_id,state_sequence,"
                    "state,reason_code,authority_identity_id,state_fingerprint,recorded_at) "
                    "VALUES (:id,:edition,1,'admitted','source.accepted',:actor,:fingerprint,:now)"
                ),
                {
                    "id": uuid7(),
                    "edition": edition_id,
                    "actor": actor_identity_id,
                    "fingerprint": edition_state_fingerprint,
                    "now": datetime.now(UTC),
                },
            )
        return guide_id, edition_id

    def save_page_manifest(self, edition_id: UUID, pages: tuple[GuidePageManifest, ...]) -> None:
        if not pages:
            raise ValueError("PageManifest cannot be empty")
        with Session(self._engine) as session, session.begin():
            expected = (
                session.execute(
                    sa.text(
                        "SELECT page_count,source_version_id FROM platform.practice_guide_editions "
                        "WHERE practice_guide_edition_id=:id"
                    ),
                    {"id": edition_id},
                )
                .mappings()
                .one()
            )
            if int(expected["page_count"]) != len(pages):
                raise ValueError("PageManifest count does not match the admitted source")
            if any(
                UUID(str(expected["source_version_id"])) != page.source_version_id for page in pages
            ):
                raise ValueError("PageManifest crossed SourceVersion identity")
            existing = tuple(
                session.execute(
                    sa.text(
                        "SELECT page_number,manifest_fingerprint FROM platform.practice_guide_page_manifests "
                        "WHERE practice_guide_edition_id=:edition ORDER BY page_number"
                    ),
                    {"edition": edition_id},
                )
            )
            expected_existing = tuple((page.page_number, page.fingerprint) for page in pages)
            if existing:
                if existing != expected_existing:
                    raise ValueError("Immutable PageManifest conflicts with an earlier inspection")
                return
            for page in pages:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.practice_guide_page_manifests "
                        "(practice_guide_edition_id,page_number,source_version_id,page_digest,width_points,height_points,"
                        "rotation,native_text_characters,image_count,content_kind,render_required,previous_page,next_page,"
                        "technical_flags,manifest_fingerprint) VALUES "
                        "(:edition,:page,:source,:digest,:width,:height,:rotation,:chars,:images,:kind,:render,:previous,:next,:flags,:fingerprint)"
                    ),
                    {
                        "edition": edition_id,
                        "page": page.page_number,
                        "source": page.source_version_id,
                        "digest": page.page_digest,
                        "width": page.width_points,
                        "height": page.height_points,
                        "rotation": page.rotation,
                        "chars": page.native_text_characters,
                        "images": page.image_count,
                        "kind": page.content_kind,
                        "render": page.render_required,
                        "previous": page.previous_page,
                        "next": page.next_page,
                        "flags": list(page.technical_flags),
                        "fingerprint": page.fingerprint,
                    },
                )

    def register_execution_profile(
        self,
        *,
        profile: GuideExecutionProfile,
        profile_version: str,
        qualification_state: str,
        qualification_evidence_digest: str | None,
    ) -> UUID:
        if qualification_state == "qualified_development" and qualification_evidence_digest is None:
            raise ValueError("Development qualification requires exact evidence")
        profile_id = uuid7()
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT execution_profile_id FROM platform.practice_guide_execution_profiles "
                    "WHERE profile_fingerprint=:fingerprint"
                ),
                {"fingerprint": profile.fingerprint},
            ).scalar_one_or_none()
            if existing is not None:
                return UUID(str(existing))
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_execution_profiles "
                    "(execution_profile_id,profile_version,provider,model_identity,model_revision,model_digest,"
                    "execution_format,quantization,runtime_version,prompt_version,schema_version,preprocessing_version,"
                    "renderer_version,verification_policy_version,deterministic_decoding,qualification_state,"
                    "qualification_evidence_digest,profile_fingerprint,created_at) VALUES "
                    "(:id,:version,:provider,:model,:revision,:digest,:format,:quantization,:runtime,:prompt,:schema,"
                    ":preprocessing,:renderer,:verification,true,:qualification,:evidence,:fingerprint,:now)"
                ),
                {
                    "id": profile_id,
                    "version": profile_version,
                    "provider": profile.provider,
                    "model": profile.model_identity,
                    "revision": profile.model_revision,
                    "digest": profile.model_digest,
                    "format": profile.execution_format,
                    "quantization": profile.quantization,
                    "runtime": profile.runtime_version,
                    "prompt": profile.prompt_version,
                    "schema": profile.schema_version,
                    "preprocessing": profile.preprocessing_version,
                    "renderer": profile.renderer_version,
                    "verification": profile.verification_policy_version,
                    "qualification": qualification_state,
                    "evidence": qualification_evidence_digest,
                    "fingerprint": profile.fingerprint,
                    "now": datetime.now(UTC),
                },
            )
        return profile_id

    def start_ingestion_run(
        self,
        *,
        edition_id: UUID,
        execution_profile_id: UUID,
        expected_page_count: int,
        pass_a_prompt_version: str,
        pass_b_prompt_version: str,
        validator_version: str,
        idempotency_key: str,
        actor_identity_id: str,
    ) -> UUID:
        run_id = uuid7()
        payload = {
            "edition_id": str(edition_id),
            "profile_id": str(execution_profile_id),
            "pages": expected_page_count,
            "pass_a": pass_a_prompt_version,
            "pass_b": pass_b_prompt_version,
            "validator": validator_version,
        }
        with Session(self._engine) as session, session.begin():
            prior = (
                session.execute(
                    sa.text(
                        "SELECT ingestion_run_id,run_fingerprint FROM platform.practice_guide_ingestion_runs "
                        "WHERE idempotency_key=:key"
                    ),
                    {"key": idempotency_key},
                )
                .mappings()
                .one_or_none()
            )
            fingerprint = digest_of(payload)
            if prior is not None:
                if str(prior["run_fingerprint"]) != fingerprint:
                    raise ValueError("Ingestion idempotency key conflicts with another plan")
                return UUID(str(prior["ingestion_run_id"]))
            now = datetime.now(UTC)
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_ingestion_runs "
                    "(ingestion_run_id,practice_guide_edition_id,execution_profile_id,expected_page_count,"
                    "pass_a_prompt_version,pass_b_prompt_version,validator_version,idempotency_key,state,"
                    "started_by_identity_id,started_at,run_fingerprint) VALUES "
                    "(:id,:edition,:profile,:pages,:pass_a,:pass_b,:validator,:key,'processing',:actor,:now,:fingerprint)"
                ),
                {
                    "id": run_id,
                    "edition": edition_id,
                    "profile": execution_profile_id,
                    "pages": expected_page_count,
                    "pass_a": pass_a_prompt_version,
                    "pass_b": pass_b_prompt_version,
                    "validator": validator_version,
                    "key": idempotency_key,
                    "actor": actor_identity_id,
                    "now": now,
                    "fingerprint": fingerprint,
                },
            )
            self._insert_run_state(
                session, run_id, 1, "processing", "ingestion.started", actor_identity_id
            )
            self._insert_edition_state(
                session,
                edition_id,
                "processing",
                "ingestion.started",
                actor_identity_id,
            )
        return run_id

    @staticmethod
    def _insert_run_state(
        session: Session,
        run_id: UUID,
        sequence: int,
        state: str,
        reason_code: str,
        actor_identity_id: str,
    ) -> None:
        fingerprint = digest_of(
            {"run": str(run_id), "sequence": sequence, "state": state, "reason": reason_code}
        )
        session.execute(
            sa.text(
                "INSERT INTO platform.practice_guide_ingestion_run_states "
                "(ingestion_run_state_id,ingestion_run_id,state_sequence,state,reason_code,"
                "authority_identity_id,state_fingerprint,recorded_at) VALUES "
                "(:id,:run,:sequence,:state,:reason,:actor,:fingerprint,:now)"
            ),
            {
                "id": uuid7(),
                "run": run_id,
                "sequence": sequence,
                "state": state,
                "reason": reason_code,
                "actor": actor_identity_id,
                "fingerprint": fingerprint,
                "now": datetime.now(UTC),
            },
        )

    @staticmethod
    def _insert_edition_state(
        session: Session,
        edition_id: UUID,
        state: str,
        reason_code: str,
        actor_identity_id: str,
    ) -> None:
        sequence = int(
            session.execute(
                sa.text(
                    "SELECT COALESCE(max(state_sequence),0)+1 FROM "
                    "platform.practice_guide_edition_states "
                    "WHERE practice_guide_edition_id=:edition"
                ),
                {"edition": edition_id},
            ).scalar_one()
        )
        fingerprint = digest_of(
            {
                "edition_id": str(edition_id),
                "sequence": sequence,
                "state": state,
                "reason": reason_code,
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO platform.practice_guide_edition_states "
                "(practice_guide_edition_state_id,practice_guide_edition_id,state_sequence,"
                "state,reason_code,authority_identity_id,state_fingerprint,recorded_at) "
                "VALUES (:id,:edition,:sequence,:state,:reason,:actor,:fingerprint,:now)"
            ),
            {
                "id": uuid7(),
                "edition": edition_id,
                "sequence": sequence,
                "state": state,
                "reason": reason_code,
                "actor": actor_identity_id,
                "fingerprint": fingerprint,
                "now": datetime.now(UTC),
            },
        )

    def save_candidate(self, run_id: UUID, candidate: GuidanceCandidateVersion) -> None:
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT candidate_fingerprint FROM platform.practice_guide_candidate_versions "
                    "WHERE guidance_candidate_id=:id AND version=:version"
                ),
                {"id": candidate.candidate_id, "version": candidate.version},
            ).scalar_one_or_none()
            if existing is not None:
                if str(existing) != candidate.fingerprint:
                    raise ValueError("CandidateVersion identity conflicts with persisted content")
                return
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_candidate_versions "
                    "(guidance_candidate_id,version,ingestion_run_id,source_version_id,page_number,region,guidance_kind,"
                    "section,topic,document_or_form_type,workflow_stage,field_or_element,instruction,required_inputs,"
                    "evidence_requirements,author_role_claims,common_error,recommended_practice,visual_example_region,"
                    "applicability_conditions,limitations,uncertainties,model_profile_fingerprint,parent_version,"
                    "candidate_fingerprint,created_at) VALUES "
                    "(:id,:version,:run,:source,:page,:region,:kind,:section,:topic,:form,:stage,:field,:instruction,"
                    "CAST(:inputs AS jsonb),CAST(:evidence AS jsonb),CAST(:roles AS jsonb),:error,:practice,:visual,"
                    "CAST(:applicability AS jsonb),CAST(:limitations AS jsonb),CAST(:uncertainties AS jsonb),"
                    ":profile,:parent,:fingerprint,:now)"
                ),
                {
                    "id": candidate.candidate_id,
                    "version": candidate.version,
                    "run": run_id,
                    "source": candidate.source_version_id,
                    "page": candidate.locator.page_number,
                    "region": list(candidate.locator.region),
                    "kind": candidate.kind,
                    "section": candidate.section,
                    "topic": candidate.topic,
                    "form": candidate.document_or_form_type,
                    "stage": candidate.workflow_stage,
                    "field": candidate.field_or_element,
                    "instruction": candidate.instruction,
                    "inputs": json.dumps(candidate.required_inputs, ensure_ascii=False),
                    "evidence": json.dumps(candidate.evidence_requirements, ensure_ascii=False),
                    "roles": json.dumps(candidate.author_role_claims, ensure_ascii=False),
                    "error": candidate.common_error,
                    "practice": candidate.recommended_practice,
                    "visual": list(candidate.visual_example_locator.region)
                    if candidate.visual_example_locator
                    else None,
                    "applicability": json.dumps(
                        candidate.applicability_conditions, ensure_ascii=False
                    ),
                    "limitations": json.dumps(candidate.limitations, ensure_ascii=False),
                    "uncertainties": json.dumps(candidate.uncertainties, ensure_ascii=False),
                    "profile": candidate.model_profile_fingerprint,
                    "parent": candidate.parent_version,
                    "fingerprint": candidate.fingerprint,
                    "now": datetime.now(UTC),
                },
            )

    def save_failed_candidate(
        self,
        run_id: UUID,
        source_version_id: UUID,
        failed: PassAFailedCandidate,
    ) -> None:
        fingerprint = digest_of(failed)
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT failed_candidate_fingerprint FROM "
                    "platform.practice_guide_failed_candidate_versions "
                    "WHERE guidance_candidate_id=:id AND version=:version"
                ),
                {"id": failed.candidate_id, "version": failed.candidate_version},
            ).scalar_one_or_none()
            if existing is not None:
                if str(existing) != fingerprint:
                    raise ValueError("Failed CandidateVersion identity conflict")
                return
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_failed_candidate_versions "
                    "(guidance_candidate_id,version,ingestion_run_id,source_version_id,page_number,ordinal,"
                    "failure_code,failure_field,invalid_region,raw_candidate,failed_candidate_fingerprint,"
                    "recorded_at) VALUES (:id,:version,:run,:source,:page,:ordinal,:code,:field,"
                    "CAST(:region AS jsonb),CAST(:candidate AS jsonb),:fingerprint,:now)"
                ),
                {
                    "id": failed.candidate_id,
                    "version": failed.candidate_version,
                    "run": run_id,
                    "source": source_version_id,
                    "page": failed.page_number,
                    "ordinal": failed.ordinal,
                    "code": failed.failure_code,
                    "field": failed.failure_field,
                    "region": json.dumps(failed.invalid_region, ensure_ascii=False),
                    "candidate": json.dumps(failed.raw_candidate, ensure_ascii=False),
                    "fingerprint": fingerprint,
                    "now": datetime.now(UTC),
                },
            )

    def save_ntd_source_row(self, run_id: UUID, row: GuideSourceRow) -> None:
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT source_row_fingerprint FROM platform.practice_guide_source_rows "
                    "WHERE source_row_id=:id"
                ),
                {"id": row.source_row_id},
            ).scalar_one_or_none()
            if existing is not None:
                if str(existing) != row.fingerprint:
                    raise ValueError("Guide source-row identity conflicts with persisted geometry")
                return
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_source_rows "
                    "(source_row_id,parent_guidance_candidate_id,parent_candidate_version,ingestion_run_id,"
                    "source_version_id,page_number,row_ordinal,region,"
                    "printed_ntd,work_or_rd_sections,id_note,layout_profile_version,extraction_digest,"
                    "parent_failed_receipt_digest,source_row_fingerprint,recorded_at) VALUES "
                    "(:id,:parent_candidate,:parent_version,:run,:source,:page,:ordinal,:region,"
                    ":ntd,:work,:note,:profile,:extraction,"
                    ":receipt,:fingerprint,:now)"
                ),
                {
                    "id": row.source_row_id,
                    "parent_candidate": row.parent_candidate_id,
                    "parent_version": row.parent_candidate_version,
                    "run": run_id,
                    "source": row.source_version_id,
                    "page": row.page_number,
                    "ordinal": row.row_ordinal,
                    "region": list(row.locator.region),
                    "ntd": row.printed_ntd,
                    "work": row.work_or_rd_sections,
                    "note": row.id_note,
                    "profile": row.layout_profile_version,
                    "extraction": row.extraction_digest,
                    "receipt": row.parent_failed_receipt_digest,
                    "fingerprint": row.fingerprint,
                    "now": datetime.now(UTC),
                },
            )

    def save_ntd_relevance_assertion(self, assertion: GuideNtdRelevanceAssertion) -> None:
        reference = assertion.normative_reference
        candidate_version = assertion.parent_candidate_version + 1
        with Session(self._engine) as session, session.begin():
            existing_reference = session.execute(
                sa.text(
                    "SELECT candidate_fingerprint FROM "
                    "platform.practice_guide_normative_reference_candidates "
                    "WHERE normative_reference_candidate_id=:id"
                ),
                {"id": reference.reference_candidate_id},
            ).scalar_one_or_none()
            if existing_reference is None:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.practice_guide_normative_reference_candidates "
                        "(normative_reference_candidate_id,source_row_id,printed_identifier,printed_title,"
                        "candidate_fingerprint,recorded_at) VALUES (:id,:row,:identifier,:title,:fingerprint,:now)"
                    ),
                    {
                        "id": reference.reference_candidate_id,
                        "row": assertion.source_row_id,
                        "identifier": reference.printed_identifier,
                        "title": reference.printed_title,
                        "fingerprint": reference.identity_fingerprint,
                        "now": datetime.now(UTC),
                    },
                )
            elif str(existing_reference) != reference.identity_fingerprint:
                raise ValueError("NormativeReferenceCandidate identity conflict")
            existing_assertion = session.execute(
                sa.text(
                    "SELECT assertion_fingerprint FROM platform.practice_guide_ntd_relevance_assertions "
                    "WHERE ntd_relevance_assertion_id=:id"
                ),
                {"id": assertion.assertion_id},
            ).scalar_one_or_none()
            if existing_assertion is not None:
                if str(existing_assertion) != assertion.fingerprint:
                    raise ValueError("GuideNtdRelevanceAssertion identity conflict")
                return
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_ntd_relevance_assertions "
                    "(ntd_relevance_assertion_id,guidance_candidate_id,candidate_version,source_row_id,"
                    "normative_reference_candidate_id,relevance_summary,document_or_form_type,workflow_stage,"
                    "applicability_conditions,uncertainty_codes,assertion_fingerprint,recorded_at) VALUES "
                    "(:id,:candidate,:version,:row,:reference,:summary,:form,:stage,CAST(:conditions AS jsonb),"
                    "CAST(:uncertainties AS jsonb),:fingerprint,:now)"
                ),
                {
                    "id": assertion.assertion_id,
                    "candidate": assertion.candidate_id,
                    "version": candidate_version,
                    "row": assertion.source_row_id,
                    "reference": reference.reference_candidate_id,
                    "summary": assertion.relevance_summary,
                    "form": assertion.document_or_form_type,
                    "stage": assertion.workflow_stage,
                    "conditions": json.dumps(
                        assertion.applicability_conditions, ensure_ascii=False
                    ),
                    "uncertainties": json.dumps(assertion.uncertainty_codes, ensure_ascii=False),
                    "fingerprint": assertion.fingerprint,
                    "now": datetime.now(UTC),
                },
            )

    def save_normative_reference_resolution(
        self,
        reference: NormativeReferenceCandidate,
        *,
        resolver_version: str,
    ) -> None:
        if reference.resolution_state is NormativeReferenceResolutionState.NOT_ATTEMPTED:
            raise ValueError("A pending NTD reference is not a resolver result")
        resolution_fingerprint = digest_of(
            {"reference": reference, "resolver_version": resolver_version}
        )
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT resolution_fingerprint FROM "
                    "platform.practice_guide_normative_reference_resolutions "
                    "WHERE normative_reference_candidate_id=:candidate"
                ),
                {"candidate": reference.reference_candidate_id},
            ).scalar_one_or_none()
            if existing is not None:
                if str(existing) != resolution_fingerprint:
                    raise ValueError("Normative reference resolution conflicts with prior receipt")
                return
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_normative_reference_resolutions "
                    "(normative_reference_resolution_id,normative_reference_candidate_id,resolution_state,"
                    "normative_document_id,normative_edition_id,uncertainty_code,resolver_version,"
                    "resolution_fingerprint,resolved_at) VALUES "
                    "(:id,:candidate,:state,:document,:edition,:uncertainty,:resolver,:fingerprint,:now)"
                ),
                {
                    "id": uuid7(),
                    "candidate": reference.reference_candidate_id,
                    "state": reference.resolution_state,
                    "document": reference.normative_document_id,
                    "edition": reference.normative_edition_id,
                    "uncertainty": reference.uncertainty_code,
                    "resolver": resolver_version,
                    "fingerprint": resolution_fingerprint,
                    "now": datetime.now(UTC),
                },
            )

    def save_validation_failures(
        self, failures: tuple[GuideValidationFailure, ...], *, validator_identity: str
    ) -> None:
        with Session(self._engine) as session, session.begin():
            for failure in failures:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.practice_guide_validation_results "
                        "(validation_result_id,guidance_candidate_id,candidate_version,validator_identity,"
                        "validator_version,failure_code,field_path,blocking,repairable,content_minimal_parameters,recorded_at) "
                        "VALUES (:id,:candidate,:version,:identity,:validator,:code,:field,:blocking,:repairable,"
                        "CAST(:parameters AS jsonb),:now) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "id": uuid7(),
                        "candidate": failure.candidate_id,
                        "version": failure.candidate_version,
                        "identity": validator_identity,
                        "validator": failure.validator_version,
                        "code": failure.failure_code,
                        "field": failure.field_path,
                        "blocking": failure.blocking,
                        "repairable": failure.repairable,
                        "parameters": json.dumps(failure.parameters, sort_keys=True),
                        "now": datetime.now(UTC),
                    },
                )

    def save_verification(self, verification: GuidanceVerification) -> None:
        with Session(self._engine) as session, session.begin():
            existing = (
                session.execute(
                    sa.text(
                        "SELECT disposition,result_digest FROM platform.practice_guide_verifications "
                        "WHERE guidance_candidate_id=:candidate AND candidate_version=:version"
                    ),
                    {
                        "candidate": verification.candidate_id,
                        "version": verification.candidate_version,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if (
                    str(existing["disposition"]) != verification.disposition
                    or str(existing["result_digest"]) != verification.result_digest
                ):
                    raise ValueError("Pass B verification conflicts with persisted receipt")
                return
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_verifications "
                    "(verification_id,guidance_candidate_id,candidate_version,disposition,source_version_id,"
                    "page_number,region,model_profile_fingerprint,verification_prompt_version,result_digest,verified_at) "
                    "VALUES (:id,:candidate,:version,:disposition,:source,:page,:region,:profile,:prompt,:digest,:at)"
                ),
                {
                    "id": verification.verification_id,
                    "candidate": verification.candidate_id,
                    "version": verification.candidate_version,
                    "disposition": verification.disposition,
                    "source": verification.source_version_id,
                    "page": verification.locator.page_number,
                    "region": list(verification.locator.region),
                    "profile": verification.model_profile_fingerprint,
                    "prompt": verification.verification_prompt_version,
                    "digest": verification.result_digest,
                    "at": verification.verified_at,
                },
            )

    def save_page_receipt(self, receipt: GuidePageTerminalReceipt) -> None:
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT receipt_digest FROM platform.practice_guide_page_terminal_receipts "
                    "WHERE ingestion_run_id=:run AND page_number=:page"
                ),
                {"run": receipt.ingestion_run_id, "page": receipt.page_number},
            ).scalar_one_or_none()
            if existing is not None:
                if str(existing) != receipt.receipt_digest:
                    raise ValueError("Page terminal receipt conflicts with persisted state")
                return
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_page_terminal_receipts "
                    "(ingestion_run_id,page_number,source_version_id,terminal_state,pass_a_attempt_ref,"
                    "pass_b_attempt_refs,candidate_count,verified_count,unresolved_count,receipt_digest,recorded_at) "
                    "VALUES (:run,:page,:source,:state,:pass_a,:pass_b,:candidates,:verified,:unresolved,:digest,:at)"
                ),
                {
                    "run": receipt.ingestion_run_id,
                    "page": receipt.page_number,
                    "source": receipt.source_version_id,
                    "state": receipt.state,
                    "pass_a": str(receipt.pass_a_attempt_id) if receipt.pass_a_attempt_id else None,
                    "pass_b": [str(receipt.pass_b_attempt_id)] if receipt.pass_b_attempt_id else [],
                    "candidates": receipt.candidate_count,
                    "verified": receipt.verified_count,
                    "unresolved": receipt.unresolved_count,
                    "digest": receipt.receipt_digest,
                    "at": receipt.recorded_at,
                },
            )

    def save_reconciliation(
        self,
        reconciliation: GuideIngestionReconciliation,
        *,
        actor_identity_id: str,
    ) -> UUID:
        reconciliation_id = uuid7()
        state_counts = {
            "verified": len(reconciliation.verified_pages),
            "partial_with_gaps": len(reconciliation.partial_pages),
            "no_methodological_content": len(reconciliation.no_content_pages),
            "unresolved": len(reconciliation.unresolved_pages),
            "insufficient_evidence": len(reconciliation.insufficient_pages),
            "model_failed": len(reconciliation.failed_pages),
            "technically_blocked": len(reconciliation.blocked_pages),
        }
        outcome = (
            "complete"
            if reconciliation.complete
            and not reconciliation.unresolved_pages
            and not reconciliation.failed_pages
            and not reconciliation.blocked_pages
            else "partial"
        )
        with Session(self._engine) as session, session.begin():
            existing = (
                session.execute(
                    sa.text(
                        "SELECT ingestion_reconciliation_id,reconciliation_fingerprint FROM "
                        "platform.practice_guide_ingestion_reconciliations "
                        "WHERE ingestion_run_id=:run"
                    ),
                    {"run": reconciliation.ingestion_run_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if str(existing["reconciliation_fingerprint"]) != reconciliation.fingerprint:
                    raise ValueError("Ingestion reconciliation conflicts with persisted state")
                return UUID(str(existing["ingestion_reconciliation_id"]))
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guide_ingestion_reconciliations "
                    "(ingestion_reconciliation_id,ingestion_run_id,expected_page_count,terminal_page_count,state_counts,"
                    "complete,reconciliation_fingerprint,reconciled_by_identity_id,reconciled_at) VALUES "
                    "(:id,:run,:expected,:terminal,CAST(:states AS jsonb),:complete,:fingerprint,:actor,:now)"
                ),
                {
                    "id": reconciliation_id,
                    "run": reconciliation.ingestion_run_id,
                    "expected": reconciliation.expected_pages,
                    "terminal": len(reconciliation.terminal_pages),
                    "states": json.dumps(state_counts, sort_keys=True),
                    "complete": reconciliation.complete,
                    "fingerprint": reconciliation.fingerprint,
                    "actor": actor_identity_id,
                    "now": datetime.now(UTC),
                },
            )
            sequence = int(
                session.execute(
                    sa.text(
                        "SELECT COALESCE(max(state_sequence),0)+1 FROM platform.practice_guide_ingestion_run_states "
                        "WHERE ingestion_run_id=:run"
                    ),
                    {"run": reconciliation.ingestion_run_id},
                ).scalar_one()
            )
            self._insert_run_state(
                session,
                reconciliation.ingestion_run_id,
                sequence,
                outcome,
                f"ingestion.{outcome}",
                actor_identity_id,
            )
            edition_id = UUID(
                str(
                    session.execute(
                        sa.text(
                            "SELECT practice_guide_edition_id FROM "
                            "platform.practice_guide_ingestion_runs "
                            "WHERE ingestion_run_id=:run"
                        ),
                        {"run": reconciliation.ingestion_run_id},
                    ).scalar_one()
                )
            )
            self._insert_edition_state(
                session,
                edition_id,
                "verified" if outcome == "complete" else "partial",
                f"ingestion.{outcome}",
                actor_identity_id,
            )
        return reconciliation_id

    def publish_verified_candidate(
        self,
        *,
        edition_id: UUID,
        candidate: GuidanceCandidateVersion,
        verification: GuidanceVerification,
        publication_decision_ref: str,
        curator: GuidanceCuratorAuthority,
    ) -> UUID:
        curator.require_publication()
        if verification.disposition is not VerificationDisposition.SUPPORTED:
            raise ValueError("Only Pass-B-supported candidates may enter canonical guidance")
        if (
            verification.candidate_id != candidate.candidate_id
            or verification.candidate_version != candidate.version
        ):
            raise ValueError("Publication verification does not match CandidateVersion")
        unit_id, evidence_id, locator_id, structural_unit_id = uuid7(), uuid7(), uuid7(), uuid7()
        with Session(self._engine) as session, session.begin():
            existing_unit = session.execute(
                sa.text(
                    "SELECT guidance_unit_id FROM platform.practice_guidance_units WHERE "
                    "guidance_candidate_id=:id AND candidate_version=:version"
                ),
                {"id": candidate.candidate_id, "version": candidate.version},
            ).scalar_one_or_none()
            if existing_unit is not None:
                return UUID(str(existing_unit))
            blocking = session.execute(
                sa.text(
                    "SELECT count(*) FROM platform.practice_guide_validation_results WHERE "
                    "guidance_candidate_id=:id AND candidate_version=:version AND blocking"
                ),
                {"id": candidate.candidate_id, "version": candidate.version},
            ).scalar_one()
            if blocking:
                raise ValueError(
                    "Candidate with blocking deterministic failures cannot be published"
                )
            page_digest = session.execute(
                sa.text(
                    "SELECT page_digest FROM platform.practice_guide_page_manifests WHERE "
                    "practice_guide_edition_id=:edition AND page_number=:page"
                ),
                {"edition": edition_id, "page": candidate.locator.page_number},
            ).scalar_one()
            locator_key = candidate.locator.key
            prior_locator = session.execute(
                sa.text(
                    "SELECT source_locator_id FROM platform.source_locators WHERE "
                    "source_version_id=:source AND locator_kind='page_region' AND locator_key=:key"
                ),
                {"source": candidate.source_version_id, "key": locator_key},
            ).scalar_one_or_none()
            if prior_locator is None:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.source_locators "
                        "(source_locator_id,source_version_id,locator_kind,locator_key,locator_value,fragment_digest) "
                        "VALUES (:id,:source,'page_region',:key,CAST(:value AS jsonb),:digest)"
                    ),
                    {
                        "id": locator_id,
                        "source": candidate.source_version_id,
                        "key": locator_key,
                        "value": json.dumps(
                            {
                                "page": candidate.locator.page_number,
                                "region": candidate.locator.region,
                            }
                        ),
                        "digest": page_digest,
                    },
                )
            else:
                locator_id = UUID(str(prior_locator))
            structural_path = (
                f"page/{candidate.locator.page_number}/region/"
                f"{hashlib.sha256((candidate.section + locator_key).encode()).hexdigest()[:24]}"
            )
            prior_structural_unit = session.execute(
                sa.text(
                    "SELECT structural_unit_id FROM platform.practice_guide_structural_units "
                    "WHERE practice_guide_edition_id=:edition AND structural_path=:path"
                ),
                {"edition": edition_id, "path": structural_path},
            ).scalar_one_or_none()
            if prior_structural_unit is None:
                structural_digest = digest_of(
                    {
                        "edition_id": str(edition_id),
                        "path": structural_path,
                        "title": candidate.section,
                        "page": candidate.locator.page_number,
                        "locator": locator_key,
                    }
                )
                session.execute(
                    sa.text(
                        "INSERT INTO platform.practice_guide_structural_units "
                        "(structural_unit_id,practice_guide_edition_id,parent_structural_unit_id,"
                        "unit_kind,structural_path,title,start_page,end_page,ordinal,integrity_digest) "
                        "VALUES (:id,:edition,NULL,'page_region',:path,:title,:page,:page,:ordinal,:digest)"
                    ),
                    {
                        "id": structural_unit_id,
                        "edition": edition_id,
                        "path": structural_path,
                        "title": candidate.section,
                        "page": candidate.locator.page_number,
                        "ordinal": candidate.locator.page_number,
                        "digest": structural_digest,
                    },
                )
            else:
                structural_unit_id = UUID(str(prior_structural_unit))
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guidance_units "
                    "(guidance_unit_id,version,practice_guide_edition_id,structural_unit_id,guidance_candidate_id,candidate_version,"
                    "guidance_kind,normalized_instruction,section,topic,document_or_form_type,workflow_stage,field_or_element,"
                    "required_inputs,evidence_requirements,author_role_claims,common_error,recommended_practice,"
                    "applicability_conditions,limitations,authority_layer,validation_status,publication_decision_ref,"
                    "curator_identity_id,integrity_digest,published_at) VALUES "
                    "(:id,1,:edition,:structural_unit,:candidate,:candidate_version,:kind,:instruction,:section,:topic,:form,:stage,:field,"
                    "CAST(:inputs AS jsonb),CAST(:evidence AS jsonb),CAST(:roles AS jsonb),:error,:practice,"
                    "CAST(:applicability AS jsonb),CAST(:limitations AS jsonb),'methodological_guidance','verified',"
                    ":decision,:curator,:digest,:now)"
                ),
                {
                    "id": unit_id,
                    "edition": edition_id,
                    "structural_unit": structural_unit_id,
                    "candidate": candidate.candidate_id,
                    "candidate_version": candidate.version,
                    "kind": candidate.kind,
                    "instruction": candidate.instruction,
                    "section": candidate.section,
                    "topic": candidate.topic,
                    "form": candidate.document_or_form_type,
                    "stage": candidate.workflow_stage,
                    "field": candidate.field_or_element,
                    "inputs": json.dumps(candidate.required_inputs, ensure_ascii=False),
                    "evidence": json.dumps(candidate.evidence_requirements, ensure_ascii=False),
                    "roles": json.dumps(candidate.author_role_claims, ensure_ascii=False),
                    "error": candidate.common_error,
                    "practice": candidate.recommended_practice,
                    "applicability": json.dumps(
                        candidate.applicability_conditions, ensure_ascii=False
                    ),
                    "limitations": json.dumps(candidate.limitations, ensure_ascii=False),
                    "decision": publication_decision_ref,
                    "curator": curator.identity_id,
                    "digest": candidate.fingerprint,
                    "now": datetime.now(UTC),
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guidance_evidence "
                    "(guidance_evidence_id,guidance_unit_id,guidance_unit_version,source_version_id,"
                    "source_locator_id,page_number,region,fragment_digest,evidence_role,verified_at) "
                    "VALUES (:id,:unit,1,:source,:locator,:page,:region,:digest,'primary',:now)"
                ),
                {
                    "id": evidence_id,
                    "unit": unit_id,
                    "source": candidate.source_version_id,
                    "locator": locator_id,
                    "page": candidate.locator.page_number,
                    "region": list(candidate.locator.region),
                    "digest": page_digest,
                    "now": datetime.now(UTC),
                },
            )
            if candidate.visual_example_locator is not None:
                visual_locator_id = uuid7()
                visual_key = candidate.visual_example_locator.key
                prior_visual_locator = session.execute(
                    sa.text(
                        "SELECT source_locator_id FROM platform.source_locators WHERE "
                        "source_version_id=:source AND locator_kind='page_region' AND locator_key=:key"
                    ),
                    {"source": candidate.source_version_id, "key": visual_key},
                ).scalar_one_or_none()
                if prior_visual_locator is None:
                    session.execute(
                        sa.text(
                            "INSERT INTO platform.source_locators "
                            "(source_locator_id,source_version_id,locator_kind,locator_key,"
                            "locator_value,fragment_digest) VALUES "
                            "(:id,:source,'page_region',:key,CAST(:value AS jsonb),:digest)"
                        ),
                        {
                            "id": visual_locator_id,
                            "source": candidate.source_version_id,
                            "key": visual_key,
                            "value": json.dumps(
                                {
                                    "page": candidate.visual_example_locator.page_number,
                                    "region": candidate.visual_example_locator.region,
                                }
                            ),
                            "digest": page_digest,
                        },
                    )
                else:
                    visual_locator_id = UUID(str(prior_visual_locator))
                session.execute(
                    sa.text(
                        "INSERT INTO platform.practice_guidance_evidence "
                        "(guidance_evidence_id,guidance_unit_id,guidance_unit_version,"
                        "source_version_id,source_locator_id,page_number,region,fragment_digest,"
                        "evidence_role,verified_at) VALUES "
                        "(:id,:unit,1,:source,:locator,:page,:region,:digest,'visual_example',:now)"
                    ),
                    {
                        "id": uuid7(),
                        "unit": unit_id,
                        "source": candidate.source_version_id,
                        "locator": visual_locator_id,
                        "page": candidate.visual_example_locator.page_number,
                        "region": list(candidate.visual_example_locator.region),
                        "digest": page_digest,
                        "now": datetime.now(UTC),
                    },
                )
            for ordinal, uncertainty in enumerate(candidate.uncertainties, start=1):
                session.execute(
                    sa.text(
                        "INSERT INTO platform.practice_guidance_uncertainties "
                        "(guidance_uncertainty_id,guidance_unit_id,guidance_unit_version,"
                        "uncertainty_code,state,content_minimal_parameters,recorded_at) "
                        "VALUES (:id,:unit,1,'SOURCE_OR_MODEL_UNCERTAINTY','open',"
                        "CAST(:parameters AS jsonb),:now)"
                    ),
                    {
                        "id": uuid7(),
                        "unit": unit_id,
                        "parameters": json.dumps(
                            {"ordinal": ordinal, "statement": uncertainty},
                            ensure_ascii=False,
                        ),
                        "now": datetime.now(UTC),
                    },
                )
        return unit_id

    def record_guidance_conflict(
        self,
        *,
        guidance_unit_id: UUID,
        guidance_unit_version: int,
        conflicting_authority_layer: str,
        conflicting_subject_ref: str,
        conflict_type: str,
        uncertainty_ref: str,
        curator: GuidanceCuratorAuthority,
    ) -> UUID:
        curator.require_conflict_recording()
        conflict_id = uuid7()
        conflict = GuidanceConflict(
            conflict_id,
            guidance_unit_id,
            guidance_unit_version,
            conflicting_authority_layer,
            conflicting_subject_ref,
            conflict_type,
            uncertainty_ref,
        )
        with Session(self._engine) as session, session.begin():
            target = (
                session.execute(
                    sa.text(
                        "SELECT guidance_candidate_id,candidate_version "
                        "FROM platform.practice_guidance_units WHERE "
                        "guidance_unit_id=:id AND version=:version"
                    ),
                    {"id": guidance_unit_id, "version": guidance_unit_version},
                )
                .mappings()
                .one_or_none()
            )
            if target is None:
                raise ValueError("Guidance conflict target does not exist")
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guidance_conflicts "
                    "(guidance_conflict_id,guidance_unit_id,guidance_unit_version,"
                    "guidance_candidate_id,candidate_version,"
                    "conflicting_authority_layer,conflicting_subject_ref,conflict_type,state,"
                    "uncertainty_ref,decision_ref,recorded_at) VALUES "
                    "(:id,:unit,:version,:candidate,:candidate_version,:layer,:subject,:type,"
                    "'open',:uncertainty,NULL,:now)"
                ),
                {
                    "id": conflict.conflict_id,
                    "unit": conflict.guidance_unit_id,
                    "version": conflict.guidance_unit_version,
                    "candidate": target["guidance_candidate_id"],
                    "candidate_version": target["candidate_version"],
                    "layer": conflict.conflicting_authority_layer,
                    "subject": conflict.conflicting_subject_ref,
                    "type": conflict.conflict_type,
                    "uncertainty": conflict.uncertainty_ref,
                    "now": datetime.now(UTC),
                },
            )
        return conflict.conflict_id

    def record_candidate_guidance_conflict(
        self,
        *,
        candidate: GuidanceCandidateVersion,
        conflicting_candidate: GuidanceCandidateVersion,
        conflict_type: str,
        curator: GuidanceCuratorAuthority,
    ) -> UUID:
        curator.require_conflict_recording()
        if candidate.source_version_id != conflicting_candidate.source_version_id:
            raise ValueError("Candidate conflict must remain within one source version")
        subject = f"candidate:{conflicting_candidate.candidate_id}:v{conflicting_candidate.version}"
        with Session(self._engine) as session, session.begin():
            exists = session.execute(
                sa.text(
                    "SELECT count(*) FROM platform.practice_guide_candidate_versions WHERE "
                    "(guidance_candidate_id=:left_id AND version=:left_version) OR "
                    "(guidance_candidate_id=:right_id AND version=:right_version)"
                ),
                {
                    "left_id": candidate.candidate_id,
                    "left_version": candidate.version,
                    "right_id": conflicting_candidate.candidate_id,
                    "right_version": conflicting_candidate.version,
                },
            ).scalar_one()
            if int(exists) != 2:
                raise ValueError("Candidate conflict target does not exist")
            existing_conflict = session.execute(
                sa.text(
                    "SELECT guidance_conflict_id FROM platform.practice_guidance_conflicts "
                    "WHERE guidance_candidate_id=:candidate AND candidate_version=:version "
                    "AND conflicting_authority_layer='methodological_guidance_peer' "
                    "AND conflicting_subject_ref=:subject AND conflict_type=:type AND state='open'"
                ),
                {
                    "candidate": candidate.candidate_id,
                    "version": candidate.version,
                    "subject": subject,
                    "type": conflict_type,
                },
            ).scalar_one_or_none()
            if existing_conflict is not None:
                return UUID(str(existing_conflict))
            conflict_id = uuid7()
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guidance_conflicts "
                    "(guidance_conflict_id,guidance_unit_id,guidance_unit_version,"
                    "guidance_candidate_id,candidate_version,conflicting_authority_layer,"
                    "conflicting_subject_ref,conflict_type,state,uncertainty_ref,decision_ref,"
                    "recorded_at) VALUES "
                    "(:id,NULL,NULL,:candidate,:version,'methodological_guidance_peer',:subject,"
                    ":type,'open',:uncertainty,NULL,:now)"
                ),
                {
                    "id": conflict_id,
                    "candidate": candidate.candidate_id,
                    "version": candidate.version,
                    "subject": subject,
                    "type": conflict_type,
                    "uncertainty": f"guidance-conflict:{conflict_id}",
                    "now": datetime.now(UTC),
                },
            )
        return conflict_id

    def save_coverage_manifest(
        self,
        manifest: CoverageManifest,
        gaps: tuple[GuidanceGap, ...],
    ) -> None:
        if any(gap.coverage_manifest_id != manifest.coverage_manifest_id for gap in gaps):
            raise ValueError("GuidanceGap belongs to another CoverageManifest")
        if len(gaps) != manifest.gap_count:
            raise ValueError("CoverageManifest gap count does not reconcile")
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT manifest_fingerprint FROM platform.practice_guidance_coverage_manifests "
                    "WHERE coverage_manifest_id=:id"
                ),
                {"id": manifest.coverage_manifest_id},
            ).scalar_one_or_none()
            if existing is not None:
                if str(existing) != manifest.manifest_fingerprint:
                    raise ValueError("CoverageManifest identity conflicts with persisted content")
                return
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_guidance_coverage_manifests "
                    "(coverage_manifest_id,practice_guide_edition_id,ingestion_run_id,"
                    "coverage_manifest_version,publication_status,expected_page_count,"
                    "terminal_page_count,page_state_counts,candidate_state_counts,"
                    "guidance_unit_count,gap_count,conflict_count,reconciliation_fingerprint,"
                    "manifest_fingerprint,recorded_at) VALUES "
                    "(:id,:edition,:run,:version,:status,:expected,:terminal,CAST(:pages AS jsonb),"
                    "CAST(:candidates AS jsonb),:guidance,:gaps,:conflicts,:reconciliation,"
                    ":fingerprint,:recorded)"
                ),
                {
                    "id": manifest.coverage_manifest_id,
                    "edition": manifest.practice_guide_edition_id,
                    "run": manifest.ingestion_run_id,
                    "version": manifest.version,
                    "status": manifest.publication_status,
                    "expected": manifest.expected_page_count,
                    "terminal": manifest.terminal_page_count,
                    "pages": json.dumps(manifest.page_state_counts, sort_keys=True),
                    "candidates": json.dumps(manifest.candidate_state_counts, sort_keys=True),
                    "guidance": manifest.guidance_unit_count,
                    "gaps": manifest.gap_count,
                    "conflicts": manifest.conflict_count,
                    "reconciliation": manifest.reconciliation_fingerprint,
                    "fingerprint": manifest.manifest_fingerprint,
                    "recorded": manifest.recorded_at,
                },
            )
            for gap in gaps:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.practice_guidance_gaps "
                        "(guidance_gap_id,coverage_manifest_id,source_version_id,page_number,"
                        "guidance_candidate_id,candidate_version,gap_code,terminal_state,topic,"
                        "document_or_form_type,field_or_element,searchable_text,"
                        "content_minimal_parameters,gap_fingerprint,recorded_at) VALUES "
                        "(:id,:manifest,:source,:page,:candidate,:version,:code,:state,:topic,"
                        ":form,:field,:search,CAST(:parameters AS jsonb),:fingerprint,:recorded)"
                    ),
                    {
                        "id": gap.guidance_gap_id,
                        "manifest": gap.coverage_manifest_id,
                        "source": gap.source_version_id,
                        "page": gap.page_number,
                        "candidate": gap.candidate_id,
                        "version": gap.candidate_version,
                        "code": gap.gap_code,
                        "state": gap.terminal_state,
                        "topic": gap.topic,
                        "form": gap.document_or_form_type,
                        "field": gap.field_or_element,
                        "search": gap.searchable_text,
                        "parameters": json.dumps(
                            gap.content_minimal_parameters, ensure_ascii=False, sort_keys=True
                        ),
                        "fingerprint": gap.gap_fingerprint,
                        "recorded": gap.recorded_at,
                    },
                )

    def rebuild_lexical_projection(self, edition_id: UUID) -> UUID:
        version_id = uuid7()
        with Session(self._engine) as session, session.begin():
            rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT guidance_unit_id,version,normalized_instruction,section,topic,"
                        "COALESCE(document_or_form_type,''),COALESCE(field_or_element,'') "
                        "FROM platform.practice_guidance_units u WHERE practice_guide_edition_id=:edition "
                        "AND NOT EXISTS (SELECT 1 FROM platform.practice_guidance_conflicts c "
                        "WHERE c.guidance_unit_id=u.guidance_unit_id "
                        "AND c.guidance_unit_version=u.version AND c.state='open') "
                        "ORDER BY guidance_unit_id,version"
                    ),
                    {"edition": edition_id},
                )
            )
            source_fingerprint = digest_of([tuple(str(value) for value in row) for row in rows])
            session.execute(
                sa.text(
                    "INSERT INTO projection.practice_guidance_lexical_versions "
                    "(lexical_version_id,practice_guide_edition_id,projection_contract_version,source_fingerprint,"
                    "state,entry_count,built_at) VALUES (:id,:edition,'1.5.0',:fingerprint,:state,:count,:now)"
                ),
                {
                    "id": version_id,
                    "edition": edition_id,
                    "fingerprint": source_fingerprint,
                    "state": "ready" if rows else "empty",
                    "count": len(rows),
                    "now": datetime.now(UTC),
                },
            )
            for row in rows:
                text = " ".join(str(value) for value in row[2:] if value)
                entry_digest = f"sha256:{hashlib.sha256(text.encode()).hexdigest()}"
                session.execute(
                    sa.text(
                        "INSERT INTO projection.practice_guidance_lexical_entries "
                        "(lexical_version_id,guidance_unit_id,guidance_unit_version,searchable_text,entry_digest) "
                        "VALUES (:index,:unit,:version,:text,:digest)"
                    ),
                    {
                        "index": version_id,
                        "unit": row[0],
                        "version": row[1],
                        "text": text,
                        "digest": entry_digest,
                    },
                )
        return version_id
