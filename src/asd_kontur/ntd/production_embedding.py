from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingProfile:
    key: str
    version: str
    dimension: int


def embed_query(
    endpoint: str,
    profile: EmbeddingProfile,
    query: str,
) -> tuple[float, ...]:
    q = query.strip()
    if not q or len(q) > 1000:
        raise ValueError("ntd_production_embedding_invalid_query")
    if profile.dimension <= 0:
        raise ValueError("ntd_production_embedding_invalid_dimension")

    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme != "http":
        raise ValueError("ntd_production_embedding_invalid_scheme")
    if parsed.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("ntd_production_embedding_invalid_host")
    if parsed.port is None:
        raise ValueError("ntd_production_embedding_missing_port")
    if parsed.path != "/v1/embeddings":
        raise ValueError("ntd_production_embedding_invalid_path")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("ntd_production_embedding_invalid_url_parts")

    payload = json.dumps({"profile": profile.key, "texts": [q]}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=30) as resp:
            body = resp.read()
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ValueError("ntd_production_embedding_network_error") from e

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError("ntd_production_embedding_invalid_json") from e

    if not isinstance(data, dict):
        raise ValueError("ntd_production_embedding_invalid_response_type")

    if data.get("profile_key") != profile.key:
        raise ValueError("ntd_production_embedding_profile_key_mismatch")
    if data.get("profile_version") != profile.version:
        raise ValueError("ntd_production_embedding_profile_version_mismatch")
    if data.get("dimension") != profile.dimension:
        raise ValueError("ntd_production_embedding_dimension_mismatch")

    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != 1:
        raise ValueError("ntd_production_embedding_invalid_embeddings_count")

    vector = embeddings[0]
    if not isinstance(vector, list) or len(vector) != profile.dimension:
        raise ValueError("ntd_production_embedding_invalid_vector_length")

    result = []
    for val in vector:
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError("ntd_production_embedding_invalid_vector_type")
        if not math.isfinite(val):
            raise ValueError("ntd_production_embedding_invalid_vector_value")
        result.append(float(val))

    return tuple(result)
