from __future__ import annotations

import io
import plistlib
import sys
import zipfile
from pathlib import Path
from threading import Event
from uuid import UUID

import pytest

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.models import ClaimedJob, JobKind, JobState, semantic_digest
from asd_kontur.application_spine.object_store import (
    IntakeError,
    WorkspaceObjectStore,
    detect_media_type,
    sanitize_display_name,
    sanitize_relative_path,
)
from asd_kontur.application_spine.postgres import (
    SpinePostgresRepository,
    _semantic_extraction_priority,
)
from asd_kontur.application_spine.runtime import _migrate, _render_launchd, _show_logs
from asd_kontur.application_spine.worker import DocumentWorker, _LeaseKeepalive, verify_bytes_digest
from asd_kontur.document_understanding.postgres import _identity_observation_group_key
from asd_kontur.web_app.app import _parse_range

ORGANIZATION_ID = UUID("018f5c3e-7b00-7000-8000-000000001801")
WORKSPACE_ID = UUID("018f5c3e-7b00-7000-8000-000000001802")


def test_unexpected_handler_error_terminalizes_job_without_crashing_worker() -> None:
    claimed = ClaimedJob(
        ORGANIZATION_ID,
        WORKSPACE_ID,
        UUID("018f5c3e-7b00-7000-8000-000000001803"),
        JobKind.PROJECT_UNDERSTANDING_RECONCILIATION,
        {},
        "sha256:" + "1" * 64,
        1,
        1,
        "none",
    )

    class Repository:
        def __init__(self) -> None:
            self.claimed = False
            self.finished: dict[str, object] | None = None

        def claim_next_job(self, **_kwargs: object) -> ClaimedJob | None:
            if self.claimed:
                return None
            self.claimed = True
            return claimed

        def reconcile_expired_exhausted_jobs(self, **_kwargs: object) -> int:
            return 0

        def mark_job_running(self, *_args: object, **_kwargs: object) -> None:
            return None

        def cancellation_requested(self, *_args: object, **_kwargs: object) -> bool:
            return False

        def heartbeat_job(self, *_args: object, **_kwargs: object) -> None:
            return None

        def finish_job(self, *_args: object, **kwargs: object) -> None:
            self.finished = kwargs

    repository = Repository()
    worker = object.__new__(DocumentWorker)
    worker._repository = repository  # type: ignore[assignment]
    worker._worker_identity = "synthetic-worker"
    worker._lease_seconds = 30
    worker._organization_id = ORGANIZATION_ID
    worker._workspace_id = WORKSPACE_ID
    worker._stopping = False

    def fail(_claimed: ClaimedJob) -> dict[str, object]:
        raise TypeError("synthetic programming defect")

    worker._execute = fail  # type: ignore[method-assign]

    outcome = worker.run_once()

    assert outcome is not None
    assert outcome.state is JobState.RECONCILIATION_REQUIRED
    assert outcome.outcome_code == "worker_unexpected_handler_error"
    assert repository.finished is not None
    assert repository.finished["terminal_state"] is JobState.RECONCILIATION_REQUIRED
    assert repository.finished["result_manifest"] == {"exception_type": "TypeError"}


def test_semantic_extraction_priority_prefers_persisted_structural_roles() -> None:
    """A one-slot worker reaches source-backed structural evidence before estimates."""

    assert _semantic_extraction_priority(("local_estimate",)) == 150
    assert _semantic_extraction_priority(("project_documentation",)) == 170
    assert _semantic_extraction_priority(("local_estimate", "drawing_or_scheme")) == 170
    assert _semantic_extraction_priority(()) == 130


def test_semantic_coverage_state_distinguishes_unresolved_and_recovered_failures() -> None:
    state = SpinePostgresRepository._semantic_coverage_state

    assert (
        state(
            accepted_fragment_count=0,
            expected_fragment_count=8,
            unresolved_failed_fragment_count=2,
        )
        == "failed"
    )
    assert (
        state(
            accepted_fragment_count=0,
            expected_fragment_count=8,
            unresolved_failed_fragment_count=0,
        )
        == "not_started"
    )
    assert (
        state(
            accepted_fragment_count=7,
            expected_fragment_count=8,
            unresolved_failed_fragment_count=1,
        )
        == "partial"
    )
    assert (
        state(
            accepted_fragment_count=8,
            expected_fragment_count=8,
            unresolved_failed_fragment_count=0,
        )
        == "complete"
    )


def test_structure_identity_group_key_admits_typographic_aliases_without_merging() -> None:
    key = _identity_observation_group_key
    assert key("\u041a\u041d\u0421-4") == "\u043a\u043d\u04414"
    assert key("\u041a\u041d\u0421 4") == "\u043a\u043d\u04414"
    assert key("\u041a\u041d\u0421-4") != key("\u041a\u041d\u0421-5")


