"""Candidate-to-Fact authority gate; confidence is deliberately absent."""

from __future__ import annotations

from .errors import KernelError, KernelErrorCode
from .models import (
    Applicability,
    AuthorityKind,
    ConfirmationRequest,
    ConfirmationResult,
    DecisionOutcome,
    DeterministicAuthority,
    HumanAuthority,
)


class ConfirmationGate:
    """Evaluate the explicit human or deterministic authority path."""

    def confirm(self, request: ConfirmationRequest) -> ConfirmationResult:
        candidate = request.candidate
        if candidate.status != "validated_candidate" or not candidate.validation_passed:
            raise KernelError(
                KernelErrorCode.CANDIDATE_NOT_VALIDATED,
                "The exact CandidateVersion has not passed deterministic validation.",
            )
        if candidate.skipped_mandatory_validators:
            raise KernelError(
                KernelErrorCode.UNCERTAINTY_UNRESOLVED,
                "A mandatory validator was skipped.",
            )
        if not candidate.source_confirmed or not candidate.evidence:
            raise KernelError(
                KernelErrorCode.EVIDENCE_MISSING,
                "Exact admitted source and field evidence are required.",
            )
        if candidate.conflict_ids:
            raise KernelError(
                KernelErrorCode.CONFLICT_UNRESOLVED,
                "An unresolved conflict blocks confirmation.",
            )
        if candidate.uncertainty_ids:
            raise KernelError(
                KernelErrorCode.UNCERTAINTY_UNRESOLVED,
                "An unresolved uncertainty blocks confirmation.",
            )
        if request.policy.status != "active":
            raise KernelError(
                KernelErrorCode.AUTHORITY_DENIED, "Confirmation policy is not active."
            )

        if isinstance(request.authority, HumanAuthority):
            self._check_human(request)
            reason = "qualified_human_authority"
        else:
            self._check_rule(request)
            reason = "policy_controlled_deterministic_rule"
        return ConfirmationResult(
            DecisionOutcome.CONFIRMED,
            request.decision_id,
            request.fact_id,
            request.expected_fact_version + 1,
            reason,
        )

    @staticmethod
    def authority_kind(request: ConfirmationRequest) -> AuthorityKind:
        return (
            AuthorityKind.QUALIFIED_HUMAN
            if isinstance(request.authority, HumanAuthority)
            else AuthorityKind.DETERMINISTIC_RULE
        )

    @staticmethod
    def _check_human(request: ConfirmationRequest) -> None:
        authority = request.authority
        assert isinstance(authority, HumanAuthority)
        if (
            not authority.active
            or authority.capability != "fact.confirm"
            or request.fact_class not in authority.qualified_fact_classes
        ):
            raise KernelError(
                KernelErrorCode.AUTHORITY_DENIED,
                "The human grant does not authorize this fact class.",
            )
        if (
            request.fact_class in request.policy.professional_fact_classes
            and not authority.professional_qualification_ref
        ):
            raise KernelError(
                KernelErrorCode.PROFESSIONAL_AUTHORITY_REQUIRED,
                "The fact class requires an exact professional qualification reference.",
            )

    @staticmethod
    def _check_rule(request: ConfirmationRequest) -> None:
        authority = request.authority
        assert isinstance(authority, DeterministicAuthority)
        if request.fact_class in request.policy.professional_fact_classes:
            raise KernelError(
                KernelErrorCode.PROFESSIONAL_AUTHORITY_REQUIRED,
                "This fact class requires qualified human authority.",
            )
        if request.fact_class not in request.policy.auto_confirm_fact_classes:
            raise KernelError(
                KernelErrorCode.AUTO_CONFIRM_DENIED,
                "The policy does not permit deterministic auto-confirm for this fact class.",
            )
        if not authority.active_rule:
            raise KernelError(KernelErrorCode.RULE_NOT_ACTIVE, "RuleVersion is not active.")
        if not authority.member_of_pinned_rule_set:
            raise KernelError(
                KernelErrorCode.RULESET_NOT_PINNED,
                "RuleVersion is not a member of the pinned RuleSetVersion.",
            )
        if (
            authority.applicability is not Applicability.APPLICABLE
            or authority.rule_outcome != "pass"
        ):
            raise KernelError(
                KernelErrorCode.INDETERMINATE,
                "Rule applicability and outcome do not permit confirmation.",
            )
        if not authority.rule_trace_fingerprint.startswith("sha256:"):
            raise KernelError(KernelErrorCode.RULE_NOT_ACTIVE, "RuleTrace is incomplete.")
