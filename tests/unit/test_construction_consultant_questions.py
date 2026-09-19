from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from asd_kontur.assistant.construction_consultant_postgres import (
    ConstructionConsultantMessage,
)
from asd_kontur.assistant.construction_consultant_questions import (
    ConstructionConsultantQuestionError,
    ConstructionConsultantQuestionService,
    _prompt,
)
from asd_kontur.knowledge.gateway import (
    EvidenceItem,
    EvidencePack,
    GatewayResponse,
    GatewayStatus,
)

OWNER = "consultant-owner"
ORGANIZATION_ID = UUID("11111111-1111-1111-1111-111111111111")
CONVERSATION_ID = UUID("22222222-2222-2222-2222-222222222222")
REQUEST_ID = UUID("33333333-3333-3333-3333-333333333333")


class HistoryStub:
    def __init__(self) -> None:
        self.history: tuple[ConstructionConsultantMessage, ...] = ()

    def organization_id(self, owner_identity_id: str) -> UUID:
        assert owner_identity_id == OWNER
        return ORGANIZATION_ID

    def messages(
        self, owner_identity_id: str, conversation_id: UUID
    ) -> tuple[ConstructionConsultantMessage, ...]:
        assert owner_identity_id == OWNER
        assert conversation_id == CONVERSATION_ID
        return self.history


class RepositoryStub:
    def __init__(self) -> None:
        self.persisted: list[ConstructionConsultantMessage] = []

    def messages_for_request(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        owner_identity_id: str,
        request_id: UUID,
    ) -> tuple[ConstructionConsultantMessage, ...]:
        assert (organization_id, conversation_id, owner_identity_id, request_id) == (
            ORGANIZATION_ID,
            CONVERSATION_ID,
            OWNER,
            REQUEST_ID,
        )
        return tuple(item for item in self.persisted if item.request_id == request_id)

    def append_message(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        owner_identity_id: str,
        role: str,
        content: str,
        *,
        sources: tuple[dict[str, Any], ...] = (),
        model_identity: str | None = None,
        model_profile_version: str | None = None,
        request_id: UUID | None = None,
    ) -> ConstructionConsultantMessage:
        assert (organization_id, conversation_id, owner_identity_id) == (
            ORGANIZATION_ID,
            CONVERSATION_ID,
            OWNER,
        )
        message = ConstructionConsultantMessage(
            message_id=UUID(int=len(self.persisted) + 1),
            conversation_id=conversation_id,
            request_id=request_id,
            ordinal=len(self.persisted) + 1,
            role=role,
            content=content,
            sources=sources,
            model_identity=model_identity,
            model_profile_version=model_profile_version,
            created_at=datetime(2026, 9, 10, tzinfo=UTC),
        )
        self.persisted.append(message)
        return message


class CollectorStub:
    def collect(self, owner_identity_id: str, question: str) -> tuple[GatewayResponse, ...]:
        assert owner_identity_id == OWNER
        assert question == "Какой уход нужен бетону?"
        item = EvidenceItem(
            "evidence-1",
            "source-version-1",
            None,
            "page:4/section:3",
            "sha256:" + "a" * 64,
            "source://sp70/page/4",
        )
        return (
            GatewayResponse(
                "consultant.search_ntd_content",
                "2.9.0",
                GatewayStatus.OK,
                {
                    "items": [{"text": "Уход за бетоном"}],
                    "sources": [
                        {
                            "source_version_id": "source-version-1",
                            "title": "СП 70.13330.2012 — Несущие и ограждающие конструкции",
                            "href": "/api/v1/platform/sources/source-version-1/content#page=4",
                            "edition": "2012",
                            "fragment": "Уход за бетоном",
                        }
                    ],
                },
                EvidencePack((item,), (), (), (), ()),
            ),
        )


class ModelStub:
    def __init__(self, answer: str = "Поддерживайте влажностный уход.") -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer


def _service(repository: RepositoryStub, model: ModelStub) -> ConstructionConsultantQuestionService:
    return ConstructionConsultantQuestionService(HistoryStub(), repository, CollectorStub(), model)


def test_question_persists_completed_answer_with_evidence_and_reuses_request() -> None:
    repository = RepositoryStub()
    model = ModelStub()
    service = _service(repository, model)

    first = service.ask(
        owner_identity_id=OWNER,
        conversation_id=CONVERSATION_ID,
        request_id=REQUEST_ID,
        question="Какой уход нужен бетону?",
    )
    repeated = service.ask(
        owner_identity_id=OWNER,
        conversation_id=CONVERSATION_ID,
        request_id=REQUEST_ID,
        question="Какой уход нужен бетону?",
    )

    assert [item.role for item in repository.persisted] == ["user", "assistant"]
    assert first.assistant_message.sources == (
        {
            "source_id": "source-version-1",
            "locator": "page:4/section:3",
            "access_reference": "source://sp70/page/4",
            "authority_layer": "normative_or_canonical_knowledge",
            "tool": "consultant.search_ntd_content",
            "title": "СП 70.13330.2012 — Несущие и ограждающие конструкции",
            "href": "/api/v1/platform/sources/source-version-1/content#page=4",
            "edition": "2012",
            "fragment": "Уход за бетоном",
        },
    )
    assert first.evidence_statuses == ("ok",)
    assert repeated == replace(first, evidence_statuses=())
    assert len(model.prompts) == 1
    assert "source://sp70/page/4" in model.prompts[0]


def test_question_does_not_persist_messages_when_inference_fails() -> None:
    class FailingModel:
        def complete(self, prompt: str) -> str:
            del prompt
            raise ConstructionConsultantQuestionError(
                "construction_consultant_inference_unavailable"
            )

    repository = RepositoryStub()
    service = ConstructionConsultantQuestionService(
        HistoryStub(), repository, CollectorStub(), FailingModel()
    )

    with pytest.raises(ConstructionConsultantQuestionError) as exc_info:
        service.ask(
            owner_identity_id=OWNER,
            conversation_id=CONVERSATION_ID,
            request_id=REQUEST_ID,
            question="Какой уход нужен бетону?",
        )

    assert exc_info.value.code == "construction_consultant_inference_unavailable"
    assert repository.persisted == []


def test_prompt_keeps_later_evidence_identity_after_long_tool_metadata() -> None:
    def response(source_id: str, locator: str, fragment: str) -> GatewayResponse:
        return GatewayResponse(
            "consultant.search_ntd_content",
            "2.9.0",
            GatewayStatus.OK,
            {
                "outcome": "found",
                "items": [{"text": fragment}],
                "metadata": "x" * 50_000,
                "sources": [
                    {
                        "source_version_id": source_id,
                        "title": f"Source {source_id}",
                        "href": f"source://{source_id}",
                        "fragment": fragment,
                    }
                ],
            },
            EvidencePack(
                (
                    EvidenceItem(
                        source_id,
                        source_id,
                        None,
                        locator,
                        "sha256:" + "a" * 64,
                        f"source://{source_id}",
                    ),
                ),
                (),
                (),
                (),
                (),
            ),
        )

    prompt = _prompt(
        "Какие документы требуют проверки?",
        (),
        (response("source-1", "page:1", "first"), response("source-2", "page:77", "second")),
    )

    assert "source-1" in prompt
    assert "source-2" in prompt
    assert "page:77" in prompt
    assert "source://source-2" in prompt
    assert '"metadata"' not in prompt
    assert '"truncated":true' not in prompt
