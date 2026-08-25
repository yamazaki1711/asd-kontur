"""PostgreSQL construction and persistence for ID Practice Intelligence."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of

from .intelligence import (
    CONSTRUCTION_PROFILE_VERSION,
    construct_practice_intelligence,
    construction_fingerprint,
    intelligence_unit_document,
    intelligence_unit_from_document,
    playbook_document,
    playbook_from_document,
)
from .memory_backup import canonical_semantic_fingerprint
from .models import (
    ContextAssemblyPolicy,
    IDPracticeIntelligenceUnit,
    PracticeGuideEditionActivationDecision,
    PracticeMemoryBackupManifest,
    PracticePlaybook,
)

INTELLIGENCE_PROJECTION_VERSION = "practice-intelligence-lexical-v0.1.0"
CONTEXT_ASSEMBLY_POLICY_VERSION = "id-practice-context-assembly-v0.1.0"


def default_context_assembly_policy(edition_id: UUID) -> ContextAssemblyPolicy:
    return ContextAssemblyPolicy(
        policy_id=deterministic_uuid(
            f"id-practice-context-policy:{edition_id}:{CONTEXT_ASSEMBLY_POLICY_VERSION}"
        ),
        version=1,
        practice_guide_edition_id=edition_id,
        policy_key=f"{CONTEXT_ASSEMBLY_POLICY_VERSION}:{edition_id}",
        allowed_modes=("Tender", "Support", "Audit", "Restoration", "IDGenerator"),
        allowed_purposes=(
            "id.tender",
            "id.support",
            "id.audit",
            "id.restoration",
            "id.generator",
            "id.memory_acceptance",
        ),
        selector_dimensions=(
            "document_type",
            "form_type",
            "field",
            "work_type",
            "rd_section",
            "construction_stage",
            "control_operation",
            "evidence_requirement",
            "package_process",
            "mode",
            "purpose",
        ),
        max_intelligence_units=12,
        max_playbooks=8,
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _require_or_create_initial_activation(
    session: Session, *, edition_id: UUID, recorded_at: datetime
) -> PracticeGuideEditionActivationDecision:
    guide_id = UUID(
        str(
            session.execute(
                sa.text(
                    "SELECT practice_guide_id FROM platform.practice_guide_editions "
                    "WHERE practice_guide_edition_id=:edition"
                ),
                {"edition": edition_id},
            ).scalar_one()
        )
    )
    session.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:guide_text,0))"),
        {"guide_text": str(guide_id)},
    )
    active = (
        session.execute(
            sa.text(
                "SELECT activation_decision_id,version,practice_guide_id,selected_edition_id,"
                "supersedes_version,reason_code,owner_decision_ref,authority_identity_id,"
                "recorded_at FROM platform.practice_guide_edition_activation_decisions "
                "WHERE practice_guide_id=:guide ORDER BY version DESC LIMIT 1"
            ),
            {"guide": guide_id},
        )
        .mappings()
        .one_or_none()
    )
    if active is not None:
        if UUID(str(active["selected_edition_id"])) != edition_id:
            raise ValueError(
                "PracticeGuideEdition is not selected by the active versioned decision"
            )
        return PracticeGuideEditionActivationDecision(
            UUID(str(active["activation_decision_id"])),
            int(active["version"]),
            guide_id,
            edition_id,
            int(active["supersedes_version"]) if active["supersedes_version"] else None,
            str(active["reason_code"]),
            str(active["owner_decision_ref"]),
            str(active["authority_identity_id"]),
            active["recorded_at"],
        )
    decision = PracticeGuideEditionActivationDecision(
        activation_decision_id=deterministic_uuid(f"practice-guide-activation:{guide_id}"),
        version=1,
        practice_guide_id=guide_id,
        selected_edition_id=edition_id,
        supersedes_version=None,
        reason_code="INITIAL_PERMANENT_PRACTICE_EDITION",
        owner_decision_ref="ADR-0011;owner:Oleg Shcherbakov;2026-08-25",
        authority_identity_id="owner.oleg-shcherbakov",
        recorded_at=recorded_at,
    )
    session.execute(
        sa.text(
            "INSERT INTO platform.practice_guide_edition_activation_decisions "
            "(activation_decision_id,version,practice_guide_id,selected_edition_id,"
            "supersedes_version,reason_code,owner_decision_ref,authority_identity_id,"
            "decision_fingerprint,recorded_at) VALUES "
            "(:id,:version,:guide,:edition,NULL,:reason,:owner,:actor,:fingerprint,:at)"
        ),
        {
            "id": decision.activation_decision_id,
            "version": decision.version,
            "guide": decision.practice_guide_id,
            "edition": decision.selected_edition_id,
            "reason": decision.reason_code,
            "owner": decision.owner_decision_ref,
            "actor": decision.authority_identity_id,
            "fingerprint": decision.fingerprint,
            "at": decision.recorded_at,
        },
    )
    return decision


def _guidance_rows(session: Session, coverage_manifest_id: UUID) -> list[dict[str, Any]]:
    coverage = (
        session.execute(
            sa.text(
                "SELECT practice_guide_edition_id,publication_status FROM "
                "platform.practice_guidance_coverage_manifests WHERE coverage_manifest_id=:id"
            ),
            {"id": coverage_manifest_id},
        )
        .mappings()
        .one_or_none()
    )
    if coverage is None:
        raise ValueError("CoverageManifest does not exist")
    rows = [
        dict(row)
        for row in session.execute(
            sa.text(
                "SELECT u.guidance_unit_id,u.version,u.guidance_candidate_id,u.candidate_version,"
                "u.guidance_kind,u.normalized_instruction,u.section,u.topic,"
                "u.document_or_form_type,u.workflow_stage,u.field_or_element,u.required_inputs,"
                "u.evidence_requirements,u.author_role_claims,u.common_error,u.recommended_practice,"
                "u.applicability_conditions,u.limitations,cv.uncertainties "
                "FROM platform.practice_guidance_units u "
                "JOIN platform.practice_guide_candidate_versions cv ON "
                "cv.guidance_candidate_id=u.guidance_candidate_id AND "
                "cv.version=u.candidate_version "
                "WHERE u.practice_guide_edition_id=:edition "
                "AND NOT EXISTS (SELECT 1 FROM platform.practice_guidance_conflicts c "
                "WHERE c.guidance_unit_id=u.guidance_unit_id AND "
                "c.guidance_unit_version=u.version AND c.state='open') "
                "ORDER BY u.guidance_unit_id,u.version"
            ),
            {"edition": coverage["practice_guide_edition_id"]},
        ).mappings()
    ]
    evidence_by_guidance: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in session.execute(
        sa.text(
            "SELECT ge.guidance_unit_id,ge.guidance_unit_version,ge.source_version_id,"
            "ge.page_number,ge.region,ge.fragment_digest FROM "
            "platform.practice_guidance_evidence ge "
            "JOIN platform.practice_guidance_units u ON u.guidance_unit_id=ge.guidance_unit_id "
            "AND u.version=ge.guidance_unit_version WHERE u.practice_guide_edition_id=:edition "
            "ORDER BY ge.guidance_unit_id,ge.guidance_unit_version,ge.guidance_evidence_id"
        ),
        {"edition": coverage["practice_guide_edition_id"]},
    ).mappings():
        evidence_by_guidance[
            (str(row["guidance_unit_id"]), int(row["guidance_unit_version"]))
        ].append(dict(row))
    normative_by_guidance: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in session.execute(
        sa.text(
            "SELECT u.guidance_unit_id,u.version,n.printed_identifier,n.printed_title,"
            "r.resolution_state,r.normative_document_id,r.normative_edition_id,"
            "r.uncertainty_code,r.resolver_version FROM platform.practice_guidance_units u "
            "JOIN platform.practice_guide_ntd_relevance_assertions a ON "
            "a.guidance_candidate_id=u.guidance_candidate_id AND "
            "a.candidate_version=u.candidate_version "
            "JOIN platform.practice_guide_normative_reference_candidates n ON "
            "n.normative_reference_candidate_id=a.normative_reference_candidate_id "
            "JOIN platform.practice_guide_normative_reference_resolutions r ON "
            "r.normative_reference_candidate_id=n.normative_reference_candidate_id "
            "WHERE u.practice_guide_edition_id=:edition ORDER BY u.guidance_unit_id,u.version"
        ),
        {"edition": coverage["practice_guide_edition_id"]},
    ).mappings():
        normative_by_guidance[(str(row["guidance_unit_id"]), int(row["version"]))].append(
            {
                "printed_identifier": str(row["printed_identifier"]),
                "printed_title": str(row["printed_title"]) if row["printed_title"] else None,
                "resolution_state": str(row["resolution_state"]),
                "normative_document_id": (
                    str(row["normative_document_id"]) if row["normative_document_id"] else None
                ),
                "normative_edition_id": (
                    str(row["normative_edition_id"]) if row["normative_edition_id"] else None
                ),
                "uncertainty_code": str(row["uncertainty_code"]),
                "resolver_version": str(row["resolver_version"]),
            }
        )
    for guidance_row in rows:
        key = (str(guidance_row["guidance_unit_id"]), int(guidance_row["version"]))
        guidance_row["evidence"] = evidence_by_guidance[key]
        guidance_row["normative_references"] = normative_by_guidance[key]
    return rows


def construct_manifest(engine: Engine, coverage_manifest_id: UUID) -> dict[str, Any]:
    with Session(engine) as session:
        coverage = (
            session.execute(
                sa.text(
                    "SELECT practice_guide_edition_id,publication_status,manifest_fingerprint FROM "
                    "platform.practice_guidance_coverage_manifests WHERE coverage_manifest_id=:id"
                ),
                {"id": coverage_manifest_id},
            )
            .mappings()
            .one_or_none()
        )
        if coverage is None:
            raise ValueError("CoverageManifest does not exist")
        guidance_rows = _guidance_rows(session, coverage_manifest_id)
    edition_id = UUID(str(coverage["practice_guide_edition_id"]))
    units, playbooks = construct_practice_intelligence(
        guidance_rows=guidance_rows,
        edition_id=edition_id,
        coverage_manifest_id=coverage_manifest_id,
        publication_status=str(coverage["publication_status"]),
    )
    fingerprint = construction_fingerprint(units, playbooks)
    construction_manifest_id = deterministic_uuid(
        f"kg-id-intelligence-manifest:{coverage_manifest_id}:{CONSTRUCTION_PROFILE_VERSION}"
    )
    return {
        "contract": "id-practice-intelligence-construction/0.1.0",
        "construction_manifest_id": str(construction_manifest_id),
        "coverage_manifest_id": str(coverage_manifest_id),
        "practice_guide_edition_id": str(edition_id),
        "publication_status": str(coverage["publication_status"]),
        "coverage_manifest_fingerprint": str(coverage["manifest_fingerprint"]),
        "construction_profile_version": CONSTRUCTION_PROFILE_VERSION,
        "source_guidance_count": len(guidance_rows),
        "intelligence_unit_count": len(units),
        "playbook_count": len(playbooks),
        "construction_fingerprint": fingerprint,
        "authority_layer": "methodological_practice",
        "product_ready": False,
        "constructed_at": datetime.now(UTC).isoformat(),
        "intelligence_kind_counts": {
            kind: sum(1 for unit in units if unit.kind.value == kind)
            for kind in sorted({unit.kind.value for unit in units})
        },
        "intelligence_units": [intelligence_unit_document(unit) for unit in units],
        "playbooks": [playbook_document(playbook) for playbook in playbooks],
    }


def _manifest_values(
    document: Mapping[str, Any],
) -> tuple[
    UUID, UUID, datetime, tuple[IDPracticeIntelligenceUnit, ...], tuple[PracticePlaybook, ...]
]:
    raw_units = document.get("intelligence_units")
    raw_playbooks = document.get("playbooks")
    if not isinstance(raw_units, list) or not isinstance(raw_playbooks, list):
        raise ValueError("Practice-intelligence construction manifest is malformed")
    units = tuple(
        intelligence_unit_from_document(value) for value in raw_units if isinstance(value, Mapping)
    )
    playbooks = tuple(
        playbook_from_document(value) for value in raw_playbooks if isinstance(value, Mapping)
    )
    if len(units) != len(raw_units) or len(playbooks) != len(raw_playbooks):
        raise ValueError("Practice-intelligence construction items are malformed")
    fingerprint = construction_fingerprint(units, playbooks)
    if fingerprint != document.get("construction_fingerprint"):
        raise ValueError("Practice-intelligence construction fingerprint mismatch")
    if int(document["intelligence_unit_count"]) != len(units):
        raise ValueError("Practice-intelligence unit count mismatch")
    if int(document["playbook_count"]) != len(playbooks):
        raise ValueError("PracticePlaybook count mismatch")
    return (
        UUID(str(document["construction_manifest_id"])),
        UUID(str(document["coverage_manifest_id"])),
        datetime.fromisoformat(str(document["constructed_at"])),
        units,
        playbooks,
    )


def _insert_unit(
    session: Session,
    construction_manifest_id: UUID,
    constructed_at: datetime,
    unit: IDPracticeIntelligenceUnit,
) -> None:
    session.execute(
        sa.text(
            "INSERT INTO platform.practice_intelligence_units "
            "(intelligence_unit_id,version,construction_manifest_id,practice_guide_edition_id,"
            "coverage_manifest_id,intelligence_kind,title,instruction,rationale,"
            "applicability_conditions,work_types,document_types,form_types,workflow_stages,"
            "field_elements,required_inputs,evidence_requirements,allowed_variants,failure_patterns,"
            "checklist_items,dependency_refs,normative_references,uncertainties,"
            "construction_profile_version,authority_layer,integrity_digest,constructed_at) VALUES "
            "(:id,:version,:manifest,:edition,:coverage,:kind,:title,:instruction,:rationale,"
            "CAST(:applicability AS jsonb),CAST(:work AS jsonb),CAST(:documents AS jsonb),"
            "CAST(:forms AS jsonb),CAST(:workflow AS jsonb),CAST(:fields AS jsonb),"
            "CAST(:inputs AS jsonb),CAST(:evidence_requirements AS jsonb),CAST(:variants AS jsonb),"
            "CAST(:failures AS jsonb),CAST(:checklist AS jsonb),CAST(:dependencies AS jsonb),"
            "CAST(:normative AS jsonb),CAST(:uncertainties AS jsonb),:profile,"
            "'methodological_practice',:digest,:at)"
        ),
        {
            "id": unit.intelligence_unit_id,
            "version": unit.version,
            "manifest": construction_manifest_id,
            "edition": unit.practice_guide_edition_id,
            "coverage": unit.coverage_manifest_id,
            "kind": unit.kind.value,
            "title": unit.title,
            "instruction": unit.instruction,
            "rationale": unit.rationale,
            "applicability": _json(unit.applicability_conditions),
            "work": _json(unit.work_types),
            "documents": _json(unit.document_types),
            "forms": _json(unit.form_types),
            "workflow": _json(unit.workflow_stages),
            "fields": _json(unit.field_elements),
            "inputs": _json(unit.required_inputs),
            "evidence_requirements": _json(unit.evidence_requirements),
            "variants": _json(unit.allowed_variants),
            "failures": _json(unit.failure_patterns),
            "checklist": _json(unit.checklist_items),
            "dependencies": _json(unit.dependency_refs),
            "normative": _json(unit.normative_references),
            "uncertainties": _json(unit.uncertainties),
            "profile": unit.construction_profile_version,
            "digest": unit.integrity_digest,
            "at": constructed_at,
        },
    )
    for evidence in unit.evidence:
        locator_key = evidence.locator.key
        locator_id = session.execute(
            sa.text(
                "SELECT source_locator_id FROM platform.source_locators "
                "WHERE source_version_id=:source AND locator_key=:key"
            ),
            {"source": evidence.source_version_id, "key": locator_key},
        ).scalar_one()
        session.execute(
            sa.text(
                "INSERT INTO platform.practice_intelligence_sources "
                "(intelligence_source_id,intelligence_unit_id,intelligence_unit_version,"
                "guidance_unit_id,guidance_unit_version,source_version_id,source_locator_id,"
                "page_number,region,fragment_digest,evidence_role,recorded_at) VALUES "
                "(:id,:unit,:unit_version,:guidance,:guidance_version,:source,:locator,"
                ":page,:region,:digest,'primary',:at)"
            ),
            {
                "id": deterministic_uuid(
                    f"kg-id-intelligence-source:{unit.intelligence_unit_id}:{unit.version}:"
                    f"{evidence.guidance_unit_id}:{evidence.guidance_unit_version}:{locator_key}"
                ),
                "unit": unit.intelligence_unit_id,
                "unit_version": unit.version,
                "guidance": evidence.guidance_unit_id,
                "guidance_version": evidence.guidance_unit_version,
                "source": evidence.source_version_id,
                "locator": locator_id,
                "page": evidence.locator.page_number,
                "region": list(evidence.locator.region),
                "digest": evidence.fragment_digest,
                "at": constructed_at,
            },
        )


def _insert_playbook(
    session: Session,
    construction_manifest_id: UUID,
    constructed_at: datetime,
    playbook: PracticePlaybook,
) -> None:
    session.execute(
        sa.text(
            "INSERT INTO platform.practice_playbooks "
            "(playbook_id,version,construction_manifest_id,practice_guide_edition_id,"
            "coverage_manifest_id,title,purpose,applicability_conditions,work_types,"
            "document_types,form_types,workflow_stages,uncertainties,construction_profile_version,"
            "authority_layer,integrity_digest,constructed_at) VALUES "
            "(:id,:version,:manifest,:edition,:coverage,:title,:purpose,"
            "CAST(:applicability AS jsonb),"
            "CAST(:work AS jsonb),CAST(:documents AS jsonb),CAST(:forms AS jsonb),"
            "CAST(:workflow AS jsonb),CAST(:uncertainties AS jsonb),:profile,"
            "'methodological_practice',:digest,:at)"
        ),
        {
            "id": playbook.playbook_id,
            "version": playbook.version,
            "manifest": construction_manifest_id,
            "edition": playbook.practice_guide_edition_id,
            "coverage": playbook.coverage_manifest_id,
            "title": playbook.title,
            "purpose": playbook.purpose,
            "applicability": _json(playbook.applicability_conditions),
            "work": _json(playbook.work_types),
            "documents": _json(playbook.document_types),
            "forms": _json(playbook.form_types),
            "workflow": _json(playbook.workflow_stages),
            "uncertainties": _json(playbook.uncertainties),
            "profile": playbook.construction_profile_version,
            "digest": playbook.integrity_digest,
            "at": constructed_at,
        },
    )
    for sequence, (unit_id, unit_version, role) in enumerate(playbook.member_refs, 1):
        session.execute(
            sa.text(
                "INSERT INTO platform.practice_playbook_members "
                "(playbook_id,playbook_version,member_sequence,intelligence_unit_id,"
                "intelligence_unit_version,member_role) VALUES "
                "(:playbook,:version,:sequence,:unit,:unit_version,:role)"
            ),
            {
                "playbook": playbook.playbook_id,
                "version": playbook.version,
                "sequence": sequence,
                "unit": unit_id,
                "unit_version": unit_version,
                "role": role,
            },
        )


def _searchable_unit(unit: IDPracticeIntelligenceUnit) -> str:
    return " ".join(
        value
        for value in (
            unit.kind.value,
            unit.title,
            unit.instruction,
            unit.rationale or "",
            *unit.applicability_conditions,
            *unit.work_types,
            *unit.document_types,
            *unit.form_types,
            *unit.workflow_stages,
            *unit.field_elements,
            *unit.required_inputs,
            *unit.evidence_requirements,
            *unit.allowed_variants,
            *unit.failure_patterns,
            *unit.checklist_items,
            *unit.dependency_refs,
        )
        if value
    )


def _rebuild_lexical_entries(
    session: Session,
    *,
    lexical_version_id: UUID,
    units: tuple[IDPracticeIntelligenceUnit, ...],
    playbooks: tuple[PracticePlaybook, ...],
) -> None:
    session.execute(
        sa.text(
            "DELETE FROM projection.practice_intelligence_lexical_entries "
            "WHERE lexical_version_id=:id"
        ),
        {"id": lexical_version_id},
    )
    for unit in units:
        searchable = _searchable_unit(unit)
        session.execute(
            sa.text(
                "INSERT INTO projection.practice_intelligence_lexical_entries "
                "(lexical_version_id,entity_kind,entity_id,entity_version,intelligence_kind,"
                "searchable_text,entry_digest) VALUES "
                "(:lexical,'intelligence_unit',:id,:version,:kind,:text,:digest)"
            ),
            {
                "lexical": lexical_version_id,
                "id": unit.intelligence_unit_id,
                "version": unit.version,
                "kind": unit.kind.value,
                "text": searchable,
                "digest": digest_of(
                    {
                        "lexical_version_id": str(lexical_version_id),
                        "entity": str(unit.intelligence_unit_id),
                        "version": unit.version,
                        "searchable_text": searchable,
                    }
                ),
            },
        )
    units_by_id = {unit.intelligence_unit_id: unit for unit in units}
    for playbook in playbooks:
        member_text = " ".join(
            _searchable_unit(units_by_id[unit_id])
            for unit_id, _version, _role in playbook.member_refs
        )
        searchable = " ".join(
            (
                playbook.title,
                playbook.purpose,
                *playbook.applicability_conditions,
                *playbook.document_types,
                *playbook.form_types,
                *playbook.workflow_stages,
                member_text,
            )
        )
        session.execute(
            sa.text(
                "INSERT INTO projection.practice_intelligence_lexical_entries "
                "(lexical_version_id,entity_kind,entity_id,entity_version,intelligence_kind,"
                "searchable_text,entry_digest) VALUES "
                "(:lexical,'practice_playbook',:id,:version,NULL,:text,:digest)"
            ),
            {
                "lexical": lexical_version_id,
                "id": playbook.playbook_id,
                "version": playbook.version,
                "text": searchable,
                "digest": digest_of(
                    {
                        "lexical_version_id": str(lexical_version_id),
                        "entity": str(playbook.playbook_id),
                        "version": playbook.version,
                        "searchable_text": searchable,
                    }
                ),
            },
        )
    session.execute(
        sa.text(
            "UPDATE projection.practice_intelligence_lexical_versions SET "
            "state='ready',entry_count=:count,built_at=:at WHERE lexical_version_id=:id"
        ),
        {
            "count": len(units) + len(playbooks),
            "at": datetime.now(UTC),
            "id": lexical_version_id,
        },
    )


def persist_manifest(engine: Engine, document: Mapping[str, Any]) -> dict[str, Any]:
    manifest_id, coverage_id, constructed_at, units, playbooks = _manifest_values(document)
    fingerprint = str(document["construction_fingerprint"])
    lexical_version_id = deterministic_uuid(
        f"kg-id-intelligence-lexical:{manifest_id}:{INTELLIGENCE_PROJECTION_VERSION}"
    )
    if not units:
        raise ValueError("Practice-intelligence release cannot be empty")
    edition_id = units[0].practice_guide_edition_id
    if any(unit.practice_guide_edition_id != edition_id for unit in units) or any(
        playbook.practice_guide_edition_id != edition_id for playbook in playbooks
    ):
        raise ValueError("Practice-intelligence release cannot mix guide editions")
    policy = default_context_assembly_policy(edition_id)
    semantic_fingerprint = canonical_semantic_fingerprint(
        source_version_id=units[0].evidence[0].source_version_id,
        construction_fingerprint=fingerprint,
        coverage_manifest_fingerprint=str(document["coverage_manifest_fingerprint"]),
        intelligence_unit_digests=(unit.integrity_digest for unit in units),
        playbook_digests=(playbook.integrity_digest for playbook in playbooks),
        context_assembly_policy_fingerprint=policy.fingerprint,
    )
    with Session(engine) as session, session.begin():
        activation = _require_or_create_initial_activation(
            session, edition_id=edition_id, recorded_at=constructed_at
        )
        release_id = deterministic_uuid(
            f"id-practice-release:{edition_id}:{manifest_id}:"
            f"{activation.activation_decision_id}:{activation.version}:{policy.policy_id}:"
            f"{policy.version}:{semantic_fingerprint}"
        )
        existing = session.execute(
            sa.text(
                "SELECT construction_fingerprint FROM "
                "platform.practice_intelligence_construction_manifests "
                "WHERE construction_manifest_id=:id"
            ),
            {"id": manifest_id},
        ).scalar_one_or_none()
        if existing is not None:
            if str(existing) != fingerprint:
                raise ValueError("ConstructionManifest identity conflicts with persisted content")
            counts = session.execute(
                sa.text(
                    "SELECT (SELECT count(*) FROM platform.practice_intelligence_units "
                    "WHERE construction_manifest_id=:id),"
                    "(SELECT count(*) FROM platform.practice_playbooks "
                    "WHERE construction_manifest_id=:id)"
                ),
                {"id": manifest_id},
            ).one()
            if (int(counts[0]), int(counts[1])) != (len(units), len(playbooks)):
                raise ValueError("Persisted intelligence construction is incomplete")
        else:
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_intelligence_construction_manifests "
                    "(construction_manifest_id,coverage_manifest_id,construction_profile_version,"
                    "source_guidance_count,intelligence_unit_count,playbook_count,"
                    "construction_fingerprint,authority_layer,product_ready,constructed_at) VALUES "
                    "(:id,:coverage,:profile,:sources,:units,:playbooks,:fingerprint,"
                    "'methodological_practice',false,:at)"
                ),
                {
                    "id": manifest_id,
                    "coverage": coverage_id,
                    "profile": str(document["construction_profile_version"]),
                    "sources": int(document["source_guidance_count"]),
                    "units": len(units),
                    "playbooks": len(playbooks),
                    "fingerprint": fingerprint,
                    "at": constructed_at,
                },
            )
            for unit in units:
                _insert_unit(session, manifest_id, constructed_at, unit)
            for playbook in playbooks:
                _insert_playbook(session, manifest_id, constructed_at, playbook)
        projection = session.execute(
            sa.text(
                "SELECT source_fingerprint FROM projection.practice_intelligence_lexical_versions "
                "WHERE lexical_version_id=:id"
            ),
            {"id": lexical_version_id},
        ).scalar_one_or_none()
        if projection is None:
            session.execute(
                sa.text(
                    "INSERT INTO projection.practice_intelligence_lexical_versions "
                    "(lexical_version_id,construction_manifest_id,projection_contract_version,"
                    "source_fingerprint,state,entry_count,built_at) VALUES "
                    "(:id,:manifest,:version,:fingerprint,'building',0,NULL)"
                ),
                {
                    "id": lexical_version_id,
                    "manifest": manifest_id,
                    "version": INTELLIGENCE_PROJECTION_VERSION,
                    "fingerprint": fingerprint,
                },
            )
            _rebuild_lexical_entries(
                session,
                lexical_version_id=lexical_version_id,
                units=units,
                playbooks=playbooks,
            )
        elif str(projection) != fingerprint:
            raise ValueError("Practice-intelligence lexical identity conflict")
        else:
            entry_count = session.execute(
                sa.text(
                    "SELECT count(*) FROM projection.practice_intelligence_lexical_entries "
                    "WHERE lexical_version_id=:id"
                ),
                {"id": lexical_version_id},
            ).scalar_one()
            if int(entry_count) != len(units) + len(playbooks):
                _rebuild_lexical_entries(
                    session,
                    lexical_version_id=lexical_version_id,
                    units=units,
                    playbooks=playbooks,
                )
        source_version_id = session.execute(
            sa.text(
                "SELECT source_version_id FROM platform.practice_guide_editions "
                "WHERE practice_guide_edition_id=:edition"
            ),
            {"edition": edition_id},
        ).scalar_one()
        publication_status = session.execute(
            sa.text(
                "SELECT publication_status FROM platform.practice_guidance_coverage_manifests "
                "WHERE coverage_manifest_id=:coverage"
            ),
            {"coverage": coverage_id},
        ).scalar_one()
        existing_policy = session.execute(
            sa.text(
                "SELECT policy_fingerprint FROM platform.context_assembly_policies "
                "WHERE policy_id=:id AND version=:version"
            ),
            {"id": policy.policy_id, "version": policy.version},
        ).scalar_one_or_none()
        if existing_policy is None:
            session.execute(
                sa.text(
                    "INSERT INTO platform.context_assembly_policies "
                    "(policy_id,version,policy_key,practice_guide_edition_id,allowed_modes,"
                    "allowed_purposes,selector_dimensions,max_intelligence_units,max_playbooks,"
                    "authority_layer,retention_class,state,policy_fingerprint,owner_decision_ref,"
                    "recorded_at) VALUES (:id,:version,:key,:edition,CAST(:modes AS jsonb),"
                    "CAST(:purposes AS jsonb),CAST(:dimensions AS jsonb),:units,:playbooks,"
                    "'methodological_practice','permanent_platform_core','active',:fingerprint,"
                    "'ADR-0011;owner:Oleg Shcherbakov;2026-08-25',:at)"
                ),
                {
                    "id": policy.policy_id,
                    "version": policy.version,
                    "key": policy.policy_key,
                    "edition": policy.practice_guide_edition_id,
                    "modes": _json(policy.allowed_modes),
                    "purposes": _json(policy.allowed_purposes),
                    "dimensions": _json(policy.selector_dimensions),
                    "units": policy.max_intelligence_units,
                    "playbooks": policy.max_playbooks,
                    "fingerprint": policy.fingerprint,
                    "at": constructed_at,
                },
            )
        elif str(existing_policy) != policy.fingerprint:
            raise ValueError("ContextAssemblyPolicy identity conflicts with persisted content")
        existing_release = session.execute(
            sa.text(
                "SELECT canonical_semantic_fingerprint FROM "
                "platform.practice_intelligence_releases WHERE release_id=:id AND version=1"
            ),
            {"id": release_id},
        ).scalar_one_or_none()
        if existing_release is None:
            session.execute(
                sa.text(
                    "INSERT INTO platform.practice_intelligence_releases "
                    "(release_id,version,construction_manifest_id,practice_guide_edition_id,"
                    "source_version_id,activation_decision_id,activation_decision_version,"
                    "context_assembly_policy_id,context_assembly_policy_version,"
                    "authority_layer,retention_class,canonical_semantic_fingerprint,"
                    "publication_status,product_ready,owner_decision_ref,published_at) VALUES "
                    "(:id,1,:manifest,:edition,:source,:activation,:activation_version,"
                    ":policy,:policy_version,"
                    "'methodological_practice','permanent_platform_core',:semantic,:status,false,"
                    "'ADR-0011;owner:Oleg Shcherbakov;2026-08-25',:at)"
                ),
                {
                    "id": release_id,
                    "manifest": manifest_id,
                    "edition": edition_id,
                    "source": source_version_id,
                    "activation": activation.activation_decision_id,
                    "activation_version": activation.version,
                    "policy": policy.policy_id,
                    "policy_version": policy.version,
                    "semantic": semantic_fingerprint,
                    "status": publication_status,
                    "at": constructed_at,
                },
            )
        elif str(existing_release) != semantic_fingerprint:
            raise ValueError("PracticeIntelligence release identity conflict")
        projection_values = (
            ("exact", "canonical-exact-v0.1.0", semantic_fingerprint, "ready"),
            (
                "fts",
                INTELLIGENCE_PROJECTION_VERSION,
                digest_of(
                    {
                        "lexical_version_id": str(lexical_version_id),
                        "entry_count": len(units) + len(playbooks),
                        "source_fingerprint": fingerprint,
                    }
                ),
                "ready",
            ),
            ("vector", "unqualified", None, "absent"),
            ("sparse", "unqualified", None, "absent"),
            ("typed_graph", "unqualified", None, "absent"),
        )
        for kind, version, projection_fingerprint, state in projection_values:
            projection_manifest_id = deterministic_uuid(
                f"id-practice-projection:{release_id}:1:{kind}:{version}"
            )
            session.execute(
                sa.text(
                    "INSERT INTO projection.practice_intelligence_projection_manifests "
                    "(projection_manifest_id,release_id,release_version,projection_kind,"
                    "projection_version,source_semantic_fingerprint,projection_fingerprint,state,"
                    "rebuilt_at) VALUES (:id,:release,1,:kind,:version,:source,:projection,:state,"
                    ":rebuilt) ON CONFLICT (projection_manifest_id) DO NOTHING"
                ),
                {
                    "id": projection_manifest_id,
                    "release": release_id,
                    "kind": kind,
                    "version": version,
                    "source": semantic_fingerprint,
                    "projection": projection_fingerprint,
                    "state": state,
                    "rebuilt": datetime.now(UTC) if state == "ready" else None,
                },
            )
    return {
        "construction_manifest_id": str(manifest_id),
        "construction_fingerprint": fingerprint,
        "source_guidance_count": int(document["source_guidance_count"]),
        "intelligence_unit_count": len(units),
        "playbook_count": len(playbooks),
        "lexical_version_id": str(lexical_version_id),
        "lexical_entry_count": len(units) + len(playbooks),
        "practice_intelligence_release_id": str(release_id),
        "practice_intelligence_release_version": 1,
        "activation_decision_id": str(activation.activation_decision_id),
        "activation_decision_version": activation.version,
        "canonical_semantic_fingerprint": semantic_fingerprint,
        "context_assembly_policy_id": str(policy.policy_id),
        "context_assembly_policy_version": policy.version,
        "context_assembly_policy_fingerprint": policy.fingerprint,
        "authority_layer": "methodological_practice",
        "retention_class": "permanent_platform_core",
        "product_ready": False,
    }


def persist_backup_manifest(
    engine: Engine,
    *,
    release_id: UUID,
    release_version: int,
    manifest: PracticeMemoryBackupManifest,
) -> None:
    with Session(engine) as session, session.begin():
        release = (
            session.execute(
                sa.text(
                    "SELECT r.practice_guide_edition_id,r.source_version_id,"
                    "r.construction_manifest_id,"
                    "r.activation_decision_id,r.activation_decision_version,"
                    "r.context_assembly_policy_id,r.context_assembly_policy_version,"
                    "r.canonical_semantic_fingerprint,c.manifest_fingerprint AS "
                    "coverage_manifest_fingerprint FROM platform.practice_intelligence_releases r "
                    "JOIN platform.practice_intelligence_construction_manifests m ON "
                    "m.construction_manifest_id=r.construction_manifest_id JOIN "
                    "platform.practice_guidance_coverage_manifests c ON "
                    "c.coverage_manifest_id=m.coverage_manifest_id "
                    "WHERE r.release_id=:id AND r.version=:version"
                ),
                {"id": release_id, "version": release_version},
            )
            .mappings()
            .one_or_none()
        )
        if release is None:
            raise ValueError("PracticeIntelligence release does not exist")
        expected = {
            "practice_guide_edition_id": str(manifest.practice_guide_edition_id),
            "source_version_id": str(manifest.source_version_id),
            "construction_manifest_id": str(manifest.construction_manifest_id),
            "activation_decision_id": str(manifest.activation_decision_id),
            "activation_decision_version": manifest.activation_decision_version,
            "coverage_manifest_fingerprint": manifest.coverage_manifest_fingerprint,
            "context_assembly_policy_id": str(manifest.context_assembly_policy_id),
            "context_assembly_policy_version": manifest.context_assembly_policy_version,
            "canonical_semantic_fingerprint": manifest.canonical_semantic_fingerprint,
        }
        actual = {
            key: int(value)
            if key in {"activation_decision_version", "context_assembly_policy_version"}
            else str(value)
            for key, value in release.items()
        }
        if actual != expected:
            raise ValueError("Practice-memory backup does not pin the exact release")
        persisted_source_digest = session.execute(
            sa.text(
                "SELECT content_digest FROM platform.source_versions WHERE source_version_id=:id"
            ),
            {"id": manifest.source_version_id},
        ).scalar_one()
        if str(persisted_source_digest) != manifest.source_object_digest:
            raise ValueError("Practice-memory backup source digest diverges from SourceVersion")
        existing = session.execute(
            sa.text(
                "SELECT canonical_semantic_fingerprint FROM "
                "platform.practice_memory_backup_manifests WHERE backup_manifest_id=:id "
                "AND version=:version"
            ),
            {"id": manifest.backup_manifest_id, "version": manifest.version},
        ).scalar_one_or_none()
        if existing is not None:
            if str(existing) != manifest.canonical_semantic_fingerprint:
                raise ValueError("Practice-memory backup manifest identity conflict")
            return
        session.execute(
            sa.text(
                "INSERT INTO platform.practice_memory_backup_manifests "
                "(backup_manifest_id,version,release_id,release_version,"
                "practice_guide_edition_id,source_version_id,source_object_digest,"
                "construction_manifest_id,construction_fingerprint,"
                "coverage_manifest_fingerprint,"
                "activation_decision_id,activation_decision_version,"
                "context_assembly_policy_id,context_assembly_policy_version,"
                "context_assembly_policy_fingerprint,canonical_semantic_fingerprint,"
                "projection_fingerprints,backup_object_reference,retention_class,"
                "integrity_status,recorded_at) VALUES "
                "(:id,:version,:release,:release_version,:edition,:source,:source_digest,"
                ":construction,:construction_fingerprint,:coverage_fingerprint,"
                ":activation,:activation_version,"
                ":policy,:policy_version,"
                ":policy_fingerprint,:semantic,CAST(:projections AS jsonb),:object_ref,"
                "'permanent_platform_core','verified',:at)"
            ),
            {
                "id": manifest.backup_manifest_id,
                "version": manifest.version,
                "release": release_id,
                "release_version": release_version,
                "edition": manifest.practice_guide_edition_id,
                "source": manifest.source_version_id,
                "source_digest": manifest.source_object_digest,
                "construction": manifest.construction_manifest_id,
                "construction_fingerprint": manifest.construction_fingerprint,
                "coverage_fingerprint": manifest.coverage_manifest_fingerprint,
                "activation": manifest.activation_decision_id,
                "activation_version": manifest.activation_decision_version,
                "policy": manifest.context_assembly_policy_id,
                "policy_version": manifest.context_assembly_policy_version,
                "policy_fingerprint": manifest.context_assembly_policy_fingerprint,
                "semantic": manifest.canonical_semantic_fingerprint,
                "projections": _json(manifest.projection_fingerprints),
                "object_ref": manifest.backup_object_reference,
                "at": manifest.recorded_at,
            },
        )
