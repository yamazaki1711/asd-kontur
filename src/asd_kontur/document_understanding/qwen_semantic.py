# ruff: noqa: E501, RUF001 -- bounded Russian JSON prompts are intentionally literal.
"""Bounded, evidence-bound Qwen semantic document classification."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from http.client import IncompleteRead, RemoteDisconnected
from typing import Any
from uuid import UUID

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid

from .models import (
    CandidateDecision,
    DocumentRole,
    ExactLocator,
    LayoutElement,
    MappingStatus,
    MaterialCandidate,
    ProjectFieldCandidate,
    QuantityCandidate,
    ReconciliationDefect,
    ReconciliationDefectKind,
    RoleCandidate,
    RoleDecision,
    StructureNodeCandidate,
    StructureRelationshipCandidate,
    WorkTypeCandidate,
)
from .semantic import StructuredCandidates

QWEN_SEMANTIC_CLASSIFICATION_PROFILE = "qwen-document-semantic-v1"
QWEN_ENGINEERING_EXTRACTION_PROFILE = "qwen-engineering-extraction-v15"
# v14 adds a required relationship collection.  Prior batch manifests did not ask
# the model to inspect or report those observations, so treating them as compatible
# would silently turn missing relationship coverage into an accepted empty result.
_COMPATIBLE_ENGINEERING_EXTRACTION_PROFILES: tuple[str, ...] = ()
_MAX_PAGES = 6
_MAX_CHARS_PER_PAGE = 800
_MAX_PROMPT_CHARS = 4_800
_LEGACY_ENGINEERING_BATCH_FRAGMENTS = 12
_DENSE_ENGINEERING_BATCH_FRAGMENTS = 48
_MAX_ENGINEERING_BATCH_CHARS = 9_000
_DENSE_ENGINEERING_BATCHING_POLICY = "dense-fragments-v1"
_RECOVERABLE_ENGINEERING_BATCH_FAILURES = frozenset(
    {
        "qwen_engineering_response_invalid_json",
        "qwen_engineering_response_invalid_shape",
        "qwen_engineering_response_invalid_evidence",
        "qwen_engineering_response_invalid_kind",
        "qwen_engineering_repair_empty",
        "qwen_semantic_response_output_exhausted",
    }
)
_ENGINEERING_STRUCTURE_KINDS = frozenset(
    {"local_area", "facility", "excavation_pit", "structure", "zone"}
)


class QwenSemanticFailure(RuntimeError):
    def __init__(self, code: str, diagnostics: dict[str, object] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.diagnostics = diagnostics or {}


@dataclass(frozen=True, slots=True)
class QwenSemanticClassification:
    candidates: tuple[RoleCandidate, ...]
    decisions: tuple[RoleDecision, ...]


@dataclass(frozen=True, slots=True)
class _SemanticFragment:
    locator: ExactLocator
    text: str
    fragment_id: str | None = None
    character_start: int = 0
    character_end: int | None = None


@dataclass(frozen=True, slots=True)
class QwenEngineeringBatch:
    ordinal: int
    digest: str
    fragments: tuple[_SemanticFragment, ...]
    prompt_strategy: str = "standard"
    batching_policy_version: str | None = None

    @property
    def locator_ids(self) -> tuple[UUID, ...]:
        return tuple(item.locator.source_locator_id for item in self.fragments)

    @property
    def input_manifest(self) -> dict[str, object]:
        values: list[dict[str, object]] = []
        for item in self.fragments:
            value: dict[str, object] = {
                "fragment_id": item.fragment_id,
                "source_locator_id": str(item.locator.source_locator_id),
                "evidence_digest": item.locator.evidence_digest,
                "character_start": item.character_start,
                "character_end": item.character_end,
            }
            if self.prompt_strategy != "standard":
                value["prompt_strategy"] = self.prompt_strategy
            values.append(value)
        manifest: dict[str, object] = {
            "profile_version": QWEN_ENGINEERING_EXTRACTION_PROFILE,
            "fragments": values,
        }
        if self.batching_policy_version is not None:
            manifest["batching_policy_version"] = self.batching_policy_version
        if self.prompt_strategy != "standard":
            manifest["prompt_strategy"] = self.prompt_strategy
        return manifest


class QwenDocumentSemanticAdapter:
    """Call loopback Qwen with bounded extracted text and exact locators only."""

    def __init__(self, endpoint: str, *, timeout_seconds: float = 900.0) -> None:
        if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("qwen_semantic_endpoint_invalid")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def classify(self, elements: Iterable[LayoutElement]) -> QwenSemanticClassification:
        pages = _sample_pages(elements)
        if not pages:
            raise QwenSemanticFailure("qwen_semantic_input_unavailable")
        prompt = _prompt(pages)
        payload = _complete(self._endpoint, prompt, self._timeout_seconds)
        roles, locator_ids = _parse(
            payload, {str(item.locator.source_locator_id): item for item in pages}
        )
        locators = tuple(
            {str(item.locator.source_locator_id): item.locator for item in pages}[item]
            for item in locator_ids
        )
        source_version_id = locators[0].source_version_id
        scope = f"page:{locators[0].page_number}"
        role_candidates: list[RoleCandidate] = []
        candidate_ids: list[UUID] = []
        for role in roles:
            candidate_id = deterministic_uuid(
                f"qwen-document-role:{source_version_id}:{role.value}:"
                f"{QWEN_SEMANTIC_CLASSIFICATION_PROFILE}"
            )
            candidate_ids.append(candidate_id)
            role_candidates.append(
                RoleCandidate(
                    candidate_id=candidate_id,
                    role=role,
                    scope=scope,
                    score=Decimal("0.80"),
                    signal_codes=("qwen:bounded_document_semantic",),
                    locators=locators,
                    extraction_profile_version=QWEN_SEMANTIC_CLASSIFICATION_PROFILE,
                    model_attempt_id=deterministic_uuid(
                        f"qwen-document-role-attempt:{source_version_id}:"
                        f"{QWEN_SEMANTIC_CLASSIFICATION_PROFILE}"
                    ),
                )
            )
        decision_id = deterministic_uuid(
            f"qwen-document-role-decision:{source_version_id}:"
            f"{QWEN_SEMANTIC_CLASSIFICATION_PROFILE}"
        )
        decision = RoleDecision(
            decision_id=decision_id,
            decision_version=1,
            scope=scope,
            selected_roles=roles,
            candidate_ids=tuple(candidate_ids),
            decision_code="qwen_bounded_document_semantic",
            validator_version=QWEN_SEMANTIC_CLASSIFICATION_PROFILE,
            locators=locators,
        )
        return QwenSemanticClassification(tuple(role_candidates), (decision,))

    def extract_structures(
        self, elements: Iterable[LayoutElement]
    ) -> tuple[StructureNodeCandidate, ...]:
        pages = _sample_pages(elements)
        if not pages:
            raise QwenSemanticFailure("qwen_structure_input_unavailable")
        payload = _complete(self._endpoint, _structure_prompt(pages), self._timeout_seconds)
        allowed = {str(item.locator.source_locator_id): item for item in pages}
        observations = _parse_structures(payload, allowed)
        values: list[StructureNodeCandidate] = []
        for kind, name, locator_id in observations:
            locator = allowed[locator_id].locator
            normalized = " ".join(name.casefold().split())
            values.append(
                StructureNodeCandidate(
                    structure_node_id=deterministic_uuid(
                        f"qwen-structure:{locator.source_version_id}:{locator.source_locator_id}:"
                        f"{kind}:{normalized}:{QWEN_SEMANTIC_CLASSIFICATION_PROFILE}"
                    ),
                    node_kind=kind,
                    raw_name=name,
                    normalized_name=normalized,
                    locator=locator,
                )
            )
        return tuple(values)

    def extract_engineering(
        self,
        elements: Iterable[LayoutElement],
        *,
        accepted_batches: Mapping[str, dict[str, object]] | None = None,
        compatible_accepted_batches: Mapping[str, dict[str, object]] | None = None,
        batching_policy_version: str | None = None,
        on_accepted_batch: Callable[[QwenEngineeringBatch, dict[str, object]], None] | None = None,
        on_batch_progress: Callable[[int, int], None] | None = None,
        on_failed_batch: Callable[[QwenEngineeringBatch, str, dict[str, object]], None]
        | None = None,
    ) -> StructuredCandidates:
        """Extract evidence-bound engineering candidates from every bounded locator batch."""
        accepted = accepted_batches or {}
        compatible = compatible_accepted_batches or {}
        # Existing accepted v15 batches predate the dense packing policy. Resume
        # them with byte-identical manifests so their evidence can be reused.
        # Callers opt into dense packing explicitly; the adapter's default stays
        # legacy-compatible for direct consumers and existing tests.
        batches = _engineering_batches(
            elements,
            batching_policy_version=(None if accepted or compatible else batching_policy_version),
        )
        if not batches:
            raise QwenSemanticFailure("qwen_engineering_input_unavailable")
        extracted: list[tuple[dict[str, _SemanticFragment], dict[str, list[tuple[str, ...]]]]] = []
        for current, batch in enumerate(batches, start=1):
            extracted.extend(
                self._extract_engineering_batch(
                    batch,
                    accepted=accepted,
                    on_accepted_batch=on_accepted_batch,
                    on_failed_batch=on_failed_batch,
                    compatible_accepted_batches=compatible,
                )
            )
            if on_batch_progress is not None:
                on_batch_progress(current, len(batches))
        fields: list[ProjectFieldCandidate] = []
        structures: list[StructureNodeCandidate] = []
        structure_relationships: list[StructureRelationshipCandidate] = []
        works: list[WorkTypeCandidate] = []
        quantities: list[QuantityCandidate] = []
        materials: list[MaterialCandidate] = []
        parsed_quantities: list[tuple[str, str, str, ExactLocator, str]] = []
        incomplete_quantities: list[tuple[str, str, str, ExactLocator, str]] = []
        parsed_materials: list[tuple[str, str, str, str, ExactLocator, str]] = []
        work_by_fragment_identity: dict[tuple[str, str], WorkTypeCandidate] = {}
        works_by_name: dict[tuple[UUID, str], list[WorkTypeCandidate]] = defaultdict(list)
        works_by_fragment: dict[str, WorkTypeCandidate] = {}
        for allowed, parsed in extracted:
            for name, locator_id in parsed["works"]:
                locator = allowed[locator_id].locator
                normalized = " ".join(name.casefold().split())
                value = WorkTypeCandidate(
                    deterministic_uuid(
                        f"qwen-work:{QWEN_ENGINEERING_EXTRACTION_PROFILE}:"
                        f"{locator.source_version_id}:{locator_id}:{normalized}"
                    ),
                    name,
                    normalized,
                    f"page:{locator.page_number}",
                    locator,
                    DocumentRole.PROJECT_DOCUMENTATION,
                    MappingStatus.UNRESOLVED,
                    extraction_profile_version=QWEN_ENGINEERING_EXTRACTION_PROFILE,
                )
                identity = (locator_id, normalized)
                if identity not in work_by_fragment_identity:
                    work_by_fragment_identity[identity] = value
                    works_by_name[(locator.source_version_id, normalized)].append(value)
                    works.append(value)
                works_by_fragment[locator_id] = work_by_fragment_identity[identity]
            for key, raw, locator_id in parsed["fields"]:
                locator = allowed[locator_id].locator
                fields.append(
                    ProjectFieldCandidate(
                        deterministic_uuid(
                            f"qwen-field:{QWEN_ENGINEERING_EXTRACTION_PROFILE}:"
                            f"{locator.source_version_id}:{locator_id}:{key}:{raw}"
                        ),
                        key,
                        raw,
                        raw,
                        "text",
                        locator,
                        QWEN_ENGINEERING_EXTRACTION_PROFILE,
                        ("qwen_semantic_candidate",),
                        extraction_profile_version=QWEN_ENGINEERING_EXTRACTION_PROFILE,
                    )
                )
            for kind, name, locator_id in parsed["structures"]:
                locator = allowed[locator_id].locator
                normalized = " ".join(name.casefold().split())
                structures.append(
                    StructureNodeCandidate(
                        deterministic_uuid(
                            f"qwen-structure:{QWEN_ENGINEERING_EXTRACTION_PROFILE}:"
                            f"{locator.source_version_id}:{locator_id}:{kind}:{normalized}"
                        ),
                        kind,
                        name,
                        normalized,
                        locator,
                        extraction_profile_version=QWEN_ENGINEERING_EXTRACTION_PROFILE,
                    )
                )
            for kind, subject_name, object_name, locator_id in parsed["structure_relationships"]:
                locator = allowed[locator_id].locator
                normalized_subject = " ".join(subject_name.casefold().split())
                normalized_object = " ".join(object_name.casefold().split())
                structure_relationships.append(
                    StructureRelationshipCandidate(
                        deterministic_uuid(
                            "qwen-structure-relationship:"
                            f"{QWEN_ENGINEERING_EXTRACTION_PROFILE}:"
                            f"{locator.source_version_id}:{locator_id}:{kind}:"
                            f"{normalized_subject}:{normalized_object}"
                        ),
                        kind,
                        subject_name,
                        normalized_subject,
                        object_name,
                        normalized_object,
                        locator,
                        extraction_profile_version=QWEN_ENGINEERING_EXTRACTION_PROFILE,
                    )
                )
            for work_name, raw, unit, locator_id, work_fragment_id in parsed["quantities"]:
                locator = allowed[locator_id].locator
                parsed_quantities.append((work_name, raw, unit, locator, work_fragment_id))
            for work_name, raw, unit, locator_id, work_fragment_id in parsed[
                "incomplete_quantities"
            ]:
                locator = allowed[locator_id].locator
                incomplete_quantities.append((work_name, raw, unit, locator, work_fragment_id))
            for work_name, name, raw, unit, locator_id, work_fragment_id in parsed["materials"]:
                locator = allowed[locator_id].locator
                parsed_materials.append((work_name, name, raw, unit, locator, work_fragment_id))
        defects: list[ReconciliationDefect] = []
        for work_name, raw, unit, locator, work_fragment_id in incomplete_quantities:
            defects.append(
                ReconciliationDefect(
                    deterministic_uuid(
                        "qwen-incomplete-quantity-candidate:"
                        f"{QWEN_ENGINEERING_EXTRACTION_PROFILE}:{locator.source_version_id}:"
                        f"{locator.source_locator_id}:"
                        f"{work_name}:{raw}:{unit}:{work_fragment_id}"
                    ),
                    ReconciliationDefectKind.AMBIGUOUS_SOURCE_MATCH,
                    f"qwen_quantity:{locator.source_locator_id}",
                    " ".join(work_name.casefold().split()) or None,
                    (locator,),
                    {
                        "code": "incomplete_quantity_candidate",
                        "work_name": work_name or None,
                        "raw_value": raw or None,
                        "unit": unit or None,
                        "work_fragment_id": work_fragment_id or None,
                    },
                    False,
                    QWEN_ENGINEERING_EXTRACTION_PROFILE,
                )
            )
        for work_name, raw, unit, locator, work_fragment_id in parsed_quantities:
            work, defect = _resolve_work_reference(
                work_name,
                locator,
                work_fragment_id,
                works_by_name,
                works_by_fragment,
                relationship_kind="quantity",
                payload={"value": raw, "unit": unit},
                extraction_profile_version=QWEN_ENGINEERING_EXTRACTION_PROFILE,
            )
            if work is None:
                if defect is not None:
                    defects.append(defect)
                continue
            try:
                parsed_value = Decimal(raw.replace(",", "."))
            except InvalidOperation:
                parsed_value = None
            quantities.append(
                QuantityCandidate(
                    deterministic_uuid(
                        f"qwen-quantity:{locator.source_version_id}:{locator.source_locator_id}:"
                        f"{work.candidate_id}:{raw}:{unit}"
                    ),
                    work.candidate_id,
                    raw,
                    parsed_value,
                    unit,
                    parsed_value,
                    unit if parsed_value is not None else None,
                    None,
                    work.scope_key,
                    locator,
                    CandidateDecision.CANDIDATE,
                )
            )
        for work_name, name, raw, unit, locator, work_fragment_id in parsed_materials:
            work, defect = _resolve_work_reference(
                work_name,
                locator,
                work_fragment_id,
                works_by_name,
                works_by_fragment,
                relationship_kind="material",
                payload={"name": name, "quantity": raw, "unit": unit},
                extraction_profile_version=QWEN_ENGINEERING_EXTRACTION_PROFILE,
            )
            if work is None:
                if defect is not None:
                    defects.append(defect)
                continue
            try:
                parsed_value = Decimal(raw.replace(",", "."))
            except InvalidOperation:
                parsed_value = None
            materials.append(
                MaterialCandidate(
                    deterministic_uuid(
                        f"qwen-material:{locator.source_version_id}:{locator.source_locator_id}:"
                        f"{work.candidate_id}:{name}"
                    ),
                    work.candidate_id,
                    name,
                    " ".join(name.casefold().split()),
                    raw or None,
                    parsed_value,
                    unit or None,
                    unit or None,
                    locator,
                    CandidateDecision.CANDIDATE,
                )
            )
        return StructuredCandidates(
            tuple(fields),
            tuple(works),
            tuple(quantities),
            tuple(materials),
            (),
            tuple(defects),
            tuple(structures),
            tuple(structure_relationships),
        )

    def accepted_batch_candidates(
        self, batch: QwenEngineeringBatch, manifest: Mapping[str, object]
    ) -> StructuredCandidates:
        """Materialize only source-backed observations from one accepted batch.

        This is deliberately a partial view.  Quantities and materials can refer
        to a work emitted in another batch, so they remain in the immutable batch
        receipt until the complete-source pass reconciles their work reference.
        Fields, structures, relationships, and work observations have exact local
        evidence and deterministic identifiers and can safely be made visible
        while Qwen continues with the remaining batches.
        """
        allowed = _engineering_allowed_fragments(batch.fragments)
        parsed = _parse_engineering_manifest(dict(manifest), allowed)
        fields: list[ProjectFieldCandidate] = []
        structures: list[StructureNodeCandidate] = []
        relationships: list[StructureRelationshipCandidate] = []
        works: list[WorkTypeCandidate] = []
        seen_works: set[tuple[str, str]] = set()
        for key, raw, locator_id in parsed["fields"]:
            locator = allowed[locator_id].locator
            fields.append(
                ProjectFieldCandidate(
                    deterministic_uuid(
                        f"qwen-field:{QWEN_ENGINEERING_EXTRACTION_PROFILE}:"
                        f"{locator.source_version_id}:{locator_id}:{key}:{raw}"
                    ),
                    key,
                    raw,
                    raw,
                    "text",
                    locator,
                    QWEN_ENGINEERING_EXTRACTION_PROFILE,
                    ("qwen_semantic_candidate",),
                    extraction_profile_version=QWEN_ENGINEERING_EXTRACTION_PROFILE,
                )
            )
        for kind, name, locator_id in parsed["structures"]:
            locator = allowed[locator_id].locator
            normalized = " ".join(name.casefold().split())
            structures.append(
                StructureNodeCandidate(
                    deterministic_uuid(
                        f"qwen-structure:{QWEN_ENGINEERING_EXTRACTION_PROFILE}:"
                        f"{locator.source_version_id}:{locator_id}:{kind}:{normalized}"
                    ),
                    kind,
                    name,
                    normalized,
                    locator,
                    extraction_profile_version=QWEN_ENGINEERING_EXTRACTION_PROFILE,
                )
            )
        for kind, subject_name, object_name, locator_id in parsed["structure_relationships"]:
            locator = allowed[locator_id].locator
            subject = " ".join(subject_name.casefold().split())
            object_ = " ".join(object_name.casefold().split())
            relationships.append(
                StructureRelationshipCandidate(
                    deterministic_uuid(
                        "qwen-structure-relationship:"
                        f"{QWEN_ENGINEERING_EXTRACTION_PROFILE}:"
                        f"{locator.source_version_id}:{locator_id}:{kind}:{subject}:{object_}"
                    ),
                    kind,
                    subject_name,
                    subject,
                    object_name,
                    object_,
                    locator,
                    extraction_profile_version=QWEN_ENGINEERING_EXTRACTION_PROFILE,
                )
            )
        for name, locator_id in parsed["works"]:
            locator = allowed[locator_id].locator
            normalized = " ".join(name.casefold().split())
            identity = (locator_id, normalized)
            if identity in seen_works:
                continue
            seen_works.add(identity)
            works.append(
                WorkTypeCandidate(
                    deterministic_uuid(
                        f"qwen-work:{QWEN_ENGINEERING_EXTRACTION_PROFILE}:"
                        f"{locator.source_version_id}:{locator_id}:{normalized}"
                    ),
                    name,
                    normalized,
                    f"page:{locator.page_number}",
                    locator,
                    DocumentRole.PROJECT_DOCUMENTATION,
                    MappingStatus.UNRESOLVED,
                    extraction_profile_version=QWEN_ENGINEERING_EXTRACTION_PROFILE,
                )
            )
        return StructuredCandidates(
            tuple(fields),
            tuple(works),
            (),
            (),
            (),
            (),
            tuple(structures),
            tuple(relationships),
        )

    def accepted_source_batch_candidates(
        self,
        elements: Iterable[LayoutElement],
        *,
        accepted_batches: Mapping[str, dict[str, object]],
        batching_policy_version: str | None = None,
    ) -> tuple[StructuredCandidates, ...]:
        """Recover publishable candidates from already accepted exact manifests.

        No Qwen call is made.  The batch digest is regenerated from the current
        elements and the persisted policy, so a changed source or batching
        contract cannot accidentally materialize an unrelated receipt.
        """
        batches = _engineering_batches(
            elements,
            batching_policy_version=(None if accepted_batches else batching_policy_version),
        )
        return tuple(
            self.accepted_batch_candidates(batch, manifest)
            for batch in batches
            if (manifest := accepted_batches.get(batch.digest)) is not None
        )

    def _extract_engineering_batch(
        self,
        batch: QwenEngineeringBatch,
        *,
        accepted: Mapping[str, dict[str, object]],
        compatible_accepted_batches: Mapping[str, dict[str, object]],
        on_accepted_batch: Callable[[QwenEngineeringBatch, dict[str, object]], None] | None,
        on_failed_batch: Callable[[QwenEngineeringBatch, str, dict[str, object]], None] | None,
    ) -> tuple[tuple[dict[str, _SemanticFragment], dict[str, list[tuple[str, ...]]]], ...]:
        allowed = _engineering_allowed_fragments(batch.fragments)
        persisted = accepted.get(batch.digest)
        if persisted is None and batch.prompt_strategy == "standard":
            for profile_version in _COMPATIBLE_ENGINEERING_EXTRACTION_PROFILES:
                persisted = compatible_accepted_batches.get(
                    _compatible_batch_digest(batch.fragments, profile_version)
                )
                if persisted is not None:
                    break
        if persisted is not None:
            return ((allowed, _parse_engineering_manifest(persisted, allowed)),)
        # A failed parent batch can already have fully accepted standard child
        # batches from its bounded recovery.  Reuse those exact child manifests
        # instead of asking Qwen to repeat the failed parent request during a
        # dependent extraction stage.
        recovered_children = _split_engineering_batch(batch)
        if recovered_children and all(
            _accepted_engineering_batch_available(
                child,
                accepted=accepted,
                compatible_accepted_batches=compatible_accepted_batches,
            )
            for child in recovered_children
        ):
            recovered_values: list[
                tuple[dict[str, _SemanticFragment], dict[str, list[tuple[str, ...]]]]
            ] = []
            for child in recovered_children:
                recovered_values.extend(
                    self._extract_engineering_batch(
                        child,
                        accepted=accepted,
                        compatible_accepted_batches=compatible_accepted_batches,
                        on_accepted_batch=on_accepted_batch,
                        on_failed_batch=on_failed_batch,
                    )
                )
            return tuple(recovered_values)
        payload = ""
        try:
            payload = _complete(
                self._endpoint,
                _engineering_prompt(batch.fragments, strategy=batch.prompt_strategy),
                self._timeout_seconds,
                max_tokens=350 if batch.prompt_strategy != "standard" else 1_200,
            )
            parsed = _parse_engineering(payload, allowed)
        except QwenSemanticFailure as exc:
            if (
                batch.prompt_strategy == "standard"
                and exc.code in _RECOVERABLE_ENGINEERING_BATCH_FAILURES
            ):
                try:
                    repaired = _complete(
                        self._endpoint,
                        _engineering_evidence_repair_prompt(batch.fragments, payload),
                        self._timeout_seconds,
                        max_tokens=1_200,
                    )
                    parsed = _parse_engineering(repaired, allowed)
                    if not _has_engineering_observations(parsed):
                        raise QwenSemanticFailure("qwen_engineering_repair_empty")
                except QwenSemanticFailure as repair_exc:
                    failure = repair_exc
                else:
                    repair_batch = _engineering_batch(
                        batch.ordinal,
                        batch.fragments,
                        prompt_strategy="evidence_reference_and_kind_repair-v2",
                        batching_policy_version=batch.batching_policy_version,
                    )
                    if on_accepted_batch is not None:
                        on_accepted_batch(repair_batch, _engineering_manifest(parsed))
                    return ((allowed, parsed),)
            else:
                failure = exc
            if on_failed_batch is not None:
                on_failed_batch(batch, failure.code, failure.diagnostics)
            if failure.code not in _RECOVERABLE_ENGINEERING_BATCH_FAILURES:
                raise failure from None
            if len(batch.fragments) == 1:
                if batch.prompt_strategy != "standard":
                    # This is the bounded terminal recovery attempt for one exact
                    # source fragment.  Its failed receipt is already durable via
                    # ``on_failed_batch``.  Do not let one malformed model output
                    # discard independently accepted evidence from the source or
                    # starve other eligible documents.  Coverage remains partial:
                    # the failed batch is deliberately not returned as an accepted
                    # manifest and the caller can expose its typed failure.
                    return ()
                return self._extract_engineering_batch(
                    _engineering_batch(
                        batch.ordinal,
                        batch.fragments,
                        prompt_strategy="single_fragment_repair-v1",
                        batching_policy_version=batch.batching_policy_version,
                    ),
                    accepted=accepted,
                    compatible_accepted_batches=compatible_accepted_batches,
                    on_accepted_batch=on_accepted_batch,
                    on_failed_batch=on_failed_batch,
                )
            values: list[tuple[dict[str, _SemanticFragment], dict[str, list[tuple[str, ...]]]]] = []
            for child in _split_engineering_batch(batch):
                values.extend(
                    self._extract_engineering_batch(
                        child,
                        accepted=accepted,
                        on_accepted_batch=on_accepted_batch,
                        on_failed_batch=on_failed_batch,
                        compatible_accepted_batches=compatible_accepted_batches,
                    )
                )
            return tuple(values)
        if on_accepted_batch is not None:
            on_accepted_batch(batch, _engineering_manifest(parsed))
        return ((allowed, parsed),)


def _resolve_work_reference(
    work_name: str,
    locator: ExactLocator,
    work_fragment_id: str,
    works_by_name: Mapping[tuple[UUID, str], list[WorkTypeCandidate]],
    works_by_fragment: Mapping[str, WorkTypeCandidate],
    *,
    relationship_kind: str,
    payload: dict[str, str],
    extraction_profile_version: str = QWEN_ENGINEERING_EXTRACTION_PROFILE,
) -> tuple[WorkTypeCandidate | None, ReconciliationDefect | None]:
    normalized = " ".join(work_name.casefold().split())
    candidates = list(works_by_name.get((locator.source_version_id, normalized), ()))
    resolution = "source_name"
    if work_fragment_id:
        fragment_candidate = works_by_fragment.get(work_fragment_id)
        if fragment_candidate is not None and fragment_candidate.normalized_name == normalized:
            candidates = [fragment_candidate]
            resolution = "work_fragment_id"
    if len(candidates) != 1:
        page_candidates = [
            item for item in candidates if item.scope_key == f"page:{locator.page_number}"
        ]
        if len(page_candidates) == 1:
            candidates = page_candidates
            resolution = "page_scope"
    if len(candidates) == 1:
        return candidates[0], None
    candidate_ids = tuple(sorted(str(item.candidate_id) for item in candidates))
    defect = ReconciliationDefect(
        deterministic_uuid(
            f"qwen-unresolved-work-reference:{extraction_profile_version}:{relationship_kind}:"
            f"{locator.source_version_id}:"
            f"{locator.source_locator_id}:{normalized}:{payload}:{candidate_ids}"
        ),
        ReconciliationDefectKind.AMBIGUOUS_SOURCE_MATCH,
        f"qwen_{relationship_kind}:{locator.source_locator_id}",
        normalized or None,
        (locator,),
        {
            "code": "unresolved_work_reference",
            "relationship_kind": relationship_kind,
            "work_name": work_name,
            "work_fragment_id": work_fragment_id or None,
            "resolution_attempt": resolution,
            "candidate_work_ids": list(candidate_ids),
            "payload": payload,
        },
        False,
        extraction_profile_version,
    )
    return None, defect


def _sample_pages(elements: Iterable[LayoutElement]) -> tuple[_SemanticFragment, ...]:
    by_page: dict[int, list[LayoutElement]] = defaultdict(list)
    for element in elements:
        if element.normalized_text:
            by_page[element.locator.page_number].append(element)
    sampled: list[_SemanticFragment] = []
    used = 0
    for page_number in sorted(by_page)[:_MAX_PAGES]:
        page_elements = by_page[page_number]
        text = " ".join(item.normalized_text for item in page_elements)
        if not text:
            continue
        if used + min(len(text), _MAX_CHARS_PER_PAGE) > _MAX_PROMPT_CHARS:
            break
        sampled.append(_SemanticFragment(page_elements[0].locator, text[:_MAX_CHARS_PER_PAGE]))
        used += min(len(text), _MAX_CHARS_PER_PAGE)
    return tuple(sampled)


def _fragments(elements: Iterable[LayoutElement]) -> tuple[_SemanticFragment, ...]:
    fragments: list[_SemanticFragment] = []
    for item in elements:
        text = item.normalized_text
        for offset in range(0, len(text), 2_400):
            end = min(offset + 2_400, len(text))
            fragments.append(
                _SemanticFragment(
                    item.locator,
                    text[offset:end],
                    str(
                        deterministic_uuid(
                            f"qwen-engineering-fragment:{item.locator.source_version_id}:"
                            f"{item.locator.source_locator_id}:{item.locator.evidence_digest}:"
                            f"{offset}:{end}"
                        )
                    ),
                    offset,
                    end,
                )
            )
    return tuple(fragments)


def _engineering_batches(
    elements: Iterable[LayoutElement], *, batching_policy_version: str | None = None
) -> tuple[QwenEngineeringBatch, ...]:
    if batching_policy_version not in {None, _DENSE_ENGINEERING_BATCHING_POLICY}:
        raise ValueError("qwen_engineering_batching_policy_unsupported")
    fragments = _fragments(elements)
    max_fragments = (
        _LEGACY_ENGINEERING_BATCH_FRAGMENTS
        if batching_policy_version is None
        else _DENSE_ENGINEERING_BATCH_FRAGMENTS
    )
    batches: list[QwenEngineeringBatch] = []
    current: list[_SemanticFragment] = []
    current_chars = 0
    for fragment in fragments:
        if current and (
            len(current) >= max_fragments
            or current_chars + len(fragment.text) > _MAX_ENGINEERING_BATCH_CHARS
        ):
            batches.append(
                _engineering_batch(
                    len(batches) + 1,
                    tuple(current),
                    batching_policy_version=batching_policy_version,
                )
            )
            current = []
            current_chars = 0
        current.append(fragment)
        current_chars += len(fragment.text)
    if current:
        batches.append(
            _engineering_batch(
                len(batches) + 1,
                tuple(current),
                batching_policy_version=batching_policy_version,
            )
        )
    return tuple(batches)


def _engineering_batch(
    ordinal: int,
    fragments: tuple[_SemanticFragment, ...],
    *,
    prompt_strategy: str = "standard",
    batching_policy_version: str | None = None,
) -> QwenEngineeringBatch:
    batch_payload = _engineering_batch_payload(fragments)
    digest_input: dict[str, object] = {
        "profile_version": QWEN_ENGINEERING_EXTRACTION_PROFILE,
        "fragments": batch_payload,
    }
    if prompt_strategy != "standard":
        digest_input["prompt_strategy"] = prompt_strategy
    if batching_policy_version is not None:
        digest_input["batching_policy_version"] = batching_policy_version
    return QwenEngineeringBatch(
        ordinal,
        semantic_digest(digest_input),
        fragments,
        prompt_strategy,
        batching_policy_version,
    )


def _engineering_batch_payload(fragments: tuple[_SemanticFragment, ...]) -> list[dict[str, object]]:
    return [
        {
            "fragment_id": item.fragment_id,
            "locator_id": str(item.locator.source_locator_id),
            "evidence_digest": item.locator.evidence_digest,
            "character_start": item.character_start,
            "character_end": item.character_end,
            "text": item.text,
        }
        for item in fragments
    ]


def _compatible_batch_digest(fragments: tuple[_SemanticFragment, ...], profile_version: str) -> str:
    return semantic_digest(
        {
            "profile_version": profile_version,
            "fragments": _engineering_batch_payload(fragments),
        }
    )


def _accepted_engineering_batch_available(
    batch: QwenEngineeringBatch,
    *,
    accepted: Mapping[str, dict[str, object]],
    compatible_accepted_batches: Mapping[str, dict[str, object]],
) -> bool:
    if batch.digest in accepted:
        return True
    return any(
        _compatible_batch_digest(batch.fragments, profile_version) in compatible_accepted_batches
        for profile_version in _COMPATIBLE_ENGINEERING_EXTRACTION_PROFILES
    )


def _split_engineering_batch(batch: QwenEngineeringBatch) -> tuple[QwenEngineeringBatch, ...]:
    midpoint = len(batch.fragments) // 2
    if midpoint < 1:
        return ()
    return (
        _engineering_batch(
            batch.ordinal * 100 + 1,
            batch.fragments[:midpoint],
            batching_policy_version=batch.batching_policy_version,
        ),
        _engineering_batch(
            batch.ordinal * 100 + 2,
            batch.fragments[midpoint:],
            batching_policy_version=batch.batching_policy_version,
        ),
    )


def _engineering_manifest(parsed: dict[str, list[tuple[str, ...]]]) -> dict[str, object]:
    return {key: [list(item) for item in values] for key, values in parsed.items()}


def _has_engineering_observations(parsed: Mapping[str, list[tuple[str, ...]]]) -> bool:
    return any(parsed.values())


def _engineering_allowed_fragments(
    fragments: tuple[_SemanticFragment, ...],
) -> dict[str, _SemanticFragment]:
    allowed: dict[str, _SemanticFragment] = {}
    for ordinal, fragment in enumerate(fragments, start=1):
        if fragment.fragment_id is None:
            continue
        allowed[str(fragment.fragment_id)] = fragment
        allowed[f"F{ordinal}"] = fragment
    locator_counts: dict[str, int] = defaultdict(int)
    for fragment in fragments:
        locator_counts[str(fragment.locator.source_locator_id)] += 1
    # Some local Qwen responses preserve a provided locator UUID rather than the
    # short prompt alias.  Accept it only when it identifies exactly one input
    # fragment; otherwise it would lose the split-fragment attribution boundary.
    for fragment in fragments:
        locator_id = str(fragment.locator.source_locator_id)
        if locator_counts[locator_id] == 1:
            allowed[locator_id] = fragment
    return allowed


def _engineering_prompt(
    elements: tuple[_SemanticFragment, ...], *, strategy: str = "standard"
) -> str:
    fragments = [
        {
            "fragment_id": f"F{ordinal}",
            "page": item.locator.page_number,
            "character_start": item.character_start,
            "character_end": item.character_end,
            "text": item.text,
        }
        for ordinal, item in enumerate(elements, start=1)
    ]
    prompt = (
        "Извлеки только явно подтверждённые инженерные кандидаты. Верни один JSON: "
        '{"fields":[{"key":"...","value":"...","fragment_id":"..."}],'
        '"structures":[{"kind":"local_area|facility|excavation_pit|structure|zone","name":"...","fragment_id":"..."}],'
        '"structure_relationships":[{"kind":"contains|located_in|serves|connects_to|depends_on","subject_name":"...","object_name":"...","fragment_id":"..."}],'
        '"works":[{"name":"...","fragment_id":"..."}],'
        '"quantities":[{"work_name":"...","value":"...","unit":"...","fragment_id":"...","work_fragment_id":"..."}],'
        '"materials":[{"work_name":"...","name":"...","quantity":"...","unit":"...","fragment_id":"...","work_fragment_id":"..."}]}. '
        "Все шесть ключей JSON обязательны, даже если соответствующий массив пуст. "
        "quantity и unit материала, а также work_fragment_id, могут быть пустыми строками, "
        "если источник их не указывает или имя работы дано только вне этого пакета. "
        "Для quantity пустые work_name, value или unit означают неполное наблюдение: "
        "всё равно укажи fragment_id, чтобы оно было сохранено как вопрос, "
        "fragment_id обязан быть одним из коротких идентификаторов F1, F2 и т.д. во входе: "
        "копируй его буквально, без точки, двоеточия, пробела или другого текста. "
        "work_fragment_id, если не пуст, также обязан быть одним из них. Если нет факта, массив пуст.\nФРАГМЕНТЫ:\n"
        + json.dumps(fragments, ensure_ascii=False, separators=(",", ":"))
    )
    if strategy == "single_fragment_repair-v1":
        return (
            "Исправь только формат доказательства для одного входного фрагмента. "
            "Верни полный JSON по указанной схеме. fragment_id копируй только точно из входа; "
            "если фрагмент не подтверждает кандидат, верни соответствующий пустой массив. "
            "Не используй locator_id как fragment_id.\n" + prompt
        )
    return prompt


def _engineering_evidence_repair_prompt(
    elements: tuple[_SemanticFragment, ...], prior_answer: str
) -> str:
    """Ask Qwen to correct evidence references without accepting the invalid output."""

    return (
        "Исправь только JSON ниже: сохрани только кандидаты, которые уже есть в ответе и "
        "привяжи каждый к одному допустимому fragment_id. Верни полный JSON с шестью обязательными "
        "массивами fields, structures, structure_relationships, works, quantities, materials. Для fragment_id используй только "
        "буквальные F1, F2 и т.д. из списка; если доказательство сопоставить нельзя, удали этот "
        "кандидат. Не добавляй новые инженерные сведения. Для structures kind допустимы только "
        "local_area, facility, excavation_pit, structure, zone. Для structure_relationships kind "
        "допустимы только contains, located_in, serves, connects_to, depends_on. Если исходный kind "
        "не переводится в один из этих точных вариантов без догадки, удали кандидат.\n"
        "ДОПУСТИМЫЕ ФРАГМЕНТЫ:\n"
        + json.dumps(
            [
                {
                    "fragment_id": f"F{ordinal}",
                    "page": fragment.locator.page_number,
                    "character_start": fragment.character_start,
                    "character_end": fragment.character_end,
                }
                for ordinal, fragment in enumerate(elements, start=1)
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\nНЕКОРРЕКТНЫЙ ОТВЕТ ДЛЯ ИСПРАВЛЕНИЯ:\n"
        + prior_answer
    )


def _parse_engineering(
    answer: str, allowed: dict[str, _SemanticFragment]
) -> dict[str, list[tuple[str, ...]]]:
    try:
        value = _json_object(answer)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_engineering_response_invalid_json") from exc
    if not isinstance(value, dict) or set(value) != {
        "fields",
        "structures",
        "structure_relationships",
        "works",
        "quantities",
        "materials",
    }:
        raise QwenSemanticFailure("qwen_engineering_response_invalid_shape")
    result: dict[str, list[tuple[str, ...]]] = {
        "fields": [],
        "structures": [],
        "structure_relationships": [],
        "works": [],
        "quantities": [],
        "incomplete_quantities": [],
        "materials": [],
    }
    specs = {
        "fields": ("key", "value", "fragment_id"),
        "structures": ("kind", "name", "fragment_id"),
        "structure_relationships": (
            "kind",
            "subject_name",
            "object_name",
            "fragment_id",
        ),
        "works": ("name", "fragment_id"),
        "quantities": ("work_name", "value", "unit", "fragment_id", "work_fragment_id"),
        "materials": (
            "work_name",
            "name",
            "quantity",
            "unit",
            "fragment_id",
            "work_fragment_id",
        ),
    }
    for key, names in specs.items():
        rows = value.get(key, [])
        if not isinstance(rows, list) or len(rows) > 64:
            raise QwenSemanticFailure("qwen_engineering_response_invalid_shape")
        for row_ordinal, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise QwenSemanticFailure("qwen_engineering_response_invalid_shape")
            item = _normalize_engineering_evidence_aliases(
                key,
                tuple(" ".join(str(row.get(name, "")).split()) for name in names),
            )
            if key == "quantities" and _engineering_quantity_evidence_valid(item, allowed):
                item = _canonicalize_engineering_item(key, item, allowed)
                if all(item[:3]):
                    result[key].append(item)
                else:
                    result["incomplete_quantities"].append(item)
                continue
            if not _engineering_item_valid(key, item, allowed):
                raise QwenSemanticFailure(
                    "qwen_engineering_response_invalid_evidence",
                    {
                        "collection": key,
                        "row_ordinal": row_ordinal,
                        "evidence_references": _engineering_evidence_references(key, item),
                    },
                )
            item = _canonicalize_engineering_item(key, item, allowed)
            if key == "structures" and item[0] not in _ENGINEERING_STRUCTURE_KINDS:
                raise QwenSemanticFailure("qwen_engineering_response_invalid_kind")
            if key == "structure_relationships" and item[0] not in {
                "contains",
                "located_in",
                "serves",
                "connects_to",
                "depends_on",
            }:
                raise QwenSemanticFailure("qwen_engineering_response_invalid_kind")
            result[key].append(item)
    return result


def _normalize_engineering_evidence_aliases(key: str, item: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize only harmless terminal punctuation on short prompt aliases.

    This is deliberately narrower than fuzzy locator matching: a model cannot
    turn an arbitrary label into evidence, and an unknown or ambiguous reference
    remains a typed extraction failure.
    """

    locator_positions = {
        "fields": (2,),
        "structures": (2,),
        "structure_relationships": (3,),
        "works": (1,),
        "quantities": (3, 4),
        "materials": (4, 5),
    }[key]
    values = list(item)
    for position in locator_positions:
        value = values[position]
        if re.fullmatch(r"F[1-9][0-9]*[.,;:]", value, flags=re.IGNORECASE):
            values[position] = value[:-1].upper()
    return tuple(values)


