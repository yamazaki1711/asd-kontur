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
                "time_requirements": [],
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
    assert [
        item["issue_id"] for item in projected["project_context"]["project_contract_findings"]
    ] == ["duration-72"]
