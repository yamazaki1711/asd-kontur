# ruff: noqa: RUF001 - Russian construction fixtures intentionally use Cyrillic markings.

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import Engine

from asd_kontur.application_spine.models import ClaimedJob, JobKind
from asd_kontur.assistant.qwen_server import _collect_generated_text
from asd_kontur.document_understanding import ocr
from asd_kontur.document_understanding.models import (
    CandidateDecision,
    DocumentRole,
    EstimatePositionCandidate,
    ExactLocator,
    LayoutElement,
    MaterialCandidate,
    OcrRoute,
    PageHealthKind,
    QuantityCandidate,
    ReconciliationDefectKind,
    StructureIdentityCandidate,
    WorkTypeCandidate,
)
from asd_kontur.document_understanding.native import (
    NativeExtractionFailure,
    _group_pdf_lines,
    _pdf_reader_document,
    analyze_page_health,
    inspect_and_extract,
)
from asd_kontur.document_understanding.ocr import OcrAdapterResult, QwenVisionOcrAdapter
from asd_kontur.document_understanding.pipeline import IndustrialDocumentUnderstandingPipeline
from asd_kontur.document_understanding.postgres import IndustrialUnderstandingRepository
from asd_kontur.document_understanding.qwen_semantic import (
    QwenDocumentSemanticAdapter,
    QwenSemanticFailure,
    _compatible_batch_digest,
    _engineering_batches,
    _fragments,
    _split_engineering_batch,
)
from asd_kontur.document_understanding.semantic import (
    StructuredCandidates,
    classify_pages,
    extract_structured_candidates,
    parse_exact_decimal,
    reconcile_sources,
)
from asd_kontur.document_understanding.work_packages import consolidate_work_package_candidates
from asd_kontur.domain import deterministic_uuid

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


