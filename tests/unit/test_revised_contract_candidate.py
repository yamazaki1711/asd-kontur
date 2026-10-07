# ruff: noqa: RUF001 -- Russian contract examples are intentional.
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from uuid import UUID
from xml.etree import ElementTree as ET

import pytest

import asd_kontur.tender.revised_contract_candidate as revised_contract_module
from asd_kontur.application_spine.services import ProductSpineService
from asd_kontur.tender.contract_analysis_view import _select_primary_revised_contract_source
from asd_kontur.tender.contract_revision_selection import (
    contract_revision_fingerprint,
    select_contract_revisions,
)
from asd_kontur.tender.revised_contract_candidate import (
    RevisedContractCandidateError,
    render_revised_contract_candidate_docx,
    render_revised_contract_source_package,
)

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _write_minimal_docx_package(package: zipfile.ZipFile, document: bytes) -> None:
    package.writestr(
        "[Content_Types].xml",
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>",
    )
    package.writestr(
        "_rels/.rels",
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>",
    )
    package.writestr("word/document.xml", document)


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
        _write_minimal_docx_package(package, document)
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
        _write_minimal_docx_package(package, document)
    return output.getvalue()


def test_revised_contract_package_applies_two_sources_and_preserves_unchanged_docx() -> None:
    source_a = _source_docx("1. Предмет договора.", "2. Оплата после акта.")
    source_b = _source_docx("Приложение. График обязателен.")
    source_c = _source_docx("Неизменённые условия страхования.")
    view = {
        "clauses": [
            {
                "clause_id": "payment-1",
                "clause_version": 1,
                "source_version_id": "source-a",
                "source_text": "2. Оплата после акта.",
            },
            {
                "clause_id": "schedule-1",
                "clause_version": 1,
                "source_version_id": "source-b",
                "source_text": "Приложение. График обязателен.",
            },
        ],
        "revised_clauses": [
            {
                "source_clause_id": "payment-1",
                "source_clause_version": 1,
                "revised_text": "2. Оплата после подписания акта в течение десяти дней.",
            },
            {
                "source_clause_id": "schedule-1",
                "source_clause_version": 1,
                "revised_text": "Приложение. График корректируется при задержке Заказчика.",
            },
        ],
        "gaps": [
            "REVISED_CONTRACT_EXCLUDES_NON_PRIMARY_SOURCE_REVISIONS",
            "CONTRACT_REFERENCED_DOCUMENT_UNRESOLVED",
        ],
    }
    sources = [
        {
            "source_version_id": "source-a",
            "safe_display_name": "contract.docx",
            "content": source_a,
        },
        {"source_version_id": "source-b", "safe_display_name": "annex.docx", "content": source_b},
        {"source_version_id": "source-c", "safe_display_name": "terms.docx", "content": source_c},
    ]
    first = render_revised_contract_source_package(sources, view)
    assert render_revised_contract_source_package(sources, view) == first
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist() == [
            "contract-source-01.docx",
            "contract-source-02.docx",
            "contract-source-03.docx",
            "change-register.csv",
            "manifest.json",
        ]
        assert _paragraphs(archive.read("contract-source-01.docx"))[1] == (
            "2. Оплата после подписания акта в течение десяти дней."
        )
        assert _paragraphs(archive.read("contract-source-02.docx"))[0] == (
            "Приложение. График корректируется при задержке Заказчика."
        )
        assert archive.read("contract-source-03.docx") == source_c
        change_register = archive.read("change-register.csv")
        changes = list(csv.DictReader(io.StringIO(change_register.decode("utf-8-sig"))))
        manifest = json.loads(archive.read("manifest.json"))
    assert len(changes) == 2
    assert [change["Документ"] for change in changes] == ["contract.docx", "annex.docx"]
    assert changes[0]["Пункт договора"] == "2"
    assert (
        changes[0]["Редакция Подрядчика"]
        == "2. Оплата после подписания акта в течение десяти дней."
    )
    assert manifest["change_register"]["revision_count"] == 2
    assert manifest["change_register"]["sha256"] == hashlib.sha256(change_register).hexdigest()
    assert [item["revision_count"] for item in manifest["sources"]] == [1, 1, 0]
    assert manifest["status"] == "human_review_candidate"
    assert manifest["coherence_review"] == {
        "status": "not_performed",
        "scope": "selected_related_clauses_only",
        "accepted_contexts": 0,
        "scheduled_contexts": 0,
        "potential_conflict_count": 0,
    }
    assert manifest["analysis_gaps"] == ["CONTRACT_REFERENCED_DOCUMENT_UNRESOLVED"]


