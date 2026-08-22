from __future__ import annotations

from pathlib import Path

import pytest

from asd_kontur.contracts import ContractRegistry


@pytest.fixture(scope="session")
def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def contract_root(repository_root: Path) -> Path:
    return repository_root / "contracts" / "v0.1"


@pytest.fixture(scope="session")
def contract_registry(contract_root: Path) -> ContractRegistry:
    return ContractRegistry.load(contract_root)
