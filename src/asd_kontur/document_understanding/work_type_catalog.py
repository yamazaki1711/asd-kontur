"""Exact, provenance-preserving work-type catalog resolution."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


def normalize_work_type_label(value: object) -> str:
    """Normalize typography only; semantic or fuzzy matching is forbidden."""

    return " ".join(str(value).split()).casefold()


def resolve_work_type_candidates(
    candidates: Iterable[Mapping[str, Any]],
    catalog_entries: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Bind exact catalog names or aliases to one canonical work-type version.

    Multiple verified catalogs may bind the same canonical identity. That is
    one resolution and every catalog provenance record is retained. A label
    that maps to different identities, versions, or stable keys is ambiguous.
    """

    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for value in catalog_entries:
        entry = dict(value)
        labels = {
            normalize_work_type_label(entry["normalized_name"]),
            normalize_work_type_label(entry["printed_name"]),
            *(normalize_work_type_label(item) for item in entry.get("aliases", ())),
        }
        for label in labels:
            if label:
                by_label[label].append(entry)

    result: list[dict[str, Any]] = []
    for value in candidates:
        candidate = dict(value)
        for key in (
            "canonical_work_type_id",
            "canonical_work_type_version",
            "canonical_work_type_key",
            "work_type_catalog_bindings",
            "work_type_catalog_matches",
        ):
            candidate.pop(key, None)
        matches = by_label.get(normalize_work_type_label(candidate.get("normalized_name", "")), ())
        identities = {
            (
                str(item["work_type_id"]),
                str(item["work_type_version"]),
                str(item["work_type_key"]),
            )
            for item in matches
        }
        bindings = sorted(
            (
                {
                    "catalog_id": str(item["catalog_id"]),
                    "catalog_version": int(item["catalog_version"]),
                    "catalog_fingerprint": str(item["catalog_fingerprint"]),
                }
                for item in matches
            ),
            key=lambda item: (item["catalog_id"], item["catalog_version"]),
        )
        if len(identities) == 1:
            identity, version, stable_key = next(iter(identities))
            candidate.update(
                {
                    "canonical_mapping_status": "resolved",
                    "canonical_work_type_id": identity,
                    "canonical_work_type_version": version,
                    "canonical_work_type_key": stable_key,
                    "work_type_catalog_bindings": bindings,
                }
            )
        elif identities:
            candidate.update(
                {
                    "canonical_mapping_status": "ambiguous",
                    "canonical_work_type_id": None,
                    "work_type_catalog_matches": [
                        {
                            "work_type_id": identity,
                            "work_type_version": version,
                            "work_type_key": stable_key,
                        }
                        for identity, version, stable_key in sorted(identities)
                    ],
                    "work_type_catalog_bindings": bindings,
                }
            )
        else:
            candidate.update(
                {
                    "canonical_mapping_status": "unresolved",
                    "canonical_work_type_id": None,
                }
            )
        result.append(candidate)
    return result
