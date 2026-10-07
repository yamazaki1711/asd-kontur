"""The Support preflight is isolated and immutable."""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import uuid7
from asd_kontur.lifecycle import LifecycleState, PostgresLifecycleRepository
from asd_kontur.support.incoming_inspection import INCOMING_CHECKS, evaluate_incoming_inspection

from .conftest import PostgreSQLEnvironment
from .test_workspace_lifecycle import create_tenant, transition

pytestmark = pytest.mark.postgres


def test_incoming_inspection_rls_and_immutable(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    first = create_tenant(postgres_environment)
    second = create_tenant(postgres_environment)
    transition(
        PostgresLifecycleRepository(postgres_environment.lifecycle_engine),
        first,
        1,
        LifecycleState.ACTIVE,
        "incoming-inspection-activate",
    )
    checks = [
        {"key": key, "state": "pending", "basis": ""}
        for key, _label, _kind in INCOMING_CHECKS
    ]
    result = evaluate_incoming_inspection(checks)
    inspection = {"material_name": "Concrete", "batch_reference": "delivery-7", "checks": checks}
    with postgres_environment.application_engine.begin() as connection:
        connection.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(first.organization_id), True),
                sa.func.set_config("asd.workspace_id", str(first.workspace_id), True),
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.support_incoming_inspection_preflights "
                "(organization_id,workspace_id,preflight_id,idempotency_key,material_name,"
                "batch_reference,inspection,result,payload_digest,submitted_by) VALUES "
                "(:o,:w,:id,'delivery-7','Concrete','delivery-7',CAST(:inspection AS jsonb),"
                "CAST(:result AS jsonb),:digest,'human:synthetic')"
            ),
            {
                "o": first.organization_id,
                "w": first.workspace_id,
                "id": uuid7(),
                "inspection": json.dumps(inspection),
                "result": json.dumps(result),
                "digest": semantic_digest(inspection),
            },
        )
        assert connection.scalar(
            sa.text("SELECT count(*) FROM workspace.support_incoming_inspection_preflights")
        ) == 1
    with postgres_environment.application_engine.begin() as connection:
        connection.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(second.organization_id), True),
                sa.func.set_config("asd.workspace_id", str(second.workspace_id), True),
            )
        )
        assert connection.scalar(
            sa.text("SELECT count(*) FROM workspace.support_incoming_inspection_preflights")
        ) == 0
    with pytest.raises(DBAPIError):
        with postgres_environment.application_engine.begin() as connection:
            connection.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(first.organization_id), True),
                    sa.func.set_config("asd.workspace_id", str(first.workspace_id), True),
                )
            )
            connection.execute(
                sa.text("DELETE FROM workspace.support_incoming_inspection_preflights")
            )
