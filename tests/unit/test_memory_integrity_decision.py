import json
from pathlib import Path

from asd_kontur.integrity.decisions import load_integrity_decision
from asd_kontur.integrity.models import canonical_digest


def test_superseding_decision_withdraws_semantic_pass_without_rewriting_series() -> None:
    decision = load_integrity_decision(
        Path("docs/verification/MEMORY_INTEGRITY_SUPERSEDING_DECISION_01.json")
    )
    assert decision["prior_series_id"] == "SIC01-20260825-R1"
    assert decision["effective_system_integrity_status"] == "PARTIAL / DATA_DEFECT"
    assert decision["historical_series_preserved"] is True
    assert decision["requires_fresh_three_cycle_series"] is True
    assert decision["product_ready"] is False


def test_exact_defect_manifest_distinguishes_locator_scoped_semantics() -> None:
    path = Path("docs/verification/MEMORY_INTEGRITY_DEFECT_MANIFEST_01.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    fingerprint = manifest.pop("manifest_fingerprint")
    assert canonical_digest(manifest) == fingerprint
    semantic = manifest["defects"][0]
    assert semantic["active_duplicate_group_count"] == 2
    assert semantic["active_duplicate_physical_row_count"] == 4
    assert semantic["all_history_duplicate_physical_row_count"] == 8
    assert len(semantic["non_duplicate_equal_text_pairs"]) == 3


def test_final_requalification_preserves_lineage_and_current_product_truth() -> None:
    final = json.loads(
        Path("docs/verification/MEMORY_INTEGRITY_FINAL_QUALIFICATION_DECISION_01.json").read_text(
            encoding="utf-8"
        )
    )
    semantic = {
        key: final[key]
        for key in (
            "integrity_decision_id",
            "version",
            "decision_type",
            "status",
            "prior_series_id",
            "canonical_commit",
            "dump_fingerprint",
            "reconciliation_fingerprint",
            "defect_identities",
            "reason",
            "owner_decision_ref",
            "product_ready",
            "recorded_at",
        )
    }
    assert canonical_digest(semantic) == final["decision_fingerprint"]
    assert final["version"] == 3
    assert final["supersedes_version"] == 2
    assert final["prior_series_id"] == "MEMORY-INTEGRITY-FIX-01-R5"

    current = json.loads(
        Path("docs/product/PRODUCT_CURRENT_STATE_DECISION_v1.1.json").read_text(encoding="utf-8")
    )
    fingerprint = current.pop("decision_fingerprint")
    assert canonical_digest(current) == fingerprint
    assert current["capability_denominator"] == 142
    assert sum(current["readiness_distribution"].values()) == 142
    assert current["product_application_ready"] == "PARTIAL"
    assert current["trial_ready"] is False
    assert current["oks_ready"] is False
    assert current["product_ready"] is False
