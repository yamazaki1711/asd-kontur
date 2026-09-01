# ruff: noqa: RUF001 - Russian construction fixtures intentionally use Cyrillic markings.

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from asd_kontur.document_understanding.models import (
    CandidateDecision,
    DocumentRole,
    OcrRoute,
    PageHealthKind,
)
from asd_kontur.document_understanding.native import (
    NativeExtractionFailure,
    _group_pdf_lines,
    _pdf_reader_document,
    analyze_page_health,
    inspect_and_extract,
)
from asd_kontur.document_understanding.semantic import (
    classify_pages,
    extract_structured_candidates,
    parse_exact_decimal,
)

DOCUMENT_ID = UUID("10000000-0000-4000-8000-000000000001")
SOURCE_VERSION_ID = UUID("20000000-0000-4000-8000-000000000001")


def _extract_csv(value: str):
    return inspect_and_extract(
        content=value.encode("utf-8"),
        media_type="text/csv",
        document_id=DOCUMENT_ID,
        document_version=1,
        source_version_id=SOURCE_VERSION_ID,
    )


def test_csv_native_pipeline_preserves_printed_numbers_units_and_cell_locators() -> None:
    document = _extract_csv(
        "Ведомость объёмов работ;;;;;\n"
        "Вид работ;Объём;Ед. изм.;Материал;Количество материала;Ед. изм. материала\n"
        "Устройство монолитной плиты;+12,350;м³;Бетон В25;12,350;м³\n"
    )

    page = document.pages[0]
    assert document.format_kind == "csv"
    assert page.health.primary_kind is PageHealthKind.TABLE_HEAVY
    assert page.health.route is OcrRoute.NOT_REQUIRED
    assert all(item.locator.cell is not None for item in page.elements)

    classification = classify_pages(page.elements)
    selected_roles = {
        role for decision in classification.decisions for role in decision.selected_roles
    }
    assert DocumentRole.BILL_OF_QUANTITIES in selected_roles

    structured = extract_structured_candidates(page.elements, classification.decisions)
    assert len(structured.works) == 1
    assert structured.works[0].raw_name == "Устройство монолитной плиты"
    assert structured.works[0].canonical_mapping_status.value == "unresolved"
    assert len(structured.quantities) == 1
    quantity = structured.quantities[0]
    assert quantity.raw_value == "+12,350"
    assert quantity.parsed_value == Decimal("12.350")
    assert quantity.raw_unit == "м³"
    assert quantity.normalized_unit == "m3"
    assert quantity.status is CandidateDecision.VERIFIED
    assert len(structured.materials) == 1
    material = structured.materials[0]
    assert material.raw_name == "Бетон В25"
    assert material.raw_quantity == "12,350"
    assert material.parsed_quantity == Decimal("12.350")
    assert material.raw_unit == "м³"


def test_content_not_filename_drives_role_and_unknown_is_explicit() -> None:
    document = _extract_csv("произвольный заголовок\nданные без классификационного сигнала\n")

    classification = classify_pages(document.pages[0].elements)

    assert len(classification.decisions) == 1
    assert classification.decisions[0].selected_roles == (DocumentRole.UNKNOWN,)
    assert classification.candidates[0].signal_codes == ("content:no_content_role_signal",)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+12,350", Decimal("12.350")),
        ("-0.025", Decimal("-0.025")),
        ("1 234,50", Decimal("1234.50")),
        ("12,3.5", None),
        ("12 м³", None),
        ("Ø12", None),
        ("", None),
    ],
)
def test_numeric_normalization_is_exact_and_fail_closed(raw: str, expected: Decimal | None) -> None:
    assert parse_exact_decimal(raw) == expected


