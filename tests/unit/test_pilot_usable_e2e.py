from __future__ import annotations

import io
import zipfile
from uuid import UUID

from pypdf import PdfReader

from asd_kontur.pilot.builder import build_pilot_result
from asd_kontur.pilot.models import PilotExportFormat, PilotExportKind, PilotMode
from asd_kontur.pilot.render import render_export, render_workspace_archive

WORKSPACE_ID = UUID("ea593b87-c5c8-44e0-b478-9f6be9ca7a87")
PROJECT_ID = UUID("4c4a8dc5-9fee-4241-b408-70172f19aa7c")
MATRIX_ID = UUID("ee792cd2-b81d-4275-90c2-24610fc07547")


def _project() -> dict[str, object]:
    locator = "f8d343e5-d518-46d0-8d0b-b5a85aa5643e"
    return {
        "reconciliation": {"terminal_status": "partial"},
        "project_definition": {
            "project_definition_id": str(PROJECT_ID),
            "version": 1,
            "definition": {
                "fields": {
                    "object_name": {
                        "normalized_value": "Учебно-производственный корпус",
                        "source_locator_id": locator,
                    }
                }
            },
        },
        "matrix": {"matrix_id": str(MATRIX_ID), "version": 1, "matrix": {"rows": []}},
        "work_packages": [
            {
                "work_package_id": "2a6d844d-e79c-4511-9633-b1106a583ec8",
                "package": {
                    "work_type": {
                        "raw": "Устройство монолитной плиты",
                        "normalized": "устройство монолитной плиты",
                    },
                    "scope": "zone:A",
                    "candidate_observation_count": 1,
                    "quantities": [
                        {
                            "raw_value": "12,350",
                            "raw_unit": "м³",
                            "source_locator_id": locator,
                        }
                    ],
                    "materials": [
                        {
                            "raw_name": "Бетон B25",
                            "raw_quantity": "12,350",
                            "raw_unit": "м³",
                            "source_locator_id": locator,
                        }
                    ],
                    "source_locator_ids": [locator],
                },
            }
        ],
        "defects": [
            {
                "defect_id": "7af17d42-7b84-4632-b727-bd7554787c77",
                "version": 1,
                "defect_kind": "quantity_mismatch",
                "source_locator_ids": [locator],
            }
        ],
        "evidence_index": {locator: {"safe_display_name": "ВОР.xlsx"}},
    }


def _documents() -> list[dict[str, object]]:
    return [
        {
            "document_id": "707f810d-cc9f-4417-839a-a2532146d488",
            "version": 1,
            "safe_display_name": "ВОР.xlsx",
            "source_version_id": "9fe4013e-c1ca-47ba-957f-13e8e3a9400d",
            "content_digest": "sha256:" + "1" * 64,
            "extraction_status": "complete",
        }
    ]


def test_pilot_result_is_deterministic_and_keeps_exact_locator() -> None:
    first = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.TENDER,
        project=_project(),
        documents=_documents(),
        support={},
    )
    second = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.TENDER,
        project=_project(),
        documents=_documents(),
        support={},
    )

    assert first == second
    assert first["fingerprint"].startswith("sha256:")
    assert first["items"][0]["source_locator_ids"] == ["f8d343e5-d518-46d0-8d0b-b5a85aa5643e"]
    assert first["normative_notice"] == "Актуальность редакций нормативных документов не проверена"


def test_tender_exposes_missing_contract_input_without_inventing_contract_review() -> None:
    result = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.TENDER,
        project=_project(),
        documents=_documents(),
        support={},
    )

    contract_item = next(
        item for item in result["items"] if item["kind"] == "contract_input_unavailable"
    )
    assert contract_item["title"] == "Договор не предоставлен для договорного анализа"
    assert "не сопоставлялись" in contract_item["description"]
    assert contract_item["source_locator_ids"] == []
    assert "Предоставить актуальную редакцию договора" in contract_item["recommended_action"]


