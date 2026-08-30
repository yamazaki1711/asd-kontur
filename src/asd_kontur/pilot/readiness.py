"""Formal, append-only TrialReadinessDecision for the deployed pilot contour."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid5

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest

from .builder import PILOT_NAMESPACE
from .postgres import PilotResultError

REQUIRED_TRIAL_CRITERIA = frozenset(
    {
        "owner_ui_path",
        "four_mode_results",
        "exact_source_navigation",
        "unconfirmed_facts_are_marked",
        "required_documents_not_fabricated",
        "restart_survival",
        "workspace_isolation",
        "exports_available",
        "limitations_visible",
        "rollback_available",
        "external_e2e_exact_commit",
    }
)

REQUIRED_THRESHOLD_KEYS = frozenset(
    {
        "max_corpus_files",
        "max_corpus_bytes",
        "admission_seconds",
        "first_result_seconds",
        "main_screen_seconds",
        "transient_retry_rate_percent",
        "unexpected_failure_rate_percent",
        "interruption_recovery_seconds",
    }
)


class TrialReadinessRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(
        self,
        *,
        deployed_commit: str,
        criteria: dict[str, bool],
        pilot_thresholds: dict[str, Any],
        external_receipts: list[dict[str, Any]],
        user_blockers: list[str],
        rollback_target: str,
        owner_identity_id: str,
    ) -> dict[str, Any]:
        missing_criteria = REQUIRED_TRIAL_CRITERIA - criteria.keys()
        missing_thresholds = REQUIRED_THRESHOLD_KEYS - pilot_thresholds.keys()
        if missing_criteria:
            raise PilotResultError("trial_readiness_criteria_incomplete")
        if missing_thresholds:
            raise PilotResultError("trial_readiness_thresholds_incomplete")
        if not external_receipts:
            raise PilotResultError("trial_readiness_external_receipts_required")
        if not rollback_target.strip():
            raise PilotResultError("trial_readiness_rollback_required")
        status = (
            "trial_ready"
            if all(bool(criteria[key]) for key in REQUIRED_TRIAL_CRITERIA) and not user_blockers
            else "blocked"
        )
        payload = {
            "deployed_commit": deployed_commit,
            "status": status,
            "criteria": criteria,
            "pilot_thresholds": pilot_thresholds,
            "external_receipts": external_receipts,
            "user_blockers": sorted(set(user_blockers)),
            "rollback_target": rollback_target,
        }
        fingerprint = semantic_digest(payload)
        decision_id = uuid5(PILOT_NAMESPACE, f"trial-readiness:{deployed_commit}")
        with Session(self._engine) as session, session.begin():
            existing = (
                session.execute(
                    sa.text(
                        "SELECT * FROM application.trial_readiness_decisions "
                        "WHERE decision_fingerprint=:fingerprint"
                    ),
                    {"fingerprint": fingerprint},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return _decision(existing)
            version = int(
                session.scalar(
                    sa.text(
                        "SELECT coalesce(max(version),0)+1 FROM "
                        "application.trial_readiness_decisions WHERE decision_id=:decision"
                    ),
                    {"decision": decision_id},
                )
                or 1
            )
            session.execute(
                sa.text(
                    "INSERT INTO application.trial_readiness_decisions "
                    "(decision_id,version,deployed_commit,status,criteria,pilot_thresholds,"
                    "external_receipts,user_blockers,rollback_target,decision_fingerprint,"
                    "decided_by_identity_id) VALUES "
                    "(:decision,:version,:commit,:status,CAST(:criteria AS jsonb),"
                    "CAST(:thresholds AS jsonb),CAST(:receipts AS jsonb),CAST(:blockers AS jsonb),"
                    ":rollback,:fingerprint,:owner)"
                ),
                {
                    "decision": decision_id,
                    "version": version,
                    "commit": deployed_commit,
                    "status": status,
                    "criteria": _json(criteria),
                    "thresholds": _json(pilot_thresholds),
                    "receipts": _json(external_receipts),
                    "blockers": _json(sorted(set(user_blockers))),
                    "rollback": rollback_target.strip(),
                    "fingerprint": fingerprint,
                    "owner": owner_identity_id,
                },
            )
        value = self.latest()
        if value is None:
            raise PilotResultError("trial_readiness_decision_not_found")
        return value

    def latest(self) -> dict[str, Any] | None:
        with Session(self._engine) as session, session.begin():
            row = (
                session.execute(
                    sa.text(
                        "SELECT * FROM application.trial_readiness_decisions "
                        "ORDER BY decided_at DESC,decision_id,version DESC LIMIT 1"
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _decision(row) if row is not None else None


def _decision(row: sa.RowMapping) -> dict[str, Any]:
    return {
        "decision_id": str(row["decision_id"]),
        "version": int(row["version"]),
        "deployed_commit": str(row["deployed_commit"]),
        "status": str(row["status"]),
        "criteria": dict(row["criteria"]),
        "pilot_thresholds": dict(row["pilot_thresholds"]),
        "external_receipts": list(row["external_receipts"]),
        "user_blockers": list(row["user_blockers"]),
        "rollback_target": str(row["rollback_target"]),
        "decision_fingerprint": str(row["decision_fingerprint"]),
        "decided_by_identity_id": str(row["decided_by_identity_id"]),
        "decided_at": row["decided_at"].isoformat(),
    }


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
