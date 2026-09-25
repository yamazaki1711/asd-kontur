from __future__ import annotations

import csv
from io import StringIO

from asd_kontur.tender.facility_work_projection import (
    build_facility_work_candidate_projection,
    render_facility_work_candidate_schedule_csv,
)


def _package(
    package_id: str,
    locator: str,
    *,
    name: str = "Монтаж опалубки",
    quantity: str | None = None,
    canonical_work_type_id: str | None = None,
) -> dict[str, object]:
    return {
        "work_package_id": package_id,
        "package": {
            "work_package_id": package_id,
            "work_type": {
                "raw": name,
                "normalized": name.casefold(),
                "mapping_status": "resolved" if canonical_work_type_id else "unresolved",
                "canonical_work_type_id": canonical_work_type_id,
            },
            "scope": "page:17",
            "candidate_observation_ids": [f"observation:{package_id}"],
            "quantities": (
                []
                if quantity is None
                else [
                    {
                        "normalized_value": quantity,
                        "normalized_unit": "m3",
                        "source_locator_id": locator,
                    }
                ]
            ),
            "materials": [],
            "source_locator_ids": [locator],
            "uncertainties": ["WORK_TYPE_MAPPING_UNRESOLVED"],
        },
    }


def _identity(candidate_id: str, *locators: str) -> dict[str, object]:
    return {
        "identity_candidate_id": candidate_id,
        "identity_kind": "facility",
        "canonical_label": f"Сооружение {candidate_id}",
        "confidence": "0.81",
        "source_locator_ids": list(locators),
    }


def _named_identity(candidate_id: str, label: str, *locators: str) -> dict[str, object]:
    return {
        **_identity(candidate_id, *locators),
        "canonical_label": label,
    }


def test_projection_consolidates_only_one_exact_identity_and_keeps_quantity_conflict() -> None:
    value = build_facility_work_candidate_projection(
        (
            _package(
                "package-a",
                "locator-a",
                quantity="12",
                canonical_work_type_id="concrete.formwork.install",
            ),
            _package(
                "package-b",
                "locator-b",
                quantity="15",
                canonical_work_type_id="concrete.formwork.install",
            ),
        ),
        (_identity("identity-1", "locator-a", "locator-b"),),
    )

    assert value["coverage"] == {
        "total_work_package_count": 2,
        "exact_identity_package_count": 2,
        "explicit_label_identity_package_count": 0,
        "ambiguous_identity_package_count": 0,
        "unassociated_package_count": 0,
        "consolidated_candidate_group_count": 1,
        "complete": True,
        "candidate_authority": "candidate_only",
        "association_rule": "exact_shared_source_locator_or_explicit_unique_identity_label",
    }
    group = value["candidate_groups"][0]
    assert group["candidate_state"] == "facility_work_candidate_not_confirmed"
    assert group["work_identity_resolution"] == "canonical_work_type"
    assert group["work_package_ids"] == ["package-a", "package-b"]
    assert group["candidate_observation_count"] == 2
    assert len(group["quantities"]) == 2
    assert "QUANTITY_OBSERVATIONS_CONFLICT" in group["uncertainties"]
    assert value["unresolved_work_packages"] == []


def test_projection_keeps_same_work_separate_for_distinct_facility_candidates() -> None:
    value = build_facility_work_candidate_projection(
        (
            _package("package-a", "locator-a"),
            _package("package-b", "locator-b"),
        ),
        (
            _identity("identity-a", "locator-a"),
            _identity("identity-b", "locator-b"),
        ),
    )

    assert len(value["candidate_groups"]) == 2
    assert {item["identity_candidate_id"] for item in value["candidate_groups"]} == {
        "identity-a",
        "identity-b",
    }


def test_projection_does_not_merge_unresolved_same_name_inside_one_facility() -> None:
    value = build_facility_work_candidate_projection(
        (
            _package("package-a", "locator-a"),
            _package("package-b", "locator-b"),
        ),
        (_identity("identity-1", "locator-a", "locator-b"),),
    )

    assert len(value["candidate_groups"]) == 2
    assert {item["work_package_ids"][0] for item in value["candidate_groups"]} == {
        "package-a",
        "package-b",
    }
    assert {item["work_identity_resolution"] for item in value["candidate_groups"]} == {
        "unresolved_observation"
    }


def test_projection_preserves_ambiguous_and_unassociated_packages() -> None:
    value = build_facility_work_candidate_projection(
        (
            _package("ambiguous", "locator-shared"),
            _package("unassociated", "locator-none"),
        ),
        (
            _identity("identity-a", "locator-shared"),
            _identity("identity-b", "locator-shared"),
        ),
    )

    assert value["candidate_groups"] == []
    assert value["coverage"]["ambiguous_identity_package_count"] == 1
    assert value["coverage"]["unassociated_package_count"] == 1
    assert value["coverage"]["complete"] is False
    by_id = {item["work_package_id"]: item for item in value["unresolved_work_packages"]}
    assert by_id["ambiguous"]["association_state"] == "ambiguous_identity_candidates"
    assert by_id["ambiguous"]["identity_candidate_ids"] == ["identity-a", "identity-b"]
    assert by_id["unassociated"]["association_state"] == (
        "no_identity_candidate_at_exact_locator_or_explicit_label"
    )