def test_structure_dossiers_keep_cross_source_identity_unresolved() -> None:
    nodes = [
        {
            "structure_node_id": "node-a",
            "node_kind": "facility",
            "raw_name": "Facility-1",
            "source_locator_id": "locator-a",
        },
        {
            "structure_node_id": "node-b",
            "node_kind": "facility",
            "raw_name": "Facility-1",
            "source_locator_id": "locator-b",
        },
    ]
    relationships = [
        {
            "relationship_kind": "located_in",
            "source_locator_id": "locator-a",
            "subject_structure_node_id": "node-a",
            "object_structure_node_id": None,
            "resolution_state": "unresolved_source_scoped_identity",
        },
        {
            "relationship_kind": "located_in",
            "source_locator_id": "locator-b",
            "subject_structure_node_id": None,
            "object_structure_node_id": "node-b",
            "resolution_state": "resolved_same_evidence",
        },
    ]

    dossiers = SpinePostgresRepository._structure_dossier_rows(nodes, relationships)

    assert [item["structure_node"]["structure_node_id"] for item in dossiers] == [
        "node-a",
        "node-b",
    ]
    assert dossiers[0]["relationships"] == [relationships[0]]
    assert dossiers[0]["unresolved_relationship_count"] == 1
    assert dossiers[1]["relationships"] == [relationships[1]]
    assert dossiers[1]["unresolved_relationship_count"] == 0


def test_structure_dossiers_link_work_observations_only_by_exact_locator() -> None:
    nodes = [
        {
            "structure_node_id": "facility-a",
            "node_kind": "facility",
            "raw_name": "Facility A",
            "source_locator_id": "locator-a",
        }
    ]
    work_packages = [
        {
            "work_package_id": "work-a",
            "package": {
                "work_type": {"raw": "Install pipe"},
                "scope": "zone-a",
                "source_locator_ids": ["locator-a"],
            },
        },
        {
            "work_package_id": "work-b",
            "package": {
                "work_type": {"raw": "Install pipe"},
                "scope": "zone-b",
                "source_locator_ids": ["locator-b"],
            },
        },
    ]

    dossiers = SpinePostgresRepository._structure_dossier_rows([], [], [])
    assert dossiers == []
    dossiers = SpinePostgresRepository._structure_dossier_rows(nodes, [], work_packages)

    assert dossiers[0]["work_association_state"] == "exact_shared_source_locator_candidate"
    assert dossiers[0]["linked_work_observations"] == [
        {"work_observation_id": "work-a", "work_name": "Install pipe", "scope": "zone-a"}
    ]


def test_structure_components_require_exact_resolved_evidence() -> None:
    nodes = [
        {"structure_node_id": "facility", "source_locator_id": "locator-a"},
        {"structure_node_id": "pit", "source_locator_id": "locator-a"},
        {"structure_node_id": "same-name-other-source", "source_locator_id": "locator-b"},
    ]
    relationships = [
        {
            "relationship_candidate_id": "relation-a",
            "source_locator_id": "locator-a",
            "subject_structure_node_id": "facility",
            "object_structure_node_id": "pit",
            "resolution_state": "resolved_same_evidence",
        },
        {
            "relationship_candidate_id": "relation-b",
            "source_locator_id": "locator-b",
            "subject_structure_node_id": "pit",
            "object_structure_node_id": "same-name-other-source",
            "resolution_state": "unresolved_source_scoped_identity",
        },
    ]

    components = SpinePostgresRepository._structure_component_rows(nodes, relationships)

    assert len(components) == 1
    assert [item["structure_node_id"] for item in components[0]["nodes"]] == [
        "facility",
        "pit",
    ]
    assert components[0]["relationships"] == [relationships[0]]


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


def test_runtime_migration_supplies_the_required_explicit_database_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def upgrade(configuration: object, revision: str) -> None:
        captured["revision"] = revision
        captured["database_url"] = configuration.cmd_opts.x

    monkeypatch.setattr("asd_kontur.application_spine.runtime.command.upgrade", upgrade)

    configured = settings(tmp_path)
    assert _migrate(configured) == 0
    assert captured == {
        "revision": "head",
        "database_url": [f"database_url={configured.database_url}"],
    }


def test_runtime_migration_uses_separately_supplied_protected_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    protected_url = "postgresql+psycopg://migration-role@localhost/asd"

    def upgrade(configuration: object, revision: str) -> None:
        captured["revision"] = revision
        captured["database_url"] = configuration.cmd_opts.x

    monkeypatch.setattr("asd_kontur.application_spine.runtime.command.upgrade", upgrade)
    monkeypatch.setenv("ASD_MIGRATION_DATABASE_URL", protected_url)

    assert _migrate(settings(tmp_path)) == 0
    assert captured == {"revision": "head", "database_url": [f"database_url={protected_url}"]}


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


def test_lease_keepalive_extends_a_long_running_job_lease() -> None:
    class RecordingRepository:
        def __init__(self) -> None:
            self.called = Event()

        def heartbeat_job(self, *_args: object, **_kwargs: object) -> None:
            self.called.set()

    repository = RecordingRepository()
    claimed = ClaimedJob(
        ORGANIZATION_ID,
        WORKSPACE_ID,
        UUID("018f5c3e-7b00-7000-8000-000000001803"),
        JobKind.OCR_EXTRACTION,
        {},
        "sha256:" + "0" * 64,
        1,
        1,
        "none",
    )
    keepalive = _LeaseKeepalive(  # type: ignore[arg-type]
        repository,
        claimed,
        worker_identity="synthetic-worker",
        lease_seconds=1,
    )

    keepalive.start()
    assert repository.called.wait(timeout=1)
    keepalive.stop()
    keepalive.raise_if_lost()


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
    assert parsed["EnvironmentVariables"]["ASD_EXPECTED_MIGRATION_HEAD"] == ("0033_ntd_memory")
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
