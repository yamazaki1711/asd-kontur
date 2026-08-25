"""Typed Construction Harness tools behind the common Knowledge Gateway."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.knowledge.gateway import (
    HARNESS_CONTRACT_VERSION,
    EvidenceItem,
    EvidencePack,
    GatewayContext,
    GatewayResponse,
    GatewayStatus,
)

from .models import ConstructionHarnessContextPack, HarnessError, HarnessErrorCode


class ConstructionHarnessQueryService:
    """Read-only exact-version query port; it exposes no SQL surface."""

    def __init__(
        self,
        context_packs: Mapping[UUID, ConstructionHarnessContextPack],
    ) -> None:
        self._context_packs = context_packs

    def execute(
        self, tool: str, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        if context.organization_id is None or context.workspace_id is None:
            raise HarnessError(
                HarnessErrorCode.SCOPE_VIOLATION,
                "Construction Harness retrieval requires exact workspace scope",
            )
        context_pack_id = UUID(str(payload["context_pack_id"]))
        pack = self._context_packs.get(context_pack_id)
        if pack is None:
            return _response(tool, GatewayStatus.NO_RESULT, {}, gaps=({"code": "no_result"},))
        if (pack.organization_id, pack.workspace_id) != (
            context.organization_id,
            context.workspace_id,
        ):
            raise HarnessError(
                HarnessErrorCode.SCOPE_VIOLATION,
                "Harness context cannot cross a workspace boundary",
            )
        if tool == "knowledge.get_construction_harness_context":
            result: dict[str, Any] = {
                "context_pack_id": str(pack.context_pack_id),
                "contract_version": pack.contract_version,
                "project_definition_ref": tuple(str(item) for item in pack.project_definition_ref),
                "matrix_ref": tuple(str(item) for item in pack.matrix_ref),
                "matrix_fingerprint": pack.matrix_fingerprint,
                "authority_layers": {
                    "workspace_facts": pack.workspace_fact_refs,
                    "methodological_practice": pack.practice_intelligence_refs,
                    "normative_authority": pack.normative_provision_refs,
                    "deterministic_rules": pack.active_rule_version_refs,
                    "customer_regulation_additions": pack.customer_addition_refs,
                },
            }
        elif tool == "knowledge.trace_work_requirement":
            result = {
                "matrix_ref": tuple(str(item) for item in pack.matrix_ref),
                "matrix_fingerprint": pack.matrix_fingerprint,
                "source_evidence": tuple(asdict(item) for item in pack.source_evidence),
            }
        else:
            return _response(tool, GatewayStatus.NO_RESULT, {}, gaps=({"code": "unknown_tool"},))
        status = GatewayStatus.KNOWLEDGE_INCOMPLETE if pack.knowledge_gaps else GatewayStatus.OK
        return _response(
            tool,
            status,
            result,
            evidence=tuple(
                EvidenceItem(
                    str(item.evidence_link_id),
                    str(item.source_version_id),
                    None,
                    item.locator,
                    item.content_digest,
                    f"knowledge://workspace-source/{item.source_version_id}/{item.locator}",
                    "workspace_fact",
                )
                for item in pack.source_evidence
            ),
            gaps=pack.knowledge_gaps,
        )


class PostgresConstructionHarnessQueryService:
    """Read immutable ContextPack versions through scoped PostgreSQL RLS."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def execute(
        self, tool: str, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        if context.organization_id is None or context.workspace_id is None:
            raise HarnessError(
                HarnessErrorCode.SCOPE_VIOLATION,
                "Construction Harness retrieval requires exact workspace scope",
            )
        pack_id = UUID(str(payload["context_pack_id"]))
        with Session(self._engine) as session:
            session.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(context.organization_id), True),
                    sa.func.set_config("asd.workspace_id", str(context.workspace_id), True),
                )
            ).one()
            row = (
                session.execute(
                    sa.text(
                        "SELECT context_pack,matrix_id,matrix_version,matrix_fingerprint "
                        "FROM workspace.construction_harness_context_packs "
                        "WHERE context_pack_id=:pack"
                    ),
                    {"pack": pack_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return _response(tool, GatewayStatus.NO_RESULT, {}, gaps=({"code": "no_result"},))
        document = row["context_pack"]
        if not isinstance(document, dict):
            return _response(
                tool,
                GatewayStatus.KNOWLEDGE_INCOMPLETE,
                {},
                gaps=({"code": "persisted_context_invalid"},),
            )
        gaps = tuple(item for item in document.get("knowledge_gaps", []) if isinstance(item, dict))
        source_rows = tuple(
            item for item in document.get("source_evidence", []) if isinstance(item, dict)
        )
        evidence = tuple(
            EvidenceItem(
                str(item["evidence_link_id"]),
                str(item["source_version_id"]),
                None,
                str(item["locator"]),
                str(item["content_digest"]),
                f"knowledge://workspace-source/{item['source_version_id']}/{item['locator']}",
                "workspace_fact",
            )
            for item in source_rows
        )
        if tool == "knowledge.get_construction_harness_context":
            result: dict[str, Any] = {
                "context_pack_id": str(pack_id),
                "contract_version": document.get("contract_version"),
                "project_definition_ref": document.get("project_definition_ref"),
                "matrix_ref": document.get("matrix_ref"),
                "matrix_fingerprint": row["matrix_fingerprint"],
                "authority_layers": {
                    "workspace_facts": document.get("workspace_fact_refs", []),
                    "methodological_practice": document.get("practice_intelligence_refs", []),
                    "normative_authority": document.get("normative_provision_refs", []),
                    "deterministic_rules": document.get("active_rule_version_refs", []),
                    "customer_regulation_additions": document.get("customer_addition_refs", []),
                },
            }
        elif tool == "knowledge.trace_work_requirement":
            result = {
                "matrix_ref": [str(row["matrix_id"]), row["matrix_version"]],
                "matrix_fingerprint": row["matrix_fingerprint"],
                "source_evidence": source_rows,
            }
        else:
            return _response(tool, GatewayStatus.NO_RESULT, {}, gaps=({"code": "unknown_tool"},))
        return _response(
            tool,
            GatewayStatus.KNOWLEDGE_INCOMPLETE if gaps else GatewayStatus.OK,
            result,
            evidence=evidence,
            gaps=gaps,
        )


def _response(
    tool: str,
    status: GatewayStatus,
    result: dict[str, Any],
    *,
    evidence: tuple[EvidenceItem, ...] = (),
    gaps: tuple[dict[str, Any], ...] = (),
) -> GatewayResponse:
    return GatewayResponse(
        tool,
        HARNESS_CONTRACT_VERSION,
        status,
        result,
        EvidencePack(evidence, (), (), gaps, ()),
    )
