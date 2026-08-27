"""Deterministic, fail-closed PD/RD normative profile assembly."""

# ruff: noqa: E501 -- audited SQL remains legible as complete clauses.

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of

from .models import ApplicablePdRdNormativeProfile

PD_RD_PROFILE_VERSION = "applicable_pd_rd_normative_profile_v0.1"


@dataclass(frozen=True, slots=True)
class EvaluatedPdRdRequirements:
    normative_edition_ids: tuple[UUID, ...]
    rule_version_ids: tuple[UUID, ...]
    required_pd_sections: tuple[dict[str, Any], ...]
    expected_rd_sets: tuple[dict[str, Any], ...]
    formatting_requirements: tuple[dict[str, Any], ...]
    unresolved_inputs: tuple[str, ...]
    gaps: tuple[dict[str, Any], ...]
    corpus_denominator: dict[str, Any]
    semantic_fingerprint: str


@dataclass(frozen=True, slots=True)
class PdRdProfileContext:
    organization_id: UUID
    workspace_id: UUID
    project_definition_id: UUID
    project_definition_version: int
    applicable_on: date | None
    dimensions: dict[str, Any]

    @property
    def input_fingerprint(self) -> str:
        return digest_of(
            {
                "profile_version": PD_RD_PROFILE_VERSION,
                "project_definition_id": self.project_definition_id,
                "project_definition_version": self.project_definition_version,
                "applicable_on": self.applicable_on,
                "dimensions": self.dimensions,
            }
        )


