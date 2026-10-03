import json
from typing import Any

import pytest

from asd_kontur.ntd.rerank_client import RerankedCandidate, rerank_candidates


def test_rerank_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __init__(self) -> None:
            self._payload = (
                b'{"model":"Qwen/Qwen3-Reranker-0.6B","results":'
                b'[{"index":1,"relevance_score":0.95},'
                b'{"index":0,"relevance_score":0.25}]}'
            )

        def read(self) -> bytes:
            return self._payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    class FakeOpener:
        def open(self, request: Any, timeout: float) -> FakeResponse:
            captured["full_url"] = request.full_url
            captured["method"] = request.method
            captured["data"] = request.data
            captured["timeout"] = timeout
            return FakeResponse()

    monkeypatch.setattr(
        "asd_kontur.ntd.rerank_client.urllib.request.build_opener",
        lambda *args, **kwargs: FakeOpener(),
    )

    result = rerank_candidates(
        "http://127.0.0.1:8792/v1/rerank",
        model_id="Qwen/Qwen3-Reranker-0.6B",
        query=" бетонные работы ",
        documents=(" first ", " second "),
        top_n=2,
    )

    assert result == (
        RerankedCandidate(index=1, relevance_score=0.95),
        RerankedCandidate(index=0, relevance_score=0.25),
    )
    assert captured["full_url"] == "http://127.0.0.1:8792/v1/rerank"
    assert captured["method"] == "POST"
    assert captured["timeout"] == 30

    payload = json.loads(captured["data"].decode("utf-8"))
    assert payload["query"] == "бетонные работы"
    assert payload["documents"] == ["first", "second"]
    assert payload["return_documents"] is False


def test_rerank_candidates_rejects_duplicate_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self) -> bytes:
            return self._payload

    class _FakeOpener:
        def open(self, request: Any, timeout: int = 30) -> _FakeResponse:
            payload = {
                "model": "Qwen/Qwen3-Reranker-0.6B",
                "results": [
                    {"index": 0, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.8},
                ],
            }
            return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(
        "asd_kontur.ntd.rerank_client.urllib.request.build_opener",
        lambda *args, **kwargs: _FakeOpener(),
    )

    with pytest.raises(ValueError, match="ntd_production_reranker_invalid_response"):
        rerank_candidates(
            "http://localhost:8792/v1/rerank",
            model_id="Qwen/Qwen3-Reranker-0.6B",
            query="concrete",
            documents=("a", "b"),
            top_n=2,
        )
