from __future__ import annotations

import io
import plistlib
import sys
import zipfile
from pathlib import Path
from uuid import UUID

import pytest

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.application_spine.object_store import (
    IntakeError,
    WorkspaceObjectStore,
    detect_media_type,
    sanitize_display_name,
    sanitize_relative_path,
)
from asd_kontur.application_spine.runtime import _render_launchd, _show_logs
from asd_kontur.application_spine.worker import verify_bytes_digest
from asd_kontur.web_app.app import _parse_range

ORGANIZATION_ID = UUID("018f5c3e-7b00-7000-8000-000000001801")
WORKSPACE_ID = UUID("018f5c3e-7b00-7000-8000-000000001802")


def settings(root: Path, **overrides: object) -> SpineSettings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://app:synthetic@127.0.0.1/spine",
        "lifecycle_database_url": "postgresql+psycopg://lifecycle:synthetic@127.0.0.1/spine",
        "worker_database_url": "postgresql+psycopg://worker:synthetic@127.0.0.1/spine",
        "destruction_database_url": "postgresql+psycopg://destroy:synthetic@127.0.0.1/spine",
        "object_store_root": root,
        "archive_store_root": root / "archives",
        "session_profile": SessionProfile.DEVELOPMENT_LOOPBACK,
        "audit_pepper": "x" * 32,
        "max_file_bytes": 1024 * 1024,
        "max_batch_bytes": 1024 * 1024,
    }
    values.update(overrides)
    return SpineSettings(**values)  # type: ignore[arg-type]


