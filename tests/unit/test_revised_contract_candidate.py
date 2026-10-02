# ruff: noqa: RUF001 -- Russian contract examples are intentional.
from __future__ import annotations

import io
import zipfile
from copy import deepcopy
from typing import Any
from uuid import UUID
from xml.etree import ElementTree as ET

import pytest

from asd_kontur.application_spine.services import ProductSpineService
from asd_kontur.tender.revised_contract_candidate import (
    RevisedContractCandidateError,
    render_revised_contract_candidate_docx,
)

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _source_docx(*paragraphs: str) -> bytes:
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{value}</w:t></w:r></w:p>' for value in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_WORD_NS}"><w:body>{body}</w:body></w:document>'
    ).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("word/document.xml", document)
        package.writestr("custom/untouched.bin", b"exact-untouched-package-member")
    return output.getvalue()


def _source_docx_with_ignorable_namespace(paragraph: str) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_WORD_NS}" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" '
        'mc:Ignorable="w15"><w:body>'
        f'<w:p><w:r><w:t xml:space="preserve">{paragraph}</w:t></w:r></w:p>'
        "</w:body></w:document>"
    ).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("word/document.xml", document)
    return output.getvalue()


def _view(source_text: str) -> dict[str, Any]:
    return {
        "clauses": [
            {
                "clause_id": "clause-arbitrary-91",
                "clause_version": 4,
                "source_text": source_text,
            }
        ],
        "revised_clauses": [
            {
                "revised_clause_id": "revision-arbitrary-12",
                "source_clause_id": "clause-arbitrary-91",
                "source_clause_version": 4,
                "revised_text": (
                    "4.2. Заказчик передаёт площадку не позднее пяти рабочих дней; "
                    "просрочка продлевает срок выполнения работ."
                ),
            }
        ],
    }


class _ContractProjection:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def latest(self, **_: object) -> dict[str, Any]:
        return deepcopy(self.value)


class _SourceRepository:
    def get_workspace_source_object(self, **_: object) -> dict[str, object]:
        return {
            "object_key": "contract-source",
            "media_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            "safe_display_name": "changed-project-contract.docx",
        }


class _ProjectContextRepository(_SourceRepository):
    def project_understanding_view(self, **_: object) -> dict[str, object]:
        return {
            "project_engineering": {
                "participants": [
                    {
                        "field": "customer",
                        "label": "Заказчик",
                        "value": "АО Заказчик-72",
                        "sources": [{"source_version_id": "source-contract-72"}],
                    },
                    {
                        "field": "designer",
                        "label": "Проектировщик",
                        "value": "Не относится к договору",
                        "sources": [{"source_version_id": "source-design-72"}],
                    },
                ],
                "contract_conditions": [
                    {
                        "field": "warranty_period",
                        "label": "Гарантийный срок",
                        "value": "24 месяца",
                        "sources": [{"source_version_id": "source-contract-72"}],
                    }
                ],
                "time_requirements": [
                    {
                        "field": "completion_date",
                        "label": "Окончание работ",
                        "value": "31 августа 2031 года",
                        "source_locator_ids": ["contract-date-72"],
                        "sources": [{"source_version_id": "source-contract-72"}],
                    },
                    {
                        "field": "work_duration",
                        "label": "Срок выполнения работ",
                        "value": "3 месяца",
                        "source_locator_ids": ["design-duration-72"],
                        "sources": [{"source_version_id": "source-design-72"}],
                    },
                    {
                        "field": "start_date",
                        "label": "Начало работ",
                        "value": "несвязанная дата",
                        "source_locator_ids": ["unrelated-date-72"],
                        "sources": [{"source_version_id": "source-design-72"}],
                    },
                ],
                "commercial_conditions": [
                    {
                        "field": "nmck",
                        "label": "НМЦК",
                        "value": "98 765 432,10 руб.",
                        "sources": [{"source_version_id": "source-procurement-72"}],
                    }
                ],
                "issues": [
                    {
                        "issue_id": "duration-72",
                        "finding_kind": "DURATION_MISMATCH",
                        "kind": "Расхождение продолжительности",
                        "description": "ПОС: 3 месяца; закупка: 5 месяцев.",
                        "source_locator_ids": ["design-duration-72"],
                        "sources": [
                            {"source_version_id": "source-design-72"},
                            {"source_version_id": "source-procurement-72"},
                        ],
                    },
                    {
                        "issue_id": "material-72",
                        "finding_kind": "MATERIAL_MISMATCH",
                        "kind": "Различие материала",
                        "sources": [{"source_version_id": "source-design-72"}],
                    },
                ],
            }
        }


