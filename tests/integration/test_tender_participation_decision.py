"""Isolated API acceptance for contractor-supplied Tender decision inputs."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment
from .test_product_application_spine import _csrf, _login, _settings

pytestmark = pytest.mark.postgres


def test_tender_participation_is_workspace_scoped_and_versioned(
    postgres_environment: PostgreSQLEnvironment, tmp_path: Path
) -> None:
    settings = _settings(postgres_environment, tmp_path)
    app = create_app(engine=postgres_environment.application_engine, settings=settings)
    app.state.container.auth.bootstrap_owner(
        username="participation-owner",
        password="Synthetic-Owner-Password-42!",
        display_name="Participation owner",
    )
    with TestClient(app) as client:
        _login(client, "participation-owner", "Synthetic-Owner-Password-42!")
        first = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Synthetic water crossing"},
            headers=_csrf(client),
        ).json()["workspace_id"]
        second = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Synthetic warehouse"},
            headers=_csrf(client),
        ).json()["workspace_id"]
        path = f"/api/v1/workspaces/{first}/tender/participation-decision"
        blank = client.get(path)
        assert blank.status_code == 200
        assert blank.json()["decision"] == "INSUFFICIENT_INPUT"
        assert blank.json()["assessment_id"] is None
        payload = {
            "company_scope_fit": "no",
            "company_scope_fit_reason": "No relevant construction qualification",
            "contract_acceptable": "unknown",
            "conditions_feasible": "unknown",
            "minimum_viable_price_rub": None,
            "price_basis_confirmed": False,
        }
        saved = client.put(path, json=payload, headers=_csrf(client))
        assert saved.status_code == 200, saved.text
        assert saved.json()["decision"] == "DO_NOT_PARTICIPATE"
        assert saved.json()["blockers"][0]["code"] == "PROFILE_MISMATCH"
        replay = client.put(path, json=payload, headers=_csrf(client))
        assert replay.status_code == 200
        assert replay.json()["assessment_id"] == saved.json()["assessment_id"]
        other = client.get(f"/api/v1/workspaces/{second}/tender/participation-decision")
        assert other.status_code == 200
        assert other.json()["assessment_id"] is None
