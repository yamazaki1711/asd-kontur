from __future__ import annotations

from uuid import UUID

import pytest

from asd_kontur.lifecycle import (
    ArchiveImportGuard,
    ExactVersionReference,
    FinalizationGuard,
    FreezeAssessment,
    LifecycleError,
    LifecycleErrorCode,
    LifecycleState,
    Mode,
    ModeExecutionConfiguration,
    ProvisioningGuard,
    RetentionProfile,
    reopen_allowed,
)


def profile(environment: str, *, complete: bool, approved: bool) -> RetentionProfile:
    return RetentionProfile(
        ExactVersionReference("retention.synthetic", "0.1.0"),
        environment,
        frozenset({"workspace_sources", "workspace_results", "recovery_residue"}),
        complete,
        approved,
    )


def mode(mode_value: Mode, value: int) -> ModeExecutionConfiguration:
    exact = ExactVersionReference("synthetic", "0.1.0")
    return ModeExecutionConfiguration(
        UUID(int=value),
        mode_value,
        exact,
        exact,
        exact,
        exact,
        exact,
        exact,
        "purpose.synthetic",
    )


def test_synthetic_provisioning_accepts_multiple_governed_modes() -> None:
    modes = tuple(mode(item, index + 1) for index, item in enumerate(Mode))
    decision = ProvisioningGuard.evaluate(
        profile=profile("development", complete=True, approved=False),
        policy_assignment=ExactVersionReference("policy.synthetic", "0.1.0"),
        authority_profile=ExactVersionReference("authority.synthetic", "0.1.0"),
        modes=modes,
    )
    assert decision.accepted
    assert len(decision.mode_execution_ids) == 4


def test_production_provision_and_finalize_are_blocked_without_policy_values() -> None:
    blocked_profile = profile("production", complete=False, approved=False)
    with pytest.raises(LifecycleError) as provisioning:
        ProvisioningGuard.evaluate(
            profile=blocked_profile,
            policy_assignment=ExactVersionReference("policy.blocked", "0.1.0"),
            authority_profile=ExactVersionReference("authority.blocked", "0.1.0"),
            modes=(),
        )
    assert provisioning.value.code is LifecycleErrorCode.POLICY_BLOCKED
    with pytest.raises(LifecycleError) as finalization:
        FinalizationGuard.evaluate(
            profile=blocked_profile,
            mode_states={},
            blockers=(),
            uncertainties=(),
        )
    assert finalization.value.code is LifecycleErrorCode.POLICY_BLOCKED


def test_freeze_requires_zero_writers_and_accounted_jobs() -> None:
    FreezeAssessment(0, ("job-1",), ("job-1",), ()).require_drained()
    with pytest.raises(LifecycleError) as not_drained:
        FreezeAssessment(1, ("job-1",), (), ()).require_drained()
    assert not_drained.value.code is LifecycleErrorCode.WRITE_FENCED


def test_terminal_modes_do_not_claim_product_ready() -> None:
    decision = FinalizationGuard.evaluate(
        profile=profile("development", complete=True, approved=False),
        mode_states={UUID(int=1): "completed", UUID(int=2): "blocked"},
        blockers=(),
        uncertainties=("uncertainty.synthetic",),
    )
    assert decision.outcome == "verified"
    assert decision.product_ready is False


def test_archive_import_creates_new_scope_and_strips_old_authority_and_indexes() -> None:
    source = UUID(int=20)
    decision = ArchiveImportGuard.decide(
        source_workspace_id=source,
        source_state=LifecycleState.CLOSED,
        archive_verified=True,
        archive_integrity_matches=True,
        schema_compatibility="compatible",
        authorized=True,
        new_workspace_id=UUID(int=21),
    )
    assert decision.new_workspace_id != source
    assert decision.candidates_require_reconfirmation
    assert not decision.project_indexes_imported
    assert not decision.old_authorizations_imported


def test_destroyed_or_corrupt_archive_import_and_post_purge_reopen_are_denied() -> None:
    with pytest.raises(LifecycleError) as destroyed:
        ArchiveImportGuard.decide(
            source_workspace_id=UUID(int=30),
            source_state=LifecycleState.DESTROYED,
            archive_verified=True,
            archive_integrity_matches=True,
            schema_compatibility="compatible",
            authorized=True,
        )
    assert destroyed.value.code is LifecycleErrorCode.IMPORT_BLOCKED
    with pytest.raises(LifecycleError) as corrupt:
        ArchiveImportGuard.decide(
            source_workspace_id=UUID(int=31),
            source_state=LifecycleState.CLOSED,
            archive_verified=True,
            archive_integrity_matches=False,
            schema_compatibility="compatible",
            authorized=True,
        )
    assert corrupt.value.code is LifecycleErrorCode.ARCHIVE_INVALID
    assert reopen_allowed(LifecycleState.CLOSED, purge_started=False, policy_allows=True)
    assert not reopen_allowed(LifecycleState.CLOSED, purge_started=True, policy_allows=True)