def test_reviewed_package_carries_matching_editable_protocol() -> None:
    original = "4.2. Customer may delay payment indefinitely."
    proposed = "4.2. Payment follows documented acceptance."
    protocol = _source_docx("ПРОТОКОЛ РАЗНОГЛАСИЙ", proposed)
    package = render_revised_contract_source_package(
        [
            {
                "source_version_id": "source-contract",
                "safe_display_name": "contract.docx",
                "content": _source_docx(original),
            }
        ],
        {
            "clauses": [
                {
                    "clause_id": "clause-42",
                    "clause_version": 1,
                    "source_version_id": "source-contract",
                    "source_text": original,
                }
            ],
            "revised_clauses": [
                {
                    "source_clause_id": "clause-42",
                    "source_clause_version": 1,
                    "revised_text": proposed,
                }
            ],
        },
        protocol_docx=protocol,
    )
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert archive.namelist() == [
            "contract-source-01.docx",
            "change-register.csv",
            "reviewed-disagreement-protocol.docx",
            "manifest.json",
        ]
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["reviewed_protocol"]["proposal_count"] == 1
        assert archive.read("reviewed-disagreement-protocol.docx") == protocol
        assert _paragraphs(archive.read("contract-source-01.docx")) == [proposed]


def test_revised_contract_refuses_unresolved_proposal_placeholder() -> None:
    original = "4.2. Заказчик оплачивает принятые работы после получения финансирования."
    with pytest.raises(RevisedContractCandidateError, match="unresolved_placeholder"):
        render_revised_contract_candidate_docx(
            _source_docx(original),
            {
                "clauses": [{"clause_id": "payment", "clause_version": 1, "source_text": original}],
                "revised_clauses": [
                    {
                        "source_clause_id": "payment",
                        "source_clause_version": 1,
                        "revised_text": "4.2. Оплата производится в течение [X] дней.",
                    }
                ],
            },
        )


def test_revised_contract_refuses_zip_without_office_document_relationship() -> None:
    original = "4.2. Payment follows acceptance."
    malformed = io.BytesIO()
    with zipfile.ZipFile(malformed, "w") as package:
        package.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="{_WORD_NS}"><w:body><w:p><w:r><w:t>'
            f"{original}</w:t></w:r></w:p></w:body></w:document>",
        )
    with pytest.raises(RevisedContractCandidateError, match="source_docx_invalid"):
        render_revised_contract_candidate_docx(
            malformed.getvalue(),
            {
                "clauses": [{"clause_id": "payment", "clause_version": 1, "source_text": original}],
                "revised_clauses": [
                    {
                        "source_clause_id": "payment",
                        "source_clause_version": 1,
                        "revised_text": "4.2. Payment follows a signed acceptance certificate.",
                    }
                ],
            },
        )


def test_revised_contract_change_register_is_editable_and_formula_safe() -> None:
    source = "=unsafe source formula"
    proposal = "@unsafe proposed formula"
    package = render_revised_contract_source_package(
        [{"source_version_id": "source-a", "content": _source_docx(source)}],
        {
            "clauses": [
                {
                    "clause_id": "clause-a",
                    "clause_version": 1,
                    "source_version_id": "source-a",
                    "source_text": source,
                    "source_page": 4,
                }
            ],
            "revised_clauses": [
                {
                    "source_clause_id": "clause-a",
                    "source_clause_version": 1,
                    "revised_text": proposal,
                }
            ],
        },
    )
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        rows = list(
            csv.DictReader(io.StringIO(archive.read("change-register.csv").decode("utf-8-sig")))
        )
        assert _paragraphs(archive.read("contract-source-01.docx")) == [proposal]
    assert rows[0]["Исходная редакция"] == "'=unsafe source formula"
    assert rows[0]["Редакция Подрядчика"] == "'@unsafe proposed formula"
    assert rows[0]["Пункт договора"] == "Пункт без номера (стр./лист 4)"
    guarded = list(
        csv.reader(
            io.StringIO(
                revised_contract_module._render_change_register([(" \t=delayed formula",)]).decode(
                    "utf-8-sig"
                )
            )
        )
    )
    assert guarded[1][0] == "' \t=delayed formula"


