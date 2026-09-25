from pathlib import Path

import pytest

from asd_kontur.ntd.retrieval_benchmark import (
    QueryRun,
    RetrievedItem,
    evaluate_retrieval,
    load_gold_benchmark,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "ntd_retrieval_gold_v1.json"


def test_gold_benchmark_has_exact_accepted_denominator() -> None:
    cases = load_gold_benchmark(FIXTURE)

    assert len(cases) == 100
    assert len({case.case_id for case in cases}) == 100
    assert sum(case.expected_negative for case in cases) == 5
    assert sum(case.expected_exact_designation is not None for case in cases) == 20


def test_metrics_reward_exact_sources_and_negative_abstention() -> None:
    cases = load_gold_benchmark(FIXTURE)
    runs = []
    for case in cases:
        items = (
            ()
            if case.expected_negative
            else tuple(
                RetrievedItem(
                    digest,
                    next((page for item, page in case.relevant_pages if item == digest), None),
                    next(
                        (clause for item, clause in case.relevant_clauses if item == digest), None
                    ),
                    1.0 - index / 100,
                )
                for index, digest in enumerate(case.relevant_documents)
            )
        )
        runs.append(
            QueryRun(
                case.case_id,
                items,
                4.0,
                resolved_designation=case.expected_exact_designation,
            )
        )

    metrics = evaluate_retrieval(cases, tuple(runs))

    assert metrics.query_count == 100
    assert metrics.document_recall_at_10 == 1.0
    assert metrics.mean_reciprocal_rank == 1.0
    assert metrics.exact_designation_accuracy == 1.0
    assert metrics.wrong_document_rate == 0.0
    assert metrics.irrelevant_context_rate == 0.0
    assert metrics.negative_query_precision == 1.0


def test_metrics_reject_incomplete_run_denominator() -> None:
    cases = load_gold_benchmark(FIXTURE)

    with pytest.raises(ValueError, match="ntd_benchmark_run_denominator_mismatch"):
        evaluate_retrieval(cases, ())
