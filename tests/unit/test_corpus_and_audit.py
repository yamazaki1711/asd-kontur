from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pypdf import PdfWriter

from asd_kontur.audit import (
    ActionRequest,
    ActionRequestState,
    AuditCommand,
    AuditCommandType,
    AuditStateMachine,
    AuditTerminalOutcome,
    CausalImpactPath,
    CausalReadinessDelta,
    ClassificationVersion,
    DeltaDenominator,
    DeltaState,
    DocumentDelta,
    EvidenceRatedItem,
    PackageAssessment,
    PackageMembership,
    PackageReadiness,
    ProcessState,
    assemble_audit_report,
    document_readiness_counts,
    evaluate_document_items,
    package_readiness_counts,
    rebuild_customer_projection,
    rebuild_pto_projection,
    scope_from_snapshot,
)
from asd_kontur.corpus import (
    BoundaryCandidate,
    BoundaryDisposition,
    CollectionMission,
    CollectionScope,
    CorpusCoverage,
    CorpusOutcome,
    CorpusScope,
    CorpusSnapshot,
    PageInspection,
    PageRoute,
    PhysicalObjectInspection,
    PhysicalObjectRef,
    ProcessingReceipt,
    ReceiptStatus,
    ResourcePolicy,
    UnresolvedCorpusItem,
    build_processing_plan,
    inspect_pdf,
    pages_for_resume,
    reconcile_processing,
    validate_boundary,
    validate_boundary_set,
)

