from __future__ import annotations

import pytest

from asd_kontur.knowledge import AuthorityIdentity, KnowledgeError, PromotionGate, PromotionState
from asd_kontur.knowledge.promotion import EvidenceCapsuleDraft


def test_positive_promotion_path_requires_qualified_human() -> None:
    human = AuthorityIdentity("qualified-human", "human", frozenset({"promotion.approve"}))
    state = PromotionState.OBSERVED
    for target in (
        PromotionState.CANDIDATE,
        PromotionState.ANONYMIZED,
        PromotionState.EVIDENCE_VERIFIED,
        PromotionState.APPLICABILITY_DEFINED,
        PromotionState.REGRESSION_TESTED,
        PromotionState.APPROVED,
        PromotionState.PUBLISHED,
    ):
        state = PromotionGate.transition(state, target, actor=human)
    assert state is PromotionState.PUBLISHED


def test_model_and_confidence_cannot_publish() -> None:
    with pytest.raises(KnowledgeError):
        PromotionGate.transition(
            PromotionState.REGRESSION_TESTED,
            PromotionState.APPROVED,
            actor=AuthorityIdentity("model", "model", frozenset({"promotion.approve"})),
        )
    capsule = PromotionGate.publishable_capsule(
        EvidenceCapsuleDraft(
            "synthetic assertion",
            "synthetic evidence summary",
            "synthetic applicability",
            "sha256:" + "a" * 64,
            "synthetic-source-class",
            confidence=1.0,
        )
    )
    assert "confidence" not in capsule


@pytest.mark.parametrize("field", ["workspace_reference", "filename"])
def test_capsule_rejects_reconstructive_linkage(field: str) -> None:
    values = {
        "assertion": "synthetic assertion",
        "evidence_summary": "synthetic evidence",
        "applicability": "synthetic applicability",
        "regression_digest": "sha256:" + "a" * 64,
        "source_class": "synthetic",
        field: "forbidden",
    }
    with pytest.raises(KnowledgeError):
        PromotionGate.publishable_capsule(EvidenceCapsuleDraft(**values))
