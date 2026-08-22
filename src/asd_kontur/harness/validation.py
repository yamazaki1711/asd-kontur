"""Deterministic validator registry; confidence is deliberately ignored."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .models import CandidateVersion, Locator, Repairability, ValidationFailure

Validator = Callable[[CandidateVersion, "ValidationContext"], tuple[ValidationFailure, ...]]

VALIDATION_FAILURE_CODES = frozenset(
    {
        "SCHEMA_REQUIRED_FIELD_MISSING",
        "TYPE_MISMATCH",
        "UNIT_MISSING",
        "UNIT_INCOMPATIBLE",
        "OUT_OF_RANGE",
        "PURPOSE_FIELD_MISSING",
        "LOCATOR_INVALID",
        "LOCATOR_OUTSIDE_SCOPE",
        "DUPLICATE_CONFLICT",
        "CROSS_FIELD_INCONSISTENT",
        "CROSS_PAGE_CONFLICT",
        "EDITION_UNAVAILABLE",
        "NATIVE_TEXT_MISMATCH",
        "GEOMETRY_INPUT_UNCONFIRMED",
        "LEGAL_LOCATOR_UNVERIFIED",
        "DOMAIN_RULE_FAILED",
        "PROVIDER_RESULT_INTEGRITY_FAILED",
        "SOURCE_STALE",
    }
)


@dataclass(frozen=True, slots=True)
class ValidationContext:
    authorized_locator_ids: frozenset[str]
    required_fields: frozenset[str]
    required_units: frozenset[str]
    confirmed_geometry_sources: frozenset[str]
    verified_legal_locators: frozenset[str]
    source_current: bool = True


@dataclass(frozen=True, slots=True)
class ValidationResult:
    status: str
    failures: tuple[ValidationFailure, ...]
    skipped_mandatory: tuple[str, ...] = ()


class ValidatorRegistry:
    def __init__(self) -> None:
        self._validators: dict[tuple[str, str], Validator] = {}

    def register(self, key: str, version: str, validator: Validator) -> None:
        identity = (key, version)
        if identity in self._validators or version.lower() == "latest":
            raise ValueError("validator identity must be unique and exact")
        self._validators[identity] = validator

    def validate(
        self,
        candidate: CandidateVersion,
        context: ValidationContext,
        required: tuple[tuple[str, str], ...],
    ) -> ValidationResult:
        failures: list[ValidationFailure] = []
        skipped: list[str] = []
        for identity in required:
            validator = self._validators.get(identity)
            if validator is None:
                skipped.append(f"{identity[0]}@{identity[1]}")
                continue
            failures.extend(validator(candidate, context))
        if skipped:
            return ValidationResult("indeterminate", tuple(failures), tuple(skipped))
        return ValidationResult(
            "failed" if any(item.blocking for item in failures) else "passed", tuple(failures)
        )


def common_validator(
    candidate: CandidateVersion, context: ValidationContext
) -> tuple[ValidationFailure, ...]:
    failures: list[ValidationFailure] = []
    found = {item.field_path for item in candidate.fields}
    for missing in sorted(context.required_fields - found):
        failures.append(
            _failure("SCHEMA_REQUIRED_FIELD_MISSING", missing, (), Repairability.TARGETED_REPAIR)
        )
    for item in candidate.fields:
        locators = tuple(item.source_locators)
        if not locators:
            failures.append(
                _failure("LOCATOR_INVALID", item.field_path, (), Repairability.TARGETED_REPAIR)
            )
        elif any(
            str(locator.locator_id) not in context.authorized_locator_ids for locator in locators
        ):
            failures.append(
                _failure(
                    "LOCATOR_OUTSIDE_SCOPE", item.field_path, locators, Repairability.NOT_REPAIRABLE
                )
            )
        if item.field_path in context.required_units and not item.unit:
            failures.append(
                _failure("UNIT_MISSING", item.field_path, locators, Repairability.TARGETED_REPAIR)
            )
    if not context.source_current:
        failures.append(_failure("SOURCE_STALE", "/", (), Repairability.NOT_REPAIRABLE))
    return tuple(failures)


def legal_validator(
    candidate: CandidateVersion, context: ValidationContext
) -> tuple[ValidationFailure, ...]:
    failures: list[ValidationFailure] = []
    for item in candidate.fields:
        if item.field_path.startswith("/legal/") and not any(
            str(locator.locator_id) in context.verified_legal_locators
            for locator in item.source_locators
        ):
            failures.append(
                _failure(
                    "LEGAL_LOCATOR_UNVERIFIED",
                    item.field_path,
                    item.source_locators,
                    Repairability.HUMAN_REQUIRED,
                )
            )
    return tuple(failures)


def geometry_validator(
    candidate: CandidateVersion, context: ValidationContext
) -> tuple[ValidationFailure, ...]:
    by_path = {item.field_path: item for item in candidate.fields}
    required = {"/geometry/source", "/geometry/crs", "/geometry/units", "/geometry/precision"}
    failures: list[ValidationFailure] = []
    for missing in sorted(required - by_path.keys()):
        failures.append(
            _failure("GEOMETRY_INPUT_UNCONFIRMED", missing, (), Repairability.HUMAN_REQUIRED)
        )
    source = by_path.get("/geometry/source")
    if source is not None and str(source.value) not in context.confirmed_geometry_sources:
        failures.append(
            _failure(
                "GEOMETRY_INPUT_UNCONFIRMED",
                source.field_path,
                source.source_locators,
                Repairability.HUMAN_REQUIRED,
            )
        )
    return tuple(failures)


def _failure(
    code: str, path: str, locators: tuple[Locator, ...], repairability: Repairability
) -> ValidationFailure:
    if code not in VALIDATION_FAILURE_CODES:
        raise ValueError(f"unregistered validation failure code: {code}")
    return ValidationFailure(
        code,
        "validator.g07.deterministic",
        "1.0.0",
        path,
        "blocker",
        locators,
        (),
        repairability,
        True,
    )
