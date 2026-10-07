"""A semantic search hit must carry separately citable table cells."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Engine

from asd_kontur.assistant import gateway
from asd_kontur.assistant.worker import _bounded_workspace_search_prompt_result


def test_search_carries_bounded_same_row_context_without_crossing_source(
    monkeypatch: Any,
) -> None:
    organization_id = uuid4()
    workspace_id = uuid4()
    source_version_id = uuid4()
    description_id = uuid4()
    quantity_id = uuid4()
    description = {
        "source_locator_id": description_id,
        "source_version_id": source_version_id,
        "locator_value": "page:7:row:3:column:2",
        "fragment_digest": "sha256:" + "1" * 64,
        "safe_display_name": "Schedule B",
        "raw_text": "Install a steel service pipe, outer diameter 144 mm",
        "page_number": 7,
        "reading_order": 13,
        "row_index": 3,
        "column_index": 2,
        "rank": 0.9,
    }
    quantity = {
        **description,
        "source_locator_id": quantity_id,
        "locator_value": "page:7:row:3:column:4",
        "fragment_digest": "sha256:" + "2" * 64,
        "raw_text": "86 m",
        "reading_order": 15,
        "column_index": 4,
    }

    class Result:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self.rows = rows

        def one(self) -> tuple[str, str]:
            return (str(organization_id), str(workspace_id))

        def mappings(self) -> list[dict[str, Any]]:
            return self.rows

    class Session:
        def __init__(self, _engine: Any) -> None:
            pass

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

        def begin(self) -> Session:
            return self

        def execute(self, query: Any, params: dict[str, Any] | None = None) -> Result:
            sql = str(query)
            if "set_config" in sql:
                return Result([])
            assert params is not None
            assert params["o"] == organization_id
            assert params["w"] == workspace_id
            if "WITH candidates" in sql:
                return Result([description])
            assert params["source_version"] == source_version_id
            assert params["page"] == 7
            assert params["row_index"] == 3
            return Result([description, quantity])

    monkeypatch.setattr(gateway, "Session", Session)
    query = gateway.ProfessionalAssistantKnowledgeQuery(cast(Engine, object()))
    items = query._workspace_search(organization_id, workspace_id, "Tender", "service pipe", 3)

    assert [item["source"]["source_id"] for item in items] == [
        str(description_id),
        str(quantity_id),
    ]
    assert items[1]["content"]["fragment"] == "86 m"
    assert items[1]["content"]["table_row"] == 3
    assert items[1]["content"]["table_column"] == 4


def test_search_prompt_retains_all_primary_matches_before_optional_context() -> None:
    matches = [
        {"source_id": str(uuid4()), "fragment": f"Element {number}", "search_match": True}
        for number in range(4)
    ]
    context = [
        {
            "source_id": str(uuid4()),
            "fragment": "unrelated neighboring text " * 15,
            "search_match": False,
        }
        for _ in range(12)
    ]
    result = _bounded_workspace_search_prompt_result(
        {"outcome": "found", "items": [*matches, *context]}, 550
    )

    assert result["matches"] == matches
    assert len(result["row_context"]) < len(context)


def test_search_prompt_bounds_long_native_fragment_without_losing_identity() -> None:
    source_id = str(uuid4())
    result = _bounded_workspace_search_prompt_result(
        {
            "outcome": "found",
            "items": [
                {
                    "source_id": source_id,
                    "document": "Drawing Q",
                    "page": 9,
                    "fragment": "long source text " * 1000,
                    "search_match": True,
                }
            ],
        },
        1200,
    )

    assert result["matches"][0]["source_id"] == source_id
    assert len(result["matches"][0]["fragment"]) == 700
