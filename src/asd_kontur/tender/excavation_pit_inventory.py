"""Source-backed excavation-pit candidate inventory.

The projection deliberately recognizes only an explicit association written in
the observation name (for example, ``котлован для КНС 4``). Generic mentions,
trenches, boreholes, and inferred facility relationships remain unresolved.
That makes the resulting count useful as an established candidate subset while
preventing it from being presented as a complete project total.
"""

# ruff: noqa: RUF002 -- Russian construction terms are intentional.

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from asd_kontur.application_spine.models import semantic_digest

_EXPLICIT_FACILITY_PIT = re.compile(
    r"\b(?P<pit>котлован|pit)\b(?P<prefix>.*?)\bдля\b\s*"
    r"(?P<kind>лос|кнс)\s*[-№nº]*\s*"
    r"(?P<number>\d+(?:\s*[.]\s*\d+)?)\b",
    flags=re.IGNORECASE | re.UNICODE,
)


def _explicit_pit_identity(raw_name: str) -> tuple[str, str, str] | None:
    match = _EXPLICIT_FACILITY_PIT.search(raw_name)
    if match is None:
        return None
    kind = match.group("kind").upper()
    number = re.sub(r"\s+", "", match.group("number"))
    designation = f"{kind} {number}"
    canonical_text = raw_name[: match.start("kind")] + designation + raw_name[match.end("number") :]
    normalized_label = re.sub(r"[^\w]+", " ", canonical_text.casefold(), flags=re.UNICODE).strip()
    return f"{kind.casefold()}:{number}", designation, normalized_label


def build_excavation_pit_inventory(
    structure_nodes: Iterable[Mapping[str, Any]],
    *,
    unresolved_sample_limit: int = 20,
) -> dict[str, Any]:
    """Return explicit pit candidates and preserve every unresolved observation."""

    if unresolved_sample_limit < 0:
        raise ValueError("excavation_pit_unresolved_sample_limit_invalid")
    pit_nodes = [
        dict(node)
        for node in structure_nodes
        if str(node.get("node_kind") or "") == "excavation_pit"
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    unresolved: list[dict[str, Any]] = []
    for node in pit_nodes:
        raw_name = str(node.get("raw_name") or "").strip()
        identity = _explicit_pit_identity(raw_name)
        if identity is None:
            unresolved.append(node)
            continue
        facility_key, _designation, normalized_label = identity
        grouped[(facility_key, normalized_label)].append(node)

    candidates: list[dict[str, Any]] = []
    for (facility_key, normalized_label), members in grouped.items():
        identity = _explicit_pit_identity(str(members[0].get("raw_name") or ""))
        if identity is None:  # pragma: no cover - guarded while grouping.
            continue
        _key, designation, _label = identity
        node_ids = sorted(
            {
                str(member["structure_node_id"])
                for member in members
                if member.get("structure_node_id") is not None
            }
        )
        locator_ids = sorted(
            {
                str(member["source_locator_id"])
                for member in members
                if member.get("source_locator_id") is not None
            }
        )
        aliases = sorted(
            {
                str(member.get("raw_name") or "").strip()
                for member in members
                if str(member.get("raw_name") or "").strip()
            }
        )
        candidate_payload = {
            "contract": "excavation-pit-explicit-association-candidate-v1",
            "facility_designation_key": facility_key,
            "normalized_pit_label": normalized_label,
            "member_structure_node_ids": node_ids,
        }
        candidates.append(
            {
                "pit_candidate_id": semantic_digest(candidate_payload),
                "identity_candidate_id": semantic_digest(candidate_payload),
                "identity_kind": "excavation_pit",
                "canonical_label": aliases[0],
                "display_name": aliases[0],
                "associated_facility_designation": designation,
                "associated_facility_designation_key": facility_key,
                "aliases": aliases,
                "member_structure_node_ids": node_ids,
                "source_locator_ids": locator_ids,
                "observation_count": len(node_ids),
                "status": "candidate",
                "candidate_state": "explicit_source_association_candidate",
                "authority": "candidate_only_not_confirmed_distinct_project_entity",
            }
        )
    candidates.sort(
        key=lambda value: (
            str(value["associated_facility_designation_key"]),
            str(value["canonical_label"]),
        )
    )
    unresolved.sort(
        key=lambda value: (
            str(value.get("raw_name") or ""),
            str(value.get("structure_node_id") or ""),
        )
    )
    return {
        "candidate_pits": candidates,
        "unresolved_observations": unresolved[:unresolved_sample_limit],
        "coverage": {
            "total_pit_observation_count": len(pit_nodes),
            "explicit_facility_association_observation_count": sum(
                int(candidate["observation_count"]) for candidate in candidates
            ),
            "unresolved_observation_count": len(unresolved),
            "returned_unresolved_observation_count": min(len(unresolved), unresolved_sample_limit),
            "candidate_pit_count": len(candidates),
            "exact_total_supported": False,
            "count_meaning": ("distinct_explicit_source_association_candidates_not_project_total"),
            "candidate_authority": "candidate_only",
        },
    }
