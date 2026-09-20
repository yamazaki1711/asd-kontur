"""Authorized Support-scope configuration through an isolated writer connection."""

from __future__ import annotations

from dataclasses import dataclass
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
        with self._application_engine.connect() as connection:
            organization_id = connection.scalar(
                sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
                {"owner": owner_identity_id, "workspace": workspace_id},
            )
        if organization_id is None:
            raise SupportScopeCommandError("workspace_not_found")
        return UUID(str(organization_id))

    def _verify_inputs(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        configuration: SupportScopeConfiguration,
    ) -> None:
        with Session(self._application_engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            mode = (
                session.execute(
                    sa.text(
                        "SELECT mode,state FROM workspace.mode_executions WHERE organization_id=:o "
                        "AND workspace_id=:w AND mode_execution_id=:mode"
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
