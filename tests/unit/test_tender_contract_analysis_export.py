from __future__ import annotations

import csv
import io
import zipfile

from asd_kontur.tender.contract_analysis_export import render_tender_contract_analysis_csv
from asd_kontur.tender.contract_analysis_report import render_tender_contract_analysis_docx


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


def test_contract_analysis_word_report_is_editable_and_preserves_exact_source() -> None:
    view = {
        "status": "drafted",
        "process": {
            "tender_process_id": "process-independent-72",
            "revision": 6,
            "state": "drafted",
        },
        "clauses": [
            {
                "clause_id": "clause-independent-7",
                "clause_version": 2,
                "clause_key": "payment.acceptance",
                "source_version_id": "source-independent-91",
                "source_locator_id": "locator-independent-311",
                "evidence_link_id": "evidence-independent-808",
                "authority_layer": "contract",
            }
        ],
        "issues": [
            {
                "issue_id": "issue-independent-11",
                "issue_kind": "contract_risk",
                "subject": "Acceptance deadline",
                "applicability": "applicable",
                "recommendation_text": "Define one evidence-backed acceptance period.",
                "consequence_code": "payment_delay",
            }
        ],
        "disagreement_items": [
            {
                "item_id": "item-independent-4",
                "clause_id": "clause-independent-7",
                "clause_version": 2,
                "proposed_clause_text": "Accept within seven working days.",
                "consequence_code": "payment_delay",
                "uncertainty_issue_ids": ["issue-independent-11"],
            }
        ],
        "revised_clauses": [
            {
                "disagreement_item_id": "item-independent-4",
                "revised_text": "Accept completed work within seven working days.",
            }
        ],
        "deliverables": [
            {
                "deliverable_kind": "revised_contract",
                "state": "drafted",
                "blocker_issue_ids": [],
                "uncertainty_issue_ids": ["issue-independent-11"],
            }
        ],
        "gaps": ["PROFESSIONAL_REVIEW_REQUIRED"],
    }

    content = render_tender_contract_analysis_docx(view)

    with zipfile.ZipFile(io.BytesIO(content)) as package:
        assert "word/document.xml" in package.namelist()
        document = package.read("word/document.xml").decode("utf-8")
        assert "Accept completed work within seven working days." in document
        assert "source-independent-91" in document
        assert "locator-independent-311" in document
        assert "evidence-independent-808" in document
        assert "PROFESSIONAL_REVIEW_REQUIRED" in document
        assert "не заменяет юридическое заключение" in document
