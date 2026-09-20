from __future__ import annotations

import csv
import io

from asd_kontur.tender.contract_analysis_export import render_tender_contract_analysis_csv


def test_contract_analysis_export_preserves_lineage_and_neutralizes_formulas() -> None:
    view = {
        "status": "drafted",
        "process": {
            "tender_process_id": "process-other-project",
            "revision": 4,
            "state": "drafted",
        },
        "assessment": {"status": "complete", "missing_source_classes": []},
        "clauses": [
            {
                "clause_id": "clause-41",
                "clause_version": 3,
                "clause_key": "payment.retention",
                "source_version_id": "source-17",
                "source_locator_id": "locator-page-89",
                "evidence_link_id": "evidence-301",
                "authority_layer": "contract",
            }
        ],
        "issues": [],
        "protocols": [],
        "disagreement_items": [
            {
                "protocol_version": 2,
                "item_id": "item-12",
                "clause_id": "clause-41",
                "clause_version": 3,
                "proposed_clause_text": "=unsafe spreadsheet expression",
                "consequence_code": "payment_delay",
                "evidence_link_ids": ["evidence-301"],
                "uncertainty_issue_ids": [],
            }
        ],
        "revised_contracts": [],
        "revised_clauses": [
            {
                "revised_contract_version": 2,
                "revised_clause_id": "revised-12",
                "source_clause_id": "clause-41",
                "source_clause_version": 3,
                "revised_text": "Pay retained amount within ten working days.",
            }
        ],
        "deliverables": [],
        "gaps": [],
        "authority_boundary": "read_only_projection",
    }

    rows = list(
        csv.DictReader(io.StringIO(render_tender_contract_analysis_csv(view).decode("utf-8-sig")))
    )
    disagreement = next(row for row in rows if row["row_kind"] == "disagreement_item")
    revised = next(row for row in rows if row["row_kind"] == "revised_clause")

    assert disagreement["source_version_id"] == "source-17"
    assert disagreement["source_locator_id"] == "locator-page-89"
    assert disagreement["evidence_link_ids"] == "evidence-301"
    assert disagreement["proposed_clause_text"] == "'=unsafe spreadsheet expression"
    assert revised["clause_key"] == "payment.retention"
    assert revised["revised_clause_text"] == "Pay retained amount within ten working days."