def _locator(*, page_number: int) -> ExactLocator:
    return ExactLocator(
        SOURCE_VERSION_ID,
        deterministic_uuid(f"test-locator:{page_number}"),
        DOCUMENT_ID,
        1,
        page_number,
        (0.0, 0.0, 1.0, 1.0),
        "sha256:" + "e" * 64,
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


def test_work_package_consolidation_preserves_scope_and_does_not_sum_conflicts() -> None:
    source_a = "20000000-0000-4000-8000-000000000001"
    source_b = "20000000-0000-4000-8000-000000000002"
    works = (
        {
            "candidate_id": "work-a-1",
            "source_role": "project_documentation",
            "source_version_id": source_a,
            "source_locator_id": "locator-a-1",
            "scope_key": "facility:los-1",
            "normalized_name": "устройство котлована",
            "raw_name": "Устройство котлована",
            "canonical_mapping_status": "unresolved",
            "canonical_work_type_id": None,
        },
        {
            "candidate_id": "work-a-2",
            "source_role": "project_documentation",
            "source_version_id": source_a,
            "source_locator_id": "locator-a-2",
            "scope_key": "facility:los-1",
            "normalized_name": "устройство котлована",
            "raw_name": "Устройство котлована",
            "canonical_mapping_status": "unresolved",
            "canonical_work_type_id": None,
        },
        {
            "candidate_id": "work-b-1",
            "source_role": "project_documentation",
            "source_version_id": source_b,
            "source_locator_id": "locator-b-1",
            "scope_key": "facility:kns-1",
            "normalized_name": "устройство котлована",
            "raw_name": "Устройство котлована",
            "canonical_mapping_status": "unresolved",
            "canonical_work_type_id": None,
        },
    )
    quantities = (
        {"work_candidate_id": "work-a-1", "normalized_value": "12", "normalized_unit": "m3"},
        {"work_candidate_id": "work-a-2", "normalized_value": "15", "normalized_unit": "m3"},
    )
    packages = consolidate_work_package_candidates(works, quantities, ())

    assert len(packages) == 2
    los = next(item for item in packages if item["scope_key"] == "facility:los-1")
    assert len(los["observations"]) == 2
    assert len(los["quantities"]) == 2
    assert "QUANTITY_OBSERVATIONS_CONFLICT" in los["uncertainties"]
    assert "SAME_WORK_NAME_DIFFERENT_SCOPE" in los["uncertainties"]
    kns = next(item for item in packages if item["scope_key"] == "facility:kns-1")
    assert len(kns["observations"]) == 1


def test_materialization_digest_changes_when_accepted_candidate_changes() -> None:
    empty = IndustrialUnderstandingRepository._materialization_input_digest(
        fields=[],
        works=[],
        quantities=[],
        materials=[],
        structures=[],
        relationships=[],
        defects=[],
    )
    one = IndustrialUnderstandingRepository._materialization_input_digest(
        fields=[{"candidate_id": "field-1", "version": 1, "candidate_digest": "sha256:one"}],
        works=[],
        quantities=[],
        materials=[],
        structures=[],
        relationships=[],
        defects=[],
    )
    reordered = IndustrialUnderstandingRepository._materialization_input_digest(
        fields=[
            {"candidate_id": "field-2", "version": 1, "candidate_digest": "sha256:two"},
            {"candidate_id": "field-1", "version": 1, "candidate_digest": "sha256:one"},
        ],
        works=[],
        quantities=[],
        materials=[],
        structures=[],
        relationships=[],
        defects=[],
    )
    reversed_rows = IndustrialUnderstandingRepository._materialization_input_digest(
        fields=[
            {"candidate_id": "field-1", "version": 1, "candidate_digest": "sha256:one"},
            {"candidate_id": "field-2", "version": 1, "candidate_digest": "sha256:two"},
        ],
        works=[],
        quantities=[],
        materials=[],
        structures=[],
        relationships=[],
        defects=[],
    )

    assert empty != one
    assert reordered == reversed_rows


def test_reconciliation_does_not_claim_each_project_work_is_missing_without_estimate_input() -> (
    None
):
    document = _extract_csv(
        "Ведомость объёмов работ;;;;;\n"
        "Вид работ;Объём;Ед. изм.;Материал;Количество материала;Ед. изм. материала\n"
        "Устройство котлована;12;м³;Бетон В25;12;м³\n"
        "Устройство основания;5;м³;Щебень;5;м³\n"
    )
    classified = classify_pages(document.pages[0].elements)
    extracted = extract_structured_candidates(document.pages[0].elements, classified.decisions)
    defects = reconcile_sources(extracted.works, extracted.quantities, extracted.materials, ())

    assert len(defects) == 1
    assert defects[0].kind is ReconciliationDefectKind.ESTIMATE_COMPARISON_INPUT_UNAVAILABLE
    assert (
        defects[0].parameters["missing_input"] == "parsed_estimate_or_bill_of_quantities_positions"
    )


def test_reconciliation_requires_unique_work_and_estimate_identity_before_matching() -> None:
    locator = _locator(page_number=1)
    estimate_locator = _locator(page_number=2)
    works = (
        WorkTypeCandidate(
            deterministic_uuid("work:los"),
            "Устройство котлована",
            "устройство котлована",
            "facility:los-1",
            locator,
            DocumentRole.PROJECT_DOCUMENTATION,
        ),
        WorkTypeCandidate(
            deterministic_uuid("work:kns"),
            "Устройство котлована",
            "устройство котлована",
            "facility:kns-1",
            _locator(page_number=3),
            DocumentRole.PROJECT_DOCUMENTATION,
        ),
    )
    estimate = EstimatePositionCandidate(
        deterministic_uuid("estimate:pit"),
        "1",
        "устройство котлована",
        "12",
        Decimal("12"),
        "м3",
        estimate_locator,
    )

    defects = reconcile_sources(works, (), (), (estimate,))

    assert [item.kind for item in defects] == [
        ReconciliationDefectKind.AMBIGUOUS_SOURCE_MATCH,
        ReconciliationDefectKind.AMBIGUOUS_SOURCE_MATCH,
    ]
    assert all(
        item.parameters["code"] == "multiple_project_work_observations_with_same_normalized_name"
        for item in defects
    )
    assert all(estimate.candidate_id.hex not in item.subject_identity for item in defects)


def test_reconciliation_does_not_claim_material_absent_without_estimate_resource_evidence() -> None:
    work = WorkTypeCandidate(
        deterministic_uuid("work:concrete"),
        "Устройство плиты",
        "устройство плиты",
        "facility:los-1",
        _locator(page_number=1),
        DocumentRole.PROJECT_DOCUMENTATION,
    )
    quantity = QuantityCandidate(
        deterministic_uuid("quantity:concrete"),
        work.candidate_id,
        "12",
        Decimal("12"),
        "м3",
        Decimal("12"),
        "m3",
        "unit-aliases@1",
        work.scope_key,
        _locator(page_number=1),
        CandidateDecision.VERIFIED,
    )
    material = MaterialCandidate(
        deterministic_uuid("material:concrete"),
        work.candidate_id,
        "Бетон В25",
        "бетон в25",
        "12",
        Decimal("12"),
        "м3",
        "m3",
        _locator(page_number=1),
        CandidateDecision.CANDIDATE,
    )
    estimate = EstimatePositionCandidate(
        deterministic_uuid("estimate:concrete"),
        "1",
        "устройство плиты",
        "13",
        Decimal("13"),
        "м3",
        _locator(page_number=2),
    )

    defects = reconcile_sources((work,), (quantity,), (material,), (estimate,))

    assert {item.kind for item in defects} == {
        ReconciliationDefectKind.QUANTITY_MISMATCH,
        ReconciliationDefectKind.ESTIMATE_MATERIAL_COMPARISON_INPUT_UNAVAILABLE,
    }
    material_gap = next(
        item
        for item in defects
        if item.kind is ReconciliationDefectKind.ESTIMATE_MATERIAL_COMPARISON_INPUT_UNAVAILABLE
    )
    assert (
        material_gap.parameters["missing_input"] == "parsed_estimate_material_or_resource_positions"
    )


def test_reconciliation_uses_exact_estimate_work_locator_for_material_comparison() -> None:
    project_work = WorkTypeCandidate(
        deterministic_uuid("work:project:concrete"),
        "Устройство плиты",
        "устройство плиты",
        "facility:los-1",
        _locator(page_number=1),
        DocumentRole.PROJECT_DOCUMENTATION,
    )
    estimate_locator = _locator(page_number=2)
    estimate_work = WorkTypeCandidate(
        deterministic_uuid("work:estimate:concrete"),
        "Устройство плиты",
        "устройство плиты",
        "estimate:1",
        estimate_locator,
        DocumentRole.LOCAL_ESTIMATE,
    )
    project_material = MaterialCandidate(
        deterministic_uuid("material:project:concrete"),
        project_work.candidate_id,
        "Бетон В25",
        "бетон в25",
        None,
        None,
        None,
        None,
        _locator(page_number=1),
        CandidateDecision.CANDIDATE,
    )
    estimate_resource = MaterialCandidate(
        deterministic_uuid("material:estimate:concrete"),
        estimate_work.candidate_id,
        "Бетон В25",
        "бетон в25",
        None,
        None,
        None,
        None,
        estimate_locator,
        CandidateDecision.CANDIDATE,
    )
    estimate = EstimatePositionCandidate(
        deterministic_uuid("estimate:concrete:position"),
        "1",
        "устройство плиты",
        None,
        None,
        None,
        estimate_locator,
    )

    assert (
        reconcile_sources(
            (project_work, estimate_work), (), (project_material, estimate_resource), (estimate,)
        )
        == ()
    )


def test_reconciliation_reports_material_quantity_delta_only_after_exact_resource_match() -> None:
    project_work = WorkTypeCandidate(
        deterministic_uuid("work:project:steel"),
        "Монтаж каркаса",
        "монтаж каркаса",
        "facility:los-1",
        _locator(page_number=4),
        DocumentRole.PROJECT_DOCUMENTATION,
    )
    estimate_locator = _locator(page_number=5)
    estimate_work = WorkTypeCandidate(
        deterministic_uuid("work:estimate:steel"),
        "Монтаж каркаса",
        "монтаж каркаса",
        "estimate:2",
        estimate_locator,
        DocumentRole.LOCAL_ESTIMATE,
    )
    project_material = MaterialCandidate(
        deterministic_uuid("material:project:steel"),
        project_work.candidate_id,
        "Сталь С245",
        "сталь с245",
        "12",
        Decimal("12"),
        "т",
        "t",
        _locator(page_number=4),
        CandidateDecision.VERIFIED,
    )
    estimate_resource = MaterialCandidate(
        deterministic_uuid("material:estimate:steel"),
        estimate_work.candidate_id,
        "Сталь С245",
        "сталь с245",
        "10",
        Decimal("10"),
        "т",
        "t",
        estimate_locator,
        CandidateDecision.VERIFIED,
    )
    estimate = EstimatePositionCandidate(
        deterministic_uuid("estimate:steel:position"),
        "2",
        "монтаж каркаса",
        None,
        None,
        None,
        estimate_locator,
    )

    defects = reconcile_sources(
        (project_work, estimate_work), (), (project_material, estimate_resource), (estimate,)
    )

    assert len(defects) == 1
    assert defects[0].kind is ReconciliationDefectKind.MATERIAL_QUANTITY_MISMATCH
    assert defects[0].parameters == {
        "material": "Сталь С245",
        "project": "12",
        "estimate": "10",
        "unit": "t",
    }


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
    assert sparse.route is OcrRoute.QWEN_VISION
    assert sparse.rotation_degrees == 90
    assert damaged.primary_kind is PageHealthKind.DAMAGED_ENCODING
    assert damaged.route is OcrRoute.QWEN_VISION


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
    assert damaged.route is OcrRoute.QWEN_VISION
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
    assert damaged.route is OcrRoute.QWEN_VISION
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
    assert page.health.route is OcrRoute.QWEN_VISION
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


def test_pdf_renderer_uses_known_local_location_when_launchd_path_is_restricted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = Path("/opt/homebrew/bin/pdftoppm")

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(ocr, "_PDFTOPPM_FALLBACKS", (candidate,))
    monkeypatch.setattr(Path, "is_file", lambda self: self == candidate)
    monkeypatch.setattr(Path, "stat", lambda self: type("Stat", (), {"st_mode": 0o755})())

    assert ocr._pdf_renderer() == str(candidate)


def test_tesseract_uses_known_local_location_when_launchd_path_is_restricted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = Path("/opt/homebrew/bin/tesseract")

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(ocr, "_TESSERACT_FALLBACKS", (candidate,))
    monkeypatch.setattr(Path, "is_file", lambda self: self == candidate)
    monkeypatch.setattr(Path, "stat", lambda self: type("Stat", (), {"st_mode": 0o755})())

    adapter = ocr.TesseractOcrAdapter()
    assert adapter.available() is True
    assert adapter._resolved_executable() == str(candidate)


def test_qwen_vision_result_is_validated_with_exact_page_locator(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"bounded-image-bytes")

    result = QwenVisionOcrAdapter("http://127.0.0.1:8790/vision")._parse_result(
        '{"observations":[{"text":"Котлован № 1","region":[0,0,1,1]}]}',
        image,
        document_id=DOCUMENT_ID,
        document_version=1,
        source_version_id=SOURCE_VERSION_ID,
        page_number=7,
    )

    assert result.adapter_key == "qwen3.8-27b-local-vision"
    assert result.elements[0].locator.page_number == 7
    assert result.elements[0].locator.source_version_id == SOURCE_VERSION_ID


def test_qwen_vision_accepts_one_complete_json_object_in_model_prose(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"bounded-image-bytes")

    result = QwenVisionOcrAdapter("http://127.0.0.1:8790/vision")._parse_result(
        'Результат распознавания: {"observations":[{"text":"Котлован № 1","region":[0,0,1,1]}]}',
        image,
        document_id=DOCUMENT_ID,
        document_version=1,
        source_version_id=SOURCE_VERSION_ID,
        page_number=7,
    )

    assert result.elements[0].raw_text == "Котлован № 1"


def test_qwen_vision_validates_root_text_with_page_scope(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"bounded-image-bytes")

    result = QwenVisionOcrAdapter("http://127.0.0.1:8790/vision")._parse_result(
        '{"text":"Котлован № 1"}',
        image,
        document_id=DOCUMENT_ID,
        document_version=1,
        source_version_id=SOURCE_VERSION_ID,
        page_number=7,
    )

    assert result.elements[0].raw_text == "Котлован № 1"
    assert result.elements[0].locator.region == (0.0, 0.0, 1.0, 1.0)


def test_qwen_vision_response_collects_all_mlx_stream_segments() -> None:
    class Segment:
        def __init__(self, text: str) -> None:
            self.text = text

    assert _collect_generated_text((Segment('{"observations":['), Segment("]}"))) == (
        '{"observations":[]}'
    )


def test_qwen_vision_ocr_uses_bounded_page_generation_budget(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    captured: dict[str, object] = {}

    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _size: int) -> bytes:
            return '{"text":"{\\"observations\\":[\\"Котлован № 1\\"]}"}'.encode()

    def open_request(request: Any, *, timeout: float) -> Response:
        captured["payload"] = request.data
        captured["timeout"] = timeout
        return Response()

    adapter = QwenVisionOcrAdapter("http://127.0.0.1:8790/vision")
    with patch("asd_kontur.document_understanding.ocr.urllib.request.urlopen", open_request):
        result = adapter.extract(
            image,
            document_id=DOCUMENT_ID,
            document_version=1,
            source_version_id=SOURCE_VERSION_ID,
            page_number=1,
        )

    assert json.loads(cast(bytes, captured["payload"]))["max_tokens"] == 800
    assert captured["timeout"] == 600.0
    assert result.adapter_version == "qwen-vision-ocr-v3"


def test_ocr_locator_retry_is_idempotent_by_deterministic_locator_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_calls: list[tuple[str, dict[str, Any]]] = []

    class RecordingSession:
        def execute(self, statement: Any, parameters: dict[str, Any]) -> None:
            recorded_calls.append((str(statement), parameters))

    @contextmanager
    def recording_session(_claimed: ClaimedJob) -> Iterator[RecordingSession]:
        yield RecordingSession()

    repository = IndustrialUnderstandingRepository(cast(Engine, object()))
    monkeypatch.setattr(repository, "_session", recording_session)
    claimed = ClaimedJob(
        UUID("30000000-0000-4000-8000-000000000001"),
        UUID("40000000-0000-4000-8000-000000000001"),
        UUID("50000000-0000-4000-8000-000000000001"),
        JobKind.OCR_EXTRACTION,
        {
            "document_id": str(DOCUMENT_ID),
            "document_version": 1,
            "source_version_id": str(SOURCE_VERSION_ID),
        },
        "sha256:" + "a" * 64,
        1,
        1,
        "none",
    )
    locator = ExactLocator(
        SOURCE_VERSION_ID,
        UUID("60000000-0000-4000-8000-000000000001"),
        DOCUMENT_ID,
        1,
        1,
        (0.0, 0.0, 1.0, 1.0),
        "sha256:" + "b" * 64,
    )
    result = OcrAdapterResult(
        "apple_vision",
        "apple-vision-ocr-v1",
        "rus+eng",
        (
            LayoutElement(
                UUID("70000000-0000-4000-8000-000000000001"), "ocr_word", "К-1", "к-1", 1, locator
            ),
        ),
        "sha256:" + "c" * 64,
        "sha256:" + "d" * 64,
    )

    repository.persist_ocr_result(claimed, page_number=1, result=result)

    locator_sql, locator_parameters = recorded_calls[1]
    assert "ON CONFLICT DO NOTHING" in locator_sql
    assert (
        locator_parameters["key"] == f"understanding:ocr:apple_vision:{locator.source_locator_id}"
    )


def test_ocr_retry_does_not_resend_pages_already_completed_by_qwen() -> None:
    class Repository:
        def load_ocr_routes(self, _claimed: ClaimedJob) -> tuple[tuple[int, str], ...]:
            return ((1, OcrRoute.QWEN_VISION.value),)

        def load_completed_ocr_pages(
            self, _claimed: ClaimedJob, *, adapter_key: str
        ) -> frozenset[int]:
            assert adapter_key == "qwen3.8-27b-local-vision"
            return frozenset({1})

    class QwenAdapter:
        adapter_key = "qwen3.8-27b-local-vision"

    claimed = ClaimedJob(
        UUID("30000000-0000-4000-8000-000000000001"),
        UUID("40000000-0000-4000-8000-000000000001"),
        UUID("50000000-0000-4000-8000-000000000001"),
        JobKind.OCR_EXTRACTION,
        {
            "document_id": str(DOCUMENT_ID),
            "document_version": 1,
            "source_version_id": str(SOURCE_VERSION_ID),
            "media_type": "image/png",
        },
        "sha256:" + "a" * 64,
        1,
        1,
        "none",
    )
    pipeline = IndustrialDocumentUnderstandingPipeline(
        cast(IndustrialUnderstandingRepository, Repository()),
        qwen_vision=cast(QwenVisionOcrAdapter, QwenAdapter()),
    )

    result = pipeline._ocr(claimed, BytesIO(b"already-completed-image-is-not-read"))

    assert result == {
        "routed_page_count": 1,
        "extracted_page_count": 0,
        "already_complete_page_count": 1,
        "blocked_pages": [],
        "results": [],
    }


def test_qwen_semantic_classification_accepts_only_returned_evidence_locators() -> None:
    document = _extract_csv("Пояснительная записка\\nНазначение объекта: насосная станция\\n")
    locator_id = str(document.pages[0].elements[0].locator.source_locator_id)
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=json.dumps(
            {"roles": ["explanatory_note"], "locator_ids": [locator_id]}, ensure_ascii=False
        ),
    ):
        result = adapter.classify(document.pages[0].elements)

    assert result.candidates[0].role is DocumentRole.EXPLANATORY_NOTE
    assert result.candidates[0].locators[0].source_locator_id == UUID(locator_id)
    assert result.decisions[0].decision_code == "qwen_bounded_document_semantic"


