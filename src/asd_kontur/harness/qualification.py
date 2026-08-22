"""Exact-profile qualification; availability and smoke are never qualification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import ExecutionIdentity, digest_of

ZERO_TOLERANCE_BLOCKERS = frozenset(
    {
        "cross_workspace_leakage",
        "invented_source",
        "invented_locator",
        "edition_substitution",
        "invented_geometry",
        "critical_unit_or_sign_error",
        "candidate_fact_bypass",
        "egress_bypass",
        "document_workspace_mixing",
        "hidden_mandatory_uncertainty",
        "schema_or_result_substitution",
    }
)


@dataclass(frozen=True, slots=True)
class MetricObservation:
    metric_key: str
    value: float
    minimum: float | None
    critical: bool


@dataclass(frozen=True, slots=True)
class QualificationProfile:
    profile_key: str
    version: str
    identity: ExecutionIdentity
    corpus_version: str
    strata: tuple[str, ...]
    metrics: tuple[MetricObservation, ...]
    blocker_counts: tuple[tuple[str, int], ...]
    valid_from: datetime
    valid_until: datetime
    environment: str
    decision: str
    approved_by_human: str | None

    @property
    def fingerprint(self) -> str:
        return digest_of(self)

    def is_qualified(self, identity: ExecutionIdentity, now: datetime) -> bool:
        if self.environment == "production" and self.approved_by_human is None:
            return False
        floors_known = all(item.minimum is not None for item in self.metrics if item.critical)
        floors_pass = all(
            item.minimum is None or item.value >= item.minimum for item in self.metrics
        )
        blockers_pass = (
            all(key in ZERO_TOLERANCE_BLOCKERS and count == 0 for key, count in self.blocker_counts)
            and {key for key, _ in self.blocker_counts} == ZERO_TOLERANCE_BLOCKERS
        )
        return all(
            (
                self.decision == "qualified",
                identity == self.identity,
                self.valid_from <= now < self.valid_until,
                floors_known,
                floors_pass,
                blockers_pass,
            )
        )


def evaluation_only_profile(
    identity: ExecutionIdentity, now: datetime, valid_until: datetime
) -> QualificationProfile:
    return QualificationProfile(
        "qwen3.8-27b.local.evaluation",
        "1.0.0",
        identity,
        "synthetic-g07-v1",
        ("synthetic-native", "synthetic-raster"),
        (),
        tuple((key, 0) for key in sorted(ZERO_TOLERANCE_BLOCKERS)),
        now,
        valid_until,
        "development",
        "evaluation_only",
        None,
    )
