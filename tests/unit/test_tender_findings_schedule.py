from __future__ import annotations

import csv
import io
import zipfile
from io import StringIO
from typing import cast
from uuid import UUID

from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.services import ProductSpineService
from asd_kontur.support.generation import validate_docx
from asd_kontur.tender.analysis_package import build_tender_analysis_archive
from asd_kontur.tender.findings_report import render_tender_findings_docx
from asd_kontur.tender.findings_schedule import render_tender_findings_csv
from asd_kontur.tender.scope_schedule import render_tender_scope_schedule_csv


def test_schedule_marks_missing_estimate_input_without_claiming_omission() -> None:
    content = render_tender_findings_csv(
        (
            {
                "defect_id": "finding-1",
                "defect_kind": "estimate_comparison_input_unavailable",
                "subject_identity": "project_estimate_comparison",
                "related_identity": None,
                "source_locator_ids": ["locator-1"],
                "parameters": {
                    "missing_input": "parsed_estimate_or_bill_of_quantities_positions",
                    "consequence": "project_work_omissions_and_quantity_deltas_not_evaluated",
                },
            },
        ),
        materialization_state="partial",
        coverage_gaps=("SEMANTIC_COVERAGE_PARTIAL",),
        evidence_index={
            "locator-1": {
                "safe_display_name": "Structural plan.pdf",
                "document_version": 3,
                "locator_value": "page:17",
            }
        },
    )

    rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert len(rows) == 1
    row = rows[0]
    assert row["finding_id"] == "finding-1"
    assert row["assessment_state"] == "comparison_not_performed"
    assert row["source_locator_ids"] == "locator-1"
    assert row["source_references"] == "Structural plan.pdf, version 3, page:17 (locator-1)"
    assert row["materialization_state"] == "partial"
    assert row["coverage_gaps"] == "SEMANTIC_COVERAGE_PARTIAL"
    assert row["required_input"] == "parsed_estimate_or_bill_of_quantities_positions"


def test_exports_resolve_work_context_only_by_exact_observation_membership() -> None:
    work_packages = (
        {
            "work_package_id": "package-a",
            "package": {
                "work_package_id": "package-a",
                "work_type": {"raw": "Монтаж лотков", "normalized": "монтаж лотков"},
                "scope": "zone-a",
                "candidate_observation_ids": ["work-a"],
            },
        },
        {
            "work_package_id": "package-b",
            "package": {
                "work_package_id": "package-b",
                "work_type": {"raw": "Монтаж лотков", "normalized": "монтаж лотков"},
                "scope": "zone-b",
                "candidate_observation_ids": ["work-b"],
            },
        },
    )
    defect = {
        "defect_id": "finding-scope-a",
        "defect_kind": "project_work_missing_in_estimate",
        "subject_identity": "work-a",
        "related_identity": None,
        "source_locator_ids": [],
        "parameters": {},
    }

    csv_payload = render_tender_findings_csv(
        (defect,),
        materialization_state="partial",
        coverage_gaps=(),
        work_packages=work_packages,
    )
    row = next(csv.DictReader(StringIO(csv_payload.decode("utf-8-sig"))))
    assert row["work_package_id"] == "package-a"
    assert row["work_name"] == "Монтаж лотков"
    assert row["scope"] == "zone-a"
    assert row["work_relation"] == "subject"

    report = render_tender_findings_docx(
        (defect,),
        materialization_state="partial",
        coverage_gaps=(),
        work_packages=work_packages,
    )
    with zipfile.ZipFile(io.BytesIO(report)) as document:
        xml = document.read("word/document.xml").decode("utf-8")
    assert "Монтаж лотков; область: zone-a" in xml
    assert "zone-b" not in xml


