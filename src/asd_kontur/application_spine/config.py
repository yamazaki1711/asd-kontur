"""Explicit Product Application Spine runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class SessionProfile(StrEnum):
    DEVELOPMENT_LOOPBACK = "development_loopback"
    PROTECTED_REMOTE = "protected_remote"


@dataclass(frozen=True, slots=True)
class SpineSettings:
    database_url: str
    lifecycle_database_url: str
    worker_database_url: str
    destruction_database_url: str
    object_store_root: Path
    archive_store_root: Path
    session_profile: SessionProfile
    audit_pepper: str
    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    session_cookie_name: str = "asd_session"
    csrf_cookie_name: str = "asd_csrf"
    inactivity_seconds: int = 1800
    absolute_session_seconds: int = 43200
    login_window_seconds: int = 300
    login_max_attempts: int = 5
    upload_chunk_bytes: int = 1024 * 1024
    max_file_bytes: int = 512 * 1024 * 1024
    max_batch_bytes: int = 2 * 1024 * 1024 * 1024
    max_batch_files: int = 1000
    job_lease_seconds: int = 30
    event_retention_seconds: int = 86400
    frontend_dist: Path | None = None

    def __post_init__(self) -> None:
        if not self.database_url.startswith(("postgresql+psycopg://", "postgresql://")):
            raise ValueError("ASD_DATABASE_URL must be an explicit PostgreSQL URL")
        if not self.lifecycle_database_url.startswith(("postgresql+psycopg://", "postgresql://")):
            raise ValueError("ASD_LIFECYCLE_DATABASE_URL must be an explicit PostgreSQL URL")
        if not self.worker_database_url.startswith(("postgresql+psycopg://", "postgresql://")):
            raise ValueError("ASD_WORKER_DATABASE_URL must be an explicit PostgreSQL URL")
        if not self.destruction_database_url.startswith(("postgresql+psycopg://", "postgresql://")):
            raise ValueError("ASD_DESTRUCTION_DATABASE_URL must be an explicit PostgreSQL URL")
        if not self.object_store_root.is_absolute():
            raise ValueError("ASD_OBJECT_STORE_ROOT must be absolute")
        if not self.archive_store_root.is_absolute():
            raise ValueError("ASD_ARCHIVE_STORE_ROOT must be absolute")
        if self.object_store_root.resolve() == self.archive_store_root.resolve():
            raise ValueError("workspace object and archive roots must be distinct")
        if len(self.audit_pepper) < 32:
            raise ValueError("ASD_AUTH_AUDIT_PEPPER must contain at least 32 characters")
        if self.session_profile is SessionProfile.DEVELOPMENT_LOOPBACK and self.bind_host not in {
            "127.0.0.1",
            "::1",
            "localhost",
        }:
            raise ValueError("development_loopback may bind only to loopback")
        if self.session_profile is SessionProfile.PROTECTED_REMOTE and self.bind_host in {
            "0.0.0.0",
            "::",
        }:
            raise ValueError("protected_remote requires an explicit protected-network address")
        if self.upload_chunk_bytes < 65536 or self.max_file_bytes < self.upload_chunk_bytes:
            raise ValueError("invalid upload chunk/file limit")
        if self.max_batch_files < 1 or self.max_batch_bytes < self.max_file_bytes:
            raise ValueError("invalid batch limits")

    @property
    def secure_cookie(self) -> bool:
        return self.session_profile is SessionProfile.PROTECTED_REMOTE

    @classmethod
    def from_env(cls) -> SpineSettings:
        frontend = os.environ.get("ASD_FRONTEND_DIST")
        return cls(
            database_url=_required("ASD_DATABASE_URL"),
            lifecycle_database_url=_required("ASD_LIFECYCLE_DATABASE_URL"),
            worker_database_url=_required("ASD_WORKER_DATABASE_URL"),
            destruction_database_url=_required("ASD_DESTRUCTION_DATABASE_URL"),
            object_store_root=Path(_required("ASD_OBJECT_STORE_ROOT")),
            archive_store_root=Path(_required("ASD_ARCHIVE_STORE_ROOT")),
            session_profile=SessionProfile(
                os.environ.get("ASD_SESSION_PROFILE", SessionProfile.DEVELOPMENT_LOOPBACK.value)
            ),
            audit_pepper=_required("ASD_AUTH_AUDIT_PEPPER"),
            bind_host=os.environ.get("ASD_BIND_HOST", "127.0.0.1"),
            bind_port=int(os.environ.get("ASD_BIND_PORT", "8765")),
            max_file_bytes=int(os.environ.get("ASD_MAX_FILE_BYTES", str(512 * 1024 * 1024))),
            max_batch_bytes=int(os.environ.get("ASD_MAX_BATCH_BYTES", str(2 * 1024 * 1024 * 1024))),
            max_batch_files=int(os.environ.get("ASD_MAX_BATCH_FILES", "1000")),
            frontend_dist=Path(frontend) if frontend else None,
        )


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} is required")
    return value
