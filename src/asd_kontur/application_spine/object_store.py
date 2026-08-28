"""Streaming workspace object plane outside Git and PostgreSQL."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, cast
from uuid import UUID


class IntakeError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class StagedObject:
    staging_path: Path
    object_key: str
    digest: str
    size_bytes: int
    media_type: str
    safe_display_name: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class CommittedObject:
    path: Path
    created: bool


@dataclass(frozen=True, slots=True)
class StoredObjectEntry:
    object_key: str
    path: Path
    digest: str
    size_bytes: int


class WorkspaceObjectStore:
    """Content-addressed local adapter; file bytes are never buffered as one value."""

    adapter_key = "local-workspace-object-store-v0.1"

    def __init__(self, root: Path, *, chunk_bytes: int, max_file_bytes: int) -> None:
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            raise ValueError("workspace object root must be a pre-created absolute directory")
        self._root = root.resolve(strict=True)
        self._chunk_bytes = chunk_bytes
        self._max_file_bytes = max_file_bytes
        self._staging = self._root / ".staging"
        self._staging.mkdir(mode=0o700, exist_ok=True)

    def stage(
        self,
        *,
        stream: BinaryIO,
        organization_id: UUID,
        workspace_id: UUID,
        original_name: str,
        relative_path: str | None,
        client_media_type: str | None,
    ) -> StagedObject:
        safe_path = sanitize_relative_path(relative_path or original_name)
        safe_name = sanitize_display_name(original_name)
        staging_path = self._staging / f"{secrets.token_hex(24)}.part"
        descriptor = os.open(staging_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        digest = hashlib.sha256()
        size = 0
        header = b""
        try:
            with os.fdopen(descriptor, "wb") as output:
                while True:
                    chunk = stream.read(self._chunk_bytes)
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise IntakeError("upload_stream_invalid")
                    size += len(chunk)
                    if size > self._max_file_bytes:
                        raise IntakeError("file_size_limit_exceeded")
                    if len(header) < 4096:
                        header += chunk[: 4096 - len(header)]
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if size == 0:
                raise IntakeError("empty_file")
            media_type = detect_staged_media_type(staging_path, header, client_media_type)
            hexdigest = digest.hexdigest()
            object_key = (
                f"workspaces/{organization_id}/{workspace_id}/sha256/{hexdigest[:2]}/{hexdigest}"
            )
            return StagedObject(
                staging_path,
                object_key,
                f"sha256:{hexdigest}",
                size,
                media_type,
                safe_name,
                safe_path,
            )
        except BaseException:
            staging_path.unlink(missing_ok=True)
            raise

    def commit(self, staged: StagedObject) -> CommittedObject:
        target = self._safe_path(staged.object_key)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise IntakeError("object_path_invalid")
            if _file_digest(target) != staged.digest:
                raise IntakeError("object_digest_conflict")
            staged.staging_path.unlink(missing_ok=True)
            return CommittedObject(target, False)
        os.replace(staged.staging_path, target)
        os.chmod(target, 0o600)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return CommittedObject(target, True)

    def expand_archive(
        self,
        staged: StagedObject,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        max_members: int,
        max_total_bytes: int,
    ) -> tuple[StagedObject, ...]:
        """Safely stage regular ZIP members while retaining the original container."""

        if staged.media_type != "application/zip":
            return ()
        expanded: list[StagedObject] = []
        observed_paths: set[str] = set()
        observed_bytes = 0
        try:
            with zipfile.ZipFile(staged.staging_path) as archive:
                members = [member for member in archive.infolist() if not member.is_dir()]
                if not members or len(members) > max_members:
                    raise IntakeError("archive_member_count_invalid")
                for member in members:
                    mode = (member.external_attr >> 16) & 0o170000
                    if member.flag_bits & 0x1:
                        raise IntakeError("archive_encrypted_member_rejected")
                    if mode == 0o120000:
                        raise IntakeError("archive_symlink_rejected")
                    member_path = sanitize_relative_path(member.filename)
                    folded = member_path.casefold()
                    if folded in observed_paths:
                        raise IntakeError("archive_duplicate_path_rejected")
                    observed_paths.add(folded)
                    if member.file_size < 1 or member.file_size > self._max_file_bytes:
                        raise IntakeError("archive_member_size_invalid")
                    if member.compress_size and member.file_size / member.compress_size > 200:
                        raise IntakeError("archive_compression_ratio_rejected")
                    observed_bytes += member.file_size
                    if observed_bytes > max_total_bytes:
                        raise IntakeError("archive_expanded_size_limit_exceeded")
                    parent = PurePosixPath(staged.relative_path).with_suffix("")
                    relative_path = (parent / member_path).as_posix()
                    with archive.open(member, "r") as source:
                        expanded.append(
                            self.stage(
                                stream=cast(BinaryIO, source),
                                organization_id=organization_id,
                                workspace_id=workspace_id,
                                original_name=PurePosixPath(member_path).name,
                                relative_path=relative_path,
                                client_media_type=None,
                            )
                        )
        except zipfile.BadZipFile as exc:
            raise IntakeError("archive_structure_invalid") from exc
        except BaseException:
            for expanded_item in expanded:
                self.abort(expanded_item)
            raise
        return tuple(expanded)

    def abort(self, staged: StagedObject) -> None:
        staged.staging_path.unlink(missing_ok=True)

    def open(self, object_key: str) -> BinaryIO:
        path = self._safe_path(object_key)
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(object_key)
        return path.open("rb")

    def put_derived(self, *, object_key: str, content: bytes) -> tuple[str, int]:
        target = self._safe_path(object_key)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if target.exists():
            if _file_digest(target) != digest:
                raise IntakeError("derived_object_digest_conflict")
            return digest, len(content)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        return digest, len(content)

    def delete(self, object_key: str) -> bool:
        target = self._safe_path(object_key)
        if not target.exists():
            return False
        if not target.is_file() or target.is_symlink():
            raise IntakeError("object_path_invalid")
        target.unlink()
        return True

    def workspace_entries(
        self, *, organization_id: UUID, workspace_id: UUID
    ) -> tuple[StoredObjectEntry, ...]:
        roots = (
            self._root / "workspaces" / str(organization_id) / str(workspace_id),
            self._root / "derived" / str(organization_id) / str(workspace_id),
        )
        entries: list[StoredObjectEntry] = []
        for workspace_root in roots:
            resolved = workspace_root.resolve(strict=False)
            if self._root not in resolved.parents:
                raise IntakeError("object_path_invalid")
            if not resolved.exists():
                continue
            for path in sorted(resolved.rglob("*")):
                if path.is_symlink() or (
                    path.exists() and not path.is_file() and not path.is_dir()
                ):
                    raise IntakeError("object_path_invalid")
                if path.is_file():
                    entries.append(
                        StoredObjectEntry(
                            path.relative_to(self._root).as_posix(),
                            path,
                            _file_digest(path),
                            path.stat().st_size,
                        )
                    )
        return tuple(entries)

    def purge_workspace(self, *, organization_id: UUID, workspace_id: UUID) -> int:
        entries = self.workspace_entries(
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        for entry in entries:
            entry.path.unlink()
        for prefix in ("workspaces", "derived"):
            workspace_root = self._root / prefix / str(organization_id) / str(workspace_id)
            if workspace_root.exists():
                for directory in sorted(
                    (path for path in workspace_root.rglob("*") if path.is_dir()),
                    key=lambda item: len(item.parts),
                    reverse=True,
                ):
                    directory.rmdir()
                workspace_root.rmdir()
        return len(entries)

    def _safe_path(self, object_key: str) -> Path:
        pure = PurePosixPath(object_key)
        if pure.is_absolute() or not pure.parts or ".." in pure.parts:
            raise IntakeError("object_path_invalid")
        target = self._root.joinpath(*pure.parts)
        parent = target.parent
        resolved_parent = parent.resolve(strict=False)
        if resolved_parent != self._root and self._root not in resolved_parent.parents:
            raise IntakeError("object_path_invalid")
        return target


def sanitize_relative_path(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value.replace("\\", "/")).strip()
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or ".." in pure.parts
        or any(not part or part in {".", ".."} for part in pure.parts)
        or "\x00" in normalized
    ):
        raise IntakeError("relative_path_rejected")
    parts = tuple(_sanitize_component(part) for part in pure.parts)
    return "/".join(parts)


def sanitize_display_name(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).replace("\\", "/").split("/")[-1]
    result = _sanitize_component(normalized)
    if result in {"", ".", ".."}:
        raise IntakeError("filename_rejected")
    return result


def _sanitize_component(value: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
    if not cleaned or len(cleaned.encode("utf-8")) > 240:
        raise IntakeError("filename_rejected")
    return cleaned


def detect_media_type(header: bytes, client_media_type: str | None) -> str:
    del client_media_type
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if b"\x00" not in header:
        try:
            header.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            return "text/plain"
    raise IntakeError("unsupported_or_mismatched_media_type")


def detect_staged_media_type(path: Path, header: bytes, client_media_type: str | None) -> str:
    """Inspect container structure; client filename and MIME are never authoritative."""

    if header.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as archive:
                names = frozenset(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise IntakeError("office_container_invalid") from exc
        if "[Content_Types].xml" in names and "word/document.xml" in names:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if "[Content_Types].xml" in names and "xl/workbook.xml" in names:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return "application/zip"
    detected = detect_media_type(header, client_media_type)
    if detected == "text/plain" and _looks_like_csv(path):
        return "text/csv"
    return detected


def _looks_like_csv(path: Path) -> bool:
    with path.open("rb") as stream:
        sample = stream.read(8192)
    try:
        text = sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    lines = [line for line in text.splitlines() if line.strip()][:8]
    if len(lines) < 2:
        return False
    for delimiter in (";", ",", "\t"):
        widths = [len(line.split(delimiter)) for line in lines]
        if min(widths) >= 2 and len(set(widths)) <= 2:
            return True
    return False


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()