def test_selected_revision_package_preserves_unselected_contract_source() -> None:
    source_a = _source_docx("Payment follows acceptance.")
    source_b = _source_docx("Warranty lasts two years.")
    selected_id = "018f5c3e-7b00-7000-8000-000000002111"
    omitted_id = "018f5c3e-7b00-7000-8000-000000002112"
    view = {
        "clauses": [
            {
                "clause_id": "payment",
                "clause_version": 1,
                "source_version_id": "source-a",
                "source_text": "Payment follows acceptance.",
            },
            {
                "clause_id": "warranty",
                "clause_version": 1,
                "source_version_id": "source-b",
                "source_text": "Warranty lasts two years.",
            },
        ],
        "revised_clauses": [
            {
                "revised_clause_id": selected_id,
                "source_clause_id": "payment",
                "source_clause_version": 1,
                "revised_text": "Payment follows acceptance within ten days.",
            },
            {
                "revised_clause_id": omitted_id,
                "source_clause_id": "warranty",
                "source_clause_version": 1,
                "revised_text": "Warranty lasts one year.",
            },
        ],
    }
    selected = select_contract_revisions(
        view,
        revision_ids=[selected_id],
        fingerprint=contract_revision_fingerprint(view),
    )
    archive_bytes = render_revised_contract_source_package(
        [
            {"source_version_id": "source-a", "content": source_a},
            {"source_version_id": "source-b", "content": source_b},
        ],
        selected,
    )
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert _paragraphs(archive.read("contract-source-01.docx")) == [
            "Payment follows acceptance within ten days."
        ]
        assert archive.read("contract-source-02.docx") == source_b
        manifest = json.loads(archive.read("manifest.json"))
    assert [source["revision_count"] for source in manifest["sources"]] == [1, 0]


def test_revised_contract_package_fails_when_revision_source_is_not_admitted() -> None:
    with pytest.raises(RevisedContractCandidateError, match="clause_source_unavailable"):
        render_revised_contract_source_package(
            [{"source_version_id": "source-a", "content": _source_docx("1. Условие.")}],
            {
                "clauses": [
                    {
                        "clause_id": "c",
                        "clause_version": 1,
                        "source_version_id": "source-b",
                        "source_text": "1. Условие.",
                    }
                ],
                "revised_clauses": [
                    {
                        "source_clause_id": "c",
                        "source_clause_version": 1,
                        "revised_text": "1. Иное условие.",
                    }
                ],
            },
        )


def test_revised_contract_does_not_carry_invalidated_source_signature() -> None:
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w") as package:
        with zipfile.ZipFile(io.BytesIO(_source_docx("1. Условие договора."))) as original:
            for member in original.namelist():
                package.writestr(member, original.read(member))
        package.writestr("_xmlsignatures/sig1.xml", b"<Signature />")
    with pytest.raises(RevisedContractCandidateError, match="signed_source_unsupported"):
        render_revised_contract_candidate_docx(source.getvalue(), _view("1. Условие договора."))


def test_revised_contract_rejects_unresolved_source_tracked_changes() -> None:
    paragraph = "1. Payment follows acceptance."
    document = (
        f'<w:document xmlns:w="{_WORD_NS}"><w:body><w:p><w:ins w:id="1">'
        f"<w:r><w:t>{paragraph}</w:t></w:r>"
        "</w:ins></w:p></w:body></w:document>"
    ).encode()
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w") as package:
        _write_minimal_docx_package(package, document)

    with pytest.raises(
        RevisedContractCandidateError,
        match="revised_contract_source_tracked_changes_unsupported",
    ):
        render_revised_contract_candidate_docx(source.getvalue(), _view(paragraph))

    with pytest.raises(
        RevisedContractCandidateError,
        match="revised_contract_source_tracked_changes_unsupported",
    ):
        render_revised_contract_source_package(
            [
                {
                    "source_version_id": "edited-source",
                    "content": _source_docx(paragraph),
                },
                {
                    "source_version_id": "untouched-source",
                    "content": source.getvalue(),
                },
            ],
            {
                "clauses": [
                    {
                        "clause_id": "one",
                        "clause_version": 1,
                        "source_version_id": "edited-source",
                        "source_text": paragraph,
                    }
                ],
                "revised_clauses": [
                    {
                        "source_clause_id": "one",
                        "source_clause_version": 1,
                        "revised_text": "1. Payment follows signed acceptance.",
                    }
                ],
            },
        )


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


