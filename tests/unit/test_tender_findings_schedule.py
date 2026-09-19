from __future__ import annotations

import csv
from io import StringIO
from typing import cast
from uuid import UUID

from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.services import ProductSpineService
from asd_kontur.tender.findings_schedule import render_tender_findings_csv


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
    )

    rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert len(rows) == 1
    row = rows[0]
    assert row["finding_id"] == "finding-1"
    assert row["assessment_state"] == "comparison_not_performed"
    assert row["source_locator_ids"] == "locator-1"
    assert row["materialization_state"] == "partial"
    assert row["coverage_gaps"] == "SEMANTIC_COVERAGE_PARTIAL"
    assert row["required_input"] == "parsed_estimate_or_bill_of_quantities_positions"


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
            }

    service = object.__new__(ProductSpineService)
    service._repository = cast(SpinePostgresRepository, Repository())
    result = service.tender_findings_schedule(
        owner_identity_id="owner-1", workspace_id=expected_workspace_id
    )

    assert result.safe_display_name == f"tender-findings-{expected_workspace_id}.csv"
    assert result.media_type == "text/csv; charset=utf-8"
    assert b"coverage_gaps" in b"".join(result.chunks)
