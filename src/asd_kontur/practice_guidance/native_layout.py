"""Deterministic native PDF geometry for bounded practice-guide recovery."""

from __future__ import annotations

import hashlib
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of

from .models import GuideLocator, GuideSourceRow

NATIVE_LAYOUT_PROFILE_VERSION = "guide_native_pdf_layout_v0.1"
NTD_TABLE_ROW_PROFILE_VERSION = "guide_ntd_three_column_rows_v0.1"


@dataclass(frozen=True, slots=True)
class NativeWord:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if not self.text or not (0 <= self.x0 < self.x1 and 0 <= self.y0 < self.y1):
            raise ValueError("Native PDF word geometry is invalid")


@dataclass(frozen=True, slots=True)
class NativeLine:
    words: tuple[NativeWord, ...]

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def box(self) -> tuple[float, float, float, float]:
        return _union_boxes(tuple(_word_box(word) for word in self.words))


@dataclass(frozen=True, slots=True)
class NativeBlock:
    lines: tuple[NativeLine, ...]

    @property
    def words(self) -> tuple[NativeWord, ...]:
        return tuple(word for line in self.lines for word in line.words)

    @property
    def text(self) -> str:
        return _join_wrapped_lines(self.lines)

    @property
    def box(self) -> tuple[float, float, float, float]:
        return _union_boxes(tuple(line.box for line in self.lines))


@dataclass(frozen=True, slots=True)
class NativePageLayout:
    page_number: int
    width_points: float
    height_points: float
    blocks: tuple[NativeBlock, ...]
    extraction_digest: str
    omitted_control_glyph_count: int = 0

    @property
    def words(self) -> tuple[NativeWord, ...]:
        return tuple(word for block in self.blocks for word in block.words)

    @property
    def native_text(self) -> str:
        return "\n".join(block.text for block in self.blocks)


@dataclass(frozen=True, slots=True)
class NativeRecoveryClassification:
    page_number: int
    recovery_route: str
    word_count: int
    line_count: int
    native_text_characters: int
    extraction_digest: str
    reason_codes: tuple[str, ...]


def _word_box(word: NativeWord) -> tuple[float, float, float, float]:
    return word.x0, word.y0, word.x1, word.y1


def _union_boxes(
    boxes: tuple[tuple[float, float, float, float], ...],
) -> tuple[float, float, float, float]:
    if not boxes:
        raise ValueError("Cannot form a locator without native PDF geometry")
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _join_wrapped_lines(lines: tuple[NativeLine, ...]) -> str:
    result = ""
    for line in lines:
        line_text = line.text.strip()
        if not line_text:
            continue
        if result.endswith("-") and not result.endswith(" -"):
            result = result[:-1] + line_text
        elif result:
            result += " " + line_text
        else:
            result = line_text
    return result


