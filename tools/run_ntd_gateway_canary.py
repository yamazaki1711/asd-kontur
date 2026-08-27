"""Invoke one exact version-pinned NTD query through the common Knowledge Gateway."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import Any

import sqlalchemy as sa

from asd_kontur.domain import uuid7
from asd_kontur.knowledge.gateway import (
    NTD_CONTRACT_VERSION,
    NTD_SCHEMA_ID,
    GatewayContext,
    GatewayRequest,
    GatewayStatus,
    KnowledgeGateway,
)
from asd_kontur.ntd.gateway import NtdKnowledgeQueryService


class _AuditReceipt:
    def __init__(self) -> None:
        self.receipts: list[dict[str, Any]] = []

    def record(
        self,
        *,
        context: GatewayContext,
        tool: str,
        status: GatewayStatus | str,
        evidence_count: int,
    ) -> None:
        self.receipts.append(
            {
                "actor": context.actor_identity_id,
                "tool": tool,
                "status": str(status),
                "evidence_count": evidence_count,
                "correlation_id": str(context.correlation_id),
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--edition-id")
    parser.add_argument("--locator")
    parser.add_argument("--guidance-unit-id")
    parser.add_argument("--as-of")
    arguments = parser.parse_args()
    if arguments.guidance_unit_id:
        if not arguments.as_of or arguments.edition_id or arguments.locator:
            parser.error("alignment query requires only --guidance-unit-id and --as-of")
        tool = "knowledge.get_practice_ntd_alignment"
        payload = {"guidance_unit_id": arguments.guidance_unit_id, "as_of": arguments.as_of}
    else:
        if not arguments.edition_id or not arguments.locator or arguments.as_of:
            parser.error("provision query requires --edition-id and --locator")
        tool = "knowledge.get_ntd_provision"
        payload = {"edition_id": arguments.edition_id, "locator": arguments.locator}
    engine = sa.create_engine(arguments.database_url)
    audit = _AuditReceipt()
    try:
        gateway = KnowledgeGateway(NtdKnowledgeQueryService(engine), audit)
        response = gateway.invoke(
            GatewayRequest(
                tool,
                NTD_CONTRACT_VERSION,
                NTD_SCHEMA_ID,
                NTD_CONTRACT_VERSION,
                payload,
            ),
            GatewayContext(
                "codex:NTD-SEED-REMEDIATION-01",
                f"{tool}.invoke",
                "native_provision_canary",
                uuid7(),
            ),
        )
        print(
            json.dumps(
                {
                    "schema": "ntd-gateway-canary-v1",
                    "status": response.status,
                    "result": response.result,
                    "evidence_pack": asdict(response.evidence_pack),
                    "audit": audit.receipts,
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
        )
        return 0 if response.status is GatewayStatus.OK else 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
