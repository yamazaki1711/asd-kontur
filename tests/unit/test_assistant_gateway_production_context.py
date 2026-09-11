# ruff: noqa: RUF001 -- Russian test display name is intentional.

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Engine

from asd_kontur.assistant.gateway import (
    ASSISTANT_TOOL,
    ProfessionalAssistantKnowledgeQuery,
)
from asd_kontur.knowledge.gateway import GatewayContext


def _source(title: str) -> dict[str, Any]:
    return {
        "source_id": f"{title}-source",
        "source_version_id": f"{title}-version",
        "edition_id": None,
        "authority_layer": "normative_authority",
        "title": title,
        "edition": "2026",
        "page": 3,
        "locator_label": "пункт 5.1",
        "fragment": "Контрольный фрагмент.",
        "content_digest": "sha256:" + "1" * 64,
        "href": "/api/v1/platform/sources/source/content#page=3",
        "edition_currency_notice": "Актуальность редакции не проверена",
    }


def test_workspace_context_uses_production_ntd_path_when_endpoint_configured(
    monkeypatch: Any,
) -> None:
    query = ProfessionalAssistantKnowledgeQuery(
        cast(Engine, object()),
        production_embedding_endpoint="http://127.0.0.1:8791/v1/embeddings",
    )
    organization_id = uuid4()
    workspace_id = uuid4()
    calls: list[tuple[str, int]] = []

    monkeypatch.setattr(
        query,
        "_workspace_context",
        lambda organization, workspace, mode, question, *, owner_identity_id=None: {
            "workspace_id": str(workspace),
            "name": "Изолированный ОКС",
            "project_definition": {"purpose": "test"},
            "work_packages": [],
            "requirement_matrix": [],
            "discrepancies": [],
            "mode_result": None,
            "documents": [],
            "source_items": [],
        },
    )
    monkeypatch.setattr(query, "_practice_context", lambda _question, _limit: [])

    def production_content(
        question: str, limit: int, document_id: object = None
    ) -> list[dict[str, Any]]:
        assert document_id is None
        calls.append((question, limit))
        return [
            {
                "content": {"document": "СП 70", "text": "Контрольный фрагмент."},
                "source": _source("СП 70"),
            }
        ]

    monkeypatch.setattr(query, "_search_ntd_content", production_content)
    monkeypatch.setattr(
        query,
        "_normative_context",
        lambda *_args: (_ for _ in ()).throw(AssertionError("legacy NTD path used")),
    )

    response = query.execute(
        ASSISTANT_TOOL,
        {"query": "Как контролировать бетонные работы?", "mode": "Support"},
        GatewayContext(
            "owner-a",
            "assistant.chat.invoke",
            "assistant-test",
            uuid4(),
            organization_id,
            workspace_id,
        ),
    )

    assert calls == [("Как контролировать бетонные работы?", 4)]
    assert response.result["workspace"]["workspace_id"] == str(workspace_id)
    assert response.result["normative_authority"][0]["document"] == "СП 70"
    assert response.evidence_pack.evidence[0].source_version_id == "СП 70-version"
