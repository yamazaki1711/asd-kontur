from __future__ import annotations

from uuid import UUID

import pytest

from asd_kontur.ntd.models import NormativeProvisionKind
from asd_kontur.ntd.parsing import extract_native_pdf


class SyntheticLayoutRunner:
    def extract(self, content: bytes) -> bytes:
        assert content.startswith(b"%PDF-")
        return b"""<?xml version='1.0' encoding='UTF-8'?>
        <html xmlns='http://www.w3.org/1999/xhtml'><body><doc>
          <page width='420' height='595'>
            <flow><block><line>
              <word xMin='50' yMin='60' xMax='60' yMax='70'>7.2</word>
              <word xMin='65' yMin='60' xMax='120' yMax='70'>Synthetic</word>
              <word xMin='125' yMin='60' xMax='180' yMax='70'>provision</word>
            </line></block></flow>
          </page>
          <page width='420' height='595'><flow><block><line>
            <word xMin='50' yMin='60' xMax='55' yMax='70'>x</word>
          </line></block></flow></page>
        </doc></body></html>"""


def test_native_pdf_extraction_creates_candidates_and_marks_raster_fallback() -> None:
    result = extract_native_pdf(
        content=b"%PDF-1.7\nsynthetic",
        normative_edition_id=UUID("3c5947b0-c67d-4fa7-ae43-57c0067a2498"),
        source_version_id=UUID("b62c0408-71dd-410d-a416-e28b0e55d459"),
        runner=SyntheticLayoutRunner(),
    )

    assert result.page_count == 2
    assert len(result.candidates) == 1
    assert result.candidates[0].structural_path == "7.2"
    assert result.candidates[0].provision_kind is NormativeProvisionKind.CLAUSE
    assert result.candidates[0].model_provenance is None
    assert result.pages_requiring_ocr == (2,)
    assert result.extraction_fingerprint.startswith("sha256:")


def test_native_pdf_rejects_invalid_signature_before_parser() -> None:
    with pytest.raises(ValueError, match="PDF_SIGNATURE"):
        extract_native_pdf(
            content=b"not-pdf",
            normative_edition_id=UUID("3c5947b0-c67d-4fa7-ae43-57c0067a2498"),
            source_version_id=UUID("b62c0408-71dd-410d-a416-e28b0e55d459"),
            runner=SyntheticLayoutRunner(),
        )
