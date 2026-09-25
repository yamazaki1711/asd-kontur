# ruff: noqa: RUF001 -- Russian construction language is intentional.

from __future__ import annotations

import csv
import io
import zipfile

from asd_kontur.tender.engineering_export import (
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
        "facilities": [{"name": "КНС 7", "kind": "Сооружение", "status": "Установлено"}],
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
            }
        ],
        "customer_questions": [{"question": "Какой объём применять?"}],
        "risks": [{"risk": "Неполная цена предложения."}],
        "requirements": {"professional_summary": "Применимость нормы уточняется."},
        "documents": [{"name": "КР.pdf", "version": 2, "document_role": "РД"}],
        "unclassified_works": [],
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


def test_tender_report_is_reopenable_editable_docx_with_engineering_sections() -> None:
    payload = render_engineering_tender_report_docx(_model())

    with zipfile.ZipFile(io.BytesIO(payload)) as document:
        assert document.testzip() is None
        xml = document.read("word/document.xml").decode("utf-8")
    assert "Tender-анализ проекта" in xml
    assert "Испытательный комплекс" in xml
    assert "Разница РД ↔ ВОР: 2.5 т" in xml
    assert "Вопросы Заказчику" in xml
