from __future__ import annotations

from asd_kontur.assistant.engineering_gateway import execute_early_strength
from asd_kontur.knowledge.gateway import GatewayResponse, GatewayStatus


def test_b20_day3_exact_values() -> None:
    payload = {
        "concrete_class": "B20",
        "age_days": 3,
    }
    response = execute_early_strength(payload)

    assert isinstance(response, GatewayResponse)
    assert response.status is GatewayStatus.OK
    assert response.tool == "consultant.estimate_concrete_early_strength"
    assert response.contract_version == "2.9.0"

    result = response.result
    assert result["outcome"] == "found"
    assert result["sources"] == []
    assert result["gaps"] == []

    value = result["value"]
    assert value["normalized_class"] == "B20"
    assert value["age_days"] == 3
    assert value["lower_mpa"] == "6.0"
    assert value["upper_mpa"] == "10.0"
    assert value["central_mpa"] == "8.0"
    assert value["lower_fraction"] == "0.30"
    assert value["upper_fraction"] == "0.50"

    # Verify empty evidence pack
    assert response.evidence_pack.evidence == ()
    assert response.evidence_pack.applicability == ()
    assert response.evidence_pack.conflicts == ()
    assert response.evidence_pack.gaps == ()
    assert response.evidence_pack.uncertainties == ()


def test_b25_day3_exact_values() -> None:
    payload = {
        "concrete_class": "B25",
        "age_days": 3,
    }
    response = execute_early_strength(payload)

    assert isinstance(response, GatewayResponse)
    assert response.status is GatewayStatus.OK

    result = response.result
    assert result["outcome"] == "found"
    assert result["sources"] == []
    assert result["gaps"] == []

    value = result["value"]
    assert value["normalized_class"] == "B25"
    assert value["age_days"] == 3
    assert value["lower_mpa"] == "7.5"
    assert value["upper_mpa"] == "12.5"
    assert value["central_mpa"] == "10.0"

    # Verify empty evidence pack
    assert response.evidence_pack.evidence == ()
    assert response.evidence_pack.applicability == ()
    assert response.evidence_pack.conflicts == ()
    assert response.evidence_pack.gaps == ()
    assert response.evidence_pack.uncertainties == ()


def test_unsupported_age_terminal_no_result() -> None:
    payload = {
        "concrete_class": "B20",
        "age_days": 7,
    }
    response = execute_early_strength(payload)

    assert isinstance(response, GatewayResponse)
    assert response.status is GatewayStatus.NO_RESULT

    result = response.result
    assert result["outcome"] == "unsupported"
    assert result["value"] is None
    assert result["sources"] == []

    gaps = result["gaps"]
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["code"] == "UNSUPPORTED_AGE"
    assert "Only age 3 days is supported" in gap["message"]

    # Verify empty evidence pack
    assert response.evidence_pack.evidence == ()
    assert response.evidence_pack.applicability == ()
    assert response.evidence_pack.conflicts == ()
    assert response.evidence_pack.gaps == ()
    assert response.evidence_pack.uncertainties == ()


def test_bool_age_invalid() -> None:
    payload = {
        "concrete_class": "B20",
        "age_days": True,
    }
    response = execute_early_strength(payload)

    assert isinstance(response, GatewayResponse)
    assert response.status is GatewayStatus.NO_RESULT

    result = response.result
    assert result["outcome"] == "unsupported"
    assert result["value"] is None
    assert result["sources"] == []

    gaps = result["gaps"]
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["code"] == "INVALID_ARGUMENTS"
    assert "age_days must be an integer, not bool" in gap["message"]

    # Verify empty evidence pack
    assert response.evidence_pack.evidence == ()
    assert response.evidence_pack.applicability == ()
    assert response.evidence_pack.conflicts == ()
    assert response.evidence_pack.gaps == ()
    assert response.evidence_pack.uncertainties == ()
