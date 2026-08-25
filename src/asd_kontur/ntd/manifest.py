"""Deterministic guide-page reference discovery for NTD-SEED-01."""

# ruff: noqa: RUF001 -- native guide designations contain exact Cyrillic glyphs.

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of
from asd_kontur.practice_guidance.native_layout import (
    NativeBlock,
    NativePageLayout,
    reconstruct_ntd_source_rows,
)

from .identifiers import NormalizedNormativeIdentifier, normalize_identifier

NTD_SEED_MANIFEST_PROFILE_VERSION = "practice_guide_ntd_seed_manifest_v0.1"
EXPECTED_PAGES = (15, 16, 17, 18, 19)
EXPECTED_RAW_MENTIONS = 37
EXPECTED_IDENTITIES = 25

_DESIGNATION = re.compile(
    r"(?i)(?:"
    r"Приказ(?:ом)?\s+Минстроя(?:\s+России)?[^«»\n]{0,55}?(?:№\s*)?\d+\s*/\s*пр"
    r"(?:[^«»\n]{0,35}?\d{2}\.\d{2}\.\d{4}(?:\s*г\.)?)?"
    r"|СП\s+\d+(?:[.-]\d+)+"
    r"|ГОСТ(?:\s+Р)?\s+\d+(?:-\d{4})?"
    r"|И\s+\d+\.\d+-\d+"
    r")"
)


@dataclass(frozen=True, slots=True)
class PracticeGuideNormativeReference:
    reference_id: UUID
    practice_guide_edition_id: UUID
    source_version_id: UUID
    pdf_page: int
    region: tuple[float, float, float, float]
    occurrence_ordinal: int
    raw_designation: str
    raw_title: str | None
    raw_context: str
    normalized: NormalizedNormativeIdentifier
    extraction_method: str
    extraction_receipt_digest: str
    source_fragment_digest: str
    verification_status: str = "geometry_verified_semantics_unresolved"

    @property
    def locator_key(self) -> str:
        values = ",".join(f"{value:.12f}" for value in self.region)
        return f"page={self.pdf_page};region={values}"


@dataclass(frozen=True, slots=True)
class PracticeGuideNtdSeedManifest:
    profile_version: str
    practice_guide_edition_id: UUID
    source_version_id: UUID
    references: tuple[PracticeGuideNormativeReference, ...]
    identity_keys: tuple[str, ...]
    page_counts: tuple[tuple[int, int], ...]
    fingerprint: str

    @property
    def raw_mention_count(self) -> int:
        return len(self.references)

    @property
    def identity_count(self) -> int:
        return len(self.identity_keys)

    def as_receipt(self) -> dict[str, Any]:
        return {
            "profile_version": self.profile_version,
            "practice_guide_edition_id": str(self.practice_guide_edition_id),
            "source_version_id": str(self.source_version_id),
            "raw_mention_count": self.raw_mention_count,
            "identity_count": self.identity_count,
            "page_counts": dict(self.page_counts),
            "references": [
                {
                    **asdict(reference),
                    "reference_id": str(reference.reference_id),
                    "practice_guide_edition_id": str(reference.practice_guide_edition_id),
                    "source_version_id": str(reference.source_version_id),
                }
                for reference in self.references
            ],
            "identity_keys": list(self.identity_keys),
            "fingerprint": self.fingerprint,
        }


