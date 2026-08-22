"""Deterministic rule lifecycle and three-valued runtime."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar

import rfc8785

from .errors import KnowledgeError, KnowledgeErrorCode


class Applicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    INDETERMINATE = "indeterminate"


class RuleState(StrEnum):
    DRAFTED = "drafted"
    EVIDENCE_ATTACHED = "evidence_attached"
    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    SUPERSEDED = "superseded"
    RETIRED = "retired"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class AuthorityIdentity:
    identity_id: str
    identity_kind: str
    qualifications: frozenset[str] = frozenset()

    @property
    def is_human(self) -> bool:
        return self.identity_kind == "human"


@dataclass(frozen=True, slots=True)
class RuleVersionDefinition:
    rule_version_id: str
    rule_key: str
    predicate: dict[str, Any]
    output: dict[str, Any]
    evidence_ids: tuple[str, ...]
    conflict_policy_version: str
    effective_from: str | None
    effective_to: str | None

    def fingerprint(self) -> str:
        canonical = rfc8785.dumps(
            {
                "conflict_policy_version": self.conflict_policy_version,
                "effective_from": self.effective_from,
                "effective_to": self.effective_to,
                "evidence_ids": sorted(self.evidence_ids),
                "output": self.output,
                "predicate": self.predicate,
                "rule_key": self.rule_key,
                "rule_version_id": self.rule_version_id,
            }
        )
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


@dataclass(frozen=True, slots=True)
class RuleEvaluationResult:
    applicability: Applicability
    output: dict[str, Any] | None
    missing_inputs: tuple[str, ...]
    conflict: bool
    fingerprint: str


class RuleLifecycle:
    _transitions: ClassVar[dict[RuleState, frozenset[RuleState]]] = {
        RuleState.DRAFTED: frozenset({RuleState.EVIDENCE_ATTACHED, RuleState.REJECTED}),
        RuleState.EVIDENCE_ATTACHED: frozenset({RuleState.CANDIDATE, RuleState.REJECTED}),
        RuleState.CANDIDATE: frozenset({RuleState.REVIEWED, RuleState.REJECTED}),
        RuleState.REVIEWED: frozenset({RuleState.APPROVED, RuleState.REJECTED}),
        RuleState.APPROVED: frozenset({RuleState.ACTIVE, RuleState.REJECTED}),
        RuleState.ACTIVE: frozenset({RuleState.SUSPENDED, RuleState.SUPERSEDED, RuleState.RETIRED}),
        RuleState.SUSPENDED: frozenset({RuleState.ACTIVE, RuleState.RETIRED}),
        RuleState.SUPERSEDED: frozenset(),
        RuleState.RETIRED: frozenset(),
        RuleState.REJECTED: frozenset(),
    }

    @classmethod
    def transition(
        cls,
        current: RuleState,
        target: RuleState,
        *,
        actor: AuthorityIdentity,
        author_identity_id: str,
        reviewer_identity_id: str | None = None,
    ) -> RuleState:
        if target not in cls._transitions[current]:
            raise KnowledgeError(
                KnowledgeErrorCode.INVALID_TRANSITION,
                f"Rule transition {current} -> {target} is not allowed.",
            )
        if target in {RuleState.REVIEWED, RuleState.APPROVED, RuleState.ACTIVE}:
            if not actor.is_human:
                raise KnowledgeError(
                    KnowledgeErrorCode.AUTHORITY_DENIED,
                    "A model or service identity cannot review, approve, or activate a rule.",
                )
        if target == RuleState.REVIEWED and actor.identity_id == author_identity_id:
            raise KnowledgeError(
                KnowledgeErrorCode.AUTHORITY_DENIED,
                "Rule review must be independent from authorship.",
            )
        if target == RuleState.APPROVED:
            if reviewer_identity_id in {None, author_identity_id, actor.identity_id}:
                raise KnowledgeError(
                    KnowledgeErrorCode.AUTHORITY_DENIED,
                    "Author, independent reviewer, and approver must be distinct.",
                )
            if "rule.approve" not in actor.qualifications:
                raise KnowledgeError(
                    KnowledgeErrorCode.AUTHORITY_DENIED,
                    "Approver lacks the required rule class qualification.",
                )
        return target


class DeclarativeRuleRuntime:
    """Evaluate a deliberately small, deterministic predicate language."""

    def evaluate(
        self,
        definition: RuleVersionDefinition,
        *,
        state: RuleState,
        pinned_rule_version_ids: frozenset[str],
        inputs: dict[str, Any],
        policy_versions: tuple[str, ...],
        rule_set_version: str,
    ) -> RuleEvaluationResult:
        if state is not RuleState.ACTIVE:
            raise KnowledgeError(
                KnowledgeErrorCode.RULE_NOT_ACTIVE,
                "Only an active RuleVersion can influence a result.",
            )
        if (
            definition.rule_version_id not in pinned_rule_version_ids
            or rule_set_version == "latest"
        ):
            raise KnowledgeError(
                KnowledgeErrorCode.RULE_SET_NOT_PINNED,
                "The exact RuleVersion must belong to an exact pinned RuleSetVersion.",
            )
        applicability, missing, conflict = self._predicate(definition.predicate, inputs)
        result_output = definition.output if applicability is Applicability.APPLICABLE else None
        canonical = rfc8785.dumps(
            {
                "applicability": applicability,
                "conflict": conflict,
                "inputs": inputs,
                "missing_inputs": missing,
                "output": result_output,
                "policy_versions": sorted(policy_versions),
                "rule_fingerprint": definition.fingerprint(),
                "rule_set_version": rule_set_version,
            }
        )
        return RuleEvaluationResult(
            applicability,
            result_output,
            tuple(missing),
            conflict,
            f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        )

    def _predicate(
        self, predicate: dict[str, Any], inputs: dict[str, Any]
    ) -> tuple[Applicability, list[str], bool]:
        field = predicate.get("field")
        operator = predicate.get("operator")
        if not isinstance(field, str) or operator not in {"eq", "in", "exists"}:
            return Applicability.INDETERMINATE, [], True
        if field not in inputs:
            return Applicability.INDETERMINATE, [field], False
        actual = inputs[field]
        if operator == "exists":
            matched = actual is not None
        elif operator == "eq":
            matched = actual == predicate.get("value")
        else:
            expected = predicate.get("values")
            if not isinstance(expected, list):
                return Applicability.INDETERMINATE, [], True
            matched = actual in expected
        return (
            Applicability.APPLICABLE if matched else Applicability.NOT_APPLICABLE,
            [],
            False,
        )