def test_page_health_routes_sparse_image_and_damaged_text_to_ocr() -> None:
    sparse = analyze_page_health(
        document_id=DOCUMENT_ID,
        document_version=1,
        page_number=1,
        text="Штамп",
        image_count=1,
        width_points=Decimal("595"),
        height_points=Decimal("842"),
        rotation_degrees=90,
    )
    damaged = analyze_page_health(
        document_id=DOCUMENT_ID,
        document_version=1,
        page_number=2,
        text="abc\ufffd\ufffd",
        image_count=0,
        width_points=Decimal("595"),
        height_points=Decimal("842"),
        rotation_degrees=0,
    )

    assert sparse.primary_kind is PageHealthKind.EXISTING_OCR
    assert sparse.route is OcrRoute.APPLE_VISION
    assert sparse.rotation_degrees == 90
    assert damaged.primary_kind is PageHealthKind.DAMAGED_ENCODING
    assert damaged.route is OcrRoute.APPLE_VISION


def test_page_health_rejects_mixed_script_ocr_garble() -> None:
    damaged = analyze_page_health(
        document_id=DOCUMENT_ID,
        document_version=1,
        page_number=3,
        text="строитЕльствА ижилищно-комlчtунАльного х|tппстЕрсrп0",
        image_count=1,
        width_points=Decimal("595"),
        height_points=Decimal("842"),
        rotation_degrees=0,
    )

    assert damaged.primary_kind is PageHealthKind.DAMAGED_ENCODING
    assert damaged.route is OcrRoute.APPLE_VISION
    assert damaged.signals == ("mixed_script_ocr_garble_high",)


def test_page_health_detects_cyrillic_utf8_mojibake() -> None:
    mojibake_sample = "ÐÑÐ¸ÐºÐ°Ð· " * 10
    damaged = analyze_page_health(
        document_id=DOCUMENT_ID,
        document_version=1,
        page_number=4,
        text=mojibake_sample,
        image_count=0,
        width_points=Decimal("595"),
        height_points=Decimal("842"),
        rotation_degrees=0,
    )

    assert damaged.primary_kind is PageHealthKind.DAMAGED_ENCODING
    assert damaged.route is OcrRoute.APPLE_VISION
    assert damaged.signals == ("cyrillic_utf8_mojibake_high",)


def test_pdf_line_grouping_recovers_unanchored_continuation_fragments() -> None:
    lines = _group_pdf_lines(
        [
            ("СВОД", 79.8, 657.2, 11.0, "Test"),
            (" ПРАВИЛ", 0.0, 0.0, 1.0, "Test"),
            (" СП", 0.0, 0.0, 1.0, "Test"),
            (" 543", 0.0, 0.0, 1.0, "Test"),
            (".1325800.2024", 462.7, 657.2, 11.0, "Test"),
            ("1.1 ", 113.4, 560.4, 10.0, "Test"),
            ("Настоящий", 136.3, 560.4, 10.0, "Test"),
            ("свод", 209.5, 560.4, 10.0, "Test"),
        ]
    )

    assert [line[0] for line in lines] == [
        "СВОД ПРАВИЛ СП 543 .1325800.2024",
        "1.1 Настоящий свод",
    ]


def test_pdf_unknown_font_encoding_is_page_scoped_damaged_native() -> None:
    class _Box:
        left = 0
        right = 595
        bottom = 0
        top = 842

    class _Page:
        cropbox = _Box()
        rotation = 0

        def extract_text(self, **_kwargs: object) -> str:
            raise LookupError("unknown encoding: /SymbolSetEncoding")

        def get(self, _key: str) -> None:
            return None

    class _Reader:
        pages = (_Page(),)

    document = _pdf_reader_document(_Reader(), DOCUMENT_ID, 1, SOURCE_VERSION_ID)  # type: ignore[arg-type]

    page = document.pages[0]
    assert page.elements == ()
    assert page.parser_observations == ("native_text_encoding_unresolved",)
    assert page.health.primary_kind is PageHealthKind.DAMAGED_ENCODING
    assert page.health.route is OcrRoute.APPLE_VISION
    assert page.health.signals == ("native_parser:native_text_encoding_unresolved",)


def test_unsupported_format_is_typed_failure() -> None:
    with pytest.raises(NativeExtractionFailure, match="document_format_not_supported") as error:
        inspect_and_extract(
            content=b"not-a-qualified-format",
            media_type="application/octet-stream",
            document_id=DOCUMENT_ID,
            document_version=1,
            source_version_id=SOURCE_VERSION_ID,
        )

    assert error.value.code == "document_format_not_supported"
