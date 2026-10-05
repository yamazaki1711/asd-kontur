from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

_ALLOWED_MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"
_ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
_ALLOWED_PATH = "/v1/rerank"
_REQUEST_TIMEOUT_SECONDS = 30


@dataclass(frozen=True, slots=True)
class RerankedCandidate:
    index: int
    relevance_score: float


def _validate_endpoint(endpoint: str) -> None:
    if not isinstance(endpoint, str):
        raise ValueError("ntd_production_reranker_invalid_endpoint")

    try:
        parts = urllib.parse.urlsplit(endpoint)
        port = parts.port
    except ValueError:
        raise ValueError("ntd_production_reranker_invalid_endpoint") from None

    if parts.scheme != "http":
        raise ValueError("ntd_production_reranker_invalid_endpoint")

    if parts.hostname not in _ALLOWED_HOSTS:
        raise ValueError("ntd_production_reranker_invalid_endpoint")

    if port is None:
        raise ValueError("ntd_production_reranker_invalid_endpoint")

    if parts.path != _ALLOWED_PATH:
        raise ValueError("ntd_production_reranker_invalid_endpoint")

    if parts.query:
        raise ValueError("ntd_production_reranker_invalid_endpoint")

    if parts.fragment:
        raise ValueError("ntd_production_reranker_invalid_endpoint")

    if parts.username is not None:
        raise ValueError("ntd_production_reranker_invalid_endpoint")

    if parts.password is not None:
        raise ValueError("ntd_production_reranker_invalid_endpoint")


def _validate_model_id(model_id: str) -> None:
    if model_id != _ALLOWED_MODEL_ID:
        raise ValueError("ntd_production_reranker_model_not_allowed")


def _normalize_query(query: str) -> str:
    if not isinstance(query, str):
        raise ValueError("ntd_production_reranker_invalid_query")

    normalized = query.strip()
    if not normalized:
        raise ValueError("ntd_production_reranker_invalid_query")

    if len(normalized) > 1000:
        raise ValueError("ntd_production_reranker_invalid_query")

    return normalized


def _normalize_documents(documents: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(documents, tuple):
        raise ValueError("ntd_production_reranker_invalid_documents")

    if not (1 <= len(documents) <= 20):
        raise ValueError("ntd_production_reranker_invalid_documents")

    normalized: list[str] = []
    for doc in documents:
        if not isinstance(doc, str):
            raise ValueError("ntd_production_reranker_invalid_documents")

        stripped = doc.strip()
        if not stripped:
            raise ValueError("ntd_production_reranker_invalid_documents")

        if len(stripped) > 16000:
            raise ValueError("ntd_production_reranker_invalid_documents")

        normalized.append(stripped)

    return tuple(normalized)


def _validate_top_n(top_n: int, doc_count: int) -> None:
    if isinstance(top_n, bool) or not isinstance(top_n, int):
        raise ValueError("ntd_production_reranker_invalid_top_n")

    if not (1 <= top_n <= doc_count):
        raise ValueError("ntd_production_reranker_invalid_top_n")


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _parse_response(
    payload: Any, expected_model: str, top_n: int, doc_count: int
) -> tuple[RerankedCandidate, ...]:
    if not isinstance(payload, dict):
        raise ValueError("ntd_production_reranker_invalid_response")

    if payload.get("model") != expected_model:
        raise ValueError("ntd_production_reranker_invalid_response")

    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("ntd_production_reranker_invalid_response")

    if len(results) != top_n:
        raise ValueError("ntd_production_reranker_invalid_response")

    seen_indexes: set[int] = set()
    candidates: list[RerankedCandidate] = []

    for item in results:
        if not isinstance(item, dict):
            raise ValueError("ntd_production_reranker_invalid_response")

        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("ntd_production_reranker_invalid_response")

        if not (0 <= index < doc_count):
            raise ValueError("ntd_production_reranker_invalid_response")

        if index in seen_indexes:
            raise ValueError("ntd_production_reranker_invalid_response")
        seen_indexes.add(index)

        score = item.get("relevance_score")
        if not _is_finite_number(score):
            raise ValueError("ntd_production_reranker_invalid_response")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError("ntd_production_reranker_invalid_response")

        candidates.append(RerankedCandidate(index=index, relevance_score=float(score)))

    return tuple(candidates)


def rerank_candidates(
    endpoint: str,
    *,
    model_id: str,
    query: str,
    documents: tuple[str, ...],
    top_n: int,
) -> tuple[RerankedCandidate, ...]:
    _validate_endpoint(endpoint)
    _validate_model_id(model_id)
    normalized_query = _normalize_query(query)
    normalized_documents = _normalize_documents(documents)
    _validate_top_n(top_n, len(normalized_documents))

    body = {
        "query": normalized_query,
        "documents": normalized_documents,
        "model": model_id,
        "top_n": top_n,
        "return_documents": False,
    }

    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    try:
        with opener.open(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        raise ValueError("ntd_production_reranker_network_error") from None

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("ntd_production_reranker_invalid_json") from None

    return _parse_response(payload, model_id, top_n, len(normalized_documents))