def test_scope_schedule_keeps_identical_work_names_in_distinct_scopes() -> None:
    content = render_tender_scope_schedule_csv(
        (
            {
                "work_package_id": "package-a",
                "package": {
                    "work_type": {"raw": "Монтаж лотков", "normalized": "монтаж лотков"},
                    "scope": "zone-a",
                    "candidate_observation_count": 1,
                    "quantities": [
                        {
                            "raw_value": "12",
                            "raw_unit": "м",
                            "normalized_value": "12",
                            "normalized_unit": "m",
                            "source_locator_id": "locator-a",
                        }
                    ],
                    "materials": [],
                    "source_locator_ids": ["locator-a"],
                    "uncertainties": ["SAME_WORK_NAME_DIFFERENT_SCOPE"],
                },
            },
            {
                "work_package_id": "package-b",
                "package": {
                    "work_type": {"raw": "Монтаж лотков", "normalized": "монтаж лотков"},
                    "scope": "zone-b",
                    "candidate_observation_count": 1,
                    "quantities": [],
                    "materials": [
                        {
                            "raw_name": "Лоток Л1",
                            "raw_quantity": "3",
                            "raw_unit": "шт",
                            "source_locator_id": "locator-b",
                        }
                    ],
                    "source_locator_ids": ["locator-b"],
                    "uncertainties": ["SAME_WORK_NAME_DIFFERENT_SCOPE"],
                },
            },
        ),
        materialization_state="partial",
        coverage_gaps=("SEMANTIC_COVERAGE_PARTIAL",),
        evidence_index={
            "locator-a": {
                "safe_display_name": "Plan A.pdf",
                "document_version": 1,
                "locator_value": "page:2",
            },
            "locator-b": {
                "safe_display_name": "Plan B.pdf",
                "document_version": 1,
                "locator_value": "page:4",
            },
        },
    )

    rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert [(row["work_package_id"], row["scope"]) for row in rows] == [
        ("package-a", "zone-a"),
        ("package-b", "zone-b"),
    ]
    assert rows[0]["quantity_observations"] == "12 м; normalized=12 m; locator=locator-a"
    assert rows[1]["material_observations"] == "Лоток Л1; 3 шт; locator=locator-b"
    assert rows[0]["source_references"] == "Plan A.pdf, version 1, page:2 (locator-a)"


def test_analysis_archive_keeps_editable_outputs_and_partial_coverage_boundary() -> None:
    archive = build_tender_analysis_archive(
        findings_report=b"docx-payload",
        findings_schedule=b"findings-csv",
        scope_schedule=b"scope-csv",
        materialization={"state": "partial", "gaps": ["SEMANTIC_COVERAGE_PARTIAL"]},
    )

    with zipfile.ZipFile(io.BytesIO(archive)) as exported:
        assert exported.namelist() == [
            "01_tender_findings_report.docx",
            "02_tender_findings_schedule.csv",
            "03_tender_work_resource_schedule.csv",
            "99_analysis_status.txt",
        ]
        assert exported.read("01_tender_findings_report.docx") == b"docx-payload"
        status = exported.read("99_analysis_status.txt").decode("utf-8")
    assert "state: partial" in status
    assert "SEMANTIC_COVERAGE_PARTIAL" in status


def test_application_service_returns_editable_schedule_from_scoped_project_view() -> None:
    expected_workspace_id = UUID("10000000-0000-4000-8000-000000000001")

    class Repository:
        def project_understanding_view(
            self, *, owner_identity_id: str, workspace_id: UUID
        ) -> dict[str, object]:
            assert owner_identity_id == "owner-1"
            assert workspace_id == expected_workspace_id
            return {
                "materialization": {"state": "partial", "gaps": ["SEMANTIC_COVERAGE_PARTIAL"]},
                "defects": [],
                "evidence_index": {},
            }

    service = object.__new__(ProductSpineService)
    service._repository = cast(SpinePostgresRepository, Repository())
    result = service.tender_findings_schedule(
        owner_identity_id="owner-1", workspace_id=expected_workspace_id
    )

    assert result.safe_display_name == f"tender-findings-{expected_workspace_id}.csv"
    assert result.media_type == "text/csv; charset=utf-8"
    assert b"coverage_gaps" in b"".join(result.chunks)


def test_report_preserves_candidate_boundary_and_source_references() -> None:
    content = render_tender_findings_docx(
        (
            {
                "defect_id": "finding-1",
                "defect_kind": "estimate_comparison_input_unavailable",
                "subject_identity": "project_estimate_comparison",
                "source_locator_ids": ["locator-1"],
                "parameters": {"missing_input": "estimate positions"},
            },
        ),
        materialization_state="partial",
        coverage_gaps=("SEMANTIC_COVERAGE_PARTIAL",),
        evidence_index={
            "locator-1": {
                "safe_display_name": "Structural plan.pdf",
                "document_version": 3,
                "locator_value": "page:17",
            }
        },
    )

    validation = validate_docx(content, required_fields=())
    assert validation.valid
    with zipfile.ZipFile(io.BytesIO(content)) as document:
        xml = document.read("word/document.xml").decode("utf-8")
    assert "Предварительный Tender-отчёт" in xml
    assert "Structural plan.pdf, version 3, page:17 (locator-1)" in xml
    assert "estimate positions" in xml
