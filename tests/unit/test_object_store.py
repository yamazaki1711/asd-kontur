from __future__ import annotations

from pathlib import Path

import pytest

from asd_kontur.knowledge import (
    InMemoryObjectStore,
    KnowledgeError,
    KnowledgeErrorCode,
    LocalFilesystemObjectStore,
)


def test_object_write_is_idempotent_but_digest_is_not_access() -> None:
    store = InMemoryObjectStore()
    first = store.put_immutable(operation_id="op-1", object_key="scoped/key", content=b"one")
    second = store.put_immutable(operation_id="op-1", object_key="scoped/key", content=b"one")
    assert first == second
    assert first.object_key != first.digest


def test_operation_reuse_with_other_bytes_is_conflict() -> None:
    store = InMemoryObjectStore()
    store.put_immutable(operation_id="op-1", object_key="scoped/key", content=b"one")
    with pytest.raises(KnowledgeError) as caught:
        store.put_immutable(operation_id="op-1", object_key="scoped/key", content=b"two")
    assert caught.value.code is KnowledgeErrorCode.DIGEST_CONFLICT


def test_unavailable_adapter_fails_closed() -> None:
    store = InMemoryObjectStore()
    store.available = False
    with pytest.raises(KnowledgeError) as caught:
        store.put_immutable(operation_id="op-1", object_key="scoped/key", content=b"one")
    assert caught.value.code is KnowledgeErrorCode.OBJECT_STORE_UNAVAILABLE


def test_local_platform_object_store_is_exact_immutable_and_contained(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    store = LocalFilesystemObjectStore(root)
    receipt = store.put_immutable(
        operation_id="guide-admission-1",
        object_key="platform/source/synthetic-guide",
        content=b"synthetic guide bytes",
    )
    assert receipt.adapter_key == "local-platform-object-store-v0.1"
    assert store.head("platform/source/synthetic-guide") == receipt.__class__(
        "head",
        receipt.object_key,
        receipt.digest,
        receipt.size_bytes,
        True,
        receipt.adapter_key,
    )
    assert (
        store.put_immutable(
            operation_id="guide-admission-1",
            object_key="platform/source/synthetic-guide",
            content=b"synthetic guide bytes",
        )
        == receipt
    )
    with pytest.raises(KnowledgeError):
        store.put_immutable(
            operation_id="guide-admission-1",
            object_key="platform/source/other",
            content=b"different",
        )
    with pytest.raises(KnowledgeError):
        store.put_immutable(
            operation_id="escape",
            object_key="../outside",
            content=b"forbidden",
        )


def test_local_platform_object_store_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    store = LocalFilesystemObjectStore(root)
    with pytest.raises(KnowledgeError):
        store.put_immutable(
            operation_id="escape",
            object_key="escape/object",
            content=b"forbidden",
        )
