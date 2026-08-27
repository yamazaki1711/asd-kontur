"""Read-only exact NTD queries behind the common Knowledge Gateway."""

# ruff: noqa: E501, RUF001 -- SQL clauses and exact Cyrillic designations are intentional.

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.knowledge.gateway import (
    NTD_CONTRACT_VERSION,
    PD_RD_NTD_CONTRACT_VERSION,
    PD_RD_NTD_TOOLS,
    EvidenceItem,
    EvidencePack,
    GatewayContext,
    GatewayResponse,
    GatewayStatus,
)

from .identifiers import normalize_identifier


class NtdKnowledgeQueryService:
    """Gateway query port; callers never receive SQL or mutation authority."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def execute(
        self, tool: str, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        handlers = {
            "knowledge.resolve_ntd": self._resolve_ntd,
            "knowledge.get_ntd_document": self._get_document,
            "knowledge.get_ntd_edition": self._get_edition,
            "knowledge.get_ntd_provision": self._get_provision,
            "knowledge.search_ntd": self._search,
            "knowledge.get_ntd_evidence_pack": self._get_evidence_pack,
            "knowledge.get_practice_ntd_alignment": self._get_alignment,
        }
        if tool in PD_RD_NTD_TOOLS:
            return self._get_pd_rd_profile(tool, payload, context)
        handler = handlers.get(tool)
        if handler is None:
            return self._response(
                tool, GatewayStatus.NO_RESULT, {}, gaps=(self._gap("unknown_tool"),)
            )
        return handler(tool, payload)

    def _get_pd_rd_profile(
        self, tool: str, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        if context.organization_id is None or context.workspace_id is None:
            return self._response(
                tool,
                GatewayStatus.NO_RESULT,
                {},
                gaps=(self._gap("workspace_scope_required"),),
            )
        profile_id = _required_uuid(payload, "profile_id")
        version = int(payload.get("version", 0))
        if version < 1:
            raise ValueError("version is required")
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(context.organization_id), True),
                    sa.func.set_config("asd.workspace_id", str(context.workspace_id), True),
                )
            ).one()
            row = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.applicable_pd_rd_normative_profiles WHERE "
                        "organization_id=:organization AND workspace_id=:workspace AND "
                        "profile_id=:profile AND version=:version"
                    ),
                    {
                        "organization": context.organization_id,
                        "workspace": context.workspace_id,
                        "profile": profile_id,
                        "version": version,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return self._response(
                tool,
                GatewayStatus.NO_RESULT,
                {},
                gaps=(self._gap("pd_rd_profile_pin_not_found", f"{profile_id}:{version}"),),
            )
        gaps = tuple(dict(item) for item in row["gaps"])
        status = GatewayStatus.KNOWLEDGE_GAP if gaps else GatewayStatus.OK
        requirements = [
            *row["required_pd_sections"],
            *row["expected_rd_sets"],
            *row["formatting_requirements"],
        ]
        evidence = tuple(
            EvidenceItem(
                evidence_link_id=(
                    f"pd-rd-rule:{item['rule_version_id']}:"
                    f"{item['normative_provision_id']}:{item['normative_provision_version']}"
                ),
                source_version_id=str(item["source_version_id"]),
                edition_id=str(item["normative_edition_id"]),
                structural_unit_locator=str(item["structural_path"]),
                content_digest=str(item["evidence_digest"]),
                access_reference=str(item["official_source"]),
                authority_layer="normative_authority",
            )
            for item in requirements
        )
        result: dict[str, Any] = {
            "authority_layer": "normative_authority",
            "profile_id": str(profile_id),
            "profile_version": version,
            "project_definition": {
                "id": str(row["project_definition_id"]),
                "version": int(row["project_definition_version"]),
                "authority_layer": "workspace_fact",
            },
            "applicable_on": (
                row["applicable_on"].isoformat() if row["applicable_on"] is not None else None
            ),
            "normative_edition_ids": [str(item) for item in row["normative_edition_ids"]],
            "rule_version_ids": [str(item) for item in row["rule_version_ids"]],
            "corpus_denominator": dict(row["corpus_denominator"]),
            "unresolved_inputs": list(row["unresolved_inputs"]),
            "gaps": list(gaps),
            "completeness_status": str(row["completeness_status"]),
            "semantic_fingerprint": str(row["semantic_fingerprint"]),
            "practice_intelligence": None,
            "customer_addition": None,
            "ai_candidate": None,
        }
        if tool == "knowledge.resolve_applicable_pd_sections":
            result["required_pd_sections"] = row["required_pd_sections"]
        elif tool == "knowledge.resolve_section_content_requirements":
            section = str(payload.get("section", ""))
            result["requirements"] = [
                item
                for item in row["required_pd_sections"]
                if not section or str(item.get("section", item.get("code", ""))) == section
            ]
        elif tool == "knowledge.resolve_expected_rd_sets":
            result["expected_rd_sets"] = row["expected_rd_sets"]
        elif tool == "knowledge.resolve_applicable_spds_profile":
            result["formatting_requirements"] = row["formatting_requirements"]
        elif tool == "knowledge.evaluate_pd_rd_completeness":
            result.update(
                {
                    "required_pd_sections": row["required_pd_sections"],
                    "expected_rd_sets": row["expected_rd_sets"],
                    "formatting_requirements": row["formatting_requirements"],
                }
            )
        elif tool == "knowledge.explain_pd_rd_normative_decision":
            result["decision_trace"] = {
                "editions": result["normative_edition_ids"],
                "rules": result["rule_version_ids"],
                "requirements": requirements,
            }
        elif tool == "knowledge.get_pd_rd_normative_gap":
            result = {
                key: result[key]
                for key in (
                    "authority_layer",
                    "profile_id",
                    "profile_version",
                    "corpus_denominator",
                    "unresolved_inputs",
                    "gaps",
                    "completeness_status",
                    "semantic_fingerprint",
                )
            }
        return self._response(tool, status, result, evidence=evidence, gaps=gaps)

    def _resolve_ntd(self, tool: str, payload: dict[str, Any]) -> GatewayResponse:
        raw = str(payload.get("identifier", ""))
        as_of = _required_date(payload, "as_of")
        try:
            identifier = normalize_identifier(raw)
        except ValueError:
            return self._response(
                tool,
                GatewayStatus.NO_RESULT,
                {},
                gaps=(self._gap("invalid_or_unsupported_identifier", raw),),
            )
        with Session(self._engine) as session:
            documents = (
                session.execute(
                    sa.text(
                        "SELECT normative_document_id,designation,title,issuer,jurisdiction,document_class "
                        "FROM platform.normative_documents WHERE designation=:designation"
                    ),
                    {"designation": _stable_designation(identifier.stable_identity_key)},
                )
                .mappings()
                .all()
            )
            seed_gap = (
                session.execute(
                    sa.text(
                        "SELECT o.terminal_status,o.terminal_receipt_id,o.normalized_designation,"
                        "g.gap_code,g.blocker_scope,g.gap_fingerprint "
                        "FROM platform.normative_seed_outcomes o LEFT JOIN platform.ntd_gaps g "
                        "ON g.stable_identity_key=o.stable_identity_key AND g.status='open' "
                        "WHERE o.stable_identity_key=:identity ORDER BY g.version DESC LIMIT 1"
                    ),
                    {"identity": identifier.stable_identity_key},
                )
                .mappings()
                .one_or_none()
            )
            reference_rows = (
                session.execute(
                    sa.text(
                        "SELECT practice_guide_reference_id,practice_guide_edition_id,"
                        "source_version_id,pdf_page,region,raw_designation,source_fragment_digest "
                        "FROM platform.practice_guide_normative_references "
                        "WHERE stable_identity_key=:identity ORDER BY occurrence_ordinal"
                    ),
                    {"identity": identifier.stable_identity_key},
                )
                .mappings()
                .all()
            )
            if len(documents) != 1:
                if not documents and seed_gap is not None:
                    return self._response(
                        tool,
                        GatewayStatus.KNOWLEDGE_GAP,
                        {
                            "authority_layer": "normative_authority",
                            "identifier": identifier.normalized_designation,
                            "official_resolution": _json_row(seed_gap),
                            "practice_guide_references": [
                                _json_row(reference) for reference in reference_rows
                            ],
                            "normative_provision": None,
                            "practice_recommendation": None,
                            "deterministic_rule_version": None,
                            "as_of_decision": {
                                "date": as_of.isoformat(),
                                "status": "unavailable_without_official_edition",
                            },
                        },
                        gaps=(
                            self._gap(
                                str(seed_gap["gap_code"] or seed_gap["terminal_status"]),
                                identifier.stable_identity_key,
                            ),
                        ),
                    )
                status = (
                    GatewayStatus.EDITION_AMBIGUOUS
                    if len(documents) > 1
                    else GatewayStatus.NO_RESULT
                )
                return self._response(
                    tool,
                    status,
                    {},
                    gaps=(self._gap("identity_ambiguous" if documents else "no_result", raw),),
                )
            document = documents[0]
            decisions = (
                session.execute(
                    sa.text(
                        "SELECT d.selected_edition_id,d.version,d.as_of,d.status,e.edition_label,"
                        "e.edition_fingerprint FROM platform.normative_activation_decisions d "
                        "JOIN platform.normative_editions e ON e.normative_edition_id=d.selected_edition_id "
                        "WHERE d.normative_document_id=:document AND d.as_of<=:as_of "
                        "ORDER BY d.as_of DESC,d.version DESC LIMIT 1"
                    ),
                    {"document": document["normative_document_id"], "as_of": as_of},
                )
                .mappings()
                .all()
            )
        if not decisions:
            return self._response(
                tool,
                GatewayStatus.KNOWLEDGE_GAP,
                {"document": _json_row(document), "as_of": as_of.isoformat()},
                gaps=(self._gap("activation_decision_missing", raw),),
            )
        decision = decisions[0]
        return self._response(
            tool,
            GatewayStatus.OK,
            {
                "authority_layer": "normative_authority",
                "document": _json_row(document),
                "edition": _json_row(decision),
                "as_of_decision": {"date": as_of.isoformat(), "explicit": True},
                "practice_recommendation": None,
                "deterministic_rule_version": None,
                "applicability_status": "not_evaluated_for_workspace",
            },
        )

    def _get_document(self, tool: str, payload: dict[str, Any]) -> GatewayResponse:
        document_id = _required_uuid(payload, "document_id")
        with Session(self._engine) as session:
            document = (
                session.execute(
                    sa.text(
                        "SELECT * FROM platform.normative_documents WHERE normative_document_id=:id"
                    ),
                    {"id": document_id},
                )
                .mappings()
                .one_or_none()
            )
            editions = (
                session.execute(
                    sa.text(
                        "SELECT normative_edition_id,edition_label,effective_from,effective_to,"
                        "official_catalog_id,official_catalog_url,edition_fingerprint "
                        "FROM platform.normative_editions WHERE normative_document_id=:id "
                        "ORDER BY effective_from NULLS LAST,edition_label"
                    ),
                    {"id": document_id},
                )
                .mappings()
                .all()
            )
        if document is None:
            return self._response(tool, GatewayStatus.NO_RESULT, {}, gaps=(self._gap("no_result"),))
        return self._response(
            tool,
            GatewayStatus.OK,
            {
                "document": _json_row(document),
                "edition_timeline": [_json_row(row) for row in editions],
            },
        )

    def _get_edition(self, tool: str, payload: dict[str, Any]) -> GatewayResponse:
        edition_id = _required_uuid(payload, "edition_id")
        with Session(self._engine) as session:
            edition = (
                session.execute(
                    sa.text(
                        "SELECT e.*,d.designation,d.title,d.issuer,d.jurisdiction,d.document_class "
                        "FROM platform.normative_editions e JOIN platform.normative_documents d "
                        "ON d.normative_document_id=e.normative_document_id "
                        "WHERE e.normative_edition_id=:id"
                    ),
                    {"id": edition_id},
                )
                .mappings()
                .one_or_none()
            )
            artifacts = (
                session.execute(
                    sa.text(
                        "SELECT normative_artifact_id,source_version_id,official_catalog_id,official_url,"
                        "filename,media_type,size_bytes,content_digest,relation_to_edition "
                        "FROM platform.normative_artifacts WHERE normative_edition_id=:id "
                        "ORDER BY relation_to_edition,official_url"
                    ),
                    {"id": edition_id},
                )
                .mappings()
                .all()
            )
            relationships = (
                session.execute(
                    sa.text(
                        "SELECT relationship_id,from_edition_id,to_edition_id,relation_kind,"
                        "official_evidence_ref,verification_status FROM "
                        "platform.normative_edition_relationships "
                        "WHERE from_edition_id=:id OR to_edition_id=:id ORDER BY relation_kind"
                    ),
                    {"id": edition_id},
                )
                .mappings()
                .all()
            )
        if edition is None:
            return self._response(tool, GatewayStatus.NO_RESULT, {}, gaps=(self._gap("no_result"),))
        if not artifacts:
            return self._response(
                tool,
                GatewayStatus.KNOWLEDGE_GAP,
                {
                    "edition": _json_row(edition),
                    "artifacts": [],
                    "relationships": [_json_row(row) for row in relationships],
                },
                gaps=(self._gap("official_artifact_unavailable", str(edition_id)),),
            )
        return self._response(
            tool,
            GatewayStatus.OK,
            {
                "authority_layer": "normative_authority",
                "edition": _json_row(edition),
                "artifacts": [_json_row(row) for row in artifacts],
                "relationships": [_json_row(row) for row in relationships],
            },
        )

    def _get_provision(self, tool: str, payload: dict[str, Any]) -> GatewayResponse:
        edition_id = _required_uuid(payload, "edition_id")
        locator = str(payload.get("locator", "")).strip()
        if not locator:
            raise ValueError("locator is required")
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    sa.text(
                        "SELECT p.*,a.official_url,a.content_digest AS artifact_digest,"
                        "a.normative_artifact_id,e.edition_label,e.edition_fingerprint,"
                        "sem.modality,sem.uncertainty_codes AS semantic_uncertainty_codes,"
                        "d.designation,d.title FROM platform.normative_provision_versions p "
                        "JOIN platform.normative_artifacts a ON a.source_version_id=p.source_version_id "
                        "JOIN platform.normative_editions e ON e.normative_edition_id="
                        "p.normative_edition_id JOIN platform.normative_documents d ON "
                        "d.normative_document_id=e.normative_document_id "
                        "LEFT JOIN platform.normative_provision_semantics sem ON "
                        "sem.provision_candidate_id=p.provision_candidate_id AND "
                        "sem.candidate_version=p.candidate_version "
                        "WHERE p.normative_edition_id=:edition AND p.structural_path=:locator "
                        "AND p.verification_status='verified' ORDER BY p.version DESC LIMIT 2"
                    ),
                    {"edition": edition_id, "locator": locator},
                )
                .mappings()
                .all()
            )
            source_locators: list[Any] = []
            activation_status: str | None = None
            rule_rows: list[Any] = []
            if len(rows) == 1:
                source_locators = list(
                    session.execute(
                        sa.text(
                            "SELECT ids.ordinality,sl.source_locator_id,sl.locator_value,"
                            "sl.fragment_digest FROM platform.normative_structural_fragments sf "
                            "CROSS JOIN LATERAL unnest(sf.source_locator_ids) WITH ORDINALITY "
                            "ids(locator_id,ordinality) JOIN platform.source_locators sl ON "
                            "sl.source_locator_id=ids.locator_id WHERE sf.structural_unit_id=:unit "
                            "AND sf.source_version_id=:source ORDER BY ids.ordinality"
                        ),
                        {
                            "unit": rows[0]["structural_unit_id"],
                            "source": rows[0]["source_version_id"],
                        },
                    )
                    .mappings()
                    .all()
                )
                if not source_locators:
                    source_locators = list(
                        session.execute(
                            sa.text(
                                "SELECT 1 AS ordinality,sl.source_locator_id,sl.locator_value,"
                                "sl.fragment_digest FROM platform.structural_units su JOIN "
                                "platform.source_locators sl ON sl.source_locator_id="
                                "su.source_locator_id WHERE su.structural_unit_id=:unit"
                            ),
                            {"unit": rows[0]["structural_unit_id"]},
                        )
                        .mappings()
                        .all()
                    )
                activation_status = session.execute(
                    sa.text(
                        "SELECT status FROM platform.normative_activation_decisions WHERE "
                        "selected_edition_id=:edition ORDER BY as_of DESC,version DESC LIMIT 1"
                    ),
                    {"edition": edition_id},
                ).scalar_one_or_none()
                rule_rows = list(
                    session.execute(
                        sa.text(
                            "SELECT candidate.normative_rule_candidate_id,candidate.version "
                            "candidate_version,candidate.deontic_type,candidate.actor,"
                            "candidate.regulated_object,candidate.required_action,"
                            "candidate.applicability_predicate,candidate.output_contract,"
                            "qualification.qualification_decision_id,qualification.status "
                            "qualification_status,qualification.gate_results,"
                            "outcome.status activation_status,outcome.reason_code activation_reason,"
                            "outcome.rule_version_id,outcome.rule_lifecycle_status FROM "
                            "platform.normative_rule_candidates candidate LEFT JOIN LATERAL "
                            "(SELECT q.* FROM platform.normative_rule_qualification_decisions q "
                            "WHERE q.normative_rule_candidate_id="
                            "candidate.normative_rule_candidate_id AND "
                            "q.normative_rule_candidate_version=candidate.version ORDER BY "
                            "q.decided_at DESC,q.version DESC LIMIT 1) qualification ON true "
                            "LEFT JOIN LATERAL (SELECT o.* FROM "
                            "platform.normative_rule_activation_outcomes o WHERE "
                            "o.normative_rule_candidate_id=candidate.normative_rule_candidate_id "
                            "AND o.normative_rule_candidate_version=candidate.version ORDER BY "
                            "o.decided_at DESC,o.version DESC LIMIT 1) outcome ON true WHERE "
                            "candidate.normative_provision_id=:provision AND "
                            "candidate.normative_provision_version=:version ORDER BY "
                            "candidate.normative_rule_candidate_id,candidate.version"
                        ),
                        {
                            "provision": rows[0]["normative_provision_id"],
                            "version": rows[0]["version"],
                        },
                    )
                    .mappings()
                    .all()
                )
        if len(rows) != 1:
            status = GatewayStatus.NORMATIVE_CONFLICT if len(rows) > 1 else GatewayStatus.NO_RESULT
            return self._response(
                tool,
                status,
                {},
                gaps=(
                    self._gap("conflicting_verified_versions" if rows else "no_result", locator),
                ),
            )
        row = rows[0]
        evidence = tuple(
            EvidenceItem(
                evidence_link_id=(
                    f"ntd:{row['normative_provision_id']}:{row['version']}:"
                    f"{locator_row['source_locator_id']}"
                ),
                source_version_id=str(row["source_version_id"]),
                edition_id=str(row["normative_edition_id"]),
                structural_unit_locator=_exact_locator(
                    str(row["structural_path"]), locator_row["locator_value"]
                ),
                content_digest=str(locator_row["fragment_digest"]),
                access_reference=str(row["official_url"]),
                authority_layer="normative_authority",
            )
            for locator_row in source_locators
        )
        if not evidence:
            return self._response(
                tool,
                GatewayStatus.KNOWLEDGE_GAP,
                {},
                gaps=(self._gap("verified_provision_locator_missing", locator),),
            )
        active_rules = [row for row in rule_rows if row["activation_status"] == "active"]
        rule_gaps = tuple(
            self._gap(
                str(row["activation_reason"] or "rule_activation_decision_missing"),
                str(row["normative_rule_candidate_id"]),
            )
            for row in rule_rows
            if row["activation_status"] != "active"
        )
        if not rule_rows:
            rule_gaps = (self._gap("verified_provision_rule_candidate_missing", locator),)
        return self._response(
            tool,
            GatewayStatus.OK,
            {
                "authority_layer": "normative_authority",
                "provision": _json_row(row),
                "source_locators": [_json_row(value) for value in source_locators],
                "edition_activation_status": activation_status or "not_activated",
                "applicability_status": "not_evaluated_for_workspace",
                "practice_recommendation": None,
                "rule_candidates": [_json_row(value) for value in rule_rows],
                "deterministic_rule_version": (
                    _json_row(active_rules[0]) if len(active_rules) == 1 else None
                ),
            },
            evidence=evidence,
            gaps=rule_gaps,
        )

    def _search(self, tool: str, payload: dict[str, Any]) -> GatewayResponse:
        query = str(payload.get("query", "")).strip()
        edition_scope = payload.get("edition_scope")
        if not query or edition_scope is None:
            raise ValueError("search_ntd requires query and exact edition_scope")
        edition_ids = tuple(UUID(str(value)) for value in edition_scope)
        if not edition_ids:
            return self._response(
                tool, GatewayStatus.KNOWLEDGE_GAP, {}, gaps=(self._gap("empty_edition_scope"),)
            )
        with Session(self._engine) as session:
            projection = session.execute(
                sa.text(
                    "SELECT lexical_version_id FROM projection.ntd_lexical_versions "
                    "WHERE status='ready' ORDER BY built_at DESC LIMIT 1"
                )
            ).scalar_one_or_none()
            if projection is None:
                return self._response(
                    tool,
                    GatewayStatus.INDEX_UNAVAILABLE,
                    {},
                    gaps=(self._gap("projection_unavailable"),),
                )
            rows = (
                session.execute(
                    sa.text(
                        "SELECT normative_provision_id,normative_provision_version,normative_edition_id,"
                        "structural_path,verbatim_text FROM projection.ntd_lexical_entries "
                        "WHERE lexical_version_id=:version AND normative_edition_id=ANY(:editions) "
                        "AND search_vector @@ plainto_tsquery('russian',:query) "
                        "ORDER BY ts_rank(search_vector,plainto_tsquery('russian',:query)) DESC "
                        "LIMIT 20"
                    ),
                    {"version": projection, "editions": list(edition_ids), "query": query},
                )
                .mappings()
                .all()
            )
        if not rows:
            return self._response(
                tool, GatewayStatus.NO_RESULT, {}, gaps=(self._gap("no_result", query),)
            )
        return self._response(
            tool,
            GatewayStatus.OK,
            {
                "results": [_json_row(row) for row in rows],
                "edition_scope": [str(value) for value in edition_ids],
            },
        )

    def _get_evidence_pack(self, tool: str, payload: dict[str, Any]) -> GatewayResponse:
        return self._get_provision(tool, payload)

    def _get_alignment(self, tool: str, payload: dict[str, Any]) -> GatewayResponse:
        guidance_id = _required_uuid(payload, "guidance_unit_id")
        as_of = _required_date(payload, "as_of")
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    sa.text(
                        "SELECT * FROM platform.practice_ntd_alignments "
                        "WHERE guidance_unit_id=:guidance AND as_of<=:as_of "
                        "ORDER BY as_of DESC,version DESC"
                    ),
                    {"guidance": guidance_id, "as_of": as_of},
                )
                .mappings()
                .all()
            )
        if not rows:
            return self._response(
                tool,
                GatewayStatus.KNOWLEDGE_GAP,
                {},
                gaps=(self._gap("practice_ntd_alignment_missing", str(guidance_id)),),
            )
        if any(row["alignment_status"] == "normative_conflict" for row in rows):
            return self._response(
                tool,
                GatewayStatus.GUIDANCE_NORMATIVE_CONFLICT,
                {"alignments": [_json_row(row) for row in rows]},
                conflicts=tuple(
                    _json_row(row)
                    for row in rows
                    if row["alignment_status"] == "normative_conflict"
                ),
            )
        selected = rows[0]
        with Session(self._engine) as session:
            guidance = (
                session.execute(
                    sa.text(
                        "SELECT guidance_unit_id,version,practice_guide_edition_id,guidance_kind,"
                        "normalized_instruction,topic,recommended_practice,authority_layer,"
                        "integrity_digest FROM platform.practice_guidance_units WHERE "
                        "guidance_unit_id=:guidance AND version=:version"
                    ),
                    {
                        "guidance": selected["guidance_unit_id"],
                        "version": selected["guidance_unit_version"],
                    },
                )
                .mappings()
                .one_or_none()
            )
            guidance_evidence = (
                session.execute(
                    sa.text(
                        "SELECT guidance_evidence_id,source_version_id,source_locator_id,"
                        "page_number,region,fragment_digest,evidence_role FROM "
                        "platform.practice_guidance_evidence WHERE guidance_unit_id=:guidance "
                        "AND guidance_unit_version=:version ORDER BY evidence_role,source_locator_id"
                    ),
                    {
                        "guidance": selected["guidance_unit_id"],
                        "version": selected["guidance_unit_version"],
                    },
                )
                .mappings()
                .all()
            )
        if guidance is None or not guidance_evidence:
            return self._response(
                tool,
                GatewayStatus.KNOWLEDGE_GAP,
                {"alignments": [_json_row(row) for row in rows]},
                gaps=(self._gap("practice_guidance_evidence_missing", str(guidance_id)),),
            )
        if (
            selected["normative_provision_id"] is None
            or selected["normative_provision_version"] is None
            or selected["normative_edition_id"] is None
        ):
            return self._response(
                tool,
                GatewayStatus.KNOWLEDGE_GAP,
                {"alignments": [_json_row(row) for row in rows]},
                gaps=(self._gap("alignment_exact_provision_missing", str(guidance_id)),),
            )
        normative = self._get_provision(
            "knowledge.get_ntd_provision",
            {
                "edition_id": str(selected["normative_edition_id"]),
                "locator": _alignment_provision_locator(self._engine, selected),
            },
        )
        if normative.status is not GatewayStatus.OK:
            return self._response(
                tool,
                normative.status,
                {"alignments": [_json_row(row) for row in rows]},
                gaps=normative.evidence_pack.gaps,
                conflicts=normative.evidence_pack.conflicts,
            )
        practice_evidence = tuple(
            EvidenceItem(
                evidence_link_id=f"practice:{value['guidance_evidence_id']}",
                source_version_id=str(value["source_version_id"]),
                edition_id=str(guidance["practice_guide_edition_id"]),
                structural_unit_locator=_exact_locator(
                    f"practice:{guidance['guidance_unit_id']}:{guidance['version']}",
                    {"page": value["page_number"], "region": value["region"]},
                ),
                content_digest=str(value["fragment_digest"]),
                access_reference=(
                    f"practice-guide-edition:{guidance['practice_guide_edition_id']}"
                ),
                authority_layer="methodological_guidance",
            )
            for value in guidance_evidence
        )
        status = (
            GatewayStatus.KNOWLEDGE_INCOMPLETE
            if selected["alignment_status"] == "edition_warning"
            else GatewayStatus.OK
        )
        alignment_gaps = (
            (
                self._gap(
                    "normative_edition_activation_not_qualified",
                    str(selected["normative_edition_id"]),
                ),
            )
            if status is GatewayStatus.KNOWLEDGE_INCOMPLETE
            else ()
        )
        gaps = normative.evidence_pack.gaps + alignment_gaps
        return self._response(
            tool,
            status,
            {
                "authority_layers": {
                    "practice_intelligence": _json_row(guidance),
                    "normative_authority": normative.result,
                    "deterministic_rule_version": normative.result.get(
                        "deterministic_rule_version"
                    ),
                    "workspace_fact": None,
                    "customer_addition": None,
                    "ai_candidate": None,
                },
                "alignments": [_json_row(row) for row in rows],
            },
            evidence=practice_evidence + normative.evidence_pack.evidence,
            gaps=gaps,
        )

    @staticmethod
    def _gap(code: str, subject: str | None = None) -> dict[str, Any]:
        return {"code": code, "subject": subject, "authority_layer": "normative_authority"}

    @staticmethod
    def _response(
        tool: str,
        status: GatewayStatus,
        result: dict[str, Any],
        *,
        evidence: tuple[EvidenceItem, ...] = (),
        gaps: tuple[dict[str, Any], ...] = (),
        conflicts: tuple[dict[str, Any], ...] = (),
    ) -> GatewayResponse:
        return GatewayResponse(
            tool=tool,
            contract_version=(
                PD_RD_NTD_CONTRACT_VERSION if tool in PD_RD_NTD_TOOLS else NTD_CONTRACT_VERSION
            ),
            status=status,
            result=result,
            evidence_pack=EvidencePack(
                evidence=evidence,
                applicability=(),
                conflicts=conflicts,
                gaps=gaps,
                uncertainties=(),
            ),
        )


def _required_uuid(payload: dict[str, Any], key: str) -> UUID:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    return UUID(str(value))


def _required_date(payload: dict[str, Any], key: str) -> date:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} is required")
    return date.fromisoformat(value)


def _json_row(row: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in dict(row).items():
        if isinstance(value, (UUID, date)):
            result[str(key)] = value.isoformat() if isinstance(value, date) else str(value)
        else:
            result[str(key)] = value
    return result


def _stable_designation(stable_identity_key: str) -> str:
    parts = stable_identity_key.split(":")
    if len(parts) < 3:
        return stable_identity_key
    namespace = parts[1]
    value = ":".join(parts[2:])
    if namespace == "sp":
        return f"СП {value}"
    if namespace == "gost-r":
        return f"ГОСТ Р {value}"
    if namespace == "gost":
        return f"ГОСТ {value}"
    if namespace == "minstroy" and value.startswith("order:"):
        order_parts = value.removeprefix("order:").split(":")
        if len(order_parts) == 2:
            issued, number = order_parts
            return (
                f"ПРИКАЗ МИНСТРОЯ РОССИИ № {number.replace('-pr', '/ПР')} "
                f"ОТ {issued[8:10]}.{issued[5:7]}.{issued[:4]}"
            )
        return stable_identity_key
    if namespace == "instruction":
        return f"И {value}"
    return stable_identity_key


def _exact_locator(structural_path: str, locator_value: Any) -> str:
    page = int(locator_value["page"])
    region = ",".join(f"{float(value):.12f}" for value in locator_value["region"])
    return f"{structural_path}#page={page};region={region}"


def _alignment_provision_locator(engine: Engine, alignment: Any) -> str:
    with Session(engine) as session:
        value = session.execute(
            sa.text(
                "SELECT structural_path FROM platform.normative_provision_versions WHERE "
                "normative_provision_id=:provision AND version=:version"
            ),
            {
                "provision": alignment["normative_provision_id"],
                "version": alignment["normative_provision_version"],
            },
        ).scalar_one_or_none()
    if value is None:
        raise ValueError("alignment provision pin is missing")
    return str(value)
