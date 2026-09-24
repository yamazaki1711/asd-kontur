"""Versioned correction and authoritative confirmation of Support fields."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid, uuid7
from asd_kontur.kernel import (
    ConfirmCandidateCommand,
    FactClass,
    FactValueKind,
    PostgresCommonKernel,
)
from asd_kontur.persistence.scope import WorkspaceContext

from .production_postgres import SupportProductionRepository


class SupportFieldCommandError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SupportFieldCommandResult:
    action: str
    work_package_id: UUID
    field_key: str
    candidate_id: UUID
    candidate_version: int
    fact_id: UUID | None
    fact_version: int | None
    outcome: str


class SupportFieldCommandService:
    """Apply corrections through the harness writer and facts through the kernel writer."""

    def __init__(
        self,
        application_engine: Engine,
        harness_engine: Engine,
        kernel_engine: Engine,
    ) -> None:
        self._application_engine = application_engine
        self._harness_engine = harness_engine
        self._kernel_engine = kernel_engine
        self._production = SupportProductionRepository(application_engine)
        self._kernel = PostgresCommonKernel(kernel_engine)

    def correct(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        work_package_id: UUID,
        field_key: str,
        candidate_id: UUID,
        candidate_version: int,
        corrected_value: str,
        reason: str,
    ) -> SupportFieldCommandResult:
        observation = self._eligible_observation(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            work_package_id=work_package_id,
            field_key=field_key,
            candidate_id=candidate_id,
            candidate_version=candidate_version,
        )
        if len(corrected_value.strip()) < 1 or len(reason.strip()) < 3:
            raise SupportFieldCommandError("support_field_correction_invalid")
        organization_id = UUID(str(observation["organization_id"]))
        self._verify_writer_role(self._harness_engine, "asd_harness_service")
        with Session(self._harness_engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            current = (
                session.execute(
                    sa.text(
                        "SELECT candidate_version,output_schema_version FROM "
                        "workspace.candidate_versions WHERE organization_id=:o AND workspace_id=:w "
                        "AND candidate_id=:candidate ORDER BY candidate_version DESC LIMIT 1 "
                        "FOR UPDATE"
                    ),
                    {"o": organization_id, "w": workspace_id, "candidate": candidate_id},
                )
                .mappings()
                .one_or_none()
            )
            if current is None or int(current["candidate_version"]) != candidate_version:
                raise SupportFieldCommandError("support_field_candidate_version_conflict")
            new_version = candidate_version + 1
            field_path = str(observation["field_path"])
            digest = semantic_digest(
                {
                    "candidate_id": candidate_id,
                    "candidate_version": new_version,
                    "parent_version": candidate_version,
                    "field_path": field_path,
                    "corrected_value": corrected_value.strip(),
                    "reason": reason.strip(),
                    "actor": owner_identity_id,
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.candidate_versions "
                    "(organization_id,workspace_id,candidate_id,candidate_version,parent_version,"
                    "attempt_id,origin,status,output_schema_version,digest,created_at) VALUES "
                    "(:o,:w,:candidate,:version,:parent,NULL,'human_draft','validated_candidate',"
                    "'support-field-correction@1.0.0',:digest,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "candidate": candidate_id,
                    "version": new_version,
                    "parent": candidate_version,
                    "digest": digest,
                },
            )
            prior_fields = list(
                session.execute(
                    sa.text(
                        "SELECT field_path,value_type,typed_value,unit FROM "
                        "workspace.candidate_fields "
                        "WHERE organization_id=:o AND workspace_id=:w AND candidate_id=:candidate "
                        "AND candidate_version=:version ORDER BY field_path"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "candidate": candidate_id,
                        "version": candidate_version,
                    },
                ).mappings()
            )
            for item in prior_fields:
                typed_value = (
                    corrected_value.strip()
                    if str(item["field_path"]) == field_path
                    else item["typed_value"]
                )
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.candidate_fields "
                        "(organization_id,workspace_id,candidate_id,candidate_version,field_path,"
                        "value_type,typed_value,unit,validation_state) VALUES "
                        "(:o,:w,:candidate,:version,:path,:type,CAST(:value AS jsonb),:unit,"
                        "'passed')"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "candidate": candidate_id,
                        "version": new_version,
                        "path": item["field_path"],
                        "type": item["value_type"],
                        "value": json.dumps(typed_value, ensure_ascii=False),
                        "unit": item["unit"],
                    },
                )
            evidence_rows = list(
                session.execute(
                    sa.text(
                        "SELECT field_path,source_version_id,source_locator_id,evidence_link_id,"
                        "evidence_role FROM workspace.candidate_field_evidence WHERE "
                        "organization_id=:o AND workspace_id=:w AND candidate_id=:candidate AND "
                        "candidate_version=:version ORDER BY field_path,source_locator_id"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "candidate": candidate_id,
                        "version": candidate_version,
                    },
                ).mappings()
            )
            for item in evidence_rows:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.candidate_field_evidence "
                        "(organization_id,workspace_id,candidate_id,candidate_version,field_path,"
                        "source_version_id,source_locator_id,evidence_link_id,evidence_role) "
                        "VALUES "
                        "(:o,:w,:candidate,:version,:path,:source,:locator,:evidence,'correction_basis')"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "candidate": candidate_id,
                        "version": new_version,
                        "path": item["field_path"],
                        "source": item["source_version_id"],
                        "locator": item["source_locator_id"],
                        "evidence": item["evidence_link_id"],
                    },
                )
            validation_id = uuid7()
            session.execute(
                sa.text(
                    "INSERT INTO workspace.vlm_validation_runs "
                    "(organization_id,workspace_id,validation_run_id,candidate_id,candidate_version,"
                    "validator_profile_version,required_validators,skipped_validators,status,digest,"
                    "validated_at) VALUES (:o,:w,:validation,:candidate,:version,"
                    "'support-field-correction-validator@1.0.0',ARRAY['source_locator_preserved',"
                    "'typed_value_nonempty'],ARRAY[]::text[],'passed',:digest,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "validation": validation_id,
                    "candidate": candidate_id,
                    "version": new_version,
                    "digest": digest,
                },
            )
            decision_id = deterministic_uuid(
                f"support-field-correction:{workspace_id}:{work_package_id}:{field_key}:"
                f"{candidate_id}"
            )
            prior_decision = session.scalar(
                sa.text(
                    "SELECT max(decision_version) FROM workspace.support_field_candidate_decisions "
                    "WHERE organization_id=:o AND workspace_id=:w AND decision_id=:decision"
                ),
                {"o": organization_id, "w": workspace_id, "decision": decision_id},
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_field_candidate_decisions "
                    "(organization_id,workspace_id,decision_id,decision_version,work_package_id,"
                    "work_package_version,target_field_key,candidate_id,from_candidate_version,"
                    "to_candidate_version,action,actor_identity_id,reason,decision_digest) VALUES "
                    "(:o,:w,:decision,:decision_version,:work,:work_version,:field,:candidate,"
                    ":from_version,:to_version,'corrected',:owner,:reason,:digest)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "decision": decision_id,
                    "decision_version": int(prior_decision or 0) + 1,
                    "work": work_package_id,
                    "work_version": int(observation["work_package_version"]),
                    "field": field_key,
                    "candidate": candidate_id,
                    "from_version": candidate_version,
                    "to_version": new_version,
                    "owner": owner_identity_id,
                    "reason": reason.strip(),
                    "digest": digest,
                },
            )
        return SupportFieldCommandResult(
            "corrected",
            work_package_id,
            field_key,
            candidate_id,
            new_version,
            None,
            None,
            "candidate_version_created",
        )

    def confirm(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        work_package_id: UUID,
        field_key: str,
        candidate_id: UUID,
        candidate_version: int,
        idempotency_key: str,
    ) -> SupportFieldCommandResult:
        observation = self._eligible_observation(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            work_package_id=work_package_id,
            field_key=field_key,
            candidate_id=candidate_id,
            candidate_version=candidate_version,
        )
        if len(idempotency_key) < 8:
            raise SupportFieldCommandError("support_field_idempotency_key_invalid")
        organization_id = UUID(str(observation["organization_id"]))
        self._verify_writer_role(self._kernel_engine, "asd_kernel_service")
        with Session(self._kernel_engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            policy = (
                session.execute(
                    sa.text(
                        "SELECT confirmation_policy_id,version FROM "
                        "platform.confirmation_policy_versions WHERE status='active' AND "
                        "('observation'=ANY(auto_confirm_fact_classes) OR "
                        "'observation'=ANY(professional_fact_classes)) ORDER BY "
                        "effective_from DESC,"
                        "confirmation_policy_id LIMIT 1"
                    )
                )
                .mappings()
                .one_or_none()
            )
            grant = (
                session.execute(
                    sa.text(
                        "SELECT grant_id,grant_version FROM "
                        "workspace.confirmation_authority_grants "
                        "WHERE organization_id=:o AND workspace_id=:w AND human_identity_id=:owner "
                        "AND capability='fact.confirm' AND 'observation'=ANY(fact_classes) AND "
                        "status='active' AND effective_from<=CURRENT_TIMESTAMP AND "
                        "(effective_until IS NULL OR effective_until>CURRENT_TIMESTAMP) "
                        "ORDER BY grant_version DESC,grant_id LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id, "owner": owner_identity_id},
                )
                .mappings()
                .one_or_none()
            )
            fact_id = deterministic_uuid(
                f"support-field-fact:{organization_id}:{workspace_id}:{work_package_id}:{field_key}"
            )
            current = session.scalar(
                sa.text(
                    "SELECT current_version FROM workspace.workspace_facts WHERE "
                    "organization_id=:o AND workspace_id=:w AND fact_id=:fact"
                ),
                {"o": organization_id, "w": workspace_id, "fact": fact_id},
            )
        if policy is None:
            raise SupportFieldCommandError("confirmation_policy_unavailable")
        if grant is None:
            raise SupportFieldCommandError("fact_confirmation_authority_unavailable")
        correlation_id = uuid7()
        result = self._kernel.confirm_candidate(
            context=WorkspaceContext(
                organization_id,
                workspace_id,
                owner_identity_id,
                "service.support-field-command-v1",
                correlation_id,
                uuid7(),
            ),
            command=ConfirmCandidateCommand(
                uuid7(),
                uuid7(),
                fact_id,
                int(current or 0),
                candidate_id,
                candidate_version,
                str(observation["field_path"]),
                f"support.aosr:{work_package_id}:{field_key}",
                FactClass.OBSERVATION,
                FactValueKind.TEXT,
                UUID(str(policy["confirmation_policy_id"])),
                str(policy["version"]),
                "qualified_human",
                owner_identity_id,
                UUID(str(grant["grant_id"])),
                int(grant["grant_version"]),
                None,
                None,
                None,
                None,
                idempotency_key,
                correlation_id,
                uuid7(),
                datetime.now(UTC),
            ),
        )
        return SupportFieldCommandResult(
            "confirmed",
            work_package_id,
            field_key,
            candidate_id,
            candidate_version,
            fact_id,
            result.fact_version,
            result.outcome.value,
        )

    def _eligible_observation(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        work_package_id: UUID,
        field_key: str,
        candidate_id: UUID,
        candidate_version: int,
    ) -> dict[str, Any]:
        view = self._production.view(owner_identity_id=owner_identity_id, workspace_id=workspace_id)
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        for work in view.get("source_field_candidates", []):
            if str(work.get("work_package_id")) != str(work_package_id):
                continue
            for field in work.get("fields", []):
                if str(field.get("field_key")) != field_key or field.get("state") != "candidate":
                    continue
                for item in field.get("observations", []):
                    if str(item.get("candidate_id")) != str(candidate_id):
                        continue
                    if int(item.get("kernel_candidate_version") or 0) != candidate_version:
                        continue
                    return {
                        **item,
                        "organization_id": organization_id,
                        "work_package_version": int(work["work_package_version"]),
                        "field_path": f"/project/{item['field_key']}",
                    }
        raise SupportFieldCommandError("support_field_candidate_not_eligible")

    def _resolve_scope(self, owner_identity_id: str, workspace_id: UUID) -> UUID:
        with self._application_engine.connect() as connection:
            value = connection.scalar(
                sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
                {"owner": owner_identity_id, "workspace": workspace_id},
            )
        if value is None:
            raise SupportFieldCommandError("workspace_not_found")
        return UUID(str(value))

    @staticmethod
    def _verify_writer_role(engine: Engine, role: str) -> None:
        with engine.connect() as connection:
            valid = connection.scalar(
                sa.text(
                    "SELECT NOT rolsuper AND NOT rolbypassrls AND "
                    "pg_has_role(current_user,:role,'member') FROM pg_roles WHERE "
                    "rolname=current_user"
                ),
                {"role": role},
            )
        if valid is not True:
            raise SupportFieldCommandError("support_field_command_role_invalid")


def _scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()