def test_projection_uses_one_explicit_unique_identity_label_without_claiming_fact() -> None:
    value = build_facility_work_candidate_projection(
        (
            _package(
                "package-los-4",
                "work-locator",
                name="Строительство ЛОС-4",
            ),
        ),
        (_named_identity("identity-los-4", "ЛОС 4", "identity-locator"),),
    )

    assert value["coverage"]["exact_identity_package_count"] == 0
    assert value["coverage"]["explicit_label_identity_package_count"] == 1
    assert value["coverage"]["unassociated_package_count"] == 0
    group = value["candidate_groups"][0]
    assert group["candidate_state"] == "facility_work_candidate_not_confirmed"
    assert group["association_state"] == "explicit_unique_identity_label_candidate"
    assert group["identity_candidate_id"] == "identity-los-4"
    assert group["matched_identity_labels"] == ["лос 4"]
    assert group["shared_source_locator_ids"] == []
    assert group["association_evidence_locator_ids"] == [
        "identity-locator",
        "work-locator",
    ]


def test_projection_keeps_equal_explicit_labels_ambiguous() -> None:
    value = build_facility_work_candidate_projection(
        (_package("package-a", "work-locator", name="Монтаж оборудования КНС-4"),),  # noqa: RUF001
        (
            _named_identity("identity-a", "КНС 4", "identity-a-locator"),  # noqa: RUF001
            _named_identity("identity-b", "КНС-4", "identity-b-locator"),  # noqa: RUF001
        ),
    )

    assert value["candidate_groups"] == []
    assert value["coverage"]["ambiguous_identity_package_count"] == 1
    unresolved = value["unresolved_work_packages"][0]
    assert unresolved["association_state"] == "ambiguous_identity_candidates"
    assert unresolved["identity_candidate_ids"] == ["identity-a", "identity-b"]


def test_projection_prefers_more_specific_explicit_label_candidate() -> None:
    value = build_facility_work_candidate_projection(
        (_package("package-a", "work-locator", name="Строительство ЛОС-4"),),
        (
            _named_identity("identity-generic", "ЛОС", "generic-locator"),
            _named_identity("identity-specific", "ЛОС 4", "specific-locator"),
        ),
    )

    assert value["candidate_groups"][0]["identity_candidate_id"] == "identity-specific"
    assert value["candidate_groups"][0]["matched_identity_labels"] == ["лос 4"]


def test_projection_does_not_select_shorter_numeric_identity_from_range() -> None:
    value = build_facility_work_candidate_projection(
        (
            _package(
                "package-range",
                "work-locator",
                name="Оценка строительства ЛОС 1-3 очередей",
            ),
            _package(
                "package-compound",
                "work-locator-2",
                name="Газоны. ЛОС7.1-7.2",  # noqa: RUF001
            ),
        ),
        (
            _named_identity("identity-los-1", "ЛОС 1", "identity-locator-1"),
            _named_identity("identity-los-7", "ЛОС7", "identity-locator-7"),  # noqa: RUF001
        ),
    )

    assert value["candidate_groups"] == []
    assert value["coverage"]["explicit_label_identity_package_count"] == 0
    assert value["coverage"]["unassociated_package_count"] == 2


def test_projection_does_not_select_one_identity_from_multi_identifier_work_name() -> None:
    value = build_facility_work_candidate_projection(
        (
            _package(
                "package-multi",
                "work-locator",
                name="Планировка ЛОС7-1; ЛОС7-2",  # noqa: RUF001
            ),
        ),
        (_named_identity("identity-los-7-2", "ЛОС7-2", "identity-locator"),),  # noqa: RUF001
    )

    assert value["candidate_groups"] == []
    assert value["coverage"]["explicit_label_identity_package_count"] == 0
    assert value["coverage"]["unassociated_package_count"] == 1


def test_candidate_schedule_keeps_evidence_and_does_not_sum_quantities() -> None:
    projection = build_facility_work_candidate_projection(
        (
            _package(
                "package-a",
                "locator-a",
                quantity="12",
                canonical_work_type_id="concrete.formwork.install",
            ),
            _package(
                "package-b",
                "locator-b",
                quantity="15",
                canonical_work_type_id="concrete.formwork.install",
            ),
        ),
        (_identity("identity-1", "locator-a", "locator-b"),),
    )

    content = render_facility_work_candidate_schedule_csv(
        projection,
        materialization_state="partial",
        coverage_gaps=("SEMANTIC_COVERAGE_PARTIAL",),
        evidence_index={
            "locator-a": {
                "safe_display_name": "Plan A.pdf",
                "document_version": 1,
                "locator_value": "page:17",
            },
            "locator-b": {
                "safe_display_name": "Plan B.pdf",
                "document_version": 2,
                "locator_value": "page:4",
            },
        },
    )

    rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert len(rows) == 1
    row = rows[0]
    assert row["identity_label"] == "Сооружение identity-1"
    assert row["association_state"] == "exact_locator_identity_candidate"
    assert row["matched_identity_labels"] == ""
    assert row["work_package_ids"] == "package-a;package-b"
    assert row["quantity_observations"].count("normalized=") == 2
    assert "12.0" not in row["quantity_observations"]
    assert "Plan A.pdf, version 1, page:17 (locator-a)" in row["source_references"]
    assert "Plan B.pdf, version 2, page:4 (locator-b)" in row["source_references"]
    assert row["candidate_status"] == "facility_work_candidate_not_confirmed"
    assert row["materialization_state"] == "partial"