def _engineering_evidence_references(key: str, item: tuple[str, ...]) -> list[str]:
    return [
        item[position]
        for position in {
            "fields": (2,),
            "structures": (2,),
            "structure_relationships": (3,),
            "works": (1,),
            "quantities": (3, 4),
            "materials": (4, 5),
        }[key]
        if item[position]
    ]


def _canonicalize_engineering_item(
    key: str, item: tuple[str, ...], allowed: Mapping[str, _SemanticFragment]
) -> tuple[str, ...]:
    locator_positions = {
        "fields": (2,),
        "structures": (2,),
        "structure_relationships": (3,),
        "works": (1,),
        "quantities": (3, 4),
        "materials": (4, 5),
    }[key]
    values = list(item)
    for position in locator_positions:
        if values[position]:
            fragment = allowed[values[position]]
            if fragment.fragment_id is None:
                raise QwenSemanticFailure("qwen_engineering_response_invalid_evidence")
            values[position] = str(fragment.fragment_id)
    return tuple(values)


def _parse_engineering_manifest(
    manifest: dict[str, object], allowed: dict[str, _SemanticFragment]
) -> dict[str, list[tuple[str, ...]]]:
    result: dict[str, list[tuple[str, ...]]] = {
        "fields": [],
        "structures": [],
        "structure_relationships": [],
        "works": [],
        "quantities": [],
        "incomplete_quantities": [],
        "materials": [],
    }
    specs = {
        "fields": ("key", "value", "fragment_id"),
        "structures": ("kind", "name", "fragment_id"),
        "structure_relationships": (
            "kind",
            "subject_name",
            "object_name",
            "fragment_id",
        ),
        "works": ("name", "fragment_id"),
        "quantities": ("work_name", "value", "unit", "fragment_id", "work_fragment_id"),
        "incomplete_quantities": (
            "work_name",
            "value",
            "unit",
            "fragment_id",
            "work_fragment_id",
        ),
        "materials": (
            "work_name",
            "name",
            "quantity",
            "unit",
            "fragment_id",
            "work_fragment_id",
        ),
    }
    for key, names in specs.items():
        rows = manifest.get(key, [])
        if not isinstance(rows, list) or len(rows) > 64:
            raise QwenSemanticFailure("qwen_engineering_manifest_invalid_shape")
        for row in rows:
            if not isinstance(row, list) or len(row) != len(names):
                raise QwenSemanticFailure("qwen_engineering_manifest_invalid_shape")
            item = tuple(" ".join(str(value).split()) for value in row)
            if key == "incomplete_quantities":
                if not _engineering_quantity_evidence_valid(item, allowed) or all(item[:3]):
                    raise QwenSemanticFailure("qwen_engineering_manifest_invalid_evidence")
            elif not _engineering_item_valid(key, item, allowed):
                raise QwenSemanticFailure("qwen_engineering_manifest_invalid_evidence")
            if key == "structures" and item[0] not in _ENGINEERING_STRUCTURE_KINDS:
                raise QwenSemanticFailure("qwen_engineering_manifest_invalid_kind")
            if key == "structure_relationships" and item[0] not in {
                "contains",
                "located_in",
                "serves",
                "connects_to",
                "depends_on",
            }:
                raise QwenSemanticFailure("qwen_engineering_manifest_invalid_kind")
            result[key].append(item)
    return result


