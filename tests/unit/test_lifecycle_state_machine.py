from __future__ import annotations

from uuid import UUID

import pytest

from asd_kontur.lifecycle import (
    Authority,
    ExactVersionReference,
    LifecycleError,
    LifecycleErrorCode,
    LifecycleState,
    LifecycleStateMachine,
    Mode,
    ModeExecutionConfiguration,
)

WORKSPACE_ID = UUID("018f5c3e-7b00-7000-8000-000000000601")


def authority(*capabilities: str) -> Authority:
    return Authority("identity.synthetic.lifecycle", "human", frozenset(capabilities))


@pytest.mark.parametrize(
    ("source", "target", "capability"),
    [
        (LifecycleState.PROVISIONING, LifecycleState.ACTIVE, "workspace.provision"),
        (LifecycleState.ACTIVE, LifecycleState.FREEZING, "workspace.freeze"),
        (LifecycleState.FREEZING, LifecycleState.FROZEN, "workspace.freeze"),
        (LifecycleState.FROZEN, LifecycleState.FINALIZING, "workspace.finalize"),
        (LifecycleState.FINALIZING, LifecycleState.FINALIZED, "workspace.finalize"),
        (LifecycleState.FINALIZED, LifecycleState.EXPORTING, "workspace.export"),
        (LifecycleState.EXPORTING, LifecycleState.EXPORTED, "workspace.export"),
        (LifecycleState.EXPORTED, LifecycleState.ARCHIVING, "workspace.archive"),
        (LifecycleState.ARCHIVING, LifecycleState.ARCHIVED, "workspace.archive"),
        (LifecycleState.ARCHIVED, LifecycleState.CLOSED, "workspace.close"),
        (LifecycleState.CLOSED, LifecycleState.REOPENING, "workspace.reopen"),
        (LifecycleState.REOPENING, LifecycleState.ACTIVE, "workspace.provision"),
        (LifecycleState.CLOSED, LifecycleState.RESET_PLANNING, "workspace.reset.plan"),
        (
            LifecycleState.RESET_PLANNING,
            LifecycleState.RESET_AUTHORIZED,
            "workspace.reset.authorize",
        ),
        (LifecycleState.RESET_AUTHORIZED, LifecycleState.PURGING, "workspace.purge.execute"),
        (
            LifecycleState.PURGING,
            LifecycleState.VERIFYING_RESET,
            "workspace.reset.verify",
        ),
        (
            LifecycleState.VERIFYING_RESET,
            LifecycleState.RESET_VERIFIED,
            "workspace.reset.verify",
        ),
        (
            LifecycleState.RESET_VERIFIED,
            LifecycleState.DESTROYING,
            "workspace.destroy.execute",
        ),
        (LifecycleState.DESTROYING, LifecycleState.DESTROYED, "workspace.destroy.verify"),
        (LifecycleState.RECOVERY_REQUIRED, LifecycleState.PURGING, "workspace.purge.execute"),
        (
            LifecycleState.RECOVERY_REQUIRED,
            LifecycleState.DESTROYING,
            "workspace.destroy.execute",
        ),
    ],
)
def test_all_happy_path_transitions_are_explicit(
    source: LifecycleState, target: LifecycleState, capability: str
) -> None:
    decision = LifecycleStateMachine.decide(
        workspace_id=WORKSPACE_ID,
        current_state=source,
        current_version=7,
        expected_version=7,
        target_state=target,
        operation_key=f"synthetic:{source}:{target}",
        actor=authority(capability),
    )
    assert decision.new_state is target
    assert decision.new_version == 8


def test_invalid_transition_and_stale_version_fail_closed() -> None:
    with pytest.raises(LifecycleError) as invalid:
        LifecycleStateMachine.decide(
            workspace_id=WORKSPACE_ID,
            current_state=LifecycleState.ACTIVE,
            current_version=1,
            expected_version=1,
            target_state=LifecycleState.DESTROYED,
            operation_key="invalid",
            actor=authority("workspace.destroy.verify"),
        )
    assert invalid.value.code is LifecycleErrorCode.INVALID_TRANSITION
    with pytest.raises(LifecycleError) as stale:
        LifecycleStateMachine.decide(
            workspace_id=WORKSPACE_ID,
            current_state=LifecycleState.ACTIVE,
            current_version=2,
            expected_version=1,
            target_state=LifecycleState.FREEZING,
            operation_key="stale",
            actor=authority("workspace.freeze"),
        )
    assert stale.value.code is LifecycleErrorCode.CONCURRENCY_CONFLICT


def test_legal_hold_blocks_destructive_transition_without_losing_state() -> None:
    with pytest.raises(LifecycleError) as blocked:
        LifecycleStateMachine.decide(
            workspace_id=WORKSPACE_ID,
            current_state=LifecycleState.RESET_AUTHORIZED,
            current_version=4,
            expected_version=4,
            target_state=LifecycleState.PURGING,
            operation_key="purge",
            actor=authority("workspace.purge.execute"),
            legal_hold_active=True,
        )
    assert blocked.value.code is LifecycleErrorCode.LEGAL_HOLD_ACTIVE


def test_only_provisioning_and_active_are_materially_writable() -> None:
    writable = {state for state in LifecycleState if LifecycleStateMachine.is_writable(state)}
    assert writable == {LifecycleState.PROVISIONING, LifecycleState.ACTIVE}


def test_four_modes_share_one_configuration_contract() -> None:
    reference = ExactVersionReference("synthetic", "0.1.0")
    configurations = {
        ModeExecutionConfiguration(
            UUID(int=index + 1),
            mode,
            reference,
            reference,
            reference,
            reference,
            reference,
            reference,
            "purpose.synthetic",
        )
        for index, mode in enumerate(Mode)
    }
    assert {item.mode for item in configurations} == set(Mode)