NOW = datetime(2026, 8, 23, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def scope() -> CorpusScope:
    return CorpusScope(uuid4(), uuid4())


def inspection(page_kinds: tuple[str, ...], *, size_bytes: int = 1024) -> PhysicalObjectInspection:
    pages = tuple(
        PageInspection(
            number,
            595.0,
            842.0,
            0,
            200 if kind in {"native", "mixed"} else 0,
            1 if kind in {"raster", "mixed"} else 0,
        )
        for number, kind in enumerate(page_kinds, start=1)
    )
    return PhysicalObjectInspection(
        scope(),
        uuid4(),
        uuid4(),
        1,
        DIGEST_A,
        size_bytes,
        "application/pdf",
        False,
        True,
        len(pages),
        pages,
        0,
        0,
        "preflight-1.0.0",
        NOW,
    )


def policy(*, external: bool = False, qualified: bool = False) -> ResourcePolicy:
    return ResourcePolicy(
        "development-1.0.0",
        50,
        50 * 1024 * 1024,
        100,
        10,
        10_000,
        external,
        qualified,
    )


def receipt(plan_id: UUID, shard_id: UUID, page: int, status: ReceiptStatus) -> ProcessingReceipt:
    return ProcessingReceipt(
        scope=CorpusScope(UUID(int=1), UUID(int=2)),
        receipt_id=uuid4(),
        plan_id=plan_id,
        plan_version=1,
        shard_id=shard_id,
        page_number=page,
        attempt_id=uuid4(),
        idempotency_key=f"page-{page}-{status}",
        status=status,
        result_digest=DIGEST_B if status is ReceiptStatus.VALIDATED else None,
        validation_codes=(),
        recorded_at=NOW,
    )


def test_organized_and_chaotic_collection_use_same_mission_model() -> None:
    shared = scope()
    organized_scope = CollectionScope(
        shared, uuid4(), 1, ("organized-room",), ("folder-register",), "claimed_complete", "1.0.0"
    )
    chaotic_scope = CollectionScope(
        shared,
        uuid4(),
        1,
        ("box-a", "disk-b", "unknown-location"),
        ("paper", "filesystem"),
        "unknown",
        "1.0.0",
    )
    for value in (organized_scope, chaotic_scope):
        mission = CollectionMission(
            shared, uuid4(), uuid4(), value.collection_scope_id, value.version, "collector", NOW
        )
        assert mission.state == "collecting"
    assert chaotic_scope.completeness_claim == "unknown"


def test_huge_raster_metadata_uses_bounded_external_eligible_route() -> None:
    value = inspection(("raster",) * 726, size_bytes=360 * 1024 * 1024)
    plan = build_processing_plan(
        value,
        purpose="document_classification",
        classification="internal",
        policy=policy(external=True, qualified=True),
    )
    assert {page.route for page in plan.page_plans} == {PageRoute.EXTERNAL_ELIGIBLE}
    assert max(len(shard.page_numbers) for shard in plan.shards) == 10
    assert len(plan.shards) == 73


def test_huge_raster_without_external_route_is_deferred_not_blind_local() -> None:
    value = inspection(("raster",) * 60, size_bytes=60 * 1024 * 1024)
    plan = build_processing_plan(
        value,
        purpose="classification",
        classification="internal",
        policy=policy(),
    )
    assert plan.state is CorpusOutcome.PARTIAL
    assert {page.route for page in plan.page_plans} == {PageRoute.DEFERRED}
    assert plan.shards == ()


def test_sensitive_huge_corpus_does_not_widen_egress() -> None:
    plan = build_processing_plan(
        inspection(("raster",) * 60, size_bytes=60 * 1024 * 1024),
        purpose="legal",
        classification="confidential",
        policy=policy(external=True, qualified=True),
        sensitive=True,
    )
    assert {page.reason_code for page in plan.page_plans} == {"SENSITIVE_HUGE_LOCAL_LIMIT"}


def test_mixed_container_routes_pages_independently() -> None:
    plan = build_processing_plan(
        inspection(("native", "raster", "mixed")),
        purpose="audit",
        classification="internal",
        policy=policy(),
    )
    assert tuple(page.route for page in plan.page_plans) == (
        PageRoute.NATIVE,
        PageRoute.LOCAL_VLM,
        PageRoute.DETERMINISTIC,
    )


def test_boundary_hints_split_contiguous_shards_without_becoming_documents() -> None:
    plan = build_processing_plan(
        inspection(("native",) * 6),
        purpose="audit",
        classification="internal",
        policy=policy(),
        boundary_hints=frozenset({4}),
    )
    assert tuple(shard.page_numbers for shard in plan.shards) == ((1, 2, 3), (4, 5, 6))
    assert all(shard.context_overlap_pages == () for shard in plan.shards)


def test_preflight_reads_path_without_path_read_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "small.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with path.open("wb") as stream:
        writer.write(stream)

    def forbidden_read_bytes(self: Path) -> bytes:
        raise AssertionError(f"whole-file read forbidden: {self}")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    result = inspect_pdf(
        path,
        scope=scope(),
        physical_object_id=uuid4(),
        physical_object_version=1,
        profile_version="1.0.0",
    )
    assert result.readable
    assert result.page_count == 1


def test_resume_skips_successful_pages() -> None:
    plan = build_processing_plan(
        inspection(("native", "raster", "raster")),
        purpose="audit",
        classification="internal",
        policy=policy(),
    )
    assert pages_for_resume(plan, frozenset({1, 2})) == (3,)


def test_receipt_reconciliation_complete_and_deterministic() -> None:
    plan = build_processing_plan(
        inspection(("native", "native")),
        purpose="audit",
        classification="internal",
        policy=policy(),
    )
    shard = plan.shards[0]
    receipts = tuple(
        ProcessingReceipt(
            plan.scope,
            uuid4(),
            plan.processing_plan_id,
            1,
            shard.shard_id,
            page,
            uuid4(),
            f"page-{page}",
            ReceiptStatus.VALIDATED,
            DIGEST_B,
            (),
            NOW,
        )
        for page in (1, 2)
    )
    first = reconcile_processing(plan, receipts)
    second = reconcile_processing(plan, receipts)
    assert first.outcome is CorpusOutcome.COMPLETE
    assert first.receipt_fingerprint == second.receipt_fingerprint


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((ReceiptStatus.VALIDATED, ReceiptStatus.FAILED), CorpusOutcome.PARTIAL),
        ((ReceiptStatus.FAILED, ReceiptStatus.FAILED), CorpusOutcome.PROVIDER_FAILED),
        ((ReceiptStatus.VALIDATED, ReceiptStatus.UNKNOWN), CorpusOutcome.UNRESOLVED),
    ],
)
def test_partial_failure_and_unknown_never_become_empty_success(
    statuses: tuple[ReceiptStatus, ReceiptStatus], expected: CorpusOutcome
) -> None:
    plan = build_processing_plan(
        inspection(("native", "native")),
        purpose="audit",
        classification="internal",
        policy=policy(),
    )
    shard = plan.shards[0]
    receipts = tuple(
        ProcessingReceipt(
            plan.scope,
            uuid4(),
            plan.processing_plan_id,
            1,
            shard.shard_id,
            page,
            uuid4(),
            f"{page}",
            status,
            DIGEST_B if status is ReceiptStatus.VALIDATED else None,
            (),
            NOW,
        )
        for page, status in enumerate(statuses, start=1)
    )
    assert reconcile_processing(plan, receipts).outcome is expected


