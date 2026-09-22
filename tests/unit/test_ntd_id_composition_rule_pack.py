from __future__ import annotations

import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from asd_kontur.ntd.rules import (
    DeonticType,
    NormativeRuleCandidate,
    RuleQualificationStatus,
    SemanticEvidenceBinding,
    qualify_rule_candidate,
)

PACK_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "rule_activation"
    / "id_composition_pack_v1.json"
)
MANIFEST = json.loads(PACK_PATH.read_text(encoding="utf-8"))
DESIGNATION = "СП 543.1325800.2024"


def _candidate(rule: dict) -> NormativeRuleCandidate:
    seed = f"{MANIFEST['selection_decision']}:{DESIGNATION}:{rule['structural_path']}"
    return NormativeRuleCandidate.create(
        normative_document_id=uuid5(NAMESPACE_URL, seed + ":document"),
        normative_edition_id=uuid5(NAMESPACE_URL, seed + ":edition"),
        source_version_id=uuid5(NAMESPACE_URL, seed + ":source"),
        normative_provision_id=uuid5(NAMESPACE_URL, seed + ":provision"),
        normative_provision_version=1,
        source_locator_id=uuid5(NAMESPACE_URL, seed + ":locator"),
        structural_path=rule["structural_path"],
        verbatim_text=rule["provision_verbatim"],
        deontic_type=DeonticType(rule["deontic_type"]),
        actor=rule["actor"],
        regulated_object=rule["regulated_object"],
        required_action=rule["required_action"],
        applicability_predicate=rule["applicability_predicate"],
        output_contract=rule["output_contract"],
        evidence_bindings=tuple(
            SemanticEvidenceBinding(field, tuple(quotes))
            for field, quotes in rule["evidence_bindings"].items()
        ),
        interpretation_profile_version=MANIFEST["interpretation_profile_version"],
    )


def test_pack_shape_matches_selection_schema() -> None:
    assert MANIFEST["schema_version"] == "rule-activation-selection-v1"
    assert MANIFEST["selection_decision"] == "NTD-RULE-ACTIVATION-ID-COMPOSITION-01"
    assert len(MANIFEST["rules"]) == 4
    paths = [rule["structural_path"] for rule in MANIFEST["rules"]]
    assert len(set(paths)) == len(paths), "structural paths must be unique"
    assert {"4.5", "6.6", "6.9", "7.2.3"} == set(paths)


def test_pack_evidence_quotes_are_verbatim_substrings() -> None:
    for rule in MANIFEST["rules"]:
        for field, quotes in rule["evidence_bindings"].items():
            for quote in quotes:
                assert quote in rule["provision_verbatim"], (
                    f"{rule['structural_path']} field {field}: quote outside provision snapshot"
                )


def test_pack_candidates_qualify_against_verified_provision() -> None:
    for rule in MANIFEST["rules"]:
        candidate = _candidate(rule)
        qualification = qualify_rule_candidate(
            candidate,
            provision_verification_status="verified",
            evidence_edition_id=candidate.normative_edition_id,
            evidence_source_version_id=candidate.source_version_id,
            evidence_locator_id=candidate.source_locator_id,
            evidence_verbatim_text=rule["provision_verbatim"],
            qualification_profile_version=MANIFEST["qualification_profile_version"],
            test_manifest_digest="sha256:" + "0" * 64,
        )
        assert qualification.status == RuleQualificationStatus.QUALIFIED, (
            f"{rule['structural_path']}: {qualification.status.value}"
        )


def test_pack_rejects_invented_evidence() -> None:
    rule = MANIFEST["rules"][0]
    candidate = _candidate(rule)
    tampered = qualify_rule_candidate(
        candidate,
        provision_verification_status="verified",
        evidence_edition_id=candidate.normative_edition_id,
        evidence_source_version_id=candidate.source_version_id,
        evidence_locator_id=candidate.source_locator_id,
        evidence_verbatim_text=rule["provision_verbatim"].replace("контроля", "надзора"),
        qualification_profile_version=MANIFEST["qualification_profile_version"],
        test_manifest_digest="sha256:" + "0" * 64,
    )
    assert tampered.status != RuleQualificationStatus.QUALIFIED
