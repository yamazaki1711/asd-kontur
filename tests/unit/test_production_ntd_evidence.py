from typing import Any
from uuid import UUID

import pytest

from asd_kontur.assistant.production_ntd_evidence import production_hit_to_ntd_page_item
from asd_kontur.ntd.production_query import ProductionRetrievalHit


def _make_hit(
    *,
    corpus_object_id: UUID,
    contextual_chunk_id: UUID,
    source_locator_ids: tuple[UUID, ...],
    authority_class: str = "official_binding_recovered",
    page_start: int = 12,
    page_end: int = 13,
    structural_path: str = "Глава 1, Статья 5",
    text: str = "Текст нормативного акта",
    lexical_rank: int | None = 1,
    lexical_score: float | None = 0.95,
    dense_rank: int | None = 2,
    dense_similarity: float | None = 0.88,
    final_score: float = 0.91,
    ranking_reasons: tuple[str, ...] = ("lexical", "dense"),
) -> ProductionRetrievalHit:
    return ProductionRetrievalHit(
        corpus_object_id=corpus_object_id,
        contextual_chunk_id=contextual_chunk_id,
        designation="ФЗ-123",
        title="Тестирование",
        authority_class=authority_class,
        page_start=page_start,
        page_end=page_end,
        structural_path=structural_path,
        text=text,
        source_locator_ids=source_locator_ids,
        lexical_rank=lexical_rank,
        lexical_score=lexical_score,
        dense_rank=dense_rank,
        dense_similarity=dense_similarity,
        final_score=final_score,
        ranking_reasons=ranking_reasons,
    )


def test_production_hit_to_ntd_page_item_canonical_mapping() -> None:
    corpus_id = UUID("11111111-1111-1111-1111-111111111111")
    chunk_id = UUID("22222222-2222-2222-2222-222222222222")
    locator_id_1 = UUID("33333333-3333-3333-3333-333333333333")
    locator_id_2 = UUID("44444444-4444-4444-4444-444444444444")
    source_version_id = UUID("55555555-5555-5555-5555-555555555555")
    edition_id = UUID("66666666-6666-6666-6666-666666666666")

    hit = _make_hit(
        corpus_object_id=corpus_id,
        contextual_chunk_id=chunk_id,
        source_locator_ids=(locator_id_1, locator_id_2),
    )

    result: dict[str, Any] = production_hit_to_ntd_page_item(
        hit,
        source_version_id=source_version_id,
        normative_edition_id=edition_id,
        source_access_href="https://example.com/doc",
    )

    content = result["content"]
    source = result["source"]

    # Content assertions
    assert content["search_document_id"] == str(corpus_id)
    assert content["contextual_chunk_id"] == str(chunk_id)
    assert content["document"] == "ФЗ-123"
    assert content["page"] == 12
    assert content["page_end"] == 13
    assert content["text"] == "Текст нормативного акта"
    assert content["authority"] == "normative_authority"
    assert (
        content["source_text_notice"]
        == "Текст нормативного документа; положения ещё не прошли структурированную проверку"
    )
    assert content["edition"] == ""
    assert content["edition_currency"] == "not_checked"
    assert content["structural_path"] == "Глава 1, Статья 5"

    ranking = content["ranking"]
    assert ranking["lexical_rank"] == 1
    assert ranking["lexical_score"] == 0.95
    assert ranking["dense_rank"] == 2
    assert ranking["dense_similarity"] == 0.88
    assert ranking["final_score"] == 0.91
    assert ranking["reasons"] == ("lexical", "dense")

    # Source assertions
    assert source["source_id"] == str(locator_id_1)
    assert source["source_version_id"] == str(source_version_id)
    assert source["edition_id"] == str(edition_id)
    assert source["authority_layer"] == "normative_authority"
    assert source["title"] == "ФЗ-123 — Тестирование"
    assert source["page"] == 12
    assert source["locator_label"] == "страницы 12-13, Глава 1, Статья 5"
    assert source["fragment"] == "Текст нормативного акта"
    assert source["content_digest"].startswith("sha256:")
    assert source["href"] == "https://example.com/doc#page=12"
    assert source["edition"] == ""
    assert source["edition_currency_notice"] == "Актуальность редакции не проверена"
    assert (
        source["source_text_notice"]
        == "Текст нормативного документа; положения ещё не прошли структурированную проверку"
    )


def test_production_hit_to_ntd_page_item_empty_locator_raises() -> None:
    corpus_id = UUID("11111111-1111-1111-1111-111111111111")
    chunk_id = UUID("22222222-2222-2222-2222-222222222222")

    hit = _make_hit(
        corpus_object_id=corpus_id,
        contextual_chunk_id=chunk_id,
        source_locator_ids=(),
    )

    with pytest.raises(ValueError) as exc_info:
        production_hit_to_ntd_page_item(
            hit,
            source_version_id=None,
            normative_edition_id=None,
            source_access_href="",
        )

    assert str(exc_info.value) == "assistant_production_hit_locator_missing"