def test_duplicate_receipt_requires_recovery_not_duplicate_logical_result() -> None:
    plan = build_processing_plan(
        inspection(("native",)), purpose="audit", classification="internal", policy=policy()
    )
    shard = plan.shards[0]
    receipts = tuple(
        ProcessingReceipt(
            plan.scope,
            uuid4(),
            plan.processing_plan_id,
            1,
            shard.shard_id,
            1,
            uuid4(),
            key,
            ReceiptStatus.VALIDATED,
            DIGEST_B,
            (),
            NOW,
        )
        for key in ("original", "duplicate-callback")
    )
    result = reconcile_processing(plan, receipts)
    assert result.outcome is CorpusOutcome.RECOVERY_REQUIRED
    assert result.duplicate_pages == (1,)


def test_failed_attempt_followed_by_validated_retry_reconciles_once() -> None:
    plan = build_processing_plan(
        inspection(("native",)), purpose="audit", classification="internal", policy=policy()
    )
    shard = plan.shards[0]
    receipts = (
        ProcessingReceipt(
            plan.scope,
            uuid4(),
            plan.processing_plan_id,
            1,
            shard.shard_id,
            1,
            uuid4(),
            "first-attempt",
            ReceiptStatus.FAILED,
            None,
            ("PROVIDER_TIMEOUT",),
            NOW,
        ),
        ProcessingReceipt(
            plan.scope,
            uuid4(),
            plan.processing_plan_id,
            1,
            shard.shard_id,
            1,
            uuid4(),
            "bounded-retry",
            ReceiptStatus.VALIDATED,
            DIGEST_B,
            (),
            NOW,
        ),
    )
    result = reconcile_processing(plan, receipts)
    assert result.outcome is CorpusOutcome.COMPLETE
    assert result.duplicate_pages == ()


def test_processing_overlap_receipt_is_context_only_and_not_duplicate_output() -> None:
    plan = build_processing_plan(
        inspection(("native",)), purpose="audit", classification="internal", policy=policy()
    )
    shard = plan.shards[0]
    logical = ProcessingReceipt(
        plan.scope,
        uuid4(),
        plan.processing_plan_id,
        1,
        shard.shard_id,
        1,
        uuid4(),
        "logical-output",
        ReceiptStatus.VALIDATED,
        DIGEST_B,
        (),
        NOW,
    )
    context = ProcessingReceipt(
        plan.scope,
        uuid4(),
        plan.processing_plan_id,
        1,
        shard.shard_id,
        1,
        uuid4(),
        "overlap-context",
        ReceiptStatus.VALIDATED,
        DIGEST_B,
        (),
        NOW,
        True,
    )
    result = reconcile_processing(plan, (logical, context))
    assert result.outcome is CorpusOutcome.COMPLETE
    assert result.duplicate_pages == ()