def build_seed_manifest(
    *,
    practice_guide_edition_id: UUID,
    source_version_id: UUID,
    layouts: tuple[NativePageLayout, ...],
) -> PracticeGuideNtdSeedManifest:
    """Build and reconcile the exact bounded manifest from native PDF geometry."""

    if tuple(layout.page_number for layout in layouts) != EXPECTED_PAGES:
        raise ValueError("NTD_SEED_REQUIRES_EXACT_PAGES_15_TO_19")
    references: list[PracticeGuideNormativeReference] = []
    for layout in layouts:
        if layout.page_number in (16, 17):
            rows = reconstruct_ntd_source_rows(
                source_version_id=source_version_id,
                layout=layout,
                parent_failed_receipt_digest="sha256:" + "0" * 64,
            )
            for row in rows:
                references.extend(
                    _references_from_text(
                        practice_guide_edition_id=practice_guide_edition_id,
                        source_version_id=source_version_id,
                        layout=layout,
                        region=row.locator.region,
                        raw_context=" | ".join(
                            (row.printed_ntd, row.work_or_rd_sections, row.id_note)
                        ),
                        designation_text=row.printed_ntd,
                        extraction_method="native_pdf_three_column_row_v0.1",
                        extraction_receipt_digest=layout.extraction_digest,
                        starting_ordinal=len(references) + 1,
                    )
                )
        else:
            for block in layout.blocks:
                if _DESIGNATION.search(block.text):
                    references.extend(
                        _references_from_block(
                            practice_guide_edition_id=practice_guide_edition_id,
                            source_version_id=source_version_id,
                            layout=layout,
                            block=block,
                            starting_ordinal=len(references) + 1,
                        )
                    )
    page_counts = tuple(
        (page, sum(reference.pdf_page == page for reference in references))
        for page in EXPECTED_PAGES
    )
    identity_keys = tuple(
        sorted({reference.normalized.stable_identity_key for reference in references})
    )
    if len(references) != EXPECTED_RAW_MENTIONS or len(identity_keys) != EXPECTED_IDENTITIES:
        raise ValueError(
            "NTD_SEED_MANIFEST_RECONCILIATION_FAILED:"
            f"mentions={len(references)};identities={len(identity_keys)}"
        )
    fingerprint_payload = {
        "profile_version": NTD_SEED_MANIFEST_PROFILE_VERSION,
        "practice_guide_edition_id": str(practice_guide_edition_id),
        "source_version_id": str(source_version_id),
        "page_counts": page_counts,
        "references": [
            {
                "reference_id": str(reference.reference_id),
                "page": reference.pdf_page,
                "region": reference.region,
                "raw_designation": reference.raw_designation,
                "identity": reference.normalized.stable_identity_key,
                "fragment": reference.source_fragment_digest,
                "receipt": reference.extraction_receipt_digest,
            }
            for reference in references
        ],
    }
    return PracticeGuideNtdSeedManifest(
        profile_version=NTD_SEED_MANIFEST_PROFILE_VERSION,
        practice_guide_edition_id=practice_guide_edition_id,
        source_version_id=source_version_id,
        references=tuple(references),
        identity_keys=identity_keys,
        page_counts=page_counts,
        fingerprint=digest_of(fingerprint_payload),
    )


def _references_from_block(
    *,
    practice_guide_edition_id: UUID,
    source_version_id: UUID,
    layout: NativePageLayout,
    block: NativeBlock,
    starting_ordinal: int,
) -> tuple[PracticeGuideNormativeReference, ...]:
    box = block.box
    region = (
        box[0] / layout.width_points,
        box[1] / layout.height_points,
        box[2] / layout.width_points,
        box[3] / layout.height_points,
    )
    return _references_from_text(
        practice_guide_edition_id=practice_guide_edition_id,
        source_version_id=source_version_id,
        layout=layout,
        region=region,
        raw_context=block.text,
        designation_text=block.text,
        extraction_method="native_pdf_block_geometry_v0.1",
        extraction_receipt_digest=layout.extraction_digest,
        starting_ordinal=starting_ordinal,
    )


def _references_from_text(
    *,
    practice_guide_edition_id: UUID,
    source_version_id: UUID,
    layout: NativePageLayout,
    region: tuple[float, float, float, float],
    raw_context: str,
    designation_text: str,
    extraction_method: str,
    extraction_receipt_digest: str,
    starting_ordinal: int,
) -> tuple[PracticeGuideNormativeReference, ...]:
    found: list[PracticeGuideNormativeReference] = []
    raw_title = _quoted_title(raw_context)
    for offset, match in enumerate(_DESIGNATION.finditer(designation_text)):
        raw_designation = " ".join(match.group(0).split()).strip(" .;,:")
        normalized = normalize_identifier(raw_designation)
        fragment_digest = "sha256:" + hashlib.sha256(raw_context.encode("utf-8")).hexdigest()
        identity_payload = {
            "guide_edition": str(practice_guide_edition_id),
            "source_version": str(source_version_id),
            "page": layout.page_number,
            "region": region,
            "occurrence": starting_ordinal + offset,
            "raw_designation": raw_designation,
            "fragment_digest": fragment_digest,
        }
        found.append(
            PracticeGuideNormativeReference(
                reference_id=deterministic_uuid(
                    f"practice-guide-ntd-reference:{digest_of(identity_payload)}"
                ),
                practice_guide_edition_id=practice_guide_edition_id,
                source_version_id=source_version_id,
                pdf_page=layout.page_number,
                region=region,
                occurrence_ordinal=starting_ordinal + offset,
                raw_designation=raw_designation,
                raw_title=raw_title,
                raw_context=raw_context,
                normalized=normalized,
                extraction_method=extraction_method,
                extraction_receipt_digest=extraction_receipt_digest,
                source_fragment_digest=fragment_digest,
            )
        )
    return tuple(found)


def _quoted_title(value: str) -> str | None:
    match = re.search(r"«([^»]+)»", value)
    return " ".join(match.group(1).split()) if match else None
