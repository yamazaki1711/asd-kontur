"""Versioned mapping from interpreted project fields to one supported ID form.

The mapping does not extract text and does not confirm facts.  It reconciles
already evidence-bound candidate keys with the qualified AOSR field schema for
one declared work profile.  Scope matching is exact: work-local values must
share a source locator with the selected work package; only explicitly listed
project-global fields may be selected outside that work scope.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from asd_kontur.application_spine.models import semantic_digest

MONOLITHIC_FOUNDATION_SLAB_PROFILE_VERSION = "support.concrete-slab.aosr-field-map@1.0.0"
MONOLITHIC_FOUNDATION_SLAB_WORK_TYPE_KEY = "concrete.slab.install"


@dataclass(frozen=True, slots=True)
class SupportFieldSourceRule:
    target_field_key: str
    source_field_keys: tuple[str, ...]
    project_global: bool = False


_AOSR_RULES = (
    SupportFieldSourceRule("object_name", ("object_name", "project_name"), True),
    SupportFieldSourceRule("developer_identity", ("developer_identity",), True),
    SupportFieldSourceRule("builder_identity", ("builder_identity",), True),
    SupportFieldSourceRule("designer_identity", ("designer_identity",), True),
    SupportFieldSourceRule("act_number", ("act_number",)),
    SupportFieldSourceRule("act_date", ("act_date",)),
    SupportFieldSourceRule("customer_representative", ("customer_representative",)),
    SupportFieldSourceRule("builder_representative", ("builder_representative",)),
    SupportFieldSourceRule(
        "construction_control_representative",
        ("construction_control_representative",),
    ),
    SupportFieldSourceRule("designer_representative", ("designer_representative",)),
    SupportFieldSourceRule("work_performer_representative", ("work_performer_representative",)),
    SupportFieldSourceRule("inspection_participants", ("inspection_participants",)),
    SupportFieldSourceRule(
        "hidden_work_description", ("hidden_work_description", "work_description")
    ),
    SupportFieldSourceRule(
        "project_document_reference",
        ("project_document_reference", "document_reference"),
    ),
    SupportFieldSourceRule(
        "materials_and_quality_documents",
        ("materials_and_quality_documents", "material_passport"),
    ),
    SupportFieldSourceRule("control_evidence_documents", ("control_evidence_documents",)),
    SupportFieldSourceRule("work_start_date", ("work_start_date", "start_date")),
    SupportFieldSourceRule("work_end_date", ("work_end_date", "end_date")),
    SupportFieldSourceRule("compliance_basis", ("compliance_basis",)),
    SupportFieldSourceRule("next_works", ("next_works", "next_work")),
    SupportFieldSourceRule("additional_information", ("additional_information",)),
    SupportFieldSourceRule("paper_copy_count", ("paper_copy_count",)),
    SupportFieldSourceRule("appendices", ("appendices",)),
    SupportFieldSourceRule("customer_signatory_name", ("customer_signatory_name",)),
    SupportFieldSourceRule("builder_signatory_name", ("builder_signatory_name",)),
    SupportFieldSourceRule(
        "construction_control_signatory_name",
        ("construction_control_signatory_name",),
    ),
    SupportFieldSourceRule("designer_signatory_name", ("designer_signatory_name",)),
    SupportFieldSourceRule("work_performer_signatory_name", ("work_performer_signatory_name",)),
)


def monolithic_foundation_slab_mapping_profile() -> dict[str, Any]:
    document = {
        "profile_version": MONOLITHIC_FOUNDATION_SLAB_PROFILE_VERSION,
        "work_type_key": MONOLITHIC_FOUNDATION_SLAB_WORK_TYPE_KEY,
        "required_document_type_ref": "support.aosr",
        "rules": [
            {
                "target_field_key": rule.target_field_key,
                "source_field_keys": list(rule.source_field_keys),
                "project_global": rule.project_global,
            }
            for rule in _AOSR_RULES
        ],
    }
    return {**document, "profile_fingerprint": semantic_digest(document)}


def reconcile_support_field_candidates(
    *,
    work_type_key: str,
    work_source_locator_ids: Iterable[object],
    template_fields: Iterable[Mapping[str, Any]],
    project_candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return candidate/conflict/missing states without promoting any value."""

    if work_type_key != MONOLITHIC_FOUNDATION_SLAB_WORK_TYPE_KEY:
        return {
            "profile": None,
            "status": "unsupported_work_type",
            "fields": [],
            "missing_field_keys": [],
            "conflict_field_keys": [],
        }
    locators = {str(value) for value in work_source_locator_ids}
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in project_candidates:
        candidate = dict(item)
        by_key[str(candidate.get("field_key", ""))].append(candidate)
    template_by_key = {str(item["field_key"]): dict(item) for item in template_fields}
    fields: list[dict[str, Any]] = []
    missing: list[str] = []
    conflicts: list[str] = []
    for rule in _AOSR_RULES:
        definition = template_by_key.get(rule.target_field_key)
        if definition is None:
            continue
        observations = [
            candidate
            for source_key in rule.source_field_keys
            for candidate in by_key.get(source_key, ())
            if rule.project_global or str(candidate.get("source_locator_id", "")) in locators
        ]
        distinct = {str(item.get("effective_value")) for item in observations}
        state = "missing"
        if len(distinct) == 1 and observations:
            state = "candidate"
        elif len(distinct) > 1:
            state = "conflict"
            conflicts.append(rule.target_field_key)
        elif bool(definition.get("required")):
            missing.append(rule.target_field_key)
        fields.append(
            {
                "field_key": rule.target_field_key,
                "required": bool(definition.get("required")),
                "material": bool(definition.get("material")),
                "state": state,
                "observations": observations,
                "source_field_keys": list(rule.source_field_keys),
                "scope_rule": "project_global" if rule.project_global else "exact_work_locator",
            }
        )
    profile = monolithic_foundation_slab_mapping_profile()
    return {
        "profile": profile,
        "status": "conflict" if conflicts else "partial" if missing else "candidate_complete",
        "fields": fields,
        "missing_field_keys": sorted(missing),
        "conflict_field_keys": sorted(conflicts),
    }
