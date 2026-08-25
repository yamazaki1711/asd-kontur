"""Semantic validation for the additive Product Capability Contract Pack."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .models import READINESS_RANK, ReadinessLevel

JsonObject = dict[str, Any]
_PLACEHOLDER_EVIDENCE = frozenset({"none", "unproven", "not_run", "not run"})
_NEGATIVE_EVIDENCE_MARKERS = ("no ", "not implemented", "absent", "unproven")


class CapabilityRegistryError(ValueError):
    """Raised when a product readiness claim is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class RegistryValidationResult:
    capability_count: int
    plane_count: int
    readiness_counts: dict[str, int]
    blocking_capability_ids: tuple[str, ...]


def _load_json(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CapabilityRegistryError(f"JSON root must be an object: {path}")
    return value


def _has_substantive_evidence(values: object) -> bool:
    if not isinstance(values, list) or not values:
        return False
    normalized = {str(value).strip().casefold() for value in values}
    if not normalized or normalized.issubset(_PLACEHOLDER_EVIDENCE):
        return False
    return any(
        not any(marker in value for marker in _NEGATIVE_EVIDENCE_MARKERS) for value in normalized
    )


def load_capability_registry(root: Path) -> JsonObject:
    """Load and schema-validate a v2.0 capability registry fixture."""

    registry = _load_json(root / "fixtures" / "valid" / "product-capability-registry.json")
    schema = _load_json(root / "schemas" / "product-readiness.schema.json")
    issues = sorted(Draft202012Validator(schema).iter_errors(registry), key=str)
    if issues:
        detail = "; ".join(issue.message for issue in issues[:5])
        raise CapabilityRegistryError(f"capability registry schema invalid: {detail}")
    return registry


def validate_capability_registry(
    registry: JsonObject,
    *,
    required_capability_ids: frozenset[str],
    required_planes: frozenset[str],
) -> RegistryValidationResult:
    """Validate the complete denominator and all readiness claims fail closed."""

    capabilities = registry.get("capabilities")
    if not isinstance(capabilities, list):
        raise CapabilityRegistryError("capabilities must be an array")
    ids = [str(item.get("capability_id")) for item in capabilities]
    if len(ids) != len(set(ids)):
        raise CapabilityRegistryError("duplicate capability identity")
    missing = sorted(required_capability_ids - set(ids))
    if missing:
        raise CapabilityRegistryError(f"mandatory capabilities missing: {', '.join(missing)}")
    unexpected = sorted(set(ids) - required_capability_ids)
    if unexpected:
        raise CapabilityRegistryError(
            f"capabilities absent from denominator: {', '.join(unexpected)}"
        )
    planes = {str(item.get("plane")) for item in capabilities}
    missing_planes = sorted(required_planes - planes)
    if missing_planes:
        raise CapabilityRegistryError(f"mandatory planes missing: {', '.join(missing_planes)}")

    by_id = {str(item["capability_id"]): item for item in capabilities}
    dependency_edges: set[tuple[str, str]] = set()
    for item in capabilities:
        for dependency in item["dependencies"]:
            if dependency not in by_id:
                raise CapabilityRegistryError(
                    f"{item['capability_id']} has unknown dependency {dependency}"
                )
            dependency_edges.add((str(item["capability_id"]), str(dependency)))
        level = ReadinessLevel(item["current_readiness"])
        if READINESS_RANK[level] >= READINESS_RANK[ReadinessLevel.CAPABILITY_READY]:
            if not _has_substantive_evidence(
                item["user_facing_surface"]
            ) or not _has_substantive_evidence(item["implementation_evidence"]):
                raise CapabilityRegistryError(
                    f"{item['capability_id']} claims capability readiness without surface/evidence"
                )
            if not _has_substantive_evidence(
                item["test_evidence"]
            ) or not _has_substantive_evidence(item["acceptance_criteria"]):
                raise CapabilityRegistryError(
                    f"{item['capability_id']} claims capability readiness without E2E acceptance"
                )

    dependency_projection = registry["capability_dependencies"]
    if dependency_projection["edge_count"] != len(dependency_edges):
        raise CapabilityRegistryError("CapabilityDependency edge denominator mismatch")

    surface_ids: set[str] = set()
    for surface in registry["interaction_surfaces"]:
        surface_id = str(surface["surface_id"])
        if surface_id in surface_ids:
            raise CapabilityRegistryError("duplicate ProductInteractionSurface identity")
        surface_ids.add(surface_id)
        for capability_id in surface["capability_ids"]:
            if capability_id not in by_id:
                raise CapabilityRegistryError(
                    f"{surface_id} references unknown capability {capability_id}"
                )

    scale_profiles = registry["scale_qualification_profiles"]
    expected_scales = {
        "intake.scale-1k": 1000,
        "intake.scale-5k": 5000,
        "intake.scale-10k": 10000,
    }
    observed_scales = {
        str(profile["profile_id"]): int(profile["file_count"]) for profile in scale_profiles
    }
    if observed_scales != expected_scales:
        raise CapabilityRegistryError("ScaleQualificationProfile denominator mismatch")

    decisions = registry["readiness_decisions"]
    mode_decisions = decisions["modes"]
    for mode in ("Tender", "Support", "Audit", "Restoration"):
        decision = mode_decisions[mode]
        if decision["ready"] and (
            not _has_substantive_evidence(decision["e2e_evidence"])
            or not _has_substantive_evidence(decision["output_evidence"])
        ):
            raise CapabilityRegistryError(f"{mode} MODE_READY lacks user E2E/output evidence")

    trial = decisions["trial"]
    trial_blockers = tuple(
        sorted(
            item["capability_id"]
            for item in capabilities
            if item["required_for_trial"]
            and READINESS_RANK[ReadinessLevel(item["current_readiness"])]
            < READINESS_RANK[ReadinessLevel.CAPABILITY_READY]
        )
    )
    if trial["ready"]:
        if trial_blockers:
            raise CapabilityRegistryError("TRIAL_READY has non-ready mandatory capabilities")
        if not trial["decision_id"] or not _has_substantive_evidence(
            trial["scale_qualification_evidence"]
        ):
            raise CapabilityRegistryError("TRIAL_READY lacks decision or scale evidence")

    if decisions["oks_ready"] and not trial["ready"]:
        raise CapabilityRegistryError("OKSReady requires TrialReadinessDecision")
    admission = decisions["real_oks_admission"]
    if (admission["proposed"] or admission["allowed"]) and (
        not trial["ready"]
        or not trial["decision_id"]
        or admission["trial_decision_id"] != trial["decision_id"]
    ):
        raise CapabilityRegistryError("real OKS admission requires exact TrialReadinessDecision")
    product = decisions["product"]
    if product["ready"]:
        if not all(mode_decisions[mode]["ready"] for mode in mode_decisions):
            raise CapabilityRegistryError("PRODUCT_READY requires four MODE_READY decisions")
        if not all(product["product_result_evidence"]):
            raise CapabilityRegistryError("PRODUCT_READY requires all three product results")

    for claim in registry["claims"]:
        if claim["outcome"] == "PASS" and (
            claim["denominator"] <= 0 or not _has_substantive_evidence(claim["evidence_refs"])
        ):
            raise CapabilityRegistryError("PASS requires exact denominator and evidence")

    readiness_counts: dict[str, int] = {level.value: 0 for level in ReadinessLevel}
    for item in capabilities:
        readiness_counts[str(item["current_readiness"])] += 1
    return RegistryValidationResult(
        capability_count=len(capabilities),
        plane_count=len(planes),
        readiness_counts=readiness_counts,
        blocking_capability_ids=trial_blockers,
    )
