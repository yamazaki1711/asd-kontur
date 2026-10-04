from __future__ import annotations

# ruff: noqa: RUF001 -- Russian engineering identifiers are intentional.
import io
import plistlib
import sys
import zipfile
from pathlib import Path
from threading import Event
from uuid import UUID

import pytest

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.application_spine.models import ClaimedJob, JobKind, JobState, semantic_digest
from asd_kontur.application_spine.object_store import (
    IntakeError,
    WorkspaceObjectStore,
    detect_media_type,
    sanitize_display_name,
    sanitize_relative_path,
)
from asd_kontur.application_spine.postgres import (
    _PROJECT_WORK_FIRST_PASS_BATCH_SIZE,
    _PROJECT_WORK_RECONCILIATION_BATCH_SIZE,
    SpinePersistenceError,
    SpinePostgresRepository,
    _bounded_scope_context_rows,
    _contract_context_batches,
    _cross_document_work_batches,
    _deterministic_scope_requires_semantic_review,
    _effective_project_processing_job_sql,
    _merged_quantity_reviews,
    _merged_work_scope_assertions,
    _priority_semantic_batch_limit,
    _quantities_requiring_semantic_review,
    _quantity_comparison_context_policy,
    _quantity_relationship_batches,
    _reserved_first_pass_classification_batch,
    _semantic_extraction_priority,
    _semantic_recovery_stalled,
    _work_reconciliation_attempt_sets,
    _work_reconciliation_manifest_replays_accepted_pair,
    _work_scope_comparison_context_available,
)
from asd_kontur.application_spine.runtime import _migrate, _render_launchd, _show_logs
from asd_kontur.application_spine.worker import DocumentWorker, _LeaseKeepalive, verify_bytes_digest
from asd_kontur.document_understanding.postgres import _identity_observation_group_key
from asd_kontur.tender.qwen_work_reconciliation import (
    PROJECT_WORK_RECONCILIATION_PROFILE,
)
from asd_kontur.web_app.app import _parse_range

ORGANIZATION_ID = UUID("018f5c3e-7b00-7000-8000-000000001801")
WORKSPACE_ID = UUID("018f5c3e-7b00-7000-8000-000000001802")


def test_project_progress_excludes_explicit_profile_supersession_history() -> None:
    predicate = _effective_project_processing_job_sql("job")

    assert "contract_analysis_profile_superseded" in predicate
    assert "work_reconciliation_profile_superseded" in predicate
    assert "job.state IN ('failed','reconciliation_required')" in predicate


def test_semantic_refill_reserves_first_pass_classification_capacity() -> None:
    assert (
        _priority_semantic_batch_limit(
            max_batches=4,
            ordinary_classification_pending=True,
        )
        == 3
    )
    assert (
        _priority_semantic_batch_limit(
            max_batches=4,
            ordinary_classification_pending=False,
        )
        == 4
    )
    assert (
        _priority_semantic_batch_limit(
            max_batches=1,
            ordinary_classification_pending=True,
        )
        == 1
    )


def test_reserved_first_pass_lane_cannot_be_consumed_by_relationship_work() -> None:
    source_id, batch = _reserved_first_pass_classification_batch(
        {
            "source-a": [
                {
                    "candidate_id": "relationship-high",
                    "wording": "High-priority relationship review",
                    "classification_review_needed": False,
                    "relationship_review_needed": True,
                    "semantic_priority": (500, 10, 10),
                    "quantity_observations": [{"quantity_candidate_id": "quantity-a"}],
                },
                {
                    "candidate_id": "first-pass-lower",
                    "wording": "Previously unseen construction operation",
                    "classification_review_needed": True,
                    "relationship_review_needed": False,
                    "semantic_priority": (100, 1, 1),
                    "quantity_observations": [],
                },
            ],
            "source-b": [
                {
                    "candidate_id": "relationship-other",
                    "wording": "Other relationship review",
                    "classification_review_needed": False,
                    "relationship_review_needed": True,
                    "semantic_priority": (600, 10, 10),
                    "quantity_observations": [],
                }
            ],
        },
        batch_size=2,
    )

    assert source_id == "source-a"
    assert [row["candidate_id"] for row in batch] == ["first-pass-lower"]
    assert "semantic_priority" not in batch[0]


def test_reserved_first_pass_lane_can_use_wider_independent_batch() -> None:
    source_id, batch = _reserved_first_pass_classification_batch(
        {
            "source-a": [
                {
                    "candidate_id": f"first-pass-{index}",
                    "wording": f"Previously unseen construction operation {index}",
                    "classification_review_needed": True,
                    "semantic_priority": (100 - index, 1, 1),
                    "quantity_observations": [],
                }
                for index in range(6)
            ]
        },
        batch_size=4,
    )

    assert source_id == "source-a"
    assert [row["candidate_id"] for row in batch] == [
        "first-pass-0",
        "first-pass-1",
        "first-pass-2",
        "first-pass-3",
    ]


def test_default_work_reconciliation_batch_matches_measured_production_policy() -> None:
    assert _PROJECT_WORK_RECONCILIATION_BATCH_SIZE == 2
    assert _PROJECT_WORK_FIRST_PASS_BATCH_SIZE == 4


def test_semantic_recovery_continues_while_accepted_coverage_advances() -> None:
    assert not _semantic_recovery_stalled(
        latest_state="succeeded",
        coverage_state="partial",
        recovery_contract="engineering-leaf-recovery-v6",
        recovery_attempt=4,
        accepted_fragment_count=38,
        previous_accepted_fragment_count=29,
    )


def test_semantic_recovery_stops_after_bounded_no_progress_attempt() -> None:
    assert _semantic_recovery_stalled(
        latest_state="succeeded",
        coverage_state="partial",
        recovery_contract="engineering-leaf-recovery-v6",
        recovery_attempt=2,
        accepted_fragment_count=38,
        previous_accepted_fragment_count=38,
    )


@pytest.mark.parametrize("coverage_state", ["not_started", "failed", "complete"])
def test_semantic_recovery_stops_for_every_no_progress_coverage_state(
    coverage_state: str,
) -> None:
    assert _semantic_recovery_stalled(
        latest_state="succeeded",
        coverage_state=coverage_state,
        recovery_contract="engineering-leaf-recovery-v6",
        recovery_attempt=1,
        accepted_fragment_count=0 if coverage_state != "complete" else 8,
        previous_accepted_fragment_count=0 if coverage_state != "complete" else 8,
    )


def test_contract_context_batch_keeps_table_row_atomic_at_locator_boundary() -> None:
    rows = [
        {
            "source_locator_id": f"paragraph-{index}",
            "page_number": 1,
            "reading_order": index,
            "element_kind": "paragraph",
            "row_index": None,
            "source_text": f"Пункт {index}",
        }
        for index in range(1, 23)
    ]
    rows.extend(
        {
            "source_locator_id": f"cell-{column}",
            "page_number": 1,
            "reading_order": 22 + column,
            "element_kind": "table_cell",
            "row_index": 7,
            "column_index": column,
            "source_text": value,
        }
        for column, value in enumerate(
            ("Работа", "м3", "36", "6013,83", "216497,88", "Россия"), start=1
        )
    )

    batches = _contract_context_batches(rows, max_locators=24, max_chars=12_000)

    assert [len(batch["rows"]) for batch in batches] == [22, 6]
    assert all(batch["context_complete"] is True for batch in batches)
    assert [row["source_locator_id"] for row in batches[1]["rows"]] == [
        f"cell-{column}" for column in range(1, 7)
    ]


def test_contract_context_marks_oversized_table_row_incomplete() -> None:
    rows = [
        {
            "source_locator_id": f"cell-{column}",
            "page_number": 2,
            "reading_order": column,
            "element_kind": "table_cell",
            "row_index": 3,
            "column_index": column,
            "source_text": f"Значение {column}",
        }
        for column in range(1, 7)
    ]

    batches = _contract_context_batches(rows, max_locators=3, max_chars=12_000)

    assert [len(batch["rows"]) for batch in batches] == [3, 3]
    assert all(batch["context_complete"] is False for batch in batches)


def test_contract_context_default_bounds_strict_output_to_eight_locators() -> None:
    rows = [
        {
            "source_locator_id": f"clause-{index}",
            "page_number": 1,
            "reading_order": index,
            "element_kind": "paragraph",
            "row_index": None,
            "source_text": f"Условие договора {index}",
        }
        for index in range(1, 18)
    ]

    batches = _contract_context_batches(rows)

    assert [len(batch["rows"]) for batch in batches] == [8, 8, 1]
    assert all(batch["context_complete"] is True for batch in batches)


def _work_batch_row(
    candidate_id: str,
    *,
    facility: str,
    family: str,
    document_role: str,
    wording: str,
    quantity_count: int = 1,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "candidate_version": 1,
        "wording": wording,
        "document_role": document_role,
        "document": f"Документ {candidate_id}",
        "page": 1,
        "scope": "",
        "facility_hints": [facility],
        "deterministic_family_hint": family,
        "nearby_context": wording,
        "nearby_context_locator_ids": [],
        "quantity_observations": [
            {"candidate_id": f"{candidate_id}-quantity-{index}"} for index in range(quantity_count)
        ],
        "source_version_id": f"source-{candidate_id}",
        "source_locator_id": f"locator-{candidate_id}",
        "semantic_priority": (100, 1, 1),
    }


@pytest.mark.parametrize(
    ("facility", "family", "design_wording", "commercial_wording"),
    (
        ("Мост через реку Северную", "pile_foundation", "Бурение свай", "Устройство свай"),
        ("Участок водовода № 7", "pipeline", "Прокладка трубы", "Монтаж трубопровода"),
    ),
)
def test_cross_document_work_batches_are_project_independent(
    facility: str,
    family: str,
    design_wording: str,
    commercial_wording: str,
) -> None:
    rows = [
        _work_batch_row(
            "design",
            facility=facility,
            family=family,
            document_role="Рабочая документация",
            wording=design_wording,
        ),
        _work_batch_row(
            "commercial",
            facility=facility,
            family=family,
            document_role="Ведомость объемов работ",
            wording=commercial_wording,
        ),
    ]

    batches, selected = _cross_document_work_batches(rows, batch_size=8, max_batches=4)

    assert [[value["candidate_id"] for value in batch] for batch in batches] == [
        ["design", "commercial"]
    ]
    assert selected == {"design", "commercial"}
    assert all("comparison_side" not in value for value in batches[0])
    assert {value["analysis_task"] for value in batches[0]} == {"CROSS_DOCUMENT_SCOPE_MATCHING"}


def test_cross_document_work_batches_skip_only_the_attempted_scope_pair() -> None:
    rows = [
        _work_batch_row(
            "design",
            facility="Gallery B",
            family="structural_steel",
            document_role="Рабочая документация",
            wording="Install roof trusses",
        ),
        _work_batch_row(
            "commercial-a",
            facility="Gallery B",
            family="structural_steel",
            document_role="Смета",
            wording="Erect roof trusses",
        ),
        _work_batch_row(
            "commercial-b",
            facility="Gallery B",
            family="structural_steel",
            document_role="Смета",
            wording="Install roof bracing",
        ),
    ]

    batches, selected = _cross_document_work_batches(
        rows,
        batch_size=2,
        max_batches=1,
        attempted_pairs={("commercial-a", "design")},
    )

    assert [[value["candidate_id"] for value in batch] for batch in batches] == [
        ["design", "commercial-b"]
    ]
    assert selected == {"design", "commercial-b"}


def test_cross_document_work_batches_do_not_mix_scope_or_one_sided_rows() -> None:
    rows = [
        _work_batch_row(
            "bridge-design",
            facility="Мост",
            family="pile_foundation",
            document_role="Рабочая документация",
            wording="Бурение свай",
        ),
        _work_batch_row(
            "building-commercial",
            facility="Административное здание",
            family="pile_foundation",
            document_role="Смета",
            wording="Устройство свай",
        ),
        _work_batch_row(
            "bridge-pipeline-commercial",
            facility="Мост",
            family="pipeline",
            document_role="Смета",
            wording="Прокладка водоотвода",
        ),
    ]

    batches, selected = _cross_document_work_batches(rows, batch_size=8, max_batches=4)

    assert batches == []
    assert selected == set()


def test_cross_document_work_batches_preserve_quantity_context_bound() -> None:
    rows = [
        _work_batch_row(
            "design",
            facility="Резервуар",
            family="reinforced_concrete",
            document_role="Проектная документация",
            wording="Устройство стен резервуара",
            quantity_count=9,
        ),
        _work_batch_row(
            "commercial",
            facility="Резервуар",
            family="reinforced_concrete",
            document_role="Локальная смета",
            wording="Бетонирование стен",
            quantity_count=7,
        ),
        _work_batch_row(
            "extra",
            facility="Резервуар",
            family="reinforced_concrete",
            document_role="Локальная смета",
            wording="Устройство железобетонных стен",
            quantity_count=2,
        ),
    ]

    batches, selected = _cross_document_work_batches(rows, batch_size=8, max_batches=4)

    assert len(batches) == 1
    assert sum(len(row["quantity_observations"]) for row in batches[0]) <= 16
    assert selected == {"design", "extra"}


