from __future__ import annotations

from uuid import uuid4

from asd_kontur.support.field_mapping import reconcile_support_field_candidates


def _field(key: str, *, required: bool = True) -> dict[str, object]:
    return {"field_key": key, "required": required, "material": required}


def _candidate(
    key: str, value: str, locator: object, *, candidate_version: int = 1
) -> dict[str, object]:
    return {
        "candidate_id": str(uuid4()),
        "field_key": key,
        "raw_value": value,
        "normalized_value": value,
        "effective_value": value,
        "source_locator_id": str(locator),
        "kernel_candidate_version": candidate_version,
        "validation_status": "passed",
    }


def test_mapping_keeps_same_named_work_scopes_separate() -> None:
    first = uuid4()
    second = uuid4()
    candidates = (
        _candidate("work_description", "Плита корпуса № 1", first),
        _candidate("work_description", "Плита корпуса Б", second),
    )

    result = reconcile_support_field_candidates(
        work_type_key="concrete.slab.install",
        work_source_locator_ids=(first,),
        template_fields=(_field("hidden_work_description"),),
        project_candidates=candidates,
    )

    field = result["fields"][0]
    assert field["state"] == "candidate"
    assert [item["effective_value"] for item in field["observations"]] == ["Плита корпуса № 1"]


def test_mapping_exposes_conflicting_revisions_instead_of_selecting_one() -> None:
    locator = uuid4()
    result = reconcile_support_field_candidates(
        work_type_key="concrete.slab.install",
        work_source_locator_ids=(locator,),
        template_fields=(_field("project_document_reference"),),
        project_candidates=(
            _candidate("document_reference", "КЖ-1, изм. 1", locator),
            _candidate("document_reference", "КЖ-1, изм. 2", locator),
        ),
    )

    assert result["status"] == "conflict"
    assert result["conflict_field_keys"] == ["project_document_reference"]


def test_mapping_uses_latest_corrected_effective_value() -> None:
    locator = uuid4()
    result = reconcile_support_field_candidates(
        work_type_key="concrete.slab.install",
        work_source_locator_ids=(locator,),
        template_fields=(_field("work_start_date"),),
        project_candidates=(_candidate("start_date", "2026-09-10", locator, candidate_version=2),),
    )

    field = result["fields"][0]
    assert field["state"] == "candidate"
    assert field["observations"][0]["kernel_candidate_version"] == 2


def test_mapping_does_not_promote_missing_required_field() -> None:
    result = reconcile_support_field_candidates(
        work_type_key="concrete.slab.install",
        work_source_locator_ids=(),
        template_fields=(_field("act_date"),),
        project_candidates=(),
    )

    assert result["status"] == "partial"
    assert result["missing_field_keys"] == ["act_date"]
