from typing import Any

from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.domain import uuid7
from asd_kontur.knowledge.gateway import (
    ASSISTANT_CONTRACT_VERSION,
    ASSISTANT_SCHEMA_ID,
    GatewayContext,
    GatewayRequest,
    GatewayResponse,
    KnowledgeGateway,
)


class _Audit:
    def record(self, **_: Any) -> None:
        pass


class ConstructionConsultantEvidenceCollector:
    def __init__(self, query: ProfessionalAssistantKnowledgeQuery) -> None:
        self._gateway = KnowledgeGateway(query, _Audit())

    def collect(self, owner_identity_id: str, question: str) -> tuple[GatewayResponse, ...]:
        normalized = " ".join(question.split())
        if not (2 <= len(normalized) <= 8000):
            raise ValueError("construction_consultant_question_invalid")

        practice_context = GatewayContext(
            owner_identity_id,
            "consultant.search_practice.invoke",
            "platform_construction_consultant",
            uuid7(),
        )
        ntd_context = GatewayContext(
            owner_identity_id,
            "consultant.search_ntd_content.invoke",
            "platform_construction_consultant",
            uuid7(),
        )

        practice_request = GatewayRequest(
            "consultant.search_practice",
            ASSISTANT_CONTRACT_VERSION,
            ASSISTANT_SCHEMA_ID,
            ASSISTANT_CONTRACT_VERSION,
            {"query": normalized, "limit": 5},
        )
        ntd_request = GatewayRequest(
            "consultant.search_ntd_content",
            ASSISTANT_CONTRACT_VERSION,
            ASSISTANT_SCHEMA_ID,
            ASSISTANT_CONTRACT_VERSION,
            {"query": normalized, "limit": 5},
        )

        practice_response = self._gateway.invoke(practice_request, practice_context)
        ntd_response = self._gateway.invoke(ntd_request, ntd_context)

        return (practice_response, ntd_response)