def test_qwen_semantic_classification_accepts_one_json_object_wrapped_by_model_text() -> None:
    document = _extract_csv("Пояснительная записка\\n")
    locator_id = str(document.pages[0].elements[0].locator.source_locator_id)
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=(
            "Результат:\\n"
            + json.dumps(
                {"roles": ["explanatory_note"], "locator_ids": [locator_id]},
                ensure_ascii=False,
            )
            + "\\nГотово."
        ),
    ):
        result = adapter.classify(document.pages[0].elements)

    assert result.candidates[0].locators[0].source_locator_id == UUID(locator_id)


def test_qwen_semantic_classification_rejects_hallucinated_locator() -> None:
    document = _extract_csv("Пояснительная записка\\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    with (
        patch(
            "asd_kontur.document_understanding.qwen_semantic._complete",
            return_value='{"roles":["explanatory_note"],"locator_ids":["missing"]}',
        ),
        pytest.raises(QwenSemanticFailure, match="qwen_semantic_response_invalid_locator"),
    ):
        adapter.classify(document.pages[0].elements)


def test_qwen_structure_extraction_requires_exact_locator() -> None:
    document = _extract_csv("Котлован К-1 расположен у насосной станции\n")
    locator_id = str(document.pages[0].elements[0].locator.source_locator_id)
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=json.dumps(
            {
                "structures": [
                    {"kind": "excavation_pit", "name": "Котлован К-1", "locator_id": locator_id}
                ]
            },
            ensure_ascii=False,
        ),
    ):
        result = adapter.extract_structures(document.pages[0].elements)

    assert len(result) == 1
    assert result[0].node_kind == "excavation_pit"
    assert result[0].locator.source_locator_id == UUID(locator_id)


