"""Immutable integrity decisions that supersede, but never rewrite, old series."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine

from .models import IntegrityFailure, canonical_digest


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
