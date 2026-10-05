from __future__ import annotations

from uuid import UUID

from asd_kontur.document_understanding.project_identity import (
    reconcile_project_identity_fields,
)


def _field(
    ordinal: int,
    *,
    key: str,
    value: str,
    source: int,
    status: str = "candidate",
) -> dict[str, object]:
    return {
        "candidate_id": UUID(int=ordinal),
        "version": 1,
        "field_key": key,
        "raw_value": value,
        "normalized_value": value,
        "source_version_id": UUID(int=source),
        "source_locator_id": UUID(int=10_000 + ordinal),
        "status": status,
    }


def test_verified_project_field_outranks_unverified_facility_observations() -> None:
    result = reconcile_project_identity_fields(
        [
            _field(
                1,
                key="purpose",
                value="Отведение и очистка поверхностных сточных вод",
                source=1,
                status="verified",
            ),
            _field(2, key="purpose", value="Подача стоков на ЛОС-4", source=2),
            _field(3, key="purpose", value="Очистка стоков ЛОС-7", source=3),
        ]
    )

    assert result["verified_fields"]["purpose"]["candidate_id"] == str(UUID(int=1))
    assert result["verified_fields"]["purpose"]["authority"] == "verified"
    assert result["outcomes"]["purpose"]["state"] == "verified"
    assert "purpose" not in result["candidate_fields"]


def test_project_title_consensus_is_candidate_and_merges_spacing_variants() -> None:
    result = reconcile_project_identity_fields(
        [
            _field(1, key="project_name", value="Система оз. Култучное", source=1),
            _field(2, key="object_name", value="Система оз.Култучное", source=2),
            _field(3, key="project_name", value="Система оз.  Култучное", source=3),
            _field(4, key="object_name", value="ЛОС-4", source=4),
        ]
    )

    candidate = result["candidate_fields"]["object_name"]
    assert candidate["authority"] == "candidate_consensus"
    assert candidate["source_count"] == 3
    assert candidate["observation_count"] == 3
    assert candidate["alternative_value_count"] == 1
    assert result["outcomes"]["object_name"]["state"] == "candidate_consensus"
    assert "object_name" not in result["verified_fields"]


def test_repetition_in_one_source_does_not_create_project_consensus() -> None:
    result = reconcile_project_identity_fields(
        [
            _field(1, key="project_name", value="Локальный заголовок", source=1),
            _field(2, key="project_name", value="Локальный заголовок", source=1),
        ]
    )

    assert "object_name" not in result["candidate_fields"]
    assert result["outcomes"]["object_name"]["state"] == "candidate_only"


def test_tied_cross_source_values_remain_unresolved() -> None:
    result = reconcile_project_identity_fields(
        [
            _field(1, key="project_name", value="Первый объект", source=1),
            _field(2, key="project_name", value="Первый объект", source=2),
            _field(3, key="project_name", value="Второй объект", source=3),
            _field(4, key="project_name", value="Второй объект", source=4),
        ]
    )

    assert "object_name" not in result["candidate_fields"]
    assert result["outcomes"]["object_name"]["state"] == "candidate_conflict"
