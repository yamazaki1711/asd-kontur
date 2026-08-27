#!/usr/bin/env python3
"""Materialize versioned rule candidates selected by an auditable input manifest."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import create_engine

from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of
from asd_kontur.knowledge.postgres import RuleRegistryService
from asd_kontur.knowledge.rules import AuthorityIdentity, RuleState, RuleVersionDefinition
from asd_kontur.ntd.models import ApplicabilityPredicate, RuleNormativeProvisionEvidence
from asd_kontur.ntd.postgres import NtdRepository
from asd_kontur.ntd.rules import (
    DeonticType,
    NormativeRuleCandidate,
    SemanticEvidenceBinding,
    decide_rule_activation,
    qualify_rule_candidate,
)

AUTHOR = AuthorityIdentity("service.normative-rule-candidate-compiler", "service")
QUALIFIER = "service.deterministic-normative-rule-qualifier"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    engine = create_engine(args.database_url)
    repository = NtdRepository(engine)
    registry = RuleRegistryService(engine)
    results: list[dict[str, Any]] = []
    for item in manifest["rules"]:
        evidence = _load_evidence(engine, item["designation"], item["structural_path"])
        candidate = _candidate(manifest, item, evidence)
        now = datetime.now(UTC)
        repository.register_rule_candidate(
            candidate, created_by_identity_id=AUTHOR.identity_id, created_at=now
        )
        test_digest = digest_of(
            {
                "schema": "normative-rule-test-manifest-v1",
                "candidate": candidate.semantic_fingerprint,
                "positive": item["applicability_predicate"],
                "unknown_behavior": "block",
            }
        )
        qualification = qualify_rule_candidate(
            candidate,
            provision_verification_status=evidence["verification_status"],
            evidence_edition_id=evidence["normative_edition_id"],
            evidence_source_version_id=evidence["source_version_id"],
            evidence_locator_id=evidence["source_locator_id"],
            evidence_verbatim_text=evidence["verbatim_text"],
            qualification_profile_version=manifest["qualification_profile_version"],
            test_manifest_digest=test_digest,
        )
        repository.record_rule_qualification(
            qualification,
            qualified_by_identity_id=QUALIFIER,
            qualification_decision_ref=f"qualification:{qualification.decision_fingerprint}",
            decided_at=now,
        )
        rule_version_id: UUID | None = None
        rule_state: str | None = None
        if qualification.qualified:
            rule_version_id, rule_state = _compile_candidate(
                engine, repository, registry, candidate, qualification, test_digest, now
            )
        edition_decision = _edition_activation(engine, candidate.normative_edition_id)
        edition_status = str(edition_decision[2]) if edition_decision else "not_activated"
        activation = decide_rule_activation(
            candidate,
            qualification,
            edition_activation_status=edition_status,
            rule_lifecycle_status=rule_state,
        )
        repository.record_rule_activation_outcome(
            activation,
            rule_version_id=rule_version_id,
            edition_activation_decision=(edition_decision[0], edition_decision[1])
            if edition_decision
            else None,
            authority_identity_id=None,
            authority_decision_ref=f"decision:{activation.decision_fingerprint}",
            decided_at=now,
        )
        results.append(
            {
                "designation": item["designation"],
                "structural_path": item["structural_path"],
                "candidate_id": str(candidate.candidate_id),
                "qualification": qualification.status.value,
                "rule_version_id": str(rule_version_id) if rule_version_id else None,
                "rule_lifecycle": rule_state,
                "activation": activation.status.value,
                "activation_reason": activation.reason_code,
            }
        )
    print(
        json.dumps(
            {"schema": "rule-activation-materialization-result-v1", "results": results}, indent=2
        )
    )


def _load_evidence(engine: sa.Engine, designation: str, structural_path: str) -> dict[str, Any]:
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.text(
                    "SELECT d.normative_document_id,p.normative_edition_id,p.source_version_id,"
                    "p.normative_provision_id,p.version,p.structural_path,p.verbatim_text,"
                    "p.verification_status,locator.source_locator_id FROM "
                    "platform.normative_provision_versions p JOIN platform.normative_editions e "
                    "USING(normative_edition_id) JOIN platform.normative_documents d "
                    "USING(normative_document_id) JOIN platform.normative_structural_fragments sf "
                    "ON sf.structural_unit_id=p.structural_unit_id AND "
                    "sf.source_version_id=p.source_version_id CROSS JOIN LATERAL "
                    "unnest(sf.source_locator_ids) WITH ORDINALITY ids(locator_id,ordinality) JOIN "
                    "platform.source_locators locator ON locator.source_locator_id=ids.locator_id "
                    "WHERE d.designation=:designation AND p.structural_path=:path AND "
                    "p.verification_status='verified' ORDER BY p.version DESC,"
                    "ids.ordinality LIMIT 1"
                ),
                {"designation": designation, "path": structural_path},
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        raise RuntimeError(f"No exact verified evidence for {designation} {structural_path}")
    return {key: UUID(str(value)) if key.endswith("_id") else value for key, value in row.items()}


def _candidate(
    manifest: dict[str, Any], item: dict[str, Any], evidence: dict[str, Any]
) -> NormativeRuleCandidate:
    return NormativeRuleCandidate.create(
        normative_document_id=evidence["normative_document_id"],
        normative_edition_id=evidence["normative_edition_id"],
        source_version_id=evidence["source_version_id"],
        normative_provision_id=evidence["normative_provision_id"],
        normative_provision_version=int(evidence["version"]),
        source_locator_id=evidence["source_locator_id"],
        structural_path=evidence["structural_path"],
        verbatim_text=evidence["verbatim_text"],
        deontic_type=DeonticType(item["deontic_type"]),
        actor=item["actor"],
        regulated_object=item["regulated_object"],
        required_action=item["required_action"],
        applicability_predicate=item["applicability_predicate"],
        output_contract=item["output_contract"],
        evidence_bindings=tuple(
            SemanticEvidenceBinding(field, tuple(quotes))
            for field, quotes in sorted(item["evidence_bindings"].items())
        ),
        interpretation_profile_version=manifest["interpretation_profile_version"],
    )


def _compile_candidate(
    engine: sa.Engine,
    repository: NtdRepository,
    registry: RuleRegistryService,
    candidate: NormativeRuleCandidate,
    qualification: Any,
    test_digest: str,
    now: datetime,
) -> tuple[UUID, str]:
    applicability_context_id = deterministic_uuid(
        f"normative-rule-applicability:{candidate.semantic_fingerprint}"
    )
    policy_id = deterministic_uuid("normative-rule-conflict-policy:single-source-fail-closed-v1")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.applicability_contexts "
                "(applicability_context_id,context_version,dimensions,unknown_behavior,"
                "integrity_digest) "
                "VALUES (:id,1,CAST(:dimensions AS jsonb),'block',:digest) ON CONFLICT DO NOTHING"
            ),
            {
                "id": applicability_context_id,
                "dimensions": json.dumps(candidate.applicability_predicate, sort_keys=True),
                "digest": digest_of(
                    {"predicate": candidate.applicability_predicate, "unknown": "block"}
                ),
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.conflict_policy_versions "
                "(conflict_policy_version_id,conflict_group_key,version,subject_domain,"
                "predicate_contract,outcome_contract,authority_reference,status,integrity_digest) "
                "VALUES (:id,'normative.single-source.fail-closed','1.0.0','normative-rule',"
                "'{}'::jsonb,'{}'::jsonb,'decision:rule-activation-vertical-slice',"
                "'active',:digest) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": policy_id, "digest": digest_of("normative.single-source.fail-closed.v1")},
        )
    rule_version_id = deterministic_uuid(f"rule-version:{candidate.semantic_fingerprint}")
    definition = RuleVersionDefinition(
        str(rule_version_id),
        f"normative.{candidate.candidate_id}",
        candidate.applicability_predicate,
        candidate.output_contract,
        (
            f"normative-provision:{candidate.normative_provision_id}:{candidate.normative_provision_version}",
        ),
        str(policy_id),
        None,
        None,
    )
    registry.register_version(
        definition=definition,
        rule_class="normative-deterministic",
        purpose="Compiled qualified normative provision candidate",
        applicability_context_id=applicability_context_id,
        author=AUTHOR,
        test_manifest_digest=test_digest,
    )
    predicate_id = deterministic_uuid(f"normative-applicability:{candidate.semantic_fingerprint}")
    predicate_fingerprint = ApplicabilityPredicate.compute_fingerprint(
        provision_id=candidate.normative_provision_id,
        provision_version=candidate.normative_provision_version,
        predicate=candidate.applicability_predicate,
        required_inputs=(str(candidate.applicability_predicate["field"]),),
        exclusions=candidate.exceptions,
    )
    repository.register_applicability_predicate(
        ApplicabilityPredicate(
            predicate_id,
            1,
            candidate.normative_provision_id,
            candidate.normative_provision_version,
            candidate.applicability_predicate,
            (str(candidate.applicability_predicate["field"]),),
            candidate.exceptions,
            predicate_fingerprint,
        ),
        qualified_by_identity_id=QUALIFIER,
        qualification_decision_ref=f"qualification:{qualification.decision_fingerprint}",
        qualified_at=now,
    )
    repository.link_rule_to_verified_provision(
        RuleNormativeProvisionEvidence(
            deterministic_uuid(f"rule-normative-evidence:{candidate.semantic_fingerprint}"),
            rule_version_id,
            candidate.normative_provision_id,
            candidate.normative_provision_version,
            candidate.normative_edition_id,
            candidate.source_version_id,
            candidate.source_locator_id,
            predicate_id,
            1,
            f"qualification:{qualification.decision_fingerprint}",
            candidate.verbatim_digest,
            now,
        )
    )
    state = _rule_state(engine, rule_version_id)
    if state == RuleState.DRAFTED.value:
        registry.transition(
            rule_version_id=rule_version_id,
            target=RuleState.EVIDENCE_ATTACHED,
            actor=AUTHOR,
            decision_ref=f"decision:evidence:{candidate.semantic_fingerprint}",
        )
        registry.transition(
            rule_version_id=rule_version_id,
            target=RuleState.CANDIDATE,
            actor=AUTHOR,
            decision_ref=f"decision:candidate:{candidate.semantic_fingerprint}",
        )
    return rule_version_id, _rule_state(engine, rule_version_id)


def _rule_state(engine: sa.Engine, rule_version_id: UUID) -> str:
    with engine.connect() as connection:
        return str(
            connection.scalar(
                sa.text(
                    "SELECT status FROM platform.rule_version_states WHERE rule_version_id=:id "
                    "ORDER BY state_sequence DESC LIMIT 1"
                ),
                {"id": rule_version_id},
            )
        )


def _edition_activation(engine: sa.Engine, edition_id: UUID) -> tuple[UUID, int, str] | None:
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT activation_decision_id,version,status FROM "
                "platform.normative_activation_decisions WHERE selected_edition_id=:edition "
                "ORDER BY as_of DESC,version DESC LIMIT 1"
            ),
            {"edition": edition_id},
        ).one_or_none()
    return (UUID(str(row[0])), int(row[1]), str(row[2])) if row else None


if __name__ == "__main__":
    main()
