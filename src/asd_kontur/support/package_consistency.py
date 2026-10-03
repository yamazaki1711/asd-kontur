"""Deterministic consistency assessment for one exact Support ID-package version."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def assess_id_package_consistency(view: Mapping[str, Any]) -> dict[str, Any]:
    """Reconcile register, members, artifacts and field evidence without inventing facts."""

    package = _mapping(view.get("package"))
    if not package:
        return {
            "contract": "support.id-package-consistency@1.0.0",
            "status": "not_formed",
            "package": None,
            "checks": [],
            "gaps": ["ID_PACKAGE_NOT_FORMED"],
            "candidate_boundary": True,
        }

    checks: list[dict[str, Any]] = []
    gaps: list[str] = []
    members = sorted(
        (dict(item) for item in _records(view.get("memberships"))),
        key=lambda item: (int(item.get("ordinal") or 0), str(item.get("membership_id") or "")),
    )
    registers = tuple(_records(view.get("registers")))
    register = dict(registers[-1]) if registers else {}
    manifest = _mapping(register.get("register_manifest"))
    package_identity = {
        "id_package_id": str(package.get("id_package_id") or ""),
        "version": int(package.get("version") or 0),
    }

    _record_check(
        checks,
        gaps,
        code="CURRENT_REGISTER_PRESENT",
        passed=bool(register),
        gap="ID_PACKAGE_REGISTER_UNAVAILABLE",
        details={"register_candidate_id": str(register.get("register_candidate_id") or "")},
    )
    _record_check(
        checks,
        gaps,
        code="REGISTER_BOUND_TO_CURRENT_PACKAGE",
        passed=bool(manifest)
        and str(manifest.get("package_id") or "") == package_identity["id_package_id"]
        and int(manifest.get("package_version") or 0) == package_identity["version"],
        gap="ID_PACKAGE_REGISTER_VERSION_MISMATCH",
        details={
            "manifest_package_id": str(manifest.get("package_id") or ""),
            "manifest_package_version": int(manifest.get("package_version") or 0),
        },
    )

    ordinals = [int(item.get("ordinal") or 0) for item in members]
    register_members = [
        item for item in members if item.get("role") == "register" and item.get("ordinal") == 1
    ]
    _record_check(
        checks,
        gaps,
        code="MEMBERSHIP_ORDER_UNAMBIGUOUS",
        passed=bool(members)
        and len(ordinals) == len(set(ordinals))
        and ordinals == list(range(1, len(members) + 1))
        and len(register_members) == 1,
        gap="ID_PACKAGE_MEMBERSHIP_ORDER_INVALID",
        details={"ordinals": ordinals, "register_count": len(register_members)},
    )

    expected = [_manifest_member(item) for item in members if item.get("role") != "register"]
    observed = [_manifest_member(item) for item in _records(manifest.get("documents"))]
    _record_check(
        checks,
        gaps,
        code="REGISTER_MATCHES_CURRENT_MEMBERSHIP",
        passed=expected == observed,
        gap="ID_PACKAGE_REGISTER_MEMBERSHIP_MISMATCH",
        details={"expected": expected, "observed": observed},
    )

    referenced_runs: set[str] = set()
    finalized_count = 0
    candidate_count = 0
    incomplete_count = 0
    for member in members:
        if member.get("role") == "register":
            continue
        role = str(member.get("role") or "unresolved_document_type")
        state = _member_state(member)
        run_id = str(member.get("generation_run_id") or "")
        if run_id:
            referenced_runs.add(run_id)
        if state == "finalized":
            finalized_count += 1
            valid = bool(
                member.get("finalized_document_id") and member.get("finalized_document_digest")
            )
            _record_check(
                checks,
                gaps,
                code=f"FINALIZED_ARTIFACT:{role}",
                passed=valid,
                gap=f"ID_FINALIZED_ARTIFACT_INCOMPLETE:{role}",
                details={"membership_id": str(member.get("membership_id") or "")},
            )
        elif state == "generated_candidate":
            candidate_count += 1
            valid = bool(
                member.get("generated_candidate_id")
                and member.get("object_reference")
                and member.get("bytes_digest")
                and str(member.get("job_state") or "") == "succeeded"
            )
            _record_check(
                checks,
                gaps,
                code=f"GENERATED_CANDIDATE_ARTIFACT:{role}",
                passed=valid,
                gap=f"ID_GENERATED_CANDIDATE_INCOMPLETE:{role}",
                details={"membership_id": str(member.get("membership_id") or "")},
            )
        else:
            incomplete_count += 1
            gaps.append(f"ID_MEMBER_{state.upper()}:{role}")
            checks.append(
                {
                    "code": f"MEMBER_AVAILABLE:{role}",
                    "outcome": "blocked",
                    "details": {
                        "membership_id": str(member.get("membership_id") or ""),
                        "state": state,
                        "blocker_codes": sorted(
                            str(value) for value in member.get("blocker_codes") or ()
                        ),
                    },
                }
            )

        if state in {"generated_candidate", "finalized"}:
            template_valid = (
                str(member.get("template_qualification_state") or "") == "active"
                and str(member.get("template_official_status") or "") == "verified"
                and str(member.get("template_assurance_class") or "") == "production"
            )
            _record_check(
                checks,
                gaps,
                code=f"TEMPLATE_PRODUCTION_QUALIFIED:{role}",
                passed=template_valid,
                gap=f"ID_TEMPLATE_NOT_PRODUCTION_QUALIFIED:{role}",
                details={
                    "template_id": str(member.get("template_id") or ""),
                    "template_version": str(member.get("template_version") or ""),
                },
            )

    field_groups = _field_groups(view.get("field_resolutions"))
    for run_id in sorted(referenced_runs):
        fields = field_groups.get(run_id, {})
        _record_check(
            checks,
            gaps,
            code=f"FIELD_RESOLUTIONS_PRESENT:{run_id}",
            passed=bool(fields),
            gap=f"ID_FIELD_RESOLUTIONS_UNAVAILABLE:{run_id}",
            details={"field_count": len(fields)},
        )
        for field_key, field in sorted(fields.items()):
            if not field["material"]:
                continue
            state = field["state"]
            ready = state == "not_applicable" or (
                state == "confirmed" and bool(field["evidence_links"] and field["locators"])
            )
            _record_check(
                checks,
                gaps,
                code=f"MATERIAL_FIELD_EVIDENCE:{run_id}:{field_key}",
                passed=ready,
                gap=f"ID_MATERIAL_FIELD_EVIDENCE_INCOMPLETE:{run_id}:{field_key}",
                details={
                    "state": state,
                    "evidence_link_ids": sorted(field["evidence_links"]),
                    "source_locator_ids": sorted(field["locators"]),
                },
            )

    hard_failures = [item for item in checks if item["outcome"] == "failed"]
    if hard_failures:
        status = "inconsistent"
    elif incomplete_count:
        status = "incomplete"
    elif candidate_count:
        status = "review_required"
    elif members and finalized_count == len(members) - 1:
        status = "complete"
    else:
        status = "incomplete"
    return {
        "contract": "support.id-package-consistency@1.0.0",
        "status": status,
        "package": package_identity,
        "checks": checks,
        "gaps": sorted(set(gaps)),
        "candidate_boundary": True,
        "summary": {
            "member_count": max(0, len(members) - 1),
            "generated_candidate_count": candidate_count,
            "finalized_count": finalized_count,
            "incomplete_count": incomplete_count,
            "referenced_generation_run_count": len(referenced_runs),
        },
    }


def _record_check(
    checks: list[dict[str, Any]],
    gaps: list[str],
    *,
    code: str,
    passed: bool,
    gap: str,
    details: Mapping[str, Any],
) -> None:
    checks.append({"code": code, "outcome": "passed" if passed else "failed", "details": details})
    if not passed:
        gaps.append(gap)


def _manifest_member(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ordinal": int(item.get("ordinal") or 0),
        "membership_id": str(item.get("membership_id") or ""),
        "membership_version": int(item.get("membership_version") or item.get("version") or 0),
        "role": str(item.get("role") or ""),
        "subject_kind": str(item.get("subject_kind") or ""),
        "subject_ref": str(item.get("subject_ref") or ""),
        "copies": int(item.get("copies") or item.get("required_copy_count") or 0),
        "stage": str(item.get("stage") or ""),
        "state": str(item.get("state") or ""),
    }


def _member_state(member: Mapping[str, Any]) -> str:
    if member.get("finalized_document_id"):
        return "finalized"
    if member.get("generated_candidate_id"):
        return "generated_candidate"
    return str(member.get("state") or "missing")


def _field_groups(value: Any) -> dict[str, dict[str, dict[str, Any]]]:
    groups: dict[str, dict[str, dict[str, Any]]] = {}
    for item in _records(value):
        run_id = str(item.get("generation_run_id") or "")
        field_key = str(item.get("field_key") or "")
        if not run_id or not field_key:
            continue
        field = groups.setdefault(run_id, {}).setdefault(
            field_key,
            {
                "state": str(item.get("state") or ""),
                "material": bool(item.get("material")),
                "evidence_links": set(),
                "locators": set(),
            },
        )
        if item.get("evidence_link_id"):
            field["evidence_links"].add(str(item["evidence_link_id"]))
        if item.get("source_locator_id"):
            field["locators"].add(str(item["source_locator_id"]))
    return groups


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _records(value: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return ()
    return (item for item in value if isinstance(item, Mapping))
