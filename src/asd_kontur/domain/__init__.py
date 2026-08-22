"""Transport- and persistence-independent domain primitives."""

from .identifiers import (
    SEMANTIC_NAMESPACE_V1,
    canonical_semantic_key,
    deterministic_uuid,
    uuid7,
    uuid7_from_parts,
)

__all__ = [
    "SEMANTIC_NAMESPACE_V1",
    "canonical_semantic_key",
    "deterministic_uuid",
    "uuid7",
    "uuid7_from_parts",
]