def test_cross_document_work_batches_review_exact_wording_without_location() -> None:
    rows = [
        _work_batch_row(
            "design",
            facility="",
            family="structural_steel",
            document_role="Рабочая документация",
            wording="Монтаж стальных балок покрытия",
            quantity_count=1,
        ),
        _work_batch_row(
            "commercial",
            facility="",
            family="structural_steel",
            document_role="Смета",
            wording="Монтаж стальных балок покрытия",
            quantity_count=1,
        ),
        _work_batch_row(
            "other-commercial",
            facility="",
            family="structural_steel",
            document_role="Смета",
            wording="Монтаж связей покрытия",
            quantity_count=1,
        ),
    ]

    batches, selected = _cross_document_work_batches(rows, batch_size=8, max_batches=4)

    assert [[value["candidate_id"] for value in batch] for batch in batches] == [
        ["design", "commercial"]
    ]
    assert selected == {"design", "commercial"}


def test_work_scope_assertions_are_preserved_across_exact_pair_reviews() -> None:
    combined = _merged_work_scope_assertions(
        [
            {
                "related_candidate_id": "commercial-a",
                "scope_compatibility": "SAME_SCOPE",
                "normalized_operation": "Монтаж ферм",
                "reason": "Один объём работ.",
            }
        ],
        [
            {
                "related_candidate_id": "commercial-b",
                "scope_compatibility": "DIFFERENT_SCOPE",
                "normalized_operation": None,
                "reason": "Связи покрытия являются другой операцией.",
            }
        ],
    )

    assert [value["related_candidate_id"] for value in combined] == [
        "commercial-a",
        "commercial-b",
    ]


def test_cross_document_work_batches_send_unlocated_family_synonyms_for_semantic_review() -> None:
    rows = [
        _work_batch_row(
            "design",
            facility="",
            family="waterproofing",
            document_role="Проектная документация",
            wording="Гидроизоляция фундаментной плиты",
        ),
        _work_batch_row(
            "commercial",
            facility="",
            family="waterproofing",
            document_role="Ведомость объемов работ",
            wording="Гидроизоляция наружных стен",
        ),
    ]

    batches, selected = _cross_document_work_batches(rows, batch_size=8, max_batches=4)

    assert [[value["candidate_id"] for value in batch] for batch in batches] == [
        ["design", "commercial"]
    ]
    assert selected == {"design", "commercial"}
    assert {value["analysis_task"] for value in batches[0]} == {"CROSS_DOCUMENT_SCOPE_MATCHING"}


def test_scope_context_is_bounded_before_source_context_loading() -> None:
    rows = [
        {
            "candidate_id": "design-alpha",
            "source_version_id": "source-design",
            "source_role": "project_documentation",
            "wording": "Install access platform",
            "deterministic_family_hint": "structural_steel",
            "scope_comparison_context_only": True,
            "prior_resolution": {"facility": "Utility Building Alpha"},
        },
        {
            "candidate_id": "commercial-alpha",
            "source_version_id": "source-commercial",
            "source_role": "local_estimate",
            "wording": "Access platform installation",
            "deterministic_family_hint": "structural_steel",
            "scope_comparison_context_only": True,
            "prior_resolution": {"facility": "Utility Building Alpha"},
        },
        {
            "candidate_id": "design-without-counterpart",
            "source_version_id": "source-design",
            "source_role": "project_documentation",
            "wording": "Apply protective coating",
            "deterministic_family_hint": "finishing",
            "scope_comparison_context_only": True,
            "prior_resolution": {"facility": "Utility Building Beta"},
        },
        {
            "candidate_id": "ordinary-unresolved",
            "source_version_id": "source-design",
            "source_role": "project_documentation",
            "wording": "Unresolved operation",
            "scope_comparison_context_only": False,
        },
    ]

    selected = _bounded_scope_context_rows(
        rows,
        source_display_names={
            "source-design": "Design package Z.pdf",
            "source-commercial": "Commercial schedule Q.pdf",
        },
        source_role_contexts={},
        attempted_pairs=set(),
        max_batches=1,
    )

    assert {value["candidate_id"] for value in selected} == {
        "design-alpha",
        "commercial-alpha",
        "ordinary-unresolved",
    }


def test_scope_context_skips_an_exact_pair_already_attempted() -> None:
    rows = [
        {
            "candidate_id": candidate_id,
            "source_version_id": source_id,
            "source_role": role,
            "wording": "Install drainage channel",
            "deterministic_family_hint": "drainage",
            "scope_comparison_context_only": True,
            "prior_resolution": {},
        }
        for candidate_id, source_id, role in (
            ("design-drainage", "source-design", "project_documentation"),
            ("commercial-drainage", "source-commercial", "local_estimate"),
        )
    ]

    selected = _bounded_scope_context_rows(
        rows,
        source_display_names={},
        source_role_contexts={},
        attempted_pairs={("commercial-drainage", "design-drainage")},
        max_batches=1,
    )

    assert selected == []


def test_scope_context_queues_unlocated_family_synonyms_from_settled_results() -> None:
    rows = [
        {
            "candidate_id": "design-fence",
            "source_version_id": "source-design",
            "source_role": "project_documentation",
            "wording": "Устройство металлического ограждения",
            "deterministic_family_hint": "fencing",
            "scope_comparison_context_only": True,
            "prior_resolution": {"operation": "Устройство металлического ограждения"},
        },
        {
            "candidate_id": "commercial-fence",
            "source_version_id": "source-commercial",
            "source_role": "local_estimate",
            "wording": "Монтаж металлических ограждений",
            "deterministic_family_hint": "fencing",
            "scope_comparison_context_only": True,
            "prior_resolution": {"operation": "Монтаж металлических ограждений"},
        },
        {
            "candidate_id": "commercial-gate",
            "source_version_id": "source-commercial",
            "source_role": "local_estimate",
            "wording": "Монтаж въездных ворот",
            "deterministic_family_hint": "fencing",
            "scope_comparison_context_only": True,
            "prior_resolution": {"operation": "Монтаж въездных ворот"},
        },
    ]

    selected = _bounded_scope_context_rows(
        rows,
        source_display_names={
            "source-design": "Design.pdf",
            "source-commercial": "Estimate.xlsx",
        },
        source_role_contexts={},
        attempted_pairs=set(),
        max_batches=1,
    )

    assert {value["candidate_id"] for value in selected} == {
        "design-fence",
        "commercial-fence",
    }


def test_scope_context_uses_page_role_for_an_embedded_commercial_section() -> None:
    rows = [
        {
            "candidate_id": "design-concrete",
            "source_version_id": "mixed-source",
            "source_locator_id": "design-page-locator",
            "source_role": "project_documentation",
            "wording": "Concrete foundation installation",
            "deterministic_family_hint": "reinforced_concrete",
            "scope_comparison_context_only": True,
            "prior_resolution": {"facility": "Service Hall Gamma"},
        },
        {
            "candidate_id": "commercial-concrete",
            "source_version_id": "mixed-source",
            "source_locator_id": "vor-page-locator",
            "source_role": "project_documentation",
            "wording": "Foundation concreting",
            "deterministic_family_hint": "reinforced_concrete",
            "scope_comparison_context_only": True,
            "prior_resolution": {"facility": "Service Hall Gamma"},
        },
    ]

    selected = _bounded_scope_context_rows(
        rows,
        source_display_names={"mixed-source": "Combined project package.pdf"},
        source_role_contexts={
            "design-page-locator": {"selected_roles": ["project_documentation"]},
            "vor-page-locator": {"selected_roles": ["bill_of_quantities"]},
        },
        attempted_pairs=set(),
        max_batches=1,
    )

    assert {value["candidate_id"] for value in selected} == {
        "design-concrete",
        "commercial-concrete",
    }


def test_known_facility_scope_still_queues_unreviewed_quantities() -> None:
    family = ("pipeline", "Трубопроводы и сети")

    assert _deterministic_scope_requires_semantic_review(
        deterministic_family=family,
        explicit_facility="ЛОС 4",
        linked_quantities=[{"candidate_id": "quantity-1"}],
    )
    assert not _deterministic_scope_requires_semantic_review(
        deterministic_family=family,
        explicit_facility="ЛОС 4",
        linked_quantities=[],
    )
    assert _deterministic_scope_requires_semantic_review(
        deterministic_family=family,
        explicit_facility=None,
        linked_quantities=[],
    )
    assert _deterministic_scope_requires_semantic_review(
        deterministic_family=family,
        explicit_facility="Reservoir Delta",
        linked_quantities=[],
        scope_comparison_context_only=True,
    )


def test_quantity_review_chunks_schedule_relationship_pass_before_completion() -> None:
    quantities = [{"candidate_id": f"quantity-{index}", "value": index} for index in range(10)]
    first_result = {
        "profile_version": PROJECT_WORK_RECONCILIATION_PROFILE,
        "quantity_reviews": [
            {
                "quantity_candidate_id": f"quantity-{index}",
                "status": "WORK_QUANTITY",
            }
            for index in range(8)
        ],
    }

    remaining = _quantities_requiring_semantic_review(quantities, first_result)

    assert [value["candidate_id"] for value in remaining] == [
        f"quantity-{index}" for index in range(10)
    ]

    for review in first_result["quantity_reviews"]:
        review["relationship_reviewed"] = True
    remaining = _quantities_requiring_semantic_review(quantities, first_result)

    assert [value["candidate_id"] for value in remaining] == ["quantity-8", "quantity-9"]


def test_legacy_component_relationship_is_requeued_for_completeness_review() -> None:
    quantities = [
        {"candidate_id": "quantity-total"},
        {"candidate_id": "quantity-part"},
    ]
    prior = {
        "profile_version": PROJECT_WORK_RECONCILIATION_PROFILE,
        "quantity_reviews": [
            {
                "quantity_candidate_id": "quantity-total",
                "status": "WORK_QUANTITY",
                "relation_kind": "TOTAL_FOR",
                "relationship_reviewed": True,
            },
            {
                "quantity_candidate_id": "quantity-part",
                "status": "WORK_QUANTITY",
                "relation_kind": "COMPONENT_OF",
                "relationship_reviewed": True,
            },
        ],
    }

    remaining = _quantities_requiring_semantic_review(quantities, prior)

    assert [value["candidate_id"] for value in remaining] == [
        "quantity-total",
        "quantity-part",
    ]


def test_v31_scope_decision_is_requeued_for_pair_specific_assertions() -> None:
    quantities = [{"candidate_id": "quantity-design"}, {"candidate_id": "quantity-vor"}]
    prior = {
        "profile_version": "qwen-project-work-reconciliation-v31",
        "quantity_reviews": [
            {
                "quantity_candidate_id": value["candidate_id"],
                "status": "WORK_QUANTITY",
                "relation_kind": "NONE",
                "relationship_reviewed": True,
                "scope_compatibility": "SAME_SCOPE",
            }
            for value in quantities
        ],
    }

    remaining = _quantities_requiring_semantic_review(quantities, prior)

    assert [value["candidate_id"] for value in remaining] == [
        "quantity-design",
        "quantity-vor",
    ]


def test_prior_profile_quantity_reviews_are_requeued_for_current_scope_policy() -> None:
    quantities = [{"candidate_id": "quantity-design"}, {"candidate_id": "quantity-vor"}]
    prior = {
        "profile_version": "qwen-project-work-reconciliation-v14",
        "quantity_reviews": [
            {
                "quantity_candidate_id": value["candidate_id"],
                "status": "WORK_QUANTITY",
                "relation_kind": "NONE",
                "relationship_reviewed": True,
                "scope_compatibility": "INSUFFICIENT_INFORMATION",
            }
            for value in quantities
        ],
    }

    assert _quantities_requiring_semantic_review(quantities, prior) == quantities


def test_compatible_terminal_non_quantity_reviews_are_not_reprocessed() -> None:
    quantities = [
        {"candidate_id": "rate"},
        {"candidate_id": "dimension"},
        {"candidate_id": "unrelated"},
        {"candidate_id": "work"},
        {"candidate_id": "duration"},
        {"candidate_id": "ambiguous"},
    ]
    prior = {
        "profile_version": "qwen-project-work-reconciliation-v23",
        "quantity_reviews": [
            {"quantity_candidate_id": "rate", "status": "RESOURCE_OR_RATE"},
            {"quantity_candidate_id": "dimension", "status": "DIMENSION"},
            {"quantity_candidate_id": "unrelated", "status": "UNRELATED"},
            {"quantity_candidate_id": "work", "status": "WORK_QUANTITY"},
            {"quantity_candidate_id": "duration", "status": "DURATION"},
            {"quantity_candidate_id": "ambiguous", "status": "AMBIGUOUS"},
        ],
    }

    remaining = _quantities_requiring_semantic_review(quantities, prior)

    assert [value["candidate_id"] for value in remaining] == [
        "work",
        "duration",
        "ambiguous",
    ]


