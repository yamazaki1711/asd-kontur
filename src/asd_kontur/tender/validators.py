"""Versioned deterministic checks for WP-12 Tender inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from asd_kontur.harness.models import digest_of
from asd_kontur.kernel import Applicability

from .models import RiskSubject, Severity, TenderIssueKind


class TenderValidationCode(StrEnum):
    REQUIRED_SECTION_MISSING = "TENDER_REQUIRED_SECTION_MISSING"
    CLAUSE_CONFLICT = "TENDER_CLAUSE_CONFLICT"
    TERM_AMBIGUOUS = "TENDER_TERM_AMBIGUOUS"
    NTD_EDITION_AMBIGUOUS = "TENDER_NTD_EDITION_AMBIGUOUS"
    CUSTOMER_REGULATION_NTD_CONFLICT = "TENDER_CUSTOMER_REGULATION_NTD_CONFLICT"
    RESPONSIBILITY_UNALLOCATED = "TENDER_RESPONSIBILITY_UNALLOCATED"
    DEADLINE_UNDEFINED = "TENDER_DEADLINE_UNDEFINED"
    ACCEPTANCE_BASIS_UNDEFINED = "TENDER_ACCEPTANCE_BASIS_UNDEFINED"
    PAYMENT_BASIS_UNDEFINED = "TENDER_PAYMENT_BASIS_UNDEFINED"
    VOLUME_UNCONFIRMED = "TENDER_VOLUME_UNCONFIRMED"
    COST_UNCONFIRMED = "TENDER_COST_UNCONFIRMED"
    WORK_OMITTED = "TENDER_WORK_OMITTED"
    MATERIAL_OMITTED = "TENDER_MATERIAL_OMITTED"
    GEOMETRY_INSUFFICIENT = "TENDER_GEOMETRY_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class TenderValidationInput:
    validator_profile_version: str
    required_sections: tuple[str, ...]
    present_sections: tuple[str, ...]
    contradictory_clause_pairs: tuple[tuple[str, str], ...] = ()
    ambiguous_terms: tuple[str, ...] = ()
    normative_reference_present: bool = False
    normative_edition_resolved: bool = True
    customer_regulation_conflicts_ntd: bool = False
    responsibility_allocated: bool = True
    deadline_defined: bool = True
    acceptance_basis_defined: bool = True
    payment_basis_defined: bool = True
    volume_confirmed: bool = True
    cost_confirmed: bool = True
    omitted_work_ids: tuple[str, ...] = ()
    omitted_material_ids: tuple[str, ...] = ()
    geometry_relevant: bool = False
    geometry_source_confirmed: bool = True
    crs_known: bool = True
    units_known: bool = True

    def __post_init__(self) -> None:
        if not self.validator_profile_version or self.validator_profile_version.lower() == "latest":
            raise ValueError("Tender validators require an exact profile version")


@dataclass(frozen=True, slots=True)
class TenderValidationFailure:
    code: TenderValidationCode
    validator_version: str
    kind: TenderIssueKind
    subject: RiskSubject
    severity: Severity
    applicability: Applicability
    required_inputs: tuple[str, ...]
    blocker: bool
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "validator_version": self.validator_version,
            "kind": self.kind,
            "subject": self.subject,
            "severity": self.severity,
            "applicability": self.applicability,
            "required_inputs": self.required_inputs,
            "blocker": self.blocker,
        }


def validate_tender(value: TenderValidationInput) -> tuple[TenderValidationFailure, ...]:
    """Return explicit failures; an empty tuple means only that these checks passed."""

    failures: list[TenderValidationFailure] = []

    def add(
        code: TenderValidationCode,
        kind: TenderIssueKind,
        subject: RiskSubject,
        required_inputs: tuple[str, ...],
        *,
        blocker: bool,
        applicability: Applicability = Applicability.INDETERMINATE,
    ) -> None:
        failures.append(
            TenderValidationFailure(
                code,
                value.validator_profile_version,
                kind,
                subject,
                Severity.BLOCKING if blocker else Severity.HIGH,
                applicability,
                required_inputs,
                blocker,
            )
        )

    missing_sections = tuple(
        sorted(set(value.required_sections).difference(value.present_sections))
    )
    if missing_sections:
        add(
            TenderValidationCode.REQUIRED_SECTION_MISSING,
            TenderIssueKind.GAP,
            RiskSubject.SOURCE_COMPLETENESS,
            missing_sections,
            blocker=True,
        )
    if value.contradictory_clause_pairs:
        add(
            TenderValidationCode.CLAUSE_CONFLICT,
            TenderIssueKind.CONFLICT,
            RiskSubject.TECHNICAL_REQUIREMENT,
            tuple(f"{left}|{right}" for left, right in value.contradictory_clause_pairs),
            blocker=True,
        )
    if value.ambiguous_terms:
        add(
            TenderValidationCode.TERM_AMBIGUOUS,
            TenderIssueKind.UNCERTAINTY,
            RiskSubject.TECHNICAL_REQUIREMENT,
            value.ambiguous_terms,
            blocker=False,
        )
    if value.normative_reference_present and not value.normative_edition_resolved:
        add(
            TenderValidationCode.NTD_EDITION_AMBIGUOUS,
            TenderIssueKind.BLOCKER,
            RiskSubject.TECHNICAL_REQUIREMENT,
            ("normative_edition", "effective_date"),
            blocker=True,
        )
    if value.customer_regulation_conflicts_ntd:
        add(
            TenderValidationCode.CUSTOMER_REGULATION_NTD_CONFLICT,
            TenderIssueKind.CONFLICT,
            RiskSubject.TECHNICAL_REQUIREMENT,
            ("customer_regulation_locator", "ntd_edition_locator", "conflict_policy"),
            blocker=True,
        )
    scalar_checks = (
        (
            value.responsibility_allocated,
            TenderValidationCode.RESPONSIBILITY_UNALLOCATED,
            RiskSubject.RESPONSIBILITY,
            "responsible_party",
        ),
        (
            value.deadline_defined,
            TenderValidationCode.DEADLINE_UNDEFINED,
            RiskSubject.DEADLINE,
            "deadline_basis",
        ),
        (
            value.acceptance_basis_defined,
            TenderValidationCode.ACCEPTANCE_BASIS_UNDEFINED,
            RiskSubject.ACCEPTANCE,
            "acceptance_basis",
        ),
        (
            value.payment_basis_defined,
            TenderValidationCode.PAYMENT_BASIS_UNDEFINED,
            RiskSubject.PAYMENT,
            "payment_basis",
        ),
        (
            value.volume_confirmed,
            TenderValidationCode.VOLUME_UNCONFIRMED,
            RiskSubject.VOLUME,
            "confirmed_volume",
        ),
        (
            value.cost_confirmed,
            TenderValidationCode.COST_UNCONFIRMED,
            RiskSubject.PRICE,
            "confirmed_cost",
        ),
    )
    for passed, code, subject, required_input in scalar_checks:
        if not passed:
            add(
                code,
                TenderIssueKind.UNCERTAINTY,
                subject,
                (required_input,),
                blocker=subject in (RiskSubject.VOLUME, RiskSubject.PRICE),
            )
    if value.omitted_work_ids:
        add(
            TenderValidationCode.WORK_OMITTED,
            TenderIssueKind.MISSING_WORK,
            RiskSubject.TECHNICAL_REQUIREMENT,
            value.omitted_work_ids,
            blocker=False,
            applicability=Applicability.APPLICABLE,
        )
    if value.omitted_material_ids:
        add(
            TenderValidationCode.MATERIAL_OMITTED,
            TenderIssueKind.MISSING_MATERIAL,
            RiskSubject.MATERIAL,
            value.omitted_material_ids,
            blocker=False,
            applicability=Applicability.APPLICABLE,
        )
    if value.geometry_relevant and not (
        value.geometry_source_confirmed and value.crs_known and value.units_known
    ):
        missing = tuple(
            name
            for name, present in (
                ("confirmed_geometry_source", value.geometry_source_confirmed),
                ("crs", value.crs_known),
                ("units", value.units_known),
            )
            if not present
        )
        add(
            TenderValidationCode.GEOMETRY_INSUFFICIENT,
            TenderIssueKind.GEOMETRY_BLOCKER,
            RiskSubject.GEOMETRY,
            missing,
            blocker=True,
        )
    return tuple(failures)
