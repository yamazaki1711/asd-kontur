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


def retain_unresolved_relationship_defects(
    defects: Iterable[Mapping[str, Any]],
    works: Iterable[Mapping[str, Any]],
    quantities: Iterable[Mapping[str, Any]],
    materials: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Drop only relationship defects superseded by one exact child observation.

    Incremental batch persistence can record an unresolved quantity or material
    before a later batch exposes its work.  History remains immutable, but a new
    project reconciliation must not keep presenting that old defect when the
    completed source contains one exact, evidence-identical linked candidate.

    Name equality alone is deliberately insufficient: the child must have the
    same evidence locator and payload, and exactly one linked work must have the
    normalized referenced name.  Zero or multiple matches preserve the defect.
    """

    work_by_id = {str(item["candidate_id"]): dict(item) for item in works}
    quantity_rows = tuple(quantities)
    material_rows = tuple(materials)

    def normalized(value: object) -> str:
        return " ".join(str(value or "").casefold().split())

    def relationship_matches(defect: Mapping[str, Any]) -> set[str]:
        parameters = defect.get("parameters")
        if not isinstance(parameters, Mapping):
            return set()
        if parameters.get("code") != "unresolved_work_reference":
            return set()
        locators = defect.get("source_locator_ids")
        if not isinstance(locators, (list, tuple)) or len(locators) != 1:
            return set()
        locator_id = str(locators[0])
        work_name = normalized(parameters.get("work_name"))
        payload = parameters.get("payload")
        if not work_name or not isinstance(payload, Mapping):
            return set()
        kind = parameters.get("relationship_kind")
        candidates = (
            quantity_rows if kind == "quantity" else material_rows if kind == "material" else ()
        )
        matches: set[str] = set()
        for child in candidates:
            if str(child.get("source_locator_id")) != locator_id:
                continue
            work_id = str(child.get("work_candidate_id"))
            work = work_by_id.get(work_id)
            if work is None or normalized(work.get("normalized_name")) != work_name:
                continue
            if kind == "quantity":
                exact_payload = str(child.get("raw_value") or "") == str(
                    payload.get("value") or ""
                ) and str(child.get("raw_unit") or "") == str(payload.get("unit") or "")
            else:
                exact_payload = (
                    str(child.get("raw_name") or "") == str(payload.get("name") or "")
                    and str(child.get("raw_quantity") or "") == str(payload.get("quantity") or "")
                    and str(child.get("raw_unit") or "") == str(payload.get("unit") or "")
                )
            if exact_payload:
                matches.add(work_id)
        return matches

    retained: list[dict[str, Any]] = []
    for value in defects:
        defect = dict(value)
        if len(relationship_matches(defect)) != 1:
            retained.append(defect)
    return tuple(retained)


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