def test_qwen_engineering_extraction_resolves_work_references_across_batches() -> None:
    document = _extract_csv(
        "\n".join(f"строка {index};значение {index}" for index in range(1, 15)) + "\n"
    )
    elements = document.pages[0].elements
    assert len(elements) > 24
    last_locator_id = str(elements[-1].locator.source_locator_id)
    batches = _engineering_batches(elements)
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    responses = [
        json.dumps(
            {
                "fields": [],
                "structures": [],
                "structure_relationships": [],
                "works": [],
                "quantities": [],
                "materials": [],
            }
        )
        for _ in batches
    ]
    responses[0] = json.dumps(
        {
            "fields": [],
            "structures": [],
            "structure_relationships": [],
            "works": [{"name": "Устройство основания", "fragment_id": "F1"}],
            "quantities": [],
            "materials": [],
        },
        ensure_ascii=False,
    )
    responses[-1] = json.dumps(
        {
            "fields": [],
            "structures": [],
            "structure_relationships": [],
            "works": [],
            "quantities": [
                {
                    "work_name": "Устройство основания",
                    "value": "12,5",
                    "unit": "м3",
                    "fragment_id": f"F{len(batches[-1].fragments)}",
                    "work_fragment_id": "",
                }
            ],
            "materials": [
                {
                    "work_name": "Устройство основания",
                    "name": "Щебень",
                    "quantity": "12,5",
                    "unit": "м3",
                    "fragment_id": f"F{len(batches[-1].fragments)}",
                    "work_fragment_id": "",
                }
            ],
        },
        ensure_ascii=False,
    )

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        side_effect=responses,
    ) as complete:
        result = adapter.extract_engineering(elements)

    assert complete.call_count == len(batches)
    assert len(result.works) == 1
    assert len(result.quantities) == 1
    assert result.quantities[0].work_candidate_id == result.works[0].candidate_id
    assert result.quantities[0].locator.source_locator_id == UUID(last_locator_id)
    assert len(result.materials) == 1
    assert result.materials[0].work_candidate_id == result.works[0].candidate_id
    assert result.materials[0].locator.source_locator_id == UUID(last_locator_id)


def test_qwen_engineering_extraction_keeps_same_named_works_distinct_by_fragment() -> None:
    document = _extract_csv("A;B;C\n")
    fragments = _engineering_batches(document.pages[0].elements)[0].fragments
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=json.dumps(
            {
                "fields": [],
                "structures": [],
                "structure_relationships": [],
                "works": [
                    {"name": "Монтаж", "fragment_id": "F1"},
                    {"name": "Монтаж", "fragment_id": "F2"},
                ],
                "quantities": [
                    {
                        "work_name": "Монтаж",
                        "value": "2",
                        "unit": "шт",
                        "fragment_id": "F2",
                        "work_fragment_id": "F2",
                    },
                    {
                        "work_name": "Монтаж",
                        "value": "3",
                        "unit": "шт",
                        "fragment_id": "F3",
                        "work_fragment_id": "",
                    },
                ],
                "materials": [],
            },
            ensure_ascii=False,
        ),
    ):
        result = adapter.extract_engineering(document.pages[0].elements)

    assert len(fragments) >= 3
    assert len(result.works) == 2
    assert len(result.quantities) == 1
    assert result.quantities[0].work_candidate_id == result.works[1].candidate_id
    assert len(result.defects) == 1
    assert result.defects[0].parameters["code"] == "unresolved_work_reference"


def test_qwen_engineering_fragments_preserve_full_text_with_traceable_spans() -> None:
    document = _extract_csv("Текст;" + "длинный " * 500 + "\n")
    element = document.pages[0].elements[1]

    fragments = _fragments((element,))

    assert "".join(item.text for item in fragments) == element.normalized_text
    assert fragments[0].character_start == 0
    assert fragments[-1].character_end == len(element.normalized_text)
    assert len({item.fragment_id for item in fragments}) == len(fragments)


def test_qwen_engineering_batches_cover_every_fragment_with_bounded_context() -> None:
    document = _extract_csv(
        "\n".join(f"строка {index};значение {index}" for index in range(1, 31)) + "\n"
    )

    fragments = _fragments(document.pages[0].elements)
    batches = _engineering_batches(document.pages[0].elements)

    assert len(batches) == 5
    assert tuple(item for batch in batches for item in batch.fragments) == fragments
    assert all(len(batch.fragments) <= 12 for batch in batches)
    assert all(sum(len(item.text) for item in batch.fragments) <= 9_000 for batch in batches)


def test_qwen_engineering_dense_batches_are_explicit_and_legacy_batches_stay_stable() -> None:
    document = _extract_csv(
        "\n".join(f"строка {index};значение {index}" for index in range(1, 31)) + "\n"
    )

    legacy = _engineering_batches(document.pages[0].elements)
    dense = _engineering_batches(
        document.pages[0].elements, batching_policy_version="dense-fragments-v1"
    )

    assert len(dense) < len(legacy)
    assert tuple(item for batch in dense for item in batch.fragments) == tuple(
        item for batch in legacy for item in batch.fragments
    )
    assert all(len(batch.fragments) <= 48 for batch in dense)
    assert all(
        batch.input_manifest["batching_policy_version"] == "dense-fragments-v1" for batch in dense
    )
    assert all("batching_policy_version" not in batch.input_manifest for batch in legacy)


def test_qwen_engineering_batches_reject_unknown_batching_policy() -> None:
    document = _extract_csv("строка;значение\n")

    with pytest.raises(ValueError, match="qwen_engineering_batching_policy_unsupported"):
        _engineering_batches(document.pages[0].elements, batching_policy_version="unknown")


def test_qwen_engineering_accepted_batch_materializes_only_local_candidates() -> None:
    document = _extract_csv("КНС-1;Устройство котлована\n")
    batch = _engineering_batches(document.pages[0].elements)[0]
    first = str(batch.fragments[0].fragment_id)
    second = str(batch.fragments[1].fragment_id)
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    result = adapter.accepted_batch_candidates(
        batch,
        {
            "fields": [["project_purpose", "КНС", first]],
            "structures": [["facility", "КНС-1", first]],
            "structure_relationships": [["contains", "КНС-1", "котлован", first]],
            "works": [["Устройство котлована", second]],
            "quantities": [["Устройство котлована", "12", "м3", second, second]],
            "materials": [],
        },
    )

    assert len(result.project_fields) == 1
    assert result.project_fields[0].uncertainty_codes == ("qwen_semantic_candidate",)
    assert len(result.structures) == 1
    assert len(result.structure_relationships) == 1
    assert len(result.works) == 1
    assert not result.quantities
    assert not result.materials


def test_qwen_structure_identity_reconciliation_requires_exact_cross_source_members() -> None:
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    left = deterministic_uuid("identity-left")
    right = deterministic_uuid("identity-right")
    left_locator = deterministic_uuid("identity-left-locator")
    right_locator = deterministic_uuid("identity-right-locator")
    observations = (
        {
            "structure_node_id": str(left),
            "node_kind": "facility",
            "raw_name": "КНС-4",
            "normalized_name": "кнс-4",
            "source_locator_id": str(left_locator),
            "source_version_id": "20000000-0000-4000-8000-000000000001",
            "page": "4",
            "safe_display_name": "ПЗУ",
        },
        {
            "structure_node_id": str(right),
            "node_kind": "facility",
            "raw_name": "КНС 4",
            "normalized_name": "кнс 4",
            "source_locator_id": str(right_locator),
            "source_version_id": "20000000-0000-4000-8000-000000000002",
            "page": "7",
            "safe_display_name": "КР",
        },
    )
    response = json.dumps(
        {
            "identities": [
                {
                    "kind": "facility",
                    "label": "КНС-4",
                    "member_node_ids": [str(left), str(right)],
                    "confidence": 0.8,
                }
            ]
        }
    )

    with patch("asd_kontur.document_understanding.qwen_semantic._complete", return_value=response):
        result = adapter.reconcile_structure_identities(observations)

    assert len(result) == 1
    assert result[0].member_structure_node_ids == (left, right)
    assert result[0].source_locator_ids == (left_locator, right_locator)


