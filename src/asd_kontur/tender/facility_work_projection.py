"""Evidence-bound facility/work candidate projection for Tender.

The projection makes the safely associated subset usable without pretending
that page-scoped extraction observations are canonical work packages.  A work
package is associated only when one cross-document identity candidate shares
an exact source locator.  Quantities and materials remain observations and are
never summed by this projection.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from asd_kontur.application_spine.models import semantic_digest

from .findings_schedule import source_reference


def build_facility_work_candidate_projection(
    work_packages: Iterable[Mapping[str, Any]],
    identity_candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return consolidated candidate groups plus explicit association coverage."""

    identities: dict[str, dict[str, Any]] = {}
    identities_by_locator: dict[str, set[str]] = defaultdict(set)
    for raw_candidate in identity_candidates:
        candidate = dict(raw_candidate)
        candidate_id = str(candidate.get("identity_candidate_id") or "")
        if not candidate_id:
            continue
        identities[candidate_id] = candidate
        for locator_id in candidate.get("source_locator_ids") or ():
            identities_by_locator[str(locator_id)].add(candidate_id)

    unresolved: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    total = 0
    exact = 0
    ambiguous = 0
    unassociated = 0
    for raw_row in work_packages:
        total += 1
        row = dict(raw_row)
        package_value = row.get("package")
        package = dict(package_value) if isinstance(package_value, Mapping) else {}
        package_id = str(row.get("work_package_id") or package.get("work_package_id") or "")
        work_value = package.get("work_type")
        work_type = dict(work_value) if isinstance(work_value, Mapping) else {}
        locator_ids = sorted({str(value) for value in package.get("source_locator_ids") or ()})
        matched_ids = sorted(
            {
                candidate_id
                for locator_id in locator_ids
                for candidate_id in identities_by_locator.get(locator_id, ())
            }
        )
        shared_locator_ids = sorted(
            {
                locator_id
                for locator_id in locator_ids
                if identities_by_locator.get(locator_id, set()).intersection(matched_ids)
            }
        )
        if len(matched_ids) != 1:
            association_state = (
                "ambiguous_identity_candidates"
                if matched_ids
                else "no_identity_candidate_at_exact_locator"
            )
            if matched_ids:
                ambiguous += 1
            else:
                unassociated += 1
            unresolved.append(
                {
                    "work_package_id": package_id,
                    "work_name": str(work_type.get("raw") or work_type.get("normalized") or ""),
                    "scope": str(package.get("scope") or "scope_not_specified"),
                    "association_state": association_state,
                    "identity_candidate_ids": matched_ids,
                    "source_locator_ids": locator_ids,
                    "shared_source_locator_ids": shared_locator_ids,
                    "uncertainties": sorted(
                        {str(value) for value in package.get("uncertainties") or ()}
                    ),
                }
            )
            continue

        exact += 1
        candidate_id = matched_ids[0]
        canonical_work_type_id = str(work_type.get("canonical_work_type_id") or "")
        # A normalized label is not a work identity. Two distinct operations can
        # have the same extracted name even inside one facility. Only an accepted
        # catalog binding is safe to consolidate; unresolved observations stay
        # separate until a later evidence-aware reconciliation resolves them.
        work_identity = canonical_work_type_id or f"unresolved-package:{package_id}"
        grouped[(candidate_id, work_identity)].append(
            {
                "row": row,
                "package": package,
                "work_type": work_type,
                "work_identity_resolution": (
                    "canonical_work_type" if canonical_work_type_id else "unresolved_observation"
                ),
                "work_package_id": package_id,
                "source_locator_ids": locator_ids,
                "shared_source_locator_ids": shared_locator_ids,
            }
        )

    candidate_groups: list[dict[str, Any]] = []
    for (candidate_id, work_identity), members in sorted(grouped.items()):
        identity = identities[candidate_id]
        members.sort(key=lambda value: value["work_package_id"])
        package_ids = [value["work_package_id"] for value in members]
        observation_ids = sorted(
            {
                str(observation_id)
                for value in members
                for observation_id in value["package"].get("candidate_observation_ids") or ()
            }
        )
        quantities = [
            dict(quantity)
            for value in members
            for quantity in value["package"].get("quantities") or ()
            if isinstance(quantity, Mapping)
        ]
        materials = [
            dict(material)
            for value in members
            for material in value["package"].get("materials") or ()
            if isinstance(material, Mapping)
        ]
        uncertainties = {
            str(uncertainty)
            for value in members
            for uncertainty in value["package"].get("uncertainties") or ()
        }
        quantity_values = {
            (str(value.get("normalized_value")), str(value.get("normalized_unit")))
            for value in quantities
            if value.get("normalized_value") is not None
        }
        if len(quantity_values) > 1:
            uncertainties.add("QUANTITY_OBSERVATIONS_CONFLICT")
        work_type = members[0]["work_type"]
        locator_ids = sorted(
            {locator_id for value in members for locator_id in value["source_locator_ids"]}
        )
        shared_locator_ids = sorted(
            {locator_id for value in members for locator_id in value["shared_source_locator_ids"]}
        )
        group_payload = {
            "identity_candidate_id": candidate_id,
            "work_identity": work_identity,
            "work_package_ids": package_ids,
            "candidate_observation_ids": observation_ids,
            "source_locator_ids": locator_ids,
        }
        candidate_groups.append(
            {
                "facility_work_candidate_id": semantic_digest(group_payload),
                "candidate_state": "facility_work_candidate_not_confirmed",
                "association_state": "exact_locator_identity_candidate",
                "identity_candidate_id": candidate_id,
                "identity_kind": str(identity.get("identity_kind") or ""),
                "identity_label": str(identity.get("canonical_label") or ""),
                "identity_confidence": identity.get("confidence"),
                "work_type": work_type,
                "work_identity_resolution": members[0]["work_identity_resolution"],
                "work_package_ids": package_ids,
                "work_package_count": len(package_ids),
                "candidate_observation_ids": observation_ids,
                "candidate_observation_count": len(observation_ids),
                "quantities": quantities,
                "materials": materials,
                "source_locator_ids": locator_ids,
                "shared_source_locator_ids": shared_locator_ids,
                "uncertainties": sorted(uncertainties),
            }
        )

    unresolved.sort(key=lambda value: (value["association_state"], value["work_package_id"]))
    return {
        "candidate_groups": candidate_groups,
        "unresolved_work_packages": unresolved,
        "coverage": {
            "total_work_package_count": total,
            "exact_identity_package_count": exact,
            "ambiguous_identity_package_count": ambiguous,
            "unassociated_package_count": unassociated,
            "consolidated_candidate_group_count": len(candidate_groups),
            "complete": total > 0 and exact == total,
            "candidate_authority": "candidate_only",
            "association_rule": "exact_shared_source_locator",
        },
    }