def _engineering_item_valid(
    key: str, item: tuple[str, ...], allowed: dict[str, _SemanticFragment]
) -> bool:
    if key in {"fields", "structures", "works"}:
        return all(item) and item[-1] in allowed
    if key == "structure_relationships":
        return all(item) and item[-1] in allowed
    if key == "quantities":
        work_name, raw_value, unit, fragment_id, work_fragment_id = item
        return (
            bool(work_name and raw_value and unit)
            and fragment_id in allowed
            and (not work_fragment_id or work_fragment_id in allowed)
        )
    if key == "materials":
        work_name, name, _raw_quantity, _unit, fragment_id, work_fragment_id = item
        return (
            bool(work_name and name)
            and fragment_id in allowed
            and (not work_fragment_id or work_fragment_id in allowed)
        )
    return False


def _engineering_quantity_evidence_valid(
    item: tuple[str, ...], allowed: Mapping[str, _SemanticFragment]
) -> bool:
    """Validate quantity provenance independently from the observation's completeness.

    A cited but incomplete quantity is a durable unresolved observation, not a
    quantity candidate and not a reason to discard the entire semantic batch.
    """

    _work_name, _raw_value, _unit, fragment_id, work_fragment_id = item
    return fragment_id in allowed and (not work_fragment_id or work_fragment_id in allowed)


