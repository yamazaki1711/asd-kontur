from __future__ import annotations

# ruff: noqa: RUF001 -- exact synthetic Cyrillic designations exercise normalization.
from uuid import UUID

import pytest

from asd_kontur.ntd.identifiers import NormativeDocumentKind, normalize_identifier
from asd_kontur.ntd.manifest import build_seed_manifest
from asd_kontur.practice_guidance.native_layout import (
    NativeBlock,
    NativeLine,
    NativePageLayout,
    NativeWord,
)

GUIDE_EDITION_ID = UUID("4a083b70-4a57-4c79-9b86-b4078cce6971")
SOURCE_VERSION_ID = UUID("14e65ad4-a23b-46bc-82c6-510f31f3d957")

PAGE_16 = (
    "Приказ Минстроя №1026/пр от 02.12.2022",
    "СП 543.1325800.2024",
    "СП 68.13330.2017",
    "ГОСТ Р 51872-2024",
    "СП 70.13330.2012",
    "СП 48.13330.2019",
    "СП 45.13330.2017",
    "СП 71.13330.2017",
    "И 1.13-07",
    "СП 77.13330.2016",
    "СП 73.13330.2016",
)
PAGE_17 = (
    "СП 347.1325800.2017",
    "СП 129.13330.2019",
    "СП 74.13330.2023",
    "СП 392.1325800.2018",
    "СП 341.1325800.2017",
    "СП 361.1325800.2017",
    "СП 42-101-2003",
    "ГОСТ 32755-2014",
    "ГОСТ 32756-2014",
    "ГОСТ Р 59492-2021",
    "ГОСТ Р 70108-2025",
)


def _block(text: str, x0: float, y0: float, x1: float | None = None) -> NativeBlock:
    words = tuple(
        NativeWord(token, x0 + index * 4, y0, min((x1 or x0 + 120), x0 + index * 4 + 3), y0 + 5)
        for index, token in enumerate(text.split())
    )
    return NativeBlock((NativeLine(words),))


def _simple_page(page: int, values: tuple[str, ...]) -> NativePageLayout:
    return NativePageLayout(
        page_number=page,
        width_points=420,
        height_points=595,
        blocks=tuple(_block(value, 55, 60 + index * 30, 360) for index, value in enumerate(values)),
        extraction_digest="sha256:" + f"{page:064x}",
    )


def _table_page(page: int, identifiers: tuple[str, ...]) -> NativePageLayout:
    blocks: list[NativeBlock] = []
    for index, identifier in enumerate(identifiers):
        y = 80 + index * 40
        blocks.extend(
            (
                _block(identifier, 55, y, 180),
                _block("synthetic work", 190, y, 260),
                _block("synthetic note", 290, y, 360),
            )
        )
    return NativePageLayout(
        page_number=page,
        width_points=420,
        height_points=595,
        blocks=tuple(blocks),
        extraction_digest="sha256:" + f"{page:064x}",
    )


def test_exact_seed_manifest_reconciles_37_mentions_and_25_identities() -> None:
    layouts = (
        _simple_page(
            15,
            (
                "Приказ Минстроя №344/пр от 16.05.2023",
                "Приказ Минстроя №344/пр от 16.05.2023",
            ),
        ),
        _table_page(16, PAGE_16),
        _table_page(17, PAGE_17),
        _simple_page(18, ("Приказ Минстроя №344/пр от 16.05.2023",) * 6),
        _simple_page(
            19,
            (
                "ГОСТ Р 51872-2024",
                "ГОСТ Р 51872-2024",
                "ГОСТ Р 58973 и ГОСТ 31937-2024",
                "СП 543.1325800.2024",
                "Приказ Минстроя №1026/пр от 02.12.2022",
                "приказом Минстроя 344/пр",
            ),
        ),
    )

    manifest = build_seed_manifest(
        practice_guide_edition_id=GUIDE_EDITION_ID,
        source_version_id=SOURCE_VERSION_ID,
        layouts=layouts,
    )

    assert manifest.raw_mention_count == 37
    assert manifest.identity_count == 25
    assert manifest.page_counts == ((15, 2), (16, 11), (17, 11), (18, 6), (19, 7))
    assert manifest.fingerprint.startswith("sha256:")
    assert len({reference.reference_id for reference in manifest.references}) == 37


def test_identifier_normalization_separates_document_from_printed_edition() -> None:
    sp = normalize_identifier("СП 543.1325800.2024")
    gost_without_year = normalize_identifier("ГОСТ Р 58973")
    order_without_date = normalize_identifier("приказом Минстроя 344/пр")

    assert sp.stable_identity_key == "ru:sp:543.1325800"
    assert sp.printed_edition == "2024"
    assert gost_without_year.stable_identity_key == "ru:gost-r:58973"
    assert gost_without_year.printed_edition is None
    assert order_without_date.stable_identity_key == "ru:minstroy:order:date-unresolved:344-pr"
    assert order_without_date.printed_edition is None
    assert order_without_date.document_kind is NormativeDocumentKind.MINSTROY_ORDER


def test_order_identity_includes_exact_date_and_manifest_resolves_number_only_occurrence() -> None:
    exact = normalize_identifier("Приказ Минстроя №344/пр от 16.05.2023")
    assert exact.stable_identity_key == "ru:minstroy:order:2023-05-16:344-pr"
    assert exact.printed_edition == "16.05.2023"


def test_manifest_fails_closed_on_missing_page() -> None:
    with pytest.raises(ValueError, match="EXACT_PAGES"):
        build_seed_manifest(
            practice_guide_edition_id=GUIDE_EDITION_ID,
            source_version_id=SOURCE_VERSION_ID,
            layouts=(_simple_page(15, ("ГОСТ Р 58973",)),),
        )
