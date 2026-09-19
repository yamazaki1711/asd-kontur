# ruff: noqa: RUF001 - fixtures preserve Russian construction terminology.

from __future__ import annotations

import io
import json
import os
import runpy
import zipfile
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.worker import DocumentWorker
from asd_kontur.document_understanding.postgres import IndustrialUnderstandingRepository
from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment

pytestmark = pytest.mark.postgres


def _build_synthetic_corpus(root: Path) -> dict[str, object]:
    namespace = runpy.run_path(
        str(
            Path(__file__).resolve().parents[2]
            / "tools/build_industrial_intake_synthetic_corpus.py"
        )
    )
    return namespace["build"](root)  # type: ignore[no-any-return,operator]


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
        empty = client.get(
            f"/api/v1/workspaces/{workspace_b['workspace_id']}/project-understanding"
        )
        assert empty.status_code == 200
        assert empty.json()["reconciliation"] == {}
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
            qwen_semantic_url=None,  # This fixture exercises native DOCX/CSV extraction.
        )
        outcomes = []
        while outcome := worker.run_once():
            outcomes.append(outcome)
        # The exact number of internal materialization jobs is not a product
        # contract. The assertions below verify the required persisted view,
        # evidence navigation and workspace isolation instead.
        assert outcomes
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
        assert package["uncertainties"] == ["WORK_TYPE_MAPPING_UNRESOLVED"]
        assert "WORK_TYPE_CATALOG_UNAVAILABLE" not in view["matrix"]["matrix"]["rows"][0]["gaps"]
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
        tender_inputs = {
            item["category"]: item for item in view["intake_summary"]["tender_input_assessment"]
        }
        assert tender_inputs["design_or_working_documentation"]["state"] == "available"
        assert tender_inputs["quantity_or_estimate"]["state"] == "available"
        assert tender_inputs["draft_contract"]["state"] == "not_detected_in_classified_sources"
        assert "Contract changes" in tender_inputs["draft_contract"]["practical_limitation"]
        assert view["page_roles"]
        assert len(view["candidates"]["project_fields"]) == 3
        assert len(view["candidates"]["quantities"]) == 1
        tender_schedule = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-findings.csv"
        )
        assert tender_schedule.status_code == 200, tender_schedule.text
        assert tender_schedule.headers["content-type"] == "text/csv; charset=utf-8"
        assert tender_schedule.headers["content-disposition"].startswith("attachment;")
        assert "source_references" in tender_schedule.content.decode("utf-8-sig")
        tender_scope_schedule = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-scope-schedule.csv"
        )
        assert tender_scope_schedule.status_code == 200, tender_scope_schedule.text
        assert tender_scope_schedule.headers["content-type"] == "text/csv; charset=utf-8"
        scope_csv = tender_scope_schedule.content.decode("utf-8-sig")
        assert "work_package_id" in scope_csv
        assert "Устройство монолитной плиты" in scope_csv
        assert "candidate" in scope_csv
        tender_coverage = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-document-coverage.csv"
        )
        assert tender_coverage.status_code == 200, tender_coverage.text
        assert tender_coverage.headers["content-type"] == "text/csv; charset=utf-8"
        coverage_csv = tender_coverage.content.decode("utf-8-sig")
        assert "native_extraction_status" in coverage_csv
        assert "semantic_coverage_state" in coverage_csv
        identity_schedule = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-structure-identity-candidates.csv"
        )
        assert identity_schedule.status_code == 200, identity_schedule.text
        assert identity_schedule.headers["content-type"] == "text/csv; charset=utf-8"
        identity_csv = identity_schedule.content.decode("utf-8-sig")
        assert "automatic_merge" in identity_csv
        assert "member_raw_name" in identity_csv
        facility_scope_schedule = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-facility-work-observations.csv"
        )
        assert facility_scope_schedule.status_code == 200, facility_scope_schedule.text
        assert facility_scope_schedule.headers["content-type"] == "text/csv; charset=utf-8"
        assert "association_state" in facility_scope_schedule.content.decode("utf-8-sig")
        tender_archive = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-analysis.zip"
        )
        assert tender_archive.status_code == 200, tender_archive.text
        assert tender_archive.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(tender_archive.content)) as exported:
            assert exported.namelist() == [
                "01_tender_findings_report.docx",
                "02_tender_findings_schedule.csv",
                "03_tender_work_resource_schedule.csv",
                "04_structure_identity_candidates.csv",
                "05_document_processing_coverage.csv",
                "06_delivery_manifest.json",
                "99_analysis_status.txt",
            ]
        tender_report = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/"
            "tender-findings.docx"
        )
        assert tender_report.status_code == 200, tender_report.text
        assert (
            tender_report.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        with zipfile.ZipFile(io.BytesIO(tender_report.content)) as report:
            assert "word/document.xml" in report.namelist()
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
        isolated = client.get(
            f"/api/v1/workspaces/{workspace_b['workspace_id']}/project-understanding"
        )
        assert isolated.status_code == 200
        assert isolated.json()["candidates"]["project_fields"] == []

        quantity = view["candidates"]["quantities"][0]
        review = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/reviews",
            json={
                "candidate_kind": "quantity",
                "candidate_id": quantity["candidate_id"],
                "candidate_version": quantity["version"],
                "action": "corrected",
                "resolved_value": "13.000",
                "reason": "Исправлено по контрольному фрагменту ведомости",
            },
            headers=csrf,
        )
        assert review.status_code == 201, review.text
        first_run = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/runs",
            headers=csrf,
        )
        second_run = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding/runs",
            headers=csrf,
        )
        assert first_run.status_code == second_run.status_code == 202
        assert first_run.json()["job_id"] == second_run.json()["job_id"]
        project_run_id = UUID(first_run.json()["job_id"])
        post_review_outcomes = []
        while outcome := worker.run_once():
            post_review_outcomes.append(outcome)
            if outcome.job_id == str(project_run_id):
                break
        assert post_review_outcomes
        assert post_review_outcomes[-1].job_id == str(project_run_id)
        assert post_review_outcomes[-1].state.value == "succeeded"
        revised = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/project-understanding"
        ).json()
        assert revised["review_decisions"][0]["action"] == "corrected"
        assert revised["work_packages"][0]["package"]["quantities"][0]["raw_value"] == "13.000"


