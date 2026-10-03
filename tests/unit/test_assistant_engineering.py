from __future__ import annotations

from decimal import Decimal

import pytest

from asd_kontur.assistant.engineering import EngineeringError, estimate_early_strength


def test_b20_day3_omitted_conditions() -> None:
    result = estimate_early_strength("B20", 3)
    assert result.normalized_class == "B20"
    assert result.age_days == 3
    assert result.assumed_temperature_c == Decimal("20")
    assert result.assumed_curing == "normal moist curing"
    assert result.temperature_assumed is True
    assert result.curing_assumed is True
    assert result.lower_fraction == Decimal("0.30")
    assert result.upper_fraction == Decimal("0.50")
    assert result.lower_mpa == Decimal("6.0")
    assert result.upper_mpa == Decimal("10.0")
    assert result.central_mpa == Decimal("8.0")


def test_b25_day3_omitted_conditions() -> None:
    result = estimate_early_strength("B25", 3)
    assert result.normalized_class == "B25"
    assert result.age_days == 3
    assert result.assumed_temperature_c == Decimal("20")
    assert result.assumed_curing == "normal moist curing"
    assert result.temperature_assumed is True
    assert result.curing_assumed is True
    assert result.lower_fraction == Decimal("0.30")
    assert result.upper_fraction == Decimal("0.50")
    assert result.lower_mpa == Decimal("7.5")
    assert result.upper_mpa == Decimal("12.5")
    assert result.central_mpa == Decimal("10.0")


def test_b20_day3_explicit_20c_and_russian_curing() -> None:
    result = estimate_early_strength(
        "B20",
        3,
        temperature_c=Decimal("20"),
        curing_condition="нормальное влажное твердение",
    )
    assert result.temperature_assumed is False
    assert result.curing_assumed is False
    assert result.assumed_temperature_c == Decimal("20")
    assert result.assumed_curing == "нормальное влажное твердение"
    assert result.lower_mpa == Decimal("6.0")
    assert result.upper_mpa == Decimal("10.0")
    assert result.central_mpa == Decimal("8.0")


def test_invalid_class() -> None:
    with pytest.raises(EngineeringError) as exc_info:
        estimate_early_strength("C20", 3)
    assert exc_info.value.code == "INVALID_CLASS"


def test_unsupported_age() -> None:
    with pytest.raises(EngineeringError) as exc_info:
        estimate_early_strength("B20", 7)
    assert exc_info.value.code == "UNSUPPORTED_AGE"


def test_unsupported_temperature() -> None:
    with pytest.raises(EngineeringError) as exc_info:
        estimate_early_strength("B20", 3, temperature_c=Decimal("25"))
    assert exc_info.value.code == "UNSUPPORTED_TEMPERATURE"


def test_unsupported_curing() -> None:
    with pytest.raises(EngineeringError) as exc_info:
        estimate_early_strength("B20", 3, curing_condition="dry curing")
    assert exc_info.value.code == "UNSUPPORTED_CURING"


def test_result_immutability() -> None:
    result = estimate_early_strength("B20", 3)
    attribute = "normalized_class"
    with pytest.raises(AttributeError):
        setattr(result, attribute, "B25")
