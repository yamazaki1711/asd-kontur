"""Provider-neutral object-store port and deterministic test double."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from .errors import KnowledgeError, KnowledgeErrorCode


@dataclass(frozen=True, slots=True)
class ObjectWriteReceipt:
    operation_id: str
    object_key: str
    digest: str
    size_bytes: int
    verified: bool


class ObjectStorePort(Protocol):
    def put_immutable(
        self, *, operation_id: str, object_key: str, content: bytes
    ) -> ObjectWriteReceipt: ...

    def head(self, object_key: str) -> ObjectWriteReceipt | None: ...

    def delete(self, object_key: str) -> bool: ...


class InMemoryObjectStore:
    """A non-networked adapter used only to prove admission and residue semantics."""

    def __init__(self) -> None:
        self.available = True
        self.fail_writes = False
        self.fail_deletes = False
        self._objects: dict[str, bytes] = {}
        self._operations: dict[str, ObjectWriteReceipt] = {}

    def put_immutable(
        self, *, operation_id: str, object_key: str, content: bytes
    ) -> ObjectWriteReceipt:
        if not self.available:
            raise KnowledgeError(
                KnowledgeErrorCode.OBJECT_STORE_UNAVAILABLE,
                "Object adapter is unavailable; source admission was not performed.",
            )
        if self.fail_writes:
            raise KnowledgeError(
                KnowledgeErrorCode.OBJECT_WRITE_FAILED,
                "Object write failed; source admission was not performed.",
            )
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        existing_operation = self._operations.get(operation_id)
        if existing_operation is not None:
            if existing_operation.digest != digest or existing_operation.object_key != object_key:
                raise KnowledgeError(
                    KnowledgeErrorCode.DIGEST_CONFLICT,
                    "An idempotency operation was reused with different bytes or object identity.",
                )
            return existing_operation
        existing_bytes = self._objects.get(object_key)
        if existing_bytes is not None and existing_bytes != content:
            raise KnowledgeError(
                KnowledgeErrorCode.DIGEST_CONFLICT,
                "Immutable object identity already refers to different bytes.",
            )
        self._objects[object_key] = bytes(content)
        receipt = ObjectWriteReceipt(operation_id, object_key, digest, len(content), True)
        self._operations[operation_id] = receipt
        return receipt

    def head(self, object_key: str) -> ObjectWriteReceipt | None:
        content = self._objects.get(object_key)
        if content is None:
            return None
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        return ObjectWriteReceipt("head", object_key, digest, len(content), True)

    def delete(self, object_key: str) -> bool:
        if self.fail_deletes:
            return False
        return self._objects.pop(object_key, None) is not None
