# ruff: noqa: E501
"""PostgreSQL application bridge for the Support production-ID vertical."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid, uuid7

from .production import (
    DocumentMembershipVersion,
    IdPackageVersion,
    MembershipRevision,
    MembershipState,
    VolumeBookVersion,
    evaluate_package_readiness,
    evolve_package_version,
    registry_manifest,
)


class SupportProductionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SupportProductionRepository:
    """Append-only package/generation commands scoped through the Product Spine owner."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def view(self, *, owner_identity_id: str, workspace_id: UUID) -> dict[str, Any]:
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            matrix = self._latest_matrix(session, organization_id, workspace_id)
            requirements = [] if matrix is None else _matrix_requirements(matrix)
            package_row = (
                session.execute(
                    sa.text(
                        "SELECT p.* FROM workspace.id_package_versions p WHERE p.organization_id=:o "
                        "AND p.workspace_id=:w AND EXISTS (SELECT 1 FROM "
                        "workspace.id_package_volume_book_versions b WHERE b.organization_id=p.organization_id "
                        "AND b.workspace_id=p.workspace_id AND b.id_package_id=p.id_package_id AND "
                        "b.id_package_version=p.version) ORDER BY p.recorded_at DESC,p.version DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            if package_row is None:
                return {
                    "workspace_id": str(workspace_id),
                    "matrix": _matrix_ref(matrix),
                    "requirements": requirements,
                    "package": None,
                    "gaps": [
                        *(("WORK_REQUIREMENT_MATRIX_UNAVAILABLE",) if matrix is None else ()),
                        "ID_PACKAGE_NOT_FORMED",
                    ],
                    "authority_layers": _authority_layers(),
                }
            package_id = UUID(str(package_row["id_package_id"]))
            package_version = int(package_row["version"])
            books = [
                dict(item)
                for item in session.execute(
                    sa.text(
                        "SELECT * FROM workspace.id_package_volume_book_versions WHERE "
                        "organization_id=:o AND workspace_id=:w AND id_package_id=:p AND "
                        "id_package_version=:v ORDER BY ordinal"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "p": package_id,
                        "v": package_version,
                    },
                ).mappings()
            ]
            memberships = [
                dict(item)
                for item in session.execute(
                    sa.text(
                        "SELECT m.*,g.job_id,g.job_state,g.typed_failure_code,g.generated_candidate_id,"
                        "g.object_reference,g.bytes_digest,g.format,g.candidate_fingerprint,"
                        "pv.print_validation_id,pv.result print_validation_result,pv.assurance_class "
                        "print_assurance_class,pv.check_codes print_check_codes,pv.blocker_codes "
                        "print_blocker_codes,tv.version template_version,tv.qualification_state "
                        "template_qualification_state,tv.official_status template_official_status,"
                        "tv.assurance_class template_assurance_class,rd.review_decision_id,rd.outcome "
                        "review_outcome,COALESCE(fd.finalized_document_id::text,CASE WHEN "
                        "m.subject_kind='finalized_document' THEN left(m.subject_ref,36) END) "
                        "finalized_document_id,fd.version finalized_document_version,"
                        "fd.qualification_level finalization_qualification_level,fd.document_digest "
                        "finalized_document_digest "
                        "FROM workspace.id_package_document_membership_versions m LEFT JOIN LATERAL ("
                        "SELECT b.template_id,b.template_version,b.job_id,j.state job_state,"
                        "j.typed_failure_code,c.generated_candidate_id,c.object_reference,c.bytes_digest,"
                        "c.format,c.semantic_fingerprint candidate_fingerprint FROM "
                        "workspace.support_generation_job_bindings b JOIN workspace.durable_jobs j ON "
                        "j.organization_id=b.organization_id AND j.workspace_id=b.workspace_id AND "
                        "j.job_id=b.job_id JOIN workspace.support_generated_document_candidates c ON "
                        "c.organization_id=b.organization_id AND c.workspace_id=b.workspace_id AND "
                        "c.generation_run_id=b.generation_run_id WHERE b.organization_id=m.organization_id "
                        "AND b.workspace_id=m.workspace_id AND b.membership_id=m.membership_id AND (("
                        "m.subject_kind='generated_document_candidate' AND "
                        "c.generated_candidate_id::text=m.subject_ref) OR (m.subject_kind='finalized_document' "
                        "AND EXISTS (SELECT 1 FROM workspace.support_finalized_document_versions selected_f "
                        "WHERE selected_f.organization_id=m.organization_id AND "
                        "selected_f.workspace_id=m.workspace_id AND "
                        "selected_f.generated_candidate_id=c.generated_candidate_id AND "
                        "selected_f.finalized_document_id::text=left(m.subject_ref,36)))) "
                        "ORDER BY c.created_at DESC LIMIT 1) g ON true LEFT JOIN "
                        "workspace.support_print_validation_results pv ON pv.organization_id=m.organization_id "
                        "AND pv.workspace_id=m.workspace_id AND pv.generated_candidate_id=g.generated_candidate_id "
                        "LEFT JOIN platform.template_versions tv ON tv.template_id=g.template_id AND "
                        "tv.version=g.template_version LEFT JOIN workspace.support_document_review_decisions rd "
                        "ON rd.organization_id=m.organization_id AND rd.workspace_id=m.workspace_id AND "
                        "rd.generated_candidate_id=g.generated_candidate_id LEFT JOIN "
                        "workspace.support_finalized_document_versions fd ON fd.organization_id=m.organization_id "
                        "AND fd.workspace_id=m.workspace_id AND fd.generated_candidate_id=g.generated_candidate_id "
                        "WHERE m.organization_id=:o AND "
                        "m.workspace_id=:w AND m.id_package_id=:p AND m.id_package_version=:v "
                        "ORDER BY m.volume_book_id,m.ordinal"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "p": package_id,
                        "v": package_version,
                    },
                ).mappings()
            ]
            registers = [
                dict(item)
                for item in session.execute(
                    sa.text(
                        "SELECT * FROM workspace.support_register_candidates WHERE organization_id=:o "
                        "AND workspace_id=:w AND id_package_id=:p AND id_package_version=:v "
                        "ORDER BY recorded_at,register_candidate_id"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "p": package_id,
                        "v": package_version,
                    },
                ).mappings()
            ]
            readiness = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.id_package_readiness_evaluations WHERE "
                        "organization_id=:o AND workspace_id=:w AND id_package_id=:p AND "
                        "id_package_version=:v ORDER BY evaluated_at DESC,evaluation_id LIMIT 1"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "p": package_id,
                        "v": package_version,
                    },
                )
                .mappings()
                .one_or_none()
            )
            fields = [
                dict(item)
                for item in session.execute(
                    sa.text(
                        "SELECT f.generation_run_id,f.field_key,f.state,f.material,f.normalized_value,"
                        "f.display_value,f.fact_id,f.fact_version,e.evidence_link_id,e.source_locator_id "
                        "FROM workspace.support_generation_field_resolutions f LEFT JOIN "
                        "workspace.support_generation_evidence_bindings e ON e.organization_id=f.organization_id "
                        "AND e.workspace_id=f.workspace_id AND e.generation_run_id=f.generation_run_id "
                        "AND e.field_key=f.field_key JOIN workspace.support_generation_job_bindings b ON "
                        "b.organization_id=f.organization_id AND b.workspace_id=f.workspace_id AND "
                        "b.generation_run_id=f.generation_run_id JOIN "
                        "workspace.id_package_document_membership_versions m ON "
                        "m.organization_id=b.organization_id AND m.workspace_id=b.workspace_id AND "
                        "m.membership_id=b.membership_id WHERE "
                        "m.id_package_id=:p AND m.id_package_version=:v ORDER BY f.generation_run_id,f.field_key"
                    ),
                    {"p": package_id, "v": package_version},
                ).mappings()
            ]
        return {
            "workspace_id": str(workspace_id),
            "matrix": _matrix_ref(matrix),
            "requirements": requirements,
            "package": _jsonable(package_row),
            "books": [_jsonable(item) for item in books],
            "memberships": [_jsonable(item) for item in memberships],
            "registers": [_jsonable(item) for item in registers],
            "readiness": _jsonable(readiness) if readiness is not None else None,
            "field_resolutions": [_jsonable(item) for item in fields],
            "gaps": sorted(
                {
                    str(code)
                    for item in memberships
                    for code in (
                        *(item.get("blocker_codes") or ()),
                        *(item.get("print_blocker_codes") or ()),
                    )
                }
            ),
            "authority_layers": _authority_layers(),
        }

    def candidate_object(
        self, *, owner_identity_id: str, workspace_id: UUID, candidate_id: UUID
    ) -> dict[str, str]:
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            row = (
                session.execute(
                    sa.text(
                        "SELECT object_reference,format,bytes_digest FROM "
                        "workspace.support_generated_document_candidates WHERE "
                        "organization_id=:o AND workspace_id=:w AND generated_candidate_id=:candidate"
                    ),
                    {"o": organization_id, "w": workspace_id, "candidate": candidate_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise SupportProductionError("generated_document_candidate_not_found")
        return {
            "object_key": str(row["object_reference"]),
            "format": str(row["format"]),
            "content_digest": str(row["bytes_digest"]),
        }

    def form_package(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        work_package_id: UUID,
    ) -> dict[str, Any]:
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        now = datetime.now(UTC)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            matrix = self._latest_matrix(session, organization_id, workspace_id)
            if matrix is None:
                raise SupportProductionError("work_requirement_matrix_unavailable")
            matrix_doc = dict(matrix["matrix"])
            row = next(
                (
                    item
                    for item in matrix_doc.get("rows", [])
                    if UUID(str(item["work_package_id"])) == work_package_id
                ),
                None,
            )
            if row is None:
                raise SupportProductionError("work_package_not_in_latest_matrix")
            existing = session.scalar(
                sa.text(
                    "SELECT m.id_package_id FROM workspace.id_package_document_membership_versions m "
                    "JOIN workspace.id_package_versions p ON p.organization_id=m.organization_id AND "
                    "p.workspace_id=m.workspace_id AND p.id_package_id=m.id_package_id AND "
                    "p.version=m.id_package_version WHERE m.organization_id=:o AND m.workspace_id=:w "
                    "AND m.matrix_id=:matrix AND m.matrix_version=:version AND p.scope_subject_id=:work "
                    "ORDER BY p.version DESC LIMIT 1"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "matrix": matrix["matrix_id"],
                    "version": matrix["version"],
                    "work": work_package_id,
                },
            )
            if existing is not None:
                return self.view(owner_identity_id=owner_identity_id, workspace_id=workspace_id)
            package_id = deterministic_uuid(f"support-id-package:{workspace_id}:{work_package_id}")
            package_version = int(
                session.scalar(
                    sa.text(
                        "SELECT coalesce(max(version),0)+1 FROM workspace.id_package_versions "
                        "WHERE organization_id=:o AND workspace_id=:w AND id_package_id=:p"
                    ),
                    {"o": organization_id, "w": workspace_id, "p": package_id},
                )
                or 1
            )
            book_id = deterministic_uuid(f"support-id-book:{package_id}:main")
            register_membership_id = deterministic_uuid(
                f"support-id-membership:{package_id}:register"
            )
            rule_set_id = (
                UUID(str(matrix_doc["rule_set_version_id"]))
                if matrix_doc.get("rule_set_version_id")
                else None
            )
            memberships = [
                DocumentMembershipVersion(
                    register_membership_id,
                    package_version,
                    "register",
                    1,
                    1,
                    "package_assembly",
                    None,
                    "package_register",
                    f"package-register:{package_id}:v{package_version}",
                    MembershipState.GENERATED_CANDIDATE,
                    ("package.register-policy@1.0.0",),
                    ("REGISTER_TEMPLATE_AUTHORITY_UNRESOLVED",),
                )
            ]
            documents = sorted(
                row.get("documents", []),
                key=lambda item: (
                    str(item.get("document_type", "")),
                    str(item["document_requirement_id"]),
                ),
            )
            for ordinal, document in enumerate(documents, start=2):
                requirement_id = UUID(str(document["document_requirement_id"]))
                authority = str(document.get("authority_status", "normative_gap"))
                blockers = _authority_blockers(authority, tuple(row.get("normative_gaps", [])))
                state = MembershipState.BLOCKED if blockers else MembershipState.MISSING
                role = str(document.get("document_type") or "unresolved_document_type")
                memberships.append(
                    DocumentMembershipVersion(
                        deterministic_uuid(f"support-id-membership:{package_id}:{requirement_id}"),
                        package_version,
                        role,
                        ordinal,
                        int(document.get("minimum_copies", 1)),
                        "work_acceptance",
                        (requirement_id, 1),
                        "required_document",
                        f"required-document:{requirement_id}:v1",
                        state,
                        tuple(
                            document.get("basis_refs")
                            or (f"matrix:{matrix['matrix_id']}:v{matrix['version']}",)
                        ),
                        blockers,
                    )
                )
            book = VolumeBookVersion(
                book_id,
                package_version,
                "Исполнительная документация по виду работ",
                1,
                "package",
                1,
                tuple(memberships),
            )
            governance = () if rule_set_id is not None else ("RULE_SET_VERSION_UNRESOLVED",)
            package = IdPackageVersion(
                package_id,
                package_version,
                (work_package_id, 1),
                (UUID(str(matrix["matrix_id"])), int(matrix["version"])),
                rule_set_id,
                "support.executive-document-package",
                (book,),
                governance,
            )
            readiness = evaluate_package_readiness(package)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.id_package_versions VALUES "
                    "(:o,:w,:p,:v,'work',:work,:status,:required,:covered,:missing,:indeterminate,"
                    ":fingerprint,:ruleset,:now)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "p": package_id,
                    "v": package_version,
                    "work": work_package_id,
                    "status": "incomplete",
                    "required": readiness.required,
                    "covered": readiness.covered + readiness.finalized,
                    "missing": readiness.missing,
                    "indeterminate": readiness.indeterminate + readiness.blocked,
                    "fingerprint": package.fingerprint,
                    "ruleset": rule_set_id,
                    "now": now,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.id_package_volume_book_versions VALUES "
                    "(:o,:w,:p,:pv,:book,:v,:ordinal,:title,:level,:copies,:fingerprint,:now)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "p": package_id,
                    "pv": package_version,
                    "book": book_id,
                    "v": book.version,
                    "ordinal": book.ordinal,
                    "title": book.title,
                    "level": book.register_level,
                    "copies": book.required_copy_count,
                    "fingerprint": book.fingerprint,
                    "now": now,
                },
            )
            for membership in memberships:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.id_package_document_membership_versions VALUES "
                        "(:o,:w,:membership,:mv,:p,:pv,:book,:bv,:matrix,:matrix_version,"
                        ":requirement,:requirement_version,:role,:ordinal,:copies,:stage,:subject_kind,"
                        ":subject_ref,:state,:evidence,:blockers,:fingerprint,:now)"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "membership": membership.membership_id,
                        "mv": membership.version,
                        "p": package_id,
                        "pv": package_version,
                        "book": book_id,
                        "bv": book.version,
                        "matrix": matrix["matrix_id"],
                        "matrix_version": matrix["version"],
                        "requirement": membership.requirement_ref[0]
                        if membership.requirement_ref
                        else None,
                        "requirement_version": membership.requirement_ref[1]
                        if membership.requirement_ref
                        else None,
                        "role": membership.role,
                        "ordinal": membership.ordinal,
                        "copies": membership.required_copy_count,
                        "stage": membership.stage,
                        "subject_kind": membership.subject_kind,
                        "subject_ref": membership.subject_ref,
                        "state": membership.state,
                        "evidence": list(membership.evidence_refs),
                        "blockers": list(membership.blocker_codes),
                        "fingerprint": membership.fingerprint,
                        "now": now,
                    },
                )
            manifest = registry_manifest(package, book)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_register_candidates VALUES "
                    "(:o,:w,:register,1,:p,:pv,:book,:bv,:membership,:mv,CAST(:manifest AS jsonb),"
                    ":fingerprint,'structured_candidate',ARRAY['REGISTER_TEMPLATE_AUTHORITY_UNRESOLVED'],:now)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "register": deterministic_uuid(
                        f"support-register:{package_id}:v{package_version}"
                    ),
                    "p": package_id,
                    "pv": package_version,
                    "book": book_id,
                    "bv": book.version,
                    "membership": register_membership_id,
                    "mv": package_version,
                    "manifest": json.dumps(
                        manifest, sort_keys=True, separators=(",", ":"), default=str
                    ),
                    "fingerprint": manifest["fingerprint"],
                    "now": now,
                },
            )
            self._insert_readiness(session, organization_id, workspace_id, readiness, now)
        return self.view(owner_identity_id=owner_identity_id, workspace_id=workspace_id)

    def start_generation(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        membership_id: UUID,
        idempotency_key: str,
        correlation_id: UUID,
    ) -> dict[str, Any]:
        if len(idempotency_key) < 8:
            raise SupportProductionError("generation_idempotency_key_invalid")
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        now = datetime.now(UTC)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            membership = (
                session.execute(
                    sa.text(
                        "SELECT m.*,p.rule_set_version_id FROM "
                        "workspace.id_package_document_membership_versions m JOIN "
                        "workspace.id_package_versions p ON p.organization_id=m.organization_id AND "
                        "p.workspace_id=m.workspace_id AND p.id_package_id=m.id_package_id AND "
                        "p.version=m.id_package_version WHERE m.organization_id=:o AND m.workspace_id=:w "
                        "AND m.membership_id=:membership ORDER BY m.version DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id, "membership": membership_id},
                )
                .mappings()
                .one_or_none()
            )
            if membership is None:
                raise SupportProductionError("package_membership_not_found")
            if membership["role"] == "register":
                raise SupportProductionError("register_generation_uses_package_register_command")
            if membership["rule_set_version_id"] is None:
                raise SupportProductionError("generation_rule_set_version_unresolved")
            requirement_id = membership["document_requirement_id"]
            catalog = (
                session.execute(
                    sa.text(
                        "SELECT t.required_document_type_id,t.document_type_key,v.version document_type_version,"
                        "tv.format format_family,v.purpose,m.template_id,m.template_version,tv.field_schema_id,"
                        "tv.field_schema_version,tv.renderer_profile_version,tv.validator_profile_version,"
                        "tv.binding_profile_version,tv.qualification_state,tv.assurance_class,tv.official_status,"
                        "a.object_key,a.content_digest template_digest,a.byte_length FROM "
                        "platform.required_document_types t JOIN platform.required_document_type_versions v "
                        "ON v.required_document_type_id=t.required_document_type_id JOIN "
                        "platform.required_document_type_templates m ON m.required_document_type_id=v.required_document_type_id "
                        "AND m.required_document_type_version=v.version JOIN platform.template_versions tv ON "
                        "tv.template_id=m.template_id AND tv.version=m.template_version JOIN "
                        "platform.template_artifacts a ON a.template_id=tv.template_id AND "
                        "a.template_version=tv.version WHERE t.document_type_key=:key AND "
                        "v.status='active' AND m.applicability_status IN ('candidate','qualified','active') "
                        "AND a.validation_status IN ('candidate','qualified') ORDER BY "
                        "CASE m.applicability_status WHEN 'active' THEN 0 WHEN 'qualified' THEN 1 ELSE 2 END,"
                        "a.artifact_version DESC LIMIT 1"
                    ),
                    {"key": membership["role"]},
                )
                .mappings()
                .one_or_none()
            )
            if catalog is None:
                raise SupportProductionError("qualified_template_mapping_unavailable")
            format_family = str(catalog["format_family"])
            if format_family not in {"DOCX", "PDF_OVERLAY"}:
                raise SupportProductionError("template_renderer_format_not_supported")
            bindings: list[dict[str, Any]] = []
            font_asset: Any = None
            if format_family == "PDF_OVERLAY":
                qualification = session.scalar(
                    sa.text(
                        "SELECT count(*) FROM platform.template_qualification_receipts WHERE "
                        "template_id=:template AND template_version=:version AND result='qualified'"
                    ),
                    {"template": catalog["template_id"], "version": catalog["template_version"]},
                )
                if not qualification:
                    raise SupportProductionError("template_qualification_receipt_unavailable")
                bindings = [
                    {
                        "field_key": str(item["field_key"]),
                        "page_index": int(item["page_index"]),
                        "x": float(item["region"][0]),
                        "y": float(item["region"][1]),
                        "width": float(item["region"][2]),
                        "height": float(item["region"][3]),
                        "font_size": float(item["typography"]["font_size"]),
                        "line_height": float(item["typography"]["line_height"]),
                        "alignment": str(item["typography"].get("alignment", "left")),
                        "material": bool(item["material"]),
                        "required": bool(item["required"]),
                    }
                    for item in session.execute(
                        sa.text(
                            "SELECT b.*,f.material,f.required FROM "
                            "platform.template_field_binding_versions b JOIN platform.template_versions t "
                            "ON t.template_id=b.template_id AND t.version=b.template_version JOIN "
                            "platform.template_field_definitions f ON f.field_schema_id=t.field_schema_id "
                            "AND f.field_schema_version=t.field_schema_version AND f.field_key=b.field_key "
                            "WHERE b.template_id=:template AND b.template_version=:version "
                            "ORDER BY b.page_index,b.field_key"
                        ),
                        {
                            "template": catalog["template_id"],
                            "version": catalog["template_version"],
                        },
                    ).mappings()
                ]
                font_asset = (
                    session.execute(
                        sa.text(
                            "SELECT object_key,content_digest FROM platform.template_renderer_assets WHERE "
                            "template_id=:template AND template_version=:version AND asset_role='font' "
                            "AND validation_status='qualified' ORDER BY asset_version DESC LIMIT 1"
                        ),
                        {
                            "template": catalog["template_id"],
                            "version": catalog["template_version"],
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
                if not bindings or font_asset is None:
                    raise SupportProductionError("template_pdf_renderer_assets_unavailable")
            requirement_trace = (
                session.execute(
                    sa.text(
                        "SELECT rule_trace_id FROM workspace.document_requirement_versions WHERE "
                        "organization_id=:o AND workspace_id=:w AND document_requirement_id=:requirement "
                        "AND version=:version"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "requirement": requirement_id,
                        "version": membership["document_requirement_version"],
                    },
                )
                .mappings()
                .one_or_none()
            )
            if requirement_trace is None:
                raise SupportProductionError("document_requirement_rule_trace_unavailable")
            process = (
                session.execute(
                    sa.text(
                        "SELECT p.support_process_id,p.mode_execution_id,s.policy_versions FROM "
                        "workspace.support_processes p JOIN workspace.support_scope_versions s ON "
                        "s.organization_id=p.organization_id AND s.workspace_id=p.workspace_id AND "
                        "s.support_process_id=p.support_process_id WHERE p.organization_id=:o AND "
                        "p.workspace_id=:w ORDER BY p.updated_at DESC,s.scope_version DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            if process is None:
                raise SupportProductionError("support_process_not_configured")
            grant = (
                session.execute(
                    sa.text(
                        "SELECT grant_id,grant_version FROM workspace.support_professional_grants "
                        "WHERE organization_id=:o AND workspace_id=:w AND human_identity_id=:owner "
                        "AND capability='support.document.generate' AND status='active' AND "
                        "effective_from<=:now AND (effective_until IS NULL OR effective_until>:now) "
                        "ORDER BY grant_version DESC LIMIT 1"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "owner": owner_identity_id,
                        "now": now,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if grant is None:
                raise SupportProductionError("generation_authority_grant_unavailable")
            field_definitions = list(
                session.execute(
                    sa.text(
                        "SELECT * FROM platform.template_field_definitions WHERE field_schema_id=:schema "
                        "AND field_schema_version=:version ORDER BY display_order"
                    ),
                    {
                        "schema": catalog["field_schema_id"],
                        "version": catalog["field_schema_version"],
                    },
                ).mappings()
            )
            if not field_definitions:
                raise SupportProductionError("template_field_schema_empty")
            resolutions = [
                self._resolve_field(session, organization_id, workspace_id, definition)
                for definition in field_definitions
            ]
            blockers = [
                item["field_key"]
                for item in resolutions
                if item["material"] and item["state"] not in {"confirmed", "not_applicable"}
            ]
            if blockers:
                raise SupportProductionError(
                    "generation_material_fields_unresolved:" + ",".join(sorted(blockers))
                )
            semantic_input = {
                "membership_id": str(membership_id),
                "membership_version": membership["version"],
                "template_id": str(catalog["template_id"]),
                "template_version": catalog["template_version"],
                "template_digest": catalog["template_digest"],
                "fields": resolutions,
                "format": format_family,
                "bindings": bindings,
                "rule_set_version_id": str(membership["rule_set_version_id"]),
            }
            input_digest = semantic_digest(semantic_input)
            existing = (
                session.execute(
                    sa.text(
                        "SELECT job_id,input_digest,state FROM workspace.durable_jobs WHERE "
                        "organization_id=:o AND workspace_id=:w AND job_kind='ID_DOCUMENT_GENERATION' "
                        "AND idempotency_key=:key"
                    ),
                    {"o": organization_id, "w": workspace_id, "key": idempotency_key},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if str(existing["input_digest"]) != input_digest:
                    raise SupportProductionError("generation_idempotency_conflict")
                return {
                    "job_id": str(existing["job_id"]),
                    "state": str(existing["state"]),
                    "duplicate": True,
                }
            request_id = deterministic_uuid(
                f"support-generation-request:{workspace_id}:{idempotency_key}"
            )
            run_id = deterministic_uuid(f"support-generation-run:{input_digest}")
            plan_id = deterministic_uuid(f"support-binding-plan:{input_digest}")
            job_id = uuid7()
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_generation_requests VALUES "
                    "(:o,:w,:request,:process,:mode,:type,:type_version,:format,'id_package_candidate',"
                    ":grant,:grant_version,:ruleset,:policies,:key,:digest,:now)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "request": request_id,
                    "process": process["support_process_id"],
                    "mode": process["mode_execution_id"],
                    "type": catalog["required_document_type_id"],
                    "type_version": catalog["document_type_version"],
                    "format": format_family,
                    "grant": grant["grant_id"],
                    "grant_version": grant["grant_version"],
                    "ruleset": membership["rule_set_version_id"],
                    "policies": list(process["policy_versions"]),
                    "key": idempotency_key,
                    "digest": input_digest,
                    "now": now,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_binding_plan_versions VALUES "
                    "(:o,:w,:plan,1,:request,:template,:template_version,:schema,:schema_version,"
                    ":binding,:target,:trace,:digest,:now)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "plan": plan_id,
                    "request": request_id,
                    "template": catalog["template_id"],
                    "template_version": catalog["template_version"],
                    "schema": catalog["field_schema_id"],
                    "schema_version": catalog["field_schema_version"],
                    "binding": catalog["binding_profile_version"],
                    "target": semantic_digest([item["field_key"] for item in resolutions]),
                    "trace": requirement_trace["rule_trace_id"],
                    "digest": semantic_digest(
                        {"plan": str(plan_id), "semantic_input": semantic_input}
                    ),
                    "now": now,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_generation_runs VALUES "
                    "(:o,:w,:run,:request,:plan,1,:renderer,:validator,:input,true,'planned',ARRAY[]::text[],:now,NULL)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "run": run_id,
                    "request": request_id,
                    "plan": plan_id,
                    "renderer": catalog["renderer_profile_version"],
                    "validator": catalog["validator_profile_version"],
                    "input": input_digest,
                    "now": now,
                },
            )
            for item in resolutions:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.support_generation_field_resolutions VALUES "
                        "(:o,:w,:run,:key,:state,:material,:normalized,:display,:fact,:version,:fingerprint)"
                    ),
                    {"o": organization_id, "w": workspace_id, "run": run_id, **item},
                )
                if item["state"] == "confirmed":
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.support_generation_evidence_bindings VALUES "
                            "(:o,:w,:binding,:run,:key,:fact,:version,:evidence,:locator,:decision,:trace,:digest)"
                        ),
                        {
                            "o": organization_id,
                            "w": workspace_id,
                            "binding": deterministic_uuid(
                                f"support-field-binding:{run_id}:{item['field_key']}"
                            ),
                            "run": run_id,
                            "key": item["field_key"],
                            "fact": item["fact"],
                            "version": item["version"],
                            "evidence": item["evidence"],
                            "locator": item["locator"],
                            "decision": item["decision"],
                            "trace": requirement_trace["rule_trace_id"],
                            "digest": semantic_digest(
                                {
                                    "run": str(run_id),
                                    "field": item["field_key"],
                                    "fact": str(item["fact"]),
                                    "version": item["version"],
                                }
                            ),
                        },
                    )
            manifest = {
                "generation_run_id": str(run_id),
                "membership_id": str(membership_id),
                "membership_version": int(membership["version"]),
                "template_id": str(catalog["template_id"]),
                "template_version": str(catalog["template_version"]),
                "template_object_key": str(catalog["object_key"]),
                "template_digest": str(catalog["template_digest"]),
                "format": format_family,
                "renderer_profile_version": str(catalog["renderer_profile_version"]),
                "validator_profile_version": str(catalog["validator_profile_version"]),
                "bindings": bindings,
                "semantic_input": semantic_input,
            }
            if font_asset is not None:
                manifest["font_object_key"] = str(font_asset["object_key"])
                manifest["font_digest"] = str(font_asset["content_digest"])
            session.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs (organization_id,workspace_id,job_id,"
                    "subject_document_id,job_kind,input_manifest,input_digest,idempotency_key,state,priority,"
                    "max_attempts,retry_policy_version,provenance,correlation_id,created_by_identity_id) VALUES "
                    "(:o,:w,:job,NULL,'ID_DOCUMENT_GENERATION',CAST(:manifest AS jsonb),:digest,:key,"
                    "'queued',200,3,'support-generation-retry@1.0.0',CAST(:provenance AS jsonb),:correlation,:owner)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "job": job_id,
                    "manifest": json.dumps(
                        manifest, sort_keys=True, separators=(",", ":"), default=str
                    ),
                    "digest": input_digest,
                    "key": idempotency_key,
                    "provenance": json.dumps(
                        {
                            "contract": "support.production-id@1.0.0",
                            "membership_id": str(membership_id),
                        },
                        sort_keys=True,
                    ),
                    "correlation": correlation_id,
                    "owner": owner_identity_id,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_generation_job_bindings VALUES "
                    "(:o,:w,:job,:run,:membership,:mv,:template,:tv,:digest,:now)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "job": job_id,
                    "run": run_id,
                    "membership": membership_id,
                    "mv": membership["version"],
                    "template": catalog["template_id"],
                    "tv": catalog["template_version"],
                    "digest": input_digest,
                    "now": now,
                },
            )
        return {
            "job_id": str(job_id),
            "generation_run_id": str(run_id),
            "state": "queued",
            "duplicate": False,
        }

    def review_candidate(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        candidate_id: UUID,
        outcome: str,
    ) -> dict[str, Any]:
        if outcome not in {"approved", "rejected", "needs_correction"}:
            raise SupportProductionError("document_review_outcome_invalid")
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        now = datetime.now(UTC)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            candidate = (
                session.execute(
                    sa.text(
                        "SELECT c.generated_candidate_id,c.bytes_digest,p.print_validation_id,p.result,"
                        "p.assurance_class FROM workspace.support_generated_document_candidates c JOIN "
                        "workspace.support_print_validation_results p ON p.organization_id=c.organization_id "
                        "AND p.workspace_id=c.workspace_id AND p.generated_candidate_id=c.generated_candidate_id "
                        "WHERE c.organization_id=:o AND c.workspace_id=:w AND c.generated_candidate_id=:candidate"
                    ),
                    {"o": organization_id, "w": workspace_id, "candidate": candidate_id},
                )
                .mappings()
                .one_or_none()
            )
            if candidate is None:
                raise SupportProductionError("generated_document_candidate_not_found")
            if outcome == "approved" and (
                candidate["result"] != "print_ready" or candidate["assurance_class"] != "production"
            ):
                raise SupportProductionError("candidate_not_production_print_ready")
            grant = self._active_grant(
                session,
                organization_id,
                workspace_id,
                owner_identity_id,
                "support.document.review",
                now,
            )
            review_id = deterministic_uuid(
                f"support-document-review:{candidate_id}:{candidate['bytes_digest']}:{owner_identity_id}:{outcome}"
            )
            decision_digest = semantic_digest(
                {
                    "review_id": str(review_id),
                    "candidate_id": str(candidate_id),
                    "candidate_digest": str(candidate["bytes_digest"]),
                    "print_validation_id": str(candidate["print_validation_id"]),
                    "reviewer": owner_identity_id,
                    "outcome": outcome,
                    "grant": [str(grant["grant_id"]), int(grant["grant_version"])],
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_document_review_decisions VALUES "
                    "(:o,:w,:review,:candidate,:validation,:owner,:grant,:grant_version,:outcome,"
                    ":candidate_digest,:decision_digest,:now) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "review": review_id,
                    "candidate": candidate_id,
                    "validation": candidate["print_validation_id"],
                    "owner": owner_identity_id,
                    "grant": grant["grant_id"],
                    "grant_version": grant["grant_version"],
                    "outcome": outcome,
                    "candidate_digest": candidate["bytes_digest"],
                    "decision_digest": decision_digest,
                    "now": now,
                },
            )
        return self.view(owner_identity_id=owner_identity_id, workspace_id=workspace_id)

    def finalize_candidate(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        candidate_id: UUID,
    ) -> dict[str, Any]:
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        now = datetime.now(UTC)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            candidate = (
                session.execute(
                    sa.text(
                        "SELECT c.*,p.print_validation_id,p.result,p.assurance_class,r.review_decision_id,"
                        "r.human_identity_id reviewer,r.outcome,b.template_id,b.template_version,"
                        "tv.qualification_state,tv.assurance_class template_assurance,tv.official_status "
                        "FROM workspace.support_generated_document_candidates c JOIN "
                        "workspace.support_print_validation_results p ON p.organization_id=c.organization_id "
                        "AND p.workspace_id=c.workspace_id AND p.generated_candidate_id=c.generated_candidate_id "
                        "JOIN workspace.support_document_review_decisions r ON r.organization_id=c.organization_id "
                        "AND r.workspace_id=c.workspace_id AND r.generated_candidate_id=c.generated_candidate_id "
                        "JOIN workspace.support_generation_job_bindings b ON b.organization_id=c.organization_id "
                        "AND b.workspace_id=c.workspace_id AND b.generation_run_id=c.generation_run_id "
                        "JOIN platform.template_versions tv ON tv.template_id=b.template_id AND "
                        "tv.version=b.template_version WHERE c.organization_id=:o AND c.workspace_id=:w "
                        "AND c.generated_candidate_id=:candidate AND r.outcome='approved' "
                        "ORDER BY r.decided_at DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id, "candidate": candidate_id},
                )
                .mappings()
                .one_or_none()
            )
            if candidate is None:
                raise SupportProductionError("approved_document_review_unavailable")
            if candidate["result"] != "print_ready" or candidate["assurance_class"] != "production":
                raise SupportProductionError("candidate_not_production_print_ready")
            if not (
                candidate["qualification_state"] == "active"
                and candidate["template_assurance"] == "production"
                and candidate["official_status"] == "verified"
            ):
                raise SupportProductionError("template_not_production_qualified")
            grant = self._active_grant(
                session,
                organization_id,
                workspace_id,
                owner_identity_id,
                "support.deliverable.finalize",
                now,
            )
            if str(candidate["reviewer"]) == owner_identity_id:
                raise SupportProductionError("independent_finalizer_required")
            finalized_id = deterministic_uuid(
                f"support-finalized-document:{candidate_id}:{candidate['bytes_digest']}"
            )
            existing = session.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.support_finalized_document_versions WHERE "
                    "organization_id=:o AND workspace_id=:w AND finalized_document_id=:finalized"
                ),
                {"o": organization_id, "w": workspace_id, "finalized": finalized_id},
            )
            if not existing:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.support_finalized_document_versions VALUES "
                        "(:o,:w,:finalized,1,:candidate,:validation,:review,:owner,:grant,:grant_version,"
                        "'production_print_ready',:digest,:now)"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "finalized": finalized_id,
                        "candidate": candidate_id,
                        "validation": candidate["print_validation_id"],
                        "review": candidate["review_decision_id"],
                        "owner": owner_identity_id,
                        "grant": grant["grant_id"],
                        "grant_version": grant["grant_version"],
                        "digest": candidate["bytes_digest"],
                        "now": now,
                    },
                )
                self._append_finalized_package_version(
                    session,
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                    candidate_id=candidate_id,
                    finalized_id=finalized_id,
                    document_digest=str(candidate["bytes_digest"]),
                    review_id=UUID(str(candidate["review_decision_id"])),
                    now=now,
                )
        return self.view(owner_identity_id=owner_identity_id, workspace_id=workspace_id)

    def finalized_object(
        self, *, owner_identity_id: str, workspace_id: UUID, finalized_id: UUID
    ) -> dict[str, str]:
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            row = (
                session.execute(
                    sa.text(
                        "SELECT c.object_reference,c.format,c.bytes_digest FROM "
                        "workspace.support_finalized_document_versions f JOIN "
                        "workspace.support_generated_document_candidates c ON c.organization_id=f.organization_id "
                        "AND c.workspace_id=f.workspace_id AND c.generated_candidate_id=f.generated_candidate_id "
                        "WHERE f.organization_id=:o AND f.workspace_id=:w AND f.finalized_document_id=:finalized"
                    ),
                    {"o": organization_id, "w": workspace_id, "finalized": finalized_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise SupportProductionError("finalized_document_not_found")
        return {
            "object_key": str(row["object_reference"]),
            "format": str(row["format"]),
            "content_digest": str(row["bytes_digest"]),
        }

    def record_package_backup_manifest(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any]:
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        now = datetime.now(UTC)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            snapshot = self._package_snapshot(session, organization_id, workspace_id)
            if snapshot["latest_package"] is None:
                raise SupportProductionError("id_package_not_formed")
            fingerprint = semantic_digest(snapshot)
            latest = snapshot["latest_package"]
            backup_id = deterministic_uuid(
                f"support-package-backup:{workspace_id}:{latest['id_package_id']}:"
                f"{latest['version']}:{fingerprint}"
            )
            object_digests = sorted(
                {
                    str(item["bytes_digest"])
                    for item in snapshot["generated_candidates"]
                    if item.get("bytes_digest")
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_package_backup_manifests VALUES "
                    "(:o,:w,:backup,1,:p,:pv,CAST(:manifest AS jsonb),:fingerprint,:objects,"
                    "'verified',ARRAY[]::text[],:now) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "backup": backup_id,
                    "p": latest["id_package_id"],
                    "pv": latest["version"],
                    "manifest": json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
                    "fingerprint": fingerprint,
                    "objects": object_digests,
                    "now": now,
                },
            )
        return {"backup_manifest_id": str(backup_id), "fingerprint": fingerprint, **snapshot}

    @staticmethod
    def _active_grant(
        session: Session,
        organization_id: UUID,
        workspace_id: UUID,
        identity_id: str,
        capability: str,
        at: datetime,
    ) -> Any:
        grant = (
            session.execute(
                sa.text(
                    "SELECT grant_id,grant_version FROM workspace.support_professional_grants WHERE "
                    "organization_id=:o AND workspace_id=:w AND human_identity_id=:identity "
                    "AND capability=:capability AND status='active' AND effective_from<=:at AND "
                    "(effective_until IS NULL OR effective_until>:at) ORDER BY grant_version DESC LIMIT 1"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "identity": identity_id,
                    "capability": capability,
                    "at": at,
                },
            )
            .mappings()
            .one_or_none()
        )
        if grant is None:
            raise SupportProductionError(f"professional_grant_unavailable:{capability}")
        return grant

    def _append_finalized_package_version(
        self,
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        candidate_id: UUID,
        finalized_id: UUID,
        document_digest: str,
        review_id: UUID,
        now: datetime,
    ) -> None:
        membership = (
            session.execute(
                sa.text(
                    "SELECT * FROM workspace.id_package_document_membership_versions WHERE "
                    "organization_id=:o AND workspace_id=:w AND subject_kind='generated_document_candidate' "
                    "AND subject_ref=:candidate ORDER BY id_package_version DESC,version DESC LIMIT 1"
                ),
                {"o": organization_id, "w": workspace_id, "candidate": str(candidate_id)},
            )
            .mappings()
            .one_or_none()
        )
        if membership is None:
            raise SupportProductionError("candidate_package_membership_unavailable")
        latest = session.scalar(
            sa.text(
                "SELECT max(version) FROM workspace.id_package_versions WHERE organization_id=:o "
                "AND workspace_id=:w AND id_package_id=:p"
            ),
            {"o": organization_id, "w": workspace_id, "p": membership["id_package_id"]},
        )
        if int(latest or 0) != int(membership["id_package_version"]):
            raise SupportProductionError("candidate_package_version_superseded")
        package, package_row = self._load_package(
            session,
            organization_id,
            workspace_id,
            UUID(str(membership["id_package_id"])),
            int(membership["id_package_version"]),
        )
        evolved = evolve_package_version(
            package,
            revisions=(
                MembershipRevision(
                    UUID(str(membership["membership_id"])),
                    "finalized_document",
                    f"{finalized_id}:v1",
                    MembershipState.FINALIZED,
                    evidence_refs=(document_digest, f"review-decision:{review_id}"),
                    blocker_codes=(),
                ),
            ),
        )
        self._persist_evolved_package(
            session,
            organization_id=organization_id,
            workspace_id=workspace_id,
            prior_row=package_row,
            package=evolved,
            now=now,
        )

    @staticmethod
    def _load_package(
        session: Session,
        organization_id: UUID,
        workspace_id: UUID,
        package_id: UUID,
        version: int,
    ) -> tuple[IdPackageVersion, Any]:
        package_row = (
            session.execute(
                sa.text(
                    "SELECT * FROM workspace.id_package_versions WHERE organization_id=:o AND "
                    "workspace_id=:w AND id_package_id=:p AND version=:v"
                ),
                {"o": organization_id, "w": workspace_id, "p": package_id, "v": version},
            )
            .mappings()
            .one()
        )
        package_basis = (
            session.execute(
                sa.text(
                    "SELECT matrix_id,matrix_version FROM "
                    "workspace.id_package_document_membership_versions WHERE "
                    "organization_id=:o AND workspace_id=:w AND id_package_id=:p AND "
                    "id_package_version=:v ORDER BY volume_book_id,ordinal LIMIT 1"
                ),
                {"o": organization_id, "w": workspace_id, "p": package_id, "v": version},
            )
            .mappings()
            .one()
        )
        books: list[VolumeBookVersion] = []
        for book in session.execute(
            sa.text(
                "SELECT * FROM workspace.id_package_volume_book_versions WHERE organization_id=:o "
                "AND workspace_id=:w AND id_package_id=:p AND id_package_version=:v ORDER BY ordinal"
            ),
            {"o": organization_id, "w": workspace_id, "p": package_id, "v": version},
        ).mappings():
            members = tuple(
                DocumentMembershipVersion(
                    UUID(str(item["membership_id"])),
                    int(item["version"]),
                    str(item["role"]),
                    int(item["ordinal"]),
                    int(item["required_copy_count"]),
                    str(item["stage"]),
                    (
                        (
                            UUID(str(item["document_requirement_id"])),
                            int(item["document_requirement_version"]),
                        )
                        if item["document_requirement_id"] is not None
                        else None
                    ),
                    str(item["subject_kind"]),
                    str(item["subject_ref"]),
                    MembershipState(str(item["state"])),
                    tuple(str(value) for value in item["evidence_refs"]),
                    tuple(str(value) for value in item["blocker_codes"]),
                )
                for item in session.execute(
                    sa.text(
                        "SELECT * FROM workspace.id_package_document_membership_versions WHERE "
                        "organization_id=:o AND workspace_id=:w AND id_package_id=:p AND "
                        "id_package_version=:v AND volume_book_id=:book ORDER BY ordinal"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "p": package_id,
                        "v": version,
                        "book": book["volume_book_id"],
                    },
                ).mappings()
            )
            books.append(
                VolumeBookVersion(
                    UUID(str(book["volume_book_id"])),
                    int(book["version"]),
                    str(book["title"]),
                    int(book["ordinal"]),
                    str(book["register_level"]),
                    int(book["required_copy_count"]),
                    members,
                )
            )
        governance = (
            ()
            if package_row["rule_set_version_id"] is not None
            else ("RULE_SET_VERSION_UNRESOLVED",)
        )
        package = IdPackageVersion(
            package_id,
            version,
            (UUID(str(package_row["scope_subject_id"])), 1),
            (
                UUID(str(package_basis["matrix_id"])),
                int(package_basis["matrix_version"]),
            ),
            UUID(str(package_row["rule_set_version_id"]))
            if package_row["rule_set_version_id"]
            else None,
            "support.executive-document-package",
            tuple(books),
            governance,
        )
        return package, package_row

    def _persist_evolved_package(
        self,
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        prior_row: Any,
        package: IdPackageVersion,
        now: datetime,
    ) -> None:
        readiness = evaluate_package_readiness(package)
        session.execute(
            sa.text(
                "INSERT INTO workspace.id_package_versions VALUES "
                "(:o,:w,:p,:v,:scope,:subject,:status,:required,:covered,:missing,:indeterminate,"
                ":fingerprint,:ruleset,:now)"
            ),
            {
                "o": organization_id,
                "w": workspace_id,
                "p": package.package_id,
                "v": package.version,
                "scope": prior_row["scope_kind"],
                "subject": prior_row["scope_subject_id"],
                "status": readiness.status,
                "required": readiness.required,
                "covered": readiness.covered + readiness.finalized,
                "missing": readiness.missing,
                "indeterminate": (
                    readiness.generated_candidates
                    + readiness.conflicts
                    + readiness.indeterminate
                    + readiness.blocked
                ),
                "fingerprint": package.fingerprint,
                "ruleset": package.rule_set_version_id,
                "now": now,
            },
        )
        for book in package.books:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.id_package_volume_book_versions VALUES "
                    "(:o,:w,:p,:pv,:book,:v,:ordinal,:title,:level,:copies,:fingerprint,:now)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "p": package.package_id,
                    "pv": package.version,
                    "book": book.volume_book_id,
                    "v": book.version,
                    "ordinal": book.ordinal,
                    "title": book.title,
                    "level": book.register_level,
                    "copies": book.required_copy_count,
                    "fingerprint": book.fingerprint,
                    "now": now,
                },
            )
            prior_matrix = (
                session.execute(
                    sa.text(
                        "SELECT matrix_id,matrix_version FROM workspace.id_package_document_membership_versions "
                        "WHERE organization_id=:o AND workspace_id=:w AND id_package_id=:p "
                        "AND id_package_version=:prior LIMIT 1"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "p": package.package_id,
                        "prior": package.version - 1,
                    },
                )
                .mappings()
                .one()
            )
            for membership in book.memberships:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.id_package_document_membership_versions VALUES "
                        "(:o,:w,:membership,:mv,:p,:pv,:book,:bv,:matrix,:matrix_version,"
                        ":requirement,:requirement_version,:role,:ordinal,:copies,:stage,:subject_kind,"
                        ":subject_ref,:state,:evidence,:blockers,:fingerprint,:now)"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "membership": membership.membership_id,
                        "mv": membership.version,
                        "p": package.package_id,
                        "pv": package.version,
                        "book": book.volume_book_id,
                        "bv": book.version,
                        "matrix": prior_matrix["matrix_id"],
                        "matrix_version": prior_matrix["matrix_version"],
                        "requirement": membership.requirement_ref[0]
                        if membership.requirement_ref
                        else None,
                        "requirement_version": membership.requirement_ref[1]
                        if membership.requirement_ref
                        else None,
                        "role": membership.role,
                        "ordinal": membership.ordinal,
                        "copies": membership.required_copy_count,
                        "stage": membership.stage,
                        "subject_kind": membership.subject_kind,
                        "subject_ref": membership.subject_ref,
                        "state": membership.state,
                        "evidence": list(membership.evidence_refs),
                        "blockers": list(membership.blocker_codes),
                        "fingerprint": membership.fingerprint,
                        "now": now,
                    },
                )
            manifest = registry_manifest(package, book)
            register = book.memberships[0]
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_register_candidates VALUES "
                    "(:o,:w,:register,1,:p,:pv,:book,:bv,:membership,:mv,CAST(:manifest AS jsonb),"
                    ":fingerprint,'structured_candidate',ARRAY['REGISTER_TEMPLATE_AUTHORITY_UNRESOLVED'],:now)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "register": deterministic_uuid(
                        f"support-register:{package.package_id}:v{package.version}"
                    ),
                    "p": package.package_id,
                    "pv": package.version,
                    "book": book.volume_book_id,
                    "bv": book.version,
                    "membership": register.membership_id,
                    "mv": register.version,
                    "manifest": json.dumps(
                        manifest, sort_keys=True, separators=(",", ":"), default=str
                    ),
                    "fingerprint": manifest["fingerprint"],
                    "now": now,
                },
            )
        self._insert_readiness(session, organization_id, workspace_id, readiness, now)

    @staticmethod
    def _package_snapshot(
        session: Session, organization_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        tables = {
            "packages": (
                "SELECT * FROM workspace.id_package_versions WHERE organization_id=:o AND workspace_id=:w "
                "ORDER BY id_package_id,version"
            ),
            "books": (
                "SELECT * FROM workspace.id_package_volume_book_versions WHERE organization_id=:o AND "
                "workspace_id=:w ORDER BY id_package_id,id_package_version,ordinal"
            ),
            "memberships": (
                "SELECT * FROM workspace.id_package_document_membership_versions WHERE organization_id=:o "
                "AND workspace_id=:w ORDER BY id_package_id,id_package_version,volume_book_id,ordinal"
            ),
            "registers": (
                "SELECT * FROM workspace.support_register_candidates WHERE organization_id=:o AND "
                "workspace_id=:w ORDER BY id_package_id,id_package_version"
            ),
            "readiness": (
                "SELECT * FROM workspace.id_package_readiness_evaluations WHERE organization_id=:o AND "
                "workspace_id=:w ORDER BY id_package_id,id_package_version,evaluated_at"
            ),
            "generation_runs": (
                "SELECT * FROM workspace.support_generation_runs WHERE organization_id=:o AND "
                "workspace_id=:w ORDER BY generation_run_id"
            ),
            "generated_candidates": (
                "SELECT * FROM workspace.support_generated_document_candidates WHERE organization_id=:o "
                "AND workspace_id=:w ORDER BY generated_candidate_id"
            ),
            "print_validations": (
                "SELECT * FROM workspace.support_print_validation_results WHERE organization_id=:o AND "
                "workspace_id=:w ORDER BY print_validation_id"
            ),
            "reviews": (
                "SELECT * FROM workspace.support_document_review_decisions WHERE organization_id=:o AND "
                "workspace_id=:w ORDER BY review_decision_id"
            ),
            "finalized_documents": (
                "SELECT * FROM workspace.support_finalized_document_versions WHERE organization_id=:o AND "
                "workspace_id=:w ORDER BY finalized_document_id,version"
            ),
            "terminal_receipts": (
                "SELECT r.* FROM workspace.job_terminal_receipts r JOIN workspace.durable_jobs j ON "
                "j.organization_id=r.organization_id AND j.workspace_id=r.workspace_id AND j.job_id=r.job_id "
                "WHERE r.organization_id=:o AND r.workspace_id=:w AND j.job_kind='ID_DOCUMENT_GENERATION' "
                "ORDER BY r.job_id"
            ),
        }
        result: dict[str, Any] = {
            key: [
                _jsonable(item)
                for item in session.execute(
                    sa.text(query), {"o": organization_id, "w": workspace_id}
                ).mappings()
            ]
            for key, query in tables.items()
        }
        packages = result["packages"]
        result["latest_package"] = packages[-1] if packages else None
        return result

    def _resolve_scope(self, owner_identity_id: str, workspace_id: UUID) -> UUID:
        with self._engine.connect() as connection:
            value = connection.scalar(
                sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
                {"owner": owner_identity_id, "workspace": workspace_id},
            )
        if value is None:
            raise SupportProductionError("workspace_not_found")
        return UUID(str(value))

    @staticmethod
    def _latest_matrix(session: Session, organization_id: UUID, workspace_id: UUID) -> Any:
        return (
            session.execute(
                sa.text(
                    "SELECT matrix_id,version,matrix,fingerprint,created_at FROM "
                    "workspace.work_requirement_matrix_versions WHERE organization_id=:o AND "
                    "workspace_id=:w ORDER BY created_at DESC,version DESC LIMIT 1"
                ),
                {"o": organization_id, "w": workspace_id},
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def _resolve_field(
        session: Session, organization_id: UUID, workspace_id: UUID, definition: Any
    ) -> dict[str, Any]:
        row = (
            session.execute(
                sa.text(
                    "SELECT f.fact_id,f.current_version,v.text_value,v.boolean_value,v.numeric_value,"
                    "v.date_value,v.reference_value,v.unit_code,v.source_locator_id,"
                    "v.confirmation_decision_id,e.evidence_link_id FROM workspace.workspace_facts f "
                    "JOIN workspace.workspace_fact_versions v ON v.organization_id=f.organization_id "
                    "AND v.workspace_id=f.workspace_id AND v.fact_id=f.fact_id AND "
                    "v.fact_version=f.current_version LEFT JOIN workspace.workspace_fact_evidence e ON "
                    "e.organization_id=v.organization_id AND e.workspace_id=v.workspace_id AND "
                    "e.fact_id=v.fact_id AND e.fact_version=v.fact_version WHERE f.organization_id=:o "
                    "AND f.workspace_id=:w AND f.fact_type=:key ORDER BY e.evidence_link_id LIMIT 1"
                ),
                {"o": organization_id, "w": workspace_id, "key": definition["field_key"]},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            state = "missing" if definition["required"] else "not_applicable"
            return {
                "key": str(definition["field_key"]),
                "field_key": str(definition["field_key"]),
                "state": state,
                "material": bool(definition["material"]),
                "normalized": None,
                "display": None,
                "fact": None,
                "version": None,
                "fingerprint": semantic_digest({"field": definition["field_key"], "state": state}),
                "evidence": None,
                "locator": None,
                "decision": None,
            }
        display = next(
            (
                str(value)
                for value in (
                    row["text_value"],
                    row["boolean_value"],
                    row["numeric_value"],
                    row["date_value"],
                    row["reference_value"],
                )
                if value is not None
            ),
            "",
        )
        if row["unit_code"]:
            display = f"{display} {row['unit_code']}"
        payload = {
            "field_key": str(definition["field_key"]),
            "state": "confirmed",
            "material": bool(definition["material"]),
            "normalized": display,
            "display": display,
            "fact": row["fact_id"],
            "version": int(row["current_version"]),
            "evidence": row["evidence_link_id"],
            "locator": row["source_locator_id"],
            "decision": row["confirmation_decision_id"],
        }
        payload["key"] = payload["field_key"]
        payload["fingerprint"] = semantic_digest(payload)
        return payload

    @staticmethod
    def _insert_readiness(
        session: Session,
        organization_id: UUID,
        workspace_id: UUID,
        readiness: Any,
        at: datetime,
    ) -> None:
        session.execute(
            sa.text(
                "INSERT INTO workspace.id_package_readiness_evaluations VALUES "
                "(:o,:w,:evaluation,1,:p,:pv,:required,:covered,:generated,:finalized,:missing,"
                ":conflicts,:indeterminate,:blocked,:not_applicable,:blockers,:status,:fingerprint,:at)"
            ),
            {
                "o": organization_id,
                "w": workspace_id,
                "evaluation": uuid7(),
                "p": readiness.package_ref[0],
                "pv": readiness.package_ref[1],
                "required": readiness.required,
                "covered": readiness.covered,
                "generated": readiness.generated_candidates,
                "finalized": readiness.finalized,
                "missing": readiness.missing,
                "conflicts": readiness.conflicts,
                "indeterminate": readiness.indeterminate,
                "blocked": readiness.blocked,
                "not_applicable": readiness.not_applicable,
                "blockers": list(readiness.blocker_codes),
                "status": readiness.status,
                "fingerprint": readiness.fingerprint,
                "at": at,
            },
        )


def _scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def _authority_blockers(authority: str, gaps: tuple[str, ...]) -> tuple[str, ...]:
    if authority == "normative_verified" or authority == "contractual":
        return ()
    if authority == "qualified_rule":
        return ("QUALIFIED_RULE_NOT_ACTIVE",)
    if authority == "methodological_advisory":
        return ("PRACTICE_GUIDANCE_NOT_NORMATIVE_AUTHORITY",)
    return tuple(sorted({"NORMATIVE_BASIS_UNRESOLVED", *gaps}))


def _matrix_requirements(matrix: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in dict(matrix["matrix"]).get("rows", []):
        for document in row.get("documents", []):
            authority = str(document.get("authority_status", "normative_gap"))
            result.append(
                {
                    **document,
                    "work_package_id": str(row["work_package_id"]),
                    "requirement_state": (
                        "required"
                        if authority in {"normative_verified", "contractual"}
                        else "unresolved"
                    ),
                    "required_stage": "work_acceptance",
                    "source_layers": [
                        _basis_layer(str(item)) for item in document.get("basis_refs", [])
                    ],
                    "blockers": list(
                        _authority_blockers(authority, tuple(row.get("normative_gaps", [])))
                    ),
                }
            )
    return result


def _basis_layer(value: str) -> str:
    lowered = value.lower()
    if "practice" in lowered or "guidance" in lowered:
        return "methodological_practice"
    if "customer" in lowered:
        return "customer_addition"
    if "contract" in lowered:
        return "contract"
    if "project" in lowered or "pd-rd" in lowered:
        return "project"
    return "normative"


def _matrix_ref(matrix: Any) -> dict[str, Any] | None:
    if matrix is None:
        return None
    return {
        "matrix_id": str(matrix["matrix_id"]),
        "version": int(matrix["version"]),
        "fingerprint": str(matrix["fingerprint"]),
    }


def _authority_layers() -> dict[str, str]:
    return {
        "normative": "verified_normative_authority_only",
        "project": "workspace_design_fact",
        "contract": "workspace_contractual_source",
        "customer_addition": "workspace_additive_only",
        "methodological_practice": "advisory_not_obligation",
    }


def _jsonable(value: Any) -> dict[str, Any]:
    if hasattr(value, "keys"):
        value = dict(value)
    return cast(dict[str, Any], json.loads(json.dumps(value, default=str, ensure_ascii=False)))
