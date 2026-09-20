"""Bounded Knowledge Gateway context for the professional assistant."""

# ruff: noqa: E501, RUF001 -- SQL clauses, URLs and Russian query terms stay readable.

from __future__ import annotations

import re
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid
from asd_kontur.knowledge.gateway import (
    ASSISTANT_CONTRACT_VERSION,
    EvidenceItem,
    EvidencePack,
    GatewayContext,
    GatewayResponse,
    GatewayStatus,
)
from asd_kontur.ntd.search_corpus import normalize_designation
from asd_kontur.support.production_postgres import SupportProductionRepository

from .engineering_gateway import execute_early_strength
from .reasoning import TOOL_NAMES

ASSISTANT_TOOL = "knowledge.get_professional_assistant_context"
ASSISTANT_REASONING_TOOLS = TOOL_NAMES

PLATFORM_CONSULTANT_TOOLS = frozenset(
    {
        "consultant.search_practice",
        "consultant.get_practice_fragment",
        "consultant.get_ntd_inventory",
        "consultant.resolve_ntd_designation",
        "consultant.search_ntd_documents",
        "consultant.search_ntd_content",
        "consultant.get_ntd_page",
        "consultant.get_ntd_section_context",
        "consultant.get_verified_provisions",
        "consultant.get_ntd_processing_status",
        "consultant.search_ntd",
        "consultant.get_ntd_provision",
    }
)