def _prompt(elements: tuple[_SemanticFragment, ...]) -> str:
    pages = [
        {
            "page": item.locator.page_number,
            "locator_id": str(item.locator.source_locator_id),
            "text": item.text,
        }
        for item in elements
    ]
    return (
        "Ты выполняешь ограниченную классификацию строительного документа. "
        "Используй только приведённые фрагменты. Верни первой и единственной строкой JSON "
        "без Markdown: "
        '{"roles":["..."],"locator_ids":["..."]}. '
        "roles — от одного до трёх точных значений из: explanatory_note, "
        "project_documentation, working_documentation, bill_of_quantities, local_estimate, "
        "object_estimate, consolidated_estimate, specification, contract, customer_regulation, "
        "normative_reference_list, executive_documentation, drawing_or_scheme, "
        "correspondence_administrative, unknown. locator_ids должны ссылаться только на "
        "фрагменты, подтверждающие выбранные roles. Не придумывай данные.\nФРАГМЕНТЫ:\n"
        + json.dumps(pages, ensure_ascii=False, separators=(",", ":"))
    )


def _structure_prompt(elements: tuple[_SemanticFragment, ...]) -> str:
    pages = [
        {
            "page": item.locator.page_number,
            "locator_id": str(item.locator.source_locator_id),
            "text": item.text,
        }
        for item in elements
    ]
    return (
        "Извлеки только явно обозначенные элементы структуры строительного объекта из фрагментов. "
        'Верни только JSON без Markdown: {"structures":[{"kind":"...","name":"...",'
        '"locator_id":"..."}]}. Допустимые kind: excavation_pit, structure, zone. '
        "Котлован включай только если фрагмент прямо устанавливает отдельный экземпляр, "
        "а не типовое решение или общее слово. locator_id обязан быть одним из входных. "
        "Не придумывай геометрию, количество, связи или имена. Если подтверждённых "
        "элементов нет, верни пустой массив.\nФРАГМЕНТЫ:\n"
        + json.dumps(pages, ensure_ascii=False, separators=(",", ":"))
    )


