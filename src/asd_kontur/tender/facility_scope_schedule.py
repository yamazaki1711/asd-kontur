"""Evidence-safe Tender association schedule for work observations and facilities."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


def render_tender_facility_scope_schedule_csv(
    work_packages: Iterable[Mapping[str, Any]],
    *,
    identity_candidates: Iterable[Mapping[str, Any]],
    materialization_state: str,
    coverage_gaps: Iterable[str],
) -> bytes:
    """Render work-to-facility candidates only when their locators coincide.

    Similar names and adjacent pages are deliberately insufficient.  A work
    observation is linked only to one cross-document identity candidate that
    includes one of its exact source locators.  Multiple possible identities
    remain an explicit ambiguity and no candidate is silently selected.
    """

    by_locator: dict[str, list[dict[str, str]]] = defaultdict(list)
    for candidate in identity_candidates:
        candidate_id = str(candidate.get("identity_candidate_id") or "")
        if not candidate_id:
            continue
        payload = {
            "identity_candidate_id": candidate_id,
            "identity_label": str(candidate.get("canonical_label") or ""),
            "identity_kind": str(candidate.get("identity_kind") or ""),
            "identity_confidence": str(candidate.get("confidence") or ""),
        }
        for locator in candidate.get("source_locator_ids") or ():
            by_locator[str(locator)].append(payload)

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
        locator_ids = sorted(str(value) for value in package.get("source_locator_ids") or ())
        matches: dict[str, dict[str, str]] = {}
        shared: set[str] = set()
        for locator_id in locator_ids:
            for candidate in by_locator.get(locator_id, []):
                matches[candidate["identity_candidate_id"]] = candidate
                shared.add(locator_id)
        candidates = [matches[key] for key in sorted(matches)]
        if len(candidates) == 1:
            association_state = "exact_locator_identity_candidate"
        elif len(candidates) > 1:
            association_state = "ambiguous_identity_candidates"
        else:
            association_state = "no_identity_candidate_at_exact_locator"
        writer.writerow(
            {
                "work_observation_id": str(
                    item.get("work_package_id") or package.get("work_package_id") or ""
                ),
                "work_name": str(work_type.get("raw") or work_type.get("normalized") or ""),
                "scope": str(package.get("scope") or "scope_not_specified"),
                "association_state": association_state,
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
                "shared_source_locator_ids": ";".join(sorted(shared)),
                "candidate_status": "candidate_no_canonical_work_package",
                "materialization_state": materialization_state,
                "coverage_gaps": gaps,
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")