def test_v24_settled_quantity_is_not_replayed_for_compound_measure_profile() -> None:
    quantities = [{"candidate_id": "single-volume", "normalized_value": "36.4", "raw_unit": "м3"}]
    prior = {
        "profile_version": "qwen-project-work-reconciliation-v24",
        "quantity_reviews": [
            {
                "quantity_candidate_id": "single-volume",
                "status": "WORK_QUANTITY",
                "relationship_reviewed": True,
                "relation_kind": "NONE",
            }
        ],
    }

    assert _quantities_requiring_semantic_review(quantities, prior) == []


def test_v24_compound_quantity_is_requeued_for_exact_measure_selection() -> None:
    quantities = [
        {
            "candidate_id": "compound-area-volume",
            "normalized_value": "420,6/21,03",
            "raw_unit": "м2/м3",
        }
    ]
    prior = {
        "profile_version": "qwen-project-work-reconciliation-v24",
        "quantity_reviews": [
            {
                "quantity_candidate_id": "compound-area-volume",
                "status": "WORK_QUANTITY",
                "relationship_reviewed": True,
                "relation_kind": "TOTAL_FOR",
                "component_set_complete": False,
            }
        ],
    }

    assert _quantities_requiring_semantic_review(quantities, prior) == quantities


def test_v28_source_value_failure_requeues_only_unresolved_compound_measure() -> None:
    quantities = [
        {
            "candidate_id": "compound-steel-measures",
            "normalized_value": "18,6/2,48",
            "raw_unit": "м/т",
        },
        {
            "candidate_id": "settled-steel-length",
            "normalized_value": "7,4",
            "raw_unit": "м",
        },
    ]
    prior = {
        "profile_version": "qwen-project-work-reconciliation-v28",
        "recovery_codes": ["qwen_work_reconciliation_quantity_source_value_invalid"],
        "quantity_reviews": [
            {
                "quantity_candidate_id": "compound-steel-measures",
                "status": "WORK_QUANTITY",
                "relationship_reviewed": False,
                "relation_kind": "NONE",
            },
            {
                "quantity_candidate_id": "settled-steel-length",
                "status": "WORK_QUANTITY",
                "relationship_reviewed": False,
                "relation_kind": "NONE",
            },
        ],
    }

    assert _quantities_requiring_semantic_review(quantities, prior) == [quantities[0]]


def test_v29_settled_quantity_is_preserved_for_cross_document_work_scope_profile() -> None:
    quantities = [{"candidate_id": "accepted-volume", "normalized_value": "84.2"}]
    prior = {
        "profile_version": "qwen-project-work-reconciliation-v29",
        "quantity_reviews": [
            {
                "quantity_candidate_id": "accepted-volume",
                "status": "WORK_QUANTITY",
                "relationship_reviewed": True,
                "relation_kind": "NONE",
                "scope_compatibility": "SAME_SCOPE",
            }
        ],
    }

    assert _quantities_requiring_semantic_review(quantities, prior) == []


def test_v30_requeues_only_unsupported_alternative_decisions() -> None:
    quantities = [
        {"candidate_id": "same-scope"},
        {"candidate_id": "alternative-relation"},
        {"candidate_id": "alternative-compatibility"},
    ]
    prior = {
        "profile_version": "qwen-project-work-reconciliation-v30",
        "quantity_reviews": [
            {
                "quantity_candidate_id": "same-scope",
                "status": "WORK_QUANTITY",
                "relationship_reviewed": True,
                "relation_kind": "NONE",
                "scope_compatibility": "SAME_SCOPE",
            },
            {
                "quantity_candidate_id": "alternative-relation",
                "status": "WORK_QUANTITY",
                "relationship_reviewed": True,
                "relation_kind": "ALTERNATIVE_TO",
                "scope_compatibility": "ALTERNATIVE_DESIGN",
            },
            {
                "quantity_candidate_id": "alternative-compatibility",
                "status": "WORK_QUANTITY",
                "relationship_reviewed": True,
                "relation_kind": "NONE",
                "scope_compatibility": "ALTERNATIVE_DESIGN",
            },
        ],
    }

    assert _quantities_requiring_semantic_review(quantities, prior) == quantities[1:]


def test_v30_settled_work_does_not_replay_entire_scope_pass() -> None:
    existing = {
        "candidate_version": 2,
        "profile_version": "qwen-project-work-reconciliation-v30",
        "status": "MATCHED",
        "family_key": "structural_steel",
        "facility": "Crossing North",
    }

    assert not _work_scope_comparison_context_available(
        existing=existing,
        candidate_version=2,
        pending_quantities=[],
    )


def test_settled_work_is_reused_only_as_bounded_scope_comparison_context() -> None:
    existing = {
        "candidate_version": 3,
        "profile_version": "qwen-project-work-reconciliation-v29",
        "status": "MATCHED",
        "family_key": "structural_steel",
        "facility": "Gallery B",
    }

    assert _work_scope_comparison_context_available(
        existing=existing,
        candidate_version=3,
        pending_quantities=[],
    )
    assert _work_scope_comparison_context_available(
        existing={**existing, "facility": None},
        candidate_version=3,
        pending_quantities=[],
    )
    assert not _work_scope_comparison_context_available(
        existing=existing,
        candidate_version=3,
        pending_quantities=[{"candidate_id": "unreviewed-mass"}],
    )
    assert not _work_scope_comparison_context_available(
        existing={**existing, "status": "AMBIGUOUS"},
        candidate_version=3,
        pending_quantities=[],
    )


def test_v28_compound_uncertainty_without_typed_failure_is_not_replayed() -> None:
    quantities = [
        {
            "candidate_id": "ambiguous-pipe-measures",
            "normalized_value": "210/14",
            "raw_unit": "м/шт",
        }
    ]
    prior = {
        "profile_version": "qwen-project-work-reconciliation-v28",
        "recovery_codes": [],
        "quantity_reviews": [
            {
                "quantity_candidate_id": "ambiguous-pipe-measures",
                "status": "WORK_QUANTITY",
                "relationship_reviewed": True,
                "relation_kind": "NONE",
            }
        ],
    }

    assert _quantities_requiring_semantic_review(quantities, prior) == []


def test_incompatible_terminal_non_quantity_reviews_are_reprocessed() -> None:
    quantities = [{"candidate_id": "rate"}]
    prior = {
        "profile_version": "qwen-project-work-reconciliation-v2",
        "quantity_reviews": [
            {"quantity_candidate_id": "rate", "status": "RESOURCE_OR_RATE"},
        ],
    }

    assert _quantities_requiring_semantic_review(quantities, prior) == quantities


def test_quantity_relationship_batches_group_by_engineering_context_not_number() -> None:
    rows = [
        _work_batch_row(
            "design",
            facility="Сооружение 7",
            family="earthworks",
            document_role="ПД",
            wording="Разработка грунта",
            quantity_count=2,
        ),
        _work_batch_row(
            "commercial",
            facility="Сооружение 7",
            family="earthworks",
            document_role="Смета",
            wording="Разработка грунта",
            quantity_count=1,
        ),
        _work_batch_row(
            "other-facility",
            facility="Сооружение 8",
            family="earthworks",
            document_role="Смета",
            wording="Разработка грунта",
            quantity_count=1,
        ),
    ]
    for row in rows:
        row["relationship_review_needed"] = True

    batches, selected = _quantity_relationship_batches(rows, batch_size=8, max_batches=4)

    assert len(batches) == 1
    assert {item["candidate_id"] for item in batches[0]} == {"design", "commercial"}
    assert all(
        item["analysis_task"] == "QUANTITY_RELATIONSHIP_ANALYSIS"
        for batch in batches
        for item in batch
    )
    assert selected == {"design", "commercial"}


def test_quantity_relationship_batches_prefer_opposite_document_sides() -> None:
    rows = [
        _work_batch_row(
            "design-high",
            facility="",
            family="reinforced_concrete",
            document_role="Рабочая документация",
            wording="Бетонирование стены",
            quantity_count=1,
        ),
        _work_batch_row(
            "design-low",
            facility="",
            family="reinforced_concrete",
            document_role="Проектная документация",
            wording="Монолитная стена",
            quantity_count=1,
        ),
        _work_batch_row(
            "commercial",
            facility="",
            family="reinforced_concrete",
            document_role="Локальная смета",
            wording="Устройство железобетонной стены",
            quantity_count=1,
        ),
    ]
    for index, row in enumerate(rows):
        row["relationship_review_needed"] = True
        row["semantic_priority"] = (100 - index, 1, 1)

    batches, selected = _quantity_relationship_batches(rows, batch_size=2, max_batches=1)

    assert [[item["candidate_id"] for item in batch] for batch in batches] == [
        ["design-high", "commercial"]
    ]
    assert selected == {"design-high", "commercial"}


@pytest.mark.parametrize(
    ("vor_role", "estimate_role"),
    (
        ("Ведомость объемов работ", "Локальная смета"),
        ("bill of quantities", "local estimate"),
    ),
)
def test_quantity_relationship_batches_include_vor_estimate_scope_review(
    vor_role: str, estimate_role: str
) -> None:
    vor = _work_batch_row(
        "vor",
        facility="Мост через реку Северную",
        family="pile_foundation",
        document_role=vor_role,
        wording="Устройство буронабивных свай",
    )
    estimate = _work_batch_row(
        "estimate",
        facility="Мост через реку Северную",
        family="pile_foundation",
        document_role=estimate_role,
        wording="Устройство буронабивных свай",
    )
    for row in (vor, estimate):
        row.update(relationship_review_needed=True, semantic_priority=(100, 1, 1))
        row["quantity_observations"][0].update(unit="м")

    batches, selected = _quantity_relationship_batches([estimate, vor], batch_size=2, max_batches=1)

    assert [[item["candidate_id"] for item in batch] for batch in batches] == [["vor", "estimate"]]
    assert selected == {"vor", "estimate"}


def test_quantity_relationship_batches_include_design_design_scope_review() -> None:
    pd = _work_batch_row(
        "pd",
        facility="Здание цеха",
        family="reinforced_concrete",
        document_role="Проектная документация",
        wording="Устройство монолитной фундаментной плиты",
    )
    rd = _work_batch_row(
        "rd",
        facility="Здание цеха",
        family="reinforced_concrete",
        document_role="Рабочая документация",
        wording="Устройство монолитной фундаментной плиты",
    )
    for row in (pd, rd):
        row.update(relationship_review_needed=True, semantic_priority=(100, 1, 1))
        row["quantity_observations"][0].update(unit="м3")

    batches, selected = _quantity_relationship_batches([rd, pd], batch_size=2, max_batches=1)

    assert [[item["candidate_id"] for item in batch] for batch in batches] == [["pd", "rd"]]
    assert selected == {"pd", "rd"}


def test_quantity_relationship_batches_prioritize_cross_document_lane() -> None:
    vor = _work_batch_row(
        "vor",
        facility="Тепловая сеть",
        family="pipeline",
        document_role="bill of quantities",
        wording="Монтаж трубопровода",
    )
    estimate = _work_batch_row(
        "estimate",
        facility="Тепловая сеть",
        family="pipeline",
        document_role="local estimate",
        wording="Монтаж трубопровода",
    )
    component_a = _work_batch_row(
        "component-a",
        facility="Кровля",
        family="waterproofing",
        document_role="ВОР",
        wording="Теплоизоляция южного ската",
        quantity_count=4,
    )
    component_b = _work_batch_row(
        "component-b",
        facility="Кровля",
        family="waterproofing",
        document_role="ВОР",
        wording="Теплоизоляция северного ската",
        quantity_count=4,
    )
    component_b["source_version_id"] = component_a["source_version_id"]
    rows = [component_a, component_b, vor, estimate]
    for row in rows:
        row.update(relationship_review_needed=True, semantic_priority=(100, 1, 1))
        for quantity in row["quantity_observations"]:
            quantity["unit"] = "м"

    batches, selected = _quantity_relationship_batches(rows, batch_size=2, max_batches=1)

    assert [[item["candidate_id"] for item in batch] for batch in batches] == [["vor", "estimate"]]
    assert selected == {"vor", "estimate"}


def test_quantity_relationship_batches_rank_semantic_scope_before_unrelated_family_rows() -> None:
    design_fence = _work_batch_row(
        "design-fence",
        facility="",
        family="fencing",
        document_role="ПД",
        wording="Устройство металлического ограждения",
    )
    design_fence["quantity_observations"][0].update(
        unit="м", prior_semantic_scope="Длина металлического ограждения"
    )
    design_drainage = _work_batch_row(
        "design-drainage",
        facility="",
        family="fencing",
        document_role="РД",
        wording="Ограждение дренажного канала",
    )
    design_drainage["quantity_observations"][0].update(
        unit="м", prior_semantic_scope="Длина ограждения дренажного канала"
    )
    commercial_fence = _work_batch_row(
        "commercial-fence",
        facility="",
        family="fencing",
        document_role="Смета",
        wording="Монтаж металлических ограждений",
    )
    commercial_fence["quantity_observations"][0].update(
        unit="м", prior_semantic_scope="Длина металлического ограждения"
    )
    commercial_unrelated = _work_batch_row(
        "commercial-unrelated",
        facility="",
        family="fencing",
        document_role="ВОР",
        wording="Разборка временного защитного забора",
    )
    commercial_unrelated["quantity_observations"][0].update(
        unit="м2", prior_semantic_scope="Площадь временного защитного забора"
    )
    rows = [design_drainage, commercial_unrelated, design_fence, commercial_fence]
    for row in rows:
        row.update(relationship_review_needed=True, semantic_priority=(100, 1, 1))

    batches, selected = _quantity_relationship_batches(rows, batch_size=2, max_batches=1)

    assert [[item["candidate_id"] for item in batch] for batch in batches] == [
        ["design-fence", "commercial-fence"]
    ]
    assert selected == {"design-fence", "commercial-fence"}