def _complete(endpoint: str, prompt: str, timeout_seconds: float, *, max_tokens: int = 350) -> str:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(
            {"prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}, ensure_ascii=False
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    parts: list[str] = []
    completed = False
    limit_reached = False
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            while line := response.readline():
                event = json.loads(line)
                if event.get("event") == "delta":
                    parts.append(str(event.get("text", "")))
                elif event.get("event") == "completed":
                    completed = True
                    limit_reached = bool(event.get("limit_reached", False))
                    break
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
        IncompleteRead,
        RemoteDisconnected,
        json.JSONDecodeError,
    ) as exc:
        raise QwenSemanticFailure("qwen_semantic_runtime_unavailable") from exc
    answer = "".join(parts).strip()
    if not completed or not answer:
        raise QwenSemanticFailure("qwen_semantic_response_incomplete")
    if limit_reached:
        raise QwenSemanticFailure("qwen_semantic_response_output_exhausted")
    return answer


def _parse(
    answer: str, allowed: dict[str, _SemanticFragment]
) -> tuple[tuple[DocumentRole, ...], tuple[str, ...]]:
    try:
        value = _json_object(answer)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_semantic_response_invalid_json") from exc
    if not isinstance(value, dict):
        raise QwenSemanticFailure("qwen_semantic_response_invalid_shape")
    raw_roles = value.get("roles")
    raw_locator_ids = value.get("locator_ids")
    if not isinstance(raw_roles, list) or not isinstance(raw_locator_ids, list):
        raise QwenSemanticFailure("qwen_semantic_response_invalid_shape")
    try:
        roles = tuple(DocumentRole(str(item)) for item in raw_roles)
    except ValueError as exc:
        raise QwenSemanticFailure("qwen_semantic_response_invalid_role") from exc
    locator_ids = tuple(str(item) for item in raw_locator_ids)
    if not 1 <= len(roles) <= 3 or len(set(roles)) != len(roles):
        raise QwenSemanticFailure("qwen_semantic_response_invalid_role")
    if not locator_ids or len(set(locator_ids)) != len(locator_ids):
        raise QwenSemanticFailure("qwen_semantic_response_invalid_locator")
    if any(item not in allowed for item in locator_ids):
        raise QwenSemanticFailure("qwen_semantic_response_invalid_locator")
    return roles, locator_ids


def _parse_structures(
    answer: str, allowed: dict[str, _SemanticFragment]
) -> tuple[tuple[str, str, str], ...]:
    try:
        value = _json_object(answer)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_structure_response_invalid_json") from exc
    rows = value.get("structures") if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) > 32:
        raise QwenSemanticFailure("qwen_structure_response_invalid_shape")
    observed: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise QwenSemanticFailure("qwen_structure_response_invalid_shape")
        kind = str(row.get("kind", ""))
        name = " ".join(str(row.get("name", "")).split())
        locator_id = str(row.get("locator_id", ""))
        if kind not in {"excavation_pit", "structure", "zone"}:
            raise QwenSemanticFailure("qwen_structure_response_invalid_kind")
        if not 2 <= len(name) <= 500 or locator_id not in allowed:
            raise QwenSemanticFailure("qwen_structure_response_invalid_evidence")
        item = (kind, name, locator_id)
        if item in seen:
            continue
        seen.add(item)
        observed.append(item)
    return tuple(observed)


def _json_object(answer: str) -> Any:
    """Accept one JSON object even when the local model wraps it in harmless prose."""
    text = answer.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0].strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise json.JSONDecodeError("JSON object not found", text, 0)
