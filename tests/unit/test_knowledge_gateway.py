from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from asd_kontur.domain import uuid7
from asd_kontur.knowledge import (
    GatewayContext,
    GatewayRequest,
    GatewayResponse,
    KnowledgeError,
    KnowledgeGateway,
)
from asd_kontur.knowledge.gateway import TOOLS, EvidencePack, GatewayStatus

SCHEMA_ID = "urn:asd-kontur:contracts:v0.1:schema:rules-knowledge"


class QueryStub:
    def execute(
        self, tool: str, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse:
        return GatewayResponse(
            tool, "0.1.0", GatewayStatus.NO_RESULT, payload, EvidencePack((), (), (), (), ())
        )


@dataclass
class AuditSpy:
    records: list[tuple[str, str]] = field(default_factory=list)

    def record(
        self,
        *,
        context: GatewayContext,
        tool: str,
        status: GatewayStatus | str,
        evidence_count: int,
    ) -> None:
        self.records.append((tool, str(status)))


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_all_six_tools_require_exact_capability_and_version(tool: str) -> None:
    audit = AuditSpy()
    gateway = KnowledgeGateway(QueryStub(), audit)
    response = gateway.invoke(
        GatewayRequest(tool, "0.1.0", SCHEMA_ID, "0.1.0", {}),
        GatewayContext("human", f"{tool}.invoke", "qualification", uuid7()),
    )
    assert response.tool == tool
    assert response.status is GatewayStatus.NO_RESULT
    assert audit.records == [(tool, str(GatewayStatus.NO_RESULT))]


def test_access_denied_is_explicit_and_audited() -> None:
    audit = AuditSpy()
    gateway = KnowledgeGateway(QueryStub(), audit)
    with pytest.raises(KnowledgeError):
        gateway.invoke(
            GatewayRequest("knowledge.search", "0.1.0", SCHEMA_ID, "0.1.0", {}),
            GatewayContext("model", "wrong", "qualification", uuid7()),
        )
    assert audit.records == [("knowledge.search", "access_denied")]


def test_partial_workspace_scope_is_rejected() -> None:
    with pytest.raises(KnowledgeError):
        GatewayContext(
            "human",
            "knowledge.search.invoke",
            "qualification",
            uuid7(),
            organization_id=uuid7(),
        )
