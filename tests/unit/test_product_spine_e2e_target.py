from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

_path = Path(__file__).resolve().parents[2] / "tools" / "run_product_spine_e2e_server.py"
_spec = importlib.util.spec_from_file_location("run_product_spine_e2e_server", _path)
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
_require_isolated_test_cluster = _module._require_isolated_test_cluster


def test_fixture_preflight_rejects_the_actual_live_cluster() -> None:
    target = make_url("postgresql+psycopg://oleg@127.0.0.1:55433/postgres")
    with pytest.raises(RuntimeError, match="owner's live PostgreSQL cluster"):
        _require_isolated_test_cluster(target, {"postgres", "asd_kontur_public_demo"})


def test_fixture_preflight_rejects_live_writer_credentials() -> None:
    target = make_url("postgresql+psycopg://asd_public_app@127.0.0.1:55433/postgres")
    with pytest.raises(RuntimeError, match="isolated cluster admin"):
        _require_isolated_test_cluster(target, {"postgres"})


def test_fixture_preflight_accepts_disposable_cluster() -> None:
    target = make_url("postgresql+psycopg://test_admin@127.0.0.1:55433/postgres")
    _require_isolated_test_cluster(target, {"postgres", "template1"})