def test_quantity_relationship_batch_keeps_related_components_with_selected_total() -> None:
    component_a = _work_batch_row(
        "component-a",
        facility="",
        family="demolition",
        document_role="ПД",
        wording="Демонтаж покрытия на участке сети",
    )
    component_a.update(page=21, relationship_review_needed=True, semantic_priority=(80, 1, 1))
    component_a["quantity_observations"][0].update(
        value="127.2",
        unit="м2",
        prior_quantity_type="COMPONENT",
        prior_semantic_scope="Площадь демонтажа покрытия",
    )
    component_b = _work_batch_row(
        "component-b",
        facility="",
        family="demolition",
        document_role="ПД",
        wording="Демонтаж покрытия на участке сооружения",
    )
    component_b.update(page=21, relationship_review_needed=True, semantic_priority=(70, 1, 1))
    component_b["quantity_observations"][0].update(
        value="147.5",
        unit="м2",
        prior_quantity_type="STANDALONE",
        prior_semantic_scope="Площадь демонтажа покрытия",
    )
    stated_total = _work_batch_row(
        "total",
        facility="",
        family="demolition",
        document_role="ВОР",
        wording="Демонтаж покрытия, всего",
    )
    stated_total.update(page=30, relationship_review_needed=True, semantic_priority=(100, 1, 1))
    stated_total["quantity_observations"][0].update(
        value="274.7",
        unit="м2",
        prior_quantity_type="TOTAL",
        prior_semantic_scope="Площадь демонтажа покрытия",
    )
    unrelated = _work_batch_row(
        "unrelated",
        facility="",
        family="demolition",
        document_role="ПД",
        wording="Демонтаж железобетонной стены",
    )
    unrelated.update(page=2, relationship_review_needed=True, semantic_priority=(99, 1, 1))
    unrelated["quantity_observations"][0].update(
        value="102", unit="м3", prior_semantic_scope="Объем демонтажа стены"
    )
    source_version = "source-project-package"
    for row in (component_a, component_b, stated_total, unrelated):
        row["source_version_id"] = source_version

    batches, selected = _quantity_relationship_batches(
        [unrelated, component_b, stated_total, component_a],
        batch_size=2,
        max_batches=1,
    )

    assert {item["candidate_id"] for item in batches[0]} == {
        "component-a",
        "component-b",
        "total",
    }
    assert selected == {"component-a", "component-b", "total"}


def test_quantity_relationship_batch_can_review_total_across_facility_components() -> None:
    north = _work_batch_row(
        "north-component",
        facility="Опора Север",
        family="structural_steel",
        document_role="РД",
        wording="Монтаж металлоконструкций северного пролёта",
    )
    north["quantity_observations"][0].update(
        quantity_candidate_id="north-mass",
        value="7.4",
        unit="т",
        prior_quantity_type="COMPONENT",
        prior_semantic_scope="Масса металлоконструкций пролёта",
    )
    south = _work_batch_row(
        "south-component",
        facility="Опора Юг",
        family="structural_steel",
        document_role="РД",
        wording="Монтаж металлоконструкций южного пролёта",
    )
    south["quantity_observations"][0].update(
        quantity_candidate_id="south-mass",
        value="5.1",
        unit="т",
        prior_quantity_type="STANDALONE",
        prior_semantic_scope="Масса металлоконструкций пролёта",
    )
    total = _work_batch_row(
        "project-total",
        facility="",
        family="structural_steel",
        document_role="ВОР",
        wording="Монтаж металлоконструкций пролётов, всего",
    )
    total["quantity_observations"][0].update(
        quantity_candidate_id="project-total-mass",
        value="12.5",
        unit="т",
        prior_quantity_type="TOTAL",
        prior_semantic_scope="Общая масса металлоконструкций пролётов",
    )
    duplicate_total = _work_batch_row(
        "project-total-alias",
        facility="",
        family="structural_steel",
        document_role="ВОР",
        wording="Металлоконструкции пролётов",
    )
    duplicate_total["quantity_observations"][0].update(
        quantity_candidate_id="project-total-mass",
        value="12.5",
        unit="т",
        prior_quantity_type="TOTAL",
        prior_semantic_scope="Общая масса металлоконструкций пролётов",
    )
    unrelated = _work_batch_row(
        "unrelated",
        facility="Башня 3",
        family="structural_steel",
        document_role="РД",
        wording="Монтаж лестничного ограждения",
    )
    unrelated["quantity_observations"][0].update(
        quantity_candidate_id="railing-mass",
        value="1.8",
        unit="т",
        prior_quantity_type="STANDALONE",
        prior_semantic_scope="Масса лестничного ограждения",
    )
    rows = [north, south, total, duplicate_total, unrelated]
    for row in rows:
        row.update(relationship_review_needed=True, semantic_priority=(100, 1, 1))

    batches, selected = _quantity_relationship_batches(rows, batch_size=2, max_batches=1)

    assert {item["candidate_id"] for item in batches[0]} == {
        "north-component",
        "south-component",
        "project-total",
    }
    quantity_ids = [
        str(quantity.get("quantity_candidate_id") or quantity.get("candidate_id"))
        for item in batches[0]
        for quantity in item["quantity_observations"]
    ]
    assert quantity_ids == list(dict.fromkeys(quantity_ids))
    assert "unrelated" not in selected


def test_quantity_relationship_batch_uses_source_formula_when_prior_total_label_was_lost() -> None:
    east = _work_batch_row(
        "east-zone",
        facility="Секция Восток",
        family="roadworks",
        document_role="Проектная документация",
        wording="Разборка покрытия восточной секции",
    )
    east["quantity_observations"][0].update(
        quantity_candidate_id="east-area",
        value="83.6",
        unit="м2",
        prior_quantity_type="COMPONENT",
        prior_semantic_scope="Площадь покрытия восточной секции",
    )
    west = _work_batch_row(
        "west-zone",
        facility="Секция Запад",
        family="roadworks",
        document_role="Проектная документация",
        wording="Разборка покрытия западной секции",
    )
    west["source_version_id"] = east["source_version_id"]
    west["quantity_observations"][0].update(
        quantity_candidate_id="west-area",
        value="41.4",
        unit="м2",
        prior_quantity_type="STANDALONE",
        prior_semantic_scope="Площадь покрытия западной секции",
    )
    stated = _work_batch_row(
        "stated-area-and-volume",
        facility="",
        family="roadworks",
        document_role="Проектная документация",
        wording="Разборка покрытия общей толщиной 0,08 м",
    )
    stated["source_version_id"] = east["source_version_id"]
    stated["quantity_observations"][0].update(
        quantity_candidate_id="compound-area-volume",
        value="125,0/10,0",
        unit="м2/м3",
        prior_quantity_type="STANDALONE",
        prior_semantic_scope="Площадь и объем разобранного покрытия",
        nearby_context="(83,6 + 41,4) x 0,08 = 10,0 м3",
    )
    repeated_total = _work_batch_row(
        "repeated-stated-area-and-volume",
        facility="",
        family="roadworks",
        document_role="Проектная документация",
        wording="Разборка покрытия, сводная таблица",
    )
    repeated_total["quantity_observations"][0].update(
        quantity_candidate_id="repeated-compound-area-volume",
        value="125,0/10,0",
        unit="м2/м3",
        prior_quantity_type="STANDALONE",
        prior_semantic_scope="Площадь и объем разобранного покрытия",
        nearby_context="Всего: 125,0 м2 / 10,0 м3",
    )
    rows = [east, west, stated, repeated_total]
    for row in rows:
        row.update(relationship_review_needed=True, semantic_priority=(100, 1, 1))

    batches, selected = _quantity_relationship_batches(rows, batch_size=2, max_batches=1)

    assert {item["candidate_id"] for item in batches[0]} == {
        "east-zone",
        "west-zone",
        "stated-area-and-volume",
    }
    assert selected == {"east-zone", "west-zone", "stated-area-and-volume"}


def test_quantity_relationship_pair_ranking_never_uses_numeric_similarity() -> None:
    design = _work_batch_row(
        "design",
        facility="",
        family="earthworks",
        document_role="ПД",
        wording="Разработка грунта котлована",
    )
    design["quantity_observations"][0].update(
        value="438", unit="м3", prior_semantic_scope="Объем грунта котлована"
    )
    commercial_related = _work_batch_row(
        "commercial-related",
        facility="",
        family="earthworks",
        document_role="Смета",
        wording="Разработка грунта в котловане",
    )
    commercial_related["quantity_observations"][0].update(
        value="361", unit="м3", prior_semantic_scope="Объем грунта котлована"
    )
    commercial_same_number = _work_batch_row(
        "commercial-same-number",
        facility="",
        family="earthworks",
        document_role="ВОР",
        wording="Обратная засыпка траншеи",
    )
    commercial_same_number["quantity_observations"][0].update(
        value="438", unit="м3", prior_semantic_scope="Объем обратной засыпки траншеи"
    )
    rows = [design, commercial_same_number, commercial_related]
    for row in rows:
        row.update(relationship_review_needed=True, semantic_priority=(100, 1, 1))

    batches, _selected = _quantity_relationship_batches(rows, batch_size=2, max_batches=1)

    assert [item["candidate_id"] for item in batches[0]] == [
        "design",
        "commercial-related",
    ]


def test_quantity_relationship_batches_do_not_repeat_attempted_pair() -> None:
    design = _work_batch_row(
        "design",
        facility="",
        family="pipeline",
        document_role="ПД",
        wording="Прокладка стального водовода",
    )
    commercial_a = _work_batch_row(
        "commercial-a",
        facility="",
        family="pipeline",
        document_role="ВОР",
        wording="Монтаж стального водовода",
    )
    commercial_b = _work_batch_row(
        "commercial-b",
        facility="",
        family="pipeline",
        document_role="Смета",
        wording="Прокладка водовода из стальных труб",
    )
    for row in (design, commercial_a, commercial_b):
        row.update(relationship_review_needed=True, semantic_priority=(100, 1, 1))
        row["quantity_observations"][0].update(unit="м")

    batches, selected = _quantity_relationship_batches(
        [design, commercial_a, commercial_b],
        batch_size=2,
        max_batches=1,
        attempted_pairs={("commercial-a", "design")},
    )

    assert [item["candidate_id"] for item in batches[0]] == ["design", "commercial-b"]
    assert selected == {"design", "commercial-b"}


def test_quantity_relationship_batches_skip_weak_unassigned_family_pair() -> None:
    design = _work_batch_row(
        "design",
        facility="",
        family="demolition",
        document_role="ПД",
        wording="Разборка асфальтового покрытия",
    )
    commercial = _work_batch_row(
        "commercial",
        facility="",
        family="demolition",
        document_role="ВОР",
        wording="Снос стены из крупных блоков",
    )
    for row in (design, commercial):
        row.update(relationship_review_needed=True, semantic_priority=(100, 1, 1))
        row["quantity_observations"][0].update(unit="м3")

    batches, selected = _quantity_relationship_batches(
        [design, commercial], batch_size=2, max_batches=1
    )

    assert batches == []
    assert selected == set()


def test_quantity_relationship_batches_reuse_settled_context_only_for_mixed_review() -> None:
    design = _work_batch_row(
        "settled-design",
        facility="",
        family="structural_steel",
        document_role="ПД",
        wording="Монтаж балок покрытия",
        quantity_count=1,
    )
    design.update(
        relationship_review_needed=True,
        comparison_context_only=True,
        semantic_priority=(100, 1, 1),
    )
    commercial = _work_batch_row(
        "new-commercial",
        facility="",
        family="structural_steel",
        document_role="Смета контракта",
        wording="Монтаж стальных балок",
        quantity_count=1,
    )
    commercial.update(relationship_review_needed=True, semantic_priority=(80, 1, 1))

    batches, selected = _quantity_relationship_batches(
        [design, commercial], batch_size=2, max_batches=1
    )

    assert [[item["candidate_id"] for item in batch] for batch in batches] == [
        ["settled-design", "new-commercial"]
    ]
    assert selected == {"settled-design", "new-commercial"}
    assert all("comparison_context_only" not in item for item in batches[0])


def test_quantity_relationship_batches_do_not_replay_same_role_settled_context() -> None:
    rows = [
        _work_batch_row(
            "settled-a",
            facility="",
            family="pipeline",
            document_role="РД",
            wording="Прокладка участка А",
            quantity_count=1,
        ),
        _work_batch_row(
            "settled-b",
            facility="",
            family="pipeline",
            document_role="РД",
            wording="Прокладка участка Б",
            quantity_count=1,
        ),
    ]
    for row in rows:
        row.update(
            relationship_review_needed=True,
            comparison_context_only=True,
            semantic_priority=(50, 1, 1),
        )

    batches, selected = _quantity_relationship_batches(rows, batch_size=2, max_batches=1)

    assert batches == []
    assert selected == set()