class _ObjectStore:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def open(self, _: str) -> io.BytesIO:
        return io.BytesIO(self.payload)


def _service(source: bytes, view: dict[str, Any]) -> ProductSpineService:
    service = ProductSpineService.__new__(ProductSpineService)
    service._tender_contract_analysis = _ContractProjection(view)  # type: ignore[assignment]
    service._repository = _SourceRepository()  # type: ignore[assignment]
    service._object_store = _ObjectStore(source)  # type: ignore[assignment]
    return service


def _paragraphs(payload: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(payload)) as package:
        document = package.read("word/document.xml")
    root = ET.fromstring(document)
    return [
        "".join(node.text or "" for node in paragraph.iter(f"{{{_WORD_NS}}}t"))
        for paragraph in root.iter(f"{{{_WORD_NS}}}p")
    ]


def test_revised_contract_changes_only_exact_source_clause() -> None:
    original_clause = "4.2. Заказчик передаёт площадку после подписания договора."
    source = _source_docx(
        "1.1. Предмет договора остаётся без изменений.",
        original_clause,
        "9.1. Гарантийный срок составляет 24 месяца.",
    )

    revised = render_revised_contract_candidate_docx(source, _view(original_clause))

    assert _paragraphs(revised) == [
        "1.1. Предмет договора остаётся без изменений.",
        (
            "4.2. Заказчик передаёт площадку не позднее пяти рабочих дней; "
            "просрочка продлевает срок выполнения работ."
        ),
        "9.1. Гарантийный срок составляет 24 месяца.",
    ]
    with zipfile.ZipFile(io.BytesIO(revised)) as package:
        assert package.read("custom/untouched.bin") == b"exact-untouched-package-member"


def test_revised_contract_rejects_ambiguous_clause_match() -> None:
    repeated = "5.1. Оплата производится после приёмки."
    source = _source_docx(repeated, repeated)

    with pytest.raises(
        RevisedContractCandidateError,
        match="revised_contract_clause_match_not_unique",
    ):
        render_revised_contract_candidate_docx(source, _view(repeated))


def test_revised_contract_uses_explicit_replacement_source_span() -> None:
    first = "5.5. Документ подписывается Подрядчиком не позднее одного часа."
    continuation = "Датой поступления документа считается дата его размещения."
    source = _source_docx(first, continuation)
    view = _view(f"{first} {continuation}")
    revisions = view["revised_clauses"]
    assert isinstance(revisions, list)
    revisions[0]["replacement_source_text"] = first

    revised = render_revised_contract_candidate_docx(source, view)

    assert _paragraphs(revised) == [
        (
            "4.2. Заказчик передаёт площадку не позднее пяти рабочих дней; "
            "просрочка продлевает срок выполнения работ."
        ),
        continuation,
    ]


