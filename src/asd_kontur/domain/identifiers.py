"""Identifiers accepted by LDM-10.

UUIDv7 follows RFC 9562 section 5.7: 48-bit Unix epoch milliseconds, version
bits, 12 random bits, RFC variant bits and 62 random bits. UUIDv5 is available
only through the registered namespace and canonicalization contract below.
"""

from __future__ import annotations

import secrets
import time
import unicodedata
import uuid

SEMANTIC_NAMESPACE_V1 = uuid.UUID("d782a58e-6316-5b9e-bf7a-ee5ae9d9597e")
SEMANTIC_CANONICALIZATION_V1 = "utf8-nfc-trim-v1"


def uuid7_from_parts(timestamp_ms: int, random_a: int, random_b: int) -> uuid.UUID:
    """Build an RFC 9562 UUIDv7 from validated bit fields."""

    if not 0 <= timestamp_ms < 1 << 48:
        raise ValueError("timestamp_ms must fit 48 bits")
    if not 0 <= random_a < 1 << 12:
        raise ValueError("random_a must fit 12 bits")
    if not 0 <= random_b < 1 << 62:
        raise ValueError("random_b must fit 62 bits")
    value = (timestamp_ms << 80) | (0b0111 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    return uuid.UUID(int=value)


def uuid7() -> uuid.UUID:
    """Create a new RFC 9562 UUIDv7 instance identity."""

    timestamp_ms = time.time_ns() // 1_000_000
    return uuid7_from_parts(timestamp_ms, secrets.randbits(12), secrets.randbits(62))


def canonical_semantic_key(value: str) -> str:
    """Apply registered v1 semantic-key canonicalization without case folding."""

    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValueError("semantic key cannot be empty")
    if "\x1f" in normalized:
        raise ValueError("semantic key contains the reserved separator")
    return normalized


def deterministic_uuid(value: str) -> uuid.UUID:
    """Create a UUIDv5 under the registered semantic namespace."""

    canonical = canonical_semantic_key(value)
    name = f"{SEMANTIC_CANONICALIZATION_V1}\x1f{canonical}"
    return uuid.uuid5(SEMANTIC_NAMESPACE_V1, name)
