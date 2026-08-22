"""Pure guards for provisioning, finalization, reopen, and archive import."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import rfc8785

from asd_kontur.domain import uuid7

from .errors import LifecycleError, LifecycleErrorCode
from .models import (
    ExactVersionReference,
    LifecycleState,
    ModeExecutionConfiguration,
    RetentionProfile,
)


@dataclass(frozen=True, slots=True)
class ProvisioningDecision:
    accepted: bool
    environment: str
    mode_execution_ids: tuple[UUID, ...]
    reason_code: str


class ProvisioningGuard:
    @staticmethod
    def evaluate(
        *,
        profile: RetentionProfile,
        policy_assignment: ExactVersionReference,
        authority_profile: ExactVersionReference,
        modes: tuple[ModeExecutionConfiguration, ...],
    ) -> ProvisioningDecision:
        del policy_assignment, authority_profile
        if not profile.complete:
            raise LifecycleError(
                LifecycleErrorCode.POLICY_BLOCKED,
                "Provisioning requires a complete RetentionProfile.",
            )
        if profile.environment == "production" and not profile.production_approved:
            raise LifecycleError(
                LifecycleErrorCode.POLICY_BLOCKED,
                "Production provisioning is default-deny without approved policy values.",
            )
        ids = tuple(item.mode_execution_id for item in modes)
        if len(ids) != len(set(ids)):
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "ModeExecution identities must be unique within a workspace.",
            )
        return ProvisioningDecision(True, profile.environment, ids, "provisioning.accepted")


@dataclass(frozen=True, slots=True)
class FreezeAssessment:
    writer_count: int
    active_job_ids: tuple[str, ...]
    cancelled_job_ids: tuple[str, ...]
    checkpointed_job_ids: tuple[str, ...]

    def require_drained(self) -> None:
        accounted = set(self.cancelled_job_ids) | set(self.checkpointed_job_ids)
        if self.writer_count != 0 or set(self.active_job_ids) - accounted:
            raise LifecycleError(
                LifecycleErrorCode.WRITE_FENCED,
                "Freeze cannot complete until writers are zero and every job is accounted for.",
            )


@dataclass(frozen=True, slots=True)
class FinalizationDecision:
    outcome: str
    blockers: tuple[str, ...]
    uncertainties: tuple[str, ...]
    result_manifest_digest: str
    product_ready: bool = False


class FinalizationGuard:
    TERMINAL_MODE_STATES = frozenset({"completed", "blocked", "failed", "cancelled"})

    @classmethod
    def evaluate(
        cls,
        *,
        profile: RetentionProfile,
        mode_states: Mapping[UUID, str],
        blockers: tuple[str, ...],
        uncertainties: tuple[str, ...],
    ) -> FinalizationDecision:
        if not profile.complete or (
            profile.environment == "production" and not profile.production_approved
        ):
            raise LifecycleError(
                LifecycleErrorCode.POLICY_BLOCKED,
                "Finalization requires a complete applicable RetentionProfile.",
            )
        non_terminal = tuple(
            str(mode_id)
            for mode_id, state in mode_states.items()
            if state not in cls.TERMINAL_MODE_STATES
        )
        all_blockers = tuple(sorted(set(blockers) | set(non_terminal)))
        outcome = "verified" if not all_blockers else "blocked"
        payload: dict[str, Any] = {
            "mode_states": sorted((str(key), value) for key, value in mode_states.items()),
            "blockers": all_blockers,
            "uncertainties": uncertainties,
            "product_ready": False,
        }
        digest = "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
        return FinalizationDecision(outcome, all_blockers, uncertainties, digest)


@dataclass(frozen=True, slots=True)
class ArchiveImportDecision:
    import_id: UUID
    source_workspace_id: UUID
    new_workspace_id: UUID
    new_workspace_revision: int
    schema_compatibility: str
    candidates_require_reconfirmation: bool
    project_indexes_imported: bool
    old_authorizations_imported: bool


class ArchiveImportGuard:
    @staticmethod
    def decide(
        *,
        source_workspace_id: UUID,
        source_state: LifecycleState,
        archive_verified: bool,
        archive_integrity_matches: bool,
        schema_compatibility: str,
        authorized: bool,
        new_workspace_id: UUID | None = None,
    ) -> ArchiveImportDecision:
        if source_state is LifecycleState.DESTROYED:
            raise LifecycleError(
                LifecycleErrorCode.IMPORT_BLOCKED,
                "An archive destroyed under an attested destroy plan cannot be imported.",
            )
        if not archive_verified or not archive_integrity_matches:
            raise LifecycleError(
                LifecycleErrorCode.ARCHIVE_INVALID,
                "Archive import requires exact integrity and readability verification.",
            )
        if schema_compatibility != "compatible" or not authorized:
            raise LifecycleError(
                LifecycleErrorCode.IMPORT_BLOCKED,
                "Archive compatibility and fresh import authority are required.",
            )
        target = new_workspace_id or uuid7()
        if target == source_workspace_id:
            raise LifecycleError(
                LifecycleErrorCode.IMPORT_BLOCKED,
                "Archive import must create a new workspace identity.",
            )
        return ArchiveImportDecision(
            uuid7(),
            source_workspace_id,
            target,
            1,
            schema_compatibility,
            True,
            False,
            False,
        )


def reopen_allowed(state: LifecycleState, *, purge_started: bool, policy_allows: bool) -> bool:
    return state is LifecycleState.CLOSED and not purge_started and policy_allows
