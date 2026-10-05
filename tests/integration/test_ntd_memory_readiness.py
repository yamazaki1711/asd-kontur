from __future__ import annotations

import pytest
import sqlalchemy as sa

from asd_kontur.ntd.readiness import (
    NTD_MEMORY_CRITERIA,
    NtdMemoryReadinessError,
    NtdMemoryReadinessRepository,
)

from .conftest import PostgreSQLEnvironment

pytestmark = pytest.mark.postgres


def test_ntd_memory_readiness_is_append_only_and_fail_closed(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    repository = NtdMemoryReadinessRepository(postgres_environment.application_engine)
    criteria = {key: False for key in NTD_MEMORY_CRITERIA}

    first = repository.record(
        source_commit="3" * 40,
        criteria=criteria,
        blockers=["NTD_MEMORY_AND_RETRIEVAL_NOT_QUALIFIED"],
        decided_by_identity_id="synthetic-owner",
    )
    duplicate = repository.record(
        source_commit="3" * 40,
        criteria=criteria,
        blockers=["NTD_MEMORY_AND_RETRIEVAL_NOT_QUALIFIED"],
        decided_by_identity_id="synthetic-owner",
    )

    assert first == duplicate
    assert first["status"] == "not_ready"
    assert first["denominator_ntd"] == 118
    assert first["deferred_estimate_references"] == 12
    with pytest.raises(NtdMemoryReadinessError, match="ntd_memory_blocker_required"):
        repository.record(
            source_commit="4" * 40,
            criteria={key: True for key in NTD_MEMORY_CRITERIA},
            blockers=[],
            decided_by_identity_id="synthetic-owner",
        )
    with pytest.raises(sa.exc.DBAPIError):
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE application.ntd_memory_readiness_decisions "
                    "SET status='ready' WHERE decision_fingerprint=:fingerprint"
                ),
                {"fingerprint": first["decision_fingerprint"]},
            )
