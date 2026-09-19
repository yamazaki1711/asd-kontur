from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from io import StringIO
from typing import cast
from uuid import UUID

from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.services import ProductSpineService
from asd_kontur.support.generation import validate_docx
from asd_kontur.tender.analysis_package import build_tender_analysis_archive
from asd_kontur.tender.coverage_schedule import render_tender_document_coverage_csv
from asd_kontur.tender.facility_scope_schedule import render_tender_facility_scope_schedule_csv
from asd_kontur.tender.findings_report import render_tender_findings_docx
from asd_kontur.tender.findings_schedule import render_tender_findings_csv
from asd_kontur.tender.scope_schedule import render_tender_scope_schedule_csv
from asd_kontur.tender.structure_identity_schedule import (
    render_tender_structure_identity_schedule_csv,
)


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


def test_findings_expose_quantity_operands_and_units_without_calculating_a_total() -> None:
    defect = {
        "defect_id": "quantity-delta",
        "defect_kind": "quantity_mismatch",
        "subject_identity": "project-quantity",
        "related_identity": "estimate-position",
        "source_locator_ids": ["project-page", "estimate-page"],
        "parameters": {
            "project": "12.5",
            "estimate": "11",
            "unit": "m3",
            "difference": "1.5",
            "difference_method": "project_minus_estimate_exact_decimal",
        },
    }
    content = render_tender_findings_csv(
        (defect,), materialization_state="partial", coverage_gaps=()
    )
    row = next(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert row["comparison_details"] == (
        "Проект: 12.5 m3; смета: 11 m3; разница (проект минус смета): 1.5 m3"
    )

    report = render_tender_findings_docx(
        (defect,), materialization_state="partial", coverage_gaps=()
    )
    with zipfile.ZipFile(io.BytesIO(report)) as document:
        xml = document.read("word/document.xml").decode("utf-8")
    assert "Проект: 12.5 m3; смета: 11 m3; разница (проект минус смета): 1.5 m3" in xml


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


def test_scope_schedule_preserves_zero_quantity_observations() -> None:
    content = render_tender_scope_schedule_csv(
        (
            {
                "work_package_id": "package-zero",
                "package": {
                    "work_type": {"raw": "Demolition", "normalized": "demolition"},
                    "scope": "zone-a",
                    "candidate_observation_count": 1,
                    "quantities": [
                        {
                            "raw_value": 0,
                            "raw_unit": "m3",
                            "normalized_value": 0,
                            "normalized_unit": "m3",
                            "source_locator_id": "locator-quantity",
                        }
                    ],
                    "materials": [
                        {
                            "raw_name": "Concrete",
                            "raw_quantity": 0,
                            "raw_unit": "m3",
                            "source_locator_id": "locator-material",
                        }
                    ],
                    "source_locator_ids": ["locator-quantity", "locator-material"],
                },
            },
        ),
        materialization_state="partial",
        coverage_gaps=(),
    )

    row = next(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert row["quantity_observations"] == "0 m3; normalized=0 m3; locator=locator-quantity"
    assert row["material_observations"] == "Concrete; 0 m3; locator=locator-material"


def test_analysis_archive_keeps_editable_outputs_and_partial_coverage_boundary() -> None:
    archive = build_tender_analysis_archive(
        findings_report=b"docx-payload",
        findings_schedule=b"findings-csv",
        scope_schedule=b"scope-csv",
        structure_identity_schedule=b"identity-csv",
        document_coverage_schedule=b"coverage-csv",
        materialization={"state": "partial", "gaps": ["SEMANTIC_COVERAGE_PARTIAL"]},
    )

    with zipfile.ZipFile(io.BytesIO(archive)) as exported:
        assert exported.namelist() == [
            "01_tender_findings_report.docx",
            "02_tender_findings_schedule.csv",
            "03_tender_work_resource_schedule.csv",
            "04_structure_identity_candidates.csv",
            "05_document_processing_coverage.csv",
            "06_delivery_manifest.json",
            "99_analysis_status.txt",
        ]
        assert exported.read("01_tender_findings_report.docx") == b"docx-payload"
        assert exported.read("04_structure_identity_candidates.csv") == b"identity-csv"
        assert exported.read("05_document_processing_coverage.csv") == b"coverage-csv"
        manifest = json.loads(exported.read("06_delivery_manifest.json"))
        status = exported.read("99_analysis_status.txt").decode("utf-8")
    assert "state: partial" in status
    assert "SEMANTIC_COVERAGE_PARTIAL" in status
    assert manifest["candidate_boundary"] is True
    assert (
        manifest["entries"][0]["sha256"] == "sha256:" + hashlib.sha256(b"docx-payload").hexdigest()
    )


def test_structure_identity_schedule_keeps_each_source_observation_unmerged() -> None:
    content = render_tender_structure_identity_schedule_csv(
        (
            {
                "identity_candidate_id": "identity-1",
                "identity_kind": "facility",
                "canonical_label": "Pump station 4",
                "status": "candidate",
                "confidence": "0.82",
                "member_structure_node_ids": ["node-a", "node-b"],
            },
        ),
        structure_nodes=(
            {
                "structure_node_id": "node-a",
                "node_kind": "facility",
                "raw_name": "Pump station-4",
                "source_locator_id": "locator-a",
            },
            {
                "structure_node_id": "node-b",
                "node_kind": "facility",
                "raw_name": "Pump station 4",
                "source_locator_id": "locator-b",
            },
        ),
        materialization_state="partial",
        coverage_gaps=("SEMANTIC_COVERAGE_PARTIAL",),
        evidence_index={
            "locator-a": {
                "safe_display_name": "General plan.pdf",
                "document_version": 1,
                "locator_value": "page:3",
            },
            "locator-b": {
                "safe_display_name": "Technology.pdf",
                "document_version": 2,
                "locator_value": "page:11",
            },
        },
    )
    rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert [row["member_raw_name"] for row in rows] == ["Pump station-4", "Pump station 4"]
    assert {row["automatic_merge"] for row in rows} == {"false"}
    assert {row["member_state"] for row in rows} == {"source_observation"}
    assert rows[0]["source_reference"] == "General plan.pdf, version 1, page:3 (locator-a)"


def test_facility_scope_schedule_requires_one_exact_shared_locator() -> None:
    work_packages = (
        {
            "work_package_id": "work-a",
            "package": {
                "work_package_id": "work-a",
                "work_type": {"raw": "Excavation", "normalized": "excavation"},
                "scope": "page:7",
                "source_locator_ids": ["locator-a"],
            },
        },
        {
            "work_package_id": "work-b",
            "package": {
                "work_package_id": "work-b",
                "work_type": {"raw": "Concrete", "normalized": "concrete"},
                "scope": "page:8",
                "source_locator_ids": ["locator-b", "locator-c"],
            },
        },
    )
    content = render_tender_facility_scope_schedule_csv(
        work_packages,
        identity_candidates=(
            {
                "identity_candidate_id": "facility-a",
                "canonical_label": "Facility A",
                "identity_kind": "facility",
                "confidence": "0.81",
                "source_locator_ids": ["locator-a"],
            },
            {
                "identity_candidate_id": "facility-b",
                "canonical_label": "Facility B",
                "identity_kind": "facility",
                "confidence": "0.74",
                "source_locator_ids": ["locator-b"],
            },
            {
                "identity_candidate_id": "facility-c",
                "canonical_label": "Facility C",
                "identity_kind": "facility",
                "confidence": "0.69",
                "source_locator_ids": ["locator-c"],
            },
        ),
        materialization_state="partial",
        coverage_gaps=("SEMANTIC_COVERAGE_PARTIAL",),
    )
    rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert rows[0]["association_state"] == "exact_locator_identity_candidate"
    assert rows[0]["identity_candidate_ids"] == "facility-a"
    assert rows[1]["association_state"] == "ambiguous_identity_candidates"
    assert rows[1]["identity_candidate_ids"] == "facility-b;facility-c"
    assert rows[1]["candidate_status"] == "candidate_no_canonical_work_package"


def test_document_coverage_keeps_native_and_semantic_statuses_distinct() -> None:
    content = render_tender_document_coverage_csv(
        (
            {
                "safe_display_name": "Site plan.pdf",
                "document_version": 2,
                "source_version_id": "source-a",
                "admission_status": "accepted",
                "extraction_status": "complete",
                "page_count": 12,
                "profile_version": "qwen-engineering-extraction-v16",
                "expected_fragment_count": 20,
                "accepted_batch_count": 3,
                "accepted_fragment_count": 16,
                "failed_batch_count": 1,
                "failed_fragment_count": 4,
                "recovered_failed_fragment_count": 0,
                "unresolved_failed_fragment_count": 4,
                "state": "partial",
            },
        ),
        materialization_state="partial",
        coverage_gaps=("SEMANTIC_COVERAGE_PARTIAL",),
    )

    row = next(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert row["native_extraction_status"] == "complete"
    assert row["semantic_coverage_state"] == "partial"
    assert row["unresolved_failed_fragment_count"] == "4"
    assert row["project_coverage_gaps"] == "SEMANTIC_COVERAGE_PARTIAL"


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
