from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from pypdf import PdfWriter

from asd_kontur.support.editable_aosr import (
    EDITABLE_AOSR_PAGE_COUNT,
    build_editable_aosr_template,
    field_keys,
    qualify_editable_aosr_template,
    validate_editable_aosr_template,
    validate_generated_editable_aosr,
)
from asd_kontur.support.models import FieldResolution, ResolutionState
from asd_kontur.support.production import TemplateBackedDocxRenderer


def _confirmed(key: str) -> FieldResolution:
    return FieldResolution(
        field_key=key,
        state=ResolutionState.CONFIRMED,
        normalized_value=f"value:{key}",
        display_value=f"Значение {key}",
        fact_id=uuid4(),
        fact_version=1,
        evidence_link_ids=(uuid4(),),
        source_locator_ids=(uuid4(),),
        material=True,
    )


def test_editable_aosr_template_has_all_bindings_and_four_page_sections() -> None:
    payload = build_editable_aosr_template()

    checks = validate_editable_aosr_template(payload)

    assert "EDITABLE_TEXT_BINDINGS_COMPLETE" in checks
    with zipfile.ZipFile(io.BytesIO(payload)) as package:
        document = package.read("word/document.xml").decode("utf-8")
    assert document.count('w:type="page"') == EDITABLE_AOSR_PAGE_COUNT - 1
    assert all(document.count("{{" + key + "}}") == 1 for key in field_keys())


def test_editable_aosr_renders_confirmed_values_without_unresolved_tokens() -> None:
    template = build_editable_aosr_template()
    fields = tuple(_confirmed(key) for key in field_keys())

    result = TemplateBackedDocxRenderer().render(
        template_bytes=template,
        template_digest="sha256:" + hashlib.sha256(template).hexdigest(),
        fields=fields,
        semantic_input={"work_type_key": "concrete.slab.install"},
    )

    checks = validate_editable_aosr_template(result.package_bytes, tokens_expected=False)
    assert "FIELD_BINDINGS_RESOLVED" in checks
    with zipfile.ZipFile(io.BytesIO(result.package_bytes)) as package:
        document = package.read("word/document.xml").decode("utf-8")
    assert "Значение hidden_work_description" in document
    assert "{{" not in document


def test_editable_aosr_qualification_fails_closed_without_converter(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="editable_aosr_converter_unavailable"):
        qualify_editable_aosr_template(
            template_bytes=build_editable_aosr_template(),
            official_profile_fingerprint="sha256:" + "1" * 64,
            official_source_digest="sha256:" + "2" * 64,
            converter_path=tmp_path / "missing-converter",
        )


def test_generated_editable_aosr_allows_content_to_expand_beyond_form_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = build_editable_aosr_template()
    fields = tuple(_confirmed(key) for key in field_keys())
    generated = TemplateBackedDocxRenderer().render(
        template_bytes=template,
        template_digest="sha256:" + hashlib.sha256(template).hexdigest(),
        fields=fields,
        semantic_input={"work_type_key": "concrete.slab.install"},
    )
    rendered = io.BytesIO()
    writer = PdfWriter()
    for _ in range(EDITABLE_AOSR_PAGE_COUNT + 1):
        writer.add_blank_page(width=595, height=842)
    writer.write(rendered)
    monkeypatch.setattr(
        "asd_kontur.support.editable_aosr._convert_to_pdf",
        lambda *_args: rendered.getvalue(),
    )

    receipt = validate_generated_editable_aosr(
        document_bytes=generated.package_bytes,
        expected_values={},
        converter_path=tmp_path / "controlled-converter",
    )

    assert receipt.page_count == EDITABLE_AOSR_PAGE_COUNT + 1
    assert "A4_FORM_MINIMUM_PAGES_RENDERED" in receipt.check_codes
