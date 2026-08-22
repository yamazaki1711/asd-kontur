"""Fail-closed workspace-to-platform Promotion Gate state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from .errors import KnowledgeError, KnowledgeErrorCode
from .rules import AuthorityIdentity


class PromotionState(StrEnum):
    OBSERVED = "observed"
    CANDIDATE = "candidate"
    ANONYMIZED = "anonymized"
    EVIDENCE_VERIFIED = "evidence_verified"
    APPLICABILITY_DEFINED = "applicability_defined"
    REGRESSION_TESTED = "regression_tested"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


@dataclass(frozen=True, slots=True)
class EvidenceCapsuleDraft:
    assertion: str
    evidence_summary: str
    applicability: str
    regression_digest: str
    source_class: str
    contains_reconstructive_content: bool = False
    workspace_reference: str | None = None
    filename: str | None = None
    confidence: float | None = None


class PromotionGate:
    _next: ClassVar[dict[PromotionState, frozenset[PromotionState]]] = {
        PromotionState.OBSERVED: frozenset({PromotionState.CANDIDATE}),
        PromotionState.CANDIDATE: frozenset({PromotionState.ANONYMIZED, PromotionState.REJECTED}),
        PromotionState.ANONYMIZED: frozenset(
            {PromotionState.EVIDENCE_VERIFIED, PromotionState.REJECTED}
        ),
        PromotionState.EVIDENCE_VERIFIED: frozenset(
            {PromotionState.APPLICABILITY_DEFINED, PromotionState.REJECTED}
        ),
        PromotionState.APPLICABILITY_DEFINED: frozenset(
            {PromotionState.REGRESSION_TESTED, PromotionState.REJECTED}
        ),
        PromotionState.REGRESSION_TESTED: frozenset(
            {PromotionState.APPROVED, PromotionState.REJECTED}
        ),
        PromotionState.APPROVED: frozenset({PromotionState.PUBLISHED}),
        PromotionState.REJECTED: frozenset(),
        PromotionState.PUBLISHED: frozenset(),
    }

    @classmethod
    def transition(
        cls,
        current: PromotionState,
        target: PromotionState,
        *,
        actor: AuthorityIdentity,
    ) -> PromotionState:
        if target not in cls._next[current]:
            raise KnowledgeError(
                KnowledgeErrorCode.INVALID_TRANSITION,
                f"Promotion transition {current} -> {target} is not allowed.",
            )
        if target in {PromotionState.APPROVED, PromotionState.PUBLISHED}:
            if not actor.is_human or "promotion.approve" not in actor.qualifications:
                raise KnowledgeError(
                    KnowledgeErrorCode.AUTHORITY_DENIED,
                    "Promotion approval and publication require qualified human authority.",
                )
        return target

    @staticmethod
    def publishable_capsule(draft: EvidenceCapsuleDraft) -> dict[str, str]:
        if (
            draft.contains_reconstructive_content
            or draft.workspace_reference is not None
            or draft.filename is not None
        ):
            raise KnowledgeError(
                KnowledgeErrorCode.PROMOTION_BLOCKED,
                "Evidence Capsule contains reconstructive workspace linkage or content.",
            )
        if not all(
            (
                draft.assertion,
                draft.evidence_summary,
                draft.applicability,
                draft.regression_digest,
                draft.source_class,
            )
        ):
            raise KnowledgeError(
                KnowledgeErrorCode.PROMOTION_BLOCKED,
                "Evidence, applicability, anonymization, and regression evidence are mandatory.",
            )
        # Confidence is intentionally excluded: it is neither authority nor promotion evidence.
        return {
            "applicability": draft.applicability,
            "assertion": draft.assertion,
            "evidence_summary": draft.evidence_summary,
            "regression_digest": draft.regression_digest,
            "source_class": draft.source_class,
        }
