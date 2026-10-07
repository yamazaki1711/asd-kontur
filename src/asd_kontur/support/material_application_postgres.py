"""Record confirmed material use without confusing delivery with application.

The qualified human supplies an actual-use observation linked to an exact work
and a verified source. Deterministic code checks the current admission and
prevents cumulative application beyond the documented delivered quantity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import uuid7

from .material_admission_postgres import MaterialAdmissionService


class MaterialApplicationError(RuntimeError):
    pass


class MaterialApplicationService:
    def __init__(self, application_engine: Engine, support_engine: Engine) -> None:
        self._application_engine = application_engine
        self._support_engine = support_engine

    def record(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        admission_id: UUID,
        evidence_link_id: UUID,
        quantity: Decimal,
        unit_code: str,
        decision_basis: str,
        professional_grant_id: UUID,
        professional_grant_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        unit_code = unit_code.strip()
        decision_basis = " ".join(decision_basis.split())
        if (
            professional_grant_version < 1
            or not 1 <= len(unit_code) <= 32
            or not 3 <= len(decision_basis) <= 1000
            or not 8 <= len(idempotency_key) <= 200
            or not quantity.is_finite()
            or quantity <= 0
            or quantity.as_tuple().exponent < -6
            or quantity > Decimal("999999999999999999.999999")
        ):
            raise MaterialApplicationError("material_application_input_invalid")
        with Session(self._application_engine) as session, session.begin():
            try:
                organization_id = MaterialAdmissionService._owner_scope(
                    session, owner_identity_id, workspace_id
                )
                MaterialAdmissionService._require_active_workspace(
                    session, organization_id, workspace_id
                )
            except RuntimeError as exc:
                raise MaterialApplicationError(str(exc)) from exc
        with Session(self._support_engine) as session, session.begin():
            session.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(organization_id), True),
                    sa.func.set_config("asd.workspace_id", str(workspace_id), True),
                )
            ).one()
            if (
                session.scalar(
                    sa.text(
                        "SELECT NOT rolsuper AND NOT rolbypassrls AND "
                        "pg_has_role(current_user,'asd_support_service','member') "
                        "FROM pg_roles WHERE rolname=current_user"
                    )
                )
                is not True
            ):
                raise MaterialApplicationError("material_application_writer_role_invalid")
            try:
                MaterialAdmissionService._require_active_workspace(
                    session, organization_id, workspace_id
                )
            except RuntimeError as exc:
                raise MaterialApplicationError(str(exc)) from exc
            admission = (
                session.execute(
                    sa.text(
                        "SELECT support_process_id,material_batch_id,material_batch_version,"
                        "work_instance_id,work_instance_version,outcome,incoming_control_id,"
                        "delivered_quantity,delivered_unit FROM "
                        "workspace.support_material_admissions WHERE organization_id=:o AND "
                        "workspace_id=:w AND admission_id=:admission"
                    ),
                    {"o": organization_id, "w": workspace_id, "admission": admission_id},
                )
                .mappings()
                .first()
            )
            if admission is None or admission["outcome"] != "admitted":
                raise MaterialApplicationError("material_application_admission_unavailable")
            batch_id = admission["material_batch_id"]
            work_id = admission["work_instance_id"]
            batch_version = admission["material_batch_version"]
            work_version = admission["work_instance_version"]
            # One batch can be admitted for several works. Serialize its global
            # quantity budget, not merely each work's share, in this transaction.
            session.execute(
                sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:identity,0))"),
                {
                    "identity": (
                        f"support-material-application:{organization_id}:{workspace_id}:{batch_id}"
                    )
                },
            )
            fingerprint = semantic_digest(
                {
                    "contract": "support-material-application@1.0.0",
                    "workspace_id": workspace_id,
                    "admission_id": admission_id,
                    "evidence_link_id": evidence_link_id,
                    "quantity": str(quantity),
                    "unit_code": unit_code,
                    "decision_basis": decision_basis,
                    "professional_grant_id": professional_grant_id,
                    "professional_grant_version": professional_grant_version,
                }
            )
            prior = (
                session.execute(
                    sa.text(
                        "SELECT material_application_id,application_digest,quantity,unit_code,"
                        "recorded_at FROM workspace.material_applications WHERE organization_id=:o "
                        "AND workspace_id=:w AND idempotency_key=:key"
                    ),
                    {"o": organization_id, "w": workspace_id, "key": idempotency_key},
                )
                .mappings()
                .first()
            )
            if prior is not None:
                if prior["application_digest"] != fingerprint:
                    raise MaterialApplicationError("material_application_idempotency_conflict")
                return self._view(prior)
            if admission["delivered_quantity"] is None or not admission["delivered_unit"]:
                raise MaterialApplicationError("material_application_delivery_basis_missing")
            if unit_code != admission["delivered_unit"]:
                raise MaterialApplicationError("material_application_unit_incompatible")
            delivery_bases = session.execute(
                sa.text(
                    "SELECT DISTINCT delivered_quantity,delivered_unit FROM "
                    "(SELECT DISTINCT ON (work_instance_id) delivered_quantity,"
                    "delivered_unit,outcome FROM workspace.support_material_admissions "
                    "WHERE organization_id=:o AND workspace_id=:w AND "
                    "material_batch_id=:batch AND material_batch_version=:batch_version "
                    "ORDER BY work_instance_id,admitted_at DESC,admission_id DESC) latest "
                    "WHERE outcome='admitted'"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "batch": batch_id,
                    "batch_version": batch_version,
                },
            ).all()
            if {(row[0], row[1]) for row in delivery_bases} != {
                (admission["delivered_quantity"], unit_code)
            }:
                raise MaterialApplicationError("material_application_delivery_basis_conflict")
            current = (
                session.execute(
                    sa.text(
                        "SELECT "
                        "(SELECT max(version) FROM workspace.material_batch_versions WHERE "
                        "organization_id=:o AND workspace_id=:w AND material_batch_id=:batch) "
                        "AS batch_version,"
                        "(SELECT max(version) FROM workspace.work_instance_versions WHERE "
                        "organization_id=:o AND workspace_id=:w AND work_instance_id=:work) "
                        "AS work_version,"
                        "(SELECT preflight_id FROM "
                        "workspace.support_incoming_inspection_preflights "
                        "WHERE organization_id=:o AND workspace_id=:w AND material_batch_id=:batch "
                        "AND material_batch_version=:batch_version ORDER BY submitted_at DESC,"
                        "preflight_id DESC LIMIT 1) AS preflight_id,"
                        "(SELECT admission_id FROM workspace.support_material_admissions WHERE "
                        "organization_id=:o AND workspace_id=:w AND material_batch_id=:batch "
                        "AND work_instance_id=:work ORDER BY admitted_at DESC,admission_id DESC "
                        "LIMIT 1) AS admission_id"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "batch": batch_id,
                        "work": work_id,
                        "batch_version": batch_version,
                    },
                )
                .mappings()
                .one()
            )
            if (
                current["batch_version"] != batch_version
                or current["work_version"] != work_version
                or current["preflight_id"] != admission["incoming_control_id"]
                or current["admission_id"] != admission_id
            ):
                raise MaterialApplicationError("material_application_admission_stale")
            process_state = session.scalar(
                sa.text(
                    "SELECT state FROM workspace.support_processes WHERE organization_id=:o "
                    "AND workspace_id=:w AND support_process_id=:process"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "process": admission["support_process_id"],
                },
            )
            if process_state not in {
                "scope_configured",
                "executing",
                "waiting_for_evidence",
                "ready_for_deliverable",
                "waiting_for_authority",
            }:
                raise MaterialApplicationError("material_application_support_process_unavailable")
            requirement = session.scalar(
                sa.text(
                    "SELECT 1 FROM workspace.material_requirement_versions r JOIN "
                    "workspace.material_batch_versions b ON "
                    "b.organization_id=r.organization_id AND b.workspace_id=r.workspace_id "
                    "AND b.material_batch_id=:batch AND b.version=:batch_version AND "
                    "b.material_class_id=r.material_class_id AND "
                    "b.material_class_version=r.material_class_version WHERE "
                    "r.organization_id=:o AND r.workspace_id=:w AND "
                    "r.work_instance_id=:work AND r.work_instance_version=:work_version "
                    "AND r.applicability='applicable' AND "
                    "r.status IN ('required','conditional','satisfied') AND r.version=(SELECT "
                    "max(v.version) FROM workspace.material_requirement_versions v WHERE "
                    "v.organization_id=r.organization_id AND v.workspace_id=r.workspace_id "
                    "AND v.material_requirement_id=r.material_requirement_id) LIMIT 1"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "batch": batch_id,
                    "batch_version": batch_version,
                    "work": work_id,
                    "work_version": work_version,
                },
            )
            if requirement != 1:
                raise MaterialApplicationError("material_application_requirement_stale")
            evidence = session.scalar(
                sa.text(
                    "SELECT 1 FROM workspace.evidence_links e JOIN "
                    "workspace.source_versions s ON s.organization_id=e.organization_id "
                    "AND s.workspace_id=e.workspace_id AND "
                    "s.source_version_id=e.source_version_id JOIN "
                    "workspace.source_artifacts a ON a.organization_id=s.organization_id "
                    "AND a.workspace_id=s.workspace_id AND "
                    "a.source_artifact_id=s.source_artifact_id WHERE "
                    "e.organization_id=:o AND e.workspace_id=:w AND "
                    "e.evidence_link_id=:evidence AND e.subject_type='work_instance' "
                    "AND e.subject_id=:work AND e.subject_version=:version "
                    "AND e.evidence_role='material_application' AND "
                    "e.validity_status='verified' AND a.source_kind='field_document' "
                    "AND a.status='active'"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "evidence": evidence_link_id,
                    "work": work_id,
                    "version": str(work_version),
                },
            )
            if evidence != 1:
                raise MaterialApplicationError("material_application_evidence_unverified")
            grant = (
                session.execute(
                    sa.text(
                        "SELECT grant_version,professional_qualification_ref,effective_from,"
                        "effective_until FROM workspace.support_professional_grants WHERE "
                        "organization_id=:o AND workspace_id=:w AND grant_id=:grant AND "
                        "human_identity_id=:owner AND capability='support.material.apply' "
                        "AND status='active' ORDER BY grant_version DESC LIMIT 1"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "grant": professional_grant_id,
                        "owner": owner_identity_id,
                    },
                )
                .mappings()
                .first()
            )
            now = datetime.now(UTC)
            if (
                grant is None
                or grant["grant_version"] != professional_grant_version
                or not str(grant["professional_qualification_ref"] or "").strip()
                or grant["effective_from"] > now
                or (grant["effective_until"] is not None and grant["effective_until"] <= now)
            ):
                raise MaterialApplicationError(
                    "material_application_professional_grant_unavailable"
                )
            totals = (
                session.execute(
                    sa.text(
                        "SELECT unit_code,coalesce(sum(quantity),0) AS applied FROM "
                        "workspace.material_applications WHERE organization_id=:o AND "
                        "workspace_id=:w AND material_batch_id=:batch GROUP BY unit_code"
                    ),
                    {"o": organization_id, "w": workspace_id, "batch": batch_id},
                )
                .mappings()
                .all()
            )
            if any(row["unit_code"] != unit_code for row in totals):
                raise MaterialApplicationError("material_application_prior_unit_incompatible")
            applied = sum((Decimal(str(row["applied"])) for row in totals), Decimal(0))
            if applied + quantity > Decimal(str(admission["delivered_quantity"])):
                raise MaterialApplicationError("material_application_exceeds_delivery")
            row = (
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.material_applications "
                        "(organization_id,workspace_id,material_application_id,material_batch_id,"
                        "material_batch_version,work_instance_id,work_instance_version,quantity,"
                        "unit_code,precision_scale,evidence_link_id,application_digest,recorded_at,"
                        "admission_id,authority_grant_id,authority_grant_version,idempotency_key,"
                        "decision_basis) VALUES (:o,:w,:id,:batch,:batch_version,:work,"
                        ":work_version,:quantity,:unit,:precision,:evidence,:digest,"
                        "CURRENT_TIMESTAMP,:admission,:grant,:grant_version,:key,:basis) RETURNING "
                        "material_application_id,application_digest,quantity,unit_code,recorded_at"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "id": uuid7(),
                        "batch": batch_id,
                        "batch_version": batch_version,
                        "work": work_id,
                        "work_version": work_version,
                        "quantity": quantity,
                        "unit": unit_code,
                        "precision": max(0, -quantity.as_tuple().exponent),
                        "evidence": evidence_link_id,
                        "digest": fingerprint,
                        "admission": admission_id,
                        "grant": professional_grant_id,
                        "grant_version": professional_grant_version,
                        "key": idempotency_key,
                        "basis": decision_basis,
                    },
                )
                .mappings()
                .one()
            )
            return self._view(row)

    @staticmethod
    def _view(row: Any) -> dict[str, Any]:
        return {
            "material_application_id": row["material_application_id"],
            "quantity": row["quantity"],
            "unit_code": row["unit_code"],
            "application_digest": row["application_digest"],
            "recorded_at": row["recorded_at"],
        }