class ProfessionalAssistantKnowledgeQuery:
    """Consultant-only allowlisted reads; the model never receives SQL access."""

    def __init__(
        self,
        engine: Engine,
        *,
        production_embedding_endpoint: str | None = None,
    ) -> None:
        self._engine = engine
        if production_embedding_endpoint is not None:
            if (
                not isinstance(production_embedding_endpoint, str)
                or production_embedding_endpoint == ""
                or not (
                    production_embedding_endpoint.startswith("http://127.0.0.1:")
                    or production_embedding_endpoint.startswith("http://localhost:")
                )
            ):
                raise ValueError("assistant_production_embedding_endpoint_invalid")
        self._production_embedding_endpoint = production_embedding_endpoint

    def memory_fingerprint(self) -> str:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    sa.text(
                        "SELECT (SELECT count(*) FROM platform.practice_intelligence_units) practice,"
                        "(SELECT count(*) FROM platform.normative_provision_versions WHERE "
                        "verification_status='verified') normative,"
                        "(SELECT count(*) FROM platform.ntd_search_documents) ntd_search_documents,"
                        "(SELECT coalesce(max(build_fingerprint),'') FROM "
                        "platform.ntd_search_index_build_receipts) ntd_search_build,"
                        "(SELECT coalesce(max(version),0) FROM "
                        "platform.practice_intelligence_releases) release_version"
                    )
                )
                .mappings()
                .one()
            )
        return semantic_digest(dict(row))

    def execute(
        self, tool: str, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        if tool == ASSISTANT_TOOL:
            return self._legacy_context(payload, context)
        if tool not in ASSISTANT_REASONING_TOOLS:
            raise ValueError("assistant_gateway_tool_not_supported")
        if tool == "consultant.estimate_concrete_early_strength":
            return execute_early_strength(payload)
        if tool in PLATFORM_CONSULTANT_TOOLS:
            mode = ""
        else:
            if context.organization_id is None or context.workspace_id is None:
                raise PermissionError("assistant_workspace_scope_required")
            mode = _mode(payload)
        organization_id = cast(UUID, context.organization_id)
        workspace_id = cast(UUID, context.workspace_id)
        result: dict[str, Any]
        if tool == "consultant.search_practice":
            query, limit = _search_arguments(payload, maximum=8)
            result = self._tool_result(tool, self._practice_context(query, limit))
        elif tool == "consultant.get_practice_fragment":
            result = self._tool_result(tool, self._practice_fragment(_source_id(payload)))
        elif tool == "consultant.get_ntd_inventory":
            result = self._plain_tool_result(tool, self._ntd_inventory())
        elif tool == "consultant.resolve_ntd_designation":
            result = self._resolve_ntd_designation(str(payload.get("designation", "")))
        elif tool == "consultant.search_ntd_documents":
            query, limit = _search_arguments(payload, maximum=10)
            result = self._tool_result(tool, self._search_ntd_documents(query, limit))
        elif tool == "consultant.search_ntd_content":
            payload_copy = dict(payload)
            raw_scope = payload_copy.pop("search_document_id", None)
            document_id: UUID | None = None
            if raw_scope is not None:
                try:
                    document_id = UUID(str(raw_scope))
                except ValueError as exc:
                    raise ValueError("assistant_tool_search_invalid") from exc
            query, limit = _search_arguments(payload_copy, maximum=8)
            result = self._tool_result(tool, self._search_ntd_content(query, limit, document_id))
        elif tool == "consultant.get_ntd_page":
            result = self._tool_result(tool, self._get_ntd_pages(payload, radius=0))
        elif tool == "consultant.get_ntd_section_context":
            radius = payload.get("radius", 1)
            if not isinstance(radius, int) or not 1 <= radius <= 2:
                raise ValueError("assistant_tool_radius_invalid")
            result = self._tool_result(tool, self._get_ntd_pages(payload, radius=radius))
        elif tool == "consultant.get_verified_provisions":
            result = self._verified_provisions_for_document(payload)
        elif tool == "consultant.get_ntd_processing_status":
            result = self._ntd_processing_status(payload)
        elif tool == "consultant.find_applicability_candidates":
            query, limit = _search_arguments(payload, maximum=8)
            result = self._applicability_candidates(
                organization_id, workspace_id, mode, query, limit
            )
        elif tool == "consultant.search_ntd":
            query, limit = _search_arguments(payload, maximum=8)
            result = self._tool_result(tool, self._normative_context(query, limit))
        elif tool == "consultant.get_ntd_provision":
            result = self._tool_result(tool, self._normative_provision(_source_id(payload)))
        elif tool == "consultant.search_workspace_documents":
            query, limit = _search_arguments(payload, maximum=10)
            result = self._tool_result(
                tool,
                self._workspace_search(organization_id, workspace_id, mode, query, limit),
            )
        elif tool == "consultant.get_workspace_fragment":
            result = self._tool_result(
                tool,
                self._workspace_fragment(
                    organization_id,
                    workspace_id,
                    mode,
                    _source_id(payload),
                ),
            )
        elif tool == "consultant.get_id_package":
            view = SupportProductionRepository(self._engine).view(
                owner_identity_id=context.actor_identity_id,
                workspace_id=workspace_id,
            )
            result = self._plain_tool_result(
                tool,
                _public_value(view),
                _canonical_workspace_sources(view, workspace_id, mode, "Комплект ИД"),
            )
        else:
            workspace = self._workspace_context(
                organization_id,
                workspace_id,
                mode,
                "",
                owner_identity_id=context.actor_identity_id,
            )
            selected = {
                "consultant.get_workspace_overview": {
                    "name": workspace["name"],
                    "project_definition": workspace["project_definition"],
                    "documents": workspace["documents"],
                    "structure_dossiers": workspace["structure_dossiers"],
                    "structure_identity_candidates": workspace.get(
                        "structure_identity_candidates", []
                    ),
                    "materialization": workspace["materialization"],
                    "semantic_coverage": workspace.get("semantic_coverage", []),
                    "candidate_summary": workspace.get("candidate_summary", {}),
                },
                "consultant.get_work_packages": {"work_packages": workspace["work_packages"]},
                "consultant.get_requirement_matrix": {
                    "requirement_matrix": workspace["requirement_matrix"]
                },
                "consultant.get_discrepancies": {"discrepancies": workspace["discrepancies"]},
                "consultant.get_mode_result": {"mode_result": workspace["mode_result"]},
                "consultant.get_information_gaps": {
                    "project_definition": workspace["project_definition"],
                    "discrepancies": workspace["discrepancies"],
                    "mode_result": workspace["mode_result"],
                    "materialization": workspace["materialization"],
                    "semantic_coverage": workspace.get("semantic_coverage", []),
                },
            }[tool]
            selected_sources = {
                "consultant.get_workspace_overview": workspace.get("overview_source_items", []),
                "consultant.get_work_packages": workspace.get("work_package_source_items", []),
                "consultant.get_requirement_matrix": workspace.get("work_package_source_items", []),
                "consultant.get_discrepancies": workspace.get("discrepancy_source_items", []),
                "consultant.get_mode_result": workspace.get("overview_source_items", []),
                "consultant.get_information_gaps": workspace.get("gap_source_items", []),
            }[tool]
            result = self._plain_tool_result(
                tool,
                selected,
                [dict(item["source"]) for item in selected_sources],
            )
        sources = tuple(dict(item) for item in result.pop("sources", []))
        evidence = tuple(_evidence(item) for item in sources)
        gaps = tuple(result.get("gaps", []))
        return GatewayResponse(
            tool,
            ASSISTANT_CONTRACT_VERSION,
            GatewayStatus.OK
            if result["outcome"]
            not in {"not_found", "document_not_present", "document_present_no_text"}
            else GatewayStatus.NO_RESULT,
            {**result, "sources": list(sources)},
            EvidencePack(evidence, (), (), gaps, ()),
        )

    def _legacy_context(self, payload: dict[str, Any], context: GatewayContext) -> GatewayResponse:
        if context.organization_id is None or context.workspace_id is None:
            raise PermissionError("assistant_workspace_scope_required")
        query = " ".join(str(payload.get("query", "")).split())
        mode = str(payload.get("mode", ""))
        if len(query) < 2 or mode not in {"Tender", "Support", "Audit", "Restoration"}:
            raise ValueError("assistant_context_request_invalid")
        workspace = self._workspace_context(
            context.organization_id,
            context.workspace_id,
            mode,
            query,
            owner_identity_id=context.actor_identity_id,
        )
        search_query = _search_query(query)
        practice = self._practice_context(search_query, 4)
        # The platform production projection is the normative retrieval path when
        # an embedding endpoint is configured for this application process.  Keep
        # the verified-provision query only as the explicit no-embedding fallback:
        # it cannot provide the same hybrid FTS/dense/graph evidence as the
        # production query used by the platform consultant.
        normative = (
            self._search_ntd_content(query, 4)
            if self._production_embedding_endpoint is not None
            else self._normative_context(search_query, 4)
        )
        sources = tuple(
            [item["source"] for item in workspace["source_items"]]
            + [item["source"] for item in practice]
            + [item["source"] for item in normative]
        )
        evidence = tuple(
            EvidenceItem(
                str(item["source_id"]),
                str(item.get("source_version_id") or item["source_id"]),
                str(item["edition_id"]) if item.get("edition_id") else None,
                str(item["locator_label"]),
                str(item["content_digest"]),
                str(item["href"]),
                str(item["authority_layer"]),
            )
            for item in sources
        )
        gaps: list[dict[str, Any]] = []
        if not workspace["project_definition"]:
            gaps.append({"code": "project_model_unavailable"})
        if not practice:
            gaps.append({"code": "practice_guidance_not_found_for_query"})
        if not normative:
            gaps.append({"code": "normative_fragment_not_found_for_query"})
        result = {
            "contract": "professional-assistant-context@2.8.0",
            "mode": mode,
            "workspace": {key: value for key, value in workspace.items() if key != "source_items"},
            "methodological_practice": [item["content"] for item in practice],
            "normative_authority": [item["content"] for item in normative],
            "sources": list(sources),
            "gaps": gaps,
            "authority_policy": {
                "methodological_practice": "recommendation_not_normative_requirement",
                "normative_authority": "edition_currency_not_checked",
                "workspace": "current_workspace_only",
                "automatic_actions": "forbidden_without_user_confirmation",
            },
        }
        return GatewayResponse(
            ASSISTANT_TOOL,
            ASSISTANT_CONTRACT_VERSION,
            GatewayStatus.KNOWLEDGE_INCOMPLETE if gaps else GatewayStatus.OK,
            result,
            EvidencePack(evidence, (), (), tuple(gaps), ()),
        )

    @staticmethod
    def _tool_result(tool: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        sources = [dict(item["source"]) for item in items]
        return {
            "contract": "construction-consultant-tools@2.8.0",
            "tool": tool,
            "outcome": "found" if items else "not_found",
            "items": [dict(item["content"]) for item in items],
            "sources": sources,
            "gaps": [] if items else [{"code": "no_relevant_result"}],
        }

    @staticmethod
    def _plain_tool_result(
        tool: str, value: Any, sources: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        found = value not in (None, {}, [], ())
        return {
            "contract": "construction-consultant-tools@2.8.0",
            "tool": tool,
            "outcome": "found" if found else "not_found",
            "value": value,
            "sources": list(sources or []),
            "gaps": [] if found else [{"code": "no_relevant_result"}],
        }

    def _workspace_context(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        mode: str,
        query: str,
        *,
        owner_identity_id: str | None = None,
    ) -> dict[str, Any]:
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            workspace = (
                session.execute(
                    sa.text(
                        "SELECT c.display_name FROM workspace.workspaces w JOIN "
                        "organization.construction_objects c ON c.organization_id=w.organization_id "
                        "AND c.construction_object_id=w.construction_object_id WHERE "
                        "w.organization_id=:o AND w.workspace_id=:w"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one()
            )
            project = (
                session.execute(
                    sa.text(
                        "SELECT project_definition_id,version,purpose,object_class,definition,fingerprint "
                        "FROM workspace.project_definition_versions WHERE organization_id=:o AND "
                        "workspace_id=:w ORDER BY created_at DESC,version DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            packages = list(
                session.execute(
                    sa.text(
                        "WITH current_reconciliation AS (SELECT reconciliation_id,version FROM "
                        "workspace.project_understanding_reconciliations WHERE organization_id=:o "
                        "AND workspace_id=:w ORDER BY recorded_at DESC,reconciliation_id DESC LIMIT 1) "
                        "SELECT package.work_package_id,package.version,package.work_type_key,"
                        "package.package FROM current_reconciliation current JOIN "
                        "workspace.project_reconciliation_work_package_memberships member ON "
                        "member.organization_id=:o AND member.workspace_id=:w AND "
                        "member.reconciliation_id=current.reconciliation_id AND "
                        "member.reconciliation_version=current.version JOIN "
                        "workspace.construction_work_package_versions package ON "
                        "package.organization_id=member.organization_id AND "
                        "package.workspace_id=member.workspace_id AND "
                        "package.work_package_id=member.work_package_id AND "
                        "package.version=member.work_package_version ORDER BY "
                        "member.member_sequence LIMIT 20"
                    ),
                    {"o": organization_id, "w": workspace_id},
                ).mappings()
            )
            matrix = (
                session.execute(
                    sa.text(
                        "SELECT matrix_id,version,matrix,fingerprint FROM "
                        "workspace.work_requirement_matrix_versions WHERE organization_id=:o AND "
                        "workspace_id=:w ORDER BY created_at DESC,version DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            defects = list(
                session.execute(
                    sa.text(
                        "SELECT defect_id,version,defect_kind,subject_identity,related_identity,"
                        "source_locator_ids,parameters,blocking,status FROM "
                        "workspace.project_reconciliation_defects WHERE organization_id=:o AND "
                        "workspace_id=:w ORDER BY recorded_at DESC LIMIT 30"
                    ),
                    {"o": organization_id, "w": workspace_id},
                ).mappings()
            )
            result = (
                session.execute(
                    sa.text(
                        "SELECT result_id,version,result_payload,unresolved_questions,status FROM "
                        "workspace.pilot_mode_result_versions WHERE organization_id=:o AND "
                        "workspace_id=:w AND mode=:mode ORDER BY formed_at DESC,version DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id, "mode": mode},
                )
                .mappings()
                .one_or_none()
            )
            documents = list(
                session.execute(
                    sa.text(
                        "SELECT DISTINCT ON (v.document_id) v.document_id,v.version,v.source_version_id,"
                        "v.safe_display_name,v.media_type,v.content_digest,s.admission_status,"
                        "s.extraction_status,s.page_count FROM workspace.document_versions v JOIN "
                        "workspace.document_processing_states s ON s.organization_id=v.organization_id "
                        "AND s.workspace_id=v.workspace_id AND s.document_id=v.document_id AND "
                        "s.document_version=v.version WHERE v.organization_id=:o AND v.workspace_id=:w "
                        "ORDER BY v.document_id,v.version DESC,s.state_sequence DESC LIMIT 100"
                    ),
                    {"o": organization_id, "w": workspace_id},
                ).mappings()
            )
        source_items = (
            self._workspace_search(
                organization_id,
                workspace_id,
                mode,
                query,
                6,
            )
            if query
            else []
        )
        model_view: dict[str, Any] | None = None
        dossier_source_items: list[dict[str, Any]] = []
        work_package_source_items: list[dict[str, Any]] = []
        discrepancy_source_items: list[dict[str, Any]] = []
        overview_dossiers: list[dict[str, Any]] = []
        overview_identities: list[dict[str, Any]] = []
        if owner_identity_id is not None:
            from asd_kontur.application_spine.postgres import SpinePostgresRepository

            model_view = SpinePostgresRepository(self._engine).project_understanding_view(
                owner_identity_id=owner_identity_id, workspace_id=workspace_id
            )
            overview_dossiers = list((model_view or {}).get("structure_dossiers", []))[:30]
            overview_identities = list((model_view or {}).get("structure_identity_candidates", []))[
                :30
            ]
            evidence_index = dict((model_view or {}).get("evidence_index", {}))

            def evidence_items(locator_ids: set[str]) -> list[dict[str, Any]]:
                return [
                    self._workspace_item(evidence_row, workspace_id, mode)
                    for locator_id in sorted(locator_ids)[:30]
                    if (evidence_row := evidence_index.get(locator_id)) is not None
                ]

            dossier_source_items = evidence_items(
                {
                    str(locator_id)
                    for dossier in overview_dossiers
                    for locator_id in dossier.get("source_locator_ids", [])
                }
                | {
                    str(locator_id)
                    for identity in overview_identities
                    for locator_id in identity.get("source_locator_ids", [])
                }
            )
            work_package_source_items = evidence_items(
                {
                    str(locator_id)
                    for row in packages
                    for locator_id in dict(row["package"]).get("source_locator_ids", [])
                }
            )
            discrepancy_source_items = evidence_items(
                {str(locator_id) for row in defects for locator_id in row["source_locator_ids"]}
            )
        gap_source_items = [
            *dossier_source_items,
            *work_package_source_items,
            *discrepancy_source_items,
        ][:30]
        return {
            "workspace_id": str(workspace_id),
            "name": str(workspace["display_name"]),
            "project_definition": _public_value(_json_row(project)),
            "work_packages": _public_value([_json_row(row) for row in packages]),
            "requirement_matrix": _public_value(_matrix_with_work_names(matrix, packages)),
            "discrepancies": _public_value([_json_row(row) for row in defects]),
            "mode_result": _public_value(_mode_result_row(result)),
            "documents": _public_value([_json_row(row) for row in documents]),
            "structure_dossiers": _public_value(overview_dossiers),
            "structure_identity_candidates": _public_value(overview_identities),
            "materialization": _public_value(dict((model_view or {}).get("materialization", {}))),
            "semantic_coverage": _public_value(
                list((model_view or {}).get("semantic_coverage", []))
            ),
            "candidate_summary": {
                "authority": "candidate_only",
                "counts": {
                    key: len(value)
                    for key, value in dict((model_view or {}).get("candidates", {})).items()
                },
                "structure_candidate_count": len(
                    list((model_view or {}).get("structure_nodes", []))
                ),
                "relationship_candidate_count": len(
                    list((model_view or {}).get("structure_relationships", []))
                ),
                "cross_source_identity_candidate_count": len(overview_identities),
                "meaning": "Извлечённые кандидаты не являются подтверждёнными фактами или полным перечнем.",
            },
            "source_items": [*source_items, *dossier_source_items],
            "overview_source_items": dossier_source_items,
            "work_package_source_items": work_package_source_items,
            "discrepancy_source_items": discrepancy_source_items,
            "gap_source_items": gap_source_items,
        }

    def _practice_context(self, query: str, limit: int) -> list[dict[str, Any]]:
        search_query = _search_query(query)
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "SELECT * FROM (SELECT u.intelligence_unit_id,u.version,u.title,u.instruction,u.rationale,"
                        "u.applicability_conditions,s.source_version_id,s.source_locator_id,s.page_number,"
                        "s.fragment_digest,a.title source_title,ts_rank_cd(to_tsvector('russian',u.title||' '||"
                        "u.instruction||' '||coalesce(u.rationale,'')),websearch_to_tsquery('russian',:query)) rank,"
                        "row_number() OVER (PARTITION BY u.title,u.instruction ORDER BY u.version DESC) rn "
                        "FROM platform.practice_intelligence_units u "
                        "JOIN platform.practice_intelligence_sources s ON s.intelligence_unit_id=u.intelligence_unit_id "
                        "AND s.intelligence_unit_version=u.version JOIN platform.source_versions sv ON "
                        "sv.source_version_id=s.source_version_id JOIN platform.source_artifacts a ON "
                        "a.source_artifact_id=sv.source_artifact_id WHERE "
                        "to_tsvector('russian',u.title||' '||u.instruction||' '||coalesce(u.rationale,'')) "
                        "@@ websearch_to_tsquery('russian',:query)) ranked WHERE rn=1 ORDER BY rank DESC,"
                        "intelligence_unit_id LIMIT :limit"
                    ),
                    {"query": search_query, "limit": limit},
                ).mappings()
            )
        return [
            {
                "content": {
                    "title": str(row["title"]),
                    "instruction": str(row["instruction"]),
                    "rationale": str(row["rationale"] or ""),
                    "applicability": row["applicability_conditions"],
                    "authority": "methodological_practice",
                },
                "source": {
                    "source_id": str(row["source_locator_id"]),
                    "source_version_id": str(row["source_version_id"]),
                    "authority_layer": "methodological_practice",
                    "title": _practice_source_title(str(row["source_title"])),
                    "edition": None,
                    "page": int(row["page_number"]),
                    "locator_label": f"раздел пособия, страница {row['page_number']}",
                    "fragment": str(row["instruction"])[:500],
                    "content_digest": str(row["fragment_digest"]),
                    "href": f"/api/v1/platform/sources/{row['source_version_id']}/content#page={row['page_number']}",
                    "edition_currency_notice": None,
                },
            }
            for row in rows
        ]

    def _ntd_inventory(self) -> dict[str, Any]:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    sa.text(
                        "SELECT count(*) document_count,"
                        "count(*) FILTER (WHERE authority_class='official') official_count,"
                        "count(*) FILTER (WHERE authority_class='legacy_reference') reference_count,"
                        "count(*) FILTER (WHERE bytes_status='present') bytes_present_count,"
                        "count(*) FILTER (WHERE search_status='searchable') searchable_count,"
                        "count(*) FILTER (WHERE search_status='partially_searchable') partially_searchable_count,"
                        "count(*) FILTER (WHERE structure_status IN ('structured','verified_provisions')) structured_count,"
                        "sum(verified_provision_count) verified_provision_count,"
                        "count(*) FILTER (WHERE text_status='none') without_text_count,"
                        "count(*) FILTER (WHERE edition_currency_status='not_checked') currency_unchecked_count "
                        "FROM platform.ntd_search_documents"
                    )
                )
                .mappings()
                .one()
            )
            identity_count = int(
                connection.scalar(
                    sa.text(
                        "SELECT coalesce(max(identity_count),0) FROM platform.ntd_seed_manifests"
                    )
                )
                or 0
            )
        return {
            **{key: int(value or 0) for key, value in row.items()},
            "catalog_identity_count": identity_count,
            "absent_identity_count": max(0, identity_count - int(row["official_count"] or 0)),
            "meaning": {
                "verified_provision_count": "Проверенные положения, а не число документов",
                "legacy_reference": "Справочный recovered-текст без полномочий active authority",
            },
        }

    def _resolve_ntd_designation(self, designation: str) -> dict[str, Any]:
        requested = " ".join(designation.split())
        normalized = normalize_designation(requested)
        if len(normalized) < 3:
            raise ValueError("assistant_ntd_designation_invalid")
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "SELECT * FROM platform.ntd_search_documents ORDER BY "
                        "CASE WHEN normalized_designation=:normalized THEN 0 ELSE 1 END,"
                        "authority_class,stable_designation"
                    ),
                    {"normalized": normalized},
                ).mappings()
            )
        matches = [
            row
            for row in rows
            if normalized == str(row["normalized_designation"])
            or (
                normalized.isdigit()
                and normalized == re.sub(r"\D", "", str(row["normalized_designation"]))
            )
            or normalized
            in {normalize_designation(str(alias)) for alias in row["alternative_designations"]}
        ]
        if not matches:
            canonical = self._canonical_ntd_documents()
            canonical_matches = [
                row
                for row in canonical
                if normalized == normalize_designation(str(row["stable_designation"]))
                or (
                    normalized.isdigit()
                    and normalized
                    == re.sub(
                        r"\D",
                        "",
                        normalize_designation(str(row["stable_designation"])),
                    )
                )
                or normalized
                in {normalize_designation(str(alias)) for alias in row["alternative_designations"]}
            ]
            if not canonical_matches:
                return {
                    "contract": "construction-consultant-ntd@2.9.0",
                    "tool": "consultant.resolve_ntd_designation",
                    "outcome": "document_not_present",
                    "requested_designation": requested,
                    "message": "Документ отсутствует в нормативной памяти",
                    "sources": [],
                    "gaps": [{"code": "document_not_present"}],
                }
            items = [self._canonical_ntd_document_item(row) for row in canonical_matches]
            outcome = "designation_ambiguous" if len(items) > 1 else "document_present_searchable"
            return {
                "contract": "construction-consultant-ntd@2.9.0",
                "tool": "consultant.resolve_ntd_designation",
                "outcome": outcome,
                "requested_designation": requested,
                "items": [item["content"] for item in items],
                "sources": [item["source"] for item in items],
                "gaps": (
                    [{"code": "edition_currency_not_checked"}]
                    if outcome == "document_present_searchable"
                    else [{"code": "designation_ambiguous"}]
                ),
            }
        unique = {str(row["search_document_id"]): row for row in matches}
        items = [self._ntd_document_item(row) for row in unique.values()]
        outcome = "designation_ambiguous" if len(items) > 1 else _document_outcome(matches[0])
        sources = [item["source"] for item in items]
        return {
            "contract": "construction-consultant-ntd@2.9.0",
            "tool": "consultant.resolve_ntd_designation",
            "outcome": outcome,
            "requested_designation": requested,
            "items": [item["content"] for item in items],
            "sources": sources,
            "gaps": _ntd_outcome_gaps(outcome, matches[0]),
        }

    def _search_ntd_documents(self, query: str, limit: int) -> list[dict[str, Any]]:
        search_query = _search_query(query)
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "SELECT *,ts_rank_cd(search_vector,websearch_to_tsquery('russian',:query)) rank "
                        "FROM platform.ntd_search_documents WHERE search_vector @@ "
                        "websearch_to_tsquery('russian',:query) ORDER BY rank DESC,"
                        "CASE authority_class WHEN 'official' THEN 0 ELSE 1 END,stable_designation LIMIT :limit"
                    ),
                    {"query": search_query, "limit": limit},
                ).mappings()
            )
        return [self._ntd_document_item(row) for row in rows]

    def _production_ntd_content(
        self, query: str, limit: int, document_id: UUID | None
    ) -> list[dict[str, Any]] | None:
        if self._production_embedding_endpoint is None:
            return None

        from asd_kontur.assistant.production_ntd_evidence import production_hit_to_ntd_page_item
        from asd_kontur.ntd.production_query import query_production_ntd

        with self._engine.connect() as connection:
            resolved_scope: UUID | None = None
            if document_id is not None:
                scope_rows = connection.execute(
                    sa.text(
                        "SELECT DISTINCT corpus_object_id FROM platform.ntd_corpus_objects "
                        "WHERE corpus_object_id = :id "
                        "UNION "
                        "SELECT DISTINCT corpus_object_id FROM platform.ntd_search_documents "
                        "WHERE search_document_id = :id AND corpus_object_id IS NOT NULL"
                    ),
                    {"id": document_id},
                ).mappings()
                scope_ids = [UUID(str(row["corpus_object_id"])) for row in scope_rows]
                if not scope_ids:
                    return []
                if len(scope_ids) > 1:
                    raise ValueError("assistant_production_document_scope_ambiguous")
                resolved_scope = scope_ids[0]

            hits = query_production_ntd(
                connection,
                self._production_embedding_endpoint,
                query,
                limit,
                corpus_object_id=resolved_scope,
            )

            if not hits:
                return []

            hit_ids = [h.corpus_object_id for h in hits]
            meta_rows = connection.execute(
                sa.text(
                    "SELECT corpus_object_id, source_version_id, normative_edition_id "
                    "FROM platform.ntd_corpus_objects "
                    "WHERE corpus_object_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": hit_ids},
            ).mappings()
            meta_map: dict[UUID, dict[str, Any]] = {
                UUID(str(row["corpus_object_id"])): dict(row) for row in meta_rows
            }

            results: list[dict[str, Any]] = []
            for hit in hits:
                meta = meta_map.get(hit.corpus_object_id)
                if meta is None:
                    raise ValueError("assistant_production_hit_metadata_missing")

                source_version_id = (
                    UUID(str(meta["source_version_id"]))
                    if meta["source_version_id"] is not None
                    else None
                )
                normative_edition_id = (
                    UUID(str(meta["normative_edition_id"]))
                    if meta["normative_edition_id"] is not None
                    else None
                )
                if source_version_id is not None:
                    href = f"/api/v1/platform/sources/{source_version_id}/content"
                else:
                    href = ""

                results.append(
                    production_hit_to_ntd_page_item(
                        hit,
                        source_version_id=source_version_id,
                        normative_edition_id=normative_edition_id,
                        source_access_href=href,
                    )
                )

            return results

    def _search_ntd_content(
        self, query: str, limit: int, document_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        result = self._production_ntd_content(query, limit, document_id)
        if result is not None:
            return result
        search_query = _search_query(query)
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "SELECT p.*,d.authority_class,d.stable_designation,d.normalized_designation,"
                        "d.title,d.edition_label,"
                        "d.source_version_id,d.normative_edition_id,d.normative_artifact_id,"
                        "d.source_access_href,d.search_status,d.structure_status,d.edition_currency_status,"
                        "ts_rank_cd(p.search_vector,websearch_to_tsquery('russian',:query)) rank "
                        "FROM platform.ntd_search_pages p JOIN platform.ntd_search_documents d ON "
                        "d.search_document_id=p.search_document_id AND d.version=p.search_document_version "
                        "WHERE p.text_status='searchable' AND (CAST(:document_id AS UUID) IS NULL OR p.search_document_id=CAST(:document_id AS UUID)) AND p.search_vector @@ "
                        "websearch_to_tsquery('russian',:query) ORDER BY rank DESC,"
                        "CASE d.authority_class WHEN 'official' THEN 0 ELSE 1 END,p.page_number LIMIT :fetch_limit"
                    ),
                    {"query": search_query, "fetch_limit": limit * 4, "document_id": document_id},
                ).mappings()
            )
            if not rows:
                rows = list(
                    connection.execute(
                        sa.text(
                            "SELECT o.corpus_object_id AS search_document_id,c.page_start AS page_number,"
                            "cc.input_text AS page_text,cc.input_digest AS page_text_digest,"
                            "c.source_locator_ids[1] AS source_locator_id,cc.contextual_fingerprint AS page_fingerprint,"
                            "o.authority_class,o.stable_designation,o.title,o.printed_edition AS edition_label,"
                            "o.source_version_id,o.normative_edition_id,o.normative_artifact_id,"
                            "CASE WHEN o.source_version_id IS NULL THEN '' ELSE "
                            "'/api/v1/platform/sources/'||o.source_version_id::text||'/content' END AS source_access_href,"
                            "'searchable' AS search_status,'structured' AS structure_status,"
                            "'not_checked' AS edition_currency_status,"
                            "ts_rank_cd(cc.lexical_vector,websearch_to_tsquery('russian',:query)) rank "
                            "FROM platform.ntd_contextual_chunks cc JOIN platform.ntd_chunks c "
                            "ON c.chunk_id=cc.chunk_id AND c.version=cc.chunk_version "
                            "JOIN platform.ntd_corpus_objects o ON o.corpus_object_id=c.corpus_object_id "
                            "WHERE (CAST(:document_id AS UUID) IS NULL OR c.corpus_object_id=CAST(:document_id AS UUID)) AND cc.lexical_vector @@ websearch_to_tsquery('russian',:query) "
                            "ORDER BY rank DESC,c.page_start LIMIT :fetch_limit"
                        ),
                        {
                            "query": search_query,
                            "fetch_limit": limit * 4,
                            "document_id": document_id,
                        },
                    ).mappings()
                )
        selected: list[Any] = []
        seen: set[str] = set()
        for row in sorted(
            rows,
            key=lambda item: (
                normalize_designation(str(item["stable_designation"])),
                0 if item["authority_class"] == "official" else 1,
                -float(item["rank"] or 0),
            ),
        ):
            identity = normalize_designation(str(row["stable_designation"]))
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(row)
        selected.sort(key=lambda item: -float(item["rank"] or 0))
        return [self._ntd_page_item(row) for row in selected[:limit]]

    def _get_ntd_pages(self, payload: dict[str, Any], *, radius: int) -> list[dict[str, Any]]:
        document_id = _uuid_argument(payload, "search_document_id")
        page_number = payload.get("page_number")
        if not isinstance(page_number, int) or page_number < 1:
            raise ValueError("assistant_ntd_page_invalid")
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "SELECT p.*,d.authority_class,d.stable_designation,d.title,d.edition_label,"
                        "d.source_version_id,d.normative_edition_id,d.normative_artifact_id,"
                        "d.source_access_href,d.search_status,d.structure_status,d.edition_currency_status "
                        "FROM platform.ntd_search_pages p JOIN platform.ntd_search_documents d ON "
                        "d.search_document_id=p.search_document_id AND d.version=p.search_document_version "
                        "WHERE p.search_document_id=:id AND p.page_number BETWEEN :first AND :last "
                        "ORDER BY p.page_number"
                    ),
                    {
                        "id": document_id,
                        "first": max(1, page_number - radius),
                        "last": page_number + radius,
                    },
                ).mappings()
            )
            if not rows:
                rows = list(
                    connection.execute(
                        sa.text(
                            "SELECT p.corpus_object_id AS search_document_id,p.page_number,"
                            "p.raw_transcription AS page_text,p.raw_text_digest AS page_text_digest,"
                            "p.source_locator_id,p.page_fingerprint,o.authority_class,o.stable_designation,"
                            "o.title,o.printed_edition AS edition_label,o.source_version_id,"
                            "o.normative_edition_id,o.normative_artifact_id,"
                            "CASE WHEN o.source_version_id IS NULL THEN '' ELSE "
                            "'/api/v1/platform/sources/'||o.source_version_id::text||'/content' END AS source_access_href,"
                            "'searchable' AS search_status,'structured' AS structure_status,"
                            "'not_checked' AS edition_currency_status "
                            "FROM platform.ntd_corpus_pages p JOIN platform.ntd_corpus_objects o "
                            "ON o.corpus_object_id=p.corpus_object_id WHERE p.corpus_object_id=:id "
                            "AND p.page_number BETWEEN :first AND :last ORDER BY p.page_number"
                        ),
                        {
                            "id": document_id,
                            "first": max(1, page_number - radius),
                            "last": page_number + radius,
                        },
                    ).mappings()
                )
        return [self._ntd_page_item(row) for row in rows]

    def _verified_provisions_for_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        document_id = _uuid_argument(payload, "search_document_id")
        query = " ".join(str(payload.get("query", "")).split())
        limit = payload.get("limit", 5)
        if not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("assistant_ntd_limit_invalid")
        with self._engine.connect() as connection:
            document = (
                connection.execute(
                    sa.text(
                        "SELECT * FROM platform.ntd_search_documents WHERE search_document_id=:id"
                    ),
                    {"id": document_id},
                )
                .mappings()
                .one_or_none()
            )
            if document is None:
                return self._ntd_missing_result("consultant.get_verified_provisions")
            if (
                not document["normative_edition_id"]
                or int(document["verified_provision_count"]) == 0
            ):
                item = self._ntd_document_item(document)
                return {
                    "contract": "construction-consultant-ntd@2.9.0",
                    "tool": "consultant.get_verified_provisions",
                    "outcome": "verified_provisions_unavailable",
                    "items": [item["content"]],
                    "sources": [item["source"]],
                    "gaps": [{"code": "verified_provisions_unavailable"}],
                }
            parameters: dict[str, Any] = {
                "edition": document["normative_edition_id"],
                "limit": limit,
            }
            predicate = ""
            if query:
                parameters["query"] = _search_query(query)
                predicate = (
                    " AND to_tsvector('russian',p.structural_path||' '||p.verbatim_text) "
                    "@@ websearch_to_tsquery('russian',:query)"
                )
            rows = list(
                connection.execute(
                    sa.text(
                        "SELECT p.normative_provision_id,p.version,p.source_version_id,p.structural_path,"
                        "p.page_number,p.verbatim_text,p.content_digest,p.normative_edition_id,"
                        "d.designation,d.title,e.edition_label,a.normative_artifact_id FROM "
                        "platform.normative_provision_versions p JOIN platform.normative_editions e ON "
                        "e.normative_edition_id=p.normative_edition_id JOIN platform.normative_documents d ON "
                        "d.normative_document_id=e.normative_document_id JOIN platform.normative_artifacts a ON "
                        "a.source_version_id=p.source_version_id WHERE p.verification_status='verified' "
                        "AND p.normative_edition_id=:edition"
                        + predicate
                        + " ORDER BY p.page_number,"
                        "p.structural_path LIMIT :limit"
                    ),
                    parameters,
                ).mappings()
            )
        return self._tool_result(
            "consultant.get_verified_provisions", [self._normative_item(row) for row in rows]
        )

    def _ntd_processing_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        document_id = _uuid_argument(payload, "search_document_id")
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    sa.text(
                        "SELECT * FROM platform.ntd_search_documents WHERE search_document_id=:id"
                    ),
                    {"id": document_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return self._ntd_missing_result("consultant.get_ntd_processing_status")
        item = self._ntd_document_item(row)
        outcome = _document_outcome(row)
        return {
            "contract": "construction-consultant-ntd@2.9.0",
            "tool": "consultant.get_ntd_processing_status",
            "outcome": outcome,
            "value": item["content"],
            "sources": [item["source"]],
            "gaps": _ntd_outcome_gaps(outcome, row),
        }

    def _applicability_candidates(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        mode: str,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        workspace = self._workspace_context(organization_id, workspace_id, mode, query)
        items = self._search_ntd_documents(query, limit)
        if not items:
            pages = self._search_ntd_content(query, limit)
            unique: dict[str, dict[str, Any]] = {}
            for item in pages:
                identity = str(item["content"]["search_document_id"])
                unique.setdefault(identity, item)
            items = list(unique.values())[:limit]
        return {
            "contract": "construction-consultant-ntd@2.9.0",
            "tool": "consultant.find_applicability_candidates",
            "outcome": "applicability_unresolved" if items else "not_found",
            "items": [item["content"] for item in items],
            "sources": [item["source"] for item in items],
            "gaps": [{"code": "applicability_unresolved"}],
            "notice": "Кандидаты найдены по предмету и сведениям ОКС; окончательная применимость требует проверки условий работ.",
            "workspace_signals": {
                "project_model_available": bool(workspace.get("project_definition")),
                "work_package_count": len(workspace.get("work_packages") or []),
            },
        }

    @staticmethod
    def _ntd_missing_result(tool: str) -> dict[str, Any]:
        return {
            "contract": "construction-consultant-ntd@2.9.0",
            "tool": tool,
            "outcome": "document_not_present",
            "sources": [],
            "gaps": [{"code": "document_not_present"}],
        }

    def _canonical_ntd_documents(self) -> list[Any]:
        with self._engine.connect() as connection:
            return list(
                connection.execute(
                    sa.text(
                        "SELECT o.corpus_object_id AS search_document_id,o.authority_class,"
                        "o.stable_designation,o.alternative_designations,o.title,o.printed_edition AS edition_label,"
                        "o.artifact_digest,o.source_version_id,o.normative_edition_id,o.normative_artifact_id,"
                        "(SELECT count(*) FROM platform.ntd_corpus_pages p WHERE p.corpus_object_id=o.corpus_object_id) page_count,"
                        "(SELECT count(*) FROM platform.ntd_corpus_pages p WHERE p.corpus_object_id=o.corpus_object_id "
                        "AND length(p.raw_transcription)>0) searchable_page_count,"
                        "(SELECT count(*) FROM platform.ntd_contextual_chunks cc JOIN platform.ntd_chunks c "
                        "ON c.chunk_id=cc.chunk_id AND c.version=cc.chunk_version "
                        "WHERE c.corpus_object_id=o.corpus_object_id) contextual_chunk_count "
                        "FROM platform.ntd_corpus_objects o WHERE o.terminal_outcome='admitted' "
                        "ORDER BY o.stable_designation,o.artifact_digest"
                    )
                ).mappings()
            )

    @staticmethod
    def _canonical_ntd_document_item(row: Any) -> dict[str, Any]:
        authority = (
            "normative_authority"
            if row["authority_class"] in {"official", "official_binding_recovered"}
            else "legacy_reference"
        )
        searchable = int(row["contextual_chunk_count"] or 0) > 0
        status = (
            "Документ присутствует и доступен для поиска"
            if searchable
            else "Документ присутствует, но обработан частично"
        )
        source_version = row["source_version_id"] or row["search_document_id"]
        href = (
            f"/api/v1/platform/sources/{row['source_version_id']}/content#page=1"
            if row["source_version_id"]
            else ""
        )
        return {
            "content": {
                "search_document_id": str(row["search_document_id"]),
                "document": str(row["stable_designation"]),
                "title": str(row["title"]),
                "edition": str(row["edition_label"] or ""),
                "authority": authority,
                "bytes_status": "present",
                "page_inventory_status": "inventoried",
                "text_status": "complete" if searchable else "partial",
                "search_status": "searchable" if searchable else "partially_searchable",
                "structure_status": "structured" if searchable else "not_structured",
                "edition_currency": "not_checked",
                "page_count": int(row["page_count"] or 0),
                "searchable_page_count": int(row["searchable_page_count"] or 0),
                "verified_provision_count": 0,
                "status_message": status,
            },
            "source": {
                "source_id": str(row["search_document_id"]),
                "source_version_id": str(source_version),
                "edition_id": (
                    str(row["normative_edition_id"]) if row["normative_edition_id"] else None
                ),
                "authority_layer": authority,
                "title": f"{row['stable_designation']} — {row['title']}",
                "edition": str(row["edition_label"] or ""),
                "page": 1,
                "locator_label": "карточка нормативного документа",
                "fragment": status,
                "content_digest": str(row["artifact_digest"]),
                "href": href,
                "edition_currency_notice": "Актуальность редакции не проверена",
            },
        }

    @staticmethod
    def _ntd_document_item(row: Any) -> dict[str, Any]:
        authority = (
            "normative_authority"
            if row["authority_class"] in {"official", "official_binding_recovered"}
            else "legacy_reference"
        )
        href = str(row["source_access_href"] or "")
        if href:
            href += "#page=1"
        return {
            "content": {
                "search_document_id": str(row["search_document_id"]),
                "document": str(row["stable_designation"]),
                "title": str(row["title"]),
                "edition": str(row["edition_label"] or ""),
                "authority": authority,
                "bytes_status": str(row["bytes_status"]),
                "page_inventory_status": str(row["page_inventory_status"]),
                "text_status": str(row["text_status"]),
                "search_status": str(row["search_status"]),
                "structure_status": str(row["structure_status"]),
                "edition_currency": str(row["edition_currency_status"]),
                "page_count": int(row["page_count"]),
                "searchable_page_count": int(row["searchable_page_count"]),
                "verified_provision_count": int(row["verified_provision_count"]),
                "status_message": _document_status_message(row),
            },
            "source": {
                "source_id": str(row["search_document_id"]),
                "source_version_id": str(row["source_version_id"] or row["search_document_id"]),
                "edition_id": str(row["normative_edition_id"])
                if row["normative_edition_id"]
                else None,
                "authority_layer": authority,
                "title": f"{row['stable_designation']} — {row['title']}",
                "edition": str(row["edition_label"] or ""),
                "page": 1,
                "locator_label": "карточка нормативного документа",
                "fragment": _document_status_message(row),
                "content_digest": str(row["artifact_digest"]),
                "href": href,
                "edition_currency_notice": "Актуальность редакции не проверена",
            },
        }

    @staticmethod
    def _ntd_page_item(row: Any) -> dict[str, Any]:
        authority = (
            "normative_authority"
            if row["authority_class"] in {"official", "official_binding_recovered"}
            else "legacy_reference"
        )
        page = int(row["page_number"])
        source_id = row["source_locator_id"] or deterministic_uuid(
            f"ntd-search-page-source:{row['page_fingerprint']}"
        )
        href = str(row["source_access_href"] or "")
        if href:
            href += f"#page={page}"
        notice = (
            "Текст нормативного документа; положения ещё не прошли структурированную проверку"
            if str(row["structure_status"]) != "verified_provisions"
            else "Проверенная редакция текста; конкретное утверждение сверяйте с проверенными положениями"
        )
        return {
            "content": {
                "search_document_id": str(row["search_document_id"]),
                "document": str(row["stable_designation"]),
                "edition": str(row["edition_label"] or ""),
                "page": page,
                "text": str(row["page_text"])[:6000],
                "authority": authority,
                "source_text_notice": notice,
                "edition_currency": "not_checked",
            },
            "source": {
                "source_id": str(source_id),
                "source_version_id": str(row["source_version_id"] or row["search_document_id"]),
                "edition_id": str(row["normative_edition_id"])
                if row["normative_edition_id"]
                else None,
                "authority_layer": authority,
                "title": f"{row['stable_designation']} — {row['title']}",
                "edition": str(row["edition_label"] or ""),
                "page": page,
                "locator_label": f"страница {page}",
                "fragment": str(row["page_text"])[:1000],
                "content_digest": str(row["page_text_digest"]),
                "href": href,
                "edition_currency_notice": "Актуальность редакции не проверена",
                "source_text_notice": notice,
            },
        }

    def _normative_context(self, query: str, limit: int) -> list[dict[str, Any]]:
        designation = _normative_designation(query)
        search_query = _search_query(query)
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "SELECT p.normative_provision_id,p.version,p.source_version_id,p.structural_path,"
                        "p.page_number,p.verbatim_text,p.content_digest,p.normative_edition_id,"
                        "d.designation,d.title,e.edition_label,a.normative_artifact_id FROM "
                        "platform.normative_provision_versions p JOIN platform.normative_editions e ON "
                        "e.normative_edition_id=p.normative_edition_id JOIN platform.normative_documents d ON "
                        "d.normative_document_id=e.normative_document_id JOIN platform.normative_artifacts a ON "
                        "a.source_version_id=p.source_version_id WHERE p.verification_status='verified' AND ("
                        "to_tsvector('russian',d.designation||' '||d.title||' '||p.structural_path||' '||"
                        "p.verbatim_text) @@ websearch_to_tsquery('russian',:query) OR "
                        "(:designation<>'' AND d.designation ILIKE '%'||:designation||'%')) ORDER BY "
                        "CASE WHEN :designation<>'' AND d.designation ILIKE '%'||:designation||'%' THEN 1 ELSE 0 END DESC,"
                        "ts_rank_cd(to_tsvector('russian',d.designation||' '||d.title||' '||p.structural_path||' '||"
                        "p.verbatim_text),websearch_to_tsquery('russian',:query)) DESC,"
                        "p.normative_edition_id,p.structural_path "
                        "LIMIT :limit"
                    ),
                    {"query": search_query, "designation": designation, "limit": limit},
                ).mappings()
            )
        return [
            {
                "content": {
                    "document": str(row["designation"]),
                    "edition": str(row["edition_label"]),
                    "provision": str(row["structural_path"]),
                    "page": int(row["page_number"] or 1),
                    "verbatim": str(row["verbatim_text"])[:1000],
                    "authority": "normative_authority",
                    "edition_currency": "not_checked",
                },
                "source": {
                    "source_id": str(row["normative_provision_id"]),
                    "source_version_id": str(row["source_version_id"]),
                    "edition_id": str(row["normative_edition_id"]),
                    "authority_layer": "normative_authority",
                    "title": f"{row['designation']} — {row['title']}",
                    "edition": str(row["edition_label"]),
                    "page": int(row["page_number"] or 1),
                    "locator_label": str(row["structural_path"]),
                    "fragment": str(row["verbatim_text"])[:500],
                    "content_digest": str(row["content_digest"]),
                    "href": f"/api/v1/platform/ntd/artifacts/{row['normative_artifact_id']}/content#page={row['page_number'] or 1}",
                    "edition_currency_notice": "Актуальность редакции не проверена",
                },
            }
            for row in rows
        ]

    def _practice_fragment(self, source_id: UUID) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "SELECT u.title,u.instruction,u.rationale,u.applicability_conditions,"
                        "s.source_version_id,s.source_locator_id,s.page_number,s.fragment_digest,"
                        "a.title source_title FROM platform.practice_intelligence_units u JOIN "
                        "platform.practice_intelligence_sources s ON s.intelligence_unit_id=u.intelligence_unit_id "
                        "AND s.intelligence_unit_version=u.version JOIN platform.source_versions sv ON "
                        "sv.source_version_id=s.source_version_id JOIN platform.source_artifacts a ON "
                        "a.source_artifact_id=sv.source_artifact_id WHERE s.source_locator_id=:id "
                        "ORDER BY u.version DESC LIMIT 1"
                    ),
                    {"id": source_id},
                ).mappings()
            )
        return [self._practice_item(row) for row in rows]

    def _normative_provision(self, source_id: UUID) -> list[dict[str, Any]]:
        rows = self._normative_rows("p.normative_provision_id=:id", {"id": source_id})
        return [self._normative_item(row) for row in rows]

    def _normative_section(self, source_id: UUID, radius: int) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "WITH ordered AS (SELECT p.normative_provision_id,p.version,p.source_version_id,"
                        "p.structural_path,p.page_number,p.verbatim_text,p.content_digest,"
                        "p.normative_edition_id,d.designation,d.title,e.edition_label,a.normative_artifact_id,"
                        "row_number() OVER (PARTITION BY p.normative_edition_id ORDER BY "
                        "coalesce(p.page_number,1),p.structural_path,p.normative_provision_id) position "
                        "FROM platform.normative_provision_versions p JOIN platform.normative_editions e ON "
                        "e.normative_edition_id=p.normative_edition_id JOIN platform.normative_documents d ON "
                        "d.normative_document_id=e.normative_document_id JOIN platform.normative_artifacts a ON "
                        "a.source_version_id=p.source_version_id WHERE p.verification_status='verified'), "
                        "target AS (SELECT normative_edition_id,position FROM ordered WHERE "
                        "normative_provision_id=:id) SELECT o.* FROM ordered o JOIN target t ON "
                        "t.normative_edition_id=o.normative_edition_id AND "
                        "o.position BETWEEN t.position-:radius AND t.position+:radius "
                        "ORDER BY o.position"
                    ),
                    {"id": source_id, "radius": radius},
                ).mappings()
            )
        return [self._normative_item(row) for row in rows]

    def _workspace_search(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        mode: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        search_query = _search_query(query)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            rows = list(
                session.execute(
                    sa.text(
                        "WITH candidates AS (SELECT sl.source_locator_id,sl.source_version_id,"
                        "sl.locator_value,sl.fragment_digest,v.safe_display_name,e.raw_text,e.page_number,"
                        "ts_rank_cd(to_tsvector('russian',coalesce(e.raw_text,'')||' '||v.safe_display_name),"
                        "websearch_to_tsquery('russian',:query)) rank,row_number() OVER (PARTITION BY "
                        "sl.source_locator_id ORDER BY e.version DESC NULLS LAST) rn FROM "
                        "workspace.source_locators sl JOIN workspace.document_versions v ON "
                        "v.organization_id=sl.organization_id AND v.workspace_id=sl.workspace_id AND "
                        "v.source_version_id=sl.source_version_id LEFT JOIN "
                        "workspace.native_layout_element_versions e ON e.organization_id=sl.organization_id "
                        "AND e.workspace_id=sl.workspace_id AND e.source_locator_id=sl.source_locator_id "
                        "WHERE sl.organization_id=:o AND sl.workspace_id=:w AND "
                        "to_tsvector('russian',coalesce(e.raw_text,'')||' '||v.safe_display_name) @@ "
                        "websearch_to_tsquery('russian',:query)) SELECT source_locator_id,source_version_id,"
                        "locator_value,fragment_digest,safe_display_name,raw_text,page_number,rank FROM "
                        "candidates WHERE rn=1 AND rank>0 ORDER BY rank DESC,source_locator_id LIMIT :limit"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "query": search_query,
                        "limit": limit,
                    },
                ).mappings()
            )
        ranked = sorted(
            rows, key=lambda row: (-float(row["rank"] or 0), str(row["source_locator_id"]))
        )
        return [self._workspace_item(row, workspace_id, mode) for row in ranked[:limit]]

    def _workspace_fragment(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        mode: str,
        source_id: UUID,
    ) -> list[dict[str, Any]]:
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            rows = list(
                session.execute(
                    sa.text(
                        "SELECT sl.source_locator_id,sl.source_version_id,sl.locator_value,"
                        "sl.fragment_digest,v.safe_display_name,e.raw_text,e.page_number FROM "
                        "workspace.source_locators sl JOIN workspace.document_versions v ON "
                        "v.organization_id=sl.organization_id AND v.workspace_id=sl.workspace_id AND "
                        "v.source_version_id=sl.source_version_id LEFT JOIN "
                        "workspace.native_layout_element_versions e ON e.organization_id=sl.organization_id "
                        "AND e.workspace_id=sl.workspace_id AND e.source_locator_id=sl.source_locator_id "
                        "WHERE sl.organization_id=:o AND sl.workspace_id=:w AND "
                        "sl.source_locator_id=:id ORDER BY e.version DESC NULLS LAST LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id, "id": source_id},
                ).mappings()
            )
        return [self._workspace_item(row, workspace_id, mode) for row in rows]

    def _normative_rows(self, predicate: str, parameters: dict[str, Any]) -> list[Any]:
        with self._engine.connect() as connection:
            return list(
                connection.execute(
                    sa.text(
                        "SELECT p.normative_provision_id,p.version,p.source_version_id,p.structural_path,"
                        "p.page_number,p.verbatim_text,p.content_digest,p.normative_edition_id,"
                        "d.designation,d.title,e.edition_label,a.normative_artifact_id FROM "
                        "platform.normative_provision_versions p JOIN platform.normative_editions e ON "
                        "e.normative_edition_id=p.normative_edition_id JOIN platform.normative_documents d ON "
                        "d.normative_document_id=e.normative_document_id JOIN platform.normative_artifacts a ON "
                        f"a.source_version_id=p.source_version_id WHERE p.verification_status='verified' AND {predicate} "
                        "ORDER BY p.version DESC LIMIT 1"
                    ),
                    parameters,
                ).mappings()
            )

    @staticmethod
    def _practice_item(row: Any) -> dict[str, Any]:
        return {
            "content": {
                "title": str(row["title"]),
                "instruction": str(row["instruction"]),
                "rationale": str(row["rationale"] or ""),
                "applicability": row["applicability_conditions"],
                "authority": "methodological_practice",
            },
            "source": {
                "source_id": str(row["source_locator_id"]),
                "source_version_id": str(row["source_version_id"]),
                "authority_layer": "methodological_practice",
                "title": _practice_source_title(str(row["source_title"])),
                "edition": None,
                "page": int(row["page_number"]),
                "locator_label": f"раздел пособия, страница {row['page_number']}",
                "fragment": str(row["instruction"])[:1000],
                "content_digest": str(row["fragment_digest"]),
                "href": f"/api/v1/platform/sources/{row['source_version_id']}/content#page={row['page_number']}",
                "edition_currency_notice": None,
            },
        }

    @staticmethod
    def _normative_item(row: Any) -> dict[str, Any]:
        return {
            "content": {
                "document": str(row["designation"]),
                "edition": str(row["edition_label"]),
                "provision": str(row["structural_path"]),
                "page": int(row["page_number"] or 1),
                "verbatim": str(row["verbatim_text"]),
                "authority": "normative_authority",
                "edition_currency": "not_checked",
            },
            "source": {
                "source_id": str(row["normative_provision_id"]),
                "source_version_id": str(row["source_version_id"]),
                "edition_id": str(row["normative_edition_id"]),
                "authority_layer": "normative_authority",
                "title": f"{row['designation']} — {row['title']}",
                "edition": str(row["edition_label"]),
                "page": int(row["page_number"] or 1),
                "locator_label": str(row["structural_path"]),
                "fragment": str(row["verbatim_text"])[:1000],
                "content_digest": str(row["content_digest"]),
                "href": f"/api/v1/platform/ntd/artifacts/{row['normative_artifact_id']}/content#page={row['page_number'] or 1}",
                "edition_currency_notice": "Актуальность редакции не проверена",
            },
        }

    @staticmethod
    def _workspace_item(row: Any, workspace_id: UUID, mode: str) -> dict[str, Any]:
        page = int(row.get("page_number") or _page_from_locator(row["locator_value"]))
        return {
            "content": {
                "document": str(row["safe_display_name"]),
                "page": page,
                "fragment": str(row["raw_text"] or "")[:4000],
                "authority": "workspace_fact",
            },
            "source": {
                "source_id": str(row["source_locator_id"]),
                "source_version_id": str(row["source_version_id"]),
                "authority_layer": "workspace_fact",
                "title": str(row["safe_display_name"]),
                "edition": None,
                "page": page,
                "locator_label": f"страница {page}",
                "fragment": str(row["raw_text"] or "")[:1000],
                "content_digest": str(row["fragment_digest"]),
                "href": f"/modes/{_mode_slug(mode)}/workspaces/{workspace_id}/evidence/locators/{row['source_locator_id']}",
                "edition_currency_notice": None,
            },
        }


def _scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def _mode(payload: dict[str, Any]) -> str:
    mode = str(payload.get("mode", ""))
    if mode not in {"Tender", "Support", "Audit", "Restoration"}:
        raise ValueError("assistant_tool_mode_invalid")
    return mode


def _uuid_argument(payload: dict[str, Any], key: str) -> UUID:
    try:
        return UUID(str(payload.get(key, "")))
    except ValueError as exc:
        raise ValueError("assistant_ntd_identity_invalid") from exc


def _document_outcome(row: Any) -> str:
    if str(row["bytes_status"]) != "present":
        return "document_not_present"
    if str(row["text_status"]) == "none":
        return "document_present_no_text"
    if str(row["search_status"]) != "searchable":
        return "document_present_processing_incomplete"
    return "document_present_searchable"


def _document_status_message(row: Any) -> str:
    outcome = _document_outcome(row)
    return {
        "document_present_searchable": "Документ присутствует и доступен для поиска",
        "document_present_processing_incomplete": "Документ присутствует, но обработан частично",
        "document_present_no_text": "Документ присутствует, но пригодный для поиска текст отсутствует",
        "document_not_present": "Документ отсутствует в нормативной памяти",
    }[outcome]


def _ntd_outcome_gaps(outcome: str, row: Any) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if outcome != "document_present_searchable":
        gaps.append({"code": outcome})
    if str(row["structure_status"]) != "verified_provisions":
        gaps.append({"code": "verified_provisions_unavailable"})
    if str(row["edition_currency_status"]) == "not_checked":
        gaps.append({"code": "edition_currency_not_checked"})
    return gaps


def _search_arguments(payload: dict[str, Any], *, maximum: int) -> tuple[str, int]:
    query = " ".join(str(payload.get("query", "")).split())
    limit = payload.get("limit", min(5, maximum))
    allowed = {"mode", "query", "limit"}
    if (
        set(payload) - allowed
        or not 2 <= len(query) <= 500
        or not isinstance(limit, int)
        or not 1 <= limit <= maximum
    ):
        raise ValueError("assistant_tool_search_invalid")
    return query, limit


def _source_id(payload: dict[str, Any]) -> UUID:
    if set(payload) - {"mode", "source_id", "radius"} or "source_id" not in payload:
        raise ValueError("assistant_tool_source_invalid")
    try:
        return UUID(str(payload["source_id"]))
    except ValueError as exc:
        raise ValueError("assistant_tool_source_invalid") from exc


def _evidence(item: dict[str, Any]) -> EvidenceItem:
    return EvidenceItem(
        str(item["source_id"]),
        str(item.get("source_version_id") or item["source_id"]),
        str(item["edition_id"]) if item.get("edition_id") else None,
        str(item["locator_label"]),
        str(item["content_digest"]),
        str(item["href"]),
        str(item["authority_layer"]),
    )


def _canonical_workspace_sources(
    value: dict[str, Any], workspace_id: UUID, mode: str, title: str
) -> list[dict[str, Any]]:
    identity = (
        value.get("package", {}).get("id_package_id")
        if isinstance(value.get("package"), dict)
        else None
    )
    if not identity:
        return []
    digest = semantic_digest(_json_value(value))
    return [
        {
            "source_id": str(identity),
            "source_version_id": str(identity),
            "authority_layer": "workspace_fact",
            "title": title,
            "edition": str(value.get("package", {}).get("version", "")),
            "page": None,
            "locator_label": "текущая версия комплекта",
            "fragment": "Состав, состояния и комплектность документов текущего объекта",
            "content_digest": digest,
            "href": f"/modes/{_mode_slug(mode)}/workspaces/{workspace_id}/support-id",
            "edition_currency_notice": None,
        }
    ]


_STOP_WORDS = frozenset(
    {
        "какие",
        "какой",
        "этого",
        "этом",
        "этой",
        "нужно",
        "необходимо",
        "обычно",
        "входят",
        "соответствующий",
        "документы",
        "документов",
        "объекте",
        "объекта",
        "этому",
        "можно",
        "которые",
    }
)

_DOMAIN_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"аоср", "акт", "скрытых", "освидетельствования"}),
    frozenset({"ид", "исполнительная", "документация", "комплект"}),
    frozenset({"вор", "ведомость", "объем", "объём"}),
    frozenset({"качество", "паспорт", "сертификат", "протокол"}),
    frozenset({"смета", "расценка", "позиция"}),
    frozenset({"контроль", "приемка", "приёмка", "проверка"}),
)


