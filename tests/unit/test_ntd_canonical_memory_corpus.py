from __future__ import annotations

from typing import Any

import pytest

from asd_kontur.ntd.canonical_memory import (
    GESN_DEFERRED_REFERENCE_COUNT,
    NTD_DENOMINATOR,
    _validated_processing_inputs,
)


def _row(index: int, classification: str) -> dict[str, Any]:
    prefix = "gesn" if classification == "GESN" else "ntd"
    return {
        "sha256": f"{prefix}-{index:03d}",
        "classification": classification,
        "size_bytes": 100,
        "mime": "application/pdf",
        "designation": f"{prefix.upper()} {index}",
        "title": f"Документ {prefix} {index}",
    }


def _rows(
    *,
    ntd: int = NTD_DENOMINATOR,
    gesn: int = GESN_DEFERRED_REFERENCE_COUNT,
) -> list[dict[str, Any]]:
    return [
        *(_row(index, "legacy/reference") for index in range(ntd)),
        *(_row(index, "GESN") for index in range(gesn)),
    ]


def test_validated_processing_inputs_excludes_deferred_gesn() -> None:
    inputs = _validated_processing_inputs(_rows())

    assert len(inputs) == NTD_DENOMINATOR
    assert all(item.authority_class != "gesn_candidate" for item in inputs)
    assert len({item.artifact_digest for item in inputs}) == NTD_DENOMINATOR


@pytest.mark.parametrize(
    ("ntd", "gesn", "outcome"),
    [
        (NTD_DENOMINATOR - 1, GESN_DEFERRED_REFERENCE_COUNT, "117:12"),
        (NTD_DENOMINATOR, GESN_DEFERRED_REFERENCE_COUNT - 1, "118:11"),
    ],
)
def test_validated_processing_inputs_rejects_audit_denominator_drift(
    ntd: int,
    gesn: int,
    outcome: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=rf"ntd_audit_denominator_mismatch:{outcome}",
    ):
        _validated_processing_inputs(_rows(ntd=ntd, gesn=gesn))
