"""Deterministic validation between the two Qwen semantic passes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from .models import (
    GuidanceCandidateVersion,
    GuidePageManifest,
    GuideValidationFailure,
)


class GuideFailureCode(StrEnum):
    SCHEMA_REQUIRED_FIELD_MISSING = "SCHEMA_REQUIRED_FIELD_MISSING"
    LOCATOR_INVALID = "LOCATOR_INVALID"
    LOCATOR_OUTSIDE_SCOPE = "LOCATOR_OUTSIDE_SCOPE"
    NATIVE_TEXT_MISMATCH = "NATIVE_TEXT_MISMATCH"
    FORM_FIELD_INCONSISTENT = "FORM_FIELD_INCONSISTENT"
    CROSS_PAGE_CONFLICT = "CROSS_PAGE_CONFLICT"
    DUPLICATE_GUIDANCE = "DUPLICATE_GUIDANCE"
    PROVIDER_RESULT_INTEGRITY_FAILED = "PROVIDER_RESULT_INTEGRITY_FAILED"
    CORRECTED_CANDIDATE_REQUIRES_REVALIDATION = "CORRECTED_CANDIDATE_REQUIRES_REVALIDATION"


@dataclass(frozen=True, slots=True)
class GuideValidationContext:
    source_version_id: UUID
    manifest: GuidePageManifest
    native_text: str
    allowed_page_numbers: tuple[int, ...]
    validator_version: str = "kg-id-guide-validator-v0.1.0"


def _failure(
    code: GuideFailureCode,
    candidate: GuidanceCandidateVersion,
    context: GuideValidationContext,
    field: str,
    *,
    repairable: bool,
    parameters: dict[str, object] | None = None,
) -> GuideValidationFailure:
    return GuideValidationFailure(
        failure_code=code,
        validator_version=context.validator_version,
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        field_path=field,
        blocking=True,
        repairable=repairable,
        parameters=parameters or {},
    )


def validate_candidate(
    candidate: GuidanceCandidateVersion,
    context: GuideValidationContext,
) -> tuple[GuideValidationFailure, ...]:
    failures: list[GuideValidationFailure] = []
    if candidate.source_version_id != context.source_version_id:
        failures.append(
            _failure(
                GuideFailureCode.PROVIDER_RESULT_INTEGRITY_FAILED,
                candidate,
                context,
                "source_version_id",
                repairable=False,
            )
        )
    if candidate.locator.page_number not in context.allowed_page_numbers:
        failures.append(
            _failure(
                GuideFailureCode.LOCATOR_OUTSIDE_SCOPE,
                candidate,
                context,
                "locator.page_number",
                repairable=False,
                parameters={"allowed_pages": context.allowed_page_numbers},
            )
        )
    if candidate.locator.page_number != context.manifest.page_number:
        failures.append(
            _failure(
                GuideFailureCode.LOCATOR_INVALID,
                candidate,
                context,
                "locator.page_number",
                repairable=True,
            )
        )
    required = {
        "section": candidate.section,
        "topic": candidate.topic,
        "instruction": candidate.instruction,
    }
    for field, value in required.items():
        if not value.strip():
            failures.append(
                _failure(
                    GuideFailureCode.SCHEMA_REQUIRED_FIELD_MISSING,
                    candidate,
                    context,
                    field,
                    repairable=True,
                )
            )
    grounded_terms = tuple(
        term.casefold()
        for term in candidate.instruction.split()
        if len(term) >= 6 and term.isalpha()
    )
    native = context.native_text.casefold()
    if context.manifest.native_text_characters >= 24 and grounded_terms:
        matches = sum(term in native for term in set(grounded_terms))
        if matches == 0:
            failures.append(
                _failure(
                    GuideFailureCode.NATIVE_TEXT_MISMATCH,
                    candidate,
                    context,
                    "instruction",
                    repairable=True,
                    parameters={"grounding_term_count": len(set(grounded_terms))},
                )
            )
    if candidate.field_or_element and not candidate.document_or_form_type:
        failures.append(
            _failure(
                GuideFailureCode.FORM_FIELD_INCONSISTENT,
                candidate,
                context,
                "document_or_form_type",
                repairable=True,
            )
        )
    return tuple(failures)


def detect_duplicate_candidates(
    candidates: tuple[GuidanceCandidateVersion, ...],
    *,
    validator_version: str = "kg-id-guide-dedup-v0.1.0",
) -> tuple[GuideValidationFailure, ...]:
    fingerprints: dict[tuple[object, ...], GuidanceCandidateVersion] = {}
    failures: list[GuideValidationFailure] = []
    for candidate in candidates:
        key = (
            candidate.kind,
            candidate.locator.key,
            candidate.instruction.casefold().strip(),
            candidate.document_or_form_type,
            candidate.field_or_element,
        )
        earlier = fingerprints.get(key)
        if earlier is None:
            fingerprints[key] = candidate
            continue
        failures.append(
            GuideValidationFailure(
                failure_code=GuideFailureCode.DUPLICATE_GUIDANCE,
                validator_version=validator_version,
                candidate_id=candidate.candidate_id,
                candidate_version=candidate.version,
                field_path="candidate",
                blocking=True,
                repairable=False,
                parameters={
                    "duplicate_of_candidate_id": str(earlier.candidate_id),
                    "duplicate_of_version": earlier.version,
                },
            )
        )
    return tuple(failures)
