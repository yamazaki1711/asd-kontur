"""Source-backed excavation-pit candidate inventory.

The projection deliberately recognizes only an explicit association written in
the observation name (for example, ``котлован для КНС 4``). Generic mentions,
trenches, boreholes, and inferred facility relationships remain unresolved.
That makes the resulting count useful as an established candidate subset while
preventing it from being presented as a complete project total.
"""

# ruff: noqa: RUF001, RUF002 -- Russian construction terms are intentional.

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

_NON_PIT_OBSERVATION = re.compile(
    r"(?:\bскв(?:ажин(?:а|ы|у|е|ой)?)?\.?\b|\bтранше\w*\b|"
    r"\bвыемк\w*\b|\bшурф\w*\b|\bприямк\w*\b)",
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
    identity_candidates: Iterable[Mapping[str, Any]] = (),
    unresolved_sample_limit: int = 20,
) -> dict[str, Any]:
    """Return scoped pit candidates and preserve every unresolved observation.

    Structure identity results are candidate evidence, not authority.  They are
    consumed only when they refer to excavation-pit members and retain a source
    association that this projection can validate.  Boreholes, trenches and
    related excavation terms remain unresolved observations rather than being
    promoted to distinct pits.
    """

    if unresolved_sample_limit < 0:
        raise ValueError("excavation_pit_unresolved_sample_limit_invalid")
    pit_nodes = [
        dict(node)
        for node in structure_nodes
        if str(node.get("node_kind") or "") == "excavation_pit"
    ]
    identity_rows = [dict(candidate) for candidate in identity_candidates]
    node_by_id = {
        str(node.get("structure_node_id")): node
        for node in pit_nodes
        if node.get("structure_node_id") is not None
    }
    identity_rejected = 0
    identity_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in identity_rows:
        if str(candidate.get("identity_kind") or "") != "excavation_pit":
            continue
        label = str(candidate.get("canonical_label") or "").strip()
        member_ids = [str(value) for value in candidate.get("member_structure_node_ids") or ()]
        if not label or not member_ids or _NON_PIT_OBSERVATION.search(label):
            identity_rejected += 1
            continue
        for member_id in member_ids:
            if member_id in node_by_id:
                identity_by_node[member_id].append(dict(candidate))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    unresolved: list[dict[str, Any]] = []
    non_pit_observation_count = 0
    generic_observation_count = 0
    identity_enriched_observation_count = 0
    for node in pit_nodes:
        raw_name = str(node.get("raw_name") or "").strip()
        identity = _explicit_pit_identity(raw_name)
        if identity is None and identity_by_node.get(str(node.get("structure_node_id"))):
            # A Qwen identity candidate can enrich a source-backed explicit
            # association only; it cannot turn a generic label into a pit.
            for candidate in identity_by_node[str(node.get("structure_node_id"))]:
                candidate_identity = _explicit_pit_identity(
                    str(candidate.get("canonical_label") or "")
                )
                if candidate_identity is not None:
                    identity = candidate_identity
                    identity_enriched_observation_count += 1
                    break
        if identity is None:
            if _NON_PIT_OBSERVATION.search(raw_name):
                non_pit_observation_count += 1
            else:
                generic_observation_count += 1
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
            "identity_candidate_count": sum(
                1
                for candidate in identity_rows
                if str(candidate.get("identity_kind") or "") == "excavation_pit"
            ),
            "identity_rejected_non_pit_count": identity_rejected,
            "identity_enriched_observation_count": identity_enriched_observation_count,
            "non_pit_observation_count": non_pit_observation_count,
            "generic_observation_count": generic_observation_count,
            "exact_total_supported": False,
            "count_meaning": ("distinct_explicit_source_association_candidates_not_project_total"),
            "candidate_authority": "candidate_only",
        },
    }
