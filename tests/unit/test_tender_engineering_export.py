# ruff: noqa: RUF001 -- Russian construction language is intentional.

from __future__ import annotations

import csv
import io
import zipfile

from asd_kontur.tender.engineering_export import (
    render_engineering_disagreement_protocol_docx,
    render_engineering_findings_csv,
    render_engineering_tender_report_docx,
    render_engineering_work_schedule_csv,
)


def _model() -> dict[str, object]:
    return {
        "project": {
            "name": {"value": "Испытательный комплекс"},
            "purpose": {"value": "Отведение воды"},
        },
        "pits": {"professional_answer": "Установлено два котлована."},
        "document_composition": {
            "professional_summary": "В комплекте есть ПД и смета; ВОР не найдена."
        },
        "facilities": [{"name": "КНС 7", "kind": "Сооружение", "status": "Установлено"}],
        "facility_cards": [
            {
                "facility": {"name": "КНС 7"},
                "characteristics": [{"label": "Производительность КНС-7", "value": "42 л/с"}],
                "pits": [{"name": "Котлован КНС 7"}],
                "structures": [{"name": "Фундаментная плита"}],
                "connections": [{"name": "Напорный трубопровод"}],
                "works": [{"work_name": "Погружение шпунта"}],
                "missing_information": ["Профиль шпунта требует уточнения"],
            }
        ],
        "works": [
            {
                "work_scope_id": "work-1",
                "facility": "КНС 7",
                "work_family": "Шпунтовые работы",
                "work_name": "Погружение шпунта",
                "project_wording": ["Погружение шпунта Л5-УМ"],
                "quantities_by_document": {
                    "РД": [{"value": "18.5", "unit": "т"}],
                    "ВОР": [{"value": "16", "unit": "т"}],
                },
                "materials_by_document": {"РД": [{"name": "Шпунт Л5-УМ, сталь С255"}]},
                "status": "Привязано к сооружению",
                "source_locator_ids": ["locator-a"],
                "sources": [{"document": "КР.pdf", "version": 2, "page": 17}],
            }
        ],
        "quantity_comparisons": [
            {
                "facility": "КНС 7",
                "work": "Погружение шпунта",
                "left": {"document_role": "РД", "value": "18.5", "unit": "т"},
                "right": {"document_role": "ВОР", "value": "16", "unit": "т"},
                "conclusion": "Разница РД ↔ ВОР: 2.5 т",
            }
        ],
        "material_comparisons": [
            {
                "facility": "КНС 7",
                "work": "Железобетонные конструкции",
                "material": "Бетон В25",
                "description": "морозостойкость: проект F200, коммерческие документы F150.",
            }
        ],
        "scope_comparisons": [
            {
                "classification": "UNRESOLVED_SCOPE_MATCH",
                "professional_status": "Требуется распределить коммерческий объём",
                "facility": "КНС 7",
                "work": "Погружение шпунта",
                "conclusion": "Сметный объём не распределён по сооружениям.",
            }
        ],
        "sheet_pile_schedule": [
            {
                "facility": "КНС 7",
                "pit": "котлован для КНС 7",
                "operation": "Погружение шпунта",
                "quantities_by_document": {"РД": [{"value": "18.5", "unit": "т"}]},
                "uncertainty": "Требуется распределить коммерческий объём.",
            }
        ],
        "materials": [],
        "issues": [
            {
                "kind": "Расхождение объёмов",
                "location": "КНС 7",
                "subject": "Погружение шпунта",
                "description": "Разница РД ↔ ВОР: 2.5 т",
                "practical_consequence": "Требуется согласовать цену.",
                "recommended_action": "Запросить подтверждение объёма.",
                "status": "Установленное расхождение",
                "source_locator_ids": ["locator-a"],
                "sources": [{"document": "КР.pdf", "version": 2, "page": 17}],
            }
        ],
        "customer_questions": [{"question": "Какой объём применять?"}],
        "risks": [{"risk": "Неполная цена предложения."}],
        "requirements": {"professional_summary": "Применимость нормы уточняется."},
        "documents": [{"name": "КР.pdf", "version": 2, "document_role": "РД"}],
        "unclassified_works": [],
        "unresolved": {
            "participants": [
                {
                    "reason": (
                        "Для роли «Заказчик» встречается альтернативное указание "
                        "«ГУП Городские сети», но оно требует уточнения."
                    )
                }
            ]
        },
    }


