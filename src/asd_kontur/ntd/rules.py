"""Evidence-bound normative rule candidates and deterministic qualification."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

import rfc8785

from asd_kontur.domain.identifiers import deterministic_uuid


class DeonticType(StrEnum):
    OBLIGATION = "obligation"
    PROHIBITION = "prohibition"
    PERMISSION = "permission"


class RuleQualificationStatus(StrEnum):
    QUALIFIED = "qualified"
    BLOCKED = "blocked"
    REJECTED = "rejected"


class RuleActivationStatus(StrEnum):
    ACTIVE = "active"
    NOT_ACTIVATED = "not_activated"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class SemanticEvidenceBinding:
    field: str
    source_quotes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.field
            or not self.source_quotes
            or any(not value for value in self.source_quotes)
        ):
            raise ValueError("A semantic field requires non-empty verbatim evidence")


@dataclass(frozen=True, slots=True)
class NormativeRuleCandidate:
    candidate_id: UUID
    version: int
    normative_document_id: UUID
    normative_edition_id: UUID
    source_version_id: UUID
    normative_provision_id: UUID
    normative_provision_version: int
    source_locator_id: UUID
    structural_path: str
    verbatim_text: str
    verbatim_digest: str
    deontic_type: DeonticType
    actor: dict[str, Any]
    regulated_object: dict[str, Any]
    required_action: dict[str, Any]
    applicability_predicate: dict[str, Any]
    conditions: tuple[dict[str, Any], ...]
    exceptions: tuple[dict[str, Any], ...]
    output_contract: dict[str, Any]
    evidence_bindings: tuple[SemanticEvidenceBinding, ...]
    interpretation_profile_version: str
    semantic_fingerprint: str

    def __post_init__(self) -> None:
        if self.version < 1 or self.normative_provision_version < 1:
            raise ValueError("Rule candidate versions must be positive")
        if not self.structural_path or not self.verbatim_text:
            raise ValueError("Rule candidate requires exact locator and verbatim evidence")
        if not self.verbatim_digest.startswith("sha256:"):
            raise ValueError("Rule candidate requires a verbatim digest")
        if (
            not self.interpretation_profile_version
            or self.interpretation_profile_version == "latest"
        ):
            raise ValueError("Rule candidate interpretation profile must be version-pinned")
        required = {"deontic_type", "actor", "regulated_object", "required_action"}
        bound = {item.field for item in self.evidence_bindings}
        if not required.issubset(bound):
            raise ValueError("Essential rule semantics must have field-level evidence")
        for binding in self.evidence_bindings:
            if any(quote not in self.verbatim_text for quote in binding.source_quotes):
                raise ValueError(f"Evidence for {binding.field} is absent from the verbatim source")

    @classmethod
    def create(
        cls,
        *,
        normative_document_id: UUID,
        normative_edition_id: UUID,
        source_version_id: UUID,
        normative_provision_id: UUID,
        normative_provision_version: int,
        source_locator_id: UUID,
        structural_path: str,
        verbatim_text: str,
        deontic_type: DeonticType,
        actor: dict[str, Any],
        regulated_object: dict[str, Any],
        required_action: dict[str, Any],
        applicability_predicate: dict[str, Any],
        conditions: tuple[dict[str, Any], ...] = (),
        exceptions: tuple[dict[str, Any], ...] = (),
        output_contract: dict[str, Any] | None = None,
        evidence_bindings: tuple[SemanticEvidenceBinding, ...],
        interpretation_profile_version: str,
    ) -> NormativeRuleCandidate:
        verbatim_digest = _digest(verbatim_text)
        payload = {
            "schema": "normative-rule-candidate-v1",
            "normative_document_id": str(normative_document_id),
            "normative_edition_id": str(normative_edition_id),
            "source_version_id": str(source_version_id),
            "normative_provision_id": str(normative_provision_id),
            "normative_provision_version": normative_provision_version,
            "source_locator_id": str(source_locator_id),
            "structural_path": structural_path,
            "verbatim_digest": verbatim_digest,
            "deontic_type": deontic_type.value,
            "actor": actor,
            "regulated_object": regulated_object,
            "required_action": required_action,
            "applicability_predicate": applicability_predicate,
            "conditions": conditions,
            "exceptions": exceptions,
            "output_contract": output_contract or {},
            "evidence_bindings": [
                {"field": item.field, "source_quotes": item.source_quotes}
                for item in sorted(evidence_bindings, key=lambda value: value.field)
            ],
            "interpretation_profile_version": interpretation_profile_version,
        }
        fingerprint = _digest(payload)
        return cls(
            deterministic_uuid(f"normative-rule-candidate:{fingerprint}"),
            1,
            normative_document_id,
            normative_edition_id,
            source_version_id,
            normative_provision_id,
            normative_provision_version,
            source_locator_id,
            structural_path,
            verbatim_text,
            verbatim_digest,
            deontic_type,
            actor,
            regulated_object,
            required_action,
            applicability_predicate,
            conditions,
            exceptions,
            output_contract or {},
            evidence_bindings,
            interpretation_profile_version,
            fingerprint,
        )


@dataclass(frozen=True, slots=True)
class RuleQualificationDecision:
    decision_id: UUID
    version: int
    candidate_id: UUID
    candidate_version: int
    status: RuleQualificationStatus
    gate_results: tuple[tuple[str, bool, str], ...]
    qualification_profile_version: str
    test_manifest_digest: str
    decision_fingerprint: str

    @property
    def qualified(self) -> bool:
        return self.status is RuleQualificationStatus.QUALIFIED


@dataclass(frozen=True, slots=True)
class RuleActivationDecision:
    decision_id: UUID
    version: int
    candidate_id: UUID
    candidate_version: int
    qualification_decision_id: UUID
    status: RuleActivationStatus
    reason_code: str
    edition_activation_status: str
    rule_lifecycle_status: str | None
    decision_fingerprint: str


def qualify_rule_candidate(
    candidate: NormativeRuleCandidate,
    *,
    provision_verification_status: str,
    evidence_edition_id: UUID,
    evidence_source_version_id: UUID,
    evidence_locator_id: UUID,
    evidence_verbatim_text: str,
    qualification_profile_version: str,
    test_manifest_digest: str,
) -> RuleQualificationDecision:
    """Apply deterministic provenance and semantic-evidence gates."""

    modal_quotes = {
        DeonticType.OBLIGATION: ("должен", "должны", "должна", "необходимо"),
        DeonticType.PROHIBITION: ("запрещается", "не допускается"),
        DeonticType.PERMISSION: ("допускается", "может"),
    }
    deontic_evidence = next(
        (item for item in candidate.evidence_bindings if item.field == "deontic_type"), None
    )
    checks = (
        (
            "verified_provision",
            provision_verification_status == "verified",
            provision_verification_status,
        ),
        (
            "exact_edition",
            candidate.normative_edition_id == evidence_edition_id,
            str(evidence_edition_id),
        ),
        (
            "exact_source_version",
            candidate.source_version_id == evidence_source_version_id,
            str(evidence_source_version_id),
        ),
        (
            "exact_locator",
            candidate.source_locator_id == evidence_locator_id,
            str(evidence_locator_id),
        ),
        (
            "verbatim_source",
            candidate.verbatim_text == evidence_verbatim_text,
            candidate.verbatim_digest,
        ),
        (
            "deontic_evidence",
            deontic_evidence is not None
            and any(
                anchor in quote.lower()
                for quote in deontic_evidence.source_quotes
                for anchor in modal_quotes[candidate.deontic_type]
            ),
            candidate.deontic_type.value,
        ),
        (
            "applicability_contract",
            _valid_predicate(candidate.applicability_predicate),
            "predicate-v1",
        ),
        ("test_manifest", test_manifest_digest.startswith("sha256:"), test_manifest_digest),
    )
    status = (
        RuleQualificationStatus.QUALIFIED
        if all(passed for _, passed, _ in checks)
        else RuleQualificationStatus.BLOCKED
    )
    payload = {
        "schema": "normative-rule-qualification-v1",
        "candidate_fingerprint": candidate.semantic_fingerprint,
        "gate_results": checks,
        "profile": qualification_profile_version,
        "status": status.value,
        "test_manifest_digest": test_manifest_digest,
    }
    fingerprint = _digest(payload)
    return RuleQualificationDecision(
        deterministic_uuid(f"normative-rule-qualification:{fingerprint}"),
        1,
        candidate.candidate_id,
        candidate.version,
        status,
        checks,
        qualification_profile_version,
        test_manifest_digest,
        fingerprint,
    )


def decide_rule_activation(
    candidate: NormativeRuleCandidate,
    qualification: RuleQualificationDecision,
    *,
    edition_activation_status: str,
    rule_lifecycle_status: str | None,
) -> RuleActivationDecision:
    if not qualification.qualified:
        status, reason = RuleActivationStatus.BLOCKED, "RULE_QUALIFICATION_NOT_PASSED"
    elif edition_activation_status != "active":
        status, reason = RuleActivationStatus.NOT_ACTIVATED, "NORMATIVE_EDITION_NOT_ACTIVATED"
    elif rule_lifecycle_status != "active":
        status, reason = RuleActivationStatus.NOT_ACTIVATED, "RULE_HUMAN_APPROVAL_NOT_ACTIVE"
    else:
        status, reason = RuleActivationStatus.ACTIVE, "QUALIFIED_RULE_AND_EDITION_ACTIVE"
    payload = {
        "schema": "normative-rule-activation-decision-v1",
        "candidate_fingerprint": candidate.semantic_fingerprint,
        "qualification_fingerprint": qualification.decision_fingerprint,
        "edition_activation_status": edition_activation_status,
        "rule_lifecycle_status": rule_lifecycle_status,
        "status": status.value,
        "reason": reason,
    }
    fingerprint = _digest(payload)
    return RuleActivationDecision(
        deterministic_uuid(f"normative-rule-activation:{fingerprint}"),
        1,
        candidate.candidate_id,
        candidate.version,
        qualification.decision_id,
        status,
        reason,
        edition_activation_status,
        rule_lifecycle_status,
        fingerprint,
    )


def _valid_predicate(value: dict[str, Any]) -> bool:
    if not value:
        return False
    operator = value.get("operator")
    return bool(value.get("field")) and operator in {"eq", "in", "exists", "gt", "gte", "lt", "lte"}


def _digest(value: Any) -> str:
    payload = value if isinstance(value, str) else rfc8785.dumps(value)
    encoded = payload.encode() if isinstance(payload, str) else payload
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
