"""Deterministic construction of task-oriented ID practice intelligence.

The constructor only restructures already verified methodological guidance. It
does not infer normative obligations, project facts, missing work types, or NTD
editions. Missing structure remains explicit uncertainty.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID

from asd_kontur.domain import canonical_semantic_key, deterministic_uuid
from asd_kontur.harness.models import digest_of

from .models import (
    GuidanceKind,
    GuideLocator,
    IDPracticeIntelligenceUnit,
    PracticeIntelligenceEvidence,
    PracticeIntelligenceKind,
    PracticePlaybook,
)

CONSTRUCTION_PROFILE_VERSION = "id-practice-intelligence-semantic-v0.4.0"
SEMANTIC_IDENTITY_SCHEMA_VERSION = "practice-intelligence-semantic-identity-v0.2.0"

PRIMARY_KIND = {
    GuidanceKind.ID_WORKFLOW_GUIDANCE: PracticeIntelligenceKind.ID_WORKFLOW_STEP,
    GuidanceKind.DOCUMENT_FORM_GUIDANCE: PracticeIntelligenceKind.FORM_COMPLETION_GUIDANCE,
    GuidanceKind.FORM_FIELD_GUIDANCE: PracticeIntelligenceKind.FIELD_COMPLETION_GUIDANCE,
    GuidanceKind.COMPLETION_INSTRUCTION: PracticeIntelligenceKind.COMPLETION_INSTRUCTION,
    GuidanceKind.REQUIRED_INPUT_GUIDANCE: PracticeIntelligenceKind.COMPLETENESS_GUIDANCE,
    GuidanceKind.EVIDENCE_REQUIREMENT_GUIDANCE: (PracticeIntelligenceKind.VERIFICATION_CHECKLIST),
    GuidanceKind.SIGNER_ROLE_GUIDANCE: PracticeIntelligenceKind.SIGNER_ROLE_GUIDANCE,
    GuidanceKind.COMMON_ERROR: PracticeIntelligenceKind.COMMON_FAILURE_PATTERN,
    GuidanceKind.GOOD_PRACTICE_ASSERTION: PracticeIntelligenceKind.ID_PRACTICE_PRINCIPLE,
    GuidanceKind.VISUAL_INSTRUCTION: PracticeIntelligenceKind.VISUAL_COMPLETION_EXAMPLE,
    GuidanceKind.EXAMPLE_REFERENCE: PracticeIntelligenceKind.VISUAL_COMPLETION_EXAMPLE,
    GuidanceKind.CROSS_REFERENCE: PracticeIntelligenceKind.DOCUMENT_DEPENDENCY_GUIDANCE,
    GuidanceKind.GUIDE_NTD_RELEVANCE_ASSERTION: (
        PracticeIntelligenceKind.DOCUMENT_DEPENDENCY_GUIDANCE
    ),
}

MEMBER_ROLE = {
    PracticeIntelligenceKind.ID_PRACTICE_PRINCIPLE: "principle",
    PracticeIntelligenceKind.ID_WORKFLOW_STEP: "workflow_step",
    PracticeIntelligenceKind.FORM_COMPLETION_GUIDANCE: "form_guidance",
    PracticeIntelligenceKind.FIELD_COMPLETION_GUIDANCE: "field_guidance",
    PracticeIntelligenceKind.ATTENTION_POINT: "attention_point",
    PracticeIntelligenceKind.ALLOWED_PRACTICE_VARIANT: "allowed_variant",
    PracticeIntelligenceKind.PRACTICE_RATIONALE: "rationale",
    PracticeIntelligenceKind.COMMON_FAILURE_PATTERN: "failure_pattern",
    PracticeIntelligenceKind.VERIFICATION_CHECKLIST: "checklist",
    PracticeIntelligenceKind.COMPLETENESS_GUIDANCE: "completeness",
    PracticeIntelligenceKind.JOURNAL_SELECTION_GUIDANCE: "journal_selection",
    PracticeIntelligenceKind.DOCUMENT_DEPENDENCY_GUIDANCE: "dependency",
    PracticeIntelligenceKind.COMPLETION_INSTRUCTION: "completion_instruction",
    PracticeIntelligenceKind.SIGNER_ROLE_GUIDANCE: "signer_guidance",
    PracticeIntelligenceKind.VISUAL_COMPLETION_EXAMPLE: "visual_example",
}

ROLE_ORDER = {role: index for index, role in enumerate(dict.fromkeys(MEMBER_ROLE.values()), 1)}

VARIANT_MARKERS = ("допуска", "вариант", "можно ", " либо ", " или ")
RATIONALE_MARKERS = ("потому", "для того", "чтобы ", "позвол", "во избежание", "обеспеч")
JOURNAL_MARKERS = ("журнал",)
JOURNAL_SELECTION_MARKERS = ("выбор", "несколько", "отдельн", "общий", "специальн", "вид работ")


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _evidence(values: object) -> tuple[PracticeIntelligenceEvidence, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("Constructed intelligence requires source evidence")
    result: dict[tuple[UUID, int, UUID, int, tuple[float, ...]], PracticeIntelligenceEvidence] = {}
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("Practice-intelligence evidence is malformed")
        region = value.get("region")
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            raise ValueError("Practice-intelligence evidence region is malformed")
        item = PracticeIntelligenceEvidence(
            guidance_unit_id=UUID(str(value["guidance_unit_id"])),
            guidance_unit_version=int(value["guidance_unit_version"]),
            source_version_id=UUID(str(value["source_version_id"])),
            locator=GuideLocator(
                int(value["page_number"]),
                tuple(float(item) for item in region),  # type: ignore[arg-type]
            ),
            fragment_digest=str(value["fragment_digest"]),
        )
        key = (
            item.guidance_unit_id,
            item.guidance_unit_version,
            item.source_version_id,
            item.locator.page_number,
            item.locator.region,
        )
        existing = result.get(key)
        if existing is not None and existing.fragment_digest != item.fragment_digest:
            raise ValueError("Duplicate evidence locator has conflicting fragment digests")
        result[key] = item
    return tuple(result.values())


def _normative_references(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _contains_any(text: str, markers: Sequence[str]) -> bool:
    folded = text.casefold()
    return any(marker in folded for marker in markers)


def _canonical_terms(values: Sequence[str]) -> tuple[str, ...]:
    """Canonicalize set-like semantic dimensions independently of processing order."""

    return tuple(sorted({canonical_semantic_key(value) for value in values if value.strip()}))


def semantic_identity_payload(
    unit: IDPracticeIntelligenceUnit,
    *,
    practice_guide_id: UUID,
    authority_layer: str = "methodological_practice",
) -> dict[str, Any]:
    """Return the canonical evidence-bound identity of one practice assertion.

    Attempt/candidate/guidance UUIDs, build/release identities, timestamps and processing order
    are excluded.  Edition, exact source version, locator, fragment digest and every typed
    semantic dimension are included.  Consequently an idempotent duplicate occurrence at the
    same evidence location converges, while equal prose at another location or edition does not.
    """

    normative = sorted(
        (dict(value) for value in unit.normative_references),
        key=digest_of,
    )
    evidence_scope = sorted(
        {
            digest_of(
                {
                    "practice_guide_edition_id": str(unit.practice_guide_edition_id),
                    "source_version_id": str(evidence.source_version_id),
                    "page_number": evidence.locator.page_number,
                    "region": list(evidence.locator.region),
                    "fragment_digest": evidence.fragment_digest,
                }
            ): {
                "practice_guide_edition_id": str(unit.practice_guide_edition_id),
                "source_version_id": str(evidence.source_version_id),
                "page_number": evidence.locator.page_number,
                "region": list(evidence.locator.region),
                "fragment_digest": evidence.fragment_digest,
            }
            for evidence in unit.evidence
        }.values(),
        key=digest_of,
    )
    if not evidence_scope:
        raise ValueError("PracticeIntelligence identity requires exact source evidence")
    return {
        "schema_version": SEMANTIC_IDENTITY_SCHEMA_VERSION,
        "practice_guide_id": str(practice_guide_id),
        "practice_guide_edition_id": str(unit.practice_guide_edition_id),
        "evidence_scope": evidence_scope,
        "typed_kind": unit.kind.value,
        "subject": canonical_semantic_key(unit.title),
        "predicate": unit.kind.value,
        "object": canonical_semantic_key(unit.instruction),
        "unit": canonical_semantic_key(unit.semantic_unit) if unit.semantic_unit else None,
        "dimension": (
            canonical_semantic_key(unit.semantic_dimension) if unit.semantic_dimension else None
        ),
        "modality": canonical_semantic_key(unit.modality),
        "applicability": _canonical_terms(unit.applicability_conditions),
        "qualifiers": {
            "work_types": _canonical_terms(unit.work_types),
            "document_types": _canonical_terms(unit.document_types),
            "form_types": _canonical_terms(unit.form_types),
            "workflow_stages": _canonical_terms(unit.workflow_stages),
            "field_elements": _canonical_terms(unit.field_elements),
            "required_inputs": _canonical_terms(unit.required_inputs),
            "evidence_requirements": _canonical_terms(unit.evidence_requirements),
            "allowed_variants": _canonical_terms(unit.allowed_variants),
            "failure_patterns": _canonical_terms(unit.failure_patterns),
            "checklist_items": _canonical_terms(unit.checklist_items),
            "dependency_refs": _canonical_terms(unit.dependency_refs),
            "normative_references": normative,
            "rationale": (
                canonical_semantic_key(unit.rationale) if unit.rationale is not None else None
            ),
        },
        "exclusions": _canonical_terms(unit.uncertainties),
        "authority_layer": authority_layer,
    }


def semantic_identity_digest(
    unit: IDPracticeIntelligenceUnit,
    *,
    practice_guide_id: UUID,
    authority_layer: str = "methodological_practice",
) -> str:
    return digest_of(
        semantic_identity_payload(
            unit,
            practice_guide_id=practice_guide_id,
            authority_layer=authority_layer,
        )
    )


def deduplicate_semantic_units(
    units: Sequence[IDPracticeIntelligenceUnit], *, practice_guide_id: UUID
) -> tuple[IDPracticeIntelligenceUnit, ...]:
    grouped: dict[str, list[IDPracticeIntelligenceUnit]] = defaultdict(list)
    for unit in units:
        grouped[semantic_identity_digest(unit, practice_guide_id=practice_guide_id)].append(unit)

    result: list[IDPracticeIntelligenceUnit] = []
    for semantic_digest, occurrences in sorted(grouped.items()):
        first = occurrences[0]
        evidence_by_key: dict[
            tuple[UUID, int, UUID, int, tuple[float, float, float, float]],
            PracticeIntelligenceEvidence,
        ] = {}
        for occurrence in occurrences:
            for evidence in occurrence.evidence:
                key = (
                    evidence.guidance_unit_id,
                    evidence.guidance_unit_version,
                    evidence.source_version_id,
                    evidence.locator.page_number,
                    evidence.locator.region,
                )
                prior = evidence_by_key.get(key)
                if prior is not None and prior.fragment_digest != evidence.fragment_digest:
                    raise ValueError("Semantic identity has conflicting evidence at one locator")
                evidence_by_key[key] = evidence
        merged_evidence = tuple(
            value
            for _, value in sorted(
                evidence_by_key.items(),
                key=lambda item: (
                    item[0][3],
                    item[0][4],
                    str(item[0][0]),
                    item[0][1],
                ),
            )
        )
        result.append(
            replace(
                first,
                intelligence_unit_id=deterministic_uuid(
                    f"{SEMANTIC_IDENTITY_SCHEMA_VERSION}:{practice_guide_id}:{semantic_digest}"
                ),
                evidence=merged_evidence,
                construction_profile_version=CONSTRUCTION_PROFILE_VERSION,
            )
        )
    return tuple(result)


def _unit(
    *,
    row: Mapping[str, Any],
    edition_id: UUID,
    coverage_manifest_id: UUID,
    kind: PracticeIntelligenceKind,
    role: str,
    instruction: str,
    evidence: tuple[PracticeIntelligenceEvidence, ...],
) -> IDPracticeIntelligenceUnit:
    guidance_id = UUID(str(row["guidance_unit_id"]))
    guidance_version = int(row["version"])
    form = str(row.get("document_or_form_type") or "").strip()
    field = str(row.get("field_or_element") or "").strip()
    workflow = str(row.get("workflow_stage") or "").strip()
    normative_references = _normative_references(row.get("normative_references"))
    uncertainties = list(_strings(row.get("uncertainties")))
    if not normative_references:
        uncertainties.append("NORMATIVE_REFERENCE_NOT_ASSERTED")
    if not form:
        uncertainties.append("DOCUMENT_OR_FORM_TYPE_NOT_STRUCTURED")
    if not workflow:
        uncertainties.append("WORKFLOW_STAGE_NOT_STRUCTURED")
    uncertainties.append("WORK_TYPE_NOT_STRUCTURED")
    required_inputs = _strings(row.get("required_inputs"))
    evidence_requirements = _strings(row.get("evidence_requirements"))
    common_error = str(row.get("common_error") or "").strip()
    limitations = _strings(row.get("limitations"))
    allowed_variants = (
        (instruction,) if kind is PracticeIntelligenceKind.ALLOWED_PRACTICE_VARIANT else ()
    )
    failure_patterns = (
        (common_error or instruction,)
        if kind is PracticeIntelligenceKind.COMMON_FAILURE_PATTERN
        else ()
    )
    checklist_items = (
        tuple(dict.fromkeys((*evidence_requirements, instruction)))
        if kind is PracticeIntelligenceKind.VERIFICATION_CHECKLIST
        else ()
    )
    dependency_refs = (
        tuple(dict.fromkeys((*required_inputs, instruction)))
        if kind is PracticeIntelligenceKind.DOCUMENT_DEPENDENCY_GUIDANCE
        else ()
    )
    rationale = instruction if kind is PracticeIntelligenceKind.PRACTICE_RATIONALE else None
    title = str(row.get("topic") or row.get("section") or kind.value).strip()
    identity_seed = (
        f"kg-id-intelligence-v2:{coverage_manifest_id}:{guidance_id}:{guidance_version}:"
        f"{kind.value}:{role}"
    )
    return IDPracticeIntelligenceUnit(
        intelligence_unit_id=deterministic_uuid(identity_seed),
        version=1,
        practice_guide_edition_id=edition_id,
        coverage_manifest_id=coverage_manifest_id,
        kind=kind,
        title=title,
        instruction=instruction,
        rationale=rationale,
        applicability_conditions=_strings(row.get("applicability_conditions")),
        work_types=(),
        document_types=(form,) if form else (),
        form_types=(form,) if form and (field or "form" in kind.value) else (),
        workflow_stages=(workflow,) if workflow else (),
        field_elements=(field,) if field else (),
        required_inputs=required_inputs,
        evidence_requirements=evidence_requirements,
        allowed_variants=allowed_variants,
        failure_patterns=failure_patterns,
        checklist_items=checklist_items,
        dependency_refs=dependency_refs,
        normative_references=normative_references,
        uncertainties=tuple(dict.fromkeys((*uncertainties, *limitations))),
        evidence=evidence,
        construction_profile_version=CONSTRUCTION_PROFILE_VERSION,
    )


def construct_practice_intelligence(
    *,
    guidance_rows: Iterable[Mapping[str, Any]],
    practice_guide_id: UUID,
    edition_id: UUID,
    coverage_manifest_id: UUID,
    publication_status: str,
) -> tuple[tuple[IDPracticeIntelligenceUnit, ...], tuple[PracticePlaybook, ...]]:
    """Construct typed units and playbooks without semantic invention."""

    units: list[IDPracticeIntelligenceUnit] = []
    for row in guidance_rows:
        guidance_kind = GuidanceKind(str(row["guidance_kind"]))
        evidence = _evidence(row.get("evidence"))
        instruction = str(row["normalized_instruction"]).strip()
        if not instruction:
            raise ValueError("Verified guidance cannot construct an empty intelligence unit")
        requested: dict[PracticeIntelligenceKind, tuple[str, str]] = {
            PRIMARY_KIND[guidance_kind]: ("primary", instruction)
        }
        required_inputs = _strings(row.get("required_inputs"))
        evidence_requirements = _strings(row.get("evidence_requirements"))
        common_error = str(row.get("common_error") or "").strip()
        recommended = str(row.get("recommended_practice") or "").strip()
        limitations = _strings(row.get("limitations"))
        combined = " ".join((instruction, recommended, *limitations)).strip()
        form_and_topic = " ".join(
            str(row.get(name) or "") for name in ("document_or_form_type", "topic", "section")
        )

        if required_inputs:
            requested.setdefault(
                PracticeIntelligenceKind.COMPLETENESS_GUIDANCE,
                ("required_inputs", instruction),
            )
            requested.setdefault(
                PracticeIntelligenceKind.DOCUMENT_DEPENDENCY_GUIDANCE,
                ("required_input_dependencies", instruction),
            )
        if evidence_requirements:
            requested.setdefault(
                PracticeIntelligenceKind.VERIFICATION_CHECKLIST,
                ("evidence_checklist", instruction),
            )
        if common_error:
            requested.setdefault(
                PracticeIntelligenceKind.COMMON_FAILURE_PATTERN,
                ("common_error", common_error),
            )
        if recommended or limitations:
            attention = recommended or "; ".join(limitations)
            requested.setdefault(
                PracticeIntelligenceKind.ATTENTION_POINT,
                ("recommended_or_limited", attention),
            )
        if _contains_any(combined, VARIANT_MARKERS):
            requested.setdefault(
                PracticeIntelligenceKind.ALLOWED_PRACTICE_VARIANT,
                ("explicit_variant_language", recommended or instruction),
            )
        if _contains_any(combined, RATIONALE_MARKERS):
            requested.setdefault(
                PracticeIntelligenceKind.PRACTICE_RATIONALE,
                ("explicit_rationale_language", recommended or instruction),
            )
        if _contains_any(form_and_topic, JOURNAL_MARKERS) and _contains_any(
            combined, JOURNAL_SELECTION_MARKERS
        ):
            requested.setdefault(
                PracticeIntelligenceKind.JOURNAL_SELECTION_GUIDANCE,
                ("explicit_journal_selection_language", instruction),
            )
        for kind, (role, value) in requested.items():
            units.append(
                _unit(
                    row=row,
                    edition_id=edition_id,
                    coverage_manifest_id=coverage_manifest_id,
                    kind=kind,
                    role=role,
                    instruction=value,
                    evidence=evidence,
                )
            )

    units = list(deduplicate_semantic_units(units, practice_guide_id=practice_guide_id))
    units.sort(
        key=lambda value: (value.evidence[0].locator.page_number, str(value.intelligence_unit_id))
    )
    grouped: dict[tuple[str, str], list[IDPracticeIntelligenceUnit]] = defaultdict(list)
    for unit in units:
        form = unit.document_types[0] if unit.document_types else ""
        workflow = unit.workflow_stages[0] if unit.workflow_stages else ""
        group_title = form or unit.title
        grouped[(group_title.casefold(), workflow.casefold())].append(unit)

    playbooks: list[PracticePlaybook] = []
    for (group_key, workflow_key), members in sorted(grouped.items()):
        members.sort(
            key=lambda value: (
                ROLE_ORDER[MEMBER_ROLE[value.kind]],
                value.evidence[0].locator.page_number,
                str(value.intelligence_unit_id),
            )
        )
        member_refs = tuple(
            (member.intelligence_unit_id, member.version, MEMBER_ROLE[member.kind])
            for member in members
        )
        form = next((item for member in members for item in member.document_types), "")
        workflow = next((item for member in members for item in member.workflow_stages), "")
        title_subject = form or members[0].title
        uncertainties = tuple(
            dict.fromkeys(
                (
                    *(item for member in members for item in member.uncertainties),
                    *(("COVERAGE_MANIFEST_PARTIAL",) if publication_status != "complete" else ()),
                )
            )
        )
        playbook_semantic_digest = digest_of(
            {"group": group_key, "workflow": workflow_key, "members": member_refs}
        )
        playbooks.append(
            PracticePlaybook(
                playbook_id=deterministic_uuid(
                    "practice-playbook-semantic-v0.1.0:"
                    f"{practice_guide_id}:{playbook_semantic_digest}"
                ),
                version=1,
                practice_guide_edition_id=edition_id,
                coverage_manifest_id=coverage_manifest_id,
                title=f"Практика ИД: {title_subject}",
                purpose=(
                    "Методический контекст для анализа, комплектования и формирования ИД; "
                    "не является нормативным требованием"
                ),
                applicability_conditions=tuple(
                    dict.fromkeys(
                        item for member in members for item in member.applicability_conditions
                    )
                ),
                work_types=tuple(
                    dict.fromkeys(item for member in members for item in member.work_types)
                ),
                document_types=(form,) if form else (),
                form_types=tuple(
                    dict.fromkeys(item for member in members for item in member.form_types)
                ),
                workflow_stages=(workflow,) if workflow else (),
                member_refs=member_refs,
                uncertainties=uncertainties,
                construction_profile_version=CONSTRUCTION_PROFILE_VERSION,
            )
        )
    return tuple(units), tuple(playbooks)


def construction_fingerprint(
    units: Sequence[IDPracticeIntelligenceUnit], playbooks: Sequence[PracticePlaybook]
) -> str:
    return digest_of(
        {
            "construction_profile_version": CONSTRUCTION_PROFILE_VERSION,
            "units": [unit.integrity_digest for unit in units],
            "playbooks": [playbook.integrity_digest for playbook in playbooks],
        }
    )


def intelligence_unit_document(unit: IDPracticeIntelligenceUnit) -> dict[str, Any]:
    return {
        "intelligence_unit_id": str(unit.intelligence_unit_id),
        "version": unit.version,
        "practice_guide_edition_id": str(unit.practice_guide_edition_id),
        "coverage_manifest_id": str(unit.coverage_manifest_id),
        "kind": unit.kind.value,
        "title": unit.title,
        "instruction": unit.instruction,
        "rationale": unit.rationale,
        "applicability_conditions": list(unit.applicability_conditions),
        "work_types": list(unit.work_types),
        "document_types": list(unit.document_types),
        "form_types": list(unit.form_types),
        "workflow_stages": list(unit.workflow_stages),
        "field_elements": list(unit.field_elements),
        "required_inputs": list(unit.required_inputs),
        "evidence_requirements": list(unit.evidence_requirements),
        "allowed_variants": list(unit.allowed_variants),
        "failure_patterns": list(unit.failure_patterns),
        "checklist_items": list(unit.checklist_items),
        "dependency_refs": list(unit.dependency_refs),
        "normative_references": list(unit.normative_references),
        "uncertainties": list(unit.uncertainties),
        "evidence": [
            {
                "guidance_unit_id": str(item.guidance_unit_id),
                "guidance_unit_version": item.guidance_unit_version,
                "source_version_id": str(item.source_version_id),
                "page_number": item.locator.page_number,
                "region": list(item.locator.region),
                "fragment_digest": item.fragment_digest,
            }
            for item in unit.evidence
        ],
        "construction_profile_version": unit.construction_profile_version,
        "semantic_unit": unit.semantic_unit,
        "semantic_dimension": unit.semantic_dimension,
        "modality": unit.modality,
        "integrity_digest": unit.integrity_digest,
    }


def intelligence_unit_from_document(value: Mapping[str, Any]) -> IDPracticeIntelligenceUnit:
    return IDPracticeIntelligenceUnit(
        intelligence_unit_id=UUID(str(value["intelligence_unit_id"])),
        version=int(value["version"]),
        practice_guide_edition_id=UUID(str(value["practice_guide_edition_id"])),
        coverage_manifest_id=UUID(str(value["coverage_manifest_id"])),
        kind=PracticeIntelligenceKind(str(value["kind"])),
        title=str(value["title"]),
        instruction=str(value["instruction"]),
        rationale=str(value["rationale"]) if value.get("rationale") is not None else None,
        applicability_conditions=_strings(value.get("applicability_conditions")),
        work_types=_strings(value.get("work_types")),
        document_types=_strings(value.get("document_types")),
        form_types=_strings(value.get("form_types")),
        workflow_stages=_strings(value.get("workflow_stages")),
        field_elements=_strings(value.get("field_elements")),
        required_inputs=_strings(value.get("required_inputs")),
        evidence_requirements=_strings(value.get("evidence_requirements")),
        allowed_variants=_strings(value.get("allowed_variants")),
        failure_patterns=_strings(value.get("failure_patterns")),
        checklist_items=_strings(value.get("checklist_items")),
        dependency_refs=_strings(value.get("dependency_refs")),
        normative_references=_normative_references(value.get("normative_references")),
        uncertainties=_strings(value.get("uncertainties")),
        evidence=_evidence(value.get("evidence")),
        construction_profile_version=str(value["construction_profile_version"]),
        semantic_unit=(
            str(value["semantic_unit"]) if value.get("semantic_unit") is not None else None
        ),
        semantic_dimension=(
            str(value["semantic_dimension"])
            if value.get("semantic_dimension") is not None
            else None
        ),
        modality=str(value.get("modality", "recommendation")),
    )


def playbook_document(playbook: PracticePlaybook) -> dict[str, Any]:
    return {
        "playbook_id": str(playbook.playbook_id),
        "version": playbook.version,
        "practice_guide_edition_id": str(playbook.practice_guide_edition_id),
        "coverage_manifest_id": str(playbook.coverage_manifest_id),
        "title": playbook.title,
        "purpose": playbook.purpose,
        "applicability_conditions": list(playbook.applicability_conditions),
        "work_types": list(playbook.work_types),
        "document_types": list(playbook.document_types),
        "form_types": list(playbook.form_types),
        "workflow_stages": list(playbook.workflow_stages),
        "member_refs": [
            {
                "intelligence_unit_id": str(unit_id),
                "intelligence_unit_version": version,
                "member_role": role,
            }
            for unit_id, version, role in playbook.member_refs
        ],
        "uncertainties": list(playbook.uncertainties),
        "construction_profile_version": playbook.construction_profile_version,
        "integrity_digest": playbook.integrity_digest,
    }


def playbook_from_document(value: Mapping[str, Any]) -> PracticePlaybook:
    raw_members = value.get("member_refs")
    if not isinstance(raw_members, list):
        raise ValueError("PracticePlaybook member lineage is malformed")
    members = tuple(
        (
            UUID(str(item["intelligence_unit_id"])),
            int(item["intelligence_unit_version"]),
            str(item["member_role"]),
        )
        for item in raw_members
        if isinstance(item, Mapping)
    )
    if len(members) != len(raw_members):
        raise ValueError("PracticePlaybook member lineage contains invalid items")
    return PracticePlaybook(
        playbook_id=UUID(str(value["playbook_id"])),
        version=int(value["version"]),
        practice_guide_edition_id=UUID(str(value["practice_guide_edition_id"])),
        coverage_manifest_id=UUID(str(value["coverage_manifest_id"])),
        title=str(value["title"]),
        purpose=str(value["purpose"]),
        applicability_conditions=_strings(value.get("applicability_conditions")),
        work_types=_strings(value.get("work_types")),
        document_types=_strings(value.get("document_types")),
        form_types=_strings(value.get("form_types")),
        workflow_stages=_strings(value.get("workflow_stages")),
        member_refs=members,
        uncertainties=_strings(value.get("uncertainties")),
        construction_profile_version=str(value["construction_profile_version"]),
    )