def test_work_and_finding_schedules_are_editable_professional_outputs() -> None:
    work_rows = list(
        csv.DictReader(
            io.StringIO(render_engineering_work_schedule_csv(_model()).decode("utf-8-sig"))
        )
    )
    finding_rows = list(
        csv.DictReader(io.StringIO(render_engineering_findings_csv(_model()).decode("utf-8-sig")))
    )

    rd_row = next(row for row in work_rows if row["Документ"] == "РД")
    assert rd_row["Сооружение / место"] == "КНС 7"
    assert rd_row["Объём"] == "18.5"
    assert rd_row["Материалы"] == "Шпунт Л5-УМ, сталь С255"
    assert finding_rows[0]["Вывод"] == "Разница РД ↔ ВОР: 2.5 т"
    assert finding_rows[0]["Действие / вопрос Заказчику"] == "Запросить подтверждение объёма."
    assert finding_rows[0]["Источники / source_references"] == ("КР.pdf, версия 2, стр./лист 17")


def test_tender_report_is_reopenable_editable_docx_with_engineering_sections() -> None:
    payload = render_engineering_tender_report_docx(_model())

    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        assert document.testzip() is None
        xml = document.read("word/document.xml").decode("utf-8")
    assert "Первичный анализ проекта" in xml
    assert "Общая характеристика проекта" in xml
    assert "В комплекте есть ПД и смета; ВОР не найдена." in xml
    assert "Испытательный комплекс" in xml
    assert "Разница РД ↔ ВОР: 2.5 т" in xml
    assert "КНС 7 — котлован для КНС 7" in xml
    assert "Бетон В25" in xml
    assert "проект F200, коммерческие документы F150" in xml
    assert "Фундаментная плита, Напорный трубопровод" in xml
    assert "Производительность КНС-7: 42 л/с" in xml
    assert "Возможные неучтённые работы" in xml
    assert "Ключевые выводы для участия в тендере" in xml
    assert "Запросить подтверждение объёма" in xml
    assert "доказанные неучтённые работы не выявлены" in xml
    assert "Требуется распределить коммерческий объём: 1 поз." in xml
    assert "Нормативные вопросы" in xml
    assert "Неопределённости / недостающие данные" in xml
    assert "ГУП Городские сети" in xml
    assert "Вопросы Заказчику" in xml
    assert 'w:header="708"' in xml
    assert 'w:footer="708"' in xml
    assert 'w:gutter="0"' in xml
    assert "<w:tblHeader/>" in xml
    assert "<w:tblBorders>" in xml
    assert '<w:tblLayout w:type="fixed"/>' in xml


def test_tender_report_omits_sections_without_project_inputs() -> None:
    payload = render_engineering_tender_report_docx(
        {
            "project": {
                "name": {"value": "Реконструкция причала"},
                "purpose": {"value": "Восстановление грузового фронта"},
            },
            "pits": {"professional_answer": "Котлованы в документах не установлены."},
            "document_composition": {"professional_summary": "Установлен раздел КР."},
            "documents": [{"name": "KR-07.pdf", "version": 1, "document_role": "РД"}],
        }
    )

    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        xml = document.read("word/document.xml").decode("utf-8")
    assert "Реконструкция причала" in xml
    assert "Восстановление грузового фронта" in xml
    assert "Расхождения проектных и коммерческих документов" not in xml
    assert "Требования закупки" not in xml
    assert "Риски Подрядчика" not in xml


