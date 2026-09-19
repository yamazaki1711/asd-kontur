from __future__ import annotations

from uuid import UUID

import pytest

from asd_kontur.pilot.models import PilotExportFormat, PilotExportKind, PilotMode
from asd_kontur.pilot.postgres import PilotResultError
from asd_kontur.pilot.service import PilotResultService


@pytest.mark.parametrize(
    ("input_kind", "export_kind", "error_code"),
    (
        (
            "contract_input_unavailable",
            PilotExportKind.DISAGREEMENT_PROTOCOL,
            "pilot_contract_input_required",
        ),
        (
            "contract_analysis_pending",
            PilotExportKind.CONTRACT_CHANGES,
            "pilot_contract_analysis_required",
        ),
    ),
)
def test_tender_contract_drafts_require_actual_contract_analysis(
    input_kind: str, export_kind: PilotExportKind, error_code: str
) -> None:
    workspace_id = UUID("d0100000-0000-4000-8000-000000000001")

    expected_workspace_id = workspace_id

    class Spine:
        @staticmethod
        def resolve_scope(owner_identity_id: str, workspace_id: object) -> str:
            assert owner_identity_id == "owner-1"
            assert workspace_id == expected_workspace_id
            return "organization-1"

    class Repository:
        @staticmethod
        def latest_result(**_: object) -> dict[str, object]:
            return {"items": [{"kind": input_kind}]}

    service = object.__new__(PilotResultService)
    service._spine = Spine()
    service._repository = Repository()

    with pytest.raises(PilotResultError, match=error_code):
        service.create_export(
            owner_identity_id="owner-1",
            workspace_id=workspace_id,
            mode=PilotMode.TENDER,
            kind=export_kind,
            output_format=PilotExportFormat.DOCX,
        )


def test_tender_design_export_remains_available_without_contract_input() -> None:
    """The contract boundary must not block non-contractual Tender output."""

    from asd_kontur.pilot.service import _require_contract_analysis

    _require_contract_analysis(
        result={"items": [{"kind": "contract_input_unavailable"}]},
        mode=PilotMode.TENDER,
        kind=PilotExportKind.WORKSPACE_RESULTS,
    )