def test_boundary_requires_range_evidence_and_authority() -> None:
    value = BoundaryCandidate(
        scope(), uuid4(), uuid4(), 2, 4, "quality-document", "model", 0.99, ()
    )
    rejected = validate_boundary(value, page_count=3, validator_version="1.0.0")
    assert rejected.disposition is BoundaryDisposition.REJECTED
    valid_range = BoundaryCandidate(
        scope(), uuid4(), uuid4(), 1, 2, "register", "model", 0.99, (uuid4(),)
    )
    unresolved = validate_boundary(valid_range, page_count=3, validator_version="1.0.0")
    assert unresolved.disposition is BoundaryDisposition.UNRESOLVED
    accepted = validate_boundary(
        valid_range,
        page_count=3,
        validator_version="1.0.0",
        authority_decision_ref="human:boundary-review",
    )
    assert accepted.disposition is BoundaryDisposition.ACCEPTED


@pytest.mark.parametrize(
    ("ranges", "code"),
    [(((1, 2), (4, 5)), "BOUNDARY_GAP"), (((1, 3), (3, 5)), "BOUNDARY_OVERLAP")],
)
def test_boundary_set_detects_gaps_and_overlap(
    ranges: tuple[tuple[int, int], ...], code: str
) -> None:
    candidates = tuple(
        BoundaryCandidate(
            scope(), uuid4(), uuid4(), start, end, "doc", "deterministic", None, (uuid4(),)
        )
        for start, end in ranges
    )
    assert code in validate_boundary_set(candidates, page_count=5)


def audit_values() -> tuple[
    CorpusSnapshot,
    DocumentDelta,
    CausalReadinessDelta,
    PackageReadiness,
]:
    common_scope = scope()
    snapshot = CorpusSnapshot(
        common_scope,
        uuid4(),
        1,
        uuid4(),
        1,
        (PhysicalObjectRef(uuid4(), 1),),
        ((uuid4(), 1),),
        (uuid4(),),
        (),
        (),
        (),
        CorpusCoverage(1, 1, 1, 1, 1, 1, 0, "coverage-1.0.0"),
        (uuid4(),),
        uuid4(),
        NOW,
        CorpusOutcome.COMPLETE,
    )
    audit_scope = scope_from_snapshot(
        snapshot,
        mode_execution_id=uuid4(),
        audit_process_id=uuid4(),
        conflict_policy_version="1.0.0",
        authority_profile_version="1.0.0",
        contract_registry_version="1.4.0",
    )
    doc_denominator = DeltaDenominator(
        uuid4(),
        1,
        ("audit-scope",),
        ("quality-document",),
        snapshot.rule_set_version_id,
        ("rule-trace",),
    )
    item = EvidenceRatedItem(
        "quality-document",
        DeltaState.SATISFIED,
        (uuid4(),),
        (uuid4(),),
        (uuid4(),),
        ("human:pto",),
        (),
        (),
        (),
    )
    document = DocumentDelta(uuid4(), 1, audit_scope, doc_denominator, (item,))
    causal_denominator = DeltaDenominator(
        uuid4(), 1, ("batch-a",), ("batch-a",), snapshot.rule_set_version_id, ("rule-trace",)
    )
    causal = CausalReadinessDelta(
        uuid4(),
        1,
        audit_scope,
        causal_denominator,
        (
            CausalImpactPath(
                uuid4(),
                "batch-a",
                "control-a",
                "admission-a",
                "work-a",
                "evidence-a",
                "id-a",
                "volume-a",
                "ks-a",
                "claim-a",
                DeltaState.SATISFIED,
                (uuid4(),),
                (),
                (),
            ),
        ),
    )
    package_denominator = DeltaDenominator(
        uuid4(), 1, ("package-a",), ("package-a",), snapshot.rule_set_version_id, ("rule-trace",)
    )
    package = PackageReadiness(
        uuid4(),
        1,
        audit_scope,
        package_denominator,
        (
            PackageAssessment(
                uuid4(),
                1,
                uuid4(),
                "section-a",
                (PackageMembership(uuid4(), 1, 1, 1, 1),),
                DeltaState.SATISFIED,
                DeltaState.SATISFIED,
                DeltaState.SATISFIED,
                DeltaState.SATISFIED,
                DeltaState.SATISFIED,
                (),
            ),
        ),
    )
    return snapshot, document, causal, package