def test_tender_report_omits_zero_pit_inventory_for_unrelated_scope() -> None:
    payload = render_engineering_tender_report_docx(
        {
            "project": {"name": {"value": "Реконструкция здания"}},
            "pits": {
                "established_count": 0,
                "unresolved_group_count": 0,
                "professional_answer": "В проекте подтверждено 0 отдельных котлованов.",
            },
        }
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        xml = document.read("word/document.xml").decode("utf-8")
    assert "котлованов" not in xml


def test_tender_report_explains_unchecked_total_without_calling_it_a_discrepancy() -> None:
    model = {
        "project": {"name": {"value": "Испытательный мост"}},
        "unresolved": {
            "quantities": [
                {
                    "unresolved_kind": "component_total_relationship",
                    "quantity_candidate_id": "total-a",
                    "facility": "Пролёт 1",
                    "work": "Монтаж металлоконструкций",
                    "document_role": "РД",
                    "value": "12",
                    "unit": "т",
                    "reason": "Связи общего объёма и составляющих противоречат друг другу.",
                },
                {
                    "quantity_candidate_id": "unreviewed-b",
                    "reason": "Непроверенное извлечение не является выводом отчёта.",
                },
            ]
        },
    }

    payload = render_engineering_tender_report_docx(model)
    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        assert document.testzip() is None
        xml = document.read("word/document.xml").decode("utf-8")

    assert "Пролёт 1: Монтаж металлоконструкций — РД 12 т." in xml
    assert "Связи общего объёма и составляющих противоречат друг другу." in xml
    assert "Непроверенное извлечение не является выводом отчёта." not in xml
    assert "Расхождения проектных и коммерческих документов" not in xml
    assert "Инвентаризация котлованов не завершена" not in xml


def test_tender_report_preserves_zero_quantity_in_unresolved_total() -> None:
    payload = render_engineering_tender_report_docx(
        {
            "unresolved": {
                "quantities": [
                    {
                        "unresolved_kind": "component_total_relationship",
                        "quantity_candidate_id": "total-zero",
                        "work": "Выемка грунта",
                        "document_role": "РД",
                        "value": 0,
                        "unit": "м3",
                        "reason": "Состав частей требует уточнения.",
                    }
                ]
            }
        }
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        xml = document.read("word/document.xml").decode("utf-8")
    assert "РД 0 м3" in xml
    assert "значение не установлено" not in xml


def test_tender_report_shows_ambiguous_design_commercial_allocation_as_uncertainty() -> None:
    payload = render_engineering_tender_report_docx(
        {
            "project": {"name": {"value": "Испытательный путепровод"}},
            "unresolved": {
                "quantities": [
                    {
                        "unresolved_kind": "cross_document_quantity_allocation",
                        "allocation_id": "allocation-a",
                        "facility": "Опора Z",
                        "work": "Монтаж облицовки",
                        "design_quantities": [
                            {"document_role": "ПД", "value": "45", "unit": "м2"},
                            {"document_role": "РД", "value": "47", "unit": "м2"},
                        ],
                        "commercial_quantities": [
                            {"document_role": "Смета", "value": "45", "unit": "м2"}
                        ],
                        "reason": "Нужно уточнить, повторяют ли проектные позиции один объём.",
                    }
                ]
            },
        }
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        xml = document.read("word/document.xml").decode("utf-8")

    assert "Опора Z: Монтаж облицовки — проект: ПД 45 м2; РД 47 м2" in xml
    assert "коммерческие документы: Смета 45 м2" in xml
    assert "Нужно уточнить, повторяют ли проектные позиции один объём." in xml
    assert "Расхождения проектных и коммерческих документов" not in xml


def test_tender_report_adapts_to_procurement_and_contract_inputs() -> None:
    value = _model()
    value["participants"] = [{"label": "Заказчик", "value": "АО Заказчик"}]
    value["commercial_conditions"] = [{"label": "НМЦК", "value": "125 млн руб."}]
    value["time_requirements"] = [{"label": "Срок договора", "value": "18 месяцев"}]
    value["procurement_requirements"] = [{"label": "Требование СРО", "value": "Членство в СРО"}]
    value["contract_conditions"] = [{"label": "Гарантийный срок", "value": "60 месяцев"}]

    payload = render_engineering_tender_report_docx(value)

    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        xml = document.read("word/document.xml").decode("utf-8")
    for expected in (
        "Участники проекта",
        "АО Заказчик",
        "Коммерческие условия / цена",
        "125 млн руб.",
        "Сроки",
        "Требования закупки",
        "Договорные условия и гарантии",
    ):
        assert expected in xml


def test_primary_tender_outputs_include_candidate_contract_risks_and_revisions() -> None:
    value = _model()
    value["contract_analysis"] = {
        "status": "drafted",
        "clauses": [
            {
                "clause_id": "clause-17",
                "clause_key": "7.4",
                "source_text": "Подрядчик отвечает за задержку независимо от причины.",
                "source_version_id": "source-contract",
                "source_locator_ids": ["page-12"],
            }
        ],
        "issues": [
            {
                "issue_id": "risk-17",
                "clause_id": "clause-17",
                "subject": "Одностороннее распределение риска задержки",
                "description": "Условие не учитывает задержку исходных данных Заказчиком.",
                "consequence_code": "Подрядчик несёт риск срока вне своего контроля.",
                "recommendation_text": "Предусмотреть продление срока при задержке Заказчика.",
                "severity": "high",
            },
            {
                "issue_id": "risk-17-duplicate",
                "clause_id": "clause-17",
                "subject": "Одностороннее распределение риска задержки",
                "description": "Условие не учитывает задержку исходных данных Заказчиком.",
                "consequence_code": "Подрядчик несёт риск срока вне своего контроля.",
                "recommendation_text": "Предусмотреть продление срока при задержке Заказчика.",
                "severity": "high",
            },
        ],
        "disagreement_items": [
            {
                "clause_id": "clause-17",
                "issue_id": "risk-17",
                "proposed_clause_text": (
                    "Срок продлевается на период задержки исходных данных Заказчиком."
                ),
            }
        ],
    }

    finding_rows = list(
        csv.DictReader(io.StringIO(render_engineering_findings_csv(value).decode("utf-8-sig")))
    )
    contract_row = next(row for row in finding_rows if row["Вид вопроса"] == "Договорный риск")
    assert contract_row["Место"] == "7.4"
    assert contract_row["Практическое последствие"] == (
        "Подрядчик несёт риск срока вне своего контроля."
    )
    assert contract_row["Источники / source_references"] == "page-12"

    payload = render_engineering_tender_report_docx(value)
    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        xml = document.read("word/document.xml").decode("utf-8")
    assert "Договорные риски Подрядчика" in xml
    assert "Условие не учитывает задержку исходных данных Заказчиком." in xml
    summary_xml = xml.split("Ключевые выводы для участия в тендере", 1)[1].split(
        "Состав объекта", 1
    )[0]
    assert summary_xml.count("Условие не учитывает задержку исходных данных Заказчиком.") == 1
    assert "Предлагаемые изменения договора" in xml
    assert "Срок продлевается на период задержки исходных данных Заказчиком." in xml


def test_disagreement_protocol_is_editable_and_keeps_contractor_action() -> None:
    payload = render_engineering_disagreement_protocol_docx(_model())

    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        assert document.testzip() is None
        xml = document.read("word/document.xml").decode("utf-8")
    assert "Протокол разногласий" in xml
    assert "Позиция Заказчика" in xml
    assert "Запросить подтверждение объёма" in xml
    assert "КР.pdf, версия 2, стр./лист 17" in xml
    assert 'w:header="708"' in xml
    assert 'w:footer="708"' in xml
    assert 'w:gutter="0"' in xml