def test_qwen_structure_identity_reconciliation_rejects_unknown_member() -> None:
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    node = deterministic_uuid("identity-known")
    locator = deterministic_uuid("identity-known-locator")
    observations = (
        {
            "structure_node_id": str(node),
            "node_kind": "facility",
            "raw_name": "КНС-4",
            "normalized_name": "кнс-4",
            "source_locator_id": str(locator),
            "source_version_id": "20000000-0000-4000-8000-000000000001",
            "page": "4",
            "safe_display_name": "ПЗУ",
        },
        {
            "structure_node_id": str(deterministic_uuid("identity-other")),
            "node_kind": "facility",
            "raw_name": "КНС 4",
            "normalized_name": "кнс 4",
            "source_locator_id": str(deterministic_uuid("identity-other-locator")),
            "source_version_id": "20000000-0000-4000-8000-000000000002",
            "page": "7",
            "safe_display_name": "КР",
        },
    )
    response = json.dumps(
        {
            "identities": [
                {
                    "kind": "facility",
                    "label": "КНС-4",
                    "member_node_ids": [str(node), str(deterministic_uuid("unknown"))],
                    "confidence": 0.8,
                }
            ]
        }
    )

    with patch("asd_kontur.document_understanding.qwen_semantic._complete", return_value=response):
        with pytest.raises(QwenSemanticFailure, match="invalid_evidence"):
            adapter.reconcile_structure_identities(observations)


def test_partial_workspace_coverage_reconciles_completed_source_group() -> None:
    """An unrelated incomplete source must not starve an eligible identity group."""

    organization_id = deterministic_uuid("partial-reconciliation-organization")
    workspace_id = deterministic_uuid("partial-reconciliation-workspace")
    left = deterministic_uuid("partial-reconciliation-left")
    right = deterministic_uuid("partial-reconciliation-right")
    left_locator = deterministic_uuid("partial-reconciliation-left-locator")
    right_locator = deterministic_uuid("partial-reconciliation-right-locator")
    persisted: list[StructureIdentityCandidate] = []

    class Repository:
        def workspace_engineering_semantic_coverage(
            self, _claimed: ClaimedJob, *, profile_version: str
        ) -> dict[str, int | bool]:
            assert profile_version == "qwen-engineering-extraction-v15"
            return {"source_count": 3, "complete_source_count": 2, "complete": False}

        def load_structure_identity_observation_groups(
            self, _claimed: ClaimedJob, *, profile_version: str
        ) -> tuple[tuple[dict[str, object], ...], ...]:
            assert profile_version == "qwen-engineering-extraction-v15"
            return (({"structure_node_id": str(left)}, {"structure_node_id": str(right)}),)

        def persist_structure_identity_candidates(
            self, _claimed: ClaimedJob, values: tuple[StructureIdentityCandidate, ...]
        ) -> None:
            persisted.extend(values)

        def assemble_workspace(self, _claimed: ClaimedJob) -> dict[str, object]:
            return {"run_id": "synthetic-run"}

    class Qwen:
        def reconcile_structure_identities(
            self, observations: tuple[dict[str, object], ...]
        ) -> tuple[StructureIdentityCandidate, ...]:
            assert {item["structure_node_id"] for item in observations} == {str(left), str(right)}
            return (
                StructureIdentityCandidate(
                    deterministic_uuid("partial-reconciliation-candidate"),
                    "facility",
                    "Synthetic facility",
                    (left, right),
                    (left_locator, right_locator),
                    Decimal("0.8"),
                    "qwen-structure-identity-v1",
                ),
            )

    pipeline = IndustrialDocumentUnderstandingPipeline(
        cast(IndustrialUnderstandingRepository, Repository()),
        qwen_vision=cast(QwenVisionOcrAdapter, object()),
        qwen_semantic=cast(QwenDocumentSemanticAdapter, Qwen()),
    )
    claimed = ClaimedJob(
        organization_id,
        workspace_id,
        deterministic_uuid("partial-reconciliation-job"),
        JobKind.PROJECT_STRUCTURE_RECONCILIATION,
        {},
        "sha256:" + "a" * 64,
        1,
        1,
        "not_requested",
    )

    result = pipeline._reconciliation(claimed, BytesIO())

    assert persisted and persisted[0].member_structure_node_ids == (left, right)
    assert result["structure_identity_candidate_count"] == 1
    assert result["structure_identity_reconciliation"] == "partial_completed_source_groups"


def test_qwen_engineering_recovers_partial_candidates_only_from_exact_batch_manifest() -> None:
    document = _extract_csv("КНС-1;значение\n")
    batches = _engineering_batches(document.pages[0].elements)
    fragment_id = str(batches[0].fragments[0].fragment_id)
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    recovered = adapter.accepted_source_batch_candidates(
        document.pages[0].elements,
        accepted_batches={
            batches[0].digest: {
                "fields": [],
                "structures": [["facility", "КНС-1", fragment_id]],
                "structure_relationships": [],
                "works": [],
                "quantities": [],
                "materials": [],
            },
            "sha256:" + "0" * 64: {
                "fields": [],
                "structures": [["facility", "Подмена", fragment_id]],
                "structure_relationships": [],
                "works": [],
                "quantities": [],
                "materials": [],
            },
        },
    )

    assert len(recovered) == 1
    assert recovered[0].structures[0].raw_name == "КНС-1"


def test_qwen_engineering_progress_reports_each_completed_base_batch() -> None:
    document = _extract_csv(
        "\n".join(f"строка {index};значение {index}" for index in range(1, 31)) + "\n"
    )
    batches = _engineering_batches(document.pages[0].elements)
    progress: list[tuple[int, int]] = []
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=json.dumps(
            {
                "fields": [],
                "structures": [],
                "structure_relationships": [],
                "works": [],
                "quantities": [],
                "materials": [],
            }
        ),
    ):
        adapter.extract_engineering(
            document.pages[0].elements,
            on_batch_progress=lambda current, total: progress.append((current, total)),
        )

    assert progress == [(index, len(batches)) for index in range(1, len(batches) + 1)]


def test_qwen_engineering_extraction_preserves_unresolved_relationship_and_optional_material() -> (
    None
):
    document = _extract_csv("A;B;C\n")
    fragments = _engineering_batches(document.pages[0].elements)[0].fragments
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=json.dumps(
            {
                "fields": [],
                "structures": [],
                "structure_relationships": [],
                "works": [{"name": "Монтаж", "fragment_id": fragments[0].fragment_id}],
                "quantities": [
                    {
                        "work_name": "Неустановленная работа",
                        "value": "4",
                        "unit": "шт",
                        "fragment_id": fragments[2].fragment_id,
                        "work_fragment_id": "",
                    }
                ],
                "materials": [
                    {
                        "work_name": "Монтаж",
                        "name": "Сталь",
                        "quantity": "",
                        "unit": "",
                        "fragment_id": fragments[2].fragment_id,
                        "work_fragment_id": fragments[0].fragment_id,
                    }
                ],
            },
            ensure_ascii=False,
        ),
    ):
        result = adapter.extract_engineering(document.pages[0].elements)

    assert not result.quantities
    assert len(result.defects) == 1
    assert result.defects[0].parameters["code"] == "unresolved_work_reference"
    assert len(result.materials) == 1
    assert result.materials[0].raw_quantity is None
    assert result.materials[0].raw_unit is None


