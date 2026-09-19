from typing import Any
from uuid import UUID

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.ntd.production_query import ProductionRetrievalHit


def production_hit_to_ntd_page_item(
    hit: ProductionRetrievalHit,
    *,
    source_version_id: UUID | None,
    normative_edition_id: UUID | None,
    source_access_href: str,
) -> dict[str, Any]:
    if not hit.source_locator_ids:
        raise ValueError("assistant_production_hit_locator_missing")

    source_id = hit.source_locator_ids[0]
    authority = (
        "normative_authority"
        if hit.authority_class in {"official", "official_binding_recovered"}
        else "legacy_reference"
    )
    page = hit.page_start
    page_end = hit.page_end
    structural_path = hit.structural_path
    notice = "Текст нормативного документа; положения ещё не прошли структурированную проверку"
    digest = semantic_digest(
        {
            "corpus_object_id": str(hit.corpus_object_id),
            "contextual_chunk_id": str(hit.contextual_chunk_id),
            "text": hit.text,
        }
    )
    href = source_access_href
    if href:
        href += f"#page={page}"
    if page_end == page:
        page_label = f"страница {page}"
    else:
        page_label = f"страницы {page}-{page_end}"
    if structural_path:
        locator_label = f"{page_label}, {structural_path}"
    else:
        locator_label = page_label
    return {
        "content": {
            "search_document_id": str(hit.corpus_object_id),
            "contextual_chunk_id": str(hit.contextual_chunk_id),
            "document": hit.designation,
            "page": page,
            "page_end": page_end,
            "text": hit.text[:6000],
            "authority": authority,
            "source_text_notice": notice,
            "edition": "",
            "edition_currency": "not_checked",
            "structural_path": structural_path,
            "ranking": {
                "lexical_rank": hit.lexical_rank,
                "lexical_score": hit.lexical_score,
                "dense_rank": hit.dense_rank,
                "dense_similarity": hit.dense_similarity,
                "final_score": hit.final_score,
                "reasons": hit.ranking_reasons,
            },
        },
        "source": {
            "source_id": str(source_id),
            "source_version_id": str(source_version_id or hit.corpus_object_id),
            "edition_id": str(normative_edition_id) if normative_edition_id else None,
            "authority_layer": authority,
            "title": f"{hit.designation} — {hit.title}",
            "page": page,
            "locator_label": locator_label,
            "fragment": hit.text[:1000],
            "content_digest": digest,
            "href": href,
            "edition": "",
            "edition_currency_notice": "Актуальность редакции не проверена",
            "source_text_notice": notice,
        },
    }
