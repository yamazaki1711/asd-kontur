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

PRACTICE_INTENT_KINDS = {
    "workflow": ("id_workflow_step", "id_practice_principle", "document_dependency_guidance"),
    "form_selection": (
        "form_completion_guidance",
        "journal_selection_guidance",
        "document_dependency_guidance",
    ),
    "form_completion": (
        "form_completion_guidance",
        "field_completion_guidance",
        "completion_instruction",
        "attention_point",
        "visual_completion_example",
    ),
    "required_inputs": ("completeness_guidance", "document_dependency_guidance"),
    "preflight_check": (
        "verification_checklist",
        "attention_point",
        "common_failure_pattern",
    ),
    "rationale": ("practice_rationale", "id_practice_principle"),
    "allowed_variants": ("allowed_practice_variant",),
    "journal_selection": ("journal_selection_guidance",),
    "failure_detection": ("common_failure_pattern", "verification_checklist"),
    "dependencies": ("document_dependency_guidance", "completeness_guidance"),
    "completeness": (
        "completeness_guidance",
        "verification_checklist",
        "document_dependency_guidance",
    ),
    "field_completion": (
        "field_completion_guidance",
        "completion_instruction",
        "attention_point",
        "common_failure_pattern",
    ),
    "signing": ("signer_role_guidance", "attention_point", "verification_checklist"),
    "visual_examples": ("visual_completion_example",),
}


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
            "knowledge.get_id_task_guidance": self._id_task_guidance,
            "knowledge.get_practice_playbook": self._practice_playbook,
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
                        "v.region,sv.content_digest,o.access_capability_ref,"
                        "e.practice_guide_edition_id "
                        "FROM platform.practice_guidance_conflicts c "
                        "JOIN platform.practice_guide_candidate_versions v ON "
                        "v.guidance_candidate_id=c.guidance_candidate_id "
                        "AND v.version=c.candidate_version "
                        "JOIN platform.source_versions sv ON sv.source_version_id=v.source_version_id "
                        "JOIN platform.practice_guide_editions e ON "
                        "e.source_version_id=v.source_version_id "
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
                    authority_layer="methodological_practice",
                ),
            )
        return GatewayResponse(
            "knowledge.explain_guidance_conflict",
            GUIDANCE_CONTRACT_VERSION,
            GatewayStatus.OK,
            {
                "conflict": dict(row),
                "practice_guide_edition_id": str(row["practice_guide_edition_id"]),
                **coverage,
            },
            EvidencePack(
                evidence,
                (),
                (dict(row),),
                (),
                ({"code": str(row["uncertainty_ref"])},),
            ),
        )

    @staticmethod
    def _practice_authority_composition(
        units: tuple[Any, ...], context: GatewayContext
    ) -> dict[str, object]:
        normative_references = tuple(
            reference
            for unit in units
            for reference in (unit.get("normative_references") or ())
            if isinstance(reference, dict)
        )
        return {
            "normative_authority": {
                "role": "what_is_required",
                "status": "references_only_not_evaluated",
                "references": normative_references,
            },
            "methodological_practice": {
                "role": "how_to_perform_and_what_to_check",
                "status": "primary_id_practice_context",
                "may_activate_rule_version": False,
            },
            "workspace_facts": {
                "role": "object_specific_documents_facts_and_conditions",
                "status": (
                    "workspace_scope_present"
                    if context.workspace_id is not None
                    else "workspace_scope_not_supplied"
                ),
                "workspace_id": str(context.workspace_id) if context.workspace_id else None,
            },
            "deterministic_rules": {
                "role": "applicability_completeness_and_blockers",
                "status": "not_evaluated_by_this_tool",
                "requires_separate_rule_evidence": True,
            },
        }

    def _id_task_guidance(
        self, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        query = str(payload.get("query", "")).strip()
        lexical_version_id = payload.get("lexical_version_id")
        edition_id = payload.get("practice_guide_edition_id")
        policy_id = payload.get("context_assembly_policy_id")
        policy_version = payload.get("context_assembly_policy_version")
        intent = str(payload.get("intent", "workflow")).strip()
        if not query or edition_id is None or intent not in PRACTICE_INTENT_KINDS:
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "practice_query_index_or_intent_invalid",
                payload,
            )
        statement = sa.text(
            "SELECT u.intelligence_unit_id,u.version,u.practice_guide_edition_id,"
            "u.intelligence_kind,u.title,u.instruction,"
            "u.rationale,u.applicability_conditions,u.work_types,u.document_types,u.form_types,"
            "u.workflow_stages,u.field_elements,u.required_inputs,u.evidence_requirements,"
            "u.allowed_variants,u.failure_patterns,u.checklist_items,u.dependency_refs,"
            "u.normative_references,u.uncertainties,u.authority_layer,u.coverage_manifest_id,"
            "EXISTS (SELECT 1 FROM platform.practice_intelligence_sources src "
            "JOIN platform.practice_guidance_conflicts conflict ON "
            "conflict.guidance_unit_id=src.guidance_unit_id AND "
            "conflict.guidance_unit_version=src.guidance_unit_version "
            "WHERE src.intelligence_unit_id=u.intelligence_unit_id AND "
            "src.intelligence_unit_version=u.version AND conflict.state='open') "
            "AS has_open_conflict "
            "FROM projection.practice_intelligence_lexical_entries e "
            "JOIN platform.practice_intelligence_units u ON "
            "u.intelligence_unit_id=e.entity_id AND u.version=e.entity_version "
            "WHERE e.lexical_version_id=:index AND e.entity_kind='intelligence_unit' "
            "AND u.practice_guide_edition_id=:edition "
            "AND (NOT EXISTS (SELECT 1 FROM "
            "platform.practice_intelligence_release_memberships any_member WHERE "
            "any_member.release_id=:release AND any_member.release_version=:release_version) "
            "OR EXISTS (SELECT 1 FROM platform.practice_intelligence_release_memberships member "
            "WHERE member.release_id=:release AND member.release_version=:release_version AND "
            "member.intelligence_identity_id=u.intelligence_unit_id AND "
            "member.intelligence_version=u.version)) "
            "AND e.intelligence_kind IN :kinds "
            "AND e.search_vector @@ plainto_tsquery('russian',:query) "
            "ORDER BY ts_rank_cd(e.search_vector,plainto_tsquery('russian',:query)) DESC,"
            "u.intelligence_kind,u.intelligence_unit_id,u.version LIMIT :unit_limit"
        ).bindparams(sa.bindparam("kinds", expanding=True))
        with Session(self._engine) as session:
            activation = (
                session.execute(
                    sa.text(
                        "SELECT e.practice_guide_id,d.activation_decision_id,d.version,"
                        "d.selected_edition_id FROM "
                        "platform.practice_guide_editions e JOIN LATERAL "
                        "(SELECT activation_decision_id,version,selected_edition_id FROM "
                        "platform.practice_guide_edition_activation_decisions "
                        "WHERE practice_guide_id=e.practice_guide_id ORDER BY version DESC LIMIT 1) d "
                        "ON true WHERE e.practice_guide_edition_id=:edition"
                    ),
                    {"edition": edition_id},
                )
                .mappings()
                .one_or_none()
            )
        if activation is None or str(activation["selected_edition_id"]) != str(edition_id):
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.EDITION_MISMATCH,
                "edition_mismatch",
                payload,
            )
        explicit_release_id = payload.get("practice_intelligence_release_id")
        explicit_release_version = payload.get("practice_intelligence_release_version")
        with Session(self._engine) as session:
            if explicit_release_id is not None or explicit_release_version is not None:
                if explicit_release_id is None or not isinstance(explicit_release_version, int):
                    release = None
                else:
                    release = (
                        session.execute(
                            sa.text(
                                "SELECT release_id,version,construction_manifest_id,"
                                "context_assembly_policy_id,context_assembly_policy_version "
                                "FROM platform.practice_intelligence_releases WHERE "
                                "release_id=:id AND version=:version AND "
                                "practice_guide_edition_id=:edition"
                            ),
                            {
                                "id": explicit_release_id,
                                "version": explicit_release_version,
                                "edition": edition_id,
                            },
                        )
                        .mappings()
                        .one_or_none()
                    )
                release_selection = "historical_exact_pin"
            else:
                release = (
                    session.execute(
                        sa.text(
                            "SELECT r.release_id,r.version,r.construction_manifest_id,"
                            "r.context_assembly_policy_id,r.context_assembly_policy_version "
                            "FROM platform.practice_intelligence_release_activation_decisions d "
                            "JOIN platform.practice_intelligence_releases r ON "
                            "r.release_id=d.selected_release_id AND "
                            "r.version=d.selected_release_version WHERE "
                            "d.practice_guide_id=:guide ORDER BY d.version DESC LIMIT 1"
                        ),
                        {"guide": activation["practice_guide_id"]},
                    )
                    .mappings()
                    .one_or_none()
                )
                release_selection = "active_release_decision"
        if release is None:
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "practice_intelligence_release_unavailable",
                payload,
            )
        if policy_id is not None and str(policy_id) != str(release["context_assembly_policy_id"]):
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "release_policy_binding_mismatch",
                payload,
            )
        if policy_version is not None and (
            not isinstance(policy_version, int)
            or policy_version != int(release["context_assembly_policy_version"])
        ):
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "release_policy_binding_mismatch",
                payload,
            )
        policy_id = release["context_assembly_policy_id"]
        policy_version = int(release["context_assembly_policy_version"])
        with Session(self._engine) as session:
            release_lexical_id = session.execute(
                sa.text(
                    "SELECT lexical_version_id FROM "
                    "projection.practice_intelligence_lexical_versions WHERE "
                    "construction_manifest_id=:manifest AND state='ready' "
                    "ORDER BY lexical_version_id DESC LIMIT 1"
                ),
                {"manifest": release["construction_manifest_id"]},
            ).scalar_one_or_none()
        if release_lexical_id is None or (
            lexical_version_id is not None and str(lexical_version_id) != str(release_lexical_id)
        ):
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.INDEX_UNAVAILABLE,
                "release_projection_binding_mismatch",
                payload,
            )
        lexical_version_id = release_lexical_id
        with Session(self._engine) as session:
            policy = (
                session.execute(
                    sa.text(
                        "SELECT practice_guide_edition_id,allowed_modes,allowed_purposes,"
                        "max_intelligence_units,max_playbooks,state "
                        "FROM platform.context_assembly_policies WHERE policy_id=:id "
                        "AND version=:version"
                    ),
                    {"id": policy_id, "version": policy_version},
                )
                .mappings()
                .one_or_none()
            )
        if policy is None or policy["state"] != "active":
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "context_assembly_policy_unavailable",
                payload,
            )
        if str(policy["practice_guide_edition_id"]) != str(edition_id):
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.EDITION_MISMATCH,
                "edition_mismatch",
                payload,
            )
        if payload.get("mode") not in (policy["allowed_modes"] or ()) or payload.get(
            "purpose"
        ) not in (policy["allowed_purposes"] or ()):
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "context_assembly_scope_not_allowed",
                payload,
            )
        with Session(self._engine) as session:
            state = session.execute(
                sa.text(
                    "SELECT state FROM projection.practice_intelligence_lexical_versions "
                    "WHERE lexical_version_id=:id AND construction_manifest_id=:manifest"
                ),
                {
                    "id": lexical_version_id,
                    "manifest": release["construction_manifest_id"],
                },
            ).scalar_one_or_none()
            matched_rows = (
                tuple(
                    session.execute(
                        statement,
                        {
                            "index": lexical_version_id,
                            "edition": edition_id,
                            "release": release["release_id"],
                            "release_version": release["version"],
                            "kinds": PRACTICE_INTENT_KINDS[intent],
                            "query": query,
                            "unit_limit": int(policy["max_intelligence_units"]),
                        },
                    ).mappings()
                )
                if state == "ready"
                else ()
            )
            rows = tuple(row for row in matched_rows if not bool(row["has_open_conflict"]))
            conflicting_rows = tuple(row for row in matched_rows if bool(row["has_open_conflict"]))
            identities = tuple(
                (UUID(str(row["intelligence_unit_id"])), int(row["version"])) for row in rows
            )
            conflicting_identities = tuple(
                (UUID(str(row["intelligence_unit_id"])), int(row["version"]))
                for row in conflicting_rows
            )
            playbooks = self._playbooks_for_units(session, identities, int(policy["max_playbooks"]))
        if state != "ready":
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.INDEX_UNAVAILABLE,
                "practice_intelligence_index_not_ready",
                payload,
            )
        if not matched_rows:
            return self._guidance_gap(
                "knowledge.get_id_task_guidance",
                GatewayStatus.NO_RESULT,
                "practice_intelligence_not_found",
                payload,
            )
        coverage, relevant_gaps = self._guidance_coverage(payload)
        pack = self._intelligence_evidence(identities)
        conflict_pack = self._intelligence_evidence(conflicting_identities)
        effective_status = (
            GatewayStatus.GUIDANCE_NORMATIVE_CONFLICT
            if conflict_pack.conflicts
            else GatewayStatus.KNOWLEDGE_INCOMPLETE
            if relevant_gaps
            else GatewayStatus.OK
        )
        return GatewayResponse(
            "knowledge.get_id_task_guidance",
            GUIDANCE_CONTRACT_VERSION,
            effective_status,
            {
                "intent": intent,
                "practice_guide_edition_id": str(edition_id),
                "activation_decision_id": str(activation["activation_decision_id"]),
                "activation_decision_version": int(activation["version"]),
                "context_assembly_policy_id": str(policy_id),
                "context_assembly_policy_version": policy_version,
                "practice_intelligence_release_id": str(release["release_id"]),
                "practice_intelligence_release_version": int(release["version"]),
                "release_selection": release_selection,
                "practice_intelligence": [
                    {key: value for key, value in dict(row).items() if key != "has_open_conflict"}
                    for row in rows
                ],
                "practice_playbooks": [dict(row) for row in playbooks],
                "quarantined_conflict_match_count": len(conflicting_rows),
                "authority_composition": self._practice_authority_composition(rows, context),
                "retrieval": "exact_fts_with_typed_intent",
                **coverage,
            },
            EvidencePack(
                (*pack.evidence, *conflict_pack.evidence),
                pack.applicability,
                conflict_pack.conflicts,
                (*pack.gaps, *conflict_pack.gaps, *relevant_gaps),
                (*pack.uncertainties, *conflict_pack.uncertainties),
            ),
        )

    def _practice_playbook(
        self, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        playbook_id = payload.get("playbook_id")
        version = payload.get("version")
        if playbook_id is None or not isinstance(version, int):
            return self._guidance_gap(
                "knowledge.get_practice_playbook",
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                "playbook_identity_or_version_missing",
                payload,
            )
        with Session(self._engine) as session:
            playbook = (
                session.execute(
                    sa.text(
                        "SELECT playbook_id,version,title,purpose,applicability_conditions,"
                        "work_types,document_types,form_types,workflow_stages,uncertainties,"
                        "authority_layer,coverage_manifest_id FROM platform.practice_playbooks "
                        "WHERE playbook_id=:id AND version=:version"
                    ),
                    {"id": playbook_id, "version": version},
                )
                .mappings()
                .one_or_none()
            )
            members = (
                tuple(
                    session.execute(
                        sa.text(
                            "SELECT m.member_sequence,m.member_role,u.intelligence_unit_id,u.version,"
                            "u.intelligence_kind,u.title,u.instruction,u.rationale,"
                            "u.applicability_conditions,u.required_inputs,u.evidence_requirements,"
                            "u.allowed_variants,u.failure_patterns,u.checklist_items,u.dependency_refs,"
                            "u.normative_references,u.uncertainties,u.authority_layer "
                            "FROM platform.practice_playbook_members m "
                            "JOIN platform.practice_intelligence_units u ON "
                            "u.intelligence_unit_id=m.intelligence_unit_id "
                            "AND u.version=m.intelligence_unit_version WHERE m.playbook_id=:id "
                            "AND m.playbook_version=:version ORDER BY m.member_sequence LIMIT 100"
                        ),
                        {"id": playbook_id, "version": version},
                    ).mappings()
                )
                if playbook is not None
                else ()
            )
        if playbook is None:
            return self._guidance_gap(
                "knowledge.get_practice_playbook",
                GatewayStatus.NO_RESULT,
                "practice_playbook_not_found",
                payload,
            )
        identities = tuple(
            (UUID(str(row["intelligence_unit_id"])), int(row["version"])) for row in members
        )
        coverage_payload = dict(payload)
        document_types = playbook["document_types"] or ()
        if document_types:
            coverage_payload["document_or_form_type"] = str(document_types[0])
        coverage, relevant_gaps = self._guidance_coverage(coverage_payload)
        pack = self._intelligence_evidence(identities)
        playbook_partial = "COVERAGE_MANIFEST_PARTIAL" in (playbook["uncertainties"] or ())
        playbook_gaps = ({"code": "playbook_coverage_partial"},) if playbook_partial else ()
        return GatewayResponse(
            "knowledge.get_practice_playbook",
            GUIDANCE_CONTRACT_VERSION,
            (
                GatewayStatus.KNOWLEDGE_INCOMPLETE
                if relevant_gaps or playbook_partial
                else GatewayStatus.OK
            ),
            {
                "practice_playbook": dict(playbook),
                "members": [dict(row) for row in members],
                "member_limit": 100,
                "authority_composition": self._practice_authority_composition(members, context),
                **coverage,
            },
            EvidencePack(
                pack.evidence,
                pack.applicability,
                pack.conflicts,
                (*pack.gaps, *playbook_gaps, *relevant_gaps),
                pack.uncertainties,
            ),
        )

    @staticmethod
    def _playbooks_for_units(
        session: Session, identities: tuple[tuple[UUID, int], ...], limit: int
    ) -> tuple[Any, ...]:
        if not identities:
            return ()
        clauses = []
        parameters: dict[str, object] = {}
        for index, (unit_id, version) in enumerate(identities):
            clauses.append(
                f"(m.intelligence_unit_id=:unit_{index} AND "
                f"m.intelligence_unit_version=:unit_version_{index})"
            )
            parameters[f"unit_{index}"] = unit_id
            parameters[f"unit_version_{index}"] = version
        return tuple(
            session.execute(
                sa.text(
                    "SELECT DISTINCT p.playbook_id,p.version,p.title,p.purpose,p.document_types,"
                    "p.form_types,p.workflow_stages,p.uncertainties,p.authority_layer "
                    "FROM platform.practice_playbook_members m JOIN platform.practice_playbooks p "
                    "ON p.playbook_id=m.playbook_id AND p.version=m.playbook_version WHERE "
                    + " OR ".join(clauses)
                    + " ORDER BY p.playbook_id,p.version LIMIT :playbook_limit"
                ),
                {**parameters, "playbook_limit": limit},
            ).mappings()
        )

    def _intelligence_evidence(self, identities: tuple[tuple[UUID, int], ...]) -> EvidencePack:
        if not identities:
            return EvidencePack((), (), (), ({"code": "practice_intelligence_unavailable"},), ())
        clauses = []
        unit_clauses = []
        parameters: dict[str, object] = {}
        for index, (unit_id, version) in enumerate(identities):
            clauses.append(
                f"(s.intelligence_unit_id=:unit_{index} AND "
                f"s.intelligence_unit_version=:version_{index})"
            )
            unit_clauses.append(
                f"(u.intelligence_unit_id=:unit_{index} AND u.version=:version_{index})"
            )
            parameters[f"unit_{index}"] = unit_id
            parameters[f"version_{index}"] = version
        with Session(self._engine) as session:
            rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT s.intelligence_source_id,s.intelligence_unit_id,"
                        "s.source_version_id,sl.locator_key,sv.content_digest,"
                        "o.access_capability_ref FROM platform.practice_intelligence_sources s "
                        "JOIN platform.source_locators sl ON sl.source_locator_id=s.source_locator_id "
                        "JOIN platform.source_versions sv ON sv.source_version_id=s.source_version_id "
                        "JOIN platform.objects o ON o.object_id=sv.object_id WHERE "
                        + " OR ".join(clauses)
                        + " ORDER BY s.intelligence_source_id"
                    ),
                    parameters,
                ).mappings()
            )
            unit_rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT u.intelligence_unit_id,u.applicability_conditions,"
                        "u.normative_references,u.uncertainties FROM "
                        "platform.practice_intelligence_units u WHERE "
                        + " OR ".join(unit_clauses)
                        + " ORDER BY u.intelligence_unit_id"
                    ),
                    parameters,
                ).mappings()
            )
            conflict_rows = tuple(
                session.execute(
                    sa.text(
                        "SELECT DISTINCT c.guidance_conflict_id,c.conflicting_authority_layer,"
                        "c.conflicting_subject_ref,c.conflict_type,c.state,c.uncertainty_ref "
                        "FROM platform.practice_intelligence_sources s JOIN "
                        "platform.practice_guidance_conflicts c ON "
                        "c.guidance_unit_id=s.guidance_unit_id AND "
                        "c.guidance_unit_version=s.guidance_unit_version WHERE ("
                        + " OR ".join(clauses)
                        + ") AND c.state='open' ORDER BY c.guidance_conflict_id"
                    ),
                    parameters,
                ).mappings()
            )
        evidence = tuple(
            EvidenceItem(
                evidence_link_id=str(row["intelligence_source_id"]),
                source_version_id=str(row["source_version_id"]),
                edition_id=None,
                structural_unit_locator=str(row["locator_key"]),
                content_digest=str(row["content_digest"]),
                access_reference=str(row["access_capability_ref"]),
                authority_layer="methodological_practice",
            )
            for row in rows
        )
        applicability = tuple(
            {
                "intelligence_unit_id": str(row["intelligence_unit_id"]),
                "conditions": row["applicability_conditions"],
            }
            for row in unit_rows
            if row["applicability_conditions"]
        )
        uncertainties = tuple(
            {
                "intelligence_unit_id": str(row["intelligence_unit_id"]),
                "code": code,
            }
            for row in unit_rows
            for code in (row["uncertainties"] or ())
        )
        gaps = () if evidence else ({"code": "practice_intelligence_evidence_unavailable"},)
        return EvidencePack(
            evidence,
            applicability,
            tuple(dict(row) for row in conflict_rows),
            gaps,
            uncertainties,
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
            {
                "guidance": [
                    {**dict(row), "authority_layer": "methodological_practice"} for row in rows
                ],
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
                authority_layer="methodological_practice",
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
        effective_status = (
            GatewayStatus.KNOWLEDGE_INCOMPLETE
            if relevant_gaps
            and status
            not in {
                GatewayStatus.EDITION_MISMATCH,
                GatewayStatus.GUIDANCE_NORMATIVE_CONFLICT,
            }
            else status
        )
        pinned_context = {
            key: payload[key]
            for key in (
                "practice_guide_edition_id",
                "context_assembly_policy_id",
                "context_assembly_policy_version",
            )
            if payload is not None and payload.get(key) is not None
        }
        return GatewayResponse(
            tool,
            GUIDANCE_CONTRACT_VERSION,
            effective_status,
            {**coverage, **pinned_context},
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