def test_audit_runs_only_after_exact_reconciled_snapshot_and_has_three_fingerprints() -> None:
    snapshot, document, causal, package = audit_values()
    report = assemble_audit_report(snapshot, document.audit_scope, document, causal, package, ())
    assert report.outcome is AuditTerminalOutcome.COMPLETE
    assert (
        len(
            {
                report.document_delta_fingerprint,
                report.causal_delta_fingerprint,
                report.package_readiness_fingerprint,
            }
        )
        == 3
    )
    assert not report.product_ready


def test_missing_document_is_gap_with_downstream_impact_not_no_risk() -> None:
    missing = evaluate_document_items(("incoming-control-act",), ())
    assert missing[0].state is DeltaState.MISSING
    assert missing[0].downstream_impacts == ("ID_READINESS_UNPROVEN",)


def test_all_files_found_but_unsigned_package_is_not_ready() -> None:
    snapshot, document, causal, package = audit_values()
    original = package.packages[0]
    unsigned = PackageAssessment(
        original.package_id,
        original.package_version,
        original.volume_or_book_id,
        original.section_ref,
        original.memberships,
        DeltaState.SATISFIED,
        DeltaState.SATISFIED,
        DeltaState.MISSING,
        DeltaState.MISSING,
        DeltaState.MISSING,
        ("SIGNATURE_MISSING",),
    )
    changed = PackageReadiness(
        package.package_readiness_id, 2, package.audit_scope, package.denominator, (unsigned,)
    )
    counts = package_readiness_counts(changed)
    assert counts[DeltaState.SATISFIED] == 0
    report = assemble_audit_report(snapshot, document.audit_scope, document, causal, changed, ())
    assert report.outcome is AuditTerminalOutcome.PARTIAL


def test_document_counts_do_not_treat_unknown_as_ready() -> None:
    snapshot, document, _, _ = audit_values()
    indeterminate = EvidenceRatedItem(
        "unknown",
        DeltaState.INDETERMINATE,
        (),
        (),
        (),
        (),
        ("TYPE_UNKNOWN",),
        (),
        (),
    )
    changed = DocumentDelta(
        document.document_delta_id, 2, document.audit_scope, document.denominator, (indeterminate,)
    )
    counts = document_readiness_counts(changed)
    assert counts[DeltaState.SATISFIED] == 0
    assert counts[DeltaState.INDETERMINATE] == 1
    assert snapshot.coverage.discovered_objects == 1


def test_action_request_closure_requires_independent_verifier_and_evidence() -> None:
    _, document, _, _ = audit_values()
    with pytest.raises(ValueError, match="independent"):
        ActionRequest(
            uuid4(),
            1,
            document.audit_scope,
            "SUPPLY_EVIDENCE",
            "pto",
            "batch-a",
            (),
            None,
            ("ID_BLOCKED",),
            "same",
            "same",
            ActionRequestState.OPEN,
        )
    with pytest.raises(ValueError, match="requires evidence"):
        ActionRequest(
            uuid4(),
            2,
            document.audit_scope,
            "SUPPLY_EVIDENCE",
            "pto",
            "batch-a",
            (),
            None,
            ("ID_BLOCKED",),
            "initiator",
            "verifier",
            ActionRequestState.VERIFIED_CLOSED,
        )


def test_reclassification_is_new_version_and_missing_attributes_keep_not_ready() -> None:
    previous = ClassificationVersion(
        uuid4(), 1, uuid4(), "unknown", (), "1.0.0", ("TYPE_UNKNOWN",), None, None
    )
    updated = ClassificationVersion(
        previous.classification_id,
        2,
        previous.occurrence_id,
        "quality_certificate",
        (),
        "1.1.0",
        ("MANUFACTURER_MISSING", "BATCH_ID_MISSING"),
        None,
        1,
    )
    assert not updated.ready
    assert updated.supersedes_version == previous.version


