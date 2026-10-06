# ruff: noqa: RUF001 -- Russian product document assertions are intentional.
from __future__ import annotations

import csv
import io
import zipfile

from asd_kontur.application_spine.services import _contract_cross_check_coverage
from asd_kontur.tender.contract_analysis_export import render_tender_contract_analysis_csv
from asd_kontur.tender.contract_analysis_report import (
    render_tender_contract_analysis_docx,
    render_tender_disagreement_protocol_docx,
)


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


def test_contract_report_explains_role_reclassification_in_product_language() -> None:
    content = render_tender_contract_analysis_docx(
        {
            "status": "analysis_pending",
            "clauses": [],
            "issues": [],
            "disagreement_items": [],
            "revised_clauses": [],
            "deliverables": [],
            "gaps": ["CONTRACT_SOURCE_RECLASSIFICATION_PENDING"],
        }
    )

    with zipfile.ZipFile(io.BytesIO(content)) as package:
        report_xml = package.read("word/document.xml").decode("utf-8")

    assert "назначение ранее найденного проекта договора уточняется повторно" in report_xml
    assert "CONTRACT_SOURCE_RECLASSIFICATION_PENDING" not in report_xml


def test_contract_only_input_declares_unperformed_project_cross_checks() -> None:
    checks = _contract_cross_check_coverage(
        {"documents": [{"document_role": "Договор"}]}
    )
    assert {item["status"] for item in checks} == {"input_not_established"}
    content = render_tender_contract_analysis_docx(
        {
            "status": "drafted",
            "clauses": [],
            "issues": [],
            "disagreement_items": [],
            "revised_clauses": [],
            "deliverables": [],
            "gaps": [],
            "project_context": {"cross_checks": checks},
        }
    )
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        report_xml = package.read("word/document.xml").decode("utf-8")
    assert "проектный объём ПД/РД" in report_xml
    assert "объёмы ВОР/сметы" in report_xml
    assert "календарный график" in report_xml
    assert "Это не означает отсутствия противоречий" in report_xml


def test_contract_cross_checks_use_roles_not_source_names() -> None:
    checks = _contract_cross_check_coverage(
        {
            "documents": [
                {"name": "alpha.bin", "document_role": "РД"},
                {"name": "beta.bin", "document_role": "Смета"},
            ]
        }
    )
    assert checks == [
        {"check": "design_scope", "status": "input_available"},
        {"check": "commercial_scope", "status": "input_available"},
        {"check": "schedule", "status": "input_not_established"},
    ]


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
                "source_name": "Changed-contract-terms.docx",
                "source_page": 12,
                "source_version_id": "source-independent-91",
                "source_locator_id": "locator-independent-311",
                "evidence_link_id": "evidence-independent-808",
                "authority_layer": "contract",
            }
        ],
        "issues": [
            {
                "issue_id": "issue-independent-11",
                "issue_version": 1,
                "issue_kind": "contract_risk",
                "subject": "Acceptance deadline",
                "description": "Acceptance depends on an undefined Customer review period.",
                "trigger_text": "Customer accepts work after its internal review.",
                "adverse_effect_text": "Payment is due only after Customer acceptance.",
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
                "issue_id": "issue-independent-11",
                "issue_version": 1,
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
        "project_context": {
            "participants": [
                {
                    "label": "Заказчик",
                    "value": "ООО «Северный заказчик»",
                    "sources": [{"document": "Changed-contract-terms.docx", "page": 1}],
                }
            ],
            "time_requirements": [
                {
                    "label": "Срок выполнения работ",
                    "value": "5 месяцев",
                    "sources": [{"document": "Условия закупки.pdf", "page": 4}],
                }
            ],
            "project_contract_findings": [
                {
                    "kind": "Расхождение продолжительности",
                    "subject": "Срок выполнения работ",
                    "description": "ПОС: 3 месяца; закупка: 5 месяцев.",
                    "practical_consequence": "Требуется согласовать календарный график.",
                    "recommended_action": "Подтвердить обязательный срок.",
                    "sources": [{"document": "ПОС.pdf", "page": 18}],
                }
            ],
        },
        "gaps": ["PROFESSIONAL_REVIEW_REQUIRED"],
    }

    content = render_tender_contract_analysis_docx(view)

    csv_rows = list(
        csv.DictReader(io.StringIO(render_tender_contract_analysis_csv(view).decode("utf-8-sig")))
    )
    issue_row = next(row for row in csv_rows if row["row_kind"] == "issue")
    assert issue_row["trigger_text"] == "Customer accepts work after its internal review."
    assert issue_row["adverse_effect_text"] == ("Payment is due only after Customer acceptance.")

    with zipfile.ZipFile(io.BytesIO(content)) as package:
        assert "word/document.xml" in package.namelist()
        document = package.read("word/document.xml").decode("utf-8")
        relationships = package.read("word/_rels/document.xml.rels").decode("utf-8")
        assert "http://schemas.openxmlformats.org/package/2006/relationships" in relationships
        assert "<w:tblPr>" in document
        assert "<w:tblGrid>" in document
        assert "Договорный анализ и предложения Подрядчика" in document
        assert '<w:sz w:val="16"/>' in document
        assert 'w:header="720"' in document
        assert 'w:footer="720"' in document
        assert 'w:gutter="0"' in document
        assert "Accept completed work within seven working days." in document
        assert "Changed-contract-terms.docx" in document
        assert "стр./лист: 12" in document
        assert "ООО «Северный заказчик»" in document
        assert "source-independent-91" not in document
        assert "locator-independent-311" not in document
        assert "evidence-independent-808" not in document
        assert "qwen_contract_candidate" not in document
        assert "требуется профессиональная юридическая проверка" in document
        assert "не является подписанным соглашением сторон" in document
        assert "Обоснование / практическая причина" in document
        assert "Acceptance depends on an undefined Customer review period." in document
        assert "Customer accepts work after its internal review." in document
        assert "Payment is due only after Customer acceptance." in document
        assert "Define one evidence-backed acceptance period." in document
        assert "Ключевые условия договора и закупки" in document
        assert "5 месяцев" in document
        assert "Связь договора с проектом" in document
        assert "ПОС: 3 месяца; закупка: 5 месяцев." in document

    protocol = render_tender_disagreement_protocol_docx(view)
    with zipfile.ZipFile(io.BytesIO(protocol)) as package:
        document = package.read("word/document.xml").decode("utf-8")
        assert "ПРОТОКОЛ РАЗНОГЛАСИЙ" in document
        assert "Accept completed work within seven working days." in document
        assert "Acceptance depends on an undefined Customer review period." in document
        assert "Changed-contract-terms.docx" in document
        assert "стр./лист: 12" in document
        assert "source-independent-91" not in document
        assert "locator-independent-311" not in document
        assert "evidence-independent-808" not in document
        assert "ООО «Северный заказчик»" in document
        assert "Объект и стороны" in document
