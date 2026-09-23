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
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from asd_kontur.application_spine.models import semantic_digest

from .findings_schedule import source_reference


@dataclass(frozen=True, slots=True)
class FacilityIdentityAssociationIndex:
    identities: dict[str, dict[str, Any]]
    identity_ids_by_locator: dict[str, frozenset[str]]
    identity_ids_by_normalized_label: dict[str, frozenset[str]]


def build_facility_identity_association_index(
    identity_candidates: Iterable[Mapping[str, Any]],
) -> FacilityIdentityAssociationIndex:
    """Index identity candidates without treating a label as canonical fact."""

    identities: dict[str, dict[str, Any]] = {}
    ids_by_locator: dict[str, set[str]] = defaultdict(set)
    ids_by_label: dict[str, set[str]] = defaultdict(set)
    for raw_candidate in identity_candidates:
        candidate = dict(raw_candidate)
        candidate_id = str(candidate.get("identity_candidate_id") or "")
        if not candidate_id:
            continue
        identities[candidate_id] = {
            **candidate,
            "identity_candidate_id": candidate_id,
            "identity_label": str(candidate.get("canonical_label") or ""),
            "identity_kind": str(candidate.get("identity_kind") or ""),
            "identity_confidence": str(candidate.get("confidence") or ""),
        }
        for locator_id in candidate.get("source_locator_ids") or ():
            ids_by_locator[str(locator_id)].add(candidate_id)
        normalized_label = _normalized_identity_text(candidate.get("canonical_label"))
        if normalized_label:
            ids_by_label[normalized_label].add(candidate_id)
    return FacilityIdentityAssociationIndex(
        identities,
        {key: frozenset(value) for key, value in ids_by_locator.items()},
        {key: frozenset(value) for key, value in ids_by_label.items()},
    )


def resolve_facility_identity_association(
    package: Mapping[str, Any], index: FacilityIdentityAssociationIndex
) -> dict[str, Any]:
    """Resolve one candidate association by exact locator or explicit unique label.

    A label match remains candidate evidence. Equal labels that point to distinct
    identity candidates and work names that mention multiple facilities remain
    ambiguous instead of selecting an arbitrary target.
    """

    locator_ids = sorted({str(value) for value in package.get("source_locator_ids") or ()})
    locator_matches = sorted(
        {
            candidate_id
            for locator_id in locator_ids
            for candidate_id in index.identity_ids_by_locator.get(locator_id, ())
        }
    )
    shared_locator_ids = sorted(
        {
            locator_id
            for locator_id in locator_ids
            if index.identity_ids_by_locator.get(locator_id, frozenset()).intersection(
                locator_matches
            )
        }
    )
    if locator_matches:
        return {
            "association_state": (
                "exact_locator_identity_candidate"
                if len(locator_matches) == 1
                else "ambiguous_identity_candidates"
            ),
            "identity_candidate_ids": locator_matches,
            "shared_source_locator_ids": shared_locator_ids,
            "association_evidence_locator_ids": shared_locator_ids,
            "matched_identity_labels": [],
        }

    work_type_value = package.get("work_type")
    work_type = work_type_value if isinstance(work_type_value, Mapping) else {}
    work_name = _normalized_identity_text(work_type.get("raw") or work_type.get("normalized"))
    matched_labels = [
        label
        for label in index.identity_ids_by_normalized_label
        if _contains_unambiguous_identity_phrase(work_name, label)
    ]
    maximal_labels = sorted(
        label
        for label in matched_labels
        if not any(
            label != other and _contains_normalized_phrase(other, label) for other in matched_labels
        )
    )
    label_matches = sorted(
        {
            candidate_id
            for label in maximal_labels
            for candidate_id in index.identity_ids_by_normalized_label[label]
        }
    )
    if not label_matches:
        return {
            "association_state": "no_identity_candidate_at_exact_locator_or_explicit_label",
            "identity_candidate_ids": [],
            "shared_source_locator_ids": [],
            "association_evidence_locator_ids": locator_ids,
            "matched_identity_labels": [],
        }
    identity_locator_ids = sorted(
        {
            str(locator_id)
            for candidate_id in label_matches
            for locator_id in index.identities[candidate_id].get("source_locator_ids") or ()
        }
    )
    return {
        "association_state": (
            "explicit_unique_identity_label_candidate"
            if len(label_matches) == 1
            else "ambiguous_identity_candidates"
        ),
        "identity_candidate_ids": label_matches,
        "shared_source_locator_ids": [],
        "association_evidence_locator_ids": sorted({*locator_ids, *identity_locator_ids}),
        "matched_identity_labels": maximal_labels,
    }