def test_zip_intake_retains_container_and_registers_members(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="archive-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Synthetic archive owner",
    )
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("ПЗ/описание.docx", _docx())
        archive.writestr("ВОР/объёмы.csv", _vor_csv())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/session/login",
            json={"username": "archive-owner", "password": "Synthetic-Owner-Password-42!"},
        )
        assert response.status_code == 200
        csrf = {"X-CSRF-Token": str(client.cookies.get("asd_csrf"))}
        workspace = client.post(
            "/api/v1/workspaces", json={"display_name": "Archive intake"}, headers=csrf
        ).json()
        uploaded = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/documents",
            files=[("files", ("исходные.zip", archive_bytes.getvalue(), "application/zip"))],
            headers=csrf,
        )
        assert uploaded.status_code == 202, uploaded.text
        assert len(uploaded.json()["accepted_document_ids"]) == 3
        documents = client.get(
            f"/api/v1/workspaces/{workspace['workspace_id']}/documents?limit=20"
        ).json()["items"]
        assert {item["media_type"] for item in documents} == {
            "application/zip",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/csv",
        }
        assert any(item["relative_path"] == "исходные/ПЗ/описание.docx" for item in documents)
        organization_id = workspace["organization_id"]
        with postgres_environment.document_worker_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(organization_id), True),
                    sa.func.set_config("asd.workspace_id", workspace["workspace_id"], True),
                )
            ).one()
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM workspace.intake_archive_members WHERE "
                        "organization_id=:o AND workspace_id=:w"
                    ),
                    {"o": organization_id, "w": workspace["workspace_id"]},
                )
                == 2
            )
        worker = DocumentWorker(
            SpinePostgresRepository(postgres_environment.document_worker_engine),
            WorkspaceObjectStore(
                settings.object_store_root,
                chunk_bytes=settings.upload_chunk_bytes,
                max_file_bytes=settings.max_file_bytes,
            ),
            worker_identity="synthetic-archive-worker",
            lease_seconds=5,
            qwen_semantic_url=None,  # Archive members are native DOCX/CSV fixtures.
        )
        outcomes = []
        while outcome := worker.run_once():
            outcomes.append(outcome)
        assert outcomes
        assert {outcome.state.value for outcome in outcomes} == {"succeeded"}


