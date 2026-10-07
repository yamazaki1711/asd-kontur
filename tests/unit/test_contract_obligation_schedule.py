"""Qwen-extracted obligations remain source-linked in the editable contract report."""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree

from asd_kontur.tender.contract_analysis_report import render_tender_contract_analysis_docx

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def test_contract_report_includes_both_party_obligations_and_source() -> None:
    view = {
        "status": "drafted",
        "process": {"revision": 1},
        "assessment": {"source_coverage": {"incomplete_source_names": []}},
        "clauses": [
            {
                "clause_id": "synthetic-payment",
                "clause_version": 1,
                "clause_key": "5.3",
                "source_text": "Customer pays accepted work after the signed acceptance act.",
                "source_name": "revised-agreement.docx",
                "source_page": 4,
                "customer_obligation": "Pay for accepted work.",
                "contractor_obligation": "Submit an acceptance act.",
                "condition": "Following acceptance.",
            },
            {
                "clause_id": "synthetic-definition",
                "clause_version": 1,
                "clause_key": "1.2",
                "source_text": "Definitions apply throughout the agreement.",
                "source_name": "revised-agreement.docx",
                "source_page": 1,
                "customer_obligation": None,
                "contractor_obligation": None,
            },
        ],
        "attachment_references": [],
        "issues": [],
        "disagreement_items": [],
        "revised_clauses": [],
        "deliverables": [],
        "project_context": {},
        "gaps": [],
    }
    document = render_tender_contract_analysis_docx(view)
    with zipfile.ZipFile(io.BytesIO(document)) as archive:
        assert archive.testzip() is None
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    text = " ".join(node.text or "" for node in root.iter(f"{{{_WORD_NS}}}t"))
    assert "Обязательства сторон и условия исполнения" in text
    assert "Pay for accepted work." in text
    assert "Submit an acceptance act." in text
    assert "Following acceptance." in text
    assert "revised-agreement.docx" in text
    assert (
        "Definitions apply throughout the agreement."
        not in text.split("Обязательства сторон и условия исполнения", 1)[1].split(
            "Ключевые условия договора и закупки", 1
        )[0]
    )
