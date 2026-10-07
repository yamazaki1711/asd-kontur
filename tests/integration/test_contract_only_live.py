"""Opt-in isolated contract-only journey with the persistent local Qwen runtime.

The corpus is synthetic and changed-party. It never uses the public database or
manually creates successor jobs; the ordinary orchestrator and worker decide
what runs. This is an integration qualification, not a release-readiness claim.
"""

# ruff: noqa: RUF001 -- Synthetic Russian contract clauses contain Cyrillic.

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.orchestrator import ProjectOrchestrator
from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.worker import DocumentWorker
from asd_kontur.tender.qwen_contract_analysis import contract_proposed_wording_has_placeholder
from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("ASD_RUN_LIVE_CONTRACT_ONLY") != "1",
        reason="Set ASD_RUN_LIVE_CONTRACT_ONLY=1 for the bounded local-Qwen journey",
    ),
]

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _contract_docx() -> bytes:
    paragraphs = (
        "ДОГОВОР СТРОИТЕЛЬНОГО ПОДРЯДА",
        "ООО Северный Берег (Заказчик) и ООО Теплоконтур (Подрядчик) заключили договор.",
        "1.1. Подрядчик реконструирует участок тепловой сети "
        "по переданной Заказчиком документации.",
        "1.2. Техническое задание (Приложение № 1) является неотъемлемой частью "
        "договора и определяет состав работ. Приложение № 1 передаётся отдельно.",
        "7.4. Заказчик оплачивает принятые работы после поступления средств от инвестора. "
        "До поступления указанных средств обязанность Заказчика по оплате не возникает.",
        "9.2. Подрядчик устраняет за свой счёт недостатки работ, возникшие по его вине, "
        "в течение гарантийного срока 24 месяца со дня приёмки.",
    )
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(value)}</w:t></w:r></w:p>'
        for value in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_WORD_NS}"><w:body>{body}</w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'wordprocessingml.document.main+xml"/></Types>'
    )
    package_relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", package_relationships)
        package.writestr("word/document.xml", document)
    return target.getvalue()


def _qwen_idle() -> bool:
    request = urllib.request.Request("http://127.0.0.1:8790/health", method="GET")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        request, timeout=5
    ) as response:
        value = json.load(response)
    return isinstance(value, dict) and value.get("status") == "QWEN_READY_IDLE"