class PdRdNormativeProfileRepository:
    """Assemble a workspace profile only from active, provision-backed RuleVersions."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def assemble(
        self, context: PdRdProfileContext, *, created_at: datetime
    ) -> ApplicablePdRdNormativeProfile:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            exists = session.scalar(
                sa.text(
                    "SELECT 1 FROM workspace.project_definition_versions WHERE "
                    "organization_id=:organization AND workspace_id=:workspace AND "
                    "project_definition_id=:project AND version=:version"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "project": context.project_definition_id,
                    "version": context.project_definition_version,
                },
            )
            if exists is None:
                raise ValueError("PROJECT_DEFINITION_PIN_NOT_FOUND")
            rows = (
                (
                    session.execute(
                        sa.text(
                            "SELECT rv.rule_version_id,rv.output_contract,rv.predicate_contract,"
                            "e.normative_edition_id,e.official_catalog_url,p.normative_provision_id,"
                            "p.version AS provision_version,p.source_version_id,p.structural_path,"
                            "p.verbatim_text,p.content_digest,sl.source_locator_id,sl.locator_value,"
                            "ap.required_inputs,ap.predicate,ap.exclusions "
                            "FROM platform.rule_versions rv "
                            "JOIN LATERAL (SELECT status FROM platform.rule_version_states s WHERE "
                            "s.rule_version_id=rv.rule_version_id ORDER BY state_sequence DESC LIMIT 1) state ON true "
                            "JOIN platform.rule_normative_provision_evidence re ON "
                            "re.rule_version_id=rv.rule_version_id "
                            "JOIN platform.normative_provision_versions p ON "
                            "p.normative_provision_id=re.normative_provision_id AND "
                            "p.version=re.normative_provision_version AND p.verification_status='verified' "
                            "JOIN platform.normative_editions e ON e.normative_edition_id=re.normative_edition_id "
                            "JOIN platform.source_locators sl ON sl.source_locator_id=re.source_locator_id "
                            "JOIN platform.normative_applicability_predicates ap ON "
                            "ap.applicability_predicate_id=re.applicability_predicate_id AND "
                            "ap.version=re.applicability_predicate_version "
                            "WHERE state.status='active' AND (rv.effective_from IS NULL OR rv.effective_from<=:as_of) "
                            "AND (rv.effective_to IS NULL OR rv.effective_to>:as_of) "
                            "ORDER BY rv.rule_version_id,p.normative_provision_id,p.version"
                        ),
                        {"as_of": context.applicable_on},
                    )
                    .mappings()
                    .all()
                )
                if context.applicable_on is not None
                else []
            )
            evaluated = evaluate_pd_rd_requirements(
                rows=tuple(dict(row) for row in rows),
                dimensions=context.dimensions,
                applicable_on=context.applicable_on,
                input_fingerprint=context.input_fingerprint,
                corpus_denominator=load_spds_corpus_denominator(session),
            )
            profile_id = deterministic_uuid(
                f"pd-rd-normative-profile:{context.workspace_id}:{context.project_definition_id}:"
                f"{context.project_definition_version}:{context.input_fingerprint}"
            )
            status = (
                "blocked"
                if any(bool(item.get("blocking")) for item in evaluated.gaps)
                else "complete"
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.applicable_pd_rd_normative_profiles "
                    "(organization_id,workspace_id,profile_id,version,project_definition_id,"
                    "project_definition_version,applicable_on,input_fingerprint,corpus_denominator,"
                    "normative_edition_ids,"
                    "rule_version_ids,required_pd_sections,expected_rd_sets,formatting_requirements,"
                    "unresolved_inputs,gaps,completeness_status,semantic_fingerprint,created_at) "
                    "VALUES (:organization,:workspace,:profile,1,:project,:project_version,:as_of,"
                    ":input,CAST(:denominator AS jsonb),:editions,:rules,CAST(:sections AS jsonb),"
                    "CAST(:sets AS jsonb),CAST(:formatting AS jsonb),:unresolved,"
                    "CAST(:gaps AS jsonb),:status,:fingerprint,"
                    ":created) ON CONFLICT (organization_id,workspace_id,input_fingerprint,"
                    "semantic_fingerprint) DO NOTHING"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "profile": profile_id,
                    "project": context.project_definition_id,
                    "project_version": context.project_definition_version,
                    "as_of": context.applicable_on,
                    "input": context.input_fingerprint,
                    "denominator": json.dumps(evaluated.corpus_denominator, sort_keys=True),
                    "editions": list(evaluated.normative_edition_ids),
                    "rules": list(evaluated.rule_version_ids),
                    "sections": json.dumps(evaluated.required_pd_sections, sort_keys=True),
                    "sets": json.dumps(evaluated.expected_rd_sets, sort_keys=True),
                    "formatting": json.dumps(evaluated.formatting_requirements, sort_keys=True),
                    "unresolved": list(evaluated.unresolved_inputs),
                    "gaps": json.dumps(evaluated.gaps, sort_keys=True),
                    "status": status,
                    "fingerprint": evaluated.semantic_fingerprint,
                    "created": created_at,
                },
            )
        return ApplicablePdRdNormativeProfile(
            profile_id=profile_id,
            version=1,
            workspace_id=context.workspace_id,
            project_definition_id=context.project_definition_id,
            project_definition_version=context.project_definition_version,
            applicable_on=context.applicable_on,
            input_fingerprint=context.input_fingerprint,
            corpus_denominator=evaluated.corpus_denominator,
            normative_edition_ids=evaluated.normative_edition_ids,
            rule_version_ids=evaluated.rule_version_ids,
            required_pd_sections=evaluated.required_pd_sections,
            expected_rd_sets=evaluated.expected_rd_sets,
            formatting_requirements=evaluated.formatting_requirements,
            unresolved_inputs=evaluated.unresolved_inputs,
            gaps=evaluated.gaps,
            completeness_status=status,
            semantic_fingerprint=evaluated.semantic_fingerprint,
        )


def load_spds_corpus_denominator(session: Session) -> dict[str, Any]:
    row = (
        session.execute(
            sa.text(
                "SELECT denominator,manifest_fingerprint FROM "
                "platform.normative_corpus_manifests WHERE corpus_key='ru:spds' "
                "ORDER BY version DESC LIMIT 1"
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return {"spds_members": 0, "gap": "SPDS_CORPUS_MANIFEST_UNAVAILABLE"}
    return {
        "spds_members": int(row["denominator"]),
        "manifest_fingerprint": str(row["manifest_fingerprint"]),
    }


def evaluate_pd_rd_requirements(
    *,
    rows: Sequence[Mapping[str, Any]],
    dimensions: Mapping[str, Any],
    applicable_on: date | None,
    input_fingerprint: str,
    corpus_denominator: dict[str, Any],
) -> EvaluatedPdRdRequirements:
    """Canonical deterministic evaluator shared by Gateway and document workers."""

    required_sections: list[dict[str, Any]] = []
    expected_sets: list[dict[str, Any]] = []
    formatting: list[dict[str, Any]] = []
    unresolved = {"applicable_on"} if applicable_on is None else set()
    edition_ids: set[UUID] = set()
    rule_ids: set[UUID] = set()
    for row in rows:
        required_inputs = tuple(str(item) for item in row["required_inputs"])
        missing = [
            item
            for item in required_inputs
            if dimensions.get(item) is None or dimensions.get(item) == ""
        ]
        if missing:
            unresolved.update(missing)
            continue
        predicate = dict(row["predicate"])
        if not _matches(predicate, dimensions):
            continue
        edition_ids.add(UUID(str(row["normative_edition_id"])))
        rule_ids.add(UUID(str(row["rule_version_id"])))
        output = dict(row["output_contract"])
        result = {
            **output,
            "rule_version_id": str(row["rule_version_id"]),
            "normative_edition_id": str(row["normative_edition_id"]),
            "normative_provision_id": str(row["normative_provision_id"]),
            "normative_provision_version": int(row["provision_version"]),
            "structural_path": str(row["structural_path"]),
            "source_locator_id": str(row["source_locator_id"]),
            "source_version_id": str(row["source_version_id"]),
            "official_source": str(row["official_catalog_url"]),
            "locator": row["locator_value"],
            "evidence_digest": str(row["content_digest"]),
            "authority_layer": "normative_authority",
        }
        kind = str(output.get("requirement_kind", ""))
        if kind == "pd_section":
            required_sections.append(result)
        elif kind == "rd_set":
            expected_sets.append(result)
        else:
            formatting.append(result)
    gaps: list[dict[str, Any]] = []
    if not rows:
        gaps.extend(
            (
                {"code": "VERIFIED_PD_RD_NTD_UNAVAILABLE", "blocking": True},
                {"code": "ACTIVE_PD_RD_RULE_VERSION_UNAVAILABLE", "blocking": True},
            )
        )
    if unresolved:
        gaps.append(
            {
                "code": "NORMATIVE_APPLICABILITY_INPUT_MISSING",
                "inputs": sorted(unresolved),
                "blocking": True,
            }
        )
    sorted_sections = tuple(sorted(required_sections, key=_result_key))
    sorted_sets = tuple(sorted(expected_sets, key=_result_key))
    sorted_formatting = tuple(sorted(formatting, key=_result_key))
    ordered_editions = tuple(sorted(edition_ids, key=str))
    ordered_rules = tuple(sorted(rule_ids, key=str))
    ordered_unresolved = tuple(sorted(unresolved))
    semantic_payload = {
        "profile_version": PD_RD_PROFILE_VERSION,
        "input_fingerprint": input_fingerprint,
        "corpus_denominator": corpus_denominator,
        "editions": [str(value) for value in ordered_editions],
        "rules": [str(value) for value in ordered_rules],
        "required_pd_sections": sorted_sections,
        "expected_rd_sets": sorted_sets,
        "formatting_requirements": sorted_formatting,
        "unresolved_inputs": ordered_unresolved,
        "gaps": gaps,
    }
    return EvaluatedPdRdRequirements(
        ordered_editions,
        ordered_rules,
        sorted_sections,
        sorted_sets,
        sorted_formatting,
        ordered_unresolved,
        tuple(gaps),
        corpus_denominator,
        digest_of(semantic_payload),
    )


def _set_scope(session: Session, context: PdRdProfileContext) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(context.organization_id), True),
            sa.func.set_config("asd.workspace_id", str(context.workspace_id), True),
        )
    ).one()


def _matches(predicate: Mapping[str, Any], dimensions: Mapping[str, Any]) -> bool:
    for key, expected in predicate.items():
        actual = dimensions.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _result_key(value: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(value.get("requirement_kind", "")),
        str(value.get("code", value.get("section", value.get("mark", "")))),
        str(value.get("rule_version_id", "")),
    )
