from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from asd_kontur.assistant.engineering import EngineeringError, estimate_early_strength
from asd_kontur.knowledge.gateway import (
    ASSISTANT_CONTRACT_VERSION,
    EvidencePack,
    GatewayResponse,
    GatewayStatus,
)

TOOL_ID = "consultant.estimate_concrete_early_strength"


def execute_early_strength(payload: dict[str, Any]) -> GatewayResponse:
    """Execute early strength estimation with strict gateway contract."""
    empty_evidence = EvidencePack(
        evidence=(),
        applicability=(),
        conflicts=(),
        gaps=(),
        uncertainties=(),
    )

    try:
        concrete_class = payload["concrete_class"]
        age_days = payload["age_days"]
        temperature_c = payload.get("temperature_c")
        curing_condition = payload.get("curing_condition")

        if not isinstance(concrete_class, str):
            raise TypeError("concrete_class must be a string")

        if isinstance(age_days, bool) or not isinstance(age_days, int):
            raise TypeError("age_days must be an integer, not bool")

        temp_decimal: Decimal | None = None
        if temperature_c is not None:
            if isinstance(temperature_c, bool):
                raise TypeError("temperature_c must not be a boolean")
            if isinstance(temperature_c, (int, float)):
                temp_decimal = Decimal(str(temperature_c))
            elif isinstance(temperature_c, Decimal):
                temp_decimal = temperature_c
            else:
                raise TypeError("temperature_c must be a number or Decimal")

        curing_str: str | None = None
        if curing_condition is not None:
            if not isinstance(curing_condition, str):
                raise TypeError("curing_condition must be a string")
            curing_str = curing_condition

        result = estimate_early_strength(
            concrete_class=concrete_class,
            age_days=age_days,
            temperature_c=temp_decimal,
            curing_condition=curing_str,
        )

        value = {
            "normalized_class": result.normalized_class,
            "age_days": result.age_days,
            "assumed_temperature_c": str(result.assumed_temperature_c),
            "assumed_curing": result.assumed_curing,
            "temperature_assumed": result.temperature_assumed,
            "curing_assumed": result.curing_assumed,
            "lower_fraction": str(result.lower_fraction),
            "upper_fraction": str(result.upper_fraction),
            "lower_mpa": str(result.lower_mpa),
            "upper_mpa": str(result.upper_mpa),
            "central_mpa": str(result.central_mpa),
            "notice": result.notice,
        }

        return GatewayResponse(
            tool=TOOL_ID,
            contract_version=ASSISTANT_CONTRACT_VERSION,
            status=GatewayStatus.OK,
            result={
                "contract": "construction-consultant-tools@2.8.0",
                "tool": TOOL_ID,
                "outcome": "found",
                "value": value,
                "sources": [],
                "gaps": [],
            },
            evidence_pack=empty_evidence,
        )

    except EngineeringError as exc:
        gap = {"code": exc.code, "message": str(exc)}
        return GatewayResponse(
            tool=TOOL_ID,
            contract_version=ASSISTANT_CONTRACT_VERSION,
            status=GatewayStatus.NO_RESULT,
            result={
                "contract": "construction-consultant-tools@2.8.0",
                "tool": TOOL_ID,
                "outcome": "unsupported",
                "value": None,
                "sources": [],
                "gaps": [gap],
            },
            evidence_pack=empty_evidence,
        )
    except (TypeError, KeyError, InvalidOperation) as exc:
        gap = {"code": "INVALID_ARGUMENTS", "message": str(exc)}
        return GatewayResponse(
            tool=TOOL_ID,
            contract_version=ASSISTANT_CONTRACT_VERSION,
            status=GatewayStatus.NO_RESULT,
            result={
                "contract": "construction-consultant-tools@2.8.0",
                "tool": TOOL_ID,
                "outcome": "unsupported",
                "value": None,
                "sources": [],
                "gaps": [gap],
            },
            evidence_pack=empty_evidence,
        )
