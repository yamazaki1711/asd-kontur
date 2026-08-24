"""Provider-neutral object-store port and deterministic test double."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import KnowledgeError, KnowledgeErrorCode


@dataclass(frozen=True, slots=True)
class ObjectWriteReceipt:
    operation_id: str
    object_key: str
    digest: str
    size_bytes: int
    verified: bool
    adapter_key: str = "test-port"


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


class LocalFilesystemObjectStore:
    """Non-networked immutable store rooted in an explicit directory outside Git."""

    adapter_key = "local-platform-object-store-v0.1"

    def __init__(self, root: Path) -> None:
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            raise ValueError("Local object store needs a pre-created absolute non-symlink root")
        self._root = root.resolve(strict=True)
        self._operations: dict[str, ObjectWriteReceipt] = {}

    def _path(self, object_key: str) -> Path:
        if object_key.startswith("/") or ".." in Path(object_key).parts:
            raise KnowledgeError(
                KnowledgeErrorCode.OBJECT_WRITE_FAILED,
                "Object key escaped the configured local store root.",
            )
        candidate = self._root.joinpath(*Path(object_key).parts)
        parent = candidate.parent
        parent.mkdir(parents=True, exist_ok=True)
        if (
            parent.resolve(strict=True) != self._root
            and self._root not in parent.resolve(strict=True).parents
        ):
            raise KnowledgeError(
                KnowledgeErrorCode.OBJECT_WRITE_FAILED,
                "Object key escaped the configured local store root.",
            )
        if any(part.is_symlink() for part in (parent, *parent.parents) if part != self._root):
            raise KnowledgeError(
                KnowledgeErrorCode.OBJECT_WRITE_FAILED,
                "Symlink traversal is forbidden in the local object store.",
            )
        return candidate

    def put_immutable(
        self, *, operation_id: str, object_key: str, content: bytes
    ) -> ObjectWriteReceipt:
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        existing = self._operations.get(operation_id)
        if existing is not None:
            if existing.object_key != object_key or existing.digest != digest:
                raise KnowledgeError(
                    KnowledgeErrorCode.DIGEST_CONFLICT,
                    "Object operation identity was reused for different bytes.",
                )
            return existing
        target = self._path(object_key)
        if target.exists():
            current = target.read_bytes()
            if current != content:
                raise KnowledgeError(
                    KnowledgeErrorCode.DIGEST_CONFLICT,
                    "Immutable object key already contains different bytes.",
                )
        else:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            descriptor = os.open(target, flags, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                target.unlink(missing_ok=True)
                raise
        receipt = ObjectWriteReceipt(
            operation_id,
            object_key,
            digest,
            len(content),
            True,
            self.adapter_key,
        )
        self._operations[operation_id] = receipt
        return receipt

    def head(self, object_key: str) -> ObjectWriteReceipt | None:
        target = self._path(object_key)
        if not target.is_file():
            return None
        content = target.read_bytes()
        return ObjectWriteReceipt(
            "head",
            object_key,
            f"sha256:{hashlib.sha256(content).hexdigest()}",
            len(content),
            True,
            self.adapter_key,
        )

    def delete(self, object_key: str) -> bool:
        target = self._path(object_key)
        if not target.exists():
            return False
        if not target.is_file() or target.is_symlink():
            return False
        target.unlink()
        return True
