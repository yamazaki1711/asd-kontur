# ruff: noqa: RUF001 -- Russian product document assertions are intentional.
from __future__ import annotations

import csv
import io
import zipfile

from asd_kontur.application_spine.services import _contract_cross_check_coverage
from asd_kontur.tender.clause_reference import (
    display_clause_reference,
    display_protocol_clause_reference,
)
from asd_kontur.tender.contract_analysis_export import render_tender_contract_analysis_csv
from asd_kontur.tender.contract_analysis_report import (
    render_tender_contract_analysis_docx,
    render_tender_disagreement_protocol_docx,
)


def test_contract_report_uses_only_source_supported_clause_references() -> None:
    assert (
        display_clause_reference(
            {"source_text": "4.7. Оплата производится", "clause_key": "clause_3"}
        )
        == "4.7"
    )
    assert (
        display_clause_reference({"source_text": "Оплата производится", "clause_key": "п. 8.2"})
        == "Пункт без номера — см. источник"
    )
    assert (
        display_clause_reference(
            {"source_text": "Выезд на объект", "clause_key": "clause_3", "source_page": 12}
        )
        == "Пункт без номера (стр./лист 12)"
    )
    assert (
        display_clause_reference({"source_text": "Выезд на объект", "clause_key": "batch-1"})
        == "Пункт без номера — см. источник"
    )
    assert (
        display_clause_reference(
            {
                "source_text": "Выезд на объект",
                "clause_key": "payment.acceptance",
                "locator_label": "6.4",
            }
        )
        == "Пункт без номера — см. источник"
    )


def test_protocol_identifies_unnumbered_source_without_inventing_a_clause_number() -> None:
    unnumbered = {
        "source_text": "Передача строительной площадки оформляется актом.",
        "source_name": "Условия выполнения работ.docx",
        "source_page": 4,
        "clause_key": "model-generated-7.9",
    }
    assert display_protocol_clause_reference(unnumbered) == (
        "Условия выполнения работ.docx: Пункт без номера (стр./лист 4)"
    )
    assert display_protocol_clause_reference(
        {"source_text": "8.3. Оплата после приёмки", "source_name": "Договор.docx"}
    ) == "Договор.docx: 8.3"
    assert display_protocol_clause_reference({"source_text": "Условие без номера"}) == (
        "Пункт без номера — см. источник"
    )


def test_protocol_word_table_names_the_unnumbered_attachment() -> None:
    view = {
        "assessment": {"source_names": ["Условия выполнения работ.docx"]},
        "clauses": [
            {
                "clause_id": "clause-a",
                "clause_version": 1,
                "source_text": "Передача площадки оформляется актом.",
                "source_name": "Условия выполнения работ.docx",
                "source_page": 4,
            }
        ],
        "disagreement_items": [
            {"item_id": "item-a", "clause_id": "clause-a", "clause_version": 1}
        ],
        "revised_clauses": [
            {"disagreement_item_id": "item-a", "revised_text": "Передача оформляется актом сторон."}
        ],
    }
    payload = render_tender_disagreement_protocol_docx(view)
    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        xml = document.read("word/document.xml").decode("utf-8")
    assert "Пункт договора / документа" in xml
    assert "Условия выполнения работ.docx: Пункт без номера (стр./лист 4)" in xml
    assert "Передача оформляется актом сторон." in xml


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


def test_contract_report_explains_multi_source_revision_limit() -> None:
    content = render_tender_contract_analysis_docx(
        {
            "status": "drafted",
            "clauses": [],
            "issues": [],
            "disagreement_items": [],
            "revised_clauses": [],
            "deliverables": [],
            "gaps": ["REVISED_CONTRACT_EXCLUDES_NON_PRIMARY_SOURCE_REVISIONS"],
        }
    )
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        report_xml = package.read("word/document.xml").decode("utf-8")
    assert "предложения относятся к нескольким договорным файлам" in report_xml
    assert "REVISED_CONTRACT_EXCLUDES_NON_PRIMARY_SOURCE_REVISIONS" not in report_xml