def _docx_text(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        assert package.testzip() is None
        root = ElementTree.fromstring(package.read("word/document.xml"))
    return "".join(node.text or "" for node in root.iter(f"{{{_WORD_NS}}}t"))


def test_contract_only_upload_autonomously_reaches_editable_outputs(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    if any(shutil.which(tool) is None for tool in ("soffice", "pdfinfo", "pdftoppm")):
        pytest.skip("DOCX page-rendering tools are unavailable")
    if not _qwen_idle():
        pytest.skip("Persistent Qwen is occupied; do not compete with owner processing")
    objects = tmp_path / "objects"
    archives = tmp_path / "archives"
    objects.mkdir()
    archives.mkdir()
    settings = SpineSettings(
        database_url=postgres_environment.application_engine.url.render_as_string(
            hide_password=False
        ),
        lifecycle_database_url=postgres_environment.lifecycle_engine.url.render_as_string(
            hide_password=False
        ),
        worker_database_url=postgres_environment.document_worker_engine.url.render_as_string(
            hide_password=False
        ),
        destruction_database_url=postgres_environment.destruction_engine.url.render_as_string(
            hide_password=False
        ),
        object_store_root=objects,
        archive_store_root=archives,
        session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
        audit_pepper="synthetic-contract-only-acceptance-pepper",
        max_file_bytes=4 * 1024 * 1024,
        max_batch_bytes=8 * 1024 * 1024,
    )
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="synthetic-contract-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Synthetic contract owner",
    )
    repository = SpinePostgresRepository(
        postgres_environment.document_worker_engine,
        contract_view_engine=postgres_environment.application_engine,
    )
    orchestrator = ProjectOrchestrator(repository)
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/session/login",
            json={
                "username": "synthetic-contract-owner",
                "password": "Synthetic-Owner-Password-42!",
            },
        )
        assert login.status_code == 200, login.text
        csrf = client.cookies.get("asd_csrf")
        assert csrf
        headers = {"X-CSRF-Token": csrf}
        created = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Heat network contract-only qualification"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        workspace = created.json()
        workspace_id = UUID(workspace["workspace_id"])
        organization_id = UUID(workspace["organization_id"])
        upload = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files=[("files", ("agreement.docx", _contract_docx(), _DOCX_MIME))],
            headers=headers,
        )
        assert upload.status_code == 202, upload.text

        worker = DocumentWorker(
            repository,
            app.state.container.object_store,
            worker_identity="isolated-contract-only-worker",
            lease_seconds=30,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        deadline = time.monotonic() + 900
        next_sweep_at = 0.0
        last_outcome_at = time.monotonic()
        seen_jobs: dict[str, int] = {}
        view: dict[str, object] = {}
        while time.monotonic() < deadline:
            if time.monotonic() >= next_sweep_at:
                sweep = orchestrator.run_once()
                assert not sweep.scope_failures, sweep.scope_failures
                next_sweep_at = time.monotonic() + 30
            outcome = worker.run_once()
            if outcome is not None:
                seen_jobs[outcome.outcome_code] = seen_jobs.get(outcome.outcome_code, 0) + 1
                last_outcome_at = time.monotonic()
            response = client.get(f"/api/v1/workspaces/{workspace_id}/tender/contract-analysis")
            assert response.status_code == 200, response.text
            view = response.json()
            revisions = view.get("revised_contracts") or []
            reference_review = view.get("reference_review")
            coherence_review = view.get("coherence_review")
            if (
                view.get("disagreement_items")
                and isinstance(revisions, list)
                and any(
                    isinstance(item, dict)
                    and item.get("state") == "exact_source_candidate_available"
                    for item in revisions
                )
                and isinstance(reference_review, dict)
                and reference_review.get("status") == "complete"
                and isinstance(coherence_review, dict)
                and coherence_review.get("status") == "reviewed_bounded_context"
            ):
                break
            if time.monotonic() - last_outcome_at > 45:
                with postgres_environment.owner_engine.connect() as connection:
                    active_jobs = connection.scalar(
                        sa.text(
                            "SELECT count(*) FROM workspace.durable_jobs WHERE "
                            "organization_id=:o AND workspace_id=:w AND "
                            "state IN ('queued','leased','running')"
                        ),
                        {"o": organization_id, "w": workspace_id},
                    )
                if active_jobs == 0:
                    break
            if outcome is None:
                time.sleep(0.5)

        issue_rows = view.get("issues")
        assert view.get("disagreement_items"), {
            "status": view.get("status"),
            "issues": len(issue_rows) if isinstance(issue_rows, list) else 0,
            "revised_contracts": view.get("revised_contracts"),
            "gaps": view.get("gaps"),
            "jobs": seen_jobs,
        }
        clauses = view.get("clauses")
        assert isinstance(clauses, list)
        assert all(isinstance(item.get("display_clause_ref"), str) for item in clauses)
        assert all(
            not str(item.get("display_clause_ref")).startswith(("clause_", "batch-"))
            for item in clauses
        )
        assert any("9.2." in str(item.get("source_text")) for item in clauses)
        risks = view.get("issues")
        assert isinstance(risks, list)
        assert any("7.4." in str(item.get("source_text")) for item in clauses)
        assert not any("9.2." in str(item.get("trigger_text")) for item in risks)
        references = view.get("attachment_references")
        assert isinstance(references, list) and references
        assert any(
            "Приложение № 1" in str(item.get("source_quote"))
            and item.get("match_decision") == "unresolved"
            for item in references
        ), references
        gaps = view.get("gaps")
        assert isinstance(gaps, list)
        assert "CONTRACT_REFERENCED_DOCUMENT_UNRESOLVED" in gaps
        for suffix in (
            "disagreement-protocol.docx",
            "revised-contract.docx",
            "revised-contract-package.zip",
        ):
            artifact = client.get(f"/api/v1/workspaces/{workspace_id}/tender/{suffix}")
            assert artifact.status_code == 200, (suffix, artifact.text[:300])
            assert artifact.content
            (tmp_path / suffix).write_bytes(artifact.content)
        for name in ("disagreement-protocol", "revised-contract"):
            source = tmp_path / f"{name}.docx"
            converted = subprocess.run(
                [
                    "soffice",
                    f"-env:UserInstallation={(tmp_path / 'libreoffice-profile').as_uri()}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            pdf = tmp_path / f"{name}.pdf"
            assert converted.returncode == 0 and pdf.is_file(), converted.stderr
            info = subprocess.run(
                ["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=30, check=True
            )
            page_line = next(line for line in info.stdout.splitlines() if line.startswith("Pages:"))
            page_count = int(page_line.split(":", 1)[1].strip())
            assert page_count > 0
            subprocess.run(
                ["pdftoppm", "-png", "-r", "100", str(pdf), str(tmp_path / f"{name}-page")],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            assert len(list(tmp_path.glob(f"{name}-page-*.png"))) == page_count
        revised = client.get(f"/api/v1/workspaces/{workspace_id}/tender/revised-contract.docx")
        revised_text = _docx_text(revised.content)
        assert not contract_proposed_wording_has_placeholder(revised_text)
        assert "9.2." in revised_text
        revised_clauses = view.get("revised_clauses")
        assert isinstance(revised_clauses, list) and revised_clauses
        coherence_review = view.get("coherence_review")
        assert isinstance(coherence_review, dict)
        with postgres_environment.owner_engine.connect() as connection:
            coherence_receipts = [
                dict(row)
                for row in connection.execute(
                    sa.text(
                        "SELECT receipt.typed_outcome_code,receipt.result_manifest "
                        "FROM workspace.job_terminal_receipts receipt JOIN "
                        "workspace.durable_jobs job ON job.organization_id=receipt.organization_id "
                        "AND job.workspace_id=receipt.workspace_id AND job.job_id=receipt.job_id "
                        "WHERE job.organization_id=:o AND job.workspace_id=:w AND "
                        "job.job_kind='CONTRACT_COHERENCE_REVIEW'"
                    ),
                    {"o": organization_id, "w": workspace_id},
                ).mappings()
            ]
        assert coherence_review.get("status") == "reviewed_bounded_context", {
            "coherence_review": coherence_review,
            "job_outcomes": seen_jobs,
            "coherence_receipts": coherence_receipts,
        }
        assert int(coherence_review.get("accepted_contexts") or 0) > 0
        assert any(
            " ".join(str(item.get("revised_text") or "").split()) in " ".join(revised_text.split())
            for item in revised_clauses
        )
        package = client.get(
            f"/api/v1/workspaces/{workspace_id}/tender/revised-contract-package.zip"
        )
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            assert archive.testzip() is None
            assert "manifest.json" in archive.namelist()
        with postgres_environment.owner_engine.connect() as connection:
            contract_jobs = connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.durable_jobs WHERE "
                    "organization_id=:o AND workspace_id=:w AND job_kind='CONTRACT_ANALYSIS' "
                    "AND state='succeeded'"
                ),
                {"o": organization_id, "w": workspace_id},
            )
        assert contract_jobs and contract_jobs > 0
