from __future__ import annotations

from dataclasses import replace

import pytest

from asd_kontur.knowledge import (
    Applicability,
    AuthorityIdentity,
    DeclarativeRuleRuntime,
    KnowledgeError,
    KnowledgeErrorCode,
    RuleLifecycle,
    RuleVersionDefinition,
)
from asd_kontur.knowledge.rules import RuleState


def definition() -> RuleVersionDefinition:
    return RuleVersionDefinition(
        "rule-version:synthetic:1",
        "synthetic.required-evidence",
        {"field": "work_class", "operator": "eq", "value": "synthetic-a"},
        {"required": True},
        ("evidence:synthetic:1",),
        "conflict-policy:synthetic:1",
        None,
        None,
    )


def test_three_valued_runtime_is_deterministic_and_pinned() -> None:
    runtime = DeclarativeRuleRuntime()
    rule = definition()
    kwargs = {
        "state": RuleState.ACTIVE,
        "pinned_rule_version_ids": frozenset({rule.rule_version_id}),
        "policy_versions": ("policy:synthetic:1",),
        "rule_set_version": "rule-set:synthetic:1",
    }
    first = runtime.evaluate(rule, inputs={"work_class": "synthetic-a"}, **kwargs)
    second = runtime.evaluate(rule, inputs={"work_class": "synthetic-a"}, **kwargs)
    negative = runtime.evaluate(rule, inputs={"work_class": "synthetic-b"}, **kwargs)
    unknown = runtime.evaluate(rule, inputs={}, **kwargs)
    assert first.applicability is Applicability.APPLICABLE
    assert first.fingerprint == second.fingerprint
    assert negative.applicability is Applicability.NOT_APPLICABLE
    assert unknown.applicability is Applicability.INDETERMINATE
    assert unknown.missing_inputs == ("work_class",)


def test_rule_fingerprint_changes_for_material_change() -> None:
    rule = definition()
    changed = replace(rule, output={"required": False})
    assert rule.fingerprint() != changed.fingerprint()


def test_inactive_or_rolling_rule_is_denied() -> None:
    runtime = DeclarativeRuleRuntime()
    rule = definition()
    with pytest.raises(KnowledgeError) as inactive:
        runtime.evaluate(
            rule,
            state=RuleState.APPROVED,
            pinned_rule_version_ids=frozenset({rule.rule_version_id}),
            inputs={},
            policy_versions=(),
            rule_set_version="rule-set:synthetic:1",
        )
    assert inactive.value.code is KnowledgeErrorCode.RULE_NOT_ACTIVE
    with pytest.raises(KnowledgeError) as latest:
        runtime.evaluate(
            rule,
            state=RuleState.ACTIVE,
            pinned_rule_version_ids=frozenset({rule.rule_version_id}),
            inputs={},
            policy_versions=(),
            rule_set_version="latest",
        )
    assert latest.value.code is KnowledgeErrorCode.RULE_SET_NOT_PINNED


def test_author_reviewer_approver_separation_and_model_denial() -> None:
    human_reviewer = AuthorityIdentity("reviewer", "human")
    assert (
        RuleLifecycle.transition(
            RuleState.CANDIDATE,
            RuleState.REVIEWED,
            actor=human_reviewer,
            author_identity_id="author",
        )
        is RuleState.REVIEWED
    )
    with pytest.raises(KnowledgeError):
        RuleLifecycle.transition(
            RuleState.CANDIDATE,
            RuleState.REVIEWED,
            actor=AuthorityIdentity("model", "model"),
            author_identity_id="author",
        )
    with pytest.raises(KnowledgeError):
        RuleLifecycle.transition(
            RuleState.REVIEWED,
            RuleState.APPROVED,
            actor=AuthorityIdentity("reviewer", "human", frozenset({"rule.approve"})),
            author_identity_id="author",
            reviewer_identity_id="reviewer",
        )
    assert (
        RuleLifecycle.transition(
            RuleState.REVIEWED,
            RuleState.APPROVED,
            actor=AuthorityIdentity("approver", "human", frozenset({"rule.approve"})),
            author_identity_id="author",
            reviewer_identity_id="reviewer",
        )
        is RuleState.APPROVED
    )
