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
        del context
        handlers = {
            "knowledge.resolve_ntd": self._resolve_ntd,
            "knowledge.get_ntd_document": self._get_document,
            "knowledge.get_ntd_edition": self._get_edition,
            "knowledge.get_ntd_provision": self._get_provision,
            "knowledge.search_ntd": self._search,
            "knowledge.get_ntd_evidence_pack": self._get_evidence_pack,
            "knowledge.get_practice_ntd_alignment": self._get_alignment,
        }
        handler = handlers.get(tool)
        if handler is None:
            return self._response(
                tool, GatewayStatus.NO_RESULT, {}, gaps=(self._gap("unknown_tool"),)
            )
        return handler(tool, payload)

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
                        "a.normative_artifact_id FROM platform.normative_provision_versions p "
                        "JOIN platform.normative_artifacts a ON a.source_version_id=p.source_version_id "
                        "WHERE p.normative_edition_id=:edition AND p.structural_path=:locator "
                        "AND p.verification_status='verified' ORDER BY p.version DESC LIMIT 2"
                    ),
                    {"edition": edition_id, "locator": locator},
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
        evidence = EvidenceItem(
            evidence_link_id=f"ntd:{row['normative_provision_id']}:{row['version']}",
            source_version_id=str(row["source_version_id"]),
            edition_id=str(row["normative_edition_id"]),
            structural_unit_locator=str(row["structural_path"]),
            content_digest=str(row["content_digest"]),
            access_reference=str(row["official_url"]),
            authority_layer="normative_authority",
        )
        return self._response(
            tool,
            GatewayStatus.OK,
            {
                "authority_layer": "normative_authority",
                "provision": _json_row(row),
                "practice_recommendation": None,
                "deterministic_rule_version": None,
            },
            evidence=(evidence,),
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
        return self._response(
            tool, GatewayStatus.OK, {"alignments": [_json_row(row) for row in rows]}
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
            contract_version=NTD_CONTRACT_VERSION,
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
        return f"ПРИКАЗ МИНСТРОЯ РОССИИ № {value.removeprefix('order:').replace('-pr', '/ПР')}"
    if namespace == "instruction":
        return f"И {value}"
    return stable_identity_key
