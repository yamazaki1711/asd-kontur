"""Authorized Support-scope configuration through an isolated writer connection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7
from asd_kontur.persistence.scope import WorkspaceContext

from .models import ProfessionalAuthority, SupportScope
from .postgres import PostgresSupportProcess, StartSupportProcess


class SupportScopeCommandError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SupportScopeConfiguration:
    mode_execution_id: UUID
    rule_set_version_id: UUID
    process_definition_version: str
    authority_profile_version: str
    contract_registry_version: str
    policy_versions: tuple[str, ...]
    deliverable_scope: tuple[str, ...]
    classification: str
    purpose: str
    source_class_allowlist: tuple[str, ...]
    input_manifest_digest: str
    professional_grant_id: UUID
    professional_grant_version: int
    professional_qualification_ref: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class SupportScopeConfigurationResult:
    support_process_id: UUID
    revision: int
    state: str
    outcome: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class SupportScopeReadiness:
    status: str
    gaps: tuple[str, ...]
    configuration: dict[str, Any] | None


class SupportScopeReadinessService:
    """Derive an owner-scoped Support command without inventing authority data."""

    def __init__(self, application_engine: Engine) -> None:
        self._application_engine = application_engine

    def inspect(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        command_service_configured: bool,
    ) -> SupportScopeReadiness:
        organization_id = _resolve_authorized_scope(
            self._application_engine, owner_identity_id, workspace_id
        )
        with Session(self._application_engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            configured = session.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.support_processes WHERE "
                    "organization_id=:o AND workspace_id=:w"
                ),
                {"o": organization_id, "w": workspace_id},
            )
            if configured:
                return SupportScopeReadiness("configured", (), None)
            mode = (
                session.execute(
                    sa.text(
                        "SELECT m.mode_execution_id,m.process_definition_key,"
                        "m.process_definition_version,m.authority_profile_key,"
                        "m.authority_profile_version,m.policy_assignment_key,"
                        "m.policy_assignment_version,m.rule_set_key,m.rule_set_version,"
                        "w.contract_registry_version FROM workspace.mode_executions m "
                        "JOIN workspace.workspaces w ON w.organization_id=m.organization_id "
                        "AND w.workspace_id=m.workspace_id WHERE m.organization_id=:o AND "
                        "m.workspace_id=:w AND m.mode='Support' AND "
                        "m.state NOT IN ('cancelled','failed') ORDER BY m.updated_at DESC,"
                        "m.mode_execution_id DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            manifest = (
                session.execute(
                    sa.text(
                        "SELECT manifest_digest FROM workspace.intake_manifests WHERE "
                        "organization_id=:o AND workspace_id=:w AND "
                        "status IN ('admitted','partial') "
                        "ORDER BY created_at DESC,intake_manifest_id DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            grant = (
                session.execute(
                    sa.text(
                        "SELECT grant_id,grant_version,professional_qualification_ref FROM "
                        "workspace.support_professional_grants WHERE organization_id=:o AND "
                        "workspace_id=:w AND human_identity_id=:owner AND "
                        "capability='support.scope.configure' AND status='active' AND "
                        "effective_from<=:now AND "
                        "(effective_until IS NULL OR effective_until>:now) "
                        "ORDER BY grant_version DESC,grant_id DESC LIMIT 1"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "owner": owner_identity_id,
                        "now": datetime.now(UTC),
                    },
                )
                .mappings()
                .one_or_none()
            )
            rule_set_version_id = None
            if mode is not None:
                rule_set_version_id = session.scalar(
                    sa.text(
                        "SELECT rule_set_version_id FROM platform.rule_set_versions WHERE "
                        "rule_set_key=:key AND version=:version AND status='active'"
                    ),
                    {"key": mode["rule_set_key"], "version": mode["rule_set_version"]},
                )
        gaps = tuple(
            code
            for code, missing in (
                ("SUPPORT_COMMAND_SERVICE_UNAVAILABLE", not command_service_configured),
                ("SUPPORT_MODE_EXECUTION_UNAVAILABLE", mode is None),
                ("SUPPORT_RULE_SET_UNAVAILABLE", mode is not None and rule_set_version_id is None),
                ("SUPPORT_INPUT_MANIFEST_UNAVAILABLE", manifest is None),
                ("SUPPORT_SCOPE_AUTHORITY_UNAVAILABLE", grant is None),
            )
            if missing
        )
        if gaps:
            return SupportScopeReadiness("blocked", gaps, None)
        assert mode is not None
        assert manifest is not None
        assert grant is not None
        assert rule_set_version_id is not None
        mode_id = str(mode["mode_execution_id"])
        manifest_digest = str(manifest["manifest_digest"])
        grant_id = str(grant["grant_id"])
        return SupportScopeReadiness(
            "ready",
            (),
            {
                "mode_execution_id": mode_id,
                "rule_set_version_id": str(rule_set_version_id),
                "process_definition_version": _qualified_version(
                    mode["process_definition_key"], mode["process_definition_version"]
                ),
                "authority_profile_version": _qualified_version(
                    mode["authority_profile_key"], mode["authority_profile_version"]
                ),
                "contract_registry_version": str(mode["contract_registry_version"]),
                "policy_versions": [
                    _qualified_version(
                        mode["policy_assignment_key"], mode["policy_assignment_version"]
                    )
                ],
                "deliverable_scope": ["id_package"],
                "classification": "workspace_project_records",
                "purpose": "Prepare the supported ID package for this Support execution",
                "source_class_allowlist": ["pd_rd", "field_evidence"],
                "input_manifest_digest": manifest_digest,
                "professional_grant_id": grant_id,
                "professional_grant_version": int(grant["grant_version"]),
                "professional_qualification_ref": str(grant["professional_qualification_ref"]),
                "idempotency_key": (
                    f"support-scope:{mode_id}:{manifest_digest[-16:]}:"
                    f"{grant_id}:{int(grant['grant_version'])}"
                ),
            },
        )


class SupportScopeCommandService:
    """Bind one authorised Support scope to exact workspace input evidence.

    The Product API resolves owner access using its low-privilege connection.
    The write itself is performed only by the separately configured Support
    service connection, where ``PostgresSupportProcess`` re-verifies the
    active human grant in the same transaction as the append-only records.
    """

    def __init__(self, application_engine: Engine, support_engine: Engine) -> None:
        self._application_engine = application_engine
        self._support_engine = support_engine
        self._support_process = PostgresSupportProcess(support_engine)

    def configure(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        configuration: SupportScopeConfiguration,
        correlation_id: UUID,
    ) -> SupportScopeConfigurationResult:
        organization_id = self._resolve_authorized_scope(owner_identity_id, workspace_id)
        self._verify_inputs(
            organization_id=organization_id,
            workspace_id=workspace_id,
            owner_identity_id=owner_identity_id,
            configuration=configuration,
        )
        self._verify_support_writer_role()
        support_process_id = uuid7()
        authority = ProfessionalAuthority(
            owner_identity_id,
            configuration.professional_grant_id,
            configuration.professional_grant_version,
            "support.scope.configure",
            configuration.professional_qualification_ref,
        )
        scope = SupportScope(
            organization_id,
            workspace_id,
            configuration.mode_execution_id,
            support_process_id,
            configuration.rule_set_version_id,
            configuration.process_definition_version,
            configuration.authority_profile_version,
            configuration.contract_registry_version,
            configuration.policy_versions,
            configuration.deliverable_scope,
            configuration.classification,
            configuration.purpose,
        )
        outcome = self._support_process.start(
            context=WorkspaceContext(
                organization_id,
                workspace_id,
                owner_identity_id,
                "service.support-scope-command-v0.1",
                correlation_id,
                uuid7(),
            ),
            command=StartSupportProcess(
                uuid7(),
                scope,
                configuration.source_class_allowlist,
                configuration.input_manifest_digest,
                authority,
                configuration.idempotency_key,
                correlation_id,
                uuid7(),
            ),
        )
        effective_process_id = self._effective_process_id(
            organization_id=organization_id,
            workspace_id=workspace_id,
            mode_execution_id=configuration.mode_execution_id,
        )
        return SupportScopeConfigurationResult(
            effective_process_id,
            outcome.revision,
            outcome.state.value,
            outcome.outcome,
            outcome.reason_code,
        )

    def _verify_support_writer_role(self) -> None:
        with self._support_engine.connect() as connection:
            valid = connection.scalar(
                sa.text(
                    "SELECT NOT rolsuper AND NOT rolbypassrls AND "
                    "pg_has_role(current_user,'asd_support_service','member') "
                    "FROM pg_roles WHERE rolname=current_user"
                )
            )
        if valid is not True:
            raise SupportScopeCommandError("support_command_role_invalid")

    def _resolve_authorized_scope(self, owner_identity_id: str, workspace_id: UUID) -> UUID:
        return _resolve_authorized_scope(self._application_engine, owner_identity_id, workspace_id)

    def _verify_inputs(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        owner_identity_id: str,
        configuration: SupportScopeConfiguration,
    ) -> None:
        with Session(self._application_engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            mode = (
                session.execute(
                    sa.text(
                        "SELECT m.mode,m.state,m.process_definition_key,"
                        "m.process_definition_version,m.authority_profile_key,"
                        "m.authority_profile_version,m.policy_assignment_key,"
                        "m.policy_assignment_version,m.rule_set_key,m.rule_set_version,"
                        "w.contract_registry_version FROM workspace.mode_executions m "
                        "JOIN workspace.workspaces w ON w.organization_id=m.organization_id "
                        "AND w.workspace_id=m.workspace_id WHERE m.organization_id=:o "
                        "AND m.workspace_id=:w AND m.mode_execution_id=:mode"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "mode": configuration.mode_execution_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if mode is None or mode["mode"] != "Support":
                raise SupportScopeCommandError("support_mode_execution_not_found")
            if mode["state"] in {"cancelled", "failed"}:
                raise SupportScopeCommandError("support_mode_execution_not_active")
            rule_set_version_id = session.scalar(
                sa.text(
                    "SELECT rule_set_version_id FROM platform.rule_set_versions WHERE "
                    "rule_set_key=:key AND version=:version AND status='active'"
                ),
                {"key": mode["rule_set_key"], "version": mode["rule_set_version"]},
            )
            expected_contract = {
                "rule_set_version_id": str(rule_set_version_id),
                "process_definition_version": _qualified_version(
                    mode["process_definition_key"], mode["process_definition_version"]
                ),
                "authority_profile_version": _qualified_version(
                    mode["authority_profile_key"], mode["authority_profile_version"]
                ),
                "contract_registry_version": str(mode["contract_registry_version"]),
                "policy_versions": (
                    _qualified_version(
                        mode["policy_assignment_key"], mode["policy_assignment_version"]
                    ),
                ),
            }
            actual_contract = {
                "rule_set_version_id": str(configuration.rule_set_version_id),
                "process_definition_version": configuration.process_definition_version,
                "authority_profile_version": configuration.authority_profile_version,
                "contract_registry_version": configuration.contract_registry_version,
                "policy_versions": configuration.policy_versions,
            }
            if rule_set_version_id is None or actual_contract != expected_contract:
                raise SupportScopeCommandError("support_scope_contract_mismatch")
            if configuration.deliverable_scope != ("id_package",) or (
                configuration.source_class_allowlist != ("pd_rd", "field_evidence")
            ):
                raise SupportScopeCommandError("support_scope_boundary_unsupported")
            manifest_found = session.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.intake_manifests WHERE organization_id=:o "
                    "AND workspace_id=:w AND manifest_digest=:digest "
                    "AND status IN ('admitted','partial')"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "digest": configuration.input_manifest_digest,
                },
            )
            if manifest_found != 1:
                raise SupportScopeCommandError("support_input_manifest_not_found")
            grant_found = session.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.support_professional_grants WHERE "
                    "organization_id=:o AND workspace_id=:w AND grant_id=:grant AND "
                    "grant_version=:version AND human_identity_id=:owner AND "
                    "capability='support.scope.configure' AND status='active' AND "
                    "professional_qualification_ref=:qualification AND "
                    "effective_from<=:now AND "
                    "(effective_until IS NULL OR effective_until>:now)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "grant": configuration.professional_grant_id,
                    "version": configuration.professional_grant_version,
                    "owner": owner_identity_id,
                    "qualification": configuration.professional_qualification_ref,
                    "now": datetime.now(UTC),
                },
            )
            if grant_found != 1:
                raise SupportScopeCommandError("support_scope_authority_mismatch")

    def _effective_process_id(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        mode_execution_id: UUID,
    ) -> UUID:
        with Session(self._support_engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            process_id = session.scalar(
                sa.text(
                    "SELECT support_process_id FROM workspace.support_processes WHERE "
                    "organization_id=:o AND workspace_id=:w AND mode_execution_id=:mode"
                ),
                {"o": organization_id, "w": workspace_id, "mode": mode_execution_id},
            )
        if process_id is None:
            raise SupportScopeCommandError("support_scope_result_not_found")
        return UUID(str(process_id))


def _set_scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def _resolve_authorized_scope(engine: Engine, owner_identity_id: str, workspace_id: UUID) -> UUID:
    with engine.connect() as connection:
        organization_id = connection.scalar(
            sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
            {"owner": owner_identity_id, "workspace": workspace_id},
        )
    if organization_id is None:
        raise SupportScopeCommandError("workspace_not_found")
    return UUID(str(organization_id))


def _qualified_version(key: object, version: object) -> str:
    return f"{key}@{version}"