def render_facility_work_candidate_schedule_csv(
    projection: Mapping[str, Any],
    *,
    materialization_state: str,
    coverage_gaps: Iterable[str],
    evidence_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> bytes:
    """Render the safely associated candidate subset without commercial totals."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "facility_work_candidate_id",
            "identity_candidate_id",
            "identity_kind",
            "identity_label",
            "identity_confidence",
            "work_name",
            "normalized_work_name",
            "work_identity_resolution",
            "work_package_ids",
            "candidate_observation_count",
            "quantity_observations",
            "material_observations",
            "source_references",
            "source_locator_ids",
            "uncertainties",
            "candidate_status",
            "materialization_state",
            "coverage_gaps",
        ),
    )
    writer.writeheader()
    evidence = evidence_index or {}
    gaps = ";".join(sorted(str(value) for value in coverage_gaps))
    groups = projection.get("candidate_groups")
    groups = groups if isinstance(groups, (list, tuple)) else ()
    for value in sorted(
        (dict(item) for item in groups if isinstance(item, Mapping)),
        key=lambda item: (
            str(item.get("identity_label") or ""),
            str(item.get("facility_work_candidate_id") or ""),
        ),
    ):
        work_type = value.get("work_type")
        work_type = work_type if isinstance(work_type, Mapping) else {}
        locator_ids = tuple(str(item) for item in value.get("source_locator_ids") or ())
        writer.writerow(
            {
                "facility_work_candidate_id": str(value.get("facility_work_candidate_id") or ""),
                "identity_candidate_id": str(value.get("identity_candidate_id") or ""),
                "identity_kind": str(value.get("identity_kind") or ""),
                "identity_label": str(value.get("identity_label") or ""),
                "identity_confidence": str(value.get("identity_confidence") or ""),
                "work_name": str(work_type.get("raw") or ""),
                "normalized_work_name": str(work_type.get("normalized") or ""),
                "work_identity_resolution": str(value.get("work_identity_resolution") or ""),
                "work_package_ids": ";".join(
                    str(item) for item in value.get("work_package_ids") or ()
                ),
                "candidate_observation_count": str(value.get("candidate_observation_count") or 0),
                "quantity_observations": " | ".join(
                    _quantity_observation_text(item)
                    for item in value.get("quantities") or ()
                    if isinstance(item, Mapping)
                ),
                "material_observations": " | ".join(
                    _material_observation_text(item)
                    for item in value.get("materials") or ()
                    if isinstance(item, Mapping)
                ),
                "source_references": "; ".join(
                    source_reference(locator_id, evidence.get(locator_id))
                    for locator_id in locator_ids
                ),
                "source_locator_ids": ";".join(locator_ids),
                "uncertainties": ";".join(
                    sorted(str(item) for item in value.get("uncertainties") or ())
                ),
                "candidate_status": str(
                    value.get("candidate_state") or "facility_work_candidate_not_confirmed"
                ),
                "materialization_state": materialization_state,
                "coverage_gaps": gaps,
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _quantity_observation_text(value: Mapping[str, Any]) -> str:
    raw = " ".join(
        str(item) for item in (value.get("raw_value"), value.get("raw_unit")) if item is not None
    )
    normalized = " ".join(
        str(item)
        for item in (value.get("normalized_value"), value.get("normalized_unit"))
        if item is not None
    )
    locator = str(value.get("source_locator_id") or "")
    return f"raw={raw}; normalized={normalized}; locator={locator}"


def _material_observation_text(value: Mapping[str, Any]) -> str:
    quantity = " ".join(
        str(item) for item in (value.get("raw_quantity"), value.get("raw_unit")) if item is not None
    )
    return (
        f"name={value.get('raw_name') or ''}; quantity={quantity}; "
        f"locator={value.get('source_locator_id') or ''}"
    )
