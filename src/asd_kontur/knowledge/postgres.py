"""Narrow PostgreSQL adapters for canonical knowledge and Gateway queries."""

# ruff: noqa: E501 -- SQL fragments retain readable clause boundaries.

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7

from .errors import KnowledgeError, KnowledgeErrorCode
from .gateway import (
    GUIDANCE_CONTRACT_VERSION,
    GUIDANCE_TOOLS,
    SUPPORTED_CONTRACT_VERSION,
    EvidenceItem,
    EvidencePack,
    GatewayContext,
    GatewayResponse,
    GatewayStatus,
)
from .rules import AuthorityIdentity, RuleLifecycle, RuleState, RuleVersionDefinition


class NormativeKnowledgeRepository:
    """Curator-facing canonical NTD writes and exact edition resolution."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def resolve_document_exact_designation(self, printed_identifier: str) -> UUID:
        """Resolve only an exact canonical designation; never infer or normalize."""

        with Session(self._engine) as session:
            rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT normative_document_id FROM platform.normative_documents "
                        "WHERE designation=:designation"
                    ),
                    {"designation": printed_identifier},
                ).scalars()
            )
        if len(rows) != 1:
            raise KnowledgeError(
                KnowledgeErrorCode.EDITION_AMBIGUOUS,
                "Exact printed NTD designation is absent or ambiguous.",
                {"candidate_count": len(rows)},
            )
        return UUID(str(rows[0]))

    def resolve_edition(self, normative_document_id: UUID, on_date: date) -> UUID:
        with Session(self._engine) as session:
            rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT e.normative_edition_id FROM platform.normative_editions e "
                        "JOIN LATERAL (SELECT status FROM platform.normative_edition_states s "
                        "WHERE s.normative_edition_id=e.normative_edition_id "
                        "ORDER BY s.recorded_at DESC LIMIT 1) current ON true "
                        "WHERE e.normative_document_id=:document "
                        "AND (e.effective_from IS NULL OR e.effective_from<=:on_date) "
                        "AND (e.effective_to IS NULL OR e.effective_to>:on_date) "
                        "AND current.status='active'"
                    ),
                    {"document": normative_document_id, "on_date": on_date},
                ).scalars()
            )
        if len(rows) != 1:
            raise KnowledgeError(
                KnowledgeErrorCode.EDITION_AMBIGUOUS,
                "Edition resolution is absent or ambiguous; a negative normative conclusion is forbidden.",
                {"candidate_count": len(rows)},
            )
        return UUID(str(rows[0]))

    def create_assertion(
        self,
        *,
        assertion_id: UUID,
        assertion_kind: str,
        proposition: str,
        structural_unit_id: UUID,
        source_version_id: UUID,
        source_locator_id: UUID,
        applicability_context_id: UUID,
        actor_identity_id: str,
        correlation_id: UUID,
    ) -> None:
        del correlation_id
        digest = f"sha256:{hashlib.sha256(proposition.encode()).hexdigest()}"
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO platform.knowledge_assertions "
                    "(knowledge_assertion_id,assertion_version,assertion_type,normalized_proposition,"
                    "structural_unit_id,applicability_context_id,status,reviewer_identity_id,"
                    "approval_decision_ref,integrity_digest,published_at) "
                    "VALUES (:id,1,:kind,:proposition,:unit,:applicability,'published',:actor,"
                    "'decision:synthetic-reviewed',:digest,CURRENT_TIMESTAMP)"
                ),
                {
                    "id": assertion_id,
                    "kind": assertion_kind,
                    "proposition": proposition,
                    "digest": digest,
                    "unit": structural_unit_id,
                    "applicability": applicability_context_id,
                    "actor": actor_identity_id,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO platform.assertion_evidence "
                    "(assertion_evidence_id,knowledge_assertion_id,assertion_version,source_version_id,"
                    "structural_unit_id,source_locator_id,evidence_role,fragment_digest,"
                    "verified_by_identity_id,verified_at) "
                    "VALUES (:id,:assertion,1,:source,:unit,:locator,'primary',:digest,:actor,CURRENT_TIMESTAMP)"
                ),
                {
                    "id": uuid7(),
                    "assertion": assertion_id,
                    "source": source_version_id,
                    "unit": structural_unit_id,
                    "locator": source_locator_id,
                    "digest": digest,
                    "actor": actor_identity_id,
                },
            )


class RuleRegistryService:
    """Curator-only version registry with explicit authority transitions."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def register_version(
        self,
        *,
        definition: RuleVersionDefinition,
        rule_class: str,
        purpose: str,
        applicability_context_id: UUID,
        author: AuthorityIdentity,
        test_manifest_digest: str,
    ) -> UUID:
        rule_id = uuid7()
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text("SELECT rule_id FROM platform.rules WHERE rule_key=:key"),
                {"key": definition.rule_key},
            ).scalar_one_or_none()
            if existing is None:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.rules "
                        "(rule_id,rule_key,rule_class,purpose,created_by_identity_id) "
                        "VALUES (:id,:key,:class,:purpose,:actor)"
                    ),
                    {
                        "id": rule_id,
                        "key": definition.rule_key,
                        "class": rule_class,
                        "purpose": purpose,
                        "actor": author.identity_id,
                    },
                )
            else:
                rule_id = UUID(str(existing))
            session.execute(
                sa.text(
                    "INSERT INTO platform.rule_versions "
                    "(rule_version_id,rule_id,version,predicate_contract,input_contract,output_contract,"
                    "applicability_context_id,conflict_policy_version_id,effective_from,effective_to,"
                    "uncertainty_behavior,failure_behavior,implementation_binding,test_manifest_digest,"
                    "integrity_digest,author_identity_id) VALUES "
                    "(:id,:rule,:version,CAST(:predicate AS jsonb),'{}'::jsonb,CAST(:output AS jsonb),"
                    ":applicability,:policy,:effective_from,:effective_to,'indeterminate','fail_closed',"
                    "'declarative-runtime:v0.1',:tests,:integrity,:author)"
                ),
                {
                    "id": UUID(definition.rule_version_id),
                    "rule": rule_id,
                    "version": definition.rule_version_id,
                    "predicate": json.dumps(definition.predicate, sort_keys=True),
                    "output": json.dumps(definition.output, sort_keys=True),
                    "applicability": applicability_context_id,
                    "policy": UUID(definition.conflict_policy_version),
                    "effective_from": definition.effective_from,
                    "effective_to": definition.effective_to,
                    "tests": test_manifest_digest,
                    "integrity": definition.fingerprint(),
                    "author": author.identity_id,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO platform.rule_version_states "
                    "(rule_version_state_id,rule_version_id,state_sequence,status,authority_identity_id,"
                    "decision_ref,effective_at) VALUES (:id,:version,1,'drafted',:actor,"
                    "'decision:authored',CURRENT_TIMESTAMP)"
                ),
                {
                    "id": uuid7(),
                    "version": UUID(definition.rule_version_id),
                    "actor": author.identity_id,
                },
            )
        return rule_id

    def transition(
        self,
        *,
        rule_version_id: UUID,
        target: RuleState,
        actor: AuthorityIdentity,
        decision_ref: str,
        qualification_ref: str = "qualification:not-applicable",
        test_manifest_digest: str = "sha256:" + "0" * 64,
    ) -> RuleState:
        with Session(self._engine) as session, session.begin():
            row = (
                session.execute(
                    sa.text(
                        "SELECT rv.author_identity_id,s.status,s.state_sequence FROM platform.rule_versions rv "
                        "JOIN LATERAL (SELECT status,state_sequence FROM platform.rule_version_states "
                        "WHERE rule_version_id=rv.rule_version_id ORDER BY state_sequence DESC LIMIT 1) s ON true "
                        "WHERE rv.rule_version_id=:id"
                    ),
                    {"id": rule_version_id},
                )
                .mappings()
                .one()
            )
            reviewer_id = session.execute(
                sa.text(
                    "SELECT reviewer_identity_id FROM platform.rule_reviews "
                    "WHERE rule_version_id=:id AND outcome='passed' ORDER BY reviewed_at DESC LIMIT 1"
                ),
                {"id": rule_version_id},
            ).scalar_one_or_none()
            current = RuleState(str(row["status"]))
            RuleLifecycle.transition(
                current,
                target,
                actor=actor,
                author_identity_id=str(row["author_identity_id"]),
                reviewer_identity_id=str(reviewer_id) if reviewer_id else None,
            )
            if target is RuleState.EVIDENCE_ATTACHED:
                count = session.scalar(
                    sa.text(
                        "SELECT count(*) FROM platform.rule_evidence WHERE rule_version_id=:id"
                    ),
                    {"id": rule_version_id},
                )
                if count == 0:
                    raise KnowledgeError(
                        KnowledgeErrorCode.EVIDENCE_MISSING,
                        "RuleVersion cannot enter evidence_attached without exact RuleEvidence.",
                    )
            if target is RuleState.REVIEWED:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.rule_reviews "
                        "(rule_review_id,rule_version_id,reviewer_identity_id,reviewer_qualification_ref,"
                        "test_manifest_digest,outcome,reviewed_at) "
                        "VALUES (:id,:version,:reviewer,:qualification,:tests,'passed',CURRENT_TIMESTAMP)"
                    ),
                    {
                        "id": uuid7(),
                        "version": rule_version_id,
                        "reviewer": actor.identity_id,
                        "qualification": qualification_ref,
                        "tests": test_manifest_digest,
                    },
                )
            if target is RuleState.APPROVED:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.rule_approvals "
                        "(rule_approval_id,rule_version_id,reviewer_identity_id,approver_identity_id,"
                        "approver_qualification_ref,authority_reference,outcome,approved_at) "
                        "VALUES (:id,:version,:reviewer,:approver,:qualification,:authority,'approved',CURRENT_TIMESTAMP)"
                    ),
                    {
                        "id": uuid7(),
                        "version": rule_version_id,
                        "reviewer": reviewer_id,
                        "approver": actor.identity_id,
                        "qualification": qualification_ref,
                        "authority": decision_ref,
                    },
                )
            session.execute(
                sa.text(
                    "INSERT INTO platform.rule_version_states "
                    "(rule_version_state_id,rule_version_id,state_sequence,status,authority_identity_id,"
                    "decision_ref,effective_at) VALUES (:id,:version,:sequence,:status,:actor,:decision,CURRENT_TIMESTAMP)"
                ),
                {
                    "id": uuid7(),
                    "version": rule_version_id,
                    "sequence": int(row["state_sequence"]) + 1,
                    "status": target,
                    "actor": actor.identity_id,
                    "decision": decision_ref,
                },
            )
        return target

    def publish_rule_set(
        self,
        *,
        rule_set_version_id: UUID,
        rule_set_key: str,
        version: str,
        members: tuple[tuple[UUID, str], ...],
        approver: AuthorityIdentity,
    ) -> str:
        if (
            version == "latest"
            or not approver.is_human
            or "rule.approve" not in approver.qualifications
        ):
            raise KnowledgeError(
                KnowledgeErrorCode.AUTHORITY_DENIED,
                "An exact RuleSetVersion requires a qualified human approver.",
            )
        manifest = sorted((str(rule_id), digest) for rule_id, digest in members)
        manifest_digest = f"sha256:{hashlib.sha256(json.dumps(manifest, separators=(',', ':')).encode()).hexdigest()}"
        with Session(self._engine) as session, session.begin():
            for rule_version_id, _digest_value in members:
                status = session.execute(
                    sa.text(
                        "SELECT status FROM platform.rule_version_states WHERE rule_version_id=:id "
                        "ORDER BY state_sequence DESC LIMIT 1"
                    ),
                    {"id": rule_version_id},
                ).scalar_one_or_none()
                if status != RuleState.ACTIVE:
                    raise KnowledgeError(
                        KnowledgeErrorCode.RULE_NOT_ACTIVE,
                        "A RuleSetVersion may contain only active RuleVersion members.",
                    )
            session.execute(
                sa.text(
                    "INSERT INTO platform.rule_set_versions "
                    "(rule_set_version_id,rule_set_key,version,status,manifest_digest,schema_version,"
                    "compatibility_contract,approval_decision_ref,approved_by_identity_id) VALUES "
                    "(:id,:key,:version,'active',:digest,'0.1.0','{}'::jsonb,"
                    "'decision:synthetic-rule-set',:approver)"
                ),
                {
                    "id": rule_set_version_id,
                    "key": rule_set_key,
                    "version": version,
                    "digest": manifest_digest,
                    "approver": approver.identity_id,
                },
            )
            for ordinal, (rule_version_id, rule_digest) in enumerate(members):
                session.execute(
                    sa.text(
                        "INSERT INTO platform.rule_set_memberships "
                        "(rule_set_version_id,rule_version_id,membership_role,ordinal,rule_integrity_digest) "
                        "VALUES (:set,:rule,'deterministic',:ordinal,:digest)"
                    ),
                    {
                        "set": rule_set_version_id,
                        "rule": rule_version_id,
                        "ordinal": ordinal,
                        "digest": rule_digest,
                    },
                )
        return manifest_digest