def test_work_reconciliation_attempt_sets_separate_single_and_mixed_context() -> None:
    attempted, mixed, scope_pairs = _work_reconciliation_attempt_sets(
        [
            {
                "work_observations": [
                    {
                        "candidate_id": "design-only",
                        "document_role": "ПД",
                        "document": "Том 1.pdf",
                    }
                ]
            },
            {
                "work_observations": [
                    {
                        "candidate_id": "design-mixed",
                        "document_role": "КР",
                        "document": "Конструкции.pdf",
                        "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
                    },
                    {
                        "candidate_id": "commercial-mixed",
                        "document_role": "ВОР",
                        "document": "Объёмы.pdf",
                        "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
                    },
                ]
            },
        ]
    )

    assert attempted == {"design-only", "design-mixed", "commercial-mixed"}
    assert mixed == {("commercial-mixed", "design-mixed")}
    assert scope_pairs == set()


def test_work_reconciliation_attempt_sets_track_vor_estimate_pair() -> None:
    attempted, pairs, scope_pairs = _work_reconciliation_attempt_sets(
        [
            {
                "work_observations": [
                    {
                        "candidate_id": "vor-row",
                        "document_role": "ВОР",
                        "document": "Ведомость.pdf",
                        "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
                    },
                    {
                        "candidate_id": "estimate-row",
                        "document_role": "Локальная смета",
                        "document": "Смета.pdf",
                        "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
                    },
                ]
            }
        ]
    )

    assert attempted == {"vor-row", "estimate-row"}
    assert pairs == {("estimate-row", "vor-row")}
    assert scope_pairs == set()


def test_mixed_source_classification_batch_is_not_relationship_authority() -> None:
    attempted, mixed, scope_pairs = _work_reconciliation_attempt_sets(
        [
            {
                "work_observations": [
                    {
                        "candidate_id": "design-row",
                        "document_role": "ПД",
                        "document": "Design.pdf",
                    },
                    {
                        "candidate_id": "commercial-row",
                        "document_role": "ВОР",
                        "document": "Commercial.pdf",
                    },
                ]
            }
        ]
    )

    assert attempted == {"design-row", "commercial-row"}
    assert mixed == set()
    assert scope_pairs == set()


def test_work_reconciliation_attempt_sets_track_explicit_scope_pair() -> None:
    attempted, quantity_pairs, scope_pairs = _work_reconciliation_attempt_sets(
        [
            {
                "work_observations": [
                    {
                        "candidate_id": "design-scope",
                        "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
                    },
                    {
                        "candidate_id": "commercial-scope",
                        "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
                    },
                ]
            }
        ]
    )

    assert attempted == {"design-scope", "commercial-scope"}
    assert quantity_pairs == set()
    assert scope_pairs == {("commercial-scope", "design-scope")}


