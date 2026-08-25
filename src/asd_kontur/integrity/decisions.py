"""Immutable integrity decisions that supersede, but never rewrite, old series."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine

from asd_kontur.domain import deterministic_uuid

from .models import IntegrityFailure, canonical_digest
from .postgres import (
    EXCLUDED_MEMORY_RELATIONS,
    NON_SEMANTIC_COLUMNS,
    PERMANENT_RELATIONS,
    PLATFORM_MEMORY_SCHEMA_VERSION,
    RELATION_NON_SEMANTIC_COLUMNS,
    REQUIRED_SEMANTIC_COLUMNS,
    active_context_binding_fingerprint,
    active_release_semantic_fingerprint,
    active_semantic_duplicate_inventory,
    platform_memory_fingerprint,
)

FINGERPRINT_SPECIFICATION_ID = deterministic_uuid(
    "platform-memory-fingerprint-specification:v2.1.0"
)


def load_integrity_decision(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise IntegrityFailure("INTEGRITY_DECISION_MALFORMED", "decision root must be an object")
    document = cast(dict[str, Any], value)
    semantic = {
        key: document[key]
        for key in (
            "integrity_decision_id",
            "version",
            "decision_type",
            "status",
            "prior_series_id",
            "canonical_commit",
            "dump_fingerprint",
            "reconciliation_fingerprint",
            "defect_identities",
            "reason",
            "owner_decision_ref",
            "product_ready",
            "recorded_at",
        )
    }
    if canonical_digest(semantic) != document.get("decision_fingerprint"):
        raise IntegrityFailure(
            "INTEGRITY_DECISION_FINGERPRINT_MISMATCH",
            "superseding decision content differs from its immutable fingerprint",
        )
    if document.get("effective_system_integrity_status") != "PARTIAL / DATA_DEFECT":
        raise IntegrityFailure(
            "INTEGRITY_DECISION_STATUS_INVALID",
            "the defect decision must withdraw semantic PASS",
        )
    if document.get("product_ready") is not False:
        raise IntegrityFailure("PRODUCT_READY_FALSE_REQUIRED", "ProductReady must remain false")
    return document


def persist_integrity_decision(engine: Engine, document: Mapping[str, Any]) -> None:
    parameters = {
        "id": UUID(str(document["integrity_decision_id"])),
        "version": int(document["version"]),
        "supersedes": document.get("supersedes_version"),
        "type": str(document["decision_type"]),
        "status": str(document["status"]),
        "series": str(document["prior_series_id"]),
        "commit": str(document["canonical_commit"]),
        "dump": str(document["dump_fingerprint"]),
        "reconciliation": str(document["reconciliation_fingerprint"]),
        "defects": json.dumps(document["defect_identities"], separators=(",", ":")),
        "reason": str(document["reason"]),
        "owner": str(document["owner_decision_ref"]),
        "product_ready": bool(document["product_ready"]),
        "fingerprint": str(document["decision_fingerprint"]),
        "recorded": datetime.fromisoformat(str(document["recorded_at"])),
    }
    with engine.begin() as connection:
        existing = connection.execute(
            sa.text(
                "SELECT decision_fingerprint FROM platform.system_integrity_decisions "
                "WHERE integrity_decision_id=:id AND version=:version"
            ),
            parameters,
        ).scalar_one_or_none()
        if existing is not None:
            if str(existing) != parameters["fingerprint"]:
                raise IntegrityFailure(
                    "INTEGRITY_DECISION_IDENTITY_CONFLICT",
                    "decision identity is already bound to different content",
                )
            return
        connection.execute(
            sa.text(
                """
                INSERT INTO platform.system_integrity_decisions (
                  integrity_decision_id,version,supersedes_version,decision_type,status,
                  prior_series_id,canonical_commit,dump_fingerprint,
                  reconciliation_fingerprint,defect_identities,reason,owner_decision_ref,
                  product_ready,decision_fingerprint,recorded_at
                ) VALUES (
                  :id,:version,:supersedes,:type,:status,:series,:commit,:dump,
                  :reconciliation,CAST(:defects AS jsonb),:reason,:owner,:product_ready,
                  :fingerprint,:recorded
                )
                """
            ),
            parameters,
        )


def persist_fingerprint_specification(engine: Engine, *, recorded_at: datetime) -> dict[str, Any]:
    """Persist the immutable, fail-closed semantic fingerprint contract."""

    payload = {
        "fingerprint_specification_id": str(FINGERPRINT_SPECIFICATION_ID),
        "version": 1,
        "schema_version": PLATFORM_MEMORY_SCHEMA_VERSION,
        "included_components": [
            {
                "relation": f"{schema}.{table}",
                "required_columns": sorted(
                    REQUIRED_SEMANTIC_COLUMNS.get((schema, table), frozenset())
                ),
            }
            for schema, table in PERMANENT_RELATIONS
        ],
        "excluded_components": EXCLUDED_MEMORY_RELATIONS,
        "canonicalization_contract": {
            "serialization": "canonical-json-typed-v1",
            "row_order": "canonical_digest",
            "non_semantic_columns": sorted(NON_SEMANTIC_COLUMNS),
            "relation_non_semantic_columns": {
                f"{schema}.{table}": sorted(columns)
                for (schema, table), columns in sorted(RELATION_NON_SEMANTIC_COLUMNS.items())
            },
            "wall_clock_excluded": True,
            "postgres_attnum_excluded": True,
        },
        "owner_decision_ref": "MEMORY-INTEGRITY-FIX-01;owner:Oleg Shcherbakov",
    }
    fingerprint = canonical_digest(payload)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.platform_memory_fingerprint_specifications "
                "(fingerprint_specification_id,version,schema_version,included_components,"
                "excluded_components,canonicalization_contract,specification_fingerprint,"
                "owner_decision_ref,recorded_at) VALUES "
                "(:id,1,:schema,CAST(:included AS jsonb),CAST(:excluded AS jsonb),"
                "CAST(:canonicalization AS jsonb),:fingerprint,:owner,:recorded) ON CONFLICT "
                "(fingerprint_specification_id,version) DO NOTHING"
            ),
            {
                "id": FINGERPRINT_SPECIFICATION_ID,
                "schema": PLATFORM_MEMORY_SCHEMA_VERSION,
                "included": json.dumps(payload["included_components"], separators=(",", ":")),
                "excluded": json.dumps(payload["excluded_components"], separators=(",", ":")),
                "canonicalization": json.dumps(
                    payload["canonicalization_contract"], separators=(",", ":")
                ),
                "fingerprint": fingerprint,
                "owner": payload["owner_decision_ref"],
                "recorded": recorded_at,
            },
        )
        persisted = connection.scalar(
            sa.text(
                "SELECT specification_fingerprint FROM "
                "platform.platform_memory_fingerprint_specifications WHERE "
                "fingerprint_specification_id=:id AND version=1"
            ),
            {"id": FINGERPRINT_SPECIFICATION_ID},
        )
    if str(persisted) != fingerprint:
        raise IntegrityFailure(
            "FINGERPRINT_SPECIFICATION_IDENTITY_CONFLICT",
            "persisted fingerprint specification has different semantics",
        )
    return {**payload, "specification_fingerprint": fingerprint}


def persist_memory_qualification(
    engine: Engine,
    *,
    receipt_ref: str,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Persist PASS only when the active memory satisfies both repaired invariants."""

    timestamp = recorded_at or datetime.now(UTC)
    specification = persist_fingerprint_specification(engine, recorded_at=timestamp)
    duplicates = active_semantic_duplicate_inventory(engine)
    all_history = platform_memory_fingerprint(engine)
    active_release = active_release_semantic_fingerprint(engine)
    context_binding = active_context_binding_fingerprint(engine)
    missing_component_count = 0  # fail-closed inventory already raises for any absence
    status = "pass" if not duplicates else "data_defect"
    blocker_codes = (
        [] if status == "pass" else ["PRACTICE_INTELLIGENCE_SEMANTIC_IDENTITY_DUPLICATED"]
    )
    decision_id = deterministic_uuid("platform-memory-qualification:MEMORY-INTEGRITY-FIX-01")
    with engine.begin() as connection:
        connection.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:identity,0))"),
            {"identity": str(decision_id)},
        )
        latest = (
            connection.execute(
                sa.text(
                    "SELECT version,status,all_history_fingerprint,"
                    "active_release_fingerprint,context_binding_fingerprint,"
                    "active_duplicate_group_count,missing_component_count,blocker_codes,"
                    "qualification_receipt_ref,decision_fingerprint FROM "
                    "platform.platform_memory_qualification_decisions WHERE "
                    "qualification_decision_id=:id ORDER BY version DESC LIMIT 1 FOR UPDATE"
                ),
                {"id": decision_id},
            )
            .mappings()
            .one_or_none()
        )
        current_semantics = {
            "status": status,
            "all_history_fingerprint": all_history,
            "active_release_fingerprint": active_release,
            "context_binding_fingerprint": context_binding,
            "active_duplicate_group_count": len(duplicates),
            "missing_component_count": missing_component_count,
            "blocker_codes": blocker_codes,
            "qualification_receipt_ref": receipt_ref,
        }
        if latest is not None and all(
            (list(latest[key]) if key == "blocker_codes" else latest[key]) == value
            for key, value in current_semantics.items()
        ):
            return {
                "qualification_decision_id": str(decision_id),
                "version": int(latest["version"]),
                "fingerprint_specification_id": str(FINGERPRINT_SPECIFICATION_ID),
                "fingerprint_specification_version": 1,
                **current_semantics,
                "decision_fingerprint": str(latest["decision_fingerprint"]),
                "specification": specification,
            }
        version = 1 if latest is None else int(latest["version"]) + 1
        supersedes = None if latest is None else int(latest["version"])
        payload = {
            "qualification_decision_id": str(decision_id),
            "version": version,
            "supersedes_version": supersedes,
            "fingerprint_specification_id": str(FINGERPRINT_SPECIFICATION_ID),
            "fingerprint_specification_version": 1,
            **current_semantics,
        }
        decision_fingerprint = canonical_digest(payload)
        connection.execute(
            sa.text(
                "INSERT INTO platform.platform_memory_qualification_decisions "
                "(qualification_decision_id,version,supersedes_version,"
                "fingerprint_specification_id,fingerprint_specification_version,status,"
                "all_history_fingerprint,active_release_fingerprint,"
                "context_binding_fingerprint,active_duplicate_group_count,"
                "missing_component_count,blocker_codes,qualification_receipt_ref,"
                "decision_fingerprint,recorded_at) VALUES "
                "(:id,:version,:supersedes,:spec,1,:status,:history,:active,:context,"
                ":duplicates,:missing,CAST(:blockers AS jsonb),:receipt,:fingerprint,:recorded)"
            ),
            {
                "id": decision_id,
                "version": version,
                "supersedes": supersedes,
                "spec": FINGERPRINT_SPECIFICATION_ID,
                "status": status,
                "history": all_history,
                "active": active_release,
                "context": context_binding,
                "duplicates": len(duplicates),
                "missing": missing_component_count,
                "blockers": json.dumps(blocker_codes, separators=(",", ":")),
                "receipt": receipt_ref,
                "fingerprint": decision_fingerprint,
                "recorded": timestamp,
            },
        )
        persisted_fingerprint = connection.scalar(
            sa.text(
                "SELECT decision_fingerprint FROM "
                "platform.platform_memory_qualification_decisions WHERE "
                "qualification_decision_id=:id AND version=:version"
            ),
            {"id": decision_id, "version": version},
        )
    if str(persisted_fingerprint) != decision_fingerprint:
        raise IntegrityFailure(
            "PLATFORM_MEMORY_QUALIFICATION_IDENTITY_CONFLICT",
            "qualification identity is already bound to different evidence",
        )
    return {**payload, "decision_fingerprint": decision_fingerprint, "specification": specification}