def test_qualified_synthetic_corpus_reaches_reviewable_project_model(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    corpus_root = tmp_path / "qualified-corpus"
    manifest = _build_synthetic_corpus(corpus_root)
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="understanding-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Synthetic understanding owner",
    )
    files = [
        path
        for path in sorted(corpus_root.rglob("*"))
        if path.is_file() and path.name != "corpus-manifest.json"
    ]
    relative_paths = [path.relative_to(corpus_root).as_posix() for path in files]
    with TestClient(app) as client:
        csrf = _login(client)
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Квалификационный обезличенный объект"},
            headers=csrf,
        ).json()
        workspace_id = workspace["workspace_id"]
        workspace_b = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Изолированный контрольный объект"},
            headers=csrf,
        ).json()
        uploaded = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files=[
                ("files", (path.name, path.read_bytes(), "application/octet-stream"))
                for path in files
            ],
            data={"relative_paths": json.dumps(relative_paths, ensure_ascii=False)},
            headers=csrf,
        )
        assert uploaded.status_code == 202, uploaded.text
        batch = uploaded.json()
        assert batch["rejected_count"] == 1
        assert len(batch["accepted_document_ids"]) == 14
        controlled_job_id = batch["job_ids"][0]
        paused = client.post(
            f"/api/v1/workspaces/{workspace_id}/jobs/{controlled_job_id}/pause",
            headers=csrf,
        )
        assert paused.status_code == 200, paused.text
        assert paused.json()["state"] == "paused"
        resumed = client.post(
            f"/api/v1/workspaces/{workspace_id}/jobs/{controlled_job_id}/resume",
            headers=csrf,
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["state"] == "queued"

        repeated_path = corpus_root / "01_Проект" / "Раздел_ПД.pdf"
        repeated = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files=[
                (
                    "files",
                    (repeated_path.name, repeated_path.read_bytes(), "application/pdf"),
                )
            ],
            data={"relative_paths": json.dumps(["01_Проект/Раздел_ПД.pdf"], ensure_ascii=False)},
            headers=csrf,
        )
        assert repeated.status_code == 202, repeated.text
        assert len(repeated.json()["duplicate_document_ids"]) == 1
        assert repeated.json()["job_ids"] == []

        worker = DocumentWorker(
            SpinePostgresRepository(postgres_environment.document_worker_engine),
            WorkspaceObjectStore(
                settings.object_store_root,
                chunk_bytes=settings.upload_chunk_bytes,
                max_file_bytes=settings.max_file_bytes,
            ),
            worker_identity="qualified-corpus-worker",
            lease_seconds=5,
            qwen_semantic_url=None,
        )
        outcomes = []
        for _ in range(1000):
            outcome = worker.run_once()
            if outcome is None:
                break
            outcomes.append(outcome)
        else:
            pytest.fail("qualified corpus worker did not reach a terminal queue state")
        states = {outcome.state.value for outcome in outcomes}
        assert "succeeded" in states
        assert "failed" in states
        failed_job_id = next(
            outcome.job_id for outcome in outcomes if outcome.state.value == "failed"
        )
        retried = client.post(
            f"/api/v1/workspaces/{workspace_id}/jobs/{failed_job_id}/retry",
            headers=csrf,
        )
        assert retried.status_code == 202, retried.text
        assert retried.json()["state"] == "queued"
        assert retried.json()["job_id"] != failed_job_id
        assert worker.run_once() is not None

        documents = client.get(
            f"/api/v1/workspaces/{workspace_id}/documents?limit=200&sort=recorded_asc"
        ).json()["items"]
        assert len(documents) == 14
        assert sum(item["admission_status"] == "quarantined" for item in documents) == 1
        assert sum(item["media_type"] == "application/zip" for item in documents) == 1
        assert sum("Дополнительный_комплект/" in item["relative_path"] for item in documents) == 2

        view_response = client.get(f"/api/v1/workspaces/{workspace_id}/project-understanding")
        assert view_response.status_code == 200, view_response.text
        view = view_response.json()
        denominator = manifest["control_denominator"]
        with postgres_environment.owner_engine.connect() as diagnostic_connection:
            diagnostics = [
                dict(row)
                for row in diagnostic_connection.execute(
                    sa.text(
                        "SELECT j.job_kind,j.typed_failure_code,r.result_manifest FROM "
                        "workspace.durable_jobs j LEFT JOIN workspace.job_terminal_receipts r ON "
                        "r.organization_id=j.organization_id AND r.workspace_id=j.workspace_id AND "
                        "r.job_id=j.job_id WHERE j.workspace_id=:workspace "
                        "AND j.state<> 'succeeded'"
                    ),
                    {"workspace": workspace_id},
                ).mappings()
            ]
        assert view["project_definition"]["definition"]["fields"], [diagnostics]
        assert len(view["work_packages"]) >= int(denominator["work_types"])
        assert len(view["candidates"]["quantities"]) >= int(denominator["quantities"])
        assert len(view["candidates"]["materials"]) >= int(denominator["materials"])
        assert view["matrix"]["matrix"]["rows"]
        assert view["defects"]
        projection_repository = IndustrialUnderstandingRepository(
            postgres_environment.document_worker_engine
        )
        first_projection = projection_repository.rebuild_project_understanding_projection(
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=UUID(workspace_id),
        )
        with postgres_environment.document_worker_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config(
                        "asd.organization_id", str(workspace["organization_id"]), True
                    ),
                    sa.func.set_config("asd.workspace_id", workspace_id, True),
                )
            ).one()
            connection.execute(
                sa.text(
                    "DELETE FROM projection.project_understanding_entries "
                    "WHERE workspace_id=:workspace"
                ),
                {"workspace": workspace_id},
            )
        rebuilt_projection = projection_repository.rebuild_project_understanding_projection(
            organization_id=UUID(workspace["organization_id"]),
            workspace_id=UUID(workspace_id),
        )
        assert rebuilt_projection == first_projection

        quantity = view["candidates"]["quantities"][0]
        reviewed = client.post(
            f"/api/v1/workspaces/{workspace_id}/project-understanding/reviews",
            json={
                "candidate_kind": "quantity",
                "candidate_id": quantity["candidate_id"],
                "candidate_version": quantity["version"],
                "action": "confirmed",
                "reason": "Сверено с контрольным фрагментом ведомости",
            },
            headers=csrf,
        )
        assert reviewed.status_code == 201, reviewed.text
        exact = client.get(
            f"/api/v1/workspaces/{workspace_id}/evidence/locators/{quantity['source_locator_id']}"
        )
        assert exact.status_code == 200, exact.text
        assert exact.json()["locator"]["source_locator_id"] == quantity["source_locator_id"]

        pilot_results: dict[str, dict[str, object]] = {}
        for mode in ("Tender", "Support", "Audit", "Restoration"):
            formed = client.post(
                f"/api/v1/workspaces/{workspace_id}/modes/{mode}/result",
                headers=csrf,
            )
            assert formed.status_code == 201, formed.text
            pilot_results[mode] = formed.json()
            assert pilot_results[mode]["source_manifest"]
            assert pilot_results[mode]["items"]
            assert (
                pilot_results[mode]["normative_notice"]
                == "Актуальность редакций нормативных документов не проверена"
            )

        tender_scope_schedule = pilot_results["Tender"]["tender_scope_schedule"]
        assert isinstance(tender_scope_schedule, list)
        assert len(tender_scope_schedule) == len(view["work_packages"])
        assert all(item["candidate_status"] == "candidate" for item in tender_scope_schedule)
        assert all(item["source_locator_ids"] for item in tender_scope_schedule)
        assert all(item["source_references"] for item in tender_scope_schedule), (
            "Every Tender scope observation must retain a readable evidence pointer"
        )

        audit_items = pilot_results["Audit"]["items"]
        assert isinstance(audit_items, list)
        first_audit_item = audit_items[0]
        assert isinstance(first_audit_item, dict)
        audit_review = client.post(
            f"/api/v1/workspaces/{workspace_id}/modes/Audit/result/items/"
            f"{first_audit_item['item_id']}/reviews",
            json={
                "action": "status_changed",
                "resolved_fields": {"status": "requires_clarification"},
                "comment": "Ответственный назначается после проверки исходного фрагмента",
            },
            headers=csrf,
        )
        assert audit_review.status_code == 201, audit_review.text
        assert audit_review.json()["reviewed_item_count"] == 1

        for kind, output_format in (
            ("disagreement_protocol", "docx"),
            ("contract_changes", "pdf"),
        ):
            blocked_contract_export = client.post(
                f"/api/v1/workspaces/{workspace_id}/modes/Tender/exports",
                json={"export_kind": kind, "output_format": output_format},
                headers=csrf,
            )
            assert blocked_contract_export.status_code == 409, blocked_contract_export.text
            assert (
                blocked_contract_export.json()["error"]["code"]
                == "pilot_contract_analysis_required"
            )

        export_cases = (
            ("Support", "requirement_matrix", "pdf"),
            ("Support", "id_package", "zip"),
            ("Support", "register", "docx"),
            ("Audit", "audit_report", "docx"),
            ("Audit", "audit_report", "pdf"),
            ("Restoration", "recovery_plan", "docx"),
            ("Restoration", "recovery_plan", "pdf"),
            ("Restoration", "recovered_drafts", "zip"),
            ("Tender", "workspace_results", "zip"),
        )
        created_exports = []
        for mode, kind, output_format in export_cases:
            created = client.post(
                f"/api/v1/workspaces/{workspace_id}/modes/{mode}/exports",
                json={"export_kind": kind, "output_format": output_format},
                headers=csrf,
            )
            assert created.status_code == 201, created.text
            export = created.json()
            assert export["size_bytes"] > 100
            assert export["content_digest"].startswith("sha256:")
            created_exports.append(export)
        tender_item = pilot_results["Tender"]["items"][0]
        assert isinstance(tender_item, dict)
        accepted_tender_item = client.post(
            f"/api/v1/workspaces/{workspace_id}/modes/Tender/result/items/"
            f"{tender_item['item_id']}/reviews",
            json={
                "action": "accepted",
                "resolved_fields": None,
                "comment": "Вывод принят после повторной проверки источника",
            },
            headers=csrf,
        )
        assert accepted_tender_item.status_code == 201, accepted_tender_item.text
        regenerated_archive = client.post(
            f"/api/v1/workspaces/{workspace_id}/modes/Tender/exports",
            json={"export_kind": "workspace_results", "output_format": "zip"},
            headers=csrf,
        )
        assert regenerated_archive.status_code == 201, regenerated_archive.text
        assert regenerated_archive.json()["export_id"] == created_exports[-1]["export_id"]
        assert regenerated_archive.json()["version"] == created_exports[-1]["version"] + 1
        unchanged_archive = client.post(
            f"/api/v1/workspaces/{workspace_id}/modes/Tender/exports",
            json={"export_kind": "workspace_results", "output_format": "zip"},
            headers=csrf,
        )
        assert unchanged_archive.status_code == 201, unchanged_archive.text
        assert unchanged_archive.json() == regenerated_archive.json()
        refreshed_tender = client.get(f"/api/v1/workspaces/{workspace_id}/modes/Tender/result")
        assert refreshed_tender.status_code == 200, refreshed_tender.text
        latest_exports = refreshed_tender.json()["exports"]
        export_ids = [item["export_id"] for item in latest_exports]
        assert len(export_ids) == len(set(export_ids))
        assert (
            next(
                item
                for item in latest_exports
                if item["export_id"] == created_exports[-1]["export_id"]
            )["version"]
            == regenerated_archive.json()["version"]
        )
        content = client.get(
            f"/api/v1/workspaces/{workspace_id}/pilot-exports/"
            f"{created_exports[-1]['export_id']}/content"
        )
        assert content.status_code == 200
        assert content.headers["accept-ranges"] == "bytes"
        with zipfile.ZipFile(io.BytesIO(content.content)) as archive:
            names = set(archive.namelist())
        assert "manifest.json" in names
        assert "tender/result.docx" in names
        assert "support/result.pdf" in names
        ranged = client.get(
            f"/api/v1/workspaces/{workspace_id}/pilot-exports/"
            f"{created_exports[0]['export_id']}/content",
            headers={"Range": "bytes=0-63"},
        )
        assert ranged.status_code == 206
        assert len(ranged.content) == 64
        assert ranged.headers["content-range"].startswith("bytes 0-63/")
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_b['workspace_id']}/modes/Tender/result"
            ).status_code
            == 404
        )

        with postgres_environment.document_worker_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config(
                        "asd.organization_id", str(workspace["organization_id"]), True
                    ),
                    sa.func.set_config("asd.workspace_id", workspace_id, True),
                )
            ).one()
            assert connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.intake_archive_members "
                    "WHERE workspace_id=:workspace"
                ),
                {"workspace": workspace_id},
            ) == int(denominator["expected_intake_outcomes"]["archive_members"])

        receipt_path = os.environ.get("ASD_INTAKE_CORPUS_RECEIPT")
        if receipt_path:
            destination = Path(receipt_path)
            if not destination.is_absolute():
                raise ValueError("ASD_INTAKE_CORPUS_RECEIPT must be outside Git")
            with postgres_environment.owner_engine.connect() as connection:
                job_counts = dict(
                    connection.execute(
                        sa.text(
                            "SELECT state,count(*) FROM workspace.durable_jobs "
                            "WHERE workspace_id=:workspace GROUP BY state"
                        ),
                        {"workspace": workspace_id},
                    ).all()
                )
                page_routes = {
                    f"{kind}:{route}": int(count)
                    for kind, route, count in connection.execute(
                        sa.text(
                            "SELECT primary_kind,ocr_route,count(*) FROM "
                            "workspace.document_page_health_versions WHERE workspace_id=:workspace "
                            "GROUP BY primary_kind,ocr_route"
                        ),
                        {"workspace": workspace_id},
                    ).all()
                }
            receipt = {
                "corpus_version": manifest["corpus_version"],
                "logical_fingerprint": manifest["logical_fingerprint"],
                "selected_files": len(files),
                "accepted_documents": len(batch["accepted_document_ids"]),
                "rejected_uploads": batch["rejected_count"],
                "duplicate_replay": len(repeated.json()["duplicate_document_ids"]),
                "registered_documents": len(documents),
                "quarantined_documents": sum(
                    item["admission_status"] == "quarantined" for item in documents
                ),
                "job_counts": dict(sorted(job_counts.items())),
                "page_routes": dict(sorted(page_routes.items())),
                "project_fields": len(view["candidates"]["project_fields"]),
                "work_types": len(view["candidates"]["work_types"]),
                "quantities": len(view["candidates"]["quantities"]),
                "materials": len(view["candidates"]["materials"]),
                "work_packages": len(view["work_packages"]),
                "matrix_rows": len(view["matrix"]["matrix"]["rows"]),
                "defects": len(view["defects"]),
                "review_decisions": 1,
            }
            destination.write_text(
                json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

        prepared = client.post(
            f"/api/v1/workspaces/{workspace_id}/lifecycle/reset/prepare",
            json={"confirmation": "PREPARE_WORKSPACE_RESET"},
            headers=csrf,
        )
        assert prepared.status_code == 200, prepared.text
        challenge = prepared.json()
        reset = client.post(
            f"/api/v1/workspaces/{workspace_id}/lifecycle/reset/execute",
            json={
                "challenge_id": challenge["challenge_id"],
                "confirmation_text": challenge["confirmation_text"],
            },
            headers=csrf,
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["outcome"] == "verified"
        remaining_workspace_ids = {
            item["workspace_id"] for item in client.get("/api/v1/workspaces").json()
        }
        assert workspace_id not in remaining_workspace_ids
        assert workspace_b["workspace_id"] in remaining_workspace_ids
        with postgres_environment.owner_engine.connect() as connection:
            for table in (
                "intake_archive_members",
                "project_candidate_review_decisions",
                "pilot_export_versions",
                "pilot_result_item_decisions",
                "pilot_mode_result_versions",
            ):
                assert (
                    connection.scalar(
                        sa.text(
                            f"SELECT count(*) FROM workspace.{table} WHERE workspace_id=:workspace"
                        ),
                        {"workspace": workspace_id},
                    )
                    == 0
                )