def test_settings_fail_closed_for_unsafe_network_and_implicit_database(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        settings(tmp_path, database_url="sqlite:///spine.db")
    with pytest.raises(ValueError, match="loopback"):
        settings(tmp_path, bind_host="0.0.0.0")
    with pytest.raises(ValueError, match="protected-network"):
        settings(
            tmp_path,
            session_profile=SessionProfile.PROTECTED_REMOTE,
            bind_host="0.0.0.0",
        )


def test_release_identity_is_explicit_and_version_pinned(tmp_path: Path) -> None:
    configured = settings(
        tmp_path,
        release_commit="0123456789abcdef",
        release_profile="public-development-contour",
        deployed_at="2026-08-27T12:00:00+12:00",
        frontend_build_digest="sha256:frontend",
        openapi_digest="sha256:openapi",
        expected_migration_head="0027_public_deployment",
    )
    assert configured.release_commit == "0123456789abcdef"
    assert configured.release_profile == "public-development-contour"
    assert configured.frontend_build_digest == "sha256:frontend"
    assert configured.openapi_digest == "sha256:openapi"
    assert configured.expected_migration_head == "0027_public_deployment"


@pytest.mark.parametrize(
    "value",
    ("../secret.pdf", "/absolute.pdf", "folder/../../secret.pdf", "\x00bad.pdf"),
)
def test_relative_path_rejects_traversal_and_invalid_names(value: str) -> None:
    with pytest.raises(IntakeError, match="relative_path_rejected"):
        sanitize_relative_path(value)


def test_display_name_strips_client_path_without_trusting_it() -> None:
    assert sanitize_display_name(r"C:\fakepath\proof.pdf") == "proof.pdf"
    assert sanitize_relative_path("site/evidence/proof.pdf") == "site/evidence/proof.pdf"


def test_content_signature_overrides_client_mime_and_unknown_binary_is_rejected() -> None:
    assert detect_media_type(b"%PDF-1.7\n", "text/plain") == "application/pdf"
    assert detect_media_type(b"plain UTF-8 evidence", "application/pdf") == "text/plain"
    with pytest.raises(IntakeError, match="unsupported_or_mismatched_media_type"):
        detect_media_type(b"\x00\x01\x02", "application/pdf")


def test_object_store_streams_commits_and_rejects_cross_root_key(tmp_path: Path) -> None:
    store = WorkspaceObjectStore(tmp_path, chunk_bytes=65536, max_file_bytes=1024 * 1024)
    payload = b"%PDF-1.7\n" + b"x" * 131072
    staged = store.stage(
        stream=io.BytesIO(payload),
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_ID,
        original_name="source.pdf",
        relative_path="package/source.pdf",
        client_media_type="application/pdf",
    )
    assert staged.size_bytes == len(payload)
    committed = store.commit(staged)
    assert committed.created
    with store.open(staged.object_key) as stream:
        assert verify_bytes_digest(stream.read()) == (staged.digest, len(payload))
    with pytest.raises(IntakeError, match="object_path_invalid"):
        store.open("../outside")


def test_archive_expansion_preserves_relative_paths_and_rejects_traversal(tmp_path: Path) -> None:
    store = WorkspaceObjectStore(tmp_path, chunk_bytes=65536, max_file_bytes=1024 * 1024)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("ПД/пояснительная-записка.txt", "Наименование объекта: Учебный корпус")
        archive.writestr("РД/лист.pdf", b"%PDF-1.7\n")
    staged = store.stage(
        stream=io.BytesIO(payload.getvalue()),
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_ID,
        original_name="исходные.zip",
        relative_path="комплект/исходные.zip",
        client_media_type="application/zip",
    )
    assert staged.media_type == "application/zip"
    members = store.expand_archive(
        staged,
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_ID,
        max_members=10,
        max_total_bytes=1024 * 1024,
    )
    assert [item.relative_path for item in members] == [
        "комплект/исходные/ПД/пояснительная-записка.txt",
        "комплект/исходные/РД/лист.pdf",
    ]
    assert [item.media_type for item in members] == ["text/plain", "application/pdf"]
    for member in members:
        store.abort(member)
    store.abort(staged)

    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../outside.txt", "blocked")
    rejected = store.stage(
        stream=io.BytesIO(unsafe.getvalue()),
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_ID,
        original_name="unsafe.zip",
        relative_path="unsafe.zip",
        client_media_type="application/zip",
    )
    with pytest.raises(IntakeError, match="relative_path_rejected"):
        store.expand_archive(
            rejected,
            organization_id=ORGANIZATION_ID,
            workspace_id=WORKSPACE_ID,
            max_members=10,
            max_total_bytes=1024 * 1024,
        )
    store.abort(rejected)


def test_semantic_digest_ignores_mapping_order_but_not_typed_payload() -> None:
    assert semantic_digest({"b": 2, "a": 1}) == semantic_digest({"a": 1, "b": 2})
    assert semantic_digest({"value": "1"}) != semantic_digest({"value": 1})


def test_launchd_and_bounded_log_contracts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_root = tmp_path / "logs"
    log_root.mkdir()
    (log_root / "api.log").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (log_root / "worker.log").write_text("worker\n", encoding="utf-8")
    (log_root / "assistant-worker.log").write_text("assistant\n", encoding="utf-8")
    (log_root / "qwen.log").write_text("qwen\n", encoding="utf-8")
    monkeypatch.setenv("ASD_LOG_ROOT", str(log_root))
    output = tmp_path / "launchd"
    _render_launchd(output, settings(tmp_path))
    api_plist = (output / "ru.asd-kontur.spine.api.plist").read_text(encoding="utf-8")
    assert "StandardOutPath" in api_plist
    assert str(log_root / "api.log") in api_plist
    parsed = plistlib.loads(api_plist.encode())
    assert parsed["Label"] == "ru.asd-kontur.spine.api"
    assert parsed["ProgramArguments"][0] == str(Path(sys.executable).absolute())
    assert parsed["EnvironmentVariables"]["ASD_DATABASE_URL"].startswith("postgresql+psycopg://")
    assert parsed["EnvironmentVariables"]["ASD_EXPECTED_MIGRATION_HEAD"] == (
        "0030_professional_assistant"
    )
    assistant_plist = plistlib.loads(
        (output / "ru.asd-kontur.spine.assistant-worker.plist").read_bytes()
    )
    assert assistant_plist["Label"] == "ru.asd-kontur.spine.assistant-worker"
    assert assistant_plist["ProgramArguments"][-1] == "run-assistant-worker"
    qwen_plist = plistlib.loads((output / "ru.asd-kontur.spine.qwen.plist").read_bytes())
    assert qwen_plist["Label"] == "ru.asd-kontur.spine.qwen"
    assert "asd_kontur.assistant.qwen_server" in qwen_plist["ProgramArguments"]
    assert "10240" in (output / "asd-kontur-spine.newsyslog.conf").read_text(encoding="utf-8")
    assert _show_logs(settings(tmp_path), "all", 2) == 0
    monkeypatch.delenv("ASD_LOG_ROOT")
    with pytest.raises(ValueError, match="ASD_LOG_ROOT"):
        _render_launchd(tmp_path / "unconfigured", settings(tmp_path))


@pytest.mark.parametrize(
    ("header", "size", "expected"),
    (
        (None, 100, None),
        ("bytes=10-19", 100, (10, 19)),
        ("bytes=90-", 100, (90, 99)),
        ("bytes=-10", 100, (90, 99)),
    ),
)
def test_pdf_range_parser(header: str | None, size: int, expected: tuple[int, int] | None) -> None:
    assert _parse_range(header, size) == expected
