from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from asd_kontur.contracts import ContractRegistry


@pytest.fixture(scope="session")
def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def migration_head(repository_root: Path) -> str:
    """Expected DB marker comes from the checked-in, single-head migration graph."""
    scripts = ScriptDirectory.from_config(Config(str(repository_root / "alembic.ini")))
    heads = scripts.get_heads()
    assert len(heads) == 1, f"Expected one migration head, got {heads}"
    return heads[0]


@pytest.fixture(scope="session")
def contract_root(repository_root: Path) -> Path:
    return repository_root / "contracts" / "v0.1"


@pytest.fixture(scope="session")
def contract_registry(contract_root: Path) -> ContractRegistry:
    return ContractRegistry.load(contract_root)