def test_qwen_engineering_extraction_preserves_incomplete_quantity_as_evidenced_defect() -> None:
    document = _extract_csv("A;B;C\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    accepted: dict[str, dict[str, object]] = {}
    response = json.dumps(
        {
            "fields": [],
            "structures": [],
            "structure_relationships": [],
            "works": [],
            "quantities": [
                {
                    "work_name": "",
                    "value": "",
                    "unit": "",
                    "fragment_id": "F1",
                    "work_fragment_id": "",
                }
            ],
            "materials": [],
        },
        ensure_ascii=False,
    )

    with patch("asd_kontur.document_understanding.qwen_semantic._complete", return_value=response):
        first = adapter.extract_engineering(
            document.pages[0].elements,
            on_accepted_batch=lambda batch, manifest: accepted.__setitem__(batch.digest, manifest),
        )

    assert not first.quantities
    assert len(first.defects) == 1
    assert first.defects[0].parameters == {
        "code": "incomplete_quantity_candidate",
        "work_name": None,
        "raw_value": None,
        "unit": None,
        "work_fragment_id": None,
    }
    assert "incomplete_quantities" in next(iter(accepted.values()))

    with patch("asd_kontur.document_understanding.qwen_semantic._complete") as complete:
        resumed = adapter.extract_engineering(document.pages[0].elements, accepted_batches=accepted)

    complete.assert_not_called()
    assert resumed == first


def test_qwen_engineering_extraction_rejects_incomplete_schema() -> None:
    document = _extract_csv("проектная запись;значение\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    failed: list[tuple[object, str]] = []

    with patch("asd_kontur.document_understanding.qwen_semantic._complete", return_value="{}"):
        result = adapter.extract_engineering(
            document.pages[0].elements,
            on_failed_batch=lambda batch, code, _details: failed.append((batch, code)),
        )

    assert result == StructuredCandidates((), (), (), (), (), ())
    assert failed
    assert all(code == "qwen_engineering_response_invalid_shape" for _, code in failed)


def test_qwen_engineering_extraction_normalizes_only_terminal_prompt_alias_punctuation() -> None:
    document = _extract_csv("Котлован К-1;подтверждено\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=json.dumps(
            {
                "fields": [],
                "structures": [
                    {"kind": "excavation_pit", "name": "Котлован К-1", "fragment_id": "F1."}
                ],
                "structure_relationships": [],
                "works": [],
                "quantities": [],
                "materials": [],
            },
            ensure_ascii=False,
        ),
    ):
        result = adapter.extract_engineering(document.pages[0].elements)

    assert len(result.structures) == 1
    assert result.structures[0].raw_name == "Котлован К-1"


def test_qwen_engineering_extraction_preserves_evidence_bound_structure_relationship() -> None:
    document = _extract_csv("Котлован К-1 обслуживает КНС-2\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=json.dumps(
            {
                "fields": [],
                "structures": [
                    {"kind": "excavation_pit", "name": "Котлован К-1", "fragment_id": "F1"},
                    {"kind": "facility", "name": "КНС-2", "fragment_id": "F1"},
                ],
                "structure_relationships": [
                    {
                        "kind": "serves",
                        "subject_name": "Котлован К-1",
                        "object_name": "КНС-2",
                        "fragment_id": "F1",
                    }
                ],
                "works": [],
                "quantities": [],
                "materials": [],
            },
            ensure_ascii=False,
        ),
    ):
        result = adapter.extract_engineering(document.pages[0].elements)

    assert len(result.structure_relationships) == 1
    assert {value.node_kind for value in result.structures} == {"excavation_pit", "facility"}
    relationship = result.structure_relationships[0]
    assert relationship.relationship_kind == "serves"
    assert relationship.subject_normalized_name == "котлован к-1"
    assert relationship.object_normalized_name == "кнс-2"
    assert (
        relationship.locator.source_locator_id
        == document.pages[0].elements[0].locator.source_locator_id
    )


def test_qwen_engineering_candidates_are_profile_scoped() -> None:
    """A later semantic profile must not collide with legacy generic candidates."""
    document = _extract_csv("Котлован К-1;устройство шпунтового ограждения\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    response = json.dumps(
        {
            "fields": [{"key": "purpose", "value": "котлован", "fragment_id": "F1"}],
            "structures": [{"kind": "excavation_pit", "name": "Котлован К-1", "fragment_id": "F1"}],
            "structure_relationships": [],
            "works": [{"name": "устройство шпунтового ограждения", "fragment_id": "F1"}],
            "quantities": [],
            "materials": [],
        },
        ensure_ascii=False,
    )
    with patch("asd_kontur.document_understanding.qwen_semantic._complete", return_value=response):
        result = adapter.extract_engineering(document.pages[0].elements)

    qwen_field = next(
        value
        for value in result.project_fields
        if value.extraction_profile_version == "qwen-engineering-extraction-v15"
    )
    assert result.works[0].extraction_profile_version == "qwen-engineering-extraction-v15"
    assert result.structures[0].extraction_profile_version == "qwen-engineering-extraction-v15"
    fragment_id = _engineering_batches(document.pages[0].elements)[0].fragments[0].fragment_id
    assert qwen_field.candidate_id == deterministic_uuid(
        "qwen-field:qwen-engineering-extraction-v15:"
        f"{qwen_field.locator.source_version_id}:{fragment_id}:purpose:котлован"
    )
    assert qwen_field.candidate_id != deterministic_uuid(
        f"qwen-field:{qwen_field.locator.source_version_id}:{fragment_id}:purpose:котлован"
    )


def test_qwen_engineering_extraction_accepts_unique_source_locator_but_not_ambiguous_one() -> None:
    document = _extract_csv("Котлован К-1;подтверждено\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    locator_id = str(document.pages[0].elements[0].locator.source_locator_id)

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=json.dumps(
            {
                "fields": [],
                "structures": [
                    {
                        "kind": "excavation_pit",
                        "name": "Котлован К-1",
                        "fragment_id": locator_id,
                    }
                ],
                "structure_relationships": [],
                "works": [],
                "quantities": [],
                "materials": [],
            },
            ensure_ascii=False,
        ),
    ):
        result = adapter.extract_engineering(document.pages[0].elements)

    assert result.structures[0].locator.source_locator_id == UUID(locator_id)


def test_qwen_engineering_extraction_repairs_recoverable_invalid_batch_before_splitting() -> None:
    document = _extract_csv("A;B;C\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    accepted: list[tuple[object, dict[str, object]]] = []
    failed: list[tuple[object, str]] = []
    repaired = json.dumps(
        {
            "fields": [{"key": "purpose", "value": "Объект", "fragment_id": "F1"}],
            "structures": [],
            "structure_relationships": [],
            "works": [],
            "quantities": [],
            "materials": [],
        },
        ensure_ascii=False,
    )

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        side_effect=("{}", repaired),
    ) as complete:
        result = adapter.extract_engineering(
            document.pages[0].elements,
            on_accepted_batch=lambda batch, manifest: accepted.append((batch, manifest)),
            on_failed_batch=lambda batch, code, _details: failed.append((batch, code)),
        )

    assert complete.call_count == 2
    assert result.project_fields[0].raw_value == "Объект"
    assert len(accepted) == 1
    assert accepted[0][0].prompt_strategy == "evidence_reference_and_kind_repair-v2"
    assert not failed


