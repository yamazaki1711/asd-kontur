from __future__ import annotations

import csv
from io import StringIO

from asd_kontur.audit.report_export import render_audit_report_projection_csv


def test_report_export_keeps_exact_projection_versions_and_requests() -> None:
    content = render_audit_report_projection_csv(
        {
            "status": "published",
            "gaps": [],
            "pto": {
                "audit_report_id": "report-1",
                "audit_report_version": 2,
                "projection_fingerprint": "sha256:projection",
                "built_at": "2026-09-19T10:00:00Z",
                "projection_payload": {
                    "report": {"outcome": "blocked"},
                    "deltas": [
                        {
                            "kind": "document",
                            "delta_id": "delta-1",
                            "version": 4,
                            "counts": {"missing": 2, "ready": 1},
                            "unresolved_items": [{"item_key": "item-a"}],
                        }
                    ],
                    "action_requests": [
                        {
                            "action_request_id": "request-1",
                            "version": 3,
                            "action_code": "collect_certificate",
                            "affected_object_ref": "work:steel",
                            "state": "issued",
                            "evidence_refs": ["locator-a"],
                            "blocking_impacts": ["MATERIAL_CERTIFICATE_MISSING"],
                        }
                    ],
                },
            },
        }
    )

    rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert [row["record_kind"] for row in rows] == ["report_status", "delta", "action_request"]
    assert rows[0]["report_id"] == "report-1"
    assert rows[0]["report_version"] == "2"
    assert rows[1]["counts"] == "missing=2;ready=1"
    assert rows[1]["unresolved_item_keys"] == "item-a"
    assert rows[2]["action_request_version"] == "3"
    assert rows[2]["evidence_refs"] == "locator-a"
    assert "does_not_create_audit_decision" in rows[2]["authority_boundary"]


def test_not_published_report_export_keeps_absence_distinct_from_clean_audit() -> None:
    content = render_audit_report_projection_csv(
        {"status": "not_published", "gaps": ["CANONICAL_AUDIT_REPORT_NOT_PUBLISHED"]}
    )

    rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["record_kind"] == "report_status"
    assert rows[0]["audit_outcome"] == ""
    assert rows[0]["gaps"] == "CANONICAL_AUDIT_REPORT_NOT_PUBLISHED"
