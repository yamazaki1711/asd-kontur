from typing import cast

import pytest

from asd_kontur.assistant.construction_consultant_evidence import (
    ConstructionConsultantEvidenceCollector,
)
from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.knowledge.gateway import (
    ASSISTANT_CONTRACT_VERSION,
    ASSISTANT_SCHEMA_ID,
    GatewayContext,
    GatewayRequest,
    GatewayResponse,
    KnowledgeGateway,
)


def test_collect_evidence_builds_platform_scoped_gateway_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_requests: list[GatewayRequest] = []
    recorded_contexts: list[GatewayContext] = []

    def fake_invoke(
        self: KnowledgeGateway, request: GatewayRequest, context: GatewayContext
    ) -> GatewayResponse:
        recorded_requests.append(request)
        recorded_contexts.append(context)
        return cast(GatewayResponse, object())

    monkeypatch.setattr(
        "asd_kontur.assistant.construction_consultant_evidence.KnowledgeGateway.invoke",
        fake_invoke,
    )

    collector = ConstructionConsultantEvidenceCollector(
        cast(ProfessionalAssistantKnowledgeQuery, object())
    )
    responses = collector.collect("owner-a", "  бетонные   работы ")

    assert len(responses) == 2

    # Check first request (practice)
    req1 = recorded_requests[0]
    ctx1 = recorded_contexts[0]
    assert req1.tool == "consultant.search_practice"
    assert req1.contract_version == ASSISTANT_CONTRACT_VERSION
    assert req1.schema_id == ASSISTANT_SCHEMA_ID
    assert req1.schema_version == ASSISTANT_CONTRACT_VERSION
    assert req1.payload == {"query": "бетонные работы", "limit": 5}
    assert ctx1.actor_identity_id == "owner-a"
    assert ctx1.capability == "consultant.search_practice.invoke"
    assert ctx1.purpose == "platform_construction_consultant"
    assert ctx1.workspace_id is None
    assert ctx1.organization_id is None

    # Check second request (ntd)
    req2 = recorded_requests[1]
    ctx2 = recorded_contexts[1]
    assert req2.tool == "consultant.search_ntd_content"
    assert req2.contract_version == ASSISTANT_CONTRACT_VERSION
    assert req2.schema_id == ASSISTANT_SCHEMA_ID
    assert req2.schema_version == ASSISTANT_CONTRACT_VERSION
    assert req2.payload == {"query": "бетонные работы", "limit": 5}
    assert ctx2.actor_identity_id == "owner-a"
    assert ctx2.capability == "consultant.search_ntd_content.invoke"
    assert ctx2.purpose == "platform_construction_consultant"
    assert ctx2.workspace_id is None
    assert ctx2.organization_id is None


def test_collect_evidence_rejects_invalid_question() -> None:
    collector = ConstructionConsultantEvidenceCollector(
        cast(ProfessionalAssistantKnowledgeQuery, object())
    )
    with pytest.raises(ValueError, match="construction_consultant_question_invalid"):
        collector.collect("owner-a", " ")
