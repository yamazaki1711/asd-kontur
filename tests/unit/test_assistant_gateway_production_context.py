# ruff: noqa: RUF001 -- Russian test display name is intentional.

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Engine

from asd_kontur.assistant.gateway import (
    ASSISTANT_TOOL,
    ProfessionalAssistantKnowledgeQuery,
    _project_pit_unresolved_inventory,
    _public_inventory_candidate,
    _select_facility_work_candidates,
    _semantic_coverage_complete,
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


def test_semantic_coverage_complete_uses_the_project_view_state_contract() -> None:
    assert _semantic_coverage_complete([]) is False
    assert _semantic_coverage_complete([{"state": "complete"}]) is True
    assert (
        _semantic_coverage_complete(
            [{"state": "complete"}, {"state": "partial", "status": "complete"}]
        )
        is False
    )
    assert _semantic_coverage_complete([{"status": "complete"}]) is False


def test_public_inventory_candidate_preserves_evidence_sources_not_internal_ids() -> None:
    source_id = uuid4()
    candidate = _public_inventory_candidate(
        {
            "identity_candidate_id": uuid4(),
            "member_structure_node_ids": [uuid4()],
            "source_locator_ids": [source_id],
            "canonical_label": "Котлован К-1",
            "status": "candidate",
        }
    )

    assert candidate == {
        "canonical_label": "Котлован К-1",
        "status": "требует подтверждения",
        "source_ids": [str(source_id)],
    }


def test_pit_inventory_preserves_dispositions_and_full_unresolved_denominator() -> None:
    rows, total, coverage, complete = _project_pit_unresolved_inventory(
        {
            "unresolved_observations": [
                {
                    "node_kind": "excavation_pit",
                    "raw_name": "Котлован",
                    "pit_observation_disposition": "generic_mention",
                    "pit_observation_reason_code": "GENERIC_CONTEXT",
                },
                {
                    "node_kind": "excavation_pit",
                    "raw_name": "Скважина 7",
                    "pit_observation_disposition": "non_pit",
                    "pit_observation_reason_code": "EXPLORATION_BOREHOLE",
                },
            ],
            "coverage": {
                "unresolved_observation_count": 7,
                "returned_unresolved_observation_count": 2,
                "disposition_counts": {"generic_mention": 3, "non_pit": 4},
                "exact_total_supported": False,
            },
        },
        query="",
    )

    assert total == 7
    assert complete is False
    assert coverage["disposition_counts"] == {"generic_mention": 3, "non_pit": 4}
    assert [row["pit_observation_disposition"] for row in rows] == [
        "generic_mention",
        "non_pit",
    ]


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


def test_workspace_work_packages_keep_their_own_source_evidence(monkeypatch: Any) -> None:
    query = ProfessionalAssistantKnowledgeQuery(cast(Engine, object()))
    organization_id = uuid4()
    workspace_id = uuid4()
    package_source = _source("Лист работ")
    package_source["authority_layer"] = "workspace_fact"

    def workspace_context(
        organization: object,
        workspace: object,
        mode: object,
        question: object,
        *,
        work_package_limit: int = 20,
        owner_identity_id: str | None = None,
    ) -> dict[str, Any]:
        assert organization == organization_id
        assert mode == "Tender"
        assert question == "разработка грунта"
        assert work_package_limit == 20
        assert owner_identity_id == "owner-a"
        return {
            "workspace_id": str(workspace),
            "name": "Изолированный ОКС",
            "project_definition": {"purpose": "test"},
            "work_packages": [{"package": {"work_type": {"raw": "Разработка грунта"}}}],
            "work_package_selection": {
                "query": "разработка грунта",
                "selection": "lexical_relevance",
                "total_observation_count": 31,
                "matched_observation_count": 1,
                "returned_observation_count": 1,
                "exhaustive_for_query": True,
                "authority": "candidate_observations_not_confirmed_work_packages",
            },
            "facility_work_candidate_groups": [
                {
                    "facility_work_candidate_id": "sha256:" + "2" * 64,
                    "identity_label": "КНС-1",
                    "work_type": {"raw": "Разработка грунта"},
                    "candidate_state": "facility_work_candidate_not_confirmed",
                }
            ],
            "facility_work_selection": {
                "query": "разработка грунта",
                "matched_candidate_group_count": 1,
                "returned_candidate_group_count": 1,
                "authority": "candidate_association_not_confirmed_scope",
            },
            "requirement_matrix": {},
            "discrepancies": [],
            "mode_result": None,
            "documents": [],
            "structure_dossiers": [],
            "materialization": {"state": "partial"},
            "source_items": [],
            "overview_source_items": [],
            "work_package_source_items": [{"source": package_source}],
            "discrepancy_source_items": [],
            "gap_source_items": [],
        }

    monkeypatch.setattr(query, "_workspace_context", workspace_context)

    response = query.execute(
        "consultant.get_work_packages",
        {"mode": "Tender", "query": "разработка грунта", "limit": 20},
        GatewayContext(
            "owner-a",
            "assistant.chat.invoke",
            "assistant-test",
            uuid4(),
            organization_id,
            workspace_id,
        ),
    )

    assert response.result["value"]["work_packages"][0]["package"]["work_type"]["raw"] == (
        "Разработка грунта"
    )
    assert response.result["value"]["selection_coverage"]["total_observation_count"] == 31
    assert response.result["value"]["selection_coverage"]["exhaustive_for_query"] is True
    assert (
        response.result["value"]["facility_work_candidate_groups"][0]["identity_label"] == "КНС-1"
    )
    assert (
        response.result["value"]["facility_work_selection_coverage"][
            "matched_candidate_group_count"
        ]
        == 1
    )
    assert response.evidence_pack.evidence[0].evidence_link_id == "Лист работ-source"
    assert response.evidence_pack.evidence[0].authority_layer == "workspace_fact"


def test_facility_work_candidate_selection_matches_facility_without_name_merging() -> None:
    groups = [
        {
            "facility_work_candidate_id": "candidate-kns",
            "identity_label": "КНС-1",
            "identity_kind": "facility",
            "work_type": {"raw": "Разработка грунта", "normalized": "разработка грунта"},
        },
        {
            "facility_work_candidate_id": "candidate-los",
            "identity_label": "ЛОС-1",
            "identity_kind": "facility",
            "work_type": {"raw": "Разработка грунта", "normalized": "разработка грунта"},
        },
    ]

    selected, coverage = _select_facility_work_candidates(
        groups,
        query="Какие работы предусмотрены для КНС-1?",
        limit=20,
        projection_coverage={"exact_identity_package_count": 2},
    )

    assert [item["facility_work_candidate_id"] for item in selected] == ["candidate-kns"]
    assert coverage == {
        "query": "Какие работы предусмотрены для КНС-1?",
        "selection": "facility_designation_and_lexical_relevance",
        "total_candidate_group_count": 2,
        "matched_candidate_group_count": 1,
        "returned_candidate_group_count": 1,
        "exhaustive_for_query": True,
        "projection_coverage": {"exact_identity_package_count": 2},
        "authority": "candidate_association_not_confirmed_scope",
    }


def test_project_entity_inventory_returns_coverage_and_workspace_sources(monkeypatch: Any) -> None:
    query = ProfessionalAssistantKnowledgeQuery(cast(Engine, object()))
    organization_id = uuid4()
    workspace_id = uuid4()
    source = _source("Лист котлована")
    source["authority_layer"] = "workspace_fact"
    monkeypatch.setattr(
        query,
        "_project_entity_inventory",
        lambda **_kwargs: (
            {
                "authority": "cross_document_identity_candidates_not_confirmed_facts",
                "candidate_entity_count": 2,
                "unresolved_observation_count": 1,
                "coverage": {"exact_total_supported": False},
            },
            [source],
        ),
    )

    response = query.execute(
        "consultant.get_project_entity_inventory",
        {"mode": "Tender", "kind": "excavation_pit", "limit": 30},
        GatewayContext(
            "owner-a",
            "assistant.chat.invoke",
            "assistant-test",
            uuid4(),
            organization_id,
            workspace_id,
        ),
    )

    assert response.result["value"]["candidate_entity_count"] == 2
    assert response.result["value"]["coverage"]["exact_total_supported"] is False
    assert response.evidence_pack.evidence[0].authority_layer == "workspace_fact"
