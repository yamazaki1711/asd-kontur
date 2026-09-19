from __future__ import annotations

from asd_kontur.audit.package_preflight import build_expected_actual_preflight
from asd_kontur.audit.preflight_export import render_expected_actual_preflight_csv


def _requirement(
    requirement_id: str, *, work_package_id: str, state: str = "required"
) -> dict[str, object]:
    return {
        "document_requirement_id": requirement_id,
        "document_requirement_version": 1,
        "work_package_id": work_package_id,
        "document_type": "support.aosr",
        "required_stage": "work_acceptance",
        "requirement_state": state,
        "authority_status": "normative_verified" if state == "required" else "normative_gap",
        "minimum_copies": 1,
        "basis_refs": [f"rule:{requirement_id}"],
        "blockers": [],
    }


def _membership(requirement_id: str, state: str, *, membership_id: str) -> dict[str, object]:
    return {
        "membership_id": membership_id,
        "document_requirement_id": requirement_id,
        "document_requirement_version": 1,
        "state": state,
        "ordinal": 2,
        "evidence_refs": [f"package:{membership_id}"],
        "blocker_codes": [],
    }


def test_preflight_keeps_identically_named_requirements_in_their_scopes() -> None:
    value = build_expected_actual_preflight(
        (
            _requirement("requirement-a", work_package_id="scope-a"),
            _requirement("requirement-b", work_package_id="scope-b"),
        ),
        matrix={"matrix_id": "matrix", "version": 1},
        package={"id_package_id": "package", "version": 1, "status": "incomplete"},
        memberships=(
            _membership("requirement-a", "generated_candidate", membership_id="membership-a"),
        ),
    )

    assert value["status"] == "partial"
    assert [item["item_key"] for item in value["items"]] == [
        "scope-a:requirement-a:v1",
        "scope-b:requirement-b:v1",
    ]
    assert [item["preflight_state"] for item in value["items"]] == [
        "generated_candidate",
        "missing",
    ]
    assert value["items"][0]["membership_ids"] == ["membership-a"]
    assert value["items"][1]["membership_ids"] == []
    assert "GENERATED_CANDIDATE_REQUIRES_AUDIT" in value["items"][0]["gaps"]
    assert "REQUIRED_DOCUMENT_NOT_IN_PACKAGE" in value["items"][1]["gaps"]


def test_preflight_never_promotes_finalized_member_to_audit_satisfied() -> None:
    value = build_expected_actual_preflight(
        (_requirement("requirement-a", work_package_id="scope-a"),),
        matrix={"matrix_id": "matrix", "version": 3},
        package={"id_package_id": "package", "version": 4, "status": "complete"},
        memberships=(
            {
                **_membership("requirement-a", "finalized", membership_id="membership-a"),
                "finalized_document_id": "finalized-a",
            },
        ),
    )

    item = value["items"][0]
    assert item["preflight_state"] == "awaiting_audit"
    assert "FINALIZED_DOCUMENT_REQUIRES_AUDIT" in item["gaps"]
    assert value["authority_layers"]["not_claimed"] == "no_preflight_item_is_audit_satisfied"


def test_preflight_exposes_unformed_and_unresolved_boundaries() -> None:
    value = build_expected_actual_preflight(
        (
            _requirement("requirement-a", work_package_id="scope-a"),
            _requirement("requirement-b", work_package_id="scope-b", state="unresolved"),
        ),
        matrix={"matrix_id": "matrix", "version": 1},
        package=None,
        memberships=(),
    )

    assert [item["preflight_state"] for item in value["items"]] == [
        "not_formed",
        "unresolved_requirement",
    ]
    assert {"ID_PACKAGE_NOT_FORMED", "REQUIREMENT_AUTHORITY_UNRESOLVED"} <= set(value["gaps"])


def test_preflight_export_keeps_scope_specific_identity_and_authority_boundary() -> None:
    preflight = build_expected_actual_preflight(
        (
            _requirement("requirement-a", work_package_id="scope-a"),
            _requirement("requirement-b", work_package_id="scope-b"),
        ),
        matrix={"matrix_id": "matrix", "version": 1},
        package={"id_package_id": "package", "version": 1, "status": "incomplete"},
        memberships=(
            _membership("requirement-a", "generated_candidate", membership_id="membership-a"),
        ),
    )

    data = render_expected_actual_preflight_csv(preflight).decode("utf-8-sig")

    assert "scope-a:requirement-a:v1" in data
    assert "scope-b:requirement-b:v1" in data
    assert "independent_audit_evidence_and_authority_required" in data
