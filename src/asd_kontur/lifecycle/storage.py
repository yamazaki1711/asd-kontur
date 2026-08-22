"""Exact-item storage adapters and deterministic portable archive support."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from uuid import UUID

import rfc8785

from asd_kontur.domain import uuid7

from .errors import LifecycleError, LifecycleErrorCode
from .models import (
    AdapterOutcome,
    AdapterReceipt,
    InventoryItem,
    StorageAdapterDefinition,
)


class StorageAdapter(Protocol):
    definition: StorageAdapterDefinition

    def inventory(self, workspace_id: UUID) -> tuple[InventoryItem, ...]: ...

    def purge_item(
        self, *, workspace_id: UUID, item_id: str, operation_id: UUID
    ) -> AdapterReceipt: ...

    def find_residue(
        self,
        *,
        workspace_id: UUID,
        known_ids: frozenset[str],
        known_digests: frozenset[str],
        known_fragments: frozenset[str],
    ) -> tuple[InventoryItem, ...]: ...


class InMemoryStorageAdapter:
    """Fault-injectable adapter for disposable acceptance evidence only."""

    def __init__(self, definition: StorageAdapterDefinition) -> None:
        self.definition = definition
        self._items: dict[tuple[UUID, str], tuple[bytes, str]] = {}
        self._receipts: dict[tuple[UUID, str], AdapterReceipt] = {}
        self.fail_items: set[str] = set()

    def put(self, workspace_id: UUID, item_id: str, payload: bytes, media_type: str) -> None:
        self._items[(workspace_id, item_id)] = (bytes(payload), media_type)

    def read(self, workspace_id: UUID, item_id: str) -> bytes:
        return self._items[(workspace_id, item_id)][0]

    def inventory(self, workspace_id: UUID) -> tuple[InventoryItem, ...]:
        self._require_available()
        return tuple(
            InventoryItem(
                item_id,
                owner,
                media_type,
                len(payload),
                "sha256:" + hashlib.sha256(payload).hexdigest(),
            )
            for (owner, item_id), (payload, media_type) in sorted(
                self._items.items(), key=lambda item: (str(item[0][0]), item[0][1])
            )
            if owner == workspace_id
        )

    def purge_item(self, *, workspace_id: UUID, item_id: str, operation_id: UUID) -> AdapterReceipt:
        self._require_available()
        key = (operation_id, item_id)
        previous = self._receipts.get(key)
        if previous is not None:
            return previous
        before = int((workspace_id, item_id) in self._items)
        if item_id in self.fail_items:
            outcome = AdapterOutcome.FAILED
            after = before
        elif self._items.pop((workspace_id, item_id), None) is None:
            outcome = AdapterOutcome.ALREADY_ABSENT
            after = 0
        else:
            outcome = AdapterOutcome.DELETED
            after = 0
        receipt = AdapterReceipt(
            uuid7(),
            self.definition.adapter_key,
            item_id,
            outcome,
            before,
            after,
            operation_id,
            datetime.now(UTC),
        )
        self._receipts[key] = receipt
        return receipt

    def find_residue(
        self,
        *,
        workspace_id: UUID,
        known_ids: frozenset[str],
        known_digests: frozenset[str],
        known_fragments: frozenset[str],
    ) -> tuple[InventoryItem, ...]:
        self._require_available()
        findings: list[InventoryItem] = []
        for item in self.inventory(workspace_id):
            payload = self._items[(workspace_id, item.item_id)][0]
            text = payload.decode("utf-8", errors="ignore")
            if (
                item.item_id in known_ids
                or item.digest in known_digests
                or any(fragment in text for fragment in known_fragments)
            ):
                findings.append(item)
        return tuple(findings)

    def _require_available(self) -> None:
        if self.definition.health != "available":
            raise LifecycleError(
                LifecycleErrorCode.ADAPTER_UNAVAILABLE,
                f"Adapter {self.definition.adapter_key} is unavailable.",
            )


class ContainedFilesystemAdapter:
    """Exact-path adapter confined to an explicit disposable test root."""

    def __init__(self, root: Path, definition: StorageAdapterDefinition) -> None:
        resolved = root.resolve(strict=True)
        forbidden = {Path("/").resolve(), Path.home().resolve()}
        if resolved in forbidden or len(resolved.parts) < 3:
            raise ValueError("filesystem adapter root is too broad")
        self.root = resolved
        self.definition = definition
        self._receipts: dict[tuple[UUID, str], AdapterReceipt] = {}

    def put(self, workspace_id: UUID, item_id: str, payload: bytes) -> Path:
        path = self._resolve_item(workspace_id, item_id, require_exists=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def inventory(self, workspace_id: UUID) -> tuple[InventoryItem, ...]:
        workspace_root = self._workspace_root(workspace_id)
        if not workspace_root.exists():
            return ()
        result: list[InventoryItem] = []
        for path in sorted(workspace_root.rglob("*")):
            if path.is_symlink():
                raise LifecycleError(
                    LifecycleErrorCode.INTEGRITY_MISMATCH,
                    "Symlinks are forbidden inside lifecycle-managed storage.",
                )
            if path.is_file():
                payload = path.read_bytes()
                result.append(
                    InventoryItem(
                        path.relative_to(workspace_root).as_posix(),
                        workspace_id,
                        "application/octet-stream",
                        len(payload),
                        "sha256:" + hashlib.sha256(payload).hexdigest(),
                    )
                )
        return tuple(result)

    def purge_item(self, *, workspace_id: UUID, item_id: str, operation_id: UUID) -> AdapterReceipt:
        key = (operation_id, item_id)
        if key in self._receipts:
            return self._receipts[key]
        path = self._resolve_item(workspace_id, item_id, require_exists=False)
        before = int(path.exists())
        if path.exists():
            if not path.is_file() or path.is_symlink():
                raise LifecycleError(
                    LifecycleErrorCode.INTEGRITY_MISMATCH,
                    "Only exact regular manifest files may be removed.",
                )
            path.unlink()
            outcome = AdapterOutcome.DELETED
        else:
            outcome = AdapterOutcome.ALREADY_ABSENT
        receipt = AdapterReceipt(
            uuid7(),
            self.definition.adapter_key,
            item_id,
            outcome,
            before,
            0,
            operation_id,
            datetime.now(UTC),
        )
        self._receipts[key] = receipt
        return receipt

    def find_residue(
        self,
        *,
        workspace_id: UUID,
        known_ids: frozenset[str],
        known_digests: frozenset[str],
        known_fragments: frozenset[str],
    ) -> tuple[InventoryItem, ...]:
        findings: list[InventoryItem] = []
        for item in self.inventory(workspace_id):
            path = self._resolve_item(workspace_id, item.item_id, require_exists=True)
            text = path.read_text(encoding="utf-8", errors="ignore")
            if (
                item.item_id in known_ids
                or item.digest in known_digests
                or any(fragment in text for fragment in known_fragments)
            ):
                findings.append(item)
        return tuple(findings)

    def _workspace_root(self, workspace_id: UUID) -> Path:
        candidate = (self.root / str(workspace_id)).resolve()
        if not candidate.is_relative_to(self.root):
            raise LifecycleError(
                LifecycleErrorCode.INTEGRITY_MISMATCH,
                "Workspace storage escaped its configured root.",
            )
        return candidate

    def _resolve_item(self, workspace_id: UUID, item_id: str, *, require_exists: bool) -> Path:
        logical = PurePosixPath(item_id)
        if logical.is_absolute() or ".." in logical.parts or not logical.parts:
            raise LifecycleError(
                LifecycleErrorCode.INTEGRITY_MISMATCH,
                "The manifest item path is unsafe.",
            )
        candidate = self._workspace_root(workspace_id).joinpath(*logical.parts)
        parent = candidate.parent.resolve(strict=parent_exists(candidate.parent))
        if not parent.is_relative_to(self.root):
            raise LifecycleError(
                LifecycleErrorCode.INTEGRITY_MISMATCH,
                "The manifest item path escaped its configured root.",
            )
        if require_exists and not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate


def parent_exists(path: Path) -> bool:
    return path.exists()


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    logical_path: str
    source_version_ref: str
    payload: bytes
    media_type: str


@dataclass(frozen=True, slots=True)
class ArchiveReceipt:
    package_id: UUID
    package_path: Path
    package_digest: str
    manifest_digest: str
    item_count: int
    verified_at: datetime


class PortableArchiveService:
    """Create and verify a sealed logical ZIP; it is never a recovery backup."""

    MANIFEST_NAME = "manifest.json"

    def create(
        self,
        *,
        package_id: UUID,
        organization_id: UUID,
        construction_object_id: UUID,
        workspace_id: UUID,
        workspace_revision: int,
        contract_versions: Mapping[str, str],
        policy_versions: Mapping[str, str],
        rule_set_version: str,
        entries: Iterable[ArchiveEntry],
        destination: Path,
    ) -> ArchiveReceipt:
        normalized = sorted(tuple(entries), key=lambda item: item.logical_path)
        paths = [item.logical_path for item in normalized]
        if len(paths) != len(set(paths)) or any(not self._safe_path(path) for path in paths):
            raise LifecycleError(
                LifecycleErrorCode.ARCHIVE_INVALID,
                "Archive paths must be unique, relative, and traversal-free.",
            )
        manifest_entries = [
            {
                "logical_path": item.logical_path,
                "source_version_ref": item.source_version_ref,
                "media_type": item.media_type,
                "size_bytes": len(item.payload),
                "digest": "sha256:" + hashlib.sha256(item.payload).hexdigest(),
            }
            for item in normalized
        ]
        manifest: dict[str, Any] = {
            "package_id": str(package_id),
            "package_version": "1.0.0",
            "package_type": "portable_logical_archive",
            "organization_id": str(organization_id),
            "construction_object_id": str(construction_object_id),
            "workspace_id": str(workspace_id),
            "workspace_revision": workspace_revision,
            "contract_versions": dict(sorted(contract_versions.items())),
            "policy_versions": dict(sorted(policy_versions.items())),
            "rule_set_version": rule_set_version,
            "entries": manifest_entries,
            "import_semantics": "new_workspace_only",
        }
        manifest_bytes = rfc8785.dumps(manifest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as package:
            package.writestr(self._zip_info(self.MANIFEST_NAME), manifest_bytes)
            for item in normalized:
                package.writestr(self._zip_info(f"objects/{item.logical_path}"), item.payload)
        receipt = self.verify(destination)
        if receipt.package_id != package_id:
            raise LifecycleError(
                LifecycleErrorCode.ARCHIVE_INVALID,
                "Archive package identity changed during creation.",
            )
        os.chmod(destination, 0o444)
        return receipt

    def verify(self, package_path: Path) -> ArchiveReceipt:
        try:
            with zipfile.ZipFile(package_path, "r") as package:
                names = package.namelist()
                if len(names) != len(set(names)) or self.MANIFEST_NAME not in names:
                    raise LifecycleError(
                        LifecycleErrorCode.ARCHIVE_INVALID,
                        "Archive manifest is missing or package contains duplicate items.",
                    )
                manifest_bytes = package.read(self.MANIFEST_NAME)
                manifest = json.loads(manifest_bytes)
                expected_names = {self.MANIFEST_NAME}
                for entry in manifest["entries"]:
                    logical_path = str(entry["logical_path"])
                    if not self._safe_path(logical_path):
                        raise LifecycleError(
                            LifecycleErrorCode.ARCHIVE_INVALID,
                            "Archive contains an unsafe logical path.",
                        )
                    name = f"objects/{logical_path}"
                    expected_names.add(name)
                    payload = package.read(name)
                    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
                    if len(payload) != entry["size_bytes"] or digest != entry["digest"]:
                        raise LifecycleError(
                            LifecycleErrorCode.INTEGRITY_MISMATCH,
                            "Archive item integrity verification failed.",
                        )
                if set(names) != expected_names:
                    raise LifecycleError(
                        LifecycleErrorCode.ARCHIVE_INVALID,
                        "Archive contains missing or extra objects.",
                    )
        except (KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
            raise LifecycleError(
                LifecycleErrorCode.ARCHIVE_INVALID,
                "Archive cannot be parsed or verified.",
            ) from exc
        raw = package_path.read_bytes()
        return ArchiveReceipt(
            UUID(str(manifest["package_id"])),
            package_path,
            "sha256:" + hashlib.sha256(raw).hexdigest(),
            "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
            len(manifest["entries"]),
            datetime.now(UTC),
        )

    @staticmethod
    def _safe_path(value: str) -> bool:
        path = PurePosixPath(value)
        return bool(value) and not path.is_absolute() and ".." not in path.parts

    @staticmethod
    def _zip_info(name: str) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = 0o100444 << 16
        return info


def inventory_digest(inventories: Mapping[str, tuple[InventoryItem, ...]]) -> str:
    payload = {
        key: [asdict(item) for item in value]
        for key, value in sorted(inventories.items(), key=lambda item: item[0])
    }
    canonical = rfc8785.dumps(json.loads(json.dumps(payload, default=str)))
    return "sha256:" + hashlib.sha256(canonical).hexdigest()