def _search_tokens(query: str) -> tuple[str, ...]:
    tokens = [
        value
        for value in re.findall(r"[0-9A-Za-zА-Яа-яЁё]{3,}", query.lower())
        if value not in _STOP_WORDS
    ]
    stems = tuple(value[:5] for value in tokens)
    expansions = [
        synonym
        for group in _DOMAIN_SYNONYM_GROUPS
        if any(
            any(term.startswith(stem) or stem.startswith(term[:5]) for term in group)
            for stem in stems
        )
        for synonym in sorted(group)
    ]
    return tuple(dict.fromkeys((*tokens, *expansions)))[:12]


def _search_query(query: str) -> str:
    tokens = _search_tokens(query)
    return " OR ".join(tokens or ("строительство",))


def _normative_designation(query: str) -> str:
    match = re.search(
        r"\b(СП|ГОСТ(?:\s+Р)?|СНиП)\s*[0-9]+(?:\.[0-9]+)*(?:-[0-9]{4})?",
        query,
        re.IGNORECASE,
    )
    return " ".join(match.group(0).upper().split()) if match else ""


def _json_row(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _json_value(value) for key, value in dict(row).items()}


def _mode_result_row(row: Any | None) -> dict[str, Any] | None:
    value = _json_row(row)
    if value is None:
        return None
    payload = value.get("result_payload")
    if isinstance(payload, dict):
        value["result_payload"] = {
            key: payload.get(key)
            for key in (
                "status",
                "summary",
                "items",
                "unresolved_questions",
                "normative_notice",
                "available_exports",
            )
            if payload.get(key) is not None
        }
    return value


