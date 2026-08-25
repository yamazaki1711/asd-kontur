from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from asd_kontur.practice_guidance.intelligence import (
    CONSTRUCTION_PROFILE_VERSION,
    deduplicate_semantic_units,
    semantic_identity_digest,
)
from asd_kontur.practice_guidance.models import (
    GuideLocator,
    IDPracticeIntelligenceUnit,
    PracticeIntelligenceEvidence,
    PracticeIntelligenceKind,
)

GUIDE_ID = UUID("0198f8ae-c954-7000-8000-000000000101")
EDITION_ID = UUID("0198f8ae-c954-7000-8000-000000000102")
COVERAGE_ID = UUID("0198f8ae-c954-7000-8000-000000000103")
SOURCE_ID = UUID("0198f8ae-c954-7000-8000-000000000104")
ZERO = "sha256:" + "0" * 64
ONE = "sha256:" + "1" * 64


def _fixture() -> dict[str, Any]:
    path = Path(__file__).parents[1] / "fixtures/practice_intelligence_semantic_groups.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


POSITIVE_GROUPS = cast(list[dict[str, object]], _fixture()["positive_groups"])


def _unit(
    *,
    identity: int,
    kind: str = "attention_point",
    statement: str = "same-statement",
    page: int = 1,
    applicability: tuple[str, ...] = (),
    work_types: tuple[str, ...] = (),
    uncertainties: tuple[str, ...] = (),
    semantic_unit: str | None = None,
    semantic_dimension: str | None = None,
    fragment_digest: str = ZERO,
    edition_id: UUID = EDITION_ID,
    source_id: UUID = SOURCE_ID,
) -> IDPracticeIntelligenceUnit:
    evidence = PracticeIntelligenceEvidence(
        guidance_unit_id=UUID(int=identity),
        guidance_unit_version=1,
        source_version_id=source_id,
        locator=GuideLocator(page, (0.1, 0.2, 0.8, 0.9)),
        fragment_digest=fragment_digest,
    )
    return IDPracticeIntelligenceUnit(
        intelligence_unit_id=UUID(int=identity + 1000),
        version=1,
        practice_guide_edition_id=edition_id,
        coverage_manifest_id=COVERAGE_ID,
        kind=PracticeIntelligenceKind(kind),
        title=statement,
        instruction=statement,
        rationale=None,
        applicability_conditions=applicability,
        work_types=work_types,
        document_types=(),
        form_types=(),
        workflow_stages=(),
        field_elements=(),
        required_inputs=(),
        evidence_requirements=(),
        allowed_variants=(),
        failure_patterns=(),
        checklist_items=(),
        dependency_refs=(),
        normative_references=(),
        uncertainties=uncertainties,
        evidence=(evidence,),
        construction_profile_version=CONSTRUCTION_PROFILE_VERSION,
        semantic_unit=semantic_unit,
        semantic_dimension=semantic_dimension,
    )


@pytest.mark.parametrize("case", POSITIVE_GROUPS)
def test_exact_duplicate_occurrences_merge_identity_and_preserve_evidence(
    case: dict[str, object],
) -> None:
    pages = [cast(int, value) for value in cast(list[object], case["pages"])]
    inputs = tuple(
        _unit(
            identity=100 + index,
            kind=str(case["kind"]),
            statement=str(case["statement"]),
            page=page,
        )
        for index, page in enumerate(pages)
    )

    merged = deduplicate_semantic_units(inputs, practice_guide_id=GUIDE_ID)

    assert len(merged) == 1
    assert len(merged[0].evidence) == 2
    assert [item.locator.page_number for item in merged[0].evidence] == pages
    assert {item.guidance_unit_id for item in merged[0].evidence} == {
        item.evidence[0].guidance_unit_id for item in inputs
    }


@pytest.mark.parametrize(
    ("left", "right"),
    (
        (
            _unit(identity=1, applicability=("scope-a",)),
            _unit(identity=2, applicability=("scope-b",)),
        ),
        (_unit(identity=3, work_types=("earth",)), _unit(identity=4, work_types=("concrete",))),
        (
            _unit(identity=5, uncertainties=("condition-a",)),
            _unit(identity=6, uncertainties=("exclusion-b",)),
        ),
        (_unit(identity=7, semantic_unit="mm"), _unit(identity=8, semantic_unit="piece")),
        (
            _unit(identity=9, semantic_dimension="length"),
            _unit(identity=10, semantic_dimension="quantity"),
        ),
        (_unit(identity=11, statement="edition-a"), _unit(identity=12, statement="edition-b")),
        (
            _unit(identity=13, uncertainties=("verified",), fragment_digest=ZERO),
            _unit(identity=14, uncertainties=("evidence-contradicted",), fragment_digest=ONE),
        ),
        (_unit(identity=15, page=240), _unit(identity=16, page=241)),
        (
            _unit(identity=17),
            _unit(identity=18, source_id=UUID("0198f8ae-c954-7000-8000-000000000105")),
        ),
        (
            _unit(identity=19),
            _unit(identity=21, edition_id=UUID("0198f8ae-c954-7000-8000-000000000106")),
        ),
    ),
)
def test_semantic_dimensions_prevent_false_merge(
    left: IDPracticeIntelligenceUnit,
    right: IDPracticeIntelligenceUnit,
) -> None:
    merged = deduplicate_semantic_units((left, right), practice_guide_id=GUIDE_ID)
    assert len(merged) == 2


def test_authority_layer_is_part_of_semantic_identity() -> None:
    unit = _unit(identity=20)
    practice = semantic_identity_digest(
        unit, practice_guide_id=GUIDE_ID, authority_layer="methodological_practice"
    )
    normative = semantic_identity_digest(
        unit, practice_guide_id=GUIDE_ID, authority_layer="normative_authority"
    )
    assert practice != normative


def test_occurrence_and_build_identity_do_not_change_semantic_identity() -> None:
    first = _unit(identity=30, page=309)
    second = replace(
        _unit(identity=31, page=309),
        coverage_manifest_id=UUID("0198f8ae-c954-7000-8000-000000000199"),
    )
    assert semantic_identity_digest(first, practice_guide_id=GUIDE_ID) == (
        semantic_identity_digest(second, practice_guide_id=GUIDE_ID)
    )