class PostgresKnowledgeQuery:
    """Six allowlisted query implementations; callers cannot submit SQL."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def execute(
        self, tool: str, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        dispatch = {
            "knowledge.search": self._search,
            "knowledge.get_source_fragment": self._source_fragment,
            "knowledge.get_applicable_rules": self._applicable_rules,
            "knowledge.trace_assertion": self._trace_assertion,
            "knowledge.explain_conflict": self._explain_conflict,
            "knowledge.get_required_documents": self._required_documents,
            "knowledge.get_id_guidance": self._id_guidance,
            "knowledge.get_form_guidance": self._form_guidance,
            "knowledge.get_field_guidance": self._field_guidance,
            "knowledge.trace_guidance": self._trace_guidance,
            "knowledge.explain_guidance_conflict": self._explain_guidance_conflict,
        }
        return dispatch[tool](payload, context)

    def _id_guidance(self, payload: dict[str, Any], _context: GatewayContext) -> GatewayResponse:
        query = str(payload.get("query", "")).strip()
        lexical_version_id = payload.get("lexical_version_id")
        if not query or lexical_version_id is None:
            return self._guidance_gap(
                "knowledge.get_id_guidance",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "guidance_query_or_index_missing",
            )
        with Session(self._engine) as session:
            state = session.execute(
                sa.text(
                    "SELECT state FROM projection.practice_guidance_lexical_versions "
                    "WHERE lexical_version_id=:id"
                ),
                {"id": lexical_version_id},
            ).scalar_one_or_none()
            rows = (
                tuple(
                    session.execute(
                        sa.text(
                            "SELECT u.guidance_unit_id,u.version,u.guidance_kind,u.normalized_instruction,"
                            "u.section,u.topic,u.document_or_form_type,u.workflow_stage,u.field_or_element,"
                            "u.applicability_conditions,u.limitations "
                            "FROM projection.practice_guidance_lexical_entries e "
                            "JOIN platform.practice_guidance_units u ON u.guidance_unit_id=e.guidance_unit_id "
                            "AND u.version=e.guidance_unit_version WHERE e.lexical_version_id=:index "
                            "AND e.search_vector @@ plainto_tsquery('russian',:query) "
                            "AND NOT EXISTS (SELECT 1 FROM platform.practice_guidance_conflicts c "
                            "WHERE c.guidance_unit_id=u.guidance_unit_id "
                            "AND c.guidance_unit_version=u.version AND c.state='open') "
                            "ORDER BY u.guidance_unit_id,u.version LIMIT 100"
                        ),
                        {"index": lexical_version_id, "query": query},
                    ).mappings()
                )
                if state == "ready"
                else ()
            )
        if state != "ready":
            return self._guidance_gap(
                "knowledge.get_id_guidance",
                GatewayStatus.INDEX_UNAVAILABLE,
                "guidance_lexical_index_not_ready",
            )
        if not rows:
            return self._guidance_gap(
                "knowledge.get_id_guidance",
                GatewayStatus.NO_RESULT,
                "guidance_not_found",
                payload,
            )
        identities = tuple(
            (UUID(str(row["guidance_unit_id"])), int(row["version"])) for row in rows
        )
        coverage, relevant_gaps = self._guidance_coverage(payload)
        pack = self._guidance_evidence(identities)
        return GatewayResponse(
            "knowledge.get_id_guidance",
            GUIDANCE_CONTRACT_VERSION,
            GatewayStatus.KNOWLEDGE_INCOMPLETE if relevant_gaps else GatewayStatus.OK,
            {
                "guidance": [dict(row) for row in rows],
                "retrieval": "exact_fts",
                **coverage,
            },
            EvidencePack(
                pack.evidence,
                pack.applicability,
                pack.conflicts,
                (*pack.gaps, *relevant_gaps),
                pack.uncertainties,
            ),
        )

    def _form_guidance(self, payload: dict[str, Any], _context: GatewayContext) -> GatewayResponse:
        form_type = str(payload.get("document_or_form_type", "")).strip()
        if not form_type:
            return self._guidance_gap(
                "knowledge.get_form_guidance",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "form_type_missing",
            )
        rows = self._guidance_rows("u.document_or_form_type=:form", {"form": form_type})
        return self._guidance_rows_response("knowledge.get_form_guidance", rows, payload)

    def _field_guidance(self, payload: dict[str, Any], _context: GatewayContext) -> GatewayResponse:
        form_type = str(payload.get("document_or_form_type", "")).strip()
        field = str(payload.get("field_or_element", "")).strip()
        if not form_type or not field:
            return self._guidance_gap(
                "knowledge.get_field_guidance",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "form_or_field_missing",
            )
        rows = self._guidance_rows(
            "u.document_or_form_type=:form AND u.field_or_element=:field",
            {"form": form_type, "field": field},
        )
        return self._guidance_rows_response("knowledge.get_field_guidance", rows, payload)

    def _trace_guidance(self, payload: dict[str, Any], _context: GatewayContext) -> GatewayResponse:
        guidance_id = payload.get("guidance_unit_id")
        version = payload.get("version")
        if guidance_id is None or not isinstance(version, int):
            return self._guidance_gap(
                "knowledge.trace_guidance",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "guidance_identity_or_version_missing",
            )
        rows = self._guidance_rows(
            "u.guidance_unit_id=:id AND u.version=:version",
            {"id": guidance_id, "version": version},
        )
        return self._guidance_rows_response("knowledge.trace_guidance", rows, payload)

    def _explain_guidance_conflict(
        self, payload: dict[str, Any], _context: GatewayContext
    ) -> GatewayResponse:
        conflict_id = payload.get("guidance_conflict_id")
        with Session(self._engine) as session:
            row = (
                session.execute(
                    sa.text(
                        "SELECT c.guidance_conflict_id,c.guidance_unit_id,"
                        "c.guidance_unit_version,c.guidance_candidate_id,c.candidate_version,"
                        "c.conflicting_authority_layer,c.conflicting_subject_ref,c.conflict_type,"
                        "c.state,c.uncertainty_ref,c.decision_ref,v.source_version_id,v.page_number,"
                        "v.region,sv.content_digest,o.access_capability_ref "
                        "FROM platform.practice_guidance_conflicts c "
                        "JOIN platform.practice_guide_candidate_versions v ON "
                        "v.guidance_candidate_id=c.guidance_candidate_id "
                        "AND v.version=c.candidate_version "
                        "JOIN platform.source_versions sv ON sv.source_version_id=v.source_version_id "
                        "JOIN platform.objects o ON o.object_id=sv.object_id "
                        "WHERE c.guidance_conflict_id=:id"
                    ),
                    {"id": conflict_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return self._guidance_gap(
                "knowledge.explain_guidance_conflict",
                GatewayStatus.NO_RESULT,
                "guidance_conflict_not_found",
            )
        coverage, _ = self._guidance_coverage({})
        if row["guidance_unit_id"] is not None:
            identity = ((UUID(str(row["guidance_unit_id"])), int(row["guidance_unit_version"])),)
            evidence = self._guidance_evidence(identity).evidence
        else:
            region = tuple(float(value) for value in row["region"])
            locator = "page:{}:region:{}".format(
                int(row["page_number"]), ",".join(f"{value:.6f}" for value in region)
            )
            evidence = (
                EvidenceItem(
                    evidence_link_id=str(row["guidance_conflict_id"]),
                    source_version_id=str(row["source_version_id"]),
                    edition_id=None,
                    structural_unit_locator=locator,
                    content_digest=str(row["content_digest"]),
                    access_reference=str(row["access_capability_ref"]),
                    authority_layer="methodological_guidance",
                ),
            )
        return GatewayResponse(
            "knowledge.explain_guidance_conflict",
            GUIDANCE_CONTRACT_VERSION,
            GatewayStatus.OK,
            {"conflict": dict(row), **coverage},
            EvidencePack(
                evidence,
                (),
                (dict(row),),
                (),
                ({"code": str(row["uncertainty_ref"])},),
            ),
        )

    def _guidance_rows(self, where_clause: str, parameters: dict[str, object]) -> tuple[Any, ...]:
        allowed = {
            "u.document_or_form_type=:form",
            "u.document_or_form_type=:form AND u.field_or_element=:field",
            "u.guidance_unit_id=:id AND u.version=:version",
        }
        if where_clause not in allowed:
            raise AssertionError("Guidance query is not allowlisted")
        with Session(self._engine) as session:
            return tuple(
                session.execute(
                    sa.text(
                        "SELECT u.guidance_unit_id,u.version,u.guidance_kind,u.normalized_instruction,"
                        "u.section,u.topic,u.document_or_form_type,u.workflow_stage,u.field_or_element,"
                        "u.required_inputs,u.evidence_requirements,u.author_role_claims,"
                        "u.applicability_conditions,u.limitations,u.authority_layer "
                        "FROM platform.practice_guidance_units u WHERE NOT EXISTS "
                        "(SELECT 1 FROM platform.practice_guidance_conflicts c WHERE "
                        "c.guidance_unit_id=u.guidance_unit_id AND "
                        "c.guidance_unit_version=u.version AND c.state='open') AND "
                        + where_clause
                        + " ORDER BY u.guidance_unit_id,u.version"
                    ),
                    parameters,
                ).mappings()
            )

    def _guidance_rows_response(
        self, tool: str, rows: tuple[Any, ...], payload: dict[str, Any]
    ) -> GatewayResponse:
        if not rows:
            return self._guidance_gap(tool, GatewayStatus.NO_RESULT, "guidance_not_found", payload)
        identities = tuple(
            (UUID(str(row["guidance_unit_id"])), int(row["version"])) for row in rows
        )
        coverage, relevant_gaps = self._guidance_coverage(payload)
        pack = self._guidance_evidence(identities)
        return GatewayResponse(
            tool,
            GUIDANCE_CONTRACT_VERSION,
            GatewayStatus.KNOWLEDGE_INCOMPLETE if relevant_gaps else GatewayStatus.OK,
            {"guidance": [dict(row) for row in rows], **coverage},
            EvidencePack(
                pack.evidence,
                pack.applicability,
                pack.conflicts,
                (*pack.gaps, *relevant_gaps),
                pack.uncertainties,
            ),
        )

    def _guidance_coverage(
        self, payload: dict[str, Any]
    ) -> tuple[dict[str, object], tuple[dict[str, Any], ...]]:
        with Session(self._engine) as session:
            coverage = (
                session.execute(
                    sa.text(
                        "SELECT coverage_manifest_id,coverage_manifest_version,"
                        "publication_status,reconciliation_fingerprint "
                        "FROM platform.practice_guidance_coverage_manifests "
                        "ORDER BY coverage_manifest_version DESC LIMIT 1"
                    )
                )
                .mappings()
                .one_or_none()
            )
            if coverage is None:
                return (
                    {"coverage_manifest_version": None},
                    ({"code": "coverage_manifest_unavailable"},),
                )
            query = str(payload.get("query", "")).strip()
            form_type = str(payload.get("document_or_form_type", "")).strip()
            field = str(payload.get("field_or_element", "")).strip()
            conditions = ["g.coverage_manifest_id=:manifest"]
            parameters: dict[str, object] = {"manifest": coverage["coverage_manifest_id"]}
            relevance: list[str] = []
            if query:
                relevance.append("g.search_vector @@ plainto_tsquery('russian',:query)")
                parameters["query"] = query
            if form_type:
                relevance.append("g.document_or_form_type=:form")
                parameters["form"] = form_type
            if field:
                relevance.append("g.field_or_element=:field")
                parameters["field"] = field
            if relevance:
                conditions.append("(" + " OR ".join(relevance) + ")")
                rows = tuple(
                    session.execute(
                        sa.text(
                            "SELECT guidance_gap_id,page_number,gap_code,terminal_state,"
                            "guidance_candidate_id,candidate_version,content_minimal_parameters "
                            "FROM platform.practice_guidance_gaps g WHERE "
                            + " AND ".join(conditions)
                            + " ORDER BY page_number,guidance_gap_id"
                        ),
                        parameters,
                    ).mappings()
                )
            else:
                rows = ()
        return (
            {
                "coverage_manifest_id": str(coverage["coverage_manifest_id"]),
                "coverage_manifest_version": int(coverage["coverage_manifest_version"]),
                "coverage_status": str(coverage["publication_status"]),
                "reconciliation_fingerprint": str(coverage["reconciliation_fingerprint"]),
            },
            tuple(dict(row) for row in rows),
        )

    def _search(self, payload: dict[str, Any], _context: GatewayContext) -> GatewayResponse:
        query = str(payload.get("query", "")).strip()
        index_id = payload.get("lexical_index_version_id")
        if not query or index_id is None:
            return self._gap(
                "knowledge.search", GatewayStatus.KNOWLEDGE_INCOMPLETE, "missing_query_or_index"
            )
        with Session(self._engine) as session:
            state = session.execute(
                sa.text(
                    "SELECT status FROM projection.lexical_index_versions "
                    "WHERE lexical_index_version_id=:id"
                ),
                {"id": index_id},
            ).scalar_one_or_none()
            if state not in {"ready", "empty"}:
                return self._gap(
                    "knowledge.search", GatewayStatus.INDEX_UNAVAILABLE, "lexical_index_not_ready"
                )
            rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT a.knowledge_assertion_id,a.assertion_type,a.normalized_proposition "
                        "FROM projection.lexical_entries p JOIN platform.knowledge_assertions a "
                        "ON a.structural_unit_id=p.structural_unit_id "
                        "WHERE p.lexical_index_version_id=:id "
                        "AND p.search_vector @@ plainto_tsquery('russian',:query) "
                        "ORDER BY a.knowledge_assertion_id"
                    ),
                    {"id": index_id, "query": query},
                ).mappings()
            )
        if not rows:
            return self._gap("knowledge.search", GatewayStatus.NO_RESULT, "no_matching_assertion")
        return GatewayResponse(
            "knowledge.search",
            SUPPORTED_CONTRACT_VERSION,
            GatewayStatus.OK,
            {"assertions": [dict(row) for row in rows]},
            self._evidence_for(tuple(UUID(str(row["knowledge_assertion_id"])) for row in rows)),
        )

    def _source_fragment(
        self, payload: dict[str, Any], _context: GatewayContext
    ) -> GatewayResponse:
        source_version_id = payload.get("source_version_id")
        locator = payload.get("locator")
        with Session(self._engine) as session:
            row = (
                session.execute(
                    sa.text(
                        "SELECT sv.source_version_id,sv.content_digest,sl.locator_kind,sl.locator_value,"
                        "o.access_capability_ref FROM platform.source_versions sv "
                        "JOIN platform.source_locators sl ON sl.source_version_id=sv.source_version_id "
                        "JOIN platform.objects o ON o.object_id=sv.object_id "
                        "WHERE sv.source_version_id=:version AND sl.locator_key=:locator"
                    ),
                    {"version": source_version_id, "locator": locator},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return self._gap(
                "knowledge.get_source_fragment", GatewayStatus.NO_RESULT, "fragment_not_found"
            )
        return GatewayResponse(
            "knowledge.get_source_fragment",
            SUPPORTED_CONTRACT_VERSION,
            GatewayStatus.OK,
            {"fragment_reference": dict(row)},
            EvidencePack((), (), (), (), ()),
        )

    def _applicable_rules(
        self, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        rule_set_id = payload.get("rule_set_version_id")
        if rule_set_id in {None, "latest"}:
            return self._gap(
                "knowledge.get_applicable_rules",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "rule_set_not_pinned",
            )
        with Session(self._engine) as session:
            if context.workspace_id is not None and context.organization_id is not None:
                session.execute(
                    sa.select(
                        sa.func.set_config(
                            "asd.organization_id", str(context.organization_id), True
                        ),
                        sa.func.set_config("asd.workspace_id", str(context.workspace_id), True),
                    )
                ).one()
            rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT rv.rule_version_id,r.rule_key,rv.predicate_contract,rv.output_contract "
                        "FROM platform.rule_set_memberships m "
                        "JOIN platform.rule_versions rv ON rv.rule_version_id=m.rule_version_id "
                        "JOIN platform.rules r ON r.rule_id=rv.rule_id "
                        "JOIN LATERAL (SELECT status FROM platform.rule_version_states s "
                        "WHERE s.rule_version_id=rv.rule_version_id ORDER BY recorded_at DESC LIMIT 1) state ON true "
                        "WHERE m.rule_set_version_id=:set AND state.status='active' ORDER BY m.ordinal"
                    ),
                    {"set": rule_set_id},
                ).mappings()
            )
            workspace_rule_ids = tuple(payload.get("workspace_rule_version_ids", ()))
            workspace_rows: tuple[Any, ...] = ()
            if workspace_rule_ids:
                if context.workspace_id is None:
                    raise KnowledgeError(
                        KnowledgeErrorCode.SCOPE_VIOLATION,
                        "Pinned workspace RuleVersion requires explicit workspace scope.",
                    )
                workspace_rows = tuple(
                    session.execute(
                        sa.text(
                            "SELECT rv.rule_version_id,r.rule_key,rv.predicate_contract,rv.output_contract "
                            "FROM workspace.rule_versions rv JOIN workspace.rules r "
                            "ON r.organization_id=rv.organization_id AND r.workspace_id=rv.workspace_id "
                            "AND r.rule_id=rv.rule_id JOIN LATERAL "
                            "(SELECT status FROM workspace.rule_version_states s WHERE "
                            "s.organization_id=rv.organization_id AND s.workspace_id=rv.workspace_id "
                            "AND s.rule_version_id=rv.rule_version_id ORDER BY state_sequence DESC LIMIT 1) state "
                            "ON true WHERE rv.rule_version_id IN :ids AND state.status='active' "
                            "ORDER BY rv.rule_version_id"
                        ).bindparams(sa.bindparam("ids", expanding=True)),
                        {"ids": workspace_rule_ids},
                    ).mappings()
                )
                if len(workspace_rows) != len(workspace_rule_ids):
                    raise KnowledgeError(
                        KnowledgeErrorCode.RULE_NOT_ACTIVE,
                        "A pinned workspace RuleVersion is absent, inactive, or outside the workspace scope.",
                    )
        return GatewayResponse(
            "knowledge.get_applicable_rules",
            SUPPORTED_CONTRACT_VERSION,
            GatewayStatus.OK if rows or workspace_rows else GatewayStatus.NO_RESULT,
            {
                "rules": [dict(row) for row in rows],
                "rule_set_version_id": rule_set_id,
                "workspace_rules": [dict(row) for row in workspace_rows],
            },
            EvidencePack((), (), (), (), ()),
        )

    def _trace_assertion(
        self, payload: dict[str, Any], _context: GatewayContext
    ) -> GatewayResponse:
        assertion = payload.get("knowledge_assertion_id")
        if assertion is None:
            return self._gap(
                "knowledge.trace_assertion",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "assertion_id_missing",
            )
        pack = self._evidence_for((UUID(str(assertion)),))
        status = GatewayStatus.OK if pack.evidence else GatewayStatus.KNOWLEDGE_INCOMPLETE
        return GatewayResponse(
            "knowledge.trace_assertion",
            SUPPORTED_CONTRACT_VERSION,
            status,
            {"knowledge_assertion_id": assertion},
            pack,
        )

    def _explain_conflict(
        self, payload: dict[str, Any], _context: GatewayContext
    ) -> GatewayResponse:
        conflict_id = payload.get("conflict_id")
        with Session(self._engine) as session:
            row = (
                session.execute(
                    sa.text(
                        "SELECT normative_conflict_id,conflict_type,state,uncertainty_ref,"
                        "conflict_policy_version_id FROM platform.normative_conflicts "
                        "WHERE normative_conflict_id=:id"
                    ),
                    {"id": conflict_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return self._gap(
                "knowledge.explain_conflict", GatewayStatus.NO_RESULT, "conflict_not_found"
            )
        return GatewayResponse(
            "knowledge.explain_conflict",
            SUPPORTED_CONTRACT_VERSION,
            GatewayStatus.OK,
            {"conflict": dict(row)},
            EvidencePack((), (), (dict(row),), (), ()),
        )

    def _required_documents(
        self, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        # G-05 exposes the exact contract and pinned rules; document determination is WP-09.
        rules = self._applicable_rules(payload, context)
        return GatewayResponse(
            "knowledge.get_required_documents",
            SUPPORTED_CONTRACT_VERSION,
            GatewayStatus.KNOWLEDGE_INCOMPLETE,
            {"required_documents": [], "applicable_rules": rules.result.get("rules", [])},
            EvidencePack(
                rules.evidence_pack.evidence,
                rules.evidence_pack.applicability,
                rules.evidence_pack.conflicts,
                ({"code": "required_document_runtime_not_implemented", "owner_gate": "WP-09"},),
                rules.evidence_pack.uncertainties,
            ),
        )

    def _evidence_for(self, assertion_ids: tuple[UUID, ...]) -> EvidencePack:
        if not assertion_ids:
            return EvidencePack((), (), (), (), ())
        with Session(self._engine) as session:
            rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT ae.assertion_evidence_id,sv.source_version_id,"
                        "ne.normative_edition_id,su.structural_path,sv.content_digest,o.access_capability_ref "
                        "FROM platform.assertion_evidence ae "
                        "JOIN platform.source_versions sv ON sv.source_version_id=ae.source_version_id "
                        "JOIN platform.objects o ON o.object_id=sv.object_id "
                        "JOIN platform.knowledge_assertions ka ON ka.knowledge_assertion_id=ae.knowledge_assertion_id "
                        "LEFT JOIN platform.structural_units su ON su.structural_unit_id=ka.structural_unit_id "
                        "LEFT JOIN platform.normative_editions ne ON ne.normative_edition_id=su.normative_edition_id "
                        "WHERE ae.knowledge_assertion_id IN :ids ORDER BY ae.assertion_evidence_id"
                    ).bindparams(sa.bindparam("ids", expanding=True)),
                    {"ids": assertion_ids},
                ).mappings()
            )
        evidence = tuple(
            EvidenceItem(
                str(row["assertion_evidence_id"]),
                str(row["source_version_id"]),
                str(row["normative_edition_id"]) if row["normative_edition_id"] else None,
                str(row["structural_path"] or ""),
                str(row["content_digest"]),
                str(row["access_capability_ref"]),
            )
            for row in rows
        )
        gaps = () if evidence else ({"code": "assertion_evidence_unavailable"},)
        return EvidencePack(evidence, (), (), gaps, ())

    def _guidance_evidence(self, identities: tuple[tuple[UUID, int], ...]) -> EvidencePack:
        if not identities:
            return EvidencePack((), (), (), ({"code": "guidance_evidence_unavailable"},), ())
        clauses = []
        conflict_clauses = []
        parameters: dict[str, object] = {}
        for index, (guidance_id, version) in enumerate(identities):
            clauses.append(
                f"(ge.guidance_unit_id=:guidance_{index} AND "
                f"ge.guidance_unit_version=:version_{index})"
            )
            conflict_clauses.append(
                f"(c.guidance_unit_id=:guidance_{index} AND "
                f"c.guidance_unit_version=:version_{index})"
            )
            parameters[f"guidance_{index}"] = guidance_id
            parameters[f"version_{index}"] = version
        with Session(self._engine) as session:
            rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT ge.guidance_evidence_id,ge.source_version_id,ge.page_number,"
                        "ge.region,sv.content_digest,o.access_capability_ref,sl.locator_key "
                        "FROM platform.practice_guidance_evidence ge "
                        "JOIN platform.source_versions sv ON sv.source_version_id=ge.source_version_id "
                        "JOIN platform.objects o ON o.object_id=sv.object_id "
                        "JOIN platform.source_locators sl ON sl.source_locator_id=ge.source_locator_id "
                        "WHERE " + " OR ".join(clauses) + " ORDER BY ge.guidance_evidence_id"
                    ),
                    parameters,
                ).mappings()
            )
            conflict_rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT c.guidance_conflict_id,c.guidance_unit_id,"
                        "c.guidance_unit_version,c.conflicting_authority_layer,"
                        "c.conflicting_subject_ref,c.conflict_type,c.state,c.uncertainty_ref "
                        "FROM platform.practice_guidance_conflicts c WHERE ("
                        + " OR ".join(conflict_clauses)
                        + ") AND c.state='open' ORDER BY c.guidance_conflict_id"
                    ),
                    parameters,
                ).mappings()
            )
        evidence = tuple(
            EvidenceItem(
                evidence_link_id=str(row["guidance_evidence_id"]),
                source_version_id=str(row["source_version_id"]),
                edition_id=None,
                structural_unit_locator=str(row["locator_key"]),
                content_digest=str(row["content_digest"]),
                access_reference=str(row["access_capability_ref"]),
                authority_layer="methodological_guidance",
            )
            for row in rows
        )
        gaps = () if evidence else ({"code": "guidance_evidence_unavailable"},)
        return EvidencePack(evidence, (), tuple(dict(row) for row in conflict_rows), gaps, ())

    @staticmethod
    def _gap(tool: str, status: GatewayStatus, code: str) -> GatewayResponse:
        return GatewayResponse(
            tool,
            SUPPORTED_CONTRACT_VERSION,
            status,
            {},
            EvidencePack((), (), (), ({"code": code},), ()),
        )

    def _guidance_gap(
        self,
        tool: str,
        status: GatewayStatus,
        code: str,
        payload: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        coverage, relevant_gaps = self._guidance_coverage(payload or {})
        effective_status = GatewayStatus.KNOWLEDGE_INCOMPLETE if relevant_gaps else status
        return GatewayResponse(
            tool,
            GUIDANCE_CONTRACT_VERSION,
            effective_status,
            coverage,
            EvidencePack((), (), (), ({"code": code}, *relevant_gaps), ()),
        )


class PostgresKnowledgeAudit:
    """Content-minimal platform audit: operation and outcome, never query text/results."""

    def __init__(self, engine: Engine, *, service_identity_id: str) -> None:
        self._engine = engine
        self._service_identity_id = service_identity_id

    def record(
        self,
        *,
        context: GatewayContext,
        tool: str,
        status: GatewayStatus | str,
        evidence_count: int,
    ) -> None:
        metadata = {"evidence_count": evidence_count, "status": str(status)}
        contract_version = (
            GUIDANCE_CONTRACT_VERSION if tool in GUIDANCE_TOOLS else SUPPORTED_CONTRACT_VERSION
        )
        digest = (
            f"sha256:{hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()}"
        )
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO audit.platform_records "
                    "(audit_record_id,audit_version,actor_identity_id,service_identity_id,capability,operation,"
                    "outcome_code,correlation_id,contract_key,contract_version,policy_key,policy_version,"
                    "safe_message_key,retention_class,record_digest) "
                    "VALUES (:id,1,:actor,:service,:capability,:operation,:outcome,:correlation,"
                    "'knowledge.gateway',:contract,'knowledge-access-policy','0.1.0',"
                    "'audit.knowledge.tool','platform-audit-minimal',:digest)"
                ),
                {
                    "id": uuid7(),
                    "actor": context.actor_identity_id,
                    "service": self._service_identity_id,
                    "capability": context.capability,
                    "operation": tool,
                    "outcome": str(status),
                    "correlation": context.correlation_id,
                    "contract": contract_version,
                    "digest": digest,
                },
            )