def _matrix_with_work_names(row: Any | None, packages: list[Any]) -> dict[str, Any] | None:
    value = _json_row(row)
    if value is None:
        return None
    names: dict[str, str] = {}
    for package_row in packages:
        package = _json_row(package_row) or {}
        payload = package.get("package")
        work_type = payload.get("work_type") if isinstance(payload, dict) else None
        if isinstance(work_type, dict):
            names[str(package.get("work_package_id"))] = str(
                work_type.get("raw") or work_type.get("normalized") or "Вид работы"
            )
    matrix = value.get("matrix")
    rows = matrix.get("rows") if isinstance(matrix, dict) else None
    if isinstance(rows, list):
        for matrix_row in rows:
            if isinstance(matrix_row, dict):
                matrix_row["work_type"] = names.get(
                    str(matrix_row.get("work_package_id")), "Вид работы требует уточнения"
                )
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


_PUBLIC_VALUE_LABELS = {
    "verified": "подтверждено",
    "confirmed": "подтверждено",
    "candidate": "требует подтверждения",
    "unresolved": "требует уточнения",
    "requires_clarification": "требует уточнения",
    "draft_with_open_questions": "проект с нерешёнными вопросами",
    "open": "не устранено",
    "available": "доступно",
    "gap": "есть пробел",
    "advisory_only": "методическая рекомендация",
    "complete": "обработано",
    "processed": "обработано",
    "accepted": "принято",
}