def test_revised_contract_replaces_one_exact_fragment_inside_paragraph() -> None:
    prefix = "3.4. Подрядчик выполняет работы. "
    unsafe = "Оплата зависит от внутреннего решения Заказчика."
    suffix = " Остальные условия пункта сохраняются."
    source = _source_docx(prefix + unsafe + suffix)
    view = _view(prefix + unsafe + suffix)
    revisions = view["revised_clauses"]
    assert isinstance(revisions, list)
    revisions[0]["replacement_source_text"] = unsafe
    revisions[0]["revised_text"] = "Оплата производится в течение семи рабочих дней."

    revised = render_revised_contract_candidate_docx(source, view)

    assert _paragraphs(revised) == [
        prefix + "Оплата производится в течение семи рабочих дней." + suffix
    ]


def test_revised_contract_does_not_duplicate_boundary_punctuation() -> None:
    unsafe = "3.5. Расходы во всех случаях несёт Подрядчик"
    source = _source_docx(unsafe + ".")
    view = _view(unsafe)
    revisions = view["revised_clauses"]
    assert isinstance(revisions, list)
    revisions[0]["replacement_source_text"] = unsafe
    revisions[0]["revised_text"] = "3.5. Расходы распределяются по установленной причине."

    revised = render_revised_contract_candidate_docx(source, view)

    assert _paragraphs(revised) == ["3.5. Расходы распределяются по установленной причине."]


def test_revised_contract_preserves_ignorable_namespace_declarations() -> None:
    original_clause = "4.2. Заказчик передаёт площадку после подписания договора."
    source = _source_docx_with_ignorable_namespace(original_clause)

    revised = render_revised_contract_candidate_docx(source, _view(original_clause))

    with zipfile.ZipFile(io.BytesIO(revised)) as package:
        document = package.read("word/document.xml").decode("utf-8")
    assert 'mc:Ignorable="w15"' in document
    assert 'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"' in document


def test_product_projection_advertises_only_verified_exact_candidate() -> None:
    original_clause = "7.3. Заказчик передаёт исходные данные после подписания договора."
    source_id = "71000000-0000-4000-8000-000000000091"
    view = _view(original_clause)
    clauses = view["clauses"]
    assert isinstance(clauses, list)
    clauses[0]["source_version_id"] = source_id
    view.update(
        {
            "revised_contracts": [{"state": "source_format_supported"}],
            "deliverables": [
                {"deliverable_kind": "revised_contract", "state": "source_format_supported"}
            ],
            "gaps": [],
        }
    )
    service = _service(_source_docx("1. Предмет договора.", original_clause), view)

    projected = service.tender_contract_analysis(
        owner_identity_id="owner:changed", workspace_id=UUID(int=72)
    )
    candidate = service.tender_revised_contract_candidate(
        owner_identity_id="owner:changed", workspace_id=UUID(int=72)
    )

    assert projected["revised_contracts"][0]["state"] == ("exact_source_candidate_available")
    assert projected["deliverables"][0]["state"] == "exact_source_candidate_available"
    assert candidate.safe_display_name == (
        "changed-project-contract-contractor-revision-candidate.docx"
    )
    assert _paragraphs(b"".join(candidate.chunks))[1].startswith("4.2.")


def test_product_projection_keeps_ambiguous_source_as_clause_schedule() -> None:
    repeated = "8.4. Оплата производится после подписания акта."
    source_id = "71000000-0000-4000-8000-000000000092"
    view = _view(repeated)
    clauses = view["clauses"]
    assert isinstance(clauses, list)
    clauses[0]["source_version_id"] = source_id
    view.update(
        {
            "revised_contracts": [{"state": "source_format_supported"}],
            "deliverables": [
                {"deliverable_kind": "revised_contract", "state": "source_format_supported"}
            ],
            "gaps": [],
        }
    )
    service = _service(_source_docx(repeated, repeated), view)

    projected = service.tender_contract_analysis(
        owner_identity_id="owner:changed", workspace_id=UUID(int=73)
    )

    assert projected["revised_contracts"] == []
    assert projected["deliverables"][0]["state"] == "candidate_clause_schedule"
    assert "revised_contract_clause_match_not_unique" in projected["gaps"]


