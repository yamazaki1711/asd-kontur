"""Record one exact Practice Intelligence to verified NTD alignment canary."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.domain import deterministic_uuid
from asd_kontur.ntd.models import PracticeNtdAlignment, PracticeNtdAlignmentStatus
from asd_kontur.ntd.postgres import NtdRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--practice-reference-id", required=True)
    parser.add_argument("--guidance-unit-id", required=True)
    parser.add_argument("--provision-id", required=True)
    arguments = parser.parse_args()
    engine = sa.create_engine(arguments.database_url)
    try:
        row = _load_alignment_inputs(
            engine,
            UUID(arguments.practice_reference_id),
            UUID(arguments.guidance_unit_id),
            UUID(arguments.provision_id),
        )
        alignment_id = deterministic_uuid(
            "practice-ntd-alignment:"
            f"{row['practice_guide_reference_id']}:{row['guidance_unit_id']}:"
            f"{row['normative_provision_id']}:{row['version']}"
        )
        alignment = PracticeNtdAlignment(
            alignment_id,
            1,
            UUID(str(row["practice_guide_reference_id"])),
            UUID(str(row["guidance_unit_id"])),
            int(row["guidance_unit_version"]),
            UUID(str(row["normative_document_id"])),
            UUID(str(row["normative_edition_id"])),
            UUID(str(row["normative_provision_id"])),
            int(row["version"]),
            PracticeNtdAlignmentStatus.EDITION_WARNING,
            row["verified_at"].date(),
            (
                f"practice-reference:{row['practice_guide_reference_id']}:"
                f"{row['practice_source_digest']}",
                f"practice-guidance:{row['guidance_unit_id']}:{row['guidance_integrity_digest']}",
                str(row["verification_decision_ref"]),
                f"official-artifact:{row['artifact_digest']}",
            ),
            "NTD-SEED-REMEDIATION-01:native-canary-alignment-v1:"
            "exact-semantics-confirmed;edition-activation-not-asserted",
            row["verified_at"],
        )
        NtdRepository(engine).record_alignment(alignment)
        print(
            json.dumps(
                {
                    "schema": "ntd-practice-alignment-canary-v1",
                    "status": "edition_warning",
                    "alignment": asdict(alignment),
                    "reason": "Exact semantics aligned; current/as-of activation is not qualified.",
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
        )
        return 0
    finally:
        engine.dispose()


def _load_alignment_inputs(
    engine: sa.Engine, practice_reference_id: UUID, guidance_unit_id: UUID, provision_id: UUID
) -> dict[str, Any]:
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.text(
                    "SELECT ref.practice_guide_reference_id,ref.stable_identity_key,"
                    "ref.source_fragment_digest AS practice_source_digest,g.guidance_unit_id,"
                    "g.version AS guidance_unit_version,g.integrity_digest AS "
                    "guidance_integrity_digest,p.normative_provision_id,p.version,p.normative_edition_id,"
                    "p.verification_decision_ref,p.verified_at,e.normative_document_id,"
                    "na.content_digest AS artifact_digest,res.canonical_stable_identity_key FROM "
                    "platform.practice_guide_normative_references ref JOIN "
                    "platform.practice_guidance_units g ON g.guidance_unit_id=:guidance JOIN "
                    "platform.normative_provision_versions p ON "
                    "p.normative_provision_id=:provision AND "
                    "p.verification_status='verified' JOIN platform.normative_editions e ON "
                    "e.normative_edition_id=p.normative_edition_id JOIN "
                    "platform.normative_artifacts na ON "
                    "na.source_version_id=p.source_version_id JOIN "
                    "platform.ntd_identity_resolution_versions ir ON "
                    "ir.normative_document_id=e.normative_document_id AND "
                    "ir.normative_edition_id=e.normative_edition_id JOIN "
                    "platform.ntd_seed_identity_reconciliations res ON "
                    "res.identity_reconciliation_id=ir.identity_reconciliation_id WHERE "
                    "ref.practice_guide_reference_id=:reference ORDER BY p.version DESC LIMIT 1"
                ),
                {
                    "reference": practice_reference_id,
                    "guidance": guidance_unit_id,
                    "provision": provision_id,
                },
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        raise ValueError("NTD_PRACTICE_ALIGNMENT_INPUT_NOT_FOUND")
    if row["stable_identity_key"] != row["canonical_stable_identity_key"]:
        raise ValueError("NTD_PRACTICE_ALIGNMENT_DOCUMENT_IDENTITY_MISMATCH")
    return dict(row)


if __name__ == "__main__":
    raise SystemExit(main())