_PUBLIC_GAP_LABELS = {
    "VERIFIED_PD_RD_NTD_UNAVAILABLE": "подтверждённое нормативное основание не найдено",
    "ACTIVE_PD_RD_RULE_VERSION_UNAVAILABLE": "автоматическая проверка не настроена",
    "NORMATIVE_APPLICABILITY_INPUT_MISSING": "не указаны сведения для проверки применимости",
    "WORK_TYPE_CATALOG_UNAVAILABLE": "вид работы требует уточнения специалистом",
    "WORK_TYPE_MAPPING_UNRESOLVED": "вид работы пока не сопоставлен с утверждённым каталогом",
    "WORK_TYPE_MAPPING_AMBIGUOUS": "для вида работы найдены неоднозначные варианты сопоставления",
}


def _public_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_public_value(item) for item in value[:30]]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key.endswith(("_id", "_ids", "_digest")) or key in {
                "fingerprint",
                "organization_id",
                "workspace_id",
                "candidate_id",
                "source_version_id",
                "recorded_at",
                "correlation_id",
            }:
                continue
            result[key] = _public_value(item)
        return result
    if isinstance(value, str):
        if value in _PUBLIC_VALUE_LABELS:
            return _PUBLIC_VALUE_LABELS[value]
        if value in _PUBLIC_GAP_LABELS:
            return _PUBLIC_GAP_LABELS[value]
        return value[:1200]
    return value


def _page_from_locator(value: Any) -> int:
    if isinstance(value, dict):
        for key in ("page", "page_number", "sheet"):
            if value.get(key) is not None:
                try:
                    return max(1, int(value[key]))
                except (TypeError, ValueError):
                    pass
    return 1


def _mode_slug(mode: str) -> str:
    return {
        "Tender": "tender",
        "Support": "support",
        "Audit": "audit",
        "Restoration": "restoration",
    }[mode]


def _practice_source_title(title: str) -> str:
    """Expose the established Russian product name, not an import-era label."""
    if title.strip().casefold() == "id practice guide":
        return "Пособие по исполнительной документации"
    return title
