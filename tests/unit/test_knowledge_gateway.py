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
from asd_kontur.knowledge.gateway import (
    GUIDANCE_CONTRACT_VERSION,
    GUIDANCE_SCHEMA_ID,
    GUIDANCE_TOOLS,
    HARNESS_CONTRACT_VERSION,
    HARNESS_SCHEMA_ID,
    HARNESS_TOOLS,
    NTD_CONTRACT_VERSION,
    NTD_SCHEMA_ID,
    NTD_TOOLS,
    TOOLS,
    EvidencePack,
    GatewayStatus,
)

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
def test_all_allowlisted_tools_require_exact_capability_and_version(tool: str) -> None:
    audit = AuditSpy()
    gateway = KnowledgeGateway(QueryStub(), audit)
    if tool in HARNESS_TOOLS:
        contract_version = HARNESS_CONTRACT_VERSION
        schema_id = HARNESS_SCHEMA_ID
    elif tool in GUIDANCE_TOOLS:
        contract_version = GUIDANCE_CONTRACT_VERSION
        schema_id = GUIDANCE_SCHEMA_ID
    elif tool in NTD_TOOLS:
        contract_version = NTD_CONTRACT_VERSION
        schema_id = NTD_SCHEMA_ID
    else:
        contract_version = "0.1.0"
        schema_id = SCHEMA_ID
    response = gateway.invoke(
        GatewayRequest(tool, contract_version, schema_id, contract_version, {}),
        GatewayContext("human", f"{tool}.invoke", "qualification", uuid7()),
    )
    assert response.tool == tool
    assert response.status is GatewayStatus.NO_RESULT
    assert audit.records == [(tool, str(GatewayStatus.NO_RESULT))]


def test_ntd_gateway_contract_rejects_unpinned_version() -> None:
    audit = AuditSpy()
    gateway = KnowledgeGateway(QueryStub(), audit)
    with pytest.raises(KnowledgeError):
        gateway.invoke(
            GatewayRequest(
                "knowledge.resolve_ntd",
                "latest",
                NTD_SCHEMA_ID,
                "latest",
                {"identifier": "СП 543.1325800.2024", "as_of": "2026-08-25"},
            ),
            GatewayContext("human", "knowledge.resolve_ntd.invoke", "normative_context", uuid7()),
        )


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
