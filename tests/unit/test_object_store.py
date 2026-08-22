from __future__ import annotations

import pytest

from asd_kontur.knowledge import InMemoryObjectStore, KnowledgeError, KnowledgeErrorCode


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
