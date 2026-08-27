"""Qualify one Polza full-page/crop consensus provision and publish it."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime

import sqlalchemy as sa

from asd_kontur.ntd.remediation import NtdRemediationRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--designation", required=True)
    parser.add_argument("--page-index", type=int, required=True)
    parser.add_argument("--clause", required=True)
    parser.add_argument("--full-profile", required=True)
    parser.add_argument("--crop-profile", required=True)
    parser.add_argument("--verifier-identity", default="codex:NTD-SEED-REMEDIATION-01")
    arguments = parser.parse_args()
    engine = sa.create_engine(arguments.database_url)
    try:
        result = NtdRemediationRepository(engine).qualify_external_provision(
            designation=arguments.designation,
            page_number=arguments.page_index,
            clause_number=arguments.clause,
            full_profile_version=arguments.full_profile,
            crop_profile_version=arguments.crop_profile,
            verified_at=datetime.now(UTC),
            verifier_identity=arguments.verifier_identity,
        )
        payload = {
            "schema": "ntd-external-provision-canary-result-v1",
            "status": "verified",
            "designation": arguments.designation,
            "clause": arguments.clause,
            **asdict(result),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