class _SourceByIdRepository(_SourceRepository):
    def get_workspace_source_object(self, **values: object) -> dict[str, object]:
        source_version_id = str(values["source_version_id"])
        return {
            "object_key": source_version_id,
            "media_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            "safe_display_name": f"source-{source_version_id[-2:]}.docx",
        }


class _ObjectStoreByKey:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads

    def open(self, key: str) -> io.BytesIO:
        return io.BytesIO(self.payloads[key])


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
    service._contract_revision_reviews = SimpleNamespace(latest_decisions=lambda **kwargs: [])  # type: ignore[assignment]
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


def test_revised_contract_preserves_clause_number_when_draft_omits_it() -> None:
    original = "7.4. Customer may delay payment."
    view = {
        "clauses": [
            {
                "clause_id": "numbered-clause",
                "clause_version": 1,
                "source_text": original,
            }
        ],
        "revised_clauses": [
            {
                "source_clause_id": "numbered-clause",
                "source_clause_version": 1,
                "revised_text": "Payment follows acceptance.",
            }
        ],
    }
    revised = render_revised_contract_candidate_docx(_source_docx(original), view)
    assert _paragraphs(revised) == ["7.4. Payment follows acceptance."]
    view["revised_clauses"][0]["revised_text"] = "8.1. Payment follows acceptance."
    with pytest.raises(RevisedContractCandidateError, match="clause_number_changed"):
        render_revised_contract_candidate_docx(_source_docx(original), view)


def test_revised_contract_rejects_two_edits_to_one_paragraph() -> None:
    original = "4.1. First obligation; second obligation."
    view = {
        "clauses": [
            {"clause_id": "first", "clause_version": 1, "source_text": "First obligation"},
            {"clause_id": "second", "clause_version": 1, "source_text": "second obligation"},
        ],
        "revised_clauses": [
            {
                "source_clause_id": "first",
                "source_clause_version": 1,
                "revised_text": "Changed first",
            },
            {
                "source_clause_id": "second",
                "source_clause_version": 1,
                "revised_text": "changed second",
            },
        ],
    }
    with pytest.raises(RevisedContractCandidateError, match="overlapping_clause_edits"):
        render_revised_contract_candidate_docx(_source_docx(original), view)


def test_revised_contract_rejects_post_edit_serialization_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_docx("Unchanged text.", "Change this clause.")
    original_restore = revised_contract_module._restore_ignorable_namespaces

    def damaged_restore(document: bytes, *, source_namespaces: dict[str, str]) -> bytes:
        restored = original_restore(document, source_namespaces=source_namespaces)
        return restored.replace(b"Unchanged text.", b"Unexpected change.")

    monkeypatch.setattr(revised_contract_module, "_restore_ignorable_namespaces", damaged_restore)
    with pytest.raises(
        RevisedContractCandidateError,
        match="revised_contract_post_edit_integrity_failed",
    ):
        render_revised_contract_candidate_docx(source, _view("Change this clause."))


def test_revised_contract_rejects_ambiguous_clause_match() -> None:
    repeated = "5.1. Оплата производится после приёмки."
    source = _source_docx(repeated, repeated)

    with pytest.raises(
        RevisedContractCandidateError,
        match="revised_contract_clause_match_not_unique",
    ):
        render_revised_contract_candidate_docx(source, _view(repeated))


def test_revised_contract_does_not_match_clause_number_inside_another_number() -> None:
    clause = "7.4. Payment follows acceptance."
    source = _source_docx("17.4. Payment follows acceptance.")

    with pytest.raises(
        RevisedContractCandidateError,
        match="revised_contract_clause_match_not_unique",
    ):
        render_revised_contract_candidate_docx(source, _view(clause))


