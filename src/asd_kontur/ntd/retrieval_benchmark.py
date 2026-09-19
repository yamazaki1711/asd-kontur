"""Deterministic evaluation contracts for the NTD retrieval qualification corpus."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any


@dataclass(frozen=True, slots=True)
class GoldQuery:
    case_id: str
    category: str
    query: str
    relevant_documents: tuple[str, ...]
    relevant_pages: tuple[tuple[str, int], ...]
    relevant_clauses: tuple[tuple[str, str], ...]
    expected_negative: bool
    expected_exact_designation: str | None


@dataclass(frozen=True, slots=True)
class RetrievedItem:
    document_digest: str
    page_number: int | None
    clause_label: str | None
    score: float


@dataclass(frozen=True, slots=True)
class QueryRun:
    case_id: str
    items: tuple[RetrievedItem, ...]
    latency_ms: float
    resolved_designation: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    query_count: int
    document_recall_at_1: float
    document_recall_at_5: float
    document_recall_at_10: float
    page_recall_at_1: float
    page_recall_at_5: float
    page_recall_at_10: float
    clause_recall_at_1: float
    clause_recall_at_5: float
    clause_recall_at_10: float
    mean_reciprocal_rank: float
    ndcg_at_10: float
    exact_designation_accuracy: float
    wrong_document_rate: float
    irrelevant_context_rate: float
    negative_query_precision: float
    latency_p50_ms: float
    latency_p95_ms: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "query_count": self.query_count,
            "document_recall_at_1": self.document_recall_at_1,
            "document_recall_at_5": self.document_recall_at_5,
            "document_recall_at_10": self.document_recall_at_10,
            "page_recall_at_1": self.page_recall_at_1,
            "page_recall_at_5": self.page_recall_at_5,
            "page_recall_at_10": self.page_recall_at_10,
            "clause_recall_at_1": self.clause_recall_at_1,
            "clause_recall_at_5": self.clause_recall_at_5,
            "clause_recall_at_10": self.clause_recall_at_10,
            "mean_reciprocal_rank": self.mean_reciprocal_rank,
            "ndcg_at_10": self.ndcg_at_10,
            "exact_designation_accuracy": self.exact_designation_accuracy,
            "wrong_document_rate": self.wrong_document_rate,
            "irrelevant_context_rate": self.irrelevant_context_rate,
            "negative_query_precision": self.negative_query_precision,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
        }


def load_gold_benchmark(path: Path) -> tuple[GoldQuery, ...]:
    """Load and validate the immutable, source-grounded benchmark definition."""

    value = json.loads(path.read_bytes())
    if value.get("profile") != "ntd-retrieval-gold@2.0.0":
        raise ValueError("ntd_gold_profile_invalid")
    raw_cases = value.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) < 100:
        raise ValueError("ntd_gold_denominator_below_100")
    result: list[GoldQuery] = []
    seen: set[str] = set()
    for raw in raw_cases:
        case_id = str(raw["case_id"])
        if case_id in seen:
            raise ValueError("ntd_gold_case_id_duplicate")
        seen.add(case_id)
        documents = tuple(str(item) for item in raw.get("relevant_documents", []))
        pages = tuple(
            (str(item["document_digest"]), int(item["page_number"]))
            for item in raw.get("relevant_pages", [])
        )
        clauses = tuple(
            (str(item["document_digest"]), str(item["clause_label"]))
            for item in raw.get("relevant_clauses", [])
        )
        negative = bool(raw.get("expected_negative", False))
        if negative and (documents or pages or clauses):
            raise ValueError("ntd_gold_negative_has_relevant_source")
        if not negative and not documents:
            raise ValueError("ntd_gold_positive_without_document")
        result.append(
            GoldQuery(
                case_id,
                str(raw["category"]),
                str(raw["query"]),
                documents,
                pages,
                clauses,
                negative,
                (
                    str(raw["expected_exact_designation"])
                    if raw.get("expected_exact_designation") is not None
                    else None
                ),
            )
        )
    return tuple(result)


def evaluate_retrieval(
    gold: tuple[GoldQuery, ...],
    runs: tuple[QueryRun, ...],
) -> RetrievalMetrics:
    """Evaluate one retrieval pipeline without asking a model to grade itself."""

    by_case = {run.case_id: run for run in runs}
    if set(by_case) != {case.case_id for case in gold}:
        raise ValueError("ntd_benchmark_run_denominator_mismatch")
    positives = [case for case in gold if not case.expected_negative]
    page_cases = [case for case in positives if case.relevant_pages]
    clause_cases = [case for case in positives if case.relevant_clauses]
    exact_cases = [case for case in gold if case.expected_exact_designation is not None]
    negative_cases = [case for case in gold if case.expected_negative]

    def document_recall(case: GoldQuery, k: int) -> float:
        returned = {item.document_digest for item in by_case[case.case_id].items[:k]}
        return len(returned.intersection(case.relevant_documents)) / len(case.relevant_documents)

    def page_recall(case: GoldQuery, k: int) -> float:
        returned = {
            (item.document_digest, item.page_number)
            for item in by_case[case.case_id].items[:k]
            if item.page_number is not None
        }
        expected = set(case.relevant_pages)
        return len(returned.intersection(expected)) / len(expected)

    def clause_recall(case: GoldQuery, k: int) -> float:
        returned = {
            (item.document_digest, item.clause_label)
            for item in by_case[case.case_id].items[:k]
            if item.clause_label is not None
        }
        expected = set(case.relevant_clauses)
        return len(returned.intersection(expected)) / len(expected)

    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    wrong_documents = 0
    irrelevant_items = 0
    returned_items = 0
    for case in positives:
        items = by_case[case.case_id].items
        first = next(
            (
                rank
                for rank, item in enumerate(items, 1)
                if item.document_digest in case.relevant_documents
            ),
            None,
        )
        reciprocal_ranks.append(0.0 if first is None else 1.0 / first)
        if items and items[0].document_digest not in case.relevant_documents:
            wrong_documents += 1
        gained_documents: set[str] = set()
        gains: list[float] = []
        for item in items[:10]:
            relevant = (
                item.document_digest in case.relevant_documents
                and item.document_digest not in gained_documents
            )
            gains.append(1.0 if relevant else 0.0)
            if relevant:
                gained_documents.add(item.document_digest)
        dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, 1))
        ideal_count = min(len(case.relevant_documents), 10)
        ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
        ndcgs.append(dcg / ideal if ideal else 0.0)
        irrelevant_items += sum(
            item.document_digest not in case.relevant_documents for item in items[:10]
        )
        returned_items += len(items[:10])

    latencies = sorted(run.latency_ms for run in runs)
    return RetrievalMetrics(
        len(gold),
        _mean(document_recall(case, 1) for case in positives),
        _mean(document_recall(case, 5) for case in positives),
        _mean(document_recall(case, 10) for case in positives),
        _mean(page_recall(case, 1) for case in page_cases),
        _mean(page_recall(case, 5) for case in page_cases),
        _mean(page_recall(case, 10) for case in page_cases),
        _mean(clause_recall(case, 1) for case in clause_cases),
        _mean(clause_recall(case, 5) for case in clause_cases),
        _mean(clause_recall(case, 10) for case in clause_cases),
        _mean(reciprocal_ranks),
        _mean(ndcgs),
        _mean(
            1.0
            if by_case[case.case_id].resolved_designation == case.expected_exact_designation
            else 0.0
            for case in exact_cases
        ),
        wrong_documents / len(positives),
        irrelevant_items / returned_items if returned_items else 0.0,
        _mean(1.0 if not by_case[case.case_id].items else 0.0 for case in negative_cases),
        _percentile(latencies, 0.50),
        _percentile(latencies, 0.95),
    )


def _mean(values: Any) -> float:
    materialized = list(values)
    return fmean(materialized) if materialized else 0.0


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, math.ceil(fraction * len(values)) - 1))
    return values[index]
