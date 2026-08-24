"""Deterministic terminal reconciliation and conservative peer-conflict analysis."""

from __future__ import annotations

from collections import defaultdict

from .models import GuidanceCandidateVersion


def candidate_conflict_pairs(
    candidates: tuple[GuidanceCandidateVersion, ...],
) -> tuple[tuple[GuidanceCandidateVersion, GuidanceCandidateVersion], ...]:
    """Return exact candidate pairs that cannot both be authoritative.

    The detector is intentionally conservative: candidates must address the same
    kind/topic/form/field/workflow key, have overlapping applicability, and contain
    different instructions. False positives are quarantined for ConflictPolicy rather
    than silently resolved during publication.
    """

    groups: dict[tuple[str, ...], list[GuidanceCandidateVersion]] = defaultdict(list)
    for candidate in candidates:
        key = (
            candidate.kind.value,
            candidate.topic.casefold().strip(),
            (candidate.document_or_form_type or "").casefold().strip(),
            (candidate.field_or_element or "").casefold().strip(),
            (candidate.workflow_stage or "").casefold().strip(),
        )
        groups[key].append(candidate)
    pairs: list[tuple[GuidanceCandidateVersion, GuidanceCandidateVersion]] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda item: (str(item.candidate_id), item.version))
        for left_index, left in enumerate(ordered):
            left_applicability = {
                value.casefold().strip() for value in left.applicability_conditions if value.strip()
            }
            for right in ordered[left_index + 1 :]:
                if left.instruction.casefold().strip() == right.instruction.casefold().strip():
                    continue
                right_applicability = {
                    value.casefold().strip()
                    for value in right.applicability_conditions
                    if value.strip()
                }
                overlaps = (
                    not left_applicability
                    or not right_applicability
                    or bool(left_applicability & right_applicability)
                )
                if overlaps:
                    pairs.append((left, right))
    return tuple(pairs)


def latest_candidate_versions(
    candidates: tuple[GuidanceCandidateVersion, ...],
) -> dict[str, GuidanceCandidateVersion]:
    latest: dict[str, GuidanceCandidateVersion] = {}
    for candidate in candidates:
        candidate_id = str(candidate.candidate_id)
        prior = latest.get(candidate_id)
        if prior is None or candidate.version > prior.version:
            latest[candidate_id] = candidate
    return latest