def _extract_bbox_xhtml(pdf_path: Path, first_page: int, last_page: int) -> bytes:
    if first_page < 1 or last_page < first_page:
        raise ValueError("Native layout page range is invalid")
    completed = subprocess.run(
        [
            "pdftotext",
            "-f",
            str(first_page),
            "-l",
            str(last_page),
            "-bbox-layout",
            "-enc",
            "UTF-8",
            str(pdf_path),
            "-",
        ],
        capture_output=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise RuntimeError("NATIVE_PDF_LAYOUT_EXTRACTION_FAILED")
    return completed.stdout


def extract_native_page_layouts(
    pdf_path: Path, *, first_page: int, last_page: int
) -> tuple[NativePageLayout, ...]:
    """Extract immutable word/line boxes through Poppler without OCR or repair."""

    raw = _extract_bbox_xhtml(pdf_path, first_page, last_page)
    invalid_control = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    omitted_control_glyph_count = len(invalid_control.findall(raw))
    xml_payload = invalid_control.sub(b"", raw)
    root = ET.fromstring(xml_payload)
    namespace = {"x": "http://www.w3.org/1999/xhtml"}
    page_nodes = root.findall(".//x:page", namespace)
    if len(page_nodes) != last_page - first_page + 1:
        raise ValueError("Native layout output does not cover the requested page range")
    layouts: list[NativePageLayout] = []
    for offset, page_node in enumerate(page_nodes):
        blocks: list[NativeBlock] = []
        for block_node in page_node.findall(".//x:block", namespace):
            lines: list[NativeLine] = []
            for line_node in block_node.findall("./x:line", namespace):
                words = tuple(
                    NativeWord(
                        text=(word_node.text or "").strip(),
                        x0=float(word_node.attrib["xMin"]),
                        y0=float(word_node.attrib["yMin"]),
                        x1=float(word_node.attrib["xMax"]),
                        y1=float(word_node.attrib["yMax"]),
                    )
                    for word_node in line_node.findall("./x:word", namespace)
                    if (word_node.text or "").strip()
                )
                if words:
                    lines.append(NativeLine(words))
            if lines:
                blocks.append(NativeBlock(tuple(lines)))
        page_number = first_page + offset
        page_payload = ET.tostring(page_node, encoding="utf-8")
        layouts.append(
            NativePageLayout(
                page_number=page_number,
                width_points=float(page_node.attrib["width"]),
                height_points=float(page_node.attrib["height"]),
                blocks=tuple(blocks),
                extraction_digest=f"sha256:{hashlib.sha256(page_payload).hexdigest()}",
                omitted_control_glyph_count=omitted_control_glyph_count,
            )
        )
    return tuple(layouts)


def classify_native_recovery(layout: NativePageLayout) -> NativeRecoveryClassification:
    line_count = sum(len(block.lines) for block in layout.blocks)
    characters = len(layout.native_text.strip())
    reasons: tuple[str, ...]
    if len(layout.words) >= 12 and line_count >= 3 and characters >= 80:
        route = "deterministic_native_locator"
        reasons = ("NATIVE_WORD_GEOMETRY_AVAILABLE", "NATIVE_TEXT_SUFFICIENT")
        if layout.omitted_control_glyph_count:
            reasons += ("NON_TEXT_CONTROL_GLYPHS_OMITTED",)
    else:
        route = "targeted_vlm_region_recovery"
        reasons = ("NATIVE_LAYOUT_INSUFFICIENT",)
    return NativeRecoveryClassification(
        page_number=layout.page_number,
        recovery_route=route,
        word_count=len(layout.words),
        line_count=line_count,
        native_text_characters=characters,
        extraction_digest=layout.extraction_digest,
        reason_codes=reasons,
    )


def _normalized_region(
    box: tuple[float, float, float, float], layout: NativePageLayout
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = box
    region = (
        x0 / layout.width_points,
        y0 / layout.height_points,
        x1 / layout.width_points,
        y1 / layout.height_points,
    )
    # No clamping or repair: invalid source geometry fails closed in GuideLocator.
    GuideLocator(layout.page_number, region)
    return region


def _column_index(block: NativeBlock) -> int | None:
    x0, _, _, _ = block.box
    if 50 <= x0 < 188:
        return 0
    if 188 <= x0 < 280:
        return 1
    if 280 <= x0 < 370:
        return 2
    return None


def reconstruct_ntd_source_rows(
    *,
    source_version_id: UUID,
    layout: NativePageLayout,
    parent_failed_receipt_digest: str,
    parent_candidates_by_ordinal: dict[int, UUID] | None = None,
) -> tuple[GuideSourceRow, ...]:
    """Reconstruct the continued three-column NTD table from native block geometry."""

    columns: dict[int, list[NativeBlock]] = {0: [], 1: [], 2: []}
    for block in layout.blocks:
        index = _column_index(block)
        if index is not None:
            columns[index].append(block)
    left_blocks = sorted(columns[0], key=lambda block: block.box[1])
    header_markers = ("Наименование НТД", "Наименование нтд")
    row_anchors = [
        block
        for block in left_blocks
        if not any(marker in block.text for marker in header_markers)
        and re.search(r"(?:№|\b(?:СП|ГОСТ|И)\s+)", block.text)
    ]
    if not row_anchors:
        raise ValueError("NTD_TABLE_ROWS_NOT_FOUND")
    if parent_candidates_by_ordinal is not None and set(parent_candidates_by_ordinal) != set(
        range(1, len(row_anchors) + 1)
    ):
        raise ValueError("NTD table parent CandidateVersion ordinals do not reconcile")
    rows: list[GuideSourceRow] = []
    for ordinal, left in enumerate(row_anchors, start=1):
        top = left.box[1]
        bottom = (
            row_anchors[ordinal].box[1]
            if ordinal < len(row_anchors)
            else max(block.box[3] for blocks in columns.values() for block in blocks) + 0.001
        )
        selected: dict[int, tuple[NativeBlock, ...]] = {}
        for column, blocks in columns.items():
            selected[column] = tuple(
                block
                for block in blocks
                if top - 0.5 <= (block.box[1] + block.box[3]) / 2 < bottom - 0.5
                and not block.text.startswith(("Наименование НТД", "Виды работ", "Примечание"))
                and not block.text.strip().isdigit()
            )
        texts = tuple(
            " ".join(block.text for block in sorted(selected[index], key=lambda item: item.box[1]))
            for index in range(3)
        )
        if not texts[0] or not texts[2]:
            raise ValueError(
                f"NTD_TABLE_ROW_REQUIRED_COLUMN_MISSING:{layout.page_number}:{ordinal}"
            )
        boxes = tuple(block.box for blocks in selected.values() for block in blocks)
        locator = GuideLocator(layout.page_number, _normalized_region(_union_boxes(boxes), layout))
        identity_payload = {
            "profile": NTD_TABLE_ROW_PROFILE_VERSION,
            "source_version_id": str(source_version_id),
            "page_number": layout.page_number,
            "row_ordinal": ordinal,
            "columns": texts,
            "locator": locator.key,
        }
        row_id = deterministic_uuid(f"guide-source-row:{digest_of(identity_payload)}")
        parent_candidate_id = (
            parent_candidates_by_ordinal[ordinal]
            if parent_candidates_by_ordinal is not None
            else deterministic_uuid(f"guide-source-row-parent:{row_id}")
        )
        rows.append(
            GuideSourceRow(
                source_row_id=row_id,
                parent_candidate_id=parent_candidate_id,
                parent_candidate_version=1,
                source_version_id=source_version_id,
                page_number=layout.page_number,
                row_ordinal=ordinal,
                locator=locator,
                printed_ntd=texts[0],
                work_or_rd_sections=texts[1],
                id_note=texts[2],
                layout_profile_version=NTD_TABLE_ROW_PROFILE_VERSION,
                extraction_digest=layout.extraction_digest,
                parent_failed_receipt_digest=parent_failed_receipt_digest,
            )
        )
    return tuple(rows)


def _lexical_units(words: tuple[NativeWord, ...]) -> tuple[tuple[str, NativeWord], ...]:
    units: list[tuple[str, NativeWord]] = []
    for word in words:
        tokens = re.findall(r"(?:[^\W_]|№)+", word.text.casefold())
        for token in tokens:
            units.append((token, word))
    return tuple(units)


def locate_source_phrase(layout: NativePageLayout, source_phrase: str) -> GuideLocator:
    """Locate an existing failed semantic candidate by deterministic token alignment."""

    page_units = _lexical_units(layout.words)
    target_tokens = tuple(re.findall(r"(?:[^\W_]|№)+", source_phrase.casefold()))
    if len(target_tokens) < 4:
        raise ValueError("NATIVE_GROUNDING_TARGET_TOO_SHORT")
    best_start = -1
    best_length = 0
    for page_start in range(len(page_units)):
        for target_start in range(len(target_tokens)):
            length = 0
            while (
                page_start + length < len(page_units)
                and target_start + length < len(target_tokens)
                and page_units[page_start + length][0] == target_tokens[target_start + length]
            ):
                length += 1
            if length > best_length:
                best_start, best_length = page_start, length
    required = max(6, int(len(target_tokens) * 0.55))
    if best_start < 0 or best_length < required:
        raise ValueError(f"NATIVE_GROUNDING_INSUFFICIENT:{best_length}/{len(target_tokens)}")
    matched_words = tuple(
        page_units[index][1] for index in range(best_start, best_start + best_length)
    )
    return GuideLocator(
        layout.page_number,
        _normalized_region(_union_boxes(tuple(_word_box(word) for word in matched_words)), layout),
    )


def native_layout_to_wire(layout: NativePageLayout) -> dict[str, Any]:
    return {
        "page_number": layout.page_number,
        "width_points": layout.width_points,
        "height_points": layout.height_points,
        "extraction_digest": layout.extraction_digest,
        "omitted_control_glyph_count": layout.omitted_control_glyph_count,
        "blocks": [
            {
                "text": block.text,
                "box_points": list(block.box),
                "lines": [
                    {
                        "text": line.text,
                        "box_points": list(line.box),
                        "words": [
                            {"text": word.text, "box_points": list(_word_box(word))}
                            for word in line.words
                        ],
                    }
                    for line in block.lines
                ],
            }
            for block in layout.blocks
        ],
    }
