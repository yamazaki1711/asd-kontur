"""Cross-record invariants represented by semantic-invalid fixtures."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .errors import ContractErrorCode, ValidationIssue

SemanticValidator = Callable[[Mapping[str, Any]], ValidationIssue | None]


def _issue(code: ContractErrorCode, message: str, invariant: str) -> ValidationIssue:
    return ValidationIssue(code, message, invariant=invariant, validation_layer="semantic")


def candidate_fact_authority(data: Mapping[str, Any]) -> ValidationIssue | None:
    fact = data["proposed_fact"]
    if fact.get("confirmation_decision_ref") is None or fact.get("authority_reference") is None:
        return _issue(
            ContractErrorCode.CANDIDATE_INVALID,
            "confidence cannot replace confirmation authority",
            "CANDIDATE_FACT_AUTHORITY",
        )
    return None


def same_workspace(data: Mapping[str, Any]) -> ValidationIssue | None:
    if data["operation_workspace_id"] != data["evidence_reference"].get("workspace_id"):
        return _issue(
            ContractErrorCode.WORKSPACE_MISMATCH,
            "evidence belongs to another workspace",
            "SCOPE_SAME_WORKSPACE",
        )
    return None


def digest_not_capability(data: Mapping[str, Any]) -> ValidationIssue | None:
    missing = set(data["missing"])
    required = {"object_id", "object_version", "workspace_id", "access_capability_ref"}
    if required <= missing:
        return _issue(
            ContractErrorCode.AUTH_UNAUTHORIZED,
            "digest does not grant object access",
            "DIGEST_NOT_CAPABILITY",
        )
    return None


def egress_default_deny(data: Mapping[str, Any]) -> ValidationIssue | None:
    if any(item["status"] in {"unset", "blocked"} for item in data["policy_instances"]):
        return _issue(
            ContractErrorCode.POLICY_BLOCKED,
            "external egress policy is not active",
            "EGRESS_DEFAULT_DENY",
        )
    return None


def document_finalization_gate(data: Mapping[str, Any]) -> ValidationIssue | None:
    if (
        data.get("print_validation_ref") is None
        or data.get("professional_review_decision_ref") is None
    ):
        return _issue(
            ContractErrorCode.RENDER_PRINT_FAILURE,
            "print validation and professional review are required",
            "DOCUMENT_FINALIZATION_GATE",
        )
    return None


def geometry_confirmed_source(data: Mapping[str, Any]) -> ValidationIssue | None:
    geometry = data["geometry"]
    if any(
        geometry.get(key) is None
        for key in ("crs_ref", "unit_profile_ref", "confirmed_observation_ref")
    ):
        return _issue(
            ContractErrorCode.GEOMETRY_BLOCKED,
            "VLM confidence is not confirmed geometry evidence",
            "GEOMETRY_CONFIRMED_SOURCE",
        )
    return None


def exact_version_pin(data: Mapping[str, Any]) -> ValidationIssue | None:
    if data["contract_reference"]["version"] == "latest":
        return _issue(
            ContractErrorCode.INCOMPATIBLE_VERSION,
            "mutable latest is forbidden",
            "EXACT_VERSION_PIN",
        )
    return None


def reset_requires_attestation(data: Mapping[str, Any]) -> ValidationIssue | None:
    if (
        data.get("destruction_attestation_ref") is None
        or not data.get("adapter_receipts")
        or not data.get("residual_scan_refs")
    ):
        return _issue(
            ContractErrorCode.RESET_INCOMPLETE,
            "verified reset requires attestation, receipts and residual scans",
            "RESET_REQUIRES_ATTESTATION",
        )
    return None


SEMANTIC_VALIDATORS: dict[str, SemanticValidator] = {
    "CANDIDATE_FACT_AUTHORITY": candidate_fact_authority,
    "SCOPE_SAME_WORKSPACE": same_workspace,
    "DIGEST_NOT_CAPABILITY": digest_not_capability,
    "EGRESS_DEFAULT_DENY": egress_default_deny,
    "DOCUMENT_FINALIZATION_GATE": document_finalization_gate,
    "GEOMETRY_CONFIRMED_SOURCE": geometry_confirmed_source,
    "EXACT_VERSION_PIN": exact_version_pin,
    "RESET_REQUIRES_ATTESTATION": reset_requires_attestation,
}


def validate_semantic(invariant: str, payload: Mapping[str, Any]) -> ValidationIssue | None:
    try:
        validator = SEMANTIC_VALIDATORS[invariant]
    except KeyError as exc:
        raise ValueError(f"unknown semantic invariant: {invariant}") from exc
    return validator(payload)
