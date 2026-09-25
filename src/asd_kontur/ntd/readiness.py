"""Append-only readiness decisions for canonical NTD memory."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid

NTD_MEMORY_CRITERIA = frozenset(
    {
        "retrieval_benchmark_accepted",
        "sp70_canary",
        "ntd_terminal_118",
        "gesn_deferred_external_smetter_route",
        "usable_documents_searchable",
        "physical_embeddings_and_indexes",
        "backup_restore",
        "projection_rebuild",
        "workspace_reset_survival",
        "consultant_harness_contracts_separated",
    }
)


class NtdMemoryReadinessError(RuntimeError):
    pass


class NtdMemoryReadinessRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(
        self,
        *,
        source_commit: str,
        criteria: dict[str, bool],
        blockers: list[str],
        decided_by_identity_id: str,
        build_receipt_id: UUID | None = None,
    ) -> dict[str, Any]:
        if len(source_commit) != 40 or any(
            value not in "0123456789abcdef" for value in source_commit
        ):
            raise NtdMemoryReadinessError("ntd_memory_source_commit_invalid")
        if set(criteria) != NTD_MEMORY_CRITERIA:
            raise NtdMemoryReadinessError("ntd_memory_readiness_criteria_invalid")
        normalized_blockers = sorted(
            {" ".join(value.split()) for value in blockers if value.strip()}
        )
        ready = all(criteria.values()) and not normalized_blockers and build_receipt_id is not None
        if not ready and not normalized_blockers:
            raise NtdMemoryReadinessError("ntd_memory_blocker_required")
        status = "ready" if ready else "not_ready"
        payload = {
            "source_commit": source_commit,
            "status": status,
            "denominator_ntd": 118,
            "deferred_estimate_references": 12,
            "build_receipt_id": str(build_receipt_id) if build_receipt_id else None,
            "criteria": criteria,
            "blockers": normalized_blockers,
        }
        fingerprint = semantic_digest(payload)
        decision_id = deterministic_uuid("ntd-memory-readiness")
        with Session(self._engine) as session, session.begin():
            existing = (
                session.execute(
                    sa.text(
                        "SELECT * FROM application.ntd_memory_readiness_decisions "
                        "WHERE decision_fingerprint=:fingerprint"
                    ),
                    {"fingerprint": fingerprint},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return _public(existing)
            version = int(
                session.scalar(
                    sa.text(
                        "SELECT coalesce(max(version),0)+1 FROM "
                        "application.ntd_memory_readiness_decisions WHERE decision_id=:decision"
                    ),
                    {"decision": decision_id},
                )
                or 1
            )
            session.execute(
                sa.text(
                    "INSERT INTO application.ntd_memory_readiness_decisions("
                    "decision_id,version,source_commit,status,denominator_ntd,deferred_estimate_references,"
                    "build_receipt_id,criteria,blockers,decision_fingerprint,"
                    "decided_by_identity_id) VALUES "
                    "(:decision,:version,:commit,:status,118,12,:build,"
                    "CAST(:criteria AS jsonb),"
                    "CAST(:blockers AS jsonb),:fingerprint,:actor)"
                ),
                {
                    "decision": decision_id,
                    "version": version,
                    "commit": source_commit,
                    "status": status,
                    "build": build_receipt_id,
                    "criteria": _json(criteria),
                    "blockers": _json(normalized_blockers),
                    "fingerprint": fingerprint,
                    "actor": decided_by_identity_id,
                },
            )
        latest = self.latest()
        if latest is None:
            raise NtdMemoryReadinessError("ntd_memory_readiness_not_found")
        return latest

    def latest(self) -> dict[str, Any] | None:
        with Session(self._engine) as session, session.begin():
            row = (
                session.execute(
                    sa.text(
                        "SELECT * FROM application.ntd_memory_readiness_decisions "
                        "ORDER BY decided_at DESC,version DESC LIMIT 1"
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _public(row) if row is not None else None


def _public(row: sa.RowMapping) -> dict[str, Any]:
    return {
        "decision_id": str(row["decision_id"]),
        "version": int(row["version"]),
        "source_commit": str(row["source_commit"]),
        "status": str(row["status"]),
        "denominator_ntd": int(row["denominator_ntd"]),
        "deferred_estimate_references": int(row["deferred_estimate_references"]),
        "build_receipt_id": str(row["build_receipt_id"]) if row["build_receipt_id"] else None,
        "criteria": dict(row["criteria"]),
        "blockers": list(row["blockers"]),
        "decision_fingerprint": str(row["decision_fingerprint"]),
        "decided_by_identity_id": str(row["decided_by_identity_id"]),
        "decided_at": row["decided_at"].isoformat(),
    }


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