def test_compatible_pair_ledger_rejects_only_exact_replay() -> None:
    accepted = {("commercial-scope", "design-scope")}
    replay = {
        "work_observations": [
            {
                "candidate_id": "design-scope",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
            {
                "candidate_id": "commercial-scope",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
        ]
    }
    distinct = {
        "work_observations": [
            {
                "candidate_id": "design-scope",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
            {
                "candidate_id": "other-commercial-scope",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
        ]
    }

    assert _work_reconciliation_manifest_replays_accepted_pair(
        replay,
        accepted_relationship_pairs=set(),
        accepted_scope_pairs=accepted,
    )
    assert not _work_reconciliation_manifest_replays_accepted_pair(
        distinct,
        accepted_relationship_pairs=set(),
        accepted_scope_pairs=accepted,
    )


def test_settled_quantity_remains_available_for_distinct_cross_document_pairs() -> None:
    quantity = {
        "candidate_id": "quantity-design",
        "version": 2,
        "normalized_value": "74.25",
        "normalized_unit": "m3",
    }
    existing = {
        "candidate_version": 4,
        "profile_version": PROJECT_WORK_RECONCILIATION_PROFILE,
        "quantity_reviews": [
            {
                "quantity_candidate_id": "quantity-design",
                "quantity_candidate_version": 2,
                "status": "WORK_QUANTITY",
                "relationship_reviewed": True,
                "semantic_scope": "Объём монолитной плиты",
            }
        ],
    }

    selected, context_only = _quantity_comparison_context_policy(
        existing=existing,
        candidate_version=4,
        linked_quantities=[quantity],
    )

    assert selected == [quantity]
    assert context_only is True


def test_current_profile_quantity_missing_relationship_is_context_only() -> None:
    quantity = {
        "candidate_id": "quantity-current-single-source",
        "version": 1,
        "normalized_value": "83.4",
        "normalized_unit": "m3",
    }
    existing = {
        "candidate_version": 2,
        "profile_version": PROJECT_WORK_RECONCILIATION_PROFILE,
        "quantity_reviews": [
            {
                "quantity_candidate_id": "quantity-current-single-source",
                "status": "WORK_QUANTITY",
                "semantic_scope": "Объём земляных работ",
                "relationship_reviewed": False,
            }
        ],
    }

    selected, context_only = _quantity_comparison_context_policy(
        existing=existing,
        candidate_version=2,
        linked_quantities=[quantity],
    )

    assert selected == [quantity]
    assert context_only is True


def test_older_quantity_meaning_is_selected_for_current_cross_document_review() -> None:
    quantity = {
        "candidate_id": "quantity-old-profile",
        "version": 1,
        "normalized_value": "186.4",
        "normalized_unit": "m",
    }
    existing = {
        "candidate_version": 3,
        "profile_version": "qwen-project-work-reconciliation-v20",
        "quantity_reviews": [
            {
                "quantity_candidate_id": "quantity-old-profile",
                "status": "WORK_QUANTITY",
                "relationship_reviewed": True,
                "semantic_scope": "Длина проектируемого участка",
            }
        ],
    }

    selected, context_only = _quantity_comparison_context_policy(
        existing=existing,
        candidate_version=3,
        linked_quantities=[quantity],
    )

    assert selected == [quantity]
    assert context_only is False
    assert bool(selected) is True


def test_quantity_review_chunks_merge_by_exact_candidate_identity() -> None:
    combined = _merged_quantity_reviews(
        (
            {"quantity_candidate_id": "quantity-1", "status": "AMBIGUOUS"},
            {"quantity_candidate_id": "quantity-2", "status": "DIMENSION"},
        ),
        (
            {"quantity_candidate_id": "quantity-1", "status": "WORK_QUANTITY"},
            {"quantity_candidate_id": "quantity-3", "status": "DURATION"},
        ),
    )

    assert combined == [
        {"quantity_candidate_id": "quantity-1", "status": "WORK_QUANTITY"},
        {"quantity_candidate_id": "quantity-2", "status": "DIMENSION"},
        {"quantity_candidate_id": "quantity-3", "status": "DURATION"},
    ]


def test_quantity_review_chunks_preserve_multiple_reviewed_relationships() -> None:
    combined = _merged_quantity_reviews(
        (
            {
                "quantity_candidate_id": "manual",
                "status": "WORK_QUANTITY",
                "relation_kind": "COMPONENT_OF",
                "related_quantity_candidate_ids": ["design-total"],
                "scope_compatibility": "COMPONENT_VS_TOTAL",
                "relationship_reviewed": True,
            },
        ),
        (
            {
                "quantity_candidate_id": "manual",
                "status": "WORK_QUANTITY",
                "relation_kind": "DUPLICATE_OF",
                "related_quantity_candidate_ids": ["vor-manual"],
                "scope_compatibility": "SAME_SCOPE",
                "relationship_reviewed": True,
            },
        ),
    )

    assert combined[0]["relation_kind"] == "DUPLICATE_OF"
    assert combined[0]["relationship_assertions"] == [
        {
            "relation_kind": "COMPONENT_OF",
            "related_quantity_candidate_ids": ["design-total"],
            "scope_compatibility": "COMPONENT_VS_TOTAL",
            "relationship_reviewed": True,
        },
        {
            "relation_kind": "DUPLICATE_OF",
            "related_quantity_candidate_ids": ["vor-manual"],
            "scope_compatibility": "SAME_SCOPE",
            "relationship_reviewed": True,
        },
    ]


def test_quantity_review_chunks_preserve_pair_specific_scope_decisions() -> None:
    combined = _merged_quantity_reviews(
        (
            {
                "quantity_candidate_id": "manual",
                "status": "WORK_QUANTITY",
                "scope_compatibility": "SAME_SCOPE",
                "scope_assertions": [
                    {
                        "related_quantity_candidate_id": "vor-manual",
                        "scope_compatibility": "SAME_SCOPE",
                        "reason": "One manual excavation scope.",
                    }
                ],
            },
        ),
        (
            {
                "quantity_candidate_id": "manual",
                "status": "WORK_QUANTITY",
                "scope_compatibility": "DIFFERENT_SCOPE",
                "scope_assertions": [
                    {
                        "related_quantity_candidate_id": "mechanized",
                        "scope_compatibility": "DIFFERENT_SCOPE",
                        "reason": "Manual and mechanized excavation are distinct.",
                    }
                ],
            },
        ),
    )

    assert combined[0]["scope_compatibility"] == "DIFFERENT_SCOPE"
    assert combined[0]["scope_assertions"] == [
        {
            "related_quantity_candidate_id": "vor-manual",
            "scope_compatibility": "SAME_SCOPE",
            "reason": "One manual excavation scope.",
        },
        {
            "related_quantity_candidate_id": "mechanized",
            "scope_compatibility": "DIFFERENT_SCOPE",
            "reason": "Manual and mechanized excavation are distinct.",
        },
    ]


def test_work_resolution_profile_upgrade_preserves_facility_and_quantity_reviews() -> None:
    rows = [
        {
            "input_manifest": {
                "work_observations": [{"candidate_id": "work-1", "candidate_version": 3}]
            },
            "profile_version": "qwen-project-work-reconciliation-v5",
            "result_manifest": {
                "observations": [
                    {
                        "candidate_id": "work-1",
                        "status": "MATCHED",
                        "family_key": "sheet_piling",
                        "facility": "КНС 4",
                        "quantity_reviews": [
                            {"quantity_candidate_id": "quantity-1", "status": "WORK_QUANTITY"}
                        ],
                        "material_reviews": [
                            {
                                "material_name": "Polymer membrane",
                                "material_kind": "polymer membrane",
                            }
                        ],
                    }
                ]
            },
            "recorded_at": "2026-09-28T00:00:00Z",
        },
        {
            "input_manifest": {
                "work_observations": [{"candidate_id": "work-1", "candidate_version": 3}]
            },
            "profile_version": "qwen-project-work-reconciliation-v6",
            "result_manifest": {
                "observations": [
                    {
                        "candidate_id": "work-1",
                        "status": "MATCHED",
                        "family_key": "sheet_piling",
                        "facility": None,
                        "quantity_reviews": [
                            {"quantity_candidate_id": "quantity-2", "status": "DIMENSION"}
                        ],
                    }
                ]
            },
            "recorded_at": "2026-09-28T00:01:00Z",
        },
    ]

    class Result:
        def mappings(self) -> list[dict[str, object]]:
            return rows

    class Session:
        def execute(self, *_args: object, **_kwargs: object) -> Result:
            return Result()

    resolved = SpinePostgresRepository._project_work_resolution_rows(
        Session(),  # type: ignore[arg-type]
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_ID,
    )["work-1"]

    assert resolved["profile_version"] == "qwen-project-work-reconciliation-v6"
    assert resolved["facility"] == "КНС 4"
    assert resolved["quantity_reviews"] == [
        {"quantity_candidate_id": "quantity-1", "status": "WORK_QUANTITY"},
        {"quantity_candidate_id": "quantity-2", "status": "DIMENSION"},
    ]
    assert resolved["material_reviews"] == [
        {"material_name": "Polymer membrane", "material_kind": "polymer membrane"}
    ]


def test_project_understanding_application_projection_keeps_counts_and_selected_section() -> None:
    view = {
        "page_roles": [{"page_number": 1}],
        "work_packages": [{"work_package_id": "work-1"}],
        "defects": [
            {"defect_id": "defect-1"},
            {"defect_id": "defect-2"},
            {"defect_id": "defect-3"},
        ],
        "candidates": {
            "project_fields": [{"candidate_id": "field-1"}],
            "work_types": [
                {"candidate_id": "work-1"},
                {"candidate_id": "work-2"},
            ],
            "quantities": [{"candidate_id": "quantity-1"}],
            "materials": [{"candidate_id": "material-1"}],
        },
        "review_decisions": [
            {"review_decision_id": "review-work", "candidate_id": "work-2"},
            {"review_decision_id": "review-material", "candidate_id": "material-1"},
        ],
        "structure_nodes": [{"structure_node_id": "node-1"}],
        "structure_relationships": [{"relationship_candidate_id": "relationship-1"}],
        "structure_dossiers": [{"structure_node": {"structure_node_id": "node-1"}}],
        "structure_components": [{"component_key": "component-1"}],
        "structure_identity_candidates": [{"identity_candidate_id": "identity-1"}],
        "structure_identity_components": [{"identity_candidate_id": "identity-component-1"}],
        "structure_identity_dossiers": [
            {"identity_candidate": {"identity_candidate_id": "identity-component-1"}}
        ],
        "structure_identity_reconciliation": {"state": "running"},
        "excavation_pit_inventory": {"candidate_pits": [{"pit_candidate_id": "pit-1"}]},
        "facility_work_projection": {"candidate_groups": [{"facility_work_candidate_id": "fw-1"}]},
        "matrix": {
            "matrix": {"rows": [{"row": "matrix-1"}, {"row": "matrix-2"}, {"row": "matrix-3"}]}
        },
        "normative_profile": {"profile_id": "profile-1"},
        "intake_summary": {
            "tender_input_assessment": [
                {
                    "category": "design",
                    "source_locator_ids": [f"locator-{index}" for index in range(12)],
                }
            ]
        },
        "summary_counts": {"structure_node_count": 7000},
    }

    structure = SpinePostgresRepository._project_understanding_application_projection(
        view, section="structure"
    )

    assert structure["summary_counts"] == {"structure_node_count": 7000}
    assert structure["structure_identity_candidates"] == []
    assert structure["structure_identity_components"] == [
        {"identity_candidate_id": "identity-component-1"}
    ]
    assert structure["excavation_pit_inventory"]["candidate_pits"] == [
        {"pit_candidate_id": "pit-1"}
    ]
    assert structure["structure_nodes"] == []
    assert structure["work_packages"] == []
    assert structure["facility_work_projection"] == {}
    assert structure["application_page"]["collection"] == "structure_identity_components"
    assert structure["matrix"] == {"matrix": {"rows": []}}
    assert "tender_input_assessment" not in structure["intake_summary"]

    packages = SpinePostgresRepository._project_understanding_application_projection(
        view, section="packages"
    )
    assert packages["facility_work_projection"]["candidate_groups"] == [
        {"facility_work_candidate_id": "fw-1"}
    ]
    assert packages["application_page"]["collection"] == "facility_work_candidate_groups"
    assert packages["structure_identity_candidates"] == []

    works = SpinePostgresRepository._project_understanding_application_projection(
        view, section="works", page_offset=1, page_limit=2
    )
    assert works["candidates"] == {
        "work_types": [{"candidate_id": "work-2"}],
        "quantities": [{"candidate_id": "quantity-1"}],
    }
    assert works["review_decisions"] == [
        {"review_decision_id": "review-work", "candidate_id": "work-2"}
    ]
    assert works["facility_work_projection"] == {}
    assert works["application_page"] == {
        "collection": "work_types+quantities",
        "offset": 1,
        "limit": 2,
        "returned": 2,
        "total": 3,
        "has_previous": True,
        "has_more": False,
    }

    materials = SpinePostgresRepository._project_understanding_application_projection(
        view, section="materials"
    )
    assert materials["candidates"] == {"materials": [{"candidate_id": "material-1"}]}
    assert materials["review_decisions"] == [
        {"review_decision_id": "review-material", "candidate_id": "material-1"}
    ]

    matrix = SpinePostgresRepository._project_understanding_application_projection(
        view, section="matrix", page_offset=1, page_limit=1
    )
    assert matrix["matrix"]["matrix"]["rows"] == [{"row": "matrix-2"}]
    assert matrix["application_page"] == {
        "collection": "matrix_rows",
        "offset": 1,
        "limit": 1,
        "returned": 1,
        "total": 3,
        "has_previous": True,
        "has_more": True,
    }

    gaps = SpinePostgresRepository._project_understanding_application_projection(
        view, section="gaps", page_offset=2, page_limit=2
    )
    assert gaps["defects"] == [{"defect_id": "defect-3"}]
    assert gaps["application_page"]["total"] == 3
    assert gaps["application_page"]["has_more"] is False

    general = SpinePostgresRepository._project_understanding_application_projection(
        view, section="general"
    )
    assessment = general["intake_summary"]["tender_input_assessment"][0]
    assert assessment["source_locator_count"] == 12
    assert assessment["source_locator_ids"] == [f"locator-{index}" for index in range(10)]
    assert general["candidates"] == {"project_fields": [{"candidate_id": "field-1"}]}

    with pytest.raises(SpinePersistenceError, match="project_understanding_section_invalid"):
        SpinePostgresRepository._project_understanding_application_projection(
            view, section="unknown"
        )
    with pytest.raises(SpinePersistenceError, match="project_understanding_page_invalid"):
        SpinePostgresRepository._project_understanding_application_projection(
            view, section="gaps", page_offset=-1
        )


def test_project_candidate_projection_pages_beyond_first_two_hundred_rows() -> None:
    view = {
        "candidates": {
            "project_fields": [],
            "work_types": [{"candidate_id": f"work-{ordinal}"} for ordinal in range(205)],
            "quantities": [{"candidate_id": f"quantity-{ordinal}"} for ordinal in range(3)],
            "materials": [],
        },
        "review_decisions": [],
        "intake_summary": {},
    }

    page = SpinePostgresRepository._project_understanding_application_projection(
        view,
        section="works",
        page_offset=200,
        page_limit=8,
    )

    assert page["candidates"] == {
        "work_types": [{"candidate_id": f"work-{ordinal}"} for ordinal in range(200, 205)],
        "quantities": [{"candidate_id": f"quantity-{ordinal}"} for ordinal in range(3)],
    }
    assert page["application_page"] == {
        "collection": "work_types+quantities",
        "offset": 200,
        "limit": 8,
        "returned": 8,
        "total": 208,
        "has_previous": True,
        "has_more": False,
    }


def test_facility_work_projection_pages_groups_without_changing_canonical_coverage() -> None:
    view = {
        "candidates": {},
        "review_decisions": [],
        "intake_summary": {},
        "facility_work_projection": {
            "candidate_groups": [
                {"facility_work_candidate_id": f"group-{ordinal}"} for ordinal in range(205)
            ],
            "coverage": {
                "total_work_package_count": 900,
                "consolidated_candidate_group_count": 205,
            },
        },
    }

    page = SpinePostgresRepository._project_understanding_application_projection(
        view,
        section="packages",
        page_offset=200,
        page_limit=5,
    )

    assert page["facility_work_projection"]["candidate_groups"] == [
        {"facility_work_candidate_id": f"group-{ordinal}"} for ordinal in range(200, 205)
    ]
    assert page["facility_work_projection"]["coverage"] == {
        "total_work_package_count": 900,
        "consolidated_candidate_group_count": 205,
        "returned_candidate_group_count": 5,
        "total_candidate_group_count": 205,
        "candidate_group_page_complete": False,
    }
    assert page["application_page"] == {
        "collection": "facility_work_candidate_groups",
        "offset": 200,
        "limit": 5,
        "returned": 5,
        "total": 205,
        "has_previous": True,
        "has_more": False,
    }


def test_structure_projection_selects_relevant_facility_work_beyond_first_page() -> None:
    groups = [
        {
            "facility_work_candidate_id": f"group-{ordinal}",
            "identity_label": f"КНС-{ordinal}",
            "identity_kind": "facility",
            "work_type": {"raw": "Общестроительные работы"},
        }
        for ordinal in range(205)
    ]
    groups.append(
        {
            "facility_work_candidate_id": "target-los-8-1",
            "identity_label": "ЛОС 8.1",
            "identity_kind": "facility",
            "work_type": {"raw": "Устройство котлована"},
        }
    )
    view = {
        "candidates": {},
        "review_decisions": [],
        "intake_summary": {},
        "structure_identity_components": [],
        "structure_identity_dossiers": [],
        "excavation_pit_inventory": {},
        "facility_work_projection": {
            "candidate_groups": groups,
            "coverage": {
                "total_work_package_count": 900,
                "consolidated_candidate_group_count": len(groups),
            },
        },
    }

    page = SpinePostgresRepository._project_understanding_application_projection(
        view,
        section="structure",
        page_limit=100,
        facility_query="Какие работы относятся к ЛОС8.1?",
        facility_limit=20,
    )

    projection = page["facility_work_projection"]
    assert [item["facility_work_candidate_id"] for item in projection["candidate_groups"]] == [
        "target-los-8-1"
    ]
    assert projection["selection"] == {
        "query": "Какие работы относятся к ЛОС8.1?",
        "selection": "facility_designation_and_lexical_relevance",
        "total_candidate_group_count": len(groups),
        "matched_candidate_group_count": 1,
        "returned_candidate_group_count": 1,
        "exhaustive_for_query": True,
        "projection_coverage": {
            "total_work_package_count": 900,
            "consolidated_candidate_group_count": len(groups),
        },
        "authority": "candidate_association_not_confirmed_scope",
    }


def test_unexpected_handler_error_terminalizes_job_without_crashing_worker() -> None:
    claimed = ClaimedJob(
        ORGANIZATION_ID,
        WORKSPACE_ID,
        UUID("018f5c3e-7b00-7000-8000-000000001803"),
        JobKind.PROJECT_UNDERSTANDING_RECONCILIATION,
        {},
        "sha256:" + "1" * 64,
        1,
        1,
        "none",
    )

    class Repository:
        def __init__(self) -> None:
            self.claimed = False
            self.finished: dict[str, object] | None = None

        def claim_next_job(self, **_kwargs: object) -> ClaimedJob | None:
            if self.claimed:
                return None
            self.claimed = True
            return claimed

        def reconcile_expired_exhausted_jobs(self, **_kwargs: object) -> int:
            return 0

        def mark_job_running(self, *_args: object, **_kwargs: object) -> None:
            return None

        def cancellation_requested(self, *_args: object, **_kwargs: object) -> bool:
            return False

        def heartbeat_job(self, *_args: object, **_kwargs: object) -> None:
            return None

        def finish_job(self, *_args: object, **kwargs: object) -> None:
            self.finished = kwargs

    repository = Repository()
    worker = object.__new__(DocumentWorker)
    worker._repository = repository  # type: ignore[assignment]
    worker._worker_identity = "synthetic-worker"
    worker._lease_seconds = 30
    worker._organization_id = ORGANIZATION_ID
    worker._workspace_id = WORKSPACE_ID
    worker._stopping = False

    def fail(_claimed: ClaimedJob) -> dict[str, object]:
        raise TypeError("synthetic programming defect")

    worker._execute = fail  # type: ignore[method-assign]

    outcome = worker.run_once()

    assert outcome is not None
    assert outcome.state is JobState.RECONCILIATION_REQUIRED
    assert outcome.outcome_code == "worker_unexpected_handler_error"
    assert repository.finished is not None
    assert repository.finished["terminal_state"] is JobState.RECONCILIATION_REQUIRED
    assert repository.finished["result_manifest"] == {"exception_type": "TypeError"}


def test_document_worker_yields_qwen_at_batch_boundary_for_foreground_assistant() -> None:
    class Repository:
        def __init__(self) -> None:
            self.claim_attempted = False

        def assistant_foreground_active(self, **_kwargs: object) -> bool:
            return True

        def claim_next_job(self, **_kwargs: object) -> None:
            self.claim_attempted = True
            return None

    repository = Repository()
    worker = object.__new__(DocumentWorker)
    worker._repository = repository  # type: ignore[assignment]
    worker._worker_identity = "synthetic-worker"
    worker._lease_seconds = 30
    worker._organization_id = ORGANIZATION_ID
    worker._workspace_id = WORKSPACE_ID
    worker._stopping = False

    assert worker.run_once() is None
    assert not repository.claim_attempted


def test_scoped_document_worker_refills_empty_semantic_queue_at_bounded_idle_interval() -> None:
    claimed = ClaimedJob(
        ORGANIZATION_ID,
        WORKSPACE_ID,
        UUID("018f5c3e-7b00-7000-8000-000000001898"),
        JobKind.PROJECT_WORK_RECONCILIATION,
        {},
        "sha256:" + "8" * 64,
        1,
        1,
        "none",
    )

    class Repository:
        def __init__(self) -> None:
            self.claim_calls = 0
            self.refill_calls = 0

        def assistant_foreground_active(self, **_kwargs: object) -> bool:
            return False

        def reconcile_expired_exhausted_jobs(self, **_kwargs: object) -> int:
            return 0

        def claim_next_job(self, **_kwargs: object) -> ClaimedJob | None:
            self.claim_calls += 1
            return claimed if self.claim_calls == 3 else None

        def refill_workspace_project_work_reconciliation_if_idle(
            self, **kwargs: object
        ) -> tuple[object, ...]:
            assert kwargs["organization_id"] == ORGANIZATION_ID
            assert kwargs["workspace_id"] == WORKSPACE_ID
            self.refill_calls += 1
            return (object(),)

        def mark_job_running(self, *_args: object, **_kwargs: object) -> None:
            return None

        def cancellation_requested(self, *_args: object, **_kwargs: object) -> bool:
            return True

        def finish_job(self, *_args: object, **_kwargs: object) -> None:
            return None

    repository = Repository()
    worker = object.__new__(DocumentWorker)
    worker._repository = repository  # type: ignore[assignment]
    worker._worker_identity = "synthetic-worker"
    worker._lease_seconds = 30
    worker._organization_id = ORGANIZATION_ID
    worker._workspace_id = WORKSPACE_ID
    worker._stopping = False
    worker._next_idle_refill_at = 0.0

    outcome = worker.run_once()

    assert outcome is not None
    assert outcome.state is JobState.CANCELLED
    assert repository.refill_calls == 1
    assert repository.claim_calls == 3


def test_shared_document_worker_recovers_terminal_leases_and_refills_their_workspace() -> None:
    claimed = ClaimedJob(
        ORGANIZATION_ID,
        WORKSPACE_ID,
        UUID("018f5c3e-7b00-7000-8000-000000001897"),
        JobKind.PROJECT_WORK_RECONCILIATION,
        {},
        "sha256:" + "7" * 64,
        1,
        1,
        "none",
    )

    class Repository:
        def __init__(self) -> None:
            self.claim_calls = 0
            self.recovered: list[tuple[object, object]] = []
            self.refilled: list[tuple[object, object]] = []

        def expired_exhausted_job_scopes(self) -> tuple[tuple[UUID, UUID], ...]:
            return ((ORGANIZATION_ID, WORKSPACE_ID),)

        def reconcile_expired_exhausted_jobs(self, **kwargs: object) -> int:
            self.recovered.append((kwargs["organization_id"], kwargs["workspace_id"]))
            return 2

        def claim_next_job(self, **_kwargs: object) -> ClaimedJob | None:
            self.claim_calls += 1
            return claimed if self.claim_calls == 3 else None

        def idle_project_work_reconciliation_scopes(
            self,
        ) -> tuple[tuple[UUID, UUID], ...]:
            return ((ORGANIZATION_ID, WORKSPACE_ID),)

        def refill_workspace_project_work_reconciliation_if_idle(
            self, **kwargs: object
        ) -> tuple[object, ...]:
            self.refilled.append((kwargs["organization_id"], kwargs["workspace_id"]))
            return (object(),)

        def assistant_foreground_active(self, **_kwargs: object) -> bool:
            return False

        def mark_job_running(self, *_args: object, **_kwargs: object) -> None:
            return None

        def cancellation_requested(self, *_args: object, **_kwargs: object) -> bool:
            return True

        def finish_job(self, *_args: object, **_kwargs: object) -> None:
            return None

    repository = Repository()
    worker = object.__new__(DocumentWorker)
    worker._repository = repository  # type: ignore[assignment]
    worker._worker_identity = "shared-worker"
    worker._lease_seconds = 30
    worker._organization_id = None
    worker._workspace_id = None
    worker._stopping = False
    worker._next_idle_refill_at = 0.0

    outcome = worker.run_once()

    assert outcome is not None
    assert outcome.state is JobState.CANCELLED
    assert repository.recovered == [(ORGANIZATION_ID, WORKSPACE_ID)]
    assert repository.refilled == [(ORGANIZATION_ID, WORKSPACE_ID)]


def test_unscoped_document_worker_returns_claim_when_foreground_assistant_is_active() -> None:
    claimed = ClaimedJob(
        ORGANIZATION_ID,
        WORKSPACE_ID,
        UUID("018f5c3e-7b00-7000-8000-000000001899"),
        JobKind.PROJECT_WORK_RECONCILIATION,
        {},
        "sha256:" + "9" * 64,
        1,
        4,
        "none",
    )

    class Repository:
        def __init__(self) -> None:
            self.claimed = False
            self.yielded = False
            self.marked_running = False

        def assistant_foreground_active(self, **kwargs: object) -> bool:
            return kwargs.get("organization_id") == ORGANIZATION_ID

        def claim_next_job(self, **_kwargs: object) -> ClaimedJob | None:
            if self.claimed:
                return None
            self.claimed = True
            return claimed

        def yield_job_for_foreground(self, value: ClaimedJob, **_kwargs: object) -> None:
            assert value is claimed
            self.yielded = True

        def mark_job_running(self, *_args: object, **_kwargs: object) -> None:
            self.marked_running = True

    repository = Repository()
    worker = object.__new__(DocumentWorker)
    worker._repository = repository  # type: ignore[assignment]
    worker._worker_identity = "synthetic-unscoped-worker"
    worker._lease_seconds = 30
    worker._organization_id = None
    worker._workspace_id = None
    worker._stopping = False

    assert worker.run_once() is None
    assert repository.yielded
    assert not repository.marked_running


def test_independent_classification_recovery_refreshes_model_without_reviving_old_chain() -> None:
    claimed = ClaimedJob(
        ORGANIZATION_ID,
        WORKSPACE_ID,
        UUID("018f5c3e-7b00-7000-8000-000000001804"),
        JobKind.DOCUMENT_PAGE_CLASSIFICATION,
        {"classification_recovery_contract": "document-classification-recovery-v1"},
        "sha256:" + "2" * 64,
        1,
        1,
        "none",
    )

    class Repository:
        def __init__(self) -> None:
            self.claimed = False
            self.recovered = 0
            self.refreshed = 0

        def claim_next_job(self, **_kwargs: object) -> ClaimedJob | None:
            if self.claimed:
                return None
            self.claimed = True
            return claimed

        def reconcile_expired_exhausted_jobs(self, **_kwargs: object) -> int:
            return 0

        def mark_job_running(self, *_args: object, **_kwargs: object) -> None:
            return None

        def cancellation_requested(self, *_args: object, **_kwargs: object) -> bool:
            return False

        def heartbeat_job(self, *_args: object, **_kwargs: object) -> None:
            return None

        def finish_job(self, *_args: object, **_kwargs: object) -> None:
            return None

        def recover_dependents_from_success(self, *_args: object) -> int:
            self.recovered += 1
            return 0

        def schedule_incremental_project_reconciliation(self, *_args: object) -> None:
            self.refreshed += 1

    repository = Repository()
    worker = object.__new__(DocumentWorker)
    worker._repository = repository  # type: ignore[assignment]
    worker._worker_identity = "synthetic-worker"
    worker._lease_seconds = 30
    worker._organization_id = ORGANIZATION_ID
    worker._workspace_id = WORKSPACE_ID
    worker._stopping = False
    worker._execute = lambda _claimed: {"decision_count": 1}  # type: ignore[method-assign]

    outcome = worker.run_once()

    assert outcome is not None
    assert outcome.state is JobState.SUCCEEDED
    assert repository.recovered == 0
    assert repository.refreshed == 1


def test_successful_project_work_job_requests_bounded_idle_refill() -> None:
    claimed = ClaimedJob(
        ORGANIZATION_ID,
        WORKSPACE_ID,
        UUID("018f5c3e-7b00-7000-8000-000000001805"),
        JobKind.PROJECT_WORK_RECONCILIATION,
        {},
        "sha256:" + "3" * 64,
        1,
        1,
        "none",
    )

    class Repository:
        def __init__(self) -> None:
            self.claimed = False
            self.refilled = 0

        def claim_next_job(self, **_kwargs: object) -> ClaimedJob | None:
            if self.claimed:
                return None
            self.claimed = True
            return claimed

        def reconcile_expired_exhausted_jobs(self, **_kwargs: object) -> int:
            return 0

        def mark_job_running(self, *_args: object, **_kwargs: object) -> None:
            return None

        def cancellation_requested(self, *_args: object, **_kwargs: object) -> bool:
            return False

        def heartbeat_job(self, *_args: object, **_kwargs: object) -> None:
            return None

        def finish_job(self, *_args: object, **_kwargs: object) -> None:
            return None

        def recover_dependents_from_success(self, *_args: object) -> int:
            return 0

        def refill_project_work_reconciliation_if_idle(self, *_args: object) -> tuple[object, ...]:
            self.refilled += 1
            return ()

    repository = Repository()
    worker = object.__new__(DocumentWorker)
    worker._repository = repository  # type: ignore[assignment]
    worker._worker_identity = "synthetic-worker"
    worker._lease_seconds = 30
    worker._organization_id = ORGANIZATION_ID
    worker._workspace_id = WORKSPACE_ID
    worker._stopping = False
    worker._execute = lambda _claimed: {"decision_count": 1}  # type: ignore[method-assign]

    outcome = worker.run_once()

    assert outcome is not None
    assert outcome.state is JobState.SUCCEEDED
    assert repository.refilled == 1


def test_semantic_extraction_priority_prefers_persisted_structural_roles() -> None:
    """A one-slot worker reaches source-backed structural evidence before estimates."""

    assert _semantic_extraction_priority(("local_estimate",)) == 190
    assert _semantic_extraction_priority(("project_documentation",)) == 195
    assert _semantic_extraction_priority(("local_estimate", "drawing_or_scheme")) == 195
    assert _semantic_extraction_priority(()) == 180


def test_first_pass_semantics_precedes_deep_work_reconciliation() -> None:
    assert _semantic_extraction_priority(()) > 175
    for role in (
        "project_documentation",
        "bill_of_quantities",
        "local_estimate",
        "procurement_notice",
        "engineering_survey",
    ):
        assert _semantic_extraction_priority((role,)) > 175


def test_semantic_coverage_state_distinguishes_unresolved_and_recovered_failures() -> None:
    state = SpinePostgresRepository._semantic_coverage_state

    assert (
        state(
            covered_fragment_count=0,
            expected_fragment_count=8,
            unresolved_failed_fragment_count=2,
        )
        == "failed"
    )
    assert (
        state(
            covered_fragment_count=0,
            expected_fragment_count=8,
            unresolved_failed_fragment_count=0,
        )
        == "not_started"
    )
    assert (
        state(
            covered_fragment_count=7,
            expected_fragment_count=8,
            unresolved_failed_fragment_count=1,
        )
        == "partial"
    )
    assert (
        state(
            covered_fragment_count=8,
            expected_fragment_count=8,
            unresolved_failed_fragment_count=0,
        )
        == "complete"
    )
    assert (
        state(
            covered_fragment_count=8,
            expected_fragment_count=8,
            unresolved_failed_fragment_count=3,
        )
        == "complete"
    )


def test_structure_identity_group_key_admits_typographic_aliases_without_merging() -> None:
    key = _identity_observation_group_key
    assert key("\u041a\u041d\u0421-4") == "\u043a\u043d\u04414"
    assert key("\u041a\u041d\u0421 4") == "\u043a\u043d\u04414"
    assert key("\u041a\u041d\u0421-4") != key("\u041a\u041d\u0421-5")


def test_structure_dossiers_keep_cross_source_identity_unresolved() -> None:
    nodes = [
        {
            "structure_node_id": "node-a",
            "node_kind": "facility",
            "raw_name": "Facility-1",
            "source_locator_id": "locator-a",
        },
        {
            "structure_node_id": "node-b",
            "node_kind": "facility",
            "raw_name": "Facility-1",
            "source_locator_id": "locator-b",
        },
    ]
    relationships = [
        {
            "relationship_kind": "located_in",
            "source_locator_id": "locator-a",
            "subject_structure_node_id": "node-a",
            "object_structure_node_id": None,
            "resolution_state": "unresolved_source_scoped_identity",
        },
        {
            "relationship_kind": "located_in",
            "source_locator_id": "locator-b",
            "subject_structure_node_id": None,
            "object_structure_node_id": "node-b",
            "resolution_state": "resolved_same_evidence",
        },
    ]

    dossiers = SpinePostgresRepository._structure_dossier_rows(nodes, relationships)

    assert [item["structure_node"]["structure_node_id"] for item in dossiers] == [
        "node-a",
        "node-b",
    ]
    assert dossiers[0]["relationships"] == [relationships[0]]
    assert dossiers[0]["unresolved_relationship_count"] == 1
    assert dossiers[1]["relationships"] == [relationships[1]]
    assert dossiers[1]["unresolved_relationship_count"] == 0


def test_structure_dossiers_link_work_observations_only_by_exact_locator() -> None:
    nodes = [
        {
            "structure_node_id": "facility-a",
            "node_kind": "facility",
            "raw_name": "Facility A",
            "source_locator_id": "locator-a",
        }
    ]
    work_packages = [
        {
            "work_package_id": "work-a",
            "package": {
                "work_type": {"raw": "Install pipe"},
                "scope": "zone-a",
                "source_locator_ids": ["locator-a"],
            },
        },
        {
            "work_package_id": "work-b",
            "package": {
                "work_type": {"raw": "Install pipe"},
                "scope": "zone-b",
                "source_locator_ids": ["locator-b"],
            },
        },
    ]

    dossiers = SpinePostgresRepository._structure_dossier_rows([], [], [])
    assert dossiers == []
    dossiers = SpinePostgresRepository._structure_dossier_rows(nodes, [], work_packages)

    assert dossiers[0]["work_association_state"] == "exact_shared_source_locator_candidate"
    assert dossiers[0]["linked_work_observations"] == [
        {"work_observation_id": "work-a", "work_name": "Install pipe", "scope": "zone-a"}
    ]


def test_structure_components_require_exact_resolved_evidence() -> None:
    nodes = [
        {"structure_node_id": "facility", "source_locator_id": "locator-a"},
        {"structure_node_id": "pit", "source_locator_id": "locator-a"},
        {"structure_node_id": "same-name-other-source", "source_locator_id": "locator-b"},
    ]
    relationships = [
        {
            "relationship_candidate_id": "relation-a",
            "source_locator_id": "locator-a",
            "subject_structure_node_id": "facility",
            "object_structure_node_id": "pit",
            "resolution_state": "resolved_same_evidence",
        },
        {
            "relationship_candidate_id": "relation-b",
            "source_locator_id": "locator-b",
            "subject_structure_node_id": "pit",
            "object_structure_node_id": "same-name-other-source",
            "resolution_state": "unresolved_source_scoped_identity",
        },
    ]

    components = SpinePostgresRepository._structure_component_rows(nodes, relationships)

    assert len(components) == 1
    assert [item["structure_node_id"] for item in components[0]["nodes"]] == [
        "facility",
        "pit",
    ]
    assert components[0]["relationships"] == [relationships[0]]


def settings(root: Path, **overrides: object) -> SpineSettings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://app:synthetic@127.0.0.1/spine",
        "lifecycle_database_url": "postgresql+psycopg://lifecycle:synthetic@127.0.0.1/spine",
        "worker_database_url": "postgresql+psycopg://worker:synthetic@127.0.0.1/spine",
        "destruction_database_url": "postgresql+psycopg://destroy:synthetic@127.0.0.1/spine",
        "object_store_root": root,
        "archive_store_root": root / "archives",
        "session_profile": SessionProfile.DEVELOPMENT_LOOPBACK,
        "audit_pepper": "x" * 32,
        "max_file_bytes": 1024 * 1024,
        "max_batch_bytes": 1024 * 1024,
    }
    values.update(overrides)
    return SpineSettings(**values)  # type: ignore[arg-type]


def test_settings_fail_closed_for_unsafe_network_and_implicit_database(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        settings(tmp_path, database_url="sqlite:///spine.db")
    with pytest.raises(ValueError, match="loopback"):
        settings(tmp_path, bind_host="0.0.0.0")
    with pytest.raises(ValueError, match="protected-network"):
        settings(
            tmp_path,
            session_profile=SessionProfile.PROTECTED_REMOTE,
            bind_host="0.0.0.0",
        )


def test_release_identity_is_explicit_and_version_pinned(tmp_path: Path) -> None:
    configured = settings(
        tmp_path,
        release_commit="0123456789abcdef",
        release_profile="public-development-contour",
        deployed_at="2026-08-27T12:00:00+12:00",
        frontend_build_digest="sha256:frontend",
        openapi_digest="sha256:openapi",
        expected_migration_head="0027_public_deployment",
    )
    assert configured.release_commit == "0123456789abcdef"
    assert configured.release_profile == "public-development-contour"
    assert configured.frontend_build_digest == "sha256:frontend"
    assert configured.openapi_digest == "sha256:openapi"
    assert configured.expected_migration_head == "0027_public_deployment"


def test_runtime_migration_supplies_the_required_explicit_database_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def upgrade(configuration: object, revision: str) -> None:
        captured["revision"] = revision
        captured["database_url"] = configuration.cmd_opts.x

    monkeypatch.setattr("asd_kontur.application_spine.runtime.command.upgrade", upgrade)

    configured = settings(tmp_path)
    assert _migrate(configured) == 0
    assert captured == {
        "revision": "head",
        "database_url": [f"database_url={configured.database_url}"],
    }


def test_runtime_migration_uses_separately_supplied_protected_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    protected_url = "postgresql+psycopg://migration-role@localhost/asd"

    def upgrade(configuration: object, revision: str) -> None:
        captured["revision"] = revision
        captured["database_url"] = configuration.cmd_opts.x

    monkeypatch.setattr("asd_kontur.application_spine.runtime.command.upgrade", upgrade)
    monkeypatch.setenv("ASD_MIGRATION_DATABASE_URL", protected_url)

    assert _migrate(settings(tmp_path)) == 0
    assert captured == {"revision": "head", "database_url": [f"database_url={protected_url}"]}


@pytest.mark.parametrize(
    "value",
    ("../secret.pdf", "/absolute.pdf", "folder/../../secret.pdf", "\x00bad.pdf"),
)
def test_relative_path_rejects_traversal_and_invalid_names(value: str) -> None:
    with pytest.raises(IntakeError, match="relative_path_rejected"):
        sanitize_relative_path(value)


def test_display_name_strips_client_path_without_trusting_it() -> None:
    assert sanitize_display_name(r"C:\fakepath\proof.pdf") == "proof.pdf"
    assert sanitize_relative_path("site/evidence/proof.pdf") == "site/evidence/proof.pdf"


def test_content_signature_overrides_client_mime_and_unknown_binary_is_rejected() -> None:
    assert detect_media_type(b"%PDF-1.7\n", "text/plain") == "application/pdf"
    assert detect_media_type(b"plain UTF-8 evidence", "application/pdf") == "text/plain"
    with pytest.raises(IntakeError, match="unsupported_or_mismatched_media_type"):
        detect_media_type(b"\x00\x01\x02", "application/pdf")


def test_object_store_streams_commits_and_rejects_cross_root_key(tmp_path: Path) -> None:
    store = WorkspaceObjectStore(tmp_path, chunk_bytes=65536, max_file_bytes=1024 * 1024)
    payload = b"%PDF-1.7\n" + b"x" * 131072
    staged = store.stage(
        stream=io.BytesIO(payload),
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_ID,
        original_name="source.pdf",
        relative_path="package/source.pdf",
        client_media_type="application/pdf",
    )
    assert staged.size_bytes == len(payload)
    committed = store.commit(staged)
    assert committed.created
    with store.open(staged.object_key) as stream:
        assert verify_bytes_digest(stream.read()) == (staged.digest, len(payload))
    with pytest.raises(IntakeError, match="object_path_invalid"):
        store.open("../outside")


def test_archive_expansion_preserves_relative_paths_and_rejects_traversal(tmp_path: Path) -> None:
    store = WorkspaceObjectStore(tmp_path, chunk_bytes=65536, max_file_bytes=1024 * 1024)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("ПД/пояснительная-записка.txt", "Наименование объекта: Учебный корпус")
        archive.writestr("РД/лист.pdf", b"%PDF-1.7\n")
    staged = store.stage(
        stream=io.BytesIO(payload.getvalue()),
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_ID,
        original_name="исходные.zip",
        relative_path="комплект/исходные.zip",
        client_media_type="application/zip",
    )
    assert staged.media_type == "application/zip"
    members = store.expand_archive(
        staged,
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_ID,
        max_members=10,
        max_total_bytes=1024 * 1024,
    )
    assert [item.relative_path for item in members] == [
        "комплект/исходные/ПД/пояснительная-записка.txt",
        "комплект/исходные/РД/лист.pdf",
    ]
    assert [item.media_type for item in members] == ["text/plain", "application/pdf"]
    for member in members:
        store.abort(member)
    store.abort(staged)

    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../outside.txt", "blocked")
    rejected = store.stage(
        stream=io.BytesIO(unsafe.getvalue()),
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_ID,
        original_name="unsafe.zip",
        relative_path="unsafe.zip",
        client_media_type="application/zip",
    )
    with pytest.raises(IntakeError, match="relative_path_rejected"):
        store.expand_archive(
            rejected,
            organization_id=ORGANIZATION_ID,
            workspace_id=WORKSPACE_ID,
            max_members=10,
            max_total_bytes=1024 * 1024,
        )
    store.abort(rejected)


def test_semantic_digest_ignores_mapping_order_but_not_typed_payload() -> None:
    assert semantic_digest({"b": 2, "a": 1}) == semantic_digest({"a": 1, "b": 2})
    assert semantic_digest({"value": "1"}) != semantic_digest({"value": 1})


def test_lease_keepalive_extends_a_long_running_job_lease() -> None:
    class RecordingRepository:
        def __init__(self) -> None:
            self.called = Event()

        def heartbeat_job(self, *_args: object, **_kwargs: object) -> None:
            self.called.set()

    repository = RecordingRepository()
    claimed = ClaimedJob(
        ORGANIZATION_ID,
        WORKSPACE_ID,
        UUID("018f5c3e-7b00-7000-8000-000000001803"),
        JobKind.OCR_EXTRACTION,
        {},
        "sha256:" + "0" * 64,
        1,
        1,
        "none",
    )
    keepalive = _LeaseKeepalive(  # type: ignore[arg-type]
        repository,
        claimed,
        worker_identity="synthetic-worker",
        lease_seconds=1,
    )

    keepalive.start()
    assert repository.called.wait(timeout=1)
    keepalive.stop()
    keepalive.raise_if_lost()


def test_launchd_and_bounded_log_contracts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_root = tmp_path / "logs"
    log_root.mkdir()
    (log_root / "api.log").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (log_root / "worker.log").write_text("worker\n", encoding="utf-8")
    (log_root / "project-orchestrator.log").write_text("orchestrator\n", encoding="utf-8")
    (log_root / "assistant-worker.log").write_text("assistant\n", encoding="utf-8")
    (log_root / "qwen.log").write_text("qwen\n", encoding="utf-8")
    monkeypatch.setenv("ASD_LOG_ROOT", str(log_root))
    output = tmp_path / "launchd"
    _render_launchd(output, settings(tmp_path))
    api_plist = (output / "ru.asd-kontur.spine.api.plist").read_text(encoding="utf-8")
    assert "StandardOutPath" in api_plist
    assert str(log_root / "api.log") in api_plist
    parsed = plistlib.loads(api_plist.encode())
    assert parsed["Label"] == "ru.asd-kontur.spine.api"
    assert parsed["ProgramArguments"][0] == str(Path(sys.executable).absolute())
    assert parsed["EnvironmentVariables"]["ASD_DATABASE_URL"].startswith("postgresql+psycopg://")
    assert parsed["EnvironmentVariables"]["ASD_EXPECTED_MIGRATION_HEAD"] == ("0033_ntd_memory")
    assert parsed["ExitTimeOut"] == 30
    assistant_plist = plistlib.loads(
        (output / "ru.asd-kontur.spine.assistant-worker.plist").read_bytes()
    )
    assert assistant_plist["Label"] == "ru.asd-kontur.spine.assistant-worker"
    assert assistant_plist["ProgramArguments"][-1] == "run-assistant-worker"
    assert assistant_plist["ExitTimeOut"] == 960
    worker_plist = plistlib.loads((output / "ru.asd-kontur.spine.worker.plist").read_bytes())
    assert worker_plist["ExitTimeOut"] == 960
    orchestrator_plist = plistlib.loads(
        (output / "ru.asd-kontur.spine.project-orchestrator.plist").read_bytes()
    )
    assert orchestrator_plist["Label"] == "ru.asd-kontur.spine.project-orchestrator"
    assert orchestrator_plist["ProgramArguments"][-1] == "run-project-orchestrator"
    qwen_plist = plistlib.loads((output / "ru.asd-kontur.spine.qwen.plist").read_bytes())
    assert qwen_plist["Label"] == "ru.asd-kontur.spine.qwen"
    assert "asd_kontur.assistant.qwen_server" in qwen_plist["ProgramArguments"]
    assert "10240" in (output / "asd-kontur-spine.newsyslog.conf").read_text(encoding="utf-8")
    assert _show_logs(settings(tmp_path), "all", 2) == 0
    monkeypatch.delenv("ASD_LOG_ROOT")
    with pytest.raises(ValueError, match="ASD_LOG_ROOT"):
        _render_launchd(tmp_path / "unconfigured", settings(tmp_path))


def test_launchd_adds_ntd_worker_only_with_explicit_scoped_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_root = tmp_path / "logs"
    log_root.mkdir()
    monkeypatch.setenv("ASD_LOG_ROOT", str(log_root))
    pgpass = tmp_path / "ntd-worker.pgpass"
    pgpass.touch(mode=0o600)
    output = tmp_path / "launchd"
    _render_launchd(
        output,
        settings(
            tmp_path,
            ntd_processing_database_url=("postgresql+psycopg://ntd-worker@127.0.0.1/spine"),
            ntd_processing_pgpassfile=pgpass,
        ),
    )

    ntd_plist = plistlib.loads((output / "ru.asd-kontur.spine.ntd-worker.plist").read_bytes())
    assert ntd_plist["ProgramArguments"][-1] == "run-ntd-worker"
    assert ntd_plist["EnvironmentVariables"]["ASD_NTD_PROCESSING_PGPASSFILE"] == str(pgpass)
    assert ntd_plist["EnvironmentVariables"]["PGPASSFILE"] == str(pgpass)
    assert not (tmp_path / "launchd" / "ru.asd-kontur.spine.ntd-worker.plist").is_symlink()


@pytest.mark.parametrize(
    ("header", "size", "expected"),
    (
        (None, 100, None),
        ("bytes=10-19", 100, (10, 19)),
        ("bytes=90-", 100, (90, 99)),
        ("bytes=-10", 100, (90, 99)),
    ),
)
def test_pdf_range_parser(header: str | None, size: int, expected: tuple[int, int] | None) -> None:
    assert _parse_range(header, size) == expected
