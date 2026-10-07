"""Qualified material admission links a real batch, work, preflight and evidence."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from asd_kontur.application_spine.auth import OwnerAuthService
from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.domain import uuid7
from asd_kontur.kernel import PostgresCommonKernel
from asd_kontur.lifecycle import LifecycleState, PostgresLifecycleRepository
from asd_kontur.persistence.scope import WorkspaceContext
from asd_kontur.support.incoming_inspection import INCOMING_CHECKS
from asd_kontur.support.incoming_inspection_postgres import IncomingInspectionRepository
from asd_kontur.support.material_admission_postgres import (
    MaterialAdmissionError,
    MaterialAdmissionService,
)
from asd_kontur.support.material_application_postgres import (
    MaterialApplicationError,
    MaterialApplicationService,
)
from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment, run_migration
from .test_common_domain_kernel import (
    DIGEST,
    _command,
    _seed_candidate,
    _seed_policy_and_grant,
    _seed_rule,
)
from .test_support_slice import _grant, _start_support
from .test_workspace_lifecycle import create_tenant, transition

pytestmark = pytest.mark.postgres


def test_material_admission_migration_roundtrip_on_disposable_database(
    postgres_environment: PostgreSQLEnvironment,
    repository_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", "1")
    url = postgres_environment.owner_engine.url
    run_migration(str(repository_root), url, "0135_support_incoming_inspection_preflights")
    with postgres_environment.owner_engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "0135_support_incoming_inspection_preflights"
        )
    run_migration(str(repository_root), url, "head")
    with postgres_environment.owner_engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "0137_support_material_application_basis"
        )
    run_migration(str(repository_root), url, "0135_support_incoming_inspection_preflights")
    with postgres_environment.owner_engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "0135_support_incoming_inspection_preflights"
        )
    run_migration(str(repository_root), url, "head")


def _seed_batch_and_work(
    environment: PostgreSQLEnvironment, tenant: object
) -> tuple[object, object, object, object]:
    candidate, _validation, source, locator = _seed_candidate(environment, tenant)
    policy, grant = _seed_policy_and_grant(environment, tenant)
    command = _command(candidate, policy, grant)
    PostgresCommonKernel(environment.kernel_engine).confirm_candidate(
        context=WorkspaceContext(
            tenant.organization_id,
            tenant.workspace_id,
            "human:synthetic",
            "service:qualification",
            uuid7(),
            uuid7(),
        ),
        command=command,
    )
    rule_set, _rule, _evaluation, trace = _seed_rule(environment, tenant)
    ids = {
        key: uuid7()
        for key in ("work_type", "material", "structure", "element", "work", "batch", "requirement")
    }
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.work_types VALUES "
                "(:id,:key,'1.0.0','human:synthetic',CURRENT_TIMESTAMP)"
            ),
            {"id": ids["work_type"], "key": f"test.admission.work.{tenant.workspace_id}"},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.work_type_versions VALUES "
                "(:id,'1.0.0','1.0.0','Test work','active',:digest,:digest,NULL,NULL)"
            ),
            {"id": ids["work_type"], "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.material_classes VALUES "
                "(:id,:key,'human:synthetic',CURRENT_TIMESTAMP)"
            ),
            {"id": ids["material"], "key": f"test.admission.material.{tenant.workspace_id}"},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.material_class_versions VALUES "
                "(:id,'1.0.0','1.0.0','Test material','active',:digest,:digest)"
            ),
            {"id": ids["material"], "digest": DIGEST},
        )
        params = {
            "o": tenant.organization_id,
            "w": tenant.workspace_id,
            "fact": command.fact_id,
            "rule_set": rule_set,
            "trace": trace,
            "digest": DIGEST,
            **ids,
        }
        for statement in (
            "INSERT INTO workspace.construction_structure_versions VALUES "
            "(:o,:w,:structure,1,:fact,1,:rule_set,:trace,'active',:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.construction_element_versions VALUES "
            "(:o,:w,:element,1,:structure,1,NULL,'test_element','E-1','zone-1',"
            ":fact,1,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.work_instance_versions VALUES "
            "(:o,:w,:work,1,:work_type,'1.0.0',:element,1,'planned',:fact,1,"
            ":rule_set,:trace,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.material_batch_versions VALUES "
            "(:o,:w,:batch,1,:material,'1.0.0','delivery-42','candidate',:fact,1,"
            ":digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.material_requirement_versions "
            "(organization_id,workspace_id,material_requirement_id,version,work_instance_id,"
            "work_instance_version,material_class_id,material_class_version,quantity,unit_code,"
            "precision_scale,applicability,status,rule_trace_id,requirement_digest,recorded_at) "
            "VALUES (:o,:w,:requirement,1,:work,1,:material,'1.0.0',NULL,NULL,NULL,"
            "'applicable','required',:trace,:digest,CURRENT_TIMESTAMP)",
        ):
            connection.execute(sa.text(statement), params)
    return ids["batch"], ids["work"], source, locator


def _evidence(
    environment: PostgreSQLEnvironment,
    tenant: object,
    batch_id: object,
    source: object,
    locator: object,
) -> tuple[object, object, object]:
    ids = tuple(uuid7() for _ in range(3))
    with environment.owner_engine.begin() as connection:
        for evidence_id, role in zip(
            ids, ("material_certificate", "material_passport", "delivery_quantity"), strict=True
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.evidence_links "
                    "(organization_id,workspace_id,evidence_link_id,subject_type,subject_id,"
                    "subject_version,source_version_id,source_locator_id,evidence_role,"
                    "validity_status,decision_ref) VALUES "
                    "(:o,:w,:id,'material_batch',:batch,'1',:source,:locator,:role,"
                    "'verified','decision:synthetic-material')"
                ),
                {
                    "o": tenant.organization_id,
                    "w": tenant.workspace_id,
                    "id": evidence_id,
                    "batch": batch_id,
                    "source": source,
                    "locator": locator,
                    "role": role,
                },
            )
    return ids


def test_material_admission_requires_bound_basis_and_survives_api_reload(
    postgres_environment: PostgreSQLEnvironment, tmp_path: Path
) -> None:
    tenant = create_tenant(postgres_environment)
    _support, process_id, _scope_grant = _start_support(postgres_environment, tenant)
    batch_id, work_id, source, locator = _seed_batch_and_work(postgres_environment, tenant)
    certificate, passport, quantity_evidence = _evidence(
        postgres_environment, tenant, batch_id, source, locator
    )
    settings = SpineSettings(
        database_url=postgres_environment.application_engine.url.render_as_string(
            hide_password=False
        ),
        lifecycle_database_url=postgres_environment.lifecycle_engine.url.render_as_string(
            hide_password=False
        ),
        worker_database_url=postgres_environment.document_worker_engine.url.render_as_string(
            hide_password=False
        ),
        destruction_database_url=postgres_environment.destruction_engine.url.render_as_string(
            hide_password=False
        ),
        support_command_database_url=postgres_environment.support_engine.url.render_as_string(
            hide_password=False
        ),
        object_store_root=tmp_path / "objects",
        archive_store_root=tmp_path / "archives",
        session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
        audit_pepper="synthetic-material-admission-pepper",
    )
    settings.object_store_root.mkdir()
    settings.archive_store_root.mkdir()
    owner = OwnerAuthService(postgres_environment.application_engine, settings).bootstrap_owner(
        username="material-owner",
        password="Synthetic-Material-Password-42!",
        display_name="Material owner",
    )
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO application.owner_organization_grants VALUES "
                "(:owner,:o,ARRAY['workspace.read','workspace.write'],1,CURRENT_TIMESTAMP)"
            ),
            {"owner": owner, "o": tenant.organization_id},
        )
    grant = _grant(postgres_environment, tenant, "support.material.admit", owner)
    checks = [
        {"key": key, "state": "passed", "basis": f"Confirmed evidence for {key}"}
        for key, _label, _kind in INCOMING_CHECKS
    ]
    inspection = IncomingInspectionRepository(postgres_environment.application_engine)
    preflight = inspection.submit(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        material_name="Test material",
        batch_reference="delivery-42",
        material_batch_id=batch_id,
        material_batch_version=1,
        checks=checks,
        idempotency_key="material-preflight-42",
    )
    command = {
        "owner_identity_id": owner,
        "workspace_id": tenant.workspace_id,
        "support_process_id": process_id,
        "material_batch_id": batch_id,
        "material_batch_version": 1,
        "work_instance_id": work_id,
        "work_instance_version": 1,
        "incoming_preflight_id": preflight["preflight_id"],
        "certificate_evidence_ids": [certificate],
        "passport_evidence_ids": [passport],
        "quantity_evidence_link_id": quantity_evidence,
        "delivered_quantity": Decimal("12.500"),
        "delivered_unit": "kg",
        "manufacturer_ref": "Factory A",
        "supplier_ref": "Supplier B",
        "custody_complete": True,
        "applicable_to_work": True,
        "decision_basis": "Verified documents and physical incoming inspection",
        "professional_grant_id": grant.grant_id,
        "professional_grant_version": grant.grant_version,
        "idempotency_key": "material-admit-delivery-42",
    }
    service = MaterialAdmissionService(
        postgres_environment.application_engine, postgres_environment.support_engine
    )
    context = service.context(owner_identity_id=owner, workspace_id=tenant.workspace_id)
    assert context["truncated_sections"] == []
    assert context["batches"][0]["material_batch_id"] == batch_id
    assert context["preflights"][0]["preflight_id"] == preflight["preflight_id"]
    assert {item["evidence_role"] for item in context["evidence"]} == {
        "material_certificate",
        "material_passport",
        "delivery_quantity",
    }
    assert context["grants"][0]["grant_id"] == grant.grant_id
    assert context["requirements"][0]["work_instance_id"] == work_id
    unrelated = create_tenant(postgres_environment)
    with pytest.raises(MaterialAdmissionError, match="workspace_not_found"):
        service.context(owner_identity_id=owner, workspace_id=unrelated.workspace_id)
    unbound = inspection.submit(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        material_name="Test material",
        batch_reference="delivery-42",
        checks=checks,
        idempotency_key="material-unbound-42",
    )
    with pytest.raises(MaterialAdmissionError, match="preflight_batch_mismatch"):
        service.record(
            **{
                **command,
                "incoming_preflight_id": unbound["preflight_id"],
                "idempotency_key": "material-unbound-admission",
            }
        )
    accepted = service.record(**command)
    assert accepted["outcome"] == "admitted"
    assert accepted["reason_codes"] == []
    current = service.context(owner_identity_id=owner, workspace_id=tenant.workspace_id)
    assert current["decisions"][0]["current_decision"] is True
    assert service.record(**command)["admission_id"] == accepted["admission_id"]
    with pytest.raises(MaterialAdmissionError, match="idempotency_conflict"):
        service.record(**{**command, "delivered_quantity": Decimal("13.000")})
    with pytest.raises(MaterialAdmissionError, match="evidence_unverified_or_unrelated"):
        service.record(
            **{
                **command,
                "certificate_evidence_ids": [passport],
                "passport_evidence_ids": [],
                "idempotency_key": "material-bad-evidence",
            }
        )

    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/session/login",
            json={"username": "material-owner", "password": "Synthetic-Material-Password-42!"},
        )
        assert login.status_code == 200
        csrf = client.cookies.get("asd_csrf")
        payload = {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in command.items()
            if key not in {"owner_identity_id", "workspace_id"}
        }
        payload["certificate_evidence_ids"] = [str(certificate)]
        payload["passport_evidence_ids"] = [str(passport)]
        for key in (
            "support_process_id",
            "material_batch_id",
            "work_instance_id",
            "incoming_preflight_id",
            "quantity_evidence_link_id",
            "professional_grant_id",
        ):
            payload[key] = str(payload[key])
        response = client.post(
            f"/api/v1/workspaces/{tenant.workspace_id}/support/material-admissions",
            json=payload,
            headers={"X-CSRF-Token": csrf or ""},
        )
        assert response.status_code == 201
        assert response.json()["admission_id"] == str(accepted["admission_id"])
        displayed = client.get(
            f"/api/v1/workspaces/{tenant.workspace_id}/support/material-admissions/context"
        )
        assert displayed.status_code == 200
        assert displayed.json()["decisions"][0]["admission_id"] == str(accepted["admission_id"])

    failed_checks = [dict(item) for item in checks]
    failed_checks[0]["state"] = "failed"
    failed = inspection.submit(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        material_name="Test material",
        batch_reference="delivery-42",
        material_batch_id=batch_id,
        material_batch_version=1,
        checks=failed_checks,
        idempotency_key="material-preflight-42-failed",
    )
    with pytest.raises(MaterialAdmissionError, match="preflight_stale"):
        service.record(**{**command, "idempotency_key": "material-old-preflight"})
    quarantined = service.record(
        **{
            **command,
            "incoming_preflight_id": failed["preflight_id"],
            "idempotency_key": "material-quarantine-delivery-42",
        }
    )
    assert quarantined["outcome"] == "quarantined"
    assert "INCOMING_CONTROL_NONCONFORMING" in quarantined["reason_codes"]
    after_failure = service.context(owner_identity_id=owner, workspace_id=tenant.workspace_id)
    assert after_failure["decisions"][0]["current_decision"] is True
    assert after_failure["decisions"][1]["current_decision"] is False

    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspace.material_requirement_versions "
                "(organization_id,workspace_id,material_requirement_id,version,work_instance_id,"
                "work_instance_version,material_class_id,material_class_version,quantity,unit_code,"
                "precision_scale,applicability,status,rule_trace_id,"
                "requirement_digest,recorded_at) "
                "SELECT organization_id,workspace_id,material_requirement_id,2,work_instance_id,"
                "work_instance_version,material_class_id,material_class_version,quantity,unit_code,"
                "precision_scale,applicability,'superseded',rule_trace_id,requirement_digest,"
                "CURRENT_TIMESTAMP FROM workspace.material_requirement_versions WHERE "
                "organization_id=:o AND workspace_id=:w AND work_instance_id=:work AND version=1"
            ),
            {"o": tenant.organization_id, "w": tenant.workspace_id, "work": work_id},
        )
    with pytest.raises(MaterialAdmissionError, match="work_material_not_specified"):
        service.record(**{**command, "idempotency_key": "material-obsolete-work-requirement"})
    after_change = service.context(owner_identity_id=owner, workspace_id=tenant.workspace_id)
    assert all(item["current_decision"] is False for item in after_change["decisions"])

    transition(
        PostgresLifecycleRepository(postgres_environment.lifecycle_engine),
        tenant,
        2,
        LifecycleState.FREEZING,
        "material-admission-freeze",
    )
    with pytest.raises(MaterialAdmissionError, match="support_workspace_not_active"):
        service.record(**{**command, "idempotency_key": "material-after-freeze"})


def test_material_application_requires_actual_use_and_caps_batch_total(
    postgres_environment: PostgreSQLEnvironment, tmp_path: Path
) -> None:
    tenant = create_tenant(postgres_environment)
    _support, process_id, _scope_grant = _start_support(postgres_environment, tenant)
    batch_id, work_id, source, locator = _seed_batch_and_work(postgres_environment, tenant)
    certificate, passport, quantity_evidence = _evidence(
        postgres_environment, tenant, batch_id, source, locator
    )
    settings = SpineSettings(
        database_url=postgres_environment.application_engine.url.render_as_string(
            hide_password=False
        ),
        lifecycle_database_url=postgres_environment.lifecycle_engine.url.render_as_string(
            hide_password=False
        ),
        worker_database_url=postgres_environment.document_worker_engine.url.render_as_string(
            hide_password=False
        ),
        destruction_database_url=postgres_environment.destruction_engine.url.render_as_string(
            hide_password=False
        ),
        support_command_database_url=postgres_environment.support_engine.url.render_as_string(
            hide_password=False
        ),
        object_store_root=tmp_path / "objects",
        archive_store_root=tmp_path / "archives",
        session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
        audit_pepper="synthetic-material-application-pepper",
    )
    settings.object_store_root.mkdir()
    settings.archive_store_root.mkdir()
    owner = OwnerAuthService(postgres_environment.application_engine, settings).bootstrap_owner(
        username="material-application-owner",
        password="Synthetic-Material-Application-42!",
        display_name="Material application owner",
    )
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO application.owner_organization_grants VALUES "
                "(:owner,:o,ARRAY['workspace.read','workspace.write'],1,CURRENT_TIMESTAMP)"
            ),
            {"owner": owner, "o": tenant.organization_id},
        )
    admit_grant = _grant(postgres_environment, tenant, "support.material.admit", owner)
    apply_grant = _grant(postgres_environment, tenant, "support.material.apply", owner)
    inspection = IncomingInspectionRepository(postgres_environment.application_engine)
    checks = [
        {"key": key, "state": "passed", "basis": f"Confirmed evidence for {key}"}
        for key, _label, _kind in INCOMING_CHECKS
    ]
    preflight = inspection.submit(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        material_name="Test material",
        batch_reference="delivery-42",
        material_batch_id=batch_id,
        material_batch_version=1,
        checks=checks,
        idempotency_key="application-preflight-42",
    )
    admission = MaterialAdmissionService(
        postgres_environment.application_engine, postgres_environment.support_engine
    ).record(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        support_process_id=process_id,
        material_batch_id=batch_id,
        material_batch_version=1,
        work_instance_id=work_id,
        work_instance_version=1,
        incoming_preflight_id=preflight["preflight_id"],
        certificate_evidence_ids=[certificate],
        passport_evidence_ids=[passport],
        quantity_evidence_link_id=quantity_evidence,
        delivered_quantity=Decimal("12.500"),
        delivered_unit="kg",
        manufacturer_ref="Factory A",
        supplier_ref="Supplier B",
        custody_complete=True,
        applicable_to_work=True,
        decision_basis="Verified delivery and inspection",
        professional_grant_id=admit_grant.grant_id,
        professional_grant_version=admit_grant.grant_version,
        idempotency_key="application-admission-42",
    )
    use_evidence = uuid7()
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE workspace.source_artifacts SET source_kind='field_document' WHERE "
                "organization_id=:o AND workspace_id=:w AND source_artifact_id=(SELECT "
                "source_artifact_id FROM workspace.source_versions WHERE organization_id=:o "
                "AND workspace_id=:w AND source_version_id=:source)"
            ),
            {"o": tenant.organization_id, "w": tenant.workspace_id, "source": source},
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.evidence_links "
                "(organization_id,workspace_id,evidence_link_id,subject_type,subject_id,"
                "subject_version,source_version_id,source_locator_id,evidence_role,"
                "validity_status,decision_ref) VALUES "
                "(:o,:w,:evidence,'work_instance',:work,'1',:source,:locator,"
                "'material_application','verified','decision:synthetic-field-confirmation')"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "evidence": use_evidence,
                "work": work_id,
                "source": source,
                "locator": locator,
            },
        )
    service = MaterialApplicationService(
        postgres_environment.application_engine, postgres_environment.support_engine
    )
    command = {
        "owner_identity_id": owner,
        "workspace_id": tenant.workspace_id,
        "admission_id": admission["admission_id"],
        "evidence_link_id": use_evidence,
        "quantity": Decimal("5.250"),
        "unit_code": "kg",
        "decision_basis": "Confirmed actual use on the selected work",
        "professional_grant_id": apply_grant.grant_id,
        "professional_grant_version": apply_grant.grant_version,
        "idempotency_key": "material-application-first",
    }
    first = service.record(**command)
    assert first["quantity"] == Decimal("5.250")
    assert service.record(**command)["material_application_id"] == first["material_application_id"]
    with pytest.raises(MaterialApplicationError, match="idempotency_conflict"):
        service.record(**{**command, "quantity": Decimal("5.251")})
    with pytest.raises(MaterialApplicationError, match="exceeds_delivery"):
        service.record(
            **{
                **command,
                "quantity": Decimal("7.251"),
                "idempotency_key": "material-application-over-delivery",
            }
        )
    with pytest.raises(MaterialApplicationError, match="unit_incompatible"):
        service.record(
            **{**command, "unit_code": "t", "idempotency_key": "material-application-wrong-unit"}
        )
    with pytest.raises(MaterialApplicationError, match="evidence_unverified"):
        service.record(
            **{
                **command,
                "evidence_link_id": certificate,
                "idempotency_key": "material-application-delivery-not-use",
            }
        )
    second = service.record(
        **{
            **command,
            "quantity": Decimal("7.250"),
            "idempotency_key": "material-application-second",
        }
    )
    assert second["quantity"] == Decimal("7.250")
    context = MaterialAdmissionService(
        postgres_environment.application_engine, postgres_environment.support_engine
    ).context(owner_identity_id=owner, workspace_id=tenant.workspace_id)
    assert len(context["applications"]) == 2
    assert context["application_grants"][0]["grant_id"] == apply_grant.grant_id
    assert context["application_evidence"][0]["evidence_link_id"] == use_evidence

    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/session/login",
            json={
                "username": "material-application-owner",
                "password": "Synthetic-Material-Application-42!",
            },
        )
        assert login.status_code == 200
        csrf = client.cookies.get("asd_csrf")
        response = client.post(
            f"/api/v1/workspaces/{tenant.workspace_id}/support/material-applications",
            json={
                key: str(value) if isinstance(value, (Decimal, type(batch_id))) else value
                for key, value in command.items()
                if key not in {"owner_identity_id", "workspace_id"}
            },
            headers={"X-CSRF-Token": csrf or ""},
        )
        assert response.status_code == 201, response.text
        assert response.json()["material_application_id"] == str(first["material_application_id"])

    inspection.submit(
        owner_identity_id=owner,
        workspace_id=tenant.workspace_id,
        material_name="Test material",
        batch_reference="delivery-42",
        material_batch_id=batch_id,
        material_batch_version=1,
        checks=checks,
        idempotency_key="application-newer-preflight-42",
    )
    with pytest.raises(MaterialApplicationError, match="admission_stale"):
        service.record(
            **{
                **command,
                "quantity": Decimal("0.100"),
                "idempotency_key": "material-application-stale-admission",
            }
        )

    transition(
        PostgresLifecycleRepository(postgres_environment.lifecycle_engine),
        tenant,
        2,
        LifecycleState.FREEZING,
        "material-application-freeze",
    )
    with pytest.raises(MaterialApplicationError, match="support_workspace_not_active"):
        service.record(
            **{
                **command,
                "quantity": Decimal("0.100"),
                "idempotency_key": "material-application-after-freeze",
            }
        )
