# ruff: noqa: RUF001 - fixtures preserve Russian construction terminology.

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.worker import DocumentWorker
from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment

pytestmark = pytest.mark.postgres


def _database_url(engine: sa.Engine) -> str:
    return engine.url.render_as_string(hide_password=False)


def _settings(environment: PostgreSQLEnvironment, root: Path) -> SpineSettings:
    objects = root / "objects"
    archives = root / "archives"
    objects.mkdir()
    archives.mkdir()
    return SpineSettings(
        database_url=_database_url(environment.application_engine),
        lifecycle_database_url=_database_url(environment.lifecycle_engine),
        worker_database_url=_database_url(environment.document_worker_engine),
        destruction_database_url=_database_url(environment.destruction_engine),
        object_store_root=objects,
        archive_store_root=archives,
        session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
        audit_pepper="synthetic-industrial-understanding-audit-pepper",
        max_file_bytes=4 * 1024 * 1024,
        max_batch_bytes=8 * 1024 * 1024,
    )


def _docx() -> bytes:
    body = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Пояснительная записка</w:t></w:r></w:p>
    <w:p><w:r><w:t>Наименование объекта: Производственный корпус</w:t></w:r></w:p>
    <w:p><w:r><w:t>Назначение объекта: Выпуск строительных материалов</w:t></w:r></w:p>
    <w:p><w:r><w:t>Состав объекта: Корпус; наружная тепловая сеть</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", body)
    return target.getvalue()


def _vor_csv() -> bytes:
    return (
        "Ведомость объёмов работ;;;;;\n"
        "Вид работ;Объём;Ед. изм.;Материал;Количество материала;Ед. изм. материала\n"
        "Устройство монолитной плиты;+12,350;м³;Бетон В25;12,350;м³\n"
    ).encode()


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/session/login",
        json={"username": "understanding-owner", "password": "Synthetic-Owner-Password-42!"},
    )
    assert response.status_code == 200
    csrf = client.cookies.get("asd_csrf")
    assert csrf
    return {"X-CSRF-Token": csrf}


def test_browser_to_evidence_project_understanding_is_workspace_scoped(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="understanding-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Synthetic understanding owner",
    )
    with TestClient(app) as client:
        csrf = _login(client)
        workspace_a = client.post(
            "/api/v1/workspaces", json={"display_name": "Understanding A"}, headers=csrf
        ).json()
        workspace_b = client.post(
            "/api/v1/workspaces", json={"display_name": "Understanding B"}, headers=csrf
        ).json()
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_b['workspace_id']}/project-understanding"
            ).status_code
            == 404
        )
        upload = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/documents",
            files=[
                (
                    "files",
                    (
                        "explanatory-note.docx",
                        _docx(),
                        "application/octet-stream",
                    ),
                ),
                ("files", ("quantities.csv", _vor_csv(), "text/plain")),
            ],
            headers=csrf,
        )
        assert upload.status_code == 202, upload.text
        assert len(upload.json()["accepted_document_ids"]) == 2

        worker = DocumentWorker(
            SpinePostgresRepository(postgres_environment.document_worker_engine),
            WorkspaceObjectStore(
                settings.object_store_root,
                chunk_bytes=settings.upload_chunk_bytes,
                max_file_bytes=settings.max_file_bytes,
            ),
            worker_identity="synthetic-understanding-worker",
            lease_seconds=5,
        )
        outcomes = []
        while outcome := worker.run_once():
            outcomes.append(outcome)
        assert len(outcomes) == 34
        assert {outcome.state.value for outcome in outcomes} == {"succeeded"}

        response = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding"
        )
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["reconciliation"]["terminal_status"] == "partial"
        assert view["project_definition"]["definition"]["fields"]["object_name"]["raw_value"] == (
            "Производственный корпус"
        )
        assert view["project_definition"]["definition"]["fields"]["purpose"]["raw_value"] == (
            "Выпуск строительных материалов"
        )
        assert len(view["work_packages"]) == 1
        package = view["work_packages"][0]["package"]
        assert package["work_type"]["raw"] == "Устройство монолитной плиты"
        assert package["quantities"][0]["raw_value"] == "+12,350"
        assert package["quantities"][0]["raw_unit"] == "м³"
        assert package["materials"][0]["raw_name"] == "Бетон В25"
        assert view["matrix"]["matrix"]["complete"] is False
        gap_codes = {item["code"] for item in view["normative_profile"]["gaps"]}
        denominator = view["normative_profile"]["corpus_denominator"]
        assert denominator["spds_members"] >= 0
        if denominator["spds_members"]:
            assert denominator["manifest_fingerprint"].startswith("sha256:")
        else:
            assert denominator["gap"] == "SPDS_CORPUS_MANIFEST_UNAVAILABLE"
        assert "VERIFIED_PD_RD_NTD_UNAVAILABLE" in gap_codes
        assert "ACTIVE_PD_RD_RULE_VERSION_UNAVAILABLE" in gap_codes
        assert view["authority_layers"]["normative_authority"] == "verified_subset_only"
        assert view["normative_profile"]["completeness_status"] == "blocked"
        assert view["page_roles"]
        object_locator = view["project_definition"]["definition"]["fields"]["object_name"][
            "source_locator_id"
        ]
        assert object_locator in view["evidence_index"]
        exact = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/evidence/locators/{object_locator}"
        )
        assert exact.status_code == 200, exact.text
        assert exact.json()["locator"]["source_locator_id"] == object_locator
        assert exact.json()["locator"]["region"] != [0.0, 0.0, 1.0, 1.0]
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_b['workspace_id']}/evidence/locators/"
                f"{object_locator}"
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_b['workspace_id']}/project-understanding"
            ).status_code
            == 404
        )