def test_contract_reference_is_visible_in_editable_outputs_without_false_absence_claim() -> None:
    view = {
        "status": "drafted",
        "clauses": [],
        "issues": [],
        "disagreement_items": [],
        "revised_clauses": [],
        "deliverables": [],
        "gaps": ["CONTRACT_REFERENCED_DOCUMENT_UNRESOLVED"],
        "attachment_references": [
            {
                "reference_id": "reference-1",
                "source_quote": "Annex C",
                "target_description": "delivery timetable",
                "kind": "schedule",
                "match_decision": "unresolved",
                "source_version_id": "source-a",
                "source_locator_id": "locator-a",
                "source_name": "Draft agreement.docx",
                "source_page": 7,
            }
        ],
    }
    with zipfile.ZipFile(io.BytesIO(render_tender_contract_analysis_docx(view))) as package:
        report_xml = package.read("word/document.xml").decode("utf-8")
    assert "Annex C" in report_xml
    assert "Связь с загруженным документом не установлена" in report_xml
    assert "не доказывает отсутствие приложения" in report_xml
    assert "CONTRACT_REFERENCED_DOCUMENT_UNRESOLVED" not in report_xml
    rows = list(
        csv.DictReader(io.StringIO(render_tender_contract_analysis_csv(view).decode("utf-8-sig")))
    )
    reference = next(row for row in rows if row["row_kind"] == "contract_reference")
    assert reference["source_locator_id"] == "locator-a"
    assert reference["state"] == "unresolved"


def test_partial_contract_package_evidence_remains_a_clarification() -> None:
    view = {
        "status": "drafted",
        "clauses": [],
        "issues": [],
        "disagreement_items": [],
        "revised_clauses": [],
        "deliverables": [],
        "gaps": ["CONTRACT_REFERENCED_DOCUMENT_UNRESOLVED"],
        "attachment_references": [
            {
                "reference_id": "reference-package",
                "source_quote": "project documentation package",
                "target_description": "design package",
                "kind": "drawing",
                "match_decision": "partially_matched",
                "matched_source_names": ["Foundation drawings", "Road drawings"],
                "uncertainty": "Package completeness is unverified.",
                "source_version_id": "source-contract",
                "source_locator_id": "contract-locator",
                "source_name": "Construction contract.docx",
            }
        ],
    }
    with zipfile.ZipFile(io.BytesIO(render_tender_contract_analysis_docx(view))) as package:
        report_xml = package.read("word/document.xml").decode("utf-8")
    assert "Частично представлен" in report_xml
    assert "Foundation drawings" in report_xml
    assert "полнота требует уточнения" in report_xml
    rows = list(
        csv.DictReader(io.StringIO(render_tender_contract_analysis_csv(view).decode("utf-8-sig")))
    )
    reference = next(row for row in rows if row["row_kind"] == "contract_reference")
    assert reference["state"] == "partially_matched"
    assert reference["recommendation"]


def test_contract_only_input_declares_unperformed_project_cross_checks() -> None:
    checks = _contract_cross_check_coverage({"documents": [{"document_role": "Договор"}]})
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
    rows = list(
        csv.DictReader(
            io.StringIO(
                render_tender_contract_analysis_csv(
                    {
                        "status": "drafted",
                        "project_context": {"cross_checks": checks},
                    }
                ).decode("utf-8-sig")
            )
        )
    )
    assert [row["item_kind"] for row in rows if row["row_kind"] == "project_cross_check_input"] == [
        "design_scope",
        "commercial_scope",
        "schedule",
    ]
    assert {row["state"] for row in rows if row["row_kind"] == "project_cross_check_input"} == {
        "input_not_established"
    }


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
        {"check": "design_scope", "status": "source_role_present"},
        {"check": "commercial_scope", "status": "source_role_present"},
        {"check": "schedule", "status": "input_not_established"},
    ]


