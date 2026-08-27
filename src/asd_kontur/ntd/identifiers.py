"""Exact, conservative normalization for the bounded NTD seed designations."""

# ruff: noqa: RUF001 -- Cyrillic designations must remain exact.

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class NormativeDocumentKind(StrEnum):
    GOVERNMENT_RESOLUTION = "government_resolution"
    MINSTROY_ORDER = "minstroy_order"
    CODE_OF_PRACTICE = "code_of_practice"
    NATIONAL_STANDARD = "national_standard"
    INTERSTATE_STANDARD = "interstate_standard"
    INSTRUCTION = "instruction"


@dataclass(frozen=True, slots=True)
class NormalizedNormativeIdentifier:
    raw: str
    normalized_designation: str
    stable_identity_key: str
    document_kind: NormativeDocumentKind
    printed_edition: str | None


_ORDER = re.compile(r"(?i)приказ(?:ом)?\s+минстроя(?:\s+россии)?(?P<body>[^«»]{0,80})")
_ORDER_NUMBER = re.compile(r"(?i)(?:№\s*)?(?P<number>\d+)\s*/\s*пр")
_ORDER_DATE = re.compile(r"(?P<date>\d{2}\.\d{2}\.\d{4})")
_SP = re.compile(r"(?i)^СП\s+(?P<number>\d+(?:[.-]\d+)+)$")
_GOST = re.compile(r"(?i)^ГОСТ(?P<r>\s+Р)?\s+(?P<number>\d+(?:\.\d+)*)(?:-(?P<year>\d{2}|\d{4}))?$")
_INSTRUCTION = re.compile(r"(?i)^И\s+(?P<number>\d+\.\d+-\d+)$")
_GOVERNMENT_RESOLUTION = re.compile(
    r"(?i)^(?:постановление\s+правительства(?:\s+российской\s+федерации|\s+рф)?|пп\s+рф)"
    r"(?:\s+от\s+(?P<date>\d{2}\.\d{2}\.\d{4}))?\s+(?:№\s*)?(?P<number>\d+)$"
)


def normalize_identifier(raw: str) -> NormalizedNormativeIdentifier:
    """Normalize only syntactically exact designations; never infer an edition."""

    collapsed = " ".join(raw.replace("№", " № ").split()).strip(" .;,:")
    government_resolution = _GOVERNMENT_RESOLUTION.match(collapsed)
    if government_resolution is not None:
        number = government_resolution.group("number")
        issued = government_resolution.group("date")
        if issued is None:
            raise ValueError("GOVERNMENT_RESOLUTION_REQUIRES_EXACT_DATE")
        return NormalizedNormativeIdentifier(
            raw=raw,
            normalized_designation=(
                f"ПОСТАНОВЛЕНИЕ ПРАВИТЕЛЬСТВА РОССИЙСКОЙ ФЕДЕРАЦИИ ОТ {issued} № {number}"
            ),
            stable_identity_key=f"ru:government:resolution:{issued}:{number}",
            document_kind=NormativeDocumentKind.GOVERNMENT_RESOLUTION,
            printed_edition=issued,
        )
    order = _ORDER.search(collapsed)
    if order is not None:
        number_match = _ORDER_NUMBER.search(order.group("body"))
        date_match = _ORDER_DATE.search(order.group("body"))
        if number_match is None:
            raise ValueError("MINSTROY_ORDER_REQUIRES_EXACT_NUMBER")
        number = number_match.group("number")
        issued = date_match.group("date") if date_match is not None else None
        normalized = f"ПРИКАЗ МИНСТРОЯ РОССИИ № {number}/ПР"
        identity_date = "date-unresolved"
        if issued is not None:
            normalized += f" ОТ {issued}"
            day, month, year = issued.split(".")
            identity_date = f"{year}-{month}-{day}"
        return NormalizedNormativeIdentifier(
            raw=raw,
            normalized_designation=normalized,
            # Order numbers are reused across years. A number-only identity is an
            # unresolved occurrence, never a canonical legal-act identity.
            stable_identity_key=f"ru:minstroy:order:{identity_date}:{number}-pr",
            document_kind=NormativeDocumentKind.MINSTROY_ORDER,
            printed_edition=issued,
        )
    sp = _SP.match(collapsed)
    if sp is not None:
        number = sp.group("number")
        printed_year = _terminal_year(number)
        stable_number = number[: -(len(printed_year) + 1)] if printed_year is not None else number
        return NormalizedNormativeIdentifier(
            raw=raw,
            normalized_designation=f"СП {number}",
            stable_identity_key=f"ru:sp:{stable_number}",
            document_kind=NormativeDocumentKind.CODE_OF_PRACTICE,
            printed_edition=printed_year,
        )
    gost = _GOST.match(collapsed)
    if gost is not None:
        number = gost.group("number")
        year = gost.group("year")
        prefix = "ГОСТ Р" if gost.group("r") else "ГОСТ"
        designation = f"{prefix} {number}" + (f"-{year}" if year else "")
        namespace = "gost-r" if gost.group("r") else "gost"
        return NormalizedNormativeIdentifier(
            raw=raw,
            normalized_designation=designation,
            stable_identity_key=f"ru:{namespace}:{number}",
            document_kind=(
                NormativeDocumentKind.NATIONAL_STANDARD
                if gost.group("r")
                else NormativeDocumentKind.INTERSTATE_STANDARD
            ),
            printed_edition=year,
        )
    instruction = _INSTRUCTION.match(collapsed)
    if instruction is not None:
        number = instruction.group("number")
        return NormalizedNormativeIdentifier(
            raw=raw,
            normalized_designation=f"И {number}",
            stable_identity_key=f"ru:instruction:{number.lower()}",
            document_kind=NormativeDocumentKind.INSTRUCTION,
            printed_edition=None,
        )
    raise ValueError(f"UNSUPPORTED_NORMATIVE_IDENTIFIER:{raw}")


def _terminal_year(number: str) -> str | None:
    match = re.search(r"(?:\.|-)(\d{4})$", number)
    return match.group(1) if match else None