def test_tender_material_gap_does_not_claim_an_unparsed_estimate_omission() -> None:
    project = _project()
    project["defects"] = [
        {
            "defect_id": "material-comparison-input",
            "version": 1,
            "defect_kind": "estimate_material_comparison_input_unavailable",
            "source_locator_ids": ["f8d343e5-d518-46d0-8d0b-b5a85aa5643e"],
        }
    ]

    result = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.TENDER,
        project=project,
        documents=_documents(),
        support={},
    )

    item = next(entry for entry in result["items"] if entry["kind"] == "defect")
    assert item["title"] == "Ресурсная часть сметы для сопоставления материалов не извлечена"
    assert "не считать материал пропущенным" in item["recommended_action"]


def test_tender_scope_schedule_keeps_identical_work_names_in_distinct_scopes() -> None:
    project = _project()
    packages = project["work_packages"]
    assert isinstance(packages, list)
    second = {
        **packages[0],
        "work_package_id": "8a6d844d-e79c-4511-9633-b1106a583ec8",
        "package": {
            **packages[0]["package"],
            "scope": "zone:B",
            "quantities": [
                {
                    "raw_value": "8,000",
                    "raw_unit": "м³",
                    "source_locator_id": "second-locator",
                }
            ],
            "source_locator_ids": ["second-locator"],
            "uncertainties": ["SAME_WORK_NAME_DIFFERENT_SCOPE"],
        },
    }
    packages.append(second)
    project["evidence_index"] = {
        **project["evidence_index"],
        "second-locator": {
            "safe_display_name": "ВОР второй зоны.xlsx",
            "document_version": 2,
            "locator_value": "sheet:Зона B!C7",
        },
    }

    result = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.TENDER,
        project=project,
        documents=_documents(),
        support={},
    )

    schedule = result["tender_scope_schedule"]
    assert len(schedule) == 2
    assert result["summary"]["candidate_work_observation_groups"] == 2
    assert "work_packages" not in result["summary"]
    assert [item["scope"] for item in schedule] == ["zone:A", "zone:B"]
    assert [item["quantities"][0]["raw_value"] for item in schedule] == ["12,350", "8,000"]
    assert "SAME_WORK_NAME_DIFFERENT_SCOPE" in schedule[1]["uncertainties"]
    assert schedule[1]["source_references"] == ["ВОР второй зоны.xlsx, версия 2, sheet:Зона B!C7"]


def test_tender_does_not_treat_contract_filename_as_clause_analysis() -> None:
    documents = [
        {
            **_documents()[0],
            "safe_display_name": "Проект договора строительного подряда.docx",
            "relative_path": "Исходные данные/Проект договора строительного подряда.docx",
        }
    ]
    result = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.TENDER,
        project=_project(),
        documents=documents,
        support={},
    )

    contract_item = next(
        item for item in result["items"] if item["kind"] == "contract_analysis_pending"
    )
    assert "ещё не извлечены" in contract_item["title"]
    assert "не подтверждает проверку условий" in contract_item["description"]


def test_mode_results_are_professionally_distinct() -> None:
    support = {
        "requirements": [
            {
                "document_requirement_id": "8ef68795-a17b-4814-97d8-7629714c9700",
                "document_type": "support.aosr",
                "requirement_state": "required",
                "basis_refs": ["project:RD-01"],
                "blockers": [],
            }
        ],
        "memberships": [
            {
                "membership_id": "7305f82e-8834-46ae-96a8-6831959730c3",
                "role": "executive_scheme",
                "blocker_codes": ["CONFIRMED_GEOMETRY_MISSING"],
            }
        ],
        "readiness": {"required_count": 4, "finalized_count": 1},
    }
    values = {
        mode: build_pilot_result(
            workspace_id=WORKSPACE_ID,
            workspace_name="Пилотный объект",
            mode=mode,
            project=_project(),
            documents=_documents(),
            support=support,
        )
        for mode in PilotMode
    }

    assert values[PilotMode.TENDER]["items"][0]["title"].startswith("Расхождение")
    assert values[PilotMode.SUPPORT]["items"][0]["title"].startswith("Акт")
    assert any(
        item["status"] == "cannot_prepare" for item in values[PilotMode.RESTORATION]["items"]
    )
    assert len({value["fingerprint"] for value in values.values()}) == 4


