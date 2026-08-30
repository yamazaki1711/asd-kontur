"""Bounded Knowledge Gateway context for the professional assistant."""

# ruff: noqa: E501, RUF001 -- SQL clauses, URLs and Russian query terms stay readable.

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.knowledge.gateway import (
    ASSISTANT_CONTRACT_VERSION,
    EvidenceItem,
    EvidencePack,
    GatewayContext,
    GatewayResponse,
    GatewayStatus,
)

ASSISTANT_TOOL = "knowledge.get_professional_assistant_context"


class ProfessionalAssistantKnowledgeQuery:
    """One allowlisted read tool; the model never receives SQL or storage access."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def memory_fingerprint(self) -> str:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    sa.text(
                        "SELECT (SELECT count(*) FROM platform.practice_intelligence_units) practice,"
                        "(SELECT count(*) FROM platform.normative_provision_versions WHERE "
                        "verification_status='verified') normative,"
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
        if tool != ASSISTANT_TOOL:
            raise ValueError("assistant_gateway_tool_not_supported")
        if context.organization_id is None or context.workspace_id is None:
            raise PermissionError("assistant_workspace_scope_required")
        query = " ".join(str(payload.get("query", "")).split())
        mode = str(payload.get("mode", ""))
        if len(query) < 2 or mode not in {"Tender", "Support", "Audit", "Restoration"}:
            raise ValueError("assistant_context_request_invalid")
        workspace = self._workspace_context(
            context.organization_id, context.workspace_id, mode, query
        )
        search_query = _search_query(query)
        practice = self._practice_context(search_query)
        normative = self._normative_context(search_query)
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
            "contract": "professional-assistant-context@2.7.0",
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
            tool,
            ASSISTANT_CONTRACT_VERSION,
            GatewayStatus.KNOWLEDGE_INCOMPLETE if gaps else GatewayStatus.OK,
            result,
            EvidencePack(evidence, (), (), tuple(gaps), ()),
        )

    def _workspace_context(
        self, organization_id: UUID, workspace_id: UUID, mode: str, query: str
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
                        "SELECT work_package_id,version,work_type_key,package FROM "
                        "workspace.construction_work_package_versions WHERE organization_id=:o "
                        "AND workspace_id=:w ORDER BY created_at DESC,work_package_id LIMIT 20"
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
            locators = list(
                session.execute(
                    sa.text(
                        "SELECT DISTINCT ON (sl.source_locator_id) sl.source_locator_id,"
                        "sl.source_version_id,sl.locator_value,sl.fragment_digest,v.document_id,"
                        "v.safe_display_name,e.raw_text,e.page_number FROM workspace.source_locators sl "
                        "JOIN workspace.document_versions v ON v.organization_id=sl.organization_id AND "
                        "v.workspace_id=sl.workspace_id AND v.source_version_id=sl.source_version_id "
                        "LEFT JOIN workspace.native_layout_element_versions e ON "
                        "e.organization_id=sl.organization_id AND e.workspace_id=sl.workspace_id AND "
                        "e.source_locator_id=sl.source_locator_id WHERE sl.organization_id=:o AND "
                        "sl.workspace_id=:w ORDER BY sl.source_locator_id,e.version DESC NULLS LAST LIMIT 100"
                    ),
                    {"o": organization_id, "w": workspace_id},
                ).mappings()
            )
        referenced = set(
            re.findall(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                str(
                    (
                        _json_row(project),
                        [_json_row(row) for row in packages],
                        _json_row(matrix),
                        [_json_row(row) for row in defects],
                        _json_row(result),
                    )
                ).lower(),
            )
        )
        tokens = _search_tokens(query)
        ranked_locators = sorted(
            locators,
            key=lambda row: (
                -_locator_score(row, tokens, referenced),
                str(row["source_locator_id"]),
            ),
        )
        selected_locators = [
            row for row in ranked_locators if _locator_score(row, tokens, referenced) > 0
        ][:6]
        source_items = []
        for row in selected_locators:
            page = int(row["page_number"] or _page_from_locator(row["locator_value"]))
            source_items.append(
                {
                    "content": {
                        "document": str(row["safe_display_name"]),
                        "page": page,
                        "fragment": str(row["raw_text"] or "")[:1200],
                    },
                    "source": {
                        "source_id": str(row["source_locator_id"]),
                        "source_version_id": str(row["source_version_id"]),
                        "authority_layer": "workspace_fact",
                        "title": str(row["safe_display_name"]),
                        "edition": None,
                        "page": page,
                        "locator_label": f"страница {page}",
                        "fragment": str(row["raw_text"] or "")[:500],
                        "content_digest": str(row["fragment_digest"]),
                        "href": f"/modes/{_mode_slug(mode)}/workspaces/{workspace_id}/evidence/locators/{row['source_locator_id']}",
                        "edition_currency_notice": None,
                    },
                }
            )
        return {
            "workspace_id": str(workspace_id),
            "name": str(workspace["display_name"]),
            "project_definition": _public_value(_json_row(project)),
            "work_packages": _public_value([_json_row(row) for row in packages]),
            "requirement_matrix": _public_value(_matrix_with_work_names(matrix, packages)),
            "discrepancies": _public_value([_json_row(row) for row in defects]),
            "mode_result": _public_value(_mode_result_row(result)),
            "documents": _public_value([_json_row(row) for row in documents]),
            "source_items": source_items,
        }

    def _practice_context(self, query: str) -> list[dict[str, Any]]:
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
                        "intelligence_unit_id LIMIT 4"
                    ),
                    {"query": query},
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

    def _normative_context(self, query: str) -> list[dict[str, Any]]:
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
                        "a.source_version_id=p.source_version_id WHERE p.verification_status='verified' AND "
                        "to_tsvector('russian',p.structural_path||' '||p.verbatim_text) @@ "
                        "websearch_to_tsquery('russian',:query) ORDER BY ts_rank_cd(to_tsvector('russian',"
                        "p.structural_path||' '||p.verbatim_text),websearch_to_tsquery('russian',:query)) DESC,"
                        "p.normative_edition_id,p.structural_path "
                        "LIMIT 4"
                    ),
                    {"query": query},
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


def _scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


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


def _search_tokens(query: str) -> tuple[str, ...]:
    tokens = [
        value
        for value in re.findall(r"[0-9A-Za-zА-Яа-яЁё]{3,}", query.lower())
        if value not in _STOP_WORDS
    ]
    lowered = query.lower()
    expansions: list[str] = []
    if "аоср" in lowered or "исполнительн" in lowered:
        expansions.extend(("аоср", "исполнительная", "акт", "комплект"))
    if "смет" in lowered or "ведомост" in lowered or "вор" in lowered:
        expansions.extend(("смета", "ведомость", "объем", "расхождение"))
    if "контрол" in lowered:
        expansions.extend(("контроль", "приемка", "качество"))
    if "восстанов" in lowered:
        expansions.extend(("восстановление", "исходные", "факты"))
    return tuple(dict.fromkeys((*tokens, *expansions)))[:12]


def _search_query(query: str) -> str:
    tokens = _search_tokens(query)
    return " OR ".join(tokens or ("строительство",))


def _locator_score(row: Any, tokens: tuple[str, ...], referenced: set[str]) -> int:
    haystack = f"{row['safe_display_name']} {row['raw_text'] or ''}".lower()
    score = sum(2 for token in tokens if token in haystack)
    if str(row["source_locator_id"]).lower() in referenced:
        score += 1
    return score


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
