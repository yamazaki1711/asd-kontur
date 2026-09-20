"""Scope-safe consolidation of extracted work observations.

This is deliberately narrower than facility reconciliation.  A repeated work
label is not a licence to merge different locations, documents or facilities.
It creates a stable *candidate package* only for observations with the same
active source, explicit extraction scope and normalized work identity.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


def consolidate_work_package_candidates(
    works: Iterable[Mapping[str, Any]],
    quantities: Iterable[Mapping[str, Any]],
    materials: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return source-scoped candidate-package inputs without adding quantities.

    The result preserves every observation and keeps same-name work in another
    scope separate.  Multiple quantities with different normalized values or
    units are a conflict, not an arithmetic total.
    """

    quantity_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    material_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for value in quantities:
        quantity_by_work[str(value["work_candidate_id"])].append(dict(value))
    for value in materials:
        material_by_work[str(value["work_candidate_id"])].append(dict(value))

    estimate_roles = {
        "local_estimate",
        "object_estimate",
        "consolidated_estimate",
    }
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for value in works:
        work = dict(value)
        if str(work["source_role"]) in estimate_roles:
            continue
        groups[
            (
                str(work["source_version_id"]),
                str(work["scope_key"]),
                str(work["normalized_name"]),
                str(work.get("canonical_work_type_id") or ""),
            )
        ].append(work)

    name_scopes: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for source, scope, normalized, _canonical in groups:
        name_scopes[normalized].add((source, scope))

    results: list[dict[str, Any]] = []
    for key, observations in sorted(groups.items()):
        source_version_id, scope_key, normalized_name, canonical_work_type_id = key
        observations.sort(key=lambda item: str(item["candidate_id"]))
        quantities_for_group = [
            item
            for observation in observations
            for item in quantity_by_work[str(observation["candidate_id"])]
        ]
        materials_for_group = [
            item
            for observation in observations
            for item in material_by_work[str(observation["candidate_id"])]
        ]
        uncertainties: set[str] = set()
        mapping_states = {
            str(item.get("canonical_mapping_status", "unresolved")) for item in observations
        }
        if "ambiguous" in mapping_states:
            uncertainties.add("WORK_TYPE_MAPPING_AMBIGUOUS")
        elif not canonical_work_type_id:
            uncertainties.add("WORK_TYPE_MAPPING_UNRESOLVED")
        if len(name_scopes[normalized_name]) > 1:
            uncertainties.add("SAME_WORK_NAME_DIFFERENT_SCOPE")
        quantity_values = {
            (str(item.get("normalized_value")), str(item.get("normalized_unit")))
            for item in quantities_for_group
            if item.get("normalized_value") is not None
        }
        if len(quantity_values) > 1:
            uncertainties.add("QUANTITY_OBSERVATIONS_CONFLICT")
        locator_ids = sorted(
            {
                str(item["source_locator_id"])
                for item in observations
                if item.get("source_locator_id") is not None
            }
        )
        results.append(
            {
                "source_version_id": source_version_id,
                "scope_key": scope_key,
                "normalized_name": normalized_name,
                "canonical_work_type_id": canonical_work_type_id or None,
                "observations": observations,
                "quantities": quantities_for_group,
                "materials": materials_for_group,
                "source_locator_ids": locator_ids,
                "uncertainties": sorted(uncertainties),
            }
        )
    return tuple(results)
