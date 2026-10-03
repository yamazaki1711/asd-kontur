"""Editable export of the immutable owner-readable Audit report projection."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any


def render_audit_report_projection_csv(projection: Mapping[str, Any]) -> bytes:
    """Render the published report projection without creating an Audit decision.

    This is a portable working projection of the already immutable report.  It
    does not derive a new conclusion, flatten an evidence reference, or mark an
    action request completed.
    """

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "record_kind",
            "report_id",
            "report_version",
            "projection_status",
            "projection_fingerprint",
            "built_at",
            "audit_outcome",
            "delta_kind",
            "delta_id",
            "delta_version",
            "counts",
            "unresolved_item_keys",
            "action_request_id",
            "action_request_version",
            "action_code",
            "affected_object_ref",
            "action_state",
            "evidence_refs",
            "blocking_impacts",
            "gaps",
            "authority_boundary",
        ),
    )
    writer.writeheader()
    status = str(projection.get("status") or "not_published")
    gaps = _joined(projection.get("gaps"))
    customer = _mapping(projection.get("customer"))
    pto = _mapping(projection.get("pto"))
    report = _mapping(_mapping(pto.get("projection_payload")).get("report"))
    common = {
        "report_id": str(pto.get("audit_report_id") or customer.get("audit_report_id") or ""),
        "report_version": str(
            pto.get("audit_report_version") or customer.get("audit_report_version") or ""
        ),
        "projection_status": status,
        "projection_fingerprint": str(pto.get("projection_fingerprint") or ""),
        "built_at": str(pto.get("built_at") or ""),
        "audit_outcome": str(report.get("outcome") or ""),
        "gaps": gaps,
        "authority_boundary": (
            "immutable_audit_projection_only; does_not_create_audit_decision_or_remediation"
        ),
    }
    if status == "not_published":
        writer.writerow({"record_kind": "report_status", **common})
        return ("\ufeff" + output.getvalue()).encode("utf-8")

    payload = _mapping(pto.get("projection_payload"))
    writer.writerow({"record_kind": "report_status", **common})
    for delta in _records(payload.get("deltas")):
        writer.writerow(
            {
                "record_kind": "delta",
                **common,
                "delta_kind": str(delta.get("kind") or ""),
                "delta_id": str(delta.get("delta_id") or ""),
                "delta_version": str(delta.get("version") or ""),
                "counts": _joined_mapping(delta.get("counts")),
                "unresolved_item_keys": _joined(
                    item.get("item_key") if isinstance(item, Mapping) else item
                    for item in delta.get("unresolved_items") or ()
                ),
            }
        )
    for action in _records(payload.get("action_requests")):
        writer.writerow(
            {
                "record_kind": "action_request",
                **common,
                "action_request_id": str(action.get("action_request_id") or ""),
                "action_request_version": str(action.get("version") or ""),
                "action_code": str(action.get("action_code") or ""),
                "affected_object_ref": str(action.get("affected_object_ref") or ""),
                "action_state": str(action.get("state") or ""),
                "evidence_refs": _joined(action.get("evidence_refs")),
                "blocking_impacts": _joined(action.get("blocking_impacts")),
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _records(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _joined(values: object) -> str:
    if isinstance(values, str):
        return values
    if isinstance(values, Mapping) or not isinstance(values, Iterable):
        return ""
    return ";".join(sorted(str(value) for value in values if value is not None))


def _joined_mapping(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    return ";".join(f"{key}={value[key]}" for key in sorted(str(key) for key in value))
