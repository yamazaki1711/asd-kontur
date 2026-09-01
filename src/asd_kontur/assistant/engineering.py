from __future__ import annotations

# ruff: noqa: RUF001 -- Russian engineering safety notice is intentional.
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


class EngineeringError(ValueError):
    """Typed error for engineering estimation failures."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class EngineeringResult:
    """Immutable result of early strength estimation."""

    normalized_class: str
    age_days: int
    assumed_temperature_c: Decimal
    assumed_curing: str
    temperature_assumed: bool
    curing_assumed: bool
    lower_fraction: Decimal
    upper_fraction: Decimal
    lower_mpa: Decimal
    upper_mpa: Decimal
    central_mpa: Decimal
    notice: str


_ALLOWED_CURING_SYNONYMS = frozenset(
    {
        "normal moist curing",
        "нормальное влажное твердение",
        "нормальное твердение",
        "влажное твердение",
    }
)

_CLASS_PATTERN = re.compile(r"^B(\d+(?:\.\d+)?)$")


def estimate_early_strength(
    concrete_class: str,
    age_days: int,
    temperature_c: Decimal | None = None,
    curing_condition: str | None = None,
) -> EngineeringResult:
    """Estimate early compressive strength of ordinary concrete."""
    normalized_class = concrete_class.strip().upper()
    match = _CLASS_PATTERN.match(normalized_class)
    if not match:
        raise EngineeringError("INVALID_CLASS", f"Invalid concrete class: {concrete_class}")

    try:
        strength_mpa = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise EngineeringError(
            "INVALID_CLASS", f"Invalid concrete class strength: {concrete_class}"
        ) from exc

    if not (Decimal("3.5") <= strength_mpa <= Decimal("100")):
        raise EngineeringError("INVALID_CLASS", "Strength must between 3.5 and 100 MPa")

    if age_days != 3:
        raise EngineeringError("UNSUPPORTED_AGE", f"Only age 3 days is supported, got {age_days}")

    if temperature_c is None:
        temp_assumed = True
        assumed_temp = Decimal("20")
    else:
        temp_assumed = False
        assumed_temp = temperature_c
        assumed_temp = Decimal(str(assumed_temp))
        if assumed_temp != Decimal("20"):
            raise EngineeringError("UNSUPPORTED_TEMPERATURE", "Only +20C is supported")

    if curing_condition is None:
        curing_assumed = True
        assumed_curing = "normal moist curing"
    else:
        curing_assumed = False
        assumed_curing = curing_condition.strip().lower()
        if assumed_curing not in _ALLOWED_CURING_SYNONYMS:
            raise EngineeringError(
                "UNSUPPORTED_CURING", f"Unsupported curing condition: {curing_condition}"
            )

    lower_fraction = Decimal("0.30")
    upper_fraction = Decimal("0.50")
    central_fraction = Decimal("0.40")

    lower_mpa = (strength_mpa * lower_fraction).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    upper_mpa = (strength_mpa * upper_fraction).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    central_mpa = (strength_mpa * central_fraction).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    notice = (
        "Ориентировочная инженерная оценка прочности бетона на 3-е сутки. "
        "Не является фактической прочностью и не дает разрешения на распалубку или нагружение. "
        "Фактическая прочность определяется только по результатам испытаний."
    )

    return EngineeringResult(
        normalized_class=normalized_class,
        age_days=age_days,
        assumed_temperature_c=assumed_temp,
        assumed_curing=assumed_curing,
        temperature_assumed=temp_assumed,
        curing_assumed=curing_assumed,
        lower_fraction=lower_fraction,
        upper_fraction=upper_fraction,
        lower_mpa=lower_mpa,
        upper_mpa=upper_mpa,
        central_mpa=central_mpa,
        notice=notice,
    )
