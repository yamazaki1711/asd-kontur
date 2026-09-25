"""Evidence-safe Tender association schedule for work observations and facilities."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any

from .facility_work_projection import (
    build_facility_identity_association_index,
    resolve_facility_identity_association,
)


def render_tender_facility_scope_schedule_csv(
    work_packages: Iterable[Mapping[str, Any]],
    *,
    identity_candidates: Iterable[Mapping[str, Any]],
    materialization_state: str,
    coverage_gaps: Iterable[str],
) -> bytes:
    """Render evidence-bounded work-to-facility association candidates.

    Exact shared locators have priority.  Without one, a work observation may be
    associated with one identity candidate only when its own name contains one
    explicit unique reconciled identity label.  Similar names, equal labels for
    distinct identities, and multiple mentioned facilities remain ambiguous.
    """

    identity_index = build_facility_identity_association_index(identity_candidates)

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "work_observation_id",
            "work_name",
            "scope",
            "association_state",
            "identity_candidate_ids",
            "identity_labels",
            "identity_kinds",
            "identity_confidences",
            "shared_source_locator_ids",
            "association_evidence_locator_ids",
            "matched_identity_labels",
            "candidate_status",
            "materialization_state",
            "coverage_gaps",
        ),
    )
    writer.writeheader()
    gaps = ";".join(sorted(str(value) for value in coverage_gaps))
    for item in sorted(
        (dict(value) for value in work_packages),
        key=lambda value: str(value.get("work_package_id") or ""),
    ):
        package = item.get("package")
        package = package if isinstance(package, Mapping) else {}
        work_type = package.get("work_type")
        work_type = work_type if isinstance(work_type, Mapping) else {}
        association = resolve_facility_identity_association(package, identity_index)
        candidates = [
            identity_index.identities[candidate_id]
            for candidate_id in association["identity_candidate_ids"]
        ]
        writer.writerow(
            {
                "work_observation_id": str(
                    item.get("work_package_id") or package.get("work_package_id") or ""
                ),
                "work_name": str(work_type.get("raw") or work_type.get("normalized") or ""),
                "scope": str(package.get("scope") or "scope_not_specified"),
                "association_state": association["association_state"],
                "identity_candidate_ids": ";".join(
                    candidate["identity_candidate_id"] for candidate in candidates
                ),
                "identity_labels": ";".join(
                    candidate["identity_label"] for candidate in candidates
                ),
                "identity_kinds": ";".join(candidate["identity_kind"] for candidate in candidates),
                "identity_confidences": ";".join(
                    candidate["identity_confidence"] for candidate in candidates
                ),
                "shared_source_locator_ids": ";".join(association["shared_source_locator_ids"]),
                "association_evidence_locator_ids": ";".join(
                    association["association_evidence_locator_ids"]
                ),
                "matched_identity_labels": ";".join(association["matched_identity_labels"]),
                "candidate_status": "candidate_no_canonical_work_package",
                "materialization_state": materialization_state,
                "coverage_gaps": gaps,
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")