def test_audit_does_not_treat_completed_extraction_as_a_conformance_result() -> None:
    result = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.AUDIT,
        project=_project(),
        documents=_documents(),
        support={},
    )

    document_item = next(item for item in result["items"] if item["kind"] == "audit-input")
    assert document_item["status"] == "requires_clarification"
    assert "доступно как вход для аудита" in document_item["description"]
    assert "не выполнены" in document_item["description"]


def test_docx_and_pdf_exports_are_reproducible_and_readable() -> None:
    result = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.AUDIT,
        project=_project(),
        documents=_documents(),
        support={},
    )
    docx = render_export(
        result=result,
        kind=PilotExportKind.AUDIT_REPORT,
        output_format=PilotExportFormat.DOCX,
    )
    pdf = render_export(
        result=result,
        kind=PilotExportKind.AUDIT_REPORT,
        output_format=PilotExportFormat.PDF,
    )

    assert docx == render_export(
        result=result,
        kind=PilotExportKind.AUDIT_REPORT,
        output_format=PilotExportFormat.DOCX,
    )
    assert pdf == render_export(
        result=result,
        kind=PilotExportKind.AUDIT_REPORT,
        output_format=PilotExportFormat.PDF,
    )
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        document_xml = archive.read("word/document.xml").decode()
        assert "Отчёт аудита строительной документации" in document_xml
        assert "Учебно-производственный корпус" not in document_xml
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 1
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Пилотный объект" in text
    assert "Отчёт аудита" in text


def test_zip_exports_do_not_depend_on_prior_export_projection() -> None:
    result = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.SUPPORT,
        project=_project(),
        documents=_documents(),
        support={},
    )
    first_package = render_export(
        result=result,
        kind=PilotExportKind.ID_PACKAGE,
        output_format=PilotExportFormat.ZIP,
    )
    first_workspace = render_workspace_archive(results=[result])

    result["exports"] = [
        {
            "export_id": "bf56e2e7-5be8-58c6-ac8c-772af057677c",
            "version": 7,
            "export_kind": "workspace_results",
            "content_digest": "sha256:" + "9" * 64,
        }
    ]

    assert first_package == render_export(
        result=result,
        kind=PilotExportKind.ID_PACKAGE,
        output_format=PilotExportFormat.ZIP,
    )
    assert first_workspace == render_workspace_archive(results=[result])
    with zipfile.ZipFile(io.BytesIO(first_workspace)) as archive:
        assert b'"exports"' not in archive.read("support/result.json")


def test_user_excluded_item_is_not_emitted_as_an_exported_finding() -> None:
    result = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.TENDER,
        project=_project(),
        documents=_documents(),
        support={},
    )
    result["items"][0]["effective_resolution_status"] = "excluded"
    docx = render_export(
        result=result,
        kind=PilotExportKind.DISAGREEMENT_PROTOCOL,
        output_format=PilotExportFormat.DOCX,
    )
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        document_xml = archive.read("word/document.xml").decode()
    assert "Расхождение объёма между ВОР и сметой" not in document_xml


def test_tender_report_keeps_readable_source_reference_for_each_finding() -> None:
    project = _project()
    project["evidence_index"] = {
        "f8d343e5-d518-46d0-8d0b-b5a85aa5643e": {
            "safe_display_name": "ВОР.xlsx",
            "document_version": 2,
            "locator_value": "sheet:Сводная!B17",
        }
    }
    result = build_pilot_result(
        workspace_id=WORKSPACE_ID,
        workspace_name="Пилотный объект",
        mode=PilotMode.TENDER,
        project=project,
        documents=_documents(),
        support={},
    )
    docx = render_export(
        result=result,
        kind=PilotExportKind.DISAGREEMENT_PROTOCOL,
        output_format=PilotExportFormat.DOCX,
    )

    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        document_xml = archive.read("word/document.xml").decode()
    assert "ВОР.xlsx, версия 2, sheet:Сводная!B17" in document_xml