def test_qwen_engineering_extraction_recovers_invalid_structure_kind_without_accepting_it() -> None:
    document = _extract_csv("Объект;Котлован К-1\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    accepted: list[tuple[object, dict[str, object]]] = []
    invalid_kind = json.dumps(
        {
            "fields": [],
            "structures": [{"kind": "pit_group", "name": "Котлован К-1", "fragment_id": "F1"}],
            "structure_relationships": [],
            "works": [],
            "quantities": [],
            "materials": [],
        },
        ensure_ascii=False,
    )
    repaired = json.dumps(
        {
            "fields": [],
            "structures": [{"kind": "excavation_pit", "name": "Котлован К-1", "fragment_id": "F1"}],
            "structure_relationships": [],
            "works": [],
            "quantities": [],
            "materials": [],
        },
        ensure_ascii=False,
    )

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        side_effect=(invalid_kind, repaired),
    ) as complete:
        result = adapter.extract_engineering(
            document.pages[0].elements,
            on_accepted_batch=lambda batch, manifest: accepted.append((batch, manifest)),
        )

    assert complete.call_count == 2
    assert result.structures[0].node_kind == "excavation_pit"
    assert accepted[0][0].prompt_strategy == "evidence_reference_and_kind_repair-v2"


def test_qwen_engineering_extraction_reuses_accepted_recovery_children_before_calling_qwen() -> (
    None
):
    document = _extract_csv("A;B;C\n")
    parent = _engineering_batches(document.pages[0].elements)[0]
    children = _split_engineering_batch(parent)
    assert children
    accepted = {
        child.digest: {
            "fields": [],
            "structures": [],
            "structure_relationships": [],
            "works": [],
            "quantities": [],
            "materials": [],
        }
        for child in children
    }
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")

    with patch("asd_kontur.document_understanding.qwen_semantic._complete") as complete:
        result = adapter.extract_engineering(
            document.pages[0].elements,
            accepted_batches=accepted,
        )

    complete.assert_not_called()
    assert result == StructuredCandidates((), (), (), (), (), ())


def test_qwen_engineering_extraction_repairs_one_invalid_single_fragment_response() -> None:
    document = _extract_csv("A\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    accepted: list[tuple[object, dict[str, object]]] = []
    valid = json.dumps(
        {
            "fields": [],
            "structures": [],
            "structure_relationships": [],
            "works": [],
            "quantities": [],
            "materials": [],
        }
    )

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        side_effect=("{}", "{}", valid),
    ) as complete:
        result = adapter.extract_engineering(
            document.pages[0].elements,
            on_accepted_batch=lambda batch, manifest: accepted.append((batch, manifest)),
        )

    assert complete.call_count == 3
    assert result == StructuredCandidates((), (), (), (), (), ())
    batch, _manifest = accepted[0]
    assert batch.prompt_strategy == "single_fragment_repair-v1"
    assert batch.input_manifest["prompt_strategy"] == "single_fragment_repair-v1"
    assert batch.input_manifest["fragments"][0]["prompt_strategy"] == "single_fragment_repair-v1"


def test_qwen_engineering_extraction_preserves_unrepaired_leaf_as_partial_coverage() -> None:
    document = _extract_csv("A\n")
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    failed: list[tuple[object, str]] = []

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        side_effect=("{}", "{}", "{}"),
    ) as complete:
        result = adapter.extract_engineering(
            document.pages[0].elements,
            on_failed_batch=lambda batch, code, _details: failed.append((batch, code)),
        )

    assert complete.call_count == 3
    assert result == StructuredCandidates((), (), (), (), (), ())
    assert [code for _, code in failed] == [
        "qwen_engineering_response_invalid_shape",
        "qwen_engineering_response_invalid_shape",
    ]
    assert [batch.prompt_strategy for batch, _ in failed] == [
        "standard",
        "single_fragment_repair-v1",
    ]


def test_qwen_engineering_batch_v6_manifest_preserves_fragment_coverage() -> None:
    document = _extract_csv("строка 1;строка 2\n")
    batch = _engineering_batches(document.pages[0].elements)[0]

    manifest = batch.input_manifest

    assert manifest["profile_version"] == "qwen-engineering-extraction-v15"
    assert isinstance(manifest["fragments"], list)
    assert {item["fragment_id"] for item in manifest["fragments"]} == {
        item.fragment_id for item in batch.fragments
    }


def test_qwen_engineering_extraction_reuses_only_validated_batch_manifests() -> None:
    document = _extract_csv("проектная запись;значение\n")
    fragment_id = str(_engineering_batches(document.pages[0].elements)[0].fragments[0].fragment_id)
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    accepted: dict[str, dict[str, object]] = {}

    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=json.dumps(
            {
                "fields": [
                    {"key": "project_purpose", "value": "Объект", "fragment_id": fragment_id}
                ],
                "structures": [],
                "structure_relationships": [],
                "works": [],
                "quantities": [],
                "materials": [],
            },
            ensure_ascii=False,
        ),
    ):
        first = adapter.extract_engineering(
            document.pages[0].elements,
            on_accepted_batch=lambda batch, manifest: accepted.__setitem__(batch.digest, manifest),
        )

    with patch("asd_kontur.document_understanding.qwen_semantic._complete") as complete:
        resumed = adapter.extract_engineering(document.pages[0].elements, accepted_batches=accepted)

    complete.assert_not_called()
    assert resumed == first
    assert len(accepted) == 1


def test_qwen_engineering_extraction_does_not_reuse_prior_profile_without_relationships() -> None:
    document = _extract_csv("проектная запись;значение\n")
    batch = _engineering_batches(document.pages[0].elements)[0]
    fragment_id = str(batch.fragments[0].fragment_id)
    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    compatible = {
        _compatible_batch_digest(batch.fragments, "qwen-engineering-extraction-v3"): {
            "fields": [["project_purpose", "Объект", fragment_id]],
            "structures": [],
            "structure_relationships": [],
            "works": [],
            "quantities": [],
            "materials": [],
        }
    }

    response = json.dumps(
        {
            "fields": [],
            "structures": [],
            "structure_relationships": [],
            "works": [],
            "quantities": [],
            "materials": [],
        }
    )
    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete", return_value=response
    ) as complete:
        result = adapter.extract_engineering(
            document.pages[0].elements, compatible_accepted_batches=compatible
        )

    complete.assert_called_once()
    assert not result.project_fields


