"""Bounded, targeted and immutable Candidate repair."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .errors import HarnessError, HarnessErrorCode
from .models import (
    CandidateStatus,
    CandidateVersion,
    FieldCandidate,
    Repairability,
    ValidationFailure,
)


@dataclass(frozen=True, slots=True)
class RepairPlan:
    repair_id: UUID
    candidate_id: UUID
    parent_version: int
    fields: tuple[str, ...]
    locator_ids: tuple[UUID, ...]
    failure_fingerprints: tuple[str, ...]
    cycle: int


@dataclass(frozen=True, slots=True)
class FieldConflict:
    field_path: str
    source_locator_ids: tuple[UUID, ...]
    values: tuple[object, ...]


class RepairController:
    def __init__(self, max_cycles: int, no_progress_limit: int) -> None:
        self.max_cycles = max_cycles
        self.no_progress_limit = no_progress_limit

    def plan(
        self,
        *,
        repair_id: UUID,
        candidate: CandidateVersion,
        failures: tuple[ValidationFailure, ...],
        cycle: int,
        prior_failure_sets: tuple[frozenset[str], ...] = (),
    ) -> RepairPlan:
        repairable = tuple(
            item for item in failures if item.repairability == Repairability.TARGETED_REPAIR
        )
        if not repairable or cycle > self.max_cycles:
            raise HarnessError(
                HarnessErrorCode.REPAIR_NOT_ALLOWED, "No bounded targeted repair is permitted."
            )
        fingerprint_set = frozenset(item.fingerprint for item in failures)
        if (
            fingerprint_set in prior_failure_sets
            or sum(1 for item in prior_failure_sets if item == fingerprint_set)
            >= self.no_progress_limit
        ):
            raise HarnessError(
                HarnessErrorCode.REPAIR_NO_PROGRESS, "Repeated failure fingerprint stopped repair."
            )
        locator_ids = sorted(
            {locator.locator_id for item in repairable for locator in item.source_locators}, key=str
        )
        return RepairPlan(
            repair_id,
            candidate.candidate_id,
            candidate.version,
            tuple(sorted({item.field_path for item in repairable})),
            tuple(locator_ids),
            tuple(sorted(item.fingerprint for item in repairable)),
            cycle,
        )

    def reconcile(
        self,
        *,
        parent: CandidateVersion,
        plan: RepairPlan,
        replacements: tuple[FieldCandidate, ...],
        new_attempt_id: UUID,
    ) -> tuple[CandidateVersion, tuple[FieldConflict, ...]]:
        if plan.candidate_id != parent.candidate_id or plan.parent_version != parent.version:
            raise HarnessError(
                HarnessErrorCode.REPAIR_NOT_ALLOWED,
                "Repair plan does not match its immutable parent.",
            )
        allowed = set(plan.fields)
        if any(item.field_path not in allowed for item in replacements):
            raise HarnessError(
                HarnessErrorCode.REPAIR_NOT_ALLOWED, "Repair attempted to change an unfailed field."
            )
        replacement_map: dict[str, list[FieldCandidate]] = {}
        for item in replacements:
            replacement_map.setdefault(item.field_path, []).append(item)
        conflicts: list[FieldConflict] = []
        chosen: dict[str, FieldCandidate] = {}
        for path, values in replacement_map.items():
            distinct = {repr(item.value) for item in values}
            if len(distinct) > 1:
                conflicts.append(
                    FieldConflict(
                        path,
                        tuple(
                            locator.locator_id
                            for item in values
                            for locator in item.source_locators
                        ),
                        tuple(item.value for item in values),
                    )
                )
            else:
                chosen[path] = values[0]
        fields = tuple(chosen.get(item.field_path, item) for item in parent.fields)
        for path, item in chosen.items():
            if all(existing.field_path != path for existing in parent.fields):
                fields += (item,)
        status = CandidateStatus.UNRESOLVED_UNCERTAINTY if conflicts else CandidateStatus.UNVERIFIED
        return CandidateVersion(
            parent.candidate_id,
            parent.version + 1,
            parent.scope,
            parent.purpose,
            "repair",
            fields,
            status,
            parent.source_version_id,
            new_attempt_id,
            parent.version,
        ), tuple(conflicts)
