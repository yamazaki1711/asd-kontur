"""Qualified, source-bound material admission for a declared Support work scope.

The application role verifies identities and evidence. Only the scoped Support
writer can append the decision, and the database write fence rejects late work
after a workspace starts deletion. No batch, work, grant or field fact is
created by this service.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import uuid7
from asd_kontur.kernel.models import Quantity

from .evaluation import evaluate_material_admission
from .models import MaterialBatchEvidence, ProfessionalAuthority


class MaterialAdmissionError(RuntimeError):
    pass


class MaterialAdmissionService:
    def __init__(self, application_engine: Engine, support_engine: Engine) -> None:
        self._application_engine = application_engine
        self._support_engine = support_engine

    def context(self, *, owner_identity_id: str, workspace_id: UUID) -> dict[str, Any]:
        """Return only current, owner-scoped choices for an admission decision.

        Truncation flags disclose when the bounded display omits rows; callers must not
        interpret a truncated list as the complete project inventory.
        """
        with Session(self._application_engine) as session, session.begin():
            organization_id = self._owner_scope(session, owner_identity_id, workspace_id)
            self._require_active_workspace(session, organization_id, workspace_id)
            params = {"o": organization_id, "w": workspace_id, "owner": owner_identity_id}
            queries = {
                "processes": (
                    "SELECT support_process_id,state FROM workspace.support_processes "
                    "WHERE organization_id=:o AND workspace_id=:w AND state IN "
                    "('scope_configured','executing','waiting_for_evidence',"
                    "'ready_for_deliverable','waiting_for_authority') "
                    "ORDER BY updated_at DESC LIMIT 201"
                ),
                "batches": (
                    "SELECT b.material_batch_id,b.version,b.batch_reference,b.admission_state,"
                    "b.material_class_id,b.material_class_version,"
                    "m.title AS material_name FROM workspace.material_batch_versions b "
                    "JOIN platform.material_class_versions m ON "
                    "m.material_class_id=b.material_class_id AND "
                    "m.version=b.material_class_version WHERE b.organization_id=:o AND "
                    "b.workspace_id=:w AND b.version=(SELECT max(v.version) FROM "
                    "workspace.material_batch_versions v WHERE v.organization_id=b.organization_id "
                    "AND v.workspace_id=b.workspace_id AND "
                    "v.material_batch_id=b.material_batch_id) "
                    "AND b.admission_state IN ('candidate','admitted') "
                    "ORDER BY b.recorded_at DESC,b.material_batch_id LIMIT 201"
                ),
                "works": (
                    "SELECT wi.work_instance_id,wi.version,wi.work_state,wt.title AS work_name "
                    "FROM workspace.work_instance_versions wi JOIN platform.work_type_versions wt "
                    "ON wt.work_type_id=wi.work_type_id AND wt.version=wi.work_type_version "
                    "WHERE wi.organization_id=:o AND wi.workspace_id=:w AND wi.version=(SELECT "
                    "max(v.version) FROM workspace.work_instance_versions v WHERE "
                    "v.organization_id=wi.organization_id AND v.workspace_id=wi.workspace_id "
                    "AND v.work_instance_id=wi.work_instance_id) AND wi.work_state IN "
                    "('planned','ready','in_progress') ORDER BY wi.recorded_at DESC,"
                    "wi.work_instance_id LIMIT 201"
                ),
                "requirements": (
                    "SELECT r.material_requirement_id,r.version,r.work_instance_id,"
                    "r.work_instance_version,r.material_class_id,r.material_class_version,"
                    "r.applicability,r.status,r.quantity,r.unit_code,"
                    "m.title AS material_name FROM workspace.material_requirement_versions r "
                    "JOIN platform.material_class_versions m ON "
                    "m.material_class_id=r.material_class_id AND "
                    "m.version=r.material_class_version "
                    "WHERE r.organization_id=:o AND r.workspace_id=:w AND "
                    "r.version=(SELECT max(v.version) FROM "
                    "workspace.material_requirement_versions v "
                    "WHERE v.organization_id=r.organization_id AND v.workspace_id=r.workspace_id "
                    "AND v.material_requirement_id=r.material_requirement_id) "
                    "ORDER BY r.recorded_at DESC,r.material_requirement_id LIMIT 201"
                ),
                "preflights": (
                    "SELECT p.preflight_id,p.material_batch_id,p.material_batch_version,"
                    "p.batch_reference,p.material_name,p.result,p.submitted_at FROM "
                    "workspace.support_incoming_inspection_preflights p WHERE "
                    "p.organization_id=:o AND p.workspace_id=:w AND "
                    "p.material_batch_id IS NOT NULL "
                    "AND p.preflight_id=(SELECT p2.preflight_id FROM "
                    "workspace.support_incoming_inspection_preflights p2 WHERE "
                    "p2.organization_id=p.organization_id AND p2.workspace_id=p.workspace_id "
                    "AND p2.material_batch_id=p.material_batch_id AND "
                    "p2.material_batch_version=p.material_batch_version ORDER BY "
                    "p2.submitted_at DESC,p2.preflight_id DESC LIMIT 1) "
                    "ORDER BY p.submitted_at DESC LIMIT 201"
                ),
                "evidence": (
                    "SELECT e.evidence_link_id,e.subject_id AS material_batch_id,"
                    "e.subject_version AS material_batch_version,e.evidence_role,"
                    "e.source_locator_id,l.locator_kind,l.locator_key,"
                    "a.title AS source_title FROM workspace.evidence_links e "
                    "JOIN workspace.source_locators l ON l.organization_id=e.organization_id "
                    "AND l.workspace_id=e.workspace_id AND l.source_locator_id=e.source_locator_id "
                    "JOIN workspace.source_versions s ON s.organization_id=e.organization_id "
                    "AND s.workspace_id=e.workspace_id AND s.source_version_id=e.source_version_id "
                    "JOIN workspace.source_artifacts a ON a.organization_id=s.organization_id "
                    "AND a.workspace_id=s.workspace_id AND "
                    "a.source_artifact_id=s.source_artifact_id "
                    "WHERE e.organization_id=:o AND e.workspace_id=:w AND "
                    "e.subject_type='material_batch' AND e.validity_status='verified' AND "
                    "e.evidence_role IN ('material_certificate','material_passport',"
                    "'delivery_quantity') ORDER BY e.created_at DESC LIMIT 201"
                ),
                "grants": (
                    "SELECT g.grant_id,g.grant_version,g.professional_qualification_ref "
                    "FROM workspace.support_professional_grants g WHERE "
                    "g.organization_id=:o AND g.workspace_id=:w AND "
                    "g.human_identity_id=:owner AND g.capability='support.material.admit' "
                    "AND g.status='active' AND g.effective_from<=CURRENT_TIMESTAMP "
                    "AND (g.effective_until IS NULL OR g.effective_until>CURRENT_TIMESTAMP) "
                    "AND g.grant_version=(SELECT max(v.grant_version) FROM "
                    "workspace.support_professional_grants v WHERE "
                    "v.organization_id=g.organization_id "
                    "AND v.workspace_id=g.workspace_id AND v.grant_id=g.grant_id) "
                    "ORDER BY g.grant_id LIMIT 201"
                ),
                "decisions": (
                    "SELECT admission_id,material_batch_id,material_batch_version,work_instance_id,"
                    "work_instance_version,outcome,reason_codes,admitted_at AS decided_at "
                    "FROM workspace.support_material_admissions WHERE organization_id=:o AND "
                    "workspace_id=:w ORDER BY admitted_at DESC,admission_id DESC LIMIT 201"
                ),
            }
            result: dict[str, Any] = {}
            truncated: list[str] = []
            for name, query in queries.items():
                rows = [dict(row) for row in session.execute(sa.text(query), params).mappings()]
                if len(rows) > 200:
                    truncated.append(name)
                result[name] = rows[:200]
            result["truncated_sections"] = truncated
            return result

    def record(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        support_process_id: UUID,
        material_batch_id: UUID,
        material_batch_version: int,
        work_instance_id: UUID,
        work_instance_version: int,
        incoming_preflight_id: UUID,
        certificate_evidence_ids: Sequence[UUID],
        passport_evidence_ids: Sequence[UUID],
        quantity_evidence_link_id: UUID,
        delivered_quantity: Decimal,
        delivered_unit: str,
        manufacturer_ref: str,
        supplier_ref: str,
        custody_complete: bool,
        applicable_to_work: bool,
        decision_basis: str,
        professional_grant_id: UUID,
        professional_grant_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if (
            material_batch_version < 1
            or work_instance_version < 1
            or professional_grant_version < 1
        ):
            raise MaterialAdmissionError("material_admission_version_invalid")
        manufacturer_ref = " ".join(manufacturer_ref.split())
        supplier_ref = " ".join(supplier_ref.split())
        delivered_unit = delivered_unit.strip()
        decision_basis = " ".join(decision_basis.split())
        if (
            min(len(manufacturer_ref), len(supplier_ref)) < 2
            or not 1 <= len(delivered_unit) <= 32
            or not 3 <= len(decision_basis) <= 1000
            or not 8 <= len(idempotency_key) <= 200
            or not delivered_quantity.is_finite()
            or delivered_quantity <= 0
            or delivered_quantity.as_tuple().exponent < -6
            or delivered_quantity > Decimal("999999999999999999.999999")
        ):
            raise MaterialAdmissionError("material_admission_input_invalid")
        certificates = tuple(dict.fromkeys(certificate_evidence_ids))
        passports = tuple(dict.fromkeys(passport_evidence_ids))
        if (
            len(certificates) != len(certificate_evidence_ids)
            or len(passports) != len(passport_evidence_ids)
            or set(certificates) & set(passports)
            or quantity_evidence_link_id in set(certificates) | set(passports)
        ):
            raise MaterialAdmissionError("material_admission_evidence_identity_invalid")

        with Session(self._application_engine) as session, session.begin():
            organization_id = self._owner_scope(session, owner_identity_id, workspace_id)
            self._require_active_workspace(session, organization_id, workspace_id)
            process = self._row(
                session,
                "SELECT state FROM workspace.support_processes WHERE "
                "organization_id=:o AND workspace_id=:w AND support_process_id=:id",
                organization_id,
                workspace_id,
                support_process_id,
            )
            if process is None or process["state"] not in {
                "scope_configured",
                "executing",
                "waiting_for_evidence",
                "ready_for_deliverable",
                "waiting_for_authority",
            }:
                raise MaterialAdmissionError("material_admission_support_process_unavailable")
            batch = self._row(
                session,
                "SELECT material_class_id,material_class_version,batch_reference,admission_state "
                "FROM workspace.material_batch_versions WHERE organization_id=:o AND "
                "workspace_id=:w AND material_batch_id=:id AND version=:version",
                organization_id,
                workspace_id,
                material_batch_id,
                material_batch_version,
            )
            if batch is None or batch["admission_state"] not in {"candidate", "admitted"}:
                raise MaterialAdmissionError("material_admission_batch_unavailable")
            latest_batch_version = session.scalar(
                sa.text(
                    "SELECT max(version) FROM workspace.material_batch_versions WHERE "
                    "organization_id=:o AND workspace_id=:w AND material_batch_id=:id"
                ),
                {"o": organization_id, "w": workspace_id, "id": material_batch_id},
            )
            if latest_batch_version != material_batch_version:
                raise MaterialAdmissionError("material_admission_batch_version_stale")
            work = self._row(
                session,
                "SELECT work_state FROM workspace.work_instance_versions WHERE "
                "organization_id=:o AND workspace_id=:w AND work_instance_id=:id "
                "AND version=:version",
                organization_id,
                workspace_id,
                work_instance_id,
                work_instance_version,
            )
            if work is None or work["work_state"] not in {"planned", "ready", "in_progress"}:
                raise MaterialAdmissionError("material_admission_work_unavailable")
            latest_work_version = session.scalar(
                sa.text(
                    "SELECT max(version) FROM workspace.work_instance_versions WHERE "
                    "organization_id=:o AND workspace_id=:w AND work_instance_id=:id"
                ),
                {"o": organization_id, "w": workspace_id, "id": work_instance_id},
            )
            if latest_work_version != work_instance_version:
                raise MaterialAdmissionError("material_admission_work_version_stale")
            specified_material = session.scalar(
                sa.text(
                    "SELECT 1 FROM workspace.material_requirement_versions r WHERE "
                    "r.organization_id=:o AND r.workspace_id=:w AND "
                    "r.work_instance_id=:work AND r.work_instance_version=:work_version AND "
                    "r.material_class_id=:class AND r.material_class_version=:class_version "
                    "AND r.applicability='applicable' AND "
                    "r.status IN ('required','conditional','satisfied') AND "
                    "r.version=(SELECT max(v.version) FROM "
                    "workspace.material_requirement_versions v "
                    "WHERE v.organization_id=r.organization_id AND v.workspace_id=r.workspace_id "
                    "AND v.material_requirement_id=r.material_requirement_id) LIMIT 1"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "work": work_instance_id,
                    "work_version": work_instance_version,
                    "class": batch["material_class_id"],
                    "class_version": batch["material_class_version"],
                },
            )
            if specified_material != 1:
                raise MaterialAdmissionError("material_admission_work_material_not_specified")
            preflight = self._row(
                session,
                "SELECT batch_reference,material_batch_id,material_batch_version,result FROM "
                "workspace.support_incoming_inspection_preflights WHERE "
                "organization_id=:o AND workspace_id=:w AND preflight_id=:id",
                organization_id,
                workspace_id,
                incoming_preflight_id,
            )
            if (
                preflight is None
                or preflight["material_batch_id"] != material_batch_id
                or preflight["material_batch_version"] != material_batch_version
                or preflight["batch_reference"] != batch["batch_reference"]
            ):
                raise MaterialAdmissionError("material_admission_preflight_batch_mismatch")
            latest_preflight_id = session.scalar(
                sa.text(
                    "SELECT preflight_id FROM workspace.support_incoming_inspection_preflights "
                    "WHERE organization_id=:o AND workspace_id=:w AND "
                    "material_batch_id=:batch AND material_batch_version=:version "
                    "ORDER BY submitted_at DESC,preflight_id DESC LIMIT 1"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "batch": material_batch_id,
                    "version": material_batch_version,
                },
            )
            if latest_preflight_id != incoming_preflight_id:
                raise MaterialAdmissionError("material_admission_preflight_stale")
            preflight_result = preflight["result"]
            if (
                not isinstance(preflight_result, Mapping)
                or preflight_result.get("hold_for_use") is not True
            ):
                raise MaterialAdmissionError("material_admission_preflight_invalid")
            grant = self._row(
                session,
                "SELECT grant_version,human_identity_id,capability,"
                "professional_qualification_ref,status,"
                "effective_from,effective_until FROM workspace.support_professional_grants "
                "WHERE organization_id=:o AND workspace_id=:w AND grant_id=:id "
                "ORDER BY grant_version DESC LIMIT 1",
                organization_id,
                workspace_id,
                professional_grant_id,
            )
            now = datetime.now(UTC)
            if (
                grant is None
                or grant["grant_version"] != professional_grant_version
                or grant["human_identity_id"] != owner_identity_id
                or grant["capability"] != "support.material.admit"
                or grant["status"] != "active"
                or not str(grant["professional_qualification_ref"] or "").strip()
                or grant["effective_from"] > now
                or (grant["effective_until"] is not None and grant["effective_until"] <= now)
            ):
                raise MaterialAdmissionError("material_admission_professional_grant_unavailable")
            self._require_evidence(
                session,
                organization_id=organization_id,
                workspace_id=workspace_id,
                material_batch_id=material_batch_id,
                material_batch_version=material_batch_version,
                certificates=certificates,
                passports=passports,
                quantity_evidence_link_id=quantity_evidence_link_id,
            )

        authority = ProfessionalAuthority(
            owner_identity_id,
            professional_grant_id,
            professional_grant_version,
            "support.material.admit",
            str(grant["professional_qualification_ref"]),
        )
        evidence = MaterialBatchEvidence(
            material_batch_id,
            material_batch_version,
            f"{batch['material_class_id']}:{batch['material_class_version']}",
            str(batch["batch_reference"]),
            manufacturer_ref,
            supplier_ref,
            Quantity(delivered_quantity, delivered_unit, 6, "rounding@1.0.0"),
            certificates,
            passports,
            incoming_preflight_id,
            str(preflight_result.get("outcome") or ""),
            custody_complete,
            applicable_to_work,
            authority,
        )
        result = evaluate_material_admission(evidence)
        fingerprint = semantic_digest(
            {
                "contract": "support-material-admission@1.0.0",
                "workspace_id": workspace_id,
                "support_process_id": support_process_id,
                "material_batch_id": material_batch_id,
                "material_batch_version": material_batch_version,
                "work_instance_id": work_instance_id,
                "work_instance_version": work_instance_version,
                "incoming_preflight_id": incoming_preflight_id,
                "certificate_evidence_ids": certificates,
                "passport_evidence_ids": passports,
                "quantity_evidence_link_id": quantity_evidence_link_id,
                "delivered_quantity": str(delivered_quantity),
                "delivered_unit": delivered_unit,
                "manufacturer_ref": manufacturer_ref,
                "supplier_ref": supplier_ref,
                "custody_complete": custody_complete,
                "applicable_to_work": applicable_to_work,
                "decision_basis": decision_basis,
                "professional_grant_id": professional_grant_id,
                "professional_grant_version": professional_grant_version,
                "outcome": result.outcome.value,
                "reason_codes": result.reason_codes,
            }
        )
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
                raise MaterialAdmissionError("material_admission_writer_role_invalid")
            self._require_active_workspace(session, organization_id, workspace_id)
            current_preflight_id = session.scalar(
                sa.text(
                    "SELECT preflight_id FROM workspace.support_incoming_inspection_preflights "
                    "WHERE organization_id=:o AND workspace_id=:w AND material_batch_id=:batch "
                    "AND material_batch_version=:version ORDER BY submitted_at DESC,"
                    "preflight_id DESC LIMIT 1"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "batch": material_batch_id,
                    "version": material_batch_version,
                },
            )
            if current_preflight_id != incoming_preflight_id:
                raise MaterialAdmissionError("material_admission_preflight_stale")
            current_grant = session.scalar(
                sa.text(
                    "SELECT grant_version FROM workspace.support_professional_grants WHERE "
                    "organization_id=:o AND workspace_id=:w AND grant_id=:grant AND "
                    "human_identity_id=:owner AND capability='support.material.admit' AND "
                    "status='active' AND effective_from<=CURRENT_TIMESTAMP AND "
                    "(effective_until IS NULL OR effective_until>CURRENT_TIMESTAMP) "
                    "ORDER BY grant_version DESC LIMIT 1"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "grant": professional_grant_id,
                    "owner": owner_identity_id,
                },
            )
            if current_grant != professional_grant_version:
                raise MaterialAdmissionError("material_admission_professional_grant_unavailable")
            prior = (
                session.execute(
                    sa.text(
                        "SELECT admission_id,admission_fingerprint,outcome,reason_codes,"
                        "admitted_at "
                        "FROM workspace.support_material_admissions WHERE organization_id=:o AND "
                        "workspace_id=:w AND idempotency_key=:key"
                    ),
                    {"o": organization_id, "w": workspace_id, "key": idempotency_key},
                )
                .mappings()
                .first()
            )
            if prior is not None:
                if prior["admission_fingerprint"] != fingerprint:
                    raise MaterialAdmissionError("material_admission_idempotency_conflict")
                return self._view(prior)
            row = (
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.support_material_admissions "
                        "(organization_id,workspace_id,admission_id,support_process_id,"
                        "material_batch_id,material_batch_version,work_instance_id,"
                        "work_instance_version,outcome,certificate_evidence_ids,"
                        "passport_evidence_ids,incoming_control_id,custody_complete,reason_codes,"
                        "authority_grant_id,authority_grant_version,admission_fingerprint,"
                        "manufacturer_ref,supplier_ref,applicable_to_work,delivered_quantity,"
                        "delivered_unit,quantity_evidence_link_id,decision_basis,idempotency_key,"
                        "admitted_at) VALUES (:o,:w,:id,:process,:batch,:batch_version,:work,"
                        ":work_version,:outcome,CAST(:certificates AS uuid[]),"
                        "CAST(:passports AS uuid[]),:preflight,:custody,CAST(:reasons AS text[]),"
                        ":grant,:grant_version,:fingerprint,:manufacturer,:supplier,:applicable,"
                        ":quantity,:unit,:quantity_evidence,:basis,:key,CURRENT_TIMESTAMP) "
                        "ON CONFLICT (organization_id,workspace_id,idempotency_key) "
                        "WHERE idempotency_key IS NOT NULL DO NOTHING RETURNING "
                        "admission_id,admission_fingerprint,outcome,reason_codes,admitted_at"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "id": uuid7(),
                        "process": support_process_id,
                        "batch": material_batch_id,
                        "batch_version": material_batch_version,
                        "work": work_instance_id,
                        "work_version": work_instance_version,
                        "outcome": result.outcome.value,
                        "certificates": list(certificates),
                        "passports": list(passports),
                        "preflight": incoming_preflight_id,
                        "custody": custody_complete,
                        "reasons": list(result.reason_codes),
                        "grant": professional_grant_id,
                        "grant_version": professional_grant_version,
                        "fingerprint": fingerprint,
                        "manufacturer": manufacturer_ref,
                        "supplier": supplier_ref,
                        "applicable": applicable_to_work,
                        "quantity": delivered_quantity,
                        "unit": delivered_unit,
                        "quantity_evidence": quantity_evidence_link_id,
                        "basis": decision_basis,
                        "key": idempotency_key,
                    },
                )
                .mappings()
                .first()
            )
            if row is None:
                row = (
                    session.execute(
                        sa.text(
                            "SELECT admission_id,admission_fingerprint,outcome,reason_codes,"
                            "admitted_at FROM workspace.support_material_admissions WHERE "
                            "organization_id=:o AND workspace_id=:w AND idempotency_key=:key"
                        ),
                        {"o": organization_id, "w": workspace_id, "key": idempotency_key},
                    )
                    .mappings()
                    .one()
                )
                if row["admission_fingerprint"] != fingerprint:
                    raise MaterialAdmissionError("material_admission_idempotency_conflict")
            return self._view(row)

    @staticmethod
    def _view(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "admission_id": row["admission_id"],
            "outcome": row["outcome"],
            "reason_codes": list(row["reason_codes"]),
            "admission_fingerprint": row["admission_fingerprint"],
            "decided_at": row["admitted_at"],
        }

    @staticmethod
    def _row(
        session: Session,
        query: str,
        organization_id: UUID,
        workspace_id: UUID,
        identity_id: UUID,
        version: int | None = None,
    ) -> Mapping[str, Any] | None:
        return (
            session.execute(
                sa.text(query),
                {"o": organization_id, "w": workspace_id, "id": identity_id, "version": version},
            )
            .mappings()
            .first()
        )

    @staticmethod
    def _owner_scope(session: Session, owner_identity_id: str, workspace_id: UUID) -> UUID:
        organization_id = session.scalar(
            sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
            {"owner": owner_identity_id, "workspace": workspace_id},
        )
        if organization_id is None:
            raise MaterialAdmissionError("workspace_not_found")
        session.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(organization_id), True),
                sa.func.set_config("asd.workspace_id", str(workspace_id), True),
            )
        ).one()
        return UUID(str(organization_id))

    @staticmethod
    def _require_active_workspace(
        session: Session, organization_id: UUID, workspace_id: UUID
    ) -> None:
        active = session.scalar(
            sa.text(
                "SELECT lifecycle_state='ACTIVE' AND write_fenced=false FROM "
                "workspace.workspaces WHERE organization_id=:o AND workspace_id=:w"
            ),
            {"o": organization_id, "w": workspace_id},
        )
        if active is not True:
            raise MaterialAdmissionError("support_workspace_not_active")

    @staticmethod
    def _require_evidence(
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        material_batch_id: UUID,
        material_batch_version: int,
        certificates: tuple[UUID, ...],
        passports: tuple[UUID, ...],
        quantity_evidence_link_id: UUID,
    ) -> None:
        expected = {
            **{value: "material_certificate" for value in certificates},
            **{value: "material_passport" for value in passports},
            quantity_evidence_link_id: "delivery_quantity",
        }
        rows = (
            session.execute(
                sa.text(
                    "SELECT evidence_link_id,evidence_role,validity_status,subject_type,"
                    "subject_id,subject_version FROM workspace.evidence_links WHERE "
                    "organization_id=:o AND workspace_id=:w AND "
                    "evidence_link_id=ANY(CAST(:ids AS uuid[]))"
                ),
                {"o": organization_id, "w": workspace_id, "ids": list(expected)},
            )
            .mappings()
            .all()
        )
        if len(rows) != len(expected) or any(
            row["validity_status"] != "verified"
            or row["evidence_role"] != expected[row["evidence_link_id"]]
            or row["subject_type"] != "material_batch"
            or row["subject_id"] != material_batch_id
            or row["subject_version"] != str(material_batch_version)
            for row in rows
        ):
            raise MaterialAdmissionError("material_admission_evidence_unverified_or_unrelated")
