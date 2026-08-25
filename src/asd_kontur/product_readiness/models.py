"""Product readiness vocabulary fixed by PRODUCT-GOAL-REBASELINE-01."""

from __future__ import annotations

from enum import StrEnum


class ReadinessLevel(StrEnum):
    """Ordered product readiness ladder; names are contract values."""

    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    CONTRACT_ONLY = "CONTRACT_ONLY"
    FOUNDATION_ONLY = "FOUNDATION_ONLY"
    PARTIAL = "PARTIAL"
    CAPABILITY_READY = "CAPABILITY_READY"
    MODE_READY = "MODE_READY"
    TRIAL_READY = "TRIAL_READY"
    PRODUCT_READY = "PRODUCT_READY"


READINESS_RANK: dict[ReadinessLevel, int] = {
    level: rank for rank, level in enumerate(ReadinessLevel)
}