def test_customer_and_pto_projection_rebuild_preserves_canonical_inputs() -> None:
    snapshot, document, causal, package = audit_values()
    first = rebuild_customer_projection(snapshot, document, causal, package, freshness_at=NOW)
    second = rebuild_customer_projection(snapshot, document, causal, package, freshness_at=NOW)
    assert first.fingerprint == second.fingerprint
    request = ActionRequest(
        uuid4(),
        1,
        document.audit_scope,
        "CLASSIFY_DOCUMENT",
        "pto",
        "occurrence-a",
        (),
        None,
        ("DOCUMENT_DELTA_OPEN",),
        "initiator",
        "verifier",
        ActionRequestState.OPEN,
    )
    pto = rebuild_pto_projection(snapshot, (request,), failed_or_unknown_pages=2, freshness_at=NOW)
    assert pto.action_request_states == (("open", 1),)


def test_duplicate_bytes_do_not_merge_workspace_authority() -> None:
    first = inspection(("native",))
    second = PhysicalObjectInspection(
        CorpusScope(first.scope.organization_id, uuid4()),
        uuid4(),
        uuid4(),
        1,
        first.digest,
        first.size_bytes,
        first.media_type,
        False,
        True,
        1,
        first.pages,
        0,
        0,
        first.inspection_profile_version,
        NOW,
    )
    assert first.digest == second.digest
    assert first.scope.workspace_id != second.scope.workspace_id
    assert first.physical_object_id != second.physical_object_id


def test_corpus_snapshot_explicitly_preserves_unknown_collection_coverage() -> None:
    common = scope()
    unresolved = UnresolvedCorpusItem(
        uuid4(), "LOCATION_NOT_YET_COLLECTED", "unknown-location", True
    )
    snapshot = CorpusSnapshot(
        common,
        uuid4(),
        1,
        uuid4(),
        1,
        (),
        (),
        (),
        (),
        (),
        (unresolved,),
        CorpusCoverage(0, 0, 0, 0, 0, 0, 1, "coverage-unknown-1.0.0"),
        (uuid4(),),
        uuid4(),
        NOW,
        CorpusOutcome.UNRESOLVED,
    )
    assert snapshot.outcome is CorpusOutcome.UNRESOLVED
    assert snapshot.coverage.unresolved_items == 1


def test_corpus_snapshot_rejects_inventory_count_substitution() -> None:
    with pytest.raises(ValueError, match="physical-object inventory"):
        CorpusSnapshot(
            scope(),
            uuid4(),
            1,
            uuid4(),
            1,
            (),
            (),
            (),
            (),
            (),
            (),
            CorpusCoverage(1, 0, 0, 0, 0, 0, 0, "coverage-1.0.0"),
            (uuid4(),),
            uuid4(),
            NOW,
            CorpusOutcome.PARTIAL,
        )


def test_audit_command_state_machine_is_optimistic_and_rejects_without_event() -> None:
    machine = AuditStateMachine()
    command = AuditCommand(
        uuid4(),
        AuditCommandType.START_COLLECTION,
        uuid4(),
        0,
        "start-collection",
        "human:collector",
        "corpus.collect",
        uuid4(),
        uuid4(),
        DIGEST_A,
    )
    accepted = machine.apply(ProcessState.REQUESTED, 0, command)
    assert accepted.accepted
    assert accepted.event_name == "CollectionMissionStarted"
    stale = machine.apply(ProcessState.REQUESTED, 1, command)
    assert not stale.accepted
    assert stale.event_name is None


def test_audit_cannot_skip_snapshot_and_jump_to_evaluation() -> None:
    command = AuditCommand(
        uuid4(),
        AuditCommandType.START_AUDIT,
        uuid4(),
        1,
        "start-audit",
        "human:auditor",
        "audit.start",
        uuid4(),
        uuid4(),
        DIGEST_A,
    )
    outcome = AuditStateMachine().apply(ProcessState.COLLECTING, 1, command)
    assert not outcome.accepted
    assert outcome.outcome_code == "TRANSITION_DENIED"
    assert outcome.event_name is None
