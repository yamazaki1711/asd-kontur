"""Evidence-aware project identity reconciliation.

Project-wide identity fields must not be inferred from an arbitrary facility
mention.  This module keeps reviewed/deterministic verified values above model
candidates and exposes repeatable multi-source consensus only as a candidate.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

PROJECT_IDENTITY_ALIASES: dict[str, frozenset[str]] = {
    "object_name": frozenset({"object_name", "project_name"}),
    "purpose": frozenset({"purpose"}),
    "object_composition": frozenset({"object_composition"}),
    "object_class": frozenset({"object_class", "printed_class"}),
}


def reconcile_project_identity_fields(
    fields: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Separate verified project fields from source-backed candidate consensus.

    A verified value wins over any number of unverified model observations.  In
    the absence of a verified value, a candidate is exposed only when the same
    normalized value occurs in at least two source versions and has strictly
    greater source support than every alternative.  The candidate is never
    promoted to a verified field by this function.
    """

    rows = [dict(value) for value in fields]
    verified_fields: dict[str, dict[str, Any]] = {}
    candidate_fields: dict[str, dict[str, Any]] = {}
    outcomes: dict[str, dict[str, Any]] = {}
    for canonical_key, aliases in PROJECT_IDENTITY_ALIASES.items():
        candidates = [row for row in rows if str(row.get("field_key")) in aliases]
        if not candidates:
            outcomes[canonical_key] = {"state": "missing", "candidate_ids": []}
            continue
        verified = [row for row in candidates if str(row.get("status")) == "verified"]
        verified_groups = _group_values(verified)
        if len(verified_groups) == 1:
            group = next(iter(verified_groups.values()))
            selected = _field_payload(group, authority="verified")
            verified_fields[canonical_key] = selected
            outcomes[canonical_key] = {
                "state": "verified",
                "candidate_ids": _candidate_ids(candidates),
                "selected_candidate_id": selected["candidate_id"],
                "selected_candidate_version": selected["candidate_version"],
            }
            continue
        if len(verified_groups) > 1:
            outcomes[canonical_key] = {
                "state": "verified_conflict",
                "candidate_ids": _candidate_ids(candidates),
            }
            continue

        groups = _group_values(candidates)
        ranked = sorted(
            groups.values(),
            key=lambda group: (
                -len({str(row["source_version_id"]) for row in group}),
                -len(group),
                _value_key(group[0].get("normalized_value")),
            ),
        )
        source_count = len({str(row["source_version_id"]) for row in ranked[0]})
        runner_up_source_count = (
            len({str(row["source_version_id"]) for row in ranked[1]}) if len(ranked) > 1 else 0
        )
        if source_count >= 2 and source_count > runner_up_source_count:
            selected = _field_payload(ranked[0], authority="candidate_consensus")
            selected["alternative_value_count"] = max(0, len(ranked) - 1)
            candidate_fields[canonical_key] = selected
            outcomes[canonical_key] = {
                "state": "candidate_consensus",
                "candidate_ids": _candidate_ids(candidates),
                "selected_candidate_id": None,
                "selected_candidate_version": None,
            }
        else:
            outcomes[canonical_key] = {
                "state": "candidate_conflict" if len(ranked) > 1 else "candidate_only",
                "candidate_ids": _candidate_ids(candidates),
            }
    return {
        "verified_fields": verified_fields,
        "candidate_fields": candidate_fields,
        "outcomes": outcomes,
    }


def _group_values(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[_value_key(row.get("normalized_value"))].append(row)
    return groups


def _value_key(value: Any) -> str:
    if not isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")  # noqa: RUF001
    normalized = normalized.translate({ord(character): '"' for character in ("«", "»", "„", "“")})
    normalized = re.sub(r"\s*([.,:;])\s*", r"\1 ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(' \t\r\n".,;:')
    return normalized


def _field_payload(group: list[dict[str, Any]], *, authority: str) -> dict[str, Any]:
    raw_counts = Counter(str(row.get("raw_value") or "") for row in group)
    representative = min(
        group,
        key=lambda row: (
            -raw_counts[str(row.get("raw_value") or "")],
            -len(str(row.get("raw_value") or "")),
            str(row.get("candidate_id") or ""),
        ),
    )
    source_version_ids = sorted({str(row["source_version_id"]) for row in group})
    source_locator_ids = sorted({str(row["source_locator_id"]) for row in group})
    return {
        "raw_value": representative.get("raw_value"),
        "normalized_value": representative.get("normalized_value"),
        "source_version_id": str(representative["source_version_id"]),
        "source_locator_id": str(representative["source_locator_id"]),
        "candidate_id": str(representative["candidate_id"]),
        "candidate_version": int(representative.get("version", 1)),
        "source_version_ids": source_version_ids,
        "source_locator_ids": source_locator_ids,
        "source_count": len(source_version_ids),
        "observation_count": len(group),
        "authority": authority,
    }


def _candidate_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted({str(row["candidate_id"]) for row in rows})