def test_revised_contract_uses_explicit_replacement_source_span() -> None:
    first = "5.5. Документ подписывается Подрядчиком не позднее одного часа."
    continuation = "Датой поступления документа считается дата его размещения."
    source = _source_docx(first, continuation)
    view = _view(f"{first} {continuation}")
    revisions = view["revised_clauses"]
    assert isinstance(revisions, list)
    revisions[0]["replacement_source_text"] = first
    revisions[0]["revised_text"] = (
        "5.5. Заказчик передаёт площадку не позднее пяти рабочих дней; "
        "просрочка продлевает срок выполнения работ."
    )

    revised = render_revised_contract_candidate_docx(source, view)

    assert _paragraphs(revised) == [
        (
            "5.5. Заказчик передаёт площадку не позднее пяти рабочих дней; "
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


def test_revised_contract_preserves_unedited_run_styles_across_split_clause() -> None:
    prefix = "3.4. Предмет: "
    unsafe = "оплата по решению Заказчика"
    suffix = "; остальные условия сохраняются."
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{_WORD_NS}"><w:body><w:p>'
        f"<w:r><w:rPr><w:b/></w:rPr><w:t>{prefix}</w:t></w:r>"
        "<w:r><w:t>оплата по </w:t></w:r>"
        "<w:r><w:t>решению Заказчика</w:t></w:r>"
        f"<w:r><w:rPr><w:i/></w:rPr><w:t>{suffix}</w:t></w:r>"
        "</w:p></w:body></w:document>"
    ).encode()
    source_buffer = io.BytesIO()
    with zipfile.ZipFile(source_buffer, "w") as package:
        _write_minimal_docx_package(package, document)
    view = _view(prefix + unsafe + suffix)
    revisions = view["revised_clauses"]
    assert isinstance(revisions, list)
    revisions[0]["replacement_source_text"] = unsafe
    revisions[0]["revised_text"] = "оплата после приёмки"

    revised = render_revised_contract_candidate_docx(source_buffer.getvalue(), view)

    assert _paragraphs(revised) == [prefix + "оплата после приёмки" + suffix]
    with zipfile.ZipFile(io.BytesIO(revised)) as package:
        root = ET.fromstring(package.read("word/document.xml"))
    runs = list(root.iter(f"{{{_WORD_NS}}}r"))
    assert runs[0].find(f"{{{_WORD_NS}}}rPr/{{{_WORD_NS}}}b") is not None
    assert runs[-1].find(f"{{{_WORD_NS}}}rPr/{{{_WORD_NS}}}i") is not None
    assert "".join(node.text or "" for node in runs[0].iter(f"{{{_WORD_NS}}}t")) == prefix
    assert "".join(node.text or "" for node in runs[-1].iter(f"{{{_WORD_NS}}}t")) == suffix


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
    view["revised_clauses"][0]["revised_text"] = (
        "7.3. Заказчик передаёт площадку не позднее пяти рабочих дней; "
        "просрочка продлевает срок выполнения работ."
    )
    view.update(
        {
            "revised_contracts": [
                {
                    "state": "source_format_supported",
                    "source_contract_version_id": source_id,
                }
            ],
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
    assert _paragraphs(b"".join(candidate.chunks))[1].startswith("7.3.")


def test_product_projection_keeps_ambiguous_source_as_clause_schedule() -> None:
    repeated = "8.4. Оплата производится после подписания акта."
    source_id = "71000000-0000-4000-8000-000000000092"
    view = _view(repeated)
    clauses = view["clauses"]
    assert isinstance(clauses, list)
    clauses[0]["source_version_id"] = source_id
    view.update(
        {
            "revised_contracts": [
                {
                    "state": "source_format_supported",
                    "source_contract_version_id": source_id,
                }
            ],
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


def test_primary_contract_source_uses_broad_governing_clause_semantics() -> None:
    primary_id = "71000000-0000-4000-8000-000000000093"
    attachment_id = "71000000-0000-4000-8000-000000000094"
    sources = [
        {
            "source_version_id": primary_id,
            "safe_display_name": "document-a.docx",
            "media_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        },
        {
            "source_version_id": attachment_id,
            "safe_display_name": "document-b.docx",
            "media_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        },
    ]
    clauses = [
        {"source_version_id": primary_id, "category": category}
        for category in (
            "payment",
            "acceptance",
            "liability",
            "warranty",
            "security",
            "termination",
            "change_procedure",
        )
    ] + [
        {"source_version_id": attachment_id, "category": category}
        for category in ("scope", "contractor_obligation", "liability")
    ]

    selected = _select_primary_revised_contract_source(sources, clauses=clauses)

    assert selected is not None
    assert str(selected["source_version_id"]) == primary_id


def test_primary_contract_source_fails_closed_for_semantically_close_sources() -> None:
    first_id = "71000000-0000-4000-8000-000000000095"
    second_id = "71000000-0000-4000-8000-000000000096"
    sources = [
        {
            "source_version_id": source_id,
            "safe_display_name": f"document-{ordinal}.docx",
            "media_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        }
        for ordinal, source_id in enumerate((first_id, second_id), start=1)
    ]
    clauses = [
        {"source_version_id": source_id, "category": category}
        for source_id in (first_id, second_id)
        for category in ("payment", "acceptance", "liability", "warranty")
    ]

    assert _select_primary_revised_contract_source(sources, clauses=clauses) is None


def test_exact_candidate_changes_only_primary_contract_source_revisions() -> None:
    primary_id = "71000000-0000-4000-8000-000000000097"
    attachment_id = "71000000-0000-4000-8000-000000000098"
    primary_clause = "2.4. Оплата зависит от лимитов финансирования Заказчика."
    attachment_clause = "3.2. Подрядчик предоставляет транспорт для выезда Заказчика."
    view = {
        "clauses": [
            {
                "clause_id": "primary-clause",
                "clause_version": 1,
                "source_version_id": primary_id,
                "source_text": primary_clause,
            },
            {
                "clause_id": "attachment-clause",
                "clause_version": 1,
                "source_version_id": attachment_id,
                "source_text": attachment_clause,
            },
        ],
        "revised_clauses": [
            {
                "source_clause_id": "primary-clause",
                "source_clause_version": 1,
                "revised_text": "2.4. Оплата производится после приёмки выполненных работ.",
            },
            {
                "source_clause_id": "attachment-clause",
                "source_clause_version": 1,
                "revised_text": "3.2. Транспорт предоставляет сторона, инициировавшая выезд.",
            },
        ],
        "revised_contracts": [
            {
                "state": "source_format_supported",
                "source_contract_version_id": primary_id,
                "included_revision_count": 1,
                "external_revision_count": 1,
            }
        ],
        "deliverables": [
            {"deliverable_kind": "revised_contract", "state": "source_format_supported"}
        ],
        "assessment": {
            "sources": [
                {"source_version_id": primary_id, "safe_display_name": "main.docx"},
                {"source_version_id": attachment_id, "safe_display_name": "annex.docx"},
            ]
        },
        "gaps": ["REVISED_CONTRACT_EXCLUDES_NON_PRIMARY_SOURCE_REVISIONS"],
    }
    service = ProductSpineService.__new__(ProductSpineService)
    service._tender_contract_analysis = _ContractProjection(view)  # type: ignore[assignment]
    service._repository = _SourceByIdRepository()  # type: ignore[assignment]
    service._contract_revision_reviews = SimpleNamespace(latest_decisions=lambda **kwargs: [])  # type: ignore[assignment]
    service._object_store = _ObjectStoreByKey(  # type: ignore[assignment]
        {
            primary_id: _source_docx(primary_clause),
            attachment_id: _source_docx(attachment_clause),
        }
    )

    candidate = service.tender_revised_contract_candidate(
        owner_identity_id="owner:changed", workspace_id=UUID(int=75)
    )

    assert _paragraphs(b"".join(candidate.chunks)) == [
        "2.4. Оплата производится после приёмки выполненных работ."
    ]
    projected = service.tender_contract_analysis(
        owner_identity_id="owner:changed", workspace_id=UUID(int=75)
    )
    assert projected["revised_contracts"][0]["package_state"] == ("exact_source_package_available")
    package = service.tender_revised_contract_package(
        owner_identity_id="owner:changed", workspace_id=UUID(int=75)
    )
    assert package.media_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(b"".join(package.chunks))) as archive:
        assert _paragraphs(archive.read("contract-source-01.docx")) == [
            "2.4. Оплата производится после приёмки выполненных работ."
        ]
        assert _paragraphs(archive.read("contract-source-02.docx")) == [
            "3.2. Транспорт предоставляет сторона, инициировавшая выезд."
        ]


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
