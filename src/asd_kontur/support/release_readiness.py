"""Deterministic Support coverage and public-release readiness projection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from .scope_commands import SupportScopeReadinessService

_PROFILE_PATH = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "support"
    / "support-work-type-capability-profiles-v1.json"
)


@dataclass(frozen=True, slots=True)
class SupportReleaseReadiness:
    ready: bool
    status: str
    blockers: tuple[str, ...]
    coverage: dict[str, Any]
    scope: dict[str, Any]
    command_writer: dict[str, Any]


def load_support_work_type_profiles(path: Path = _PROFILE_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "asd-kontur-support-work-type-capability-profiles-v1":
        raise ValueError("support_work_type_profile_schema_invalid")
    profiles = value.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("support_work_type_profiles_empty")
    keys = [str(item.get("work_type_key", "")) for item in profiles]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("support_work_type_profile_key_invalid")
    return cast(dict[str, Any], value)


class SupportReleaseReadinessService:
    """Report independent technical and professional activation blockers."""

    def __init__(self, application_engine: Engine, support_engine: Engine | None) -> None:
        self._application_engine = application_engine
        self._support_engine = support_engine
        self._scope = SupportScopeReadinessService(application_engine)

    def inspect(self, *, owner_identity_id: str, workspace_id: UUID) -> SupportReleaseReadiness:
        writer = self._writer_status()
        scope = self._scope.inspect(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            command_service_configured=bool(writer["role_valid"]),
        )
        coverage = self._coverage()
        blockers: set[str] = set(scope.gaps)
        if not writer["configured"]:
            blockers.add("SUPPORT_COMMAND_DATABASE_URL_UNAVAILABLE")
        elif not writer["role_valid"]:
            blockers.add("SUPPORT_COMMAND_DATABASE_ROLE_INVALID")
        if coverage["production_catalog_entries"] == 0:
            blockers.add("SUPPORT_PRODUCTION_CATALOG_EMPTY")
        if coverage["professionally_approved_work_types"] == 0:
            blockers.add("SUPPORT_PROFESSIONAL_CATALOG_APPROVAL_UNAVAILABLE")
        return SupportReleaseReadiness(
            ready=not blockers,
            status="ready" if not blockers else "blocked",
            blockers=tuple(sorted(blockers)),
            coverage=coverage,
            scope={"status": scope.status, "gaps": list(scope.gaps)},
            command_writer=writer,
        )

    def _writer_status(self) -> dict[str, Any]:
        return support_writer_status(self._support_engine)

    def _coverage(self) -> dict[str, Any]:
        profiles = load_support_work_type_profiles()["profiles"]
        with Session(self._application_engine) as session, session.begin():
            canonical_keys = sorted(
                str(value)
                for value in session.scalars(
                    sa.text(
                        "SELECT DISTINCT wt.work_type_key FROM platform.work_types wt JOIN "
                        "platform.work_type_versions wv ON wv.work_type_id=wt.work_type_id "
                        "WHERE wv.status='active' ORDER BY wt.work_type_key"
                    )
                )
            )
            catalog_rows = list(
                session.execute(
                    sa.text(
                        "SELECT DISTINCT e.stable_key,c.provenance FROM "
                        "platform.work_type_catalog_versions c JOIN "
                        "platform.work_type_catalog_entries e ON e.catalog_id=c.catalog_id AND "
                        "e.catalog_version=c.version WHERE c.status='verified' AND "
                        "e.state='effective'"
                    )
                ).mappings()
            )
            usable_template_keys = sorted(
                str(value)
                for value in session.scalars(
                    sa.text(
                        "SELECT DISTINCT d.document_type_key FROM "
                        "platform.required_document_type_templates m JOIN "
                        "platform.required_document_types d ON "
                        "d.required_document_type_id=m.required_document_type_id JOIN "
                        "platform.template_versions t "
                        "ON t.template_id=m.template_id AND t.version=m.template_version WHERE "
                        "m.applicability_status='active' AND t.qualification_state='active' "
                        "ORDER BY d.document_type_key"
                    )
                )
            )
        catalog_keys = sorted({str(row["stable_key"]) for row in catalog_rows})
        approved = {
            str(row["stable_key"])
            for row in catalog_rows
            if _production_approval_ref(row["provenance"]) is not None
        }
        return {
            "canonical_work_types": len(canonical_keys),
            "canonical_work_type_keys": canonical_keys,
            "production_catalog_entries": len(catalog_keys),
            "production_catalog_work_type_keys": catalog_keys,
            "professionally_approved_work_types": len(approved),
            "professionally_approved_work_type_keys": sorted(approved),
            "resolved_field_requirement_profiles": sum(
                bool(item.get("field_requirement_profile")) for item in profiles
            ),
            "document_requirement_profiles": sum(
                bool(item.get("document_requirement_source")) for item in profiles
            ),
            "usable_template_document_types": len(usable_template_keys),
            "usable_template_document_type_keys": usable_template_keys,
            "package_capable_work_types": sum(
                bool(item.get("package_capable")) for item in profiles
            ),
            "isolated_qualified_work_types": sum(
                bool(item.get("isolated_qualification")) for item in profiles
            ),
            "browser_e2e_work_types": sum(bool(item.get("browser_e2e")) for item in profiles),
            "blocked_qualification_work_types": [
                {
                    "work_type_key": item["work_type_key"],
                    "blockers": list(item.get("blockers", ())),
                }
                for item in profiles
                if item.get("blockers")
            ],
            "qualification_profiles": profiles,
        }


def _production_approval_ref(provenance: object) -> str | None:
    if not isinstance(provenance, dict):
        return None
    value = provenance.get("professional_approval_ref")
    if not isinstance(value, str) or not value.strip():
        return None
    lowered = value.lower()
    if "synthetic" in lowered or lowered.startswith("qualification:"):
        return None
    return value


def support_writer_status(support_engine: Engine | None) -> dict[str, Any]:
    """Validate the configured command connection without exposing credentials.

    The application may remain available when this check fails, but no Support
    scope command service may be constructed from the unqualified connection.
    """

    if support_engine is None:
        return {"configured": False, "role_valid": False, "reason": "not_configured"}
    try:
        with support_engine.connect() as connection:
            row = connection.execute(
                sa.text(
                    "SELECT current_user,pg_has_role(current_user,'asd_support_service','member')"
                )
            ).one()
    except sa.exc.SQLAlchemyError:
        return {"configured": True, "role_valid": False, "reason": "connection_failed"}
    valid = bool(row[1])
    return {
        "configured": True,
        "role_valid": valid,
        "reason": "ready" if valid else "role_membership_missing",
    }