def test_project_field_stage_persists_each_accepted_qwen_engineering_batch() -> None:
    document = _extract_csv("Котлован К-1;подтверждено\n")
    locator_id = str(document.pages[0].elements[0].locator.source_locator_id)
    fragment_id = str(_engineering_batches(document.pages[0].elements)[0].fragments[0].fragment_id)
    claimed = ClaimedJob(
        UUID("30000000-0000-4000-8000-000000000002"),
        UUID("40000000-0000-4000-8000-000000000002"),
        UUID("50000000-0000-4000-8000-000000000002"),
        JobKind.PROJECT_DEFINITION_EXTRACTION,
        {
            "document_id": str(DOCUMENT_ID),
            "document_version": 1,
            "source_version_id": str(SOURCE_VERSION_ID),
        },
        "sha256:" + "b" * 64,
        1,
        1,
        "none",
    )
    persisted: dict[str, object] = {}

    class Repository:
        def load_accepted_engineering_batches(
            self, _claimed: ClaimedJob, *, profile_version: str
        ) -> dict[str, dict[str, object]]:
            assert profile_version in {
                "qwen-engineering-extraction-v15",
            }
            return {}

        def load_elements(self, _claimed: ClaimedJob) -> tuple[LayoutElement, ...]:
            return document.pages[0].elements

        def record_accepted_engineering_batch(self, _claimed: ClaimedJob, **values: object) -> None:
            persisted.update(values)

        def persist_structured(self, _claimed: ClaimedJob, bundle: StructuredCandidates) -> None:
            persisted.setdefault("bundles", []).append(bundle)

    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    pipeline = IndustrialDocumentUnderstandingPipeline(
        cast(IndustrialUnderstandingRepository, Repository()),
        qwen_vision=cast(QwenVisionOcrAdapter, object()),
        qwen_semantic=adapter,
    )
    with (
        patch.object(
            pipeline, "_structured", return_value=StructuredCandidates((), (), (), (), (), ())
        ),
        patch(
            "asd_kontur.document_understanding.qwen_semantic._complete",
            return_value=json.dumps(
                {
                    "fields": [],
                    "structures": [
                        {
                            "kind": "excavation_pit",
                            "name": "Котлован К-1",
                            "fragment_id": fragment_id,
                        }
                    ],
                    "structure_relationships": [],
                    "works": [{"name": "Разработка котлована", "fragment_id": fragment_id}],
                    "quantities": [
                        {
                            "work_name": "Разработка котлована",
                            "value": "12",
                            "unit": "м3",
                            "fragment_id": fragment_id,
                            "work_fragment_id": fragment_id,
                        }
                    ],
                    "materials": [
                        {
                            "work_name": "Разработка котлована",
                            "name": "Песок",
                            "quantity": "",
                            "unit": "",
                            "fragment_id": fragment_id,
                            "work_fragment_id": fragment_id,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        ),
    ):
        result = pipeline._project_fields(claimed, BytesIO())

    assert result["structure_candidate_count"] == 1
    assert result["work_candidate_count"] == 1
    assert result["quantity_candidate_count"] == 1
    assert result["material_candidate_count"] == 1
    assert persisted["batch_ordinal"] == 1
    assert persisted["source_locator_ids"] == (
        UUID(locator_id),
        UUID(str(document.pages[0].elements[1].locator.source_locator_id)),
    )
    assert persisted["input_manifest"]
    assert persisted["input_manifest"]["batching_policy_version"] == "dense-fragments-v1"
    bundles = cast(list[StructuredCandidates], persisted["bundles"])
    assert len(bundles) == 2
    partial = bundles[0]
    assert len(partial.structures) == 1
    assert len(partial.works) == 1
    assert not partial.quantities
    assert not partial.materials
    bundle = bundles[-1]
    assert len(bundle.structures) == 1
    assert len(bundle.works) == 1
    assert len(bundle.quantities) == 1
    assert len(bundle.materials) == 1


def test_project_field_stage_marks_unresolved_semantic_coverage_partial() -> None:
    """A durable job may finish while one evidence leaf remains unresolved."""
    claimed = ClaimedJob(
        UUID("30000000-0000-4000-8000-000000000004"),
        UUID("40000000-0000-4000-8000-000000000004"),
        UUID("50000000-0000-4000-8000-000000000004"),
        JobKind.PROJECT_DEFINITION_EXTRACTION,
        {
            "document_id": str(DOCUMENT_ID),
            "document_version": 1,
            "source_version_id": str(SOURCE_VERSION_ID),
        },
        "sha256:" + "d" * 64,
        1,
        1,
        "none",
    )
    persisted: dict[str, object] = {}

    class Repository:
        def record_stage_result(self, _claimed: ClaimedJob, **values: object) -> None:
            persisted.update(values)

    pipeline = IndustrialDocumentUnderstandingPipeline(
        cast(IndustrialUnderstandingRepository, Repository()),
        qwen_vision=cast(QwenVisionOcrAdapter, object()),
    )
    with patch.object(
        pipeline,
        "_project_fields",
        return_value={
            "project_field_candidate_count": 1,
            "semantic_coverage": {
                "complete": False,
                "accepted_fragment_count": 5,
                "expected_fragment_count": 6,
                "unresolved_failed_fragment_count": 1,
            },
        },
    ):
        pipeline.execute(claimed, BytesIO())

    assert persisted["terminal_status"] == "partial"
    assert persisted["typed_failure_code"] == "qwen_engineering_coverage_incomplete"


def test_project_field_stage_uses_qwen_evidence_when_classification_is_unavailable() -> None:
    document = _extract_csv("КНС-1;котлован К-1\n")
    fragment_id = str(_engineering_batches(document.pages[0].elements)[0].fragments[0].fragment_id)
    claimed = ClaimedJob(
        UUID("30000000-0000-4000-8000-000000000003"),
        UUID("40000000-0000-4000-8000-000000000003"),
        UUID("50000000-0000-4000-8000-000000000003"),
        JobKind.PROJECT_DEFINITION_EXTRACTION,
        {
            "document_id": str(DOCUMENT_ID),
            "document_version": 1,
            "source_version_id": str(SOURCE_VERSION_ID),
        },
        "sha256:" + "c" * 64,
        1,
        1,
        "none",
    )
    persisted: dict[str, object] = {}

    class Repository:
        def load_accepted_engineering_batches(
            self, _claimed: ClaimedJob, *, profile_version: str
        ) -> dict[str, dict[str, object]]:
            assert profile_version == "qwen-engineering-extraction-v15"
            return {}

        def load_elements(self, _claimed: ClaimedJob) -> tuple[LayoutElement, ...]:
            return document.pages[0].elements

        def load_role_decisions(self, _claimed: ClaimedJob) -> tuple[object, ...]:
            return ()

        def record_accepted_engineering_batch(
            self, _claimed: ClaimedJob, **_values: object
        ) -> None:
            return None

        def persist_structured(self, _claimed: ClaimedJob, bundle: StructuredCandidates) -> None:
            persisted["bundle"] = bundle

    adapter = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    pipeline = IndustrialDocumentUnderstandingPipeline(
        cast(IndustrialUnderstandingRepository, Repository()),
        qwen_vision=cast(QwenVisionOcrAdapter, object()),
        qwen_semantic=adapter,
    )
    response = json.dumps(
        {
            "fields": [],
            "structures": [{"kind": "facility", "name": "КНС-1", "fragment_id": fragment_id}],
            "structure_relationships": [
                {
                    "kind": "contains",
                    "subject_name": "КНС-1",
                    "object_name": "котлован К-1",
                    "fragment_id": fragment_id,
                }
            ],
            "works": [],
            "quantities": [],
            "materials": [],
        },
        ensure_ascii=False,
    )
    with patch("asd_kontur.document_understanding.qwen_semantic._complete", return_value=response):
        result = pipeline._project_fields(claimed, BytesIO())

    assert result["structure_candidate_count"] == 1
    bundle = cast(StructuredCandidates, persisted["bundle"])
    assert len(bundle.structures) == 1
    assert len(bundle.structure_relationships) == 1


def test_classification_persists_qwen_semantic_candidate_alongside_page_roles() -> None:
    document = _extract_csv("Пояснительная записка\nНазначение объекта: насосная станция\n")
    locator_id = str(document.pages[0].elements[0].locator.source_locator_id)
    qwen = QwenDocumentSemanticAdapter("http://127.0.0.1:8790/generate")
    with patch(
        "asd_kontur.document_understanding.qwen_semantic._complete",
        return_value=json.dumps(
            {"roles": ["explanatory_note"], "locator_ids": [locator_id]}, ensure_ascii=False
        ),
    ):
        semantic = qwen.classify(document.pages[0].elements)

    captured: dict[str, object] = {}

    class Repository:
        def load_elements(self, _claimed: ClaimedJob) -> tuple[object, ...]:
            return document.pages[0].elements

        def persist_classification(
            self,
            _claimed: ClaimedJob,
            candidates: tuple[object, ...],
            decisions: tuple[object, ...],
        ) -> None:
            captured["candidates"] = candidates
            captured["decisions"] = decisions

    class SemanticAdapter:
        def classify(self, _elements: tuple[object, ...]):
            return semantic

    pipeline = IndustrialDocumentUnderstandingPipeline(
        cast(IndustrialUnderstandingRepository, Repository()),
        qwen_vision=cast(QwenVisionOcrAdapter, object()),
        qwen_semantic=cast(QwenDocumentSemanticAdapter, SemanticAdapter()),
    )
    result = pipeline._classification(cast(ClaimedJob, object()), BytesIO())

    assert result["qwen_semantic_candidate_count"] == 1
    assert any(
        candidate.extraction_profile_version == "qwen-document-semantic-v1"
        for candidate in cast(tuple[Any, ...], captured["candidates"])
    )
