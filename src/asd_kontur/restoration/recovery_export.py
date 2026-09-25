"""Editable export for evidence-constrained Restoration recovery plans."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any


def render_recovery_plan_csv(plan: Mapping[str, Any]) -> bytes:
    """Render a portable working schedule without changing the plan state."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "disposition",
            "item_key",
            "work_package_id",
            "document_requirement_id",
            "document_requirement_version",
            "document_type",
            "preflight_state",
            "action",
            "required_input",
            "evidence_refs",
            "generated_candidate_ids",
            "finalized_document_ids",
            "blocker_codes",
            "fabrication_prohibited",
            "plan_status",
            "global_blockers",
        ),
    )
    writer.writeheader()
    global_blockers = ";".join(sorted(str(value) for value in plan.get("global_blockers") or ()))
    for disposition, items in (
        ("recoverable", plan.get("recoverable_actions") or ()),
        ("blocked", plan.get("blocked_actions") or ()),
    ):
        for item in _records(items):
            writer.writerow(
                {
                    "disposition": disposition,
                    "item_key": item.get("item_key", ""),
                    "work_package_id": item.get("work_package_id", ""),
                    "document_requirement_id": item.get("document_requirement_id", ""),
                    "document_requirement_version": item.get("document_requirement_version", ""),
                    "document_type": item.get("document_type", ""),
                    "preflight_state": item.get("preflight_state", ""),
                    "action": item.get("action", ""),
                    "required_input": item.get("required_input", ""),
                    "evidence_refs": ";".join(
                        str(value) for value in item.get("evidence_refs") or ()
                    ),
                    "generated_candidate_ids": ";".join(
                        str(value) for value in item.get("generated_candidate_ids") or ()
                    ),
                    "finalized_document_ids": ";".join(
                        str(value) for value in item.get("finalized_document_ids") or ()
                    ),
                    "blocker_codes": ";".join(
                        str(value) for value in item.get("blocker_codes") or ()
                    ),
                    "fabrication_prohibited": str(bool(item.get("fabrication_prohibited"))).lower(),
                    "plan_status": str(plan.get("status") or "blocked"),
                    "global_blockers": global_blockers,
                }
            )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _records(values: Iterable[object]) -> Iterable[Mapping[str, Any]]:
    return (value for value in values if isinstance(value, Mapping))