def build_facility_work_candidate_projection(
    work_packages: Iterable[Mapping[str, Any]],
    identity_candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return consolidated candidate groups plus explicit association coverage."""

    identity_index = build_facility_identity_association_index(identity_candidates)

    unresolved: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    total = 0
    exact = 0
    explicit_label = 0
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
        association = resolve_facility_identity_association(package, identity_index)
        matched_ids = list(association["identity_candidate_ids"])
        association_state = str(association["association_state"])
        if len(matched_ids) != 1:
            if association_state == "ambiguous_identity_candidates":
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
                    "shared_source_locator_ids": association["shared_source_locator_ids"],
                    "association_evidence_locator_ids": association[
                        "association_evidence_locator_ids"
                    ],
                    "matched_identity_labels": association["matched_identity_labels"],
                    "uncertainties": sorted(
                        {str(value) for value in package.get("uncertainties") or ()}
                    ),
                }
            )
            continue

        if association_state == "exact_locator_identity_candidate":
            exact += 1
        else:
            explicit_label += 1
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
                "shared_source_locator_ids": association["shared_source_locator_ids"],
                "association_evidence_locator_ids": association["association_evidence_locator_ids"],
                "matched_identity_labels": association["matched_identity_labels"],
                "association_state": association_state,
            }
        )

    candidate_groups: list[dict[str, Any]] = []
    for (candidate_id, work_identity), members in sorted(grouped.items()):
        identity = identity_index.identities[candidate_id]
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
        association_evidence_locator_ids = sorted(
            {
                locator_id
                for value in members
                for locator_id in value["association_evidence_locator_ids"]
            }
        )
        association_states = sorted({str(value["association_state"]) for value in members})
        matched_identity_labels = sorted(
            {label for value in members for label in value["matched_identity_labels"]}
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
                "association_state": (
                    association_states[0]
                    if len(association_states) == 1
                    else "mixed_candidate_association_evidence"
                ),
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
                "association_evidence_locator_ids": association_evidence_locator_ids,
                "matched_identity_labels": matched_identity_labels,
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
            "explicit_label_identity_package_count": explicit_label,
            "ambiguous_identity_package_count": ambiguous,
            "unassociated_package_count": unassociated,
            "consolidated_candidate_group_count": len(candidate_groups),
            "complete": total > 0 and exact + explicit_label == total,
            "candidate_authority": "candidate_only",
            "association_rule": "exact_shared_source_locator_or_explicit_unique_identity_label",
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
            "association_state",
            "matched_identity_labels",
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
        locator_ids = tuple(
            str(item)
            for item in value.get("association_evidence_locator_ids")
            or value.get("source_locator_ids")
            or ()
        )
        writer.writerow(
            {
                "facility_work_candidate_id": str(value.get("facility_work_candidate_id") or ""),
                "identity_candidate_id": str(value.get("identity_candidate_id") or ""),
                "identity_kind": str(value.get("identity_kind") or ""),
                "identity_label": str(value.get("identity_label") or ""),
                "identity_confidence": str(value.get("identity_confidence") or ""),
                "association_state": str(value.get("association_state") or ""),
                "matched_identity_labels": ";".join(
                    str(item) for item in value.get("matched_identity_labels") or ()
                ),
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


def _normalized_identity_text(value: object) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", str(value or "").casefold()).split())


def _contains_normalized_phrase(value: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {value} "


def _contains_unambiguous_identity_phrase(value: str, phrase: str) -> bool:
    """Reject a shorter numeric identity embedded in an explicit range/compound.

    For example, ``LOS 1`` must not be selected from ``LOS 1-3`` and ``LOS7``
    must not be selected from ``LOS7.1-7.2``.  A later exact occurrence can still
    qualify, so every token-aligned occurrence is considered independently.
    """

    value_tokens = value.split()
    phrase_tokens = phrase.split()
    if not phrase_tokens or len(phrase_tokens) > len(value_tokens):
        return False
    last_phrase_has_digit = any(character.isdigit() for character in phrase_tokens[-1])
    code_prefix = _short_identity_code_prefix(phrase_tokens)
    if code_prefix and _identity_code_occurrence_count(value_tokens, code_prefix) > 1:
        return False
    width = len(phrase_tokens)
    for start in range(len(value_tokens) - width + 1):
        if value_tokens[start : start + width] != phrase_tokens:
            continue
        next_index = start + width
        if (
            last_phrase_has_digit
            and next_index < len(value_tokens)
            and value_tokens[next_index].isdigit()
        ):
            continue
        return True
    return False


def _short_identity_code_prefix(tokens: list[str]) -> str | None:
    first_alpha = "".join(character for character in tokens[0] if character.isalpha())
    if not first_alpha or len(first_alpha) > 5:
        return None
    if any(character.isdigit() for character in tokens[0]):
        return first_alpha
    if len(tokens) > 1 and any(character.isdigit() for character in tokens[1]):
        return first_alpha
    return None


def _identity_code_occurrence_count(tokens: list[str], prefix: str) -> int:
    count = 0
    for index, token in enumerate(tokens):
        alpha = "".join(character for character in token if character.isalpha())
        if alpha != prefix:
            continue
        if any(character.isdigit() for character in token):
            count += 1
        elif index + 1 < len(tokens) and any(
            character.isdigit() for character in tokens[index + 1]
        ):
            count += 1
    return count


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