def test_source_roles_without_published_findings_do_not_claim_clean_comparison() -> None:
    checks = _contract_cross_check_coverage(
        {
            "documents": [
                {"document_role": "РД"},
                {"document_role": "Смета"},
                {"document_role": "Календарный график"},
            ]
        }
    )
    assert {item["status"] for item in checks} == {"source_role_present"}
    content = render_tender_contract_analysis_docx(
        {
            "status": "drafted",
            "clauses": [],
            "issues": [],
            "disagreement_items": [],
            "revised_clauses": [],
            "deliverables": [],
            "gaps": [],
            "project_context": {"cross_checks": checks, "project_contract_findings": []},
        }
    )
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        report_xml = package.read("word/document.xml").decode("utf-8")
    assert "полнота сопоставления не подтверждена" in report_xml


def test_partial_contract_source_coverage_is_visible_in_editable_outputs() -> None:
    view = {
        "status": "drafted",
        "assessment": {
            "status": "partial",
            "source_coverage": {
                "total_sources": 2,
                "complete_sources": 1,
                "incomplete_source_names": ["Attachment Q"],
            },
        },
        "project_context": {},
    }
    with zipfile.ZipFile(io.BytesIO(render_tender_contract_analysis_docx(view))) as package:
        report_xml = package.read("word/document.xml").decode("utf-8")
    assert "Анализ исходных договорных документов не завершён: Attachment Q" in report_xml
    rows = list(
        csv.DictReader(io.StringIO(render_tender_contract_analysis_csv(view).decode("utf-8-sig")))
    )
    assert {
        (row["subject"], row["state"])
        for row in rows
        if row["row_kind"] == "contract_source_coverage"
    } == {("Attachment Q", "incomplete")}


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
                "display_clause_ref": "Пункт без номера (стр./лист 12)",
                "source_name": "Changed-contract-terms.docx",
                "source_page": 12,
                "source_version_id": "source-independent-91",
                "source_locator_id": "locator-independent-311",
                "evidence_link_id": "evidence-independent-808",
                "authority_layer": "contract",
                "customer_obligation": "Provide site access before mobilisation.",
            }
        ],
        "attachment_references": [
            {
                "source_quote": "Site access appendix",
                "target_description": "Site access conditions",
                "match_decision": "unresolved",
                "source_name": "Changed-contract-terms.docx",
                "source_page": 12,
            }
        ],
        "issues": [
            {
                "issue_id": "issue-independent-11",
                "issue_version": 1,
                "issue_kind": "contract_risk",
                "subject": "payment_dependency",
                "clause_id": "clause-independent-7",
                "clause_version": 2,
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
    clause_row = next(row for row in csv_rows if row["row_kind"] == "source_clause")
    assert clause_row["clause_key"] == "Пункт без номера (стр./лист 12)"
    assert not any(row["clause_key"] == "payment.acceptance" for row in csv_rows)

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
        assert "Договорный риск" in document
        assert "Зависимость оплаты от внешнего условия" in document
        assert "Пункт / документ" in document
        assert "Changed-contract-terms.docx: Пункт без номера (стр./лист 12)" in document
        assert "Применимо" in document
        assert ">payment_dependency<" not in document
        assert ">contract_risk<" not in document
        assert "Customer accepts work after its internal review." in document
        assert "Payment is due only after Customer acceptance." in document
        assert "Define one evidence-backed acceptance period." in document
        assert "Ключевые условия договора и закупки" in document
        assert "5 месяцев" in document
        assert "Связь договора с проектом" in document
        assert "ПОС: 3 месяца; закупка: 5 месяцев." in document
        assert (
            document.index("Вопросы и риски")
            < document.index("Предложения для протокола разногласий")
            < document.index("Ключевые условия договора и закупки")
            < document.index("Связь договора с проектом")
            < document.index("Документы, на которые ссылается договор")
            < document.index("Обязательства сторон и условия исполнения")
        )

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
        assert '<w:gridCol w:w="5350"/>' in document
        assert '<w:cantSplit w:val="true"/>' in document
        assert '<w:tblHeader w:val="true"/>' in document
        assert "Источник: Документ: Changed-contract-terms.docx" in document