def test_product_projection_joins_contract_parties_and_project_wide_conditions() -> None:
    view = _view("1.1. Предмет договора.")
    view.update(
        {
            "assessment": {
                "sources": [{"source_version_id": "source-contract-72"}],
            },
            "revised_contracts": [],
            "deliverables": [],
            "gaps": [],
        }
    )
    service = _service(_source_docx("1.1. Предмет договора."), view)
    service._repository = _ProjectContextRepository()  # type: ignore[assignment]

    projected = service.tender_contract_analysis(
        owner_identity_id="owner:changed", workspace_id=UUID(int=74)
    )

    assert [item["value"] for item in projected["project_context"]["participants"]] == [
        "АО Заказчик-72"
    ]
    assert projected["project_context"]["key_conditions"][0]["value"] == "24 месяца"
    assert projected["project_context"]["commercial_conditions"][0]["value"] == (
        "98 765 432,10 руб."
    )
    assert [item["value"] for item in projected["project_context"]["time_requirements"]] == [
        "31 августа 2031 года",
        "3 месяца",
    ]
    assert [
        item["issue_id"] for item in projected["project_context"]["project_contract_findings"]
    ] == ["duration-72"]


def test_product_projection_summarizes_numbered_contract_clauses_without_project_facts() -> None:
    view = _view("3.1. Цена договора составляет 27 500 000 рублей.")
    view.update(
        {
            "clauses": [
                {
                    "category": "price",
                    "clause_ref": "item_17",
                    "source_text": "17 Плита сборная шт 8 125000,00",
                    "source_name": "Изменённый договор.docx",
                    "source_page": 2,
                },
                {
                    "category": "price",
                    "clause_ref": "3.1",
                    "source_text": "3.1. Цена договора составляет 27 500 000 рублей.",
                    "source_name": "Изменённый договор.docx",
                    "source_page": 4,
                    "source_version_id": "source-contract-91",
                    "source_locator_id": "locator-price-91",
                },
                {
                    "category": "payment",
                    "clause_ref": "4.7",
                    "source_text": "4.7. Оплата производится в течение 12 рабочих дней.",
                    "source_name": "Изменённый договор.docx",
                    "source_page": 5,
                },
                {
                    "category": "payment",
                    "clause_ref": "4.8",
                    "source_text": "4.8. Аванс засчитывается при окончательном расчёте.",
                    "source_name": "Изменённый договор.docx",
                    "source_page": 5,
                },
                {
                    "category": "security",
                    "clause_ref": "6.10_dup",
                    "source_text": (
                        "6.10. Обеспечение гарантийных обязательств составляет 3 процента."
                    ),
                    "source_name": "Изменённый договор.docx",
                    "source_page": 8,
                },
            ],
            "revised_contracts": [],
            "deliverables": [],
            "gaps": [],
        }
    )
    service = _service(_source_docx("3.1. Цена договора."), view)

    projected = service.tender_contract_analysis(
        owner_identity_id="owner:changed", workspace_id=UUID(int=75)
    )

    assert [
        (item["field"], item["label"], item["value"])
        for item in projected["project_context"]["key_conditions"]
    ] == [
        (
            "contract_clause_price",
            "Цена договора (п. 3.1)",
            "3.1. Цена договора составляет 27 500 000 рублей.",
        ),
        (
            "contract_clause_payment",
            "Порядок оплаты (п. 4.7)",
            "4.7. Оплата производится в течение 12 рабочих дней.",
        ),
        (
            "contract_clause_security",
            "Обеспечение (п. 6.10)",
            "6.10. Обеспечение гарантийных обязательств составляет 3 процента.",
        ),
    ]
    assert projected["project_context"]["key_conditions"][0]["sources"] == [
        {
            "source_version_id": "source-contract-91",
            "source_locator_id": "locator-price-91",
            "document": "Изменённый договор.docx",
            "page": 4,
        }
    ]
