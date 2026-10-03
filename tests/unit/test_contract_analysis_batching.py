from __future__ import annotations

from itertools import pairwise

from asd_kontur.application_spine.postgres import _contract_text_segments


def test_contract_text_segments_preserve_exact_source_and_bound_context() -> None:
    source = ("Clause alpha has bounded text.\n" * 420) + "Final clause."

    ranges = _contract_text_segments(source, max_chars=1_000)

    assert len(ranges) > 1
    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(source)
    assert all(end - start <= 1_000 for start, end in ranges)
    assert all(left[1] == right[0] for left, right in pairwise(ranges))
    assert "".join(source[start:end] for start, end in ranges) == source


def test_contract_text_segments_use_hard_limit_without_breaks() -> None:
    source = "x" * 2_501

    assert _contract_text_segments(source, max_chars=1_000) == (
        (0, 1_000),
        (1_000, 2_000),
        (2_000, 2_501),
    )
