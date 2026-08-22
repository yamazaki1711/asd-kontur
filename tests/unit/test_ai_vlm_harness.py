from __future__ import annotations

import sys
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Thread
from uuid import UUID

import pytest
from pypdf import PdfWriter

from asd_kontur.domain import uuid7
from asd_kontur.harness.batch import BatchCoordinator, BatchItem, BatchItemState, BatchManifest
from asd_kontur.harness.errors import HarnessError, HarnessErrorCode
from asd_kontur.harness.models import (
    CandidateStatus,
    CandidateVersion,
    ExecutionBudget,
    ExecutionIdentity,
    ExecutionRequest,
    FieldCandidate,
    Locator,
    ProviderExecutionResult,
    ProviderState,
    Repairability,
    Scope,
    ValidationFailure,
    digest_of,
)
from asd_kontur.harness.native import (
    NativeLayer,
    NativePreflight,
    PdfNativeExtractor,
    PreflightDisposition,
    PreflightInput,
)
from asd_kontur.harness.providers import (
    DeterministicExternalProvider,
    LocalProcessProfile,
    LocalQwenProcessProvider,
)
from asd_kontur.harness.qualification import (
    ZERO_TOLERANCE_BLOCKERS,
    MetricObservation,
    QualificationProfile,
)
from asd_kontur.harness.repair import RepairController
from asd_kontur.harness.routing import (
    CostEnvelope,
    CostLedger,
    RoutingContext,
    RoutingPolicy,
    route,
)
from asd_kontur.harness.validation import (
    VALIDATION_FAILURE_CODES,
    ValidationContext,
    ValidatorRegistry,
    common_validator,
    geometry_validator,
    legal_validator,
)

ORG = UUID("018f0000-0000-7000-8000-000000000001")
WORKSPACE = UUID("018f0000-0000-7000-8000-000000000002")
SOURCE = UUID("018f0000-0000-7000-8000-000000000003")
LOCATOR_ID = UUID("018f0000-0000-7000-8000-000000000004")


def identity(*, quantization: str = "8bit", revision: str = "sha256:model") -> ExecutionIdentity:
    return ExecutionIdentity(
        "provider.local.qwen",
        "1.0.0",
        "Qwen3.8-27B",
        revision,
        "mlx",
        quantization,
        "mlx-evaluation",
        f"qwen-{quantization}-evaluation-1.0.0",
        "prompt-1.0.0",
        "candidate-0.1.0",
        "preprocess-1.0.0",
        "render-1.0.0",
        "verify-1.0.0",
    )


def request(
    *,
    workspace: UUID = WORKSPACE,
    idempotency: str = "request-1",
    profile: ExecutionIdentity | None = None,
) -> ExecutionRequest:
    scope = Scope(ORG, workspace)
    return ExecutionRequest(
        uuid7(),
        uuid7(),
        scope,
        SOURCE,
        "sha256:" + "a" * 64,
        (Locator(SOURCE, LOCATOR_ID, 1),),
        "synthetic.extract",
        "1.0.0",
        "synthetic",
        route=__import__("asd_kontur.harness.models", fromlist=["Route"]).Route.LOCAL_VLM,
        identity=profile or identity(),
        rule_set_version="rules-1.0.0",
        authorization_id=uuid7(),
        policy_versions=("policy-1.0.0",),
        budget=ExecutionBudget(
            "budget.synthetic", "1.0.0", 2, 1, 5, 100, 3, 4096, 1, False, "10 TEST"
        ),
        idempotency_key=idempotency,
        correlation_id=uuid7(),
        causation_id=uuid7(),
        payload_digest="sha256:" + "b" * 64,
    )


def candidate(
    *,
    status: CandidateStatus = CandidateStatus.UNVERIFIED,
    fields: tuple[FieldCandidate, ...] | None = None,
) -> CandidateVersion:
    actual = fields or (
        FieldCandidate(
            "/name",
            "string",
            "synthetic",
            (Locator(SOURCE, LOCATOR_ID, 1),),
            ("evidence:synthetic",),
        ),
    )
    refs = ("validation:1",) if status == CandidateStatus.VALIDATED_CANDIDATE else ()
    return CandidateVersion(
        uuid7(),
        1,
        Scope(ORG, WORKSPACE),
        "synthetic.extract",
        "vlm",
        actual,
        status,
        SOURCE,
        uuid7(),
        validation_refs=refs,
    )


def test_native_sufficient_never_needs_provider() -> None:
    result = NativePreflight().evaluate(
        PreflightInput(
            "sha256:a",
            "sha256:a",
            (Locator(SOURCE, LOCATOR_ID, 1),),
            "application/pdf",
            "synthetic",
            "extract",
            True,
            NativeLayer("application/pdf", "x", (("name", "ok"),), "pdf.native", "1.0.0"),
            False,
        ),
        required_fields=frozenset({"name"}),
    )
    assert result.disposition == PreflightDisposition.NATIVE_SUFFICIENT


def test_short_native_text_is_not_automatic_raster_route() -> None:
    result = NativePreflight().evaluate(
        PreflightInput(
            "a",
            "a",
            (Locator(SOURCE, LOCATOR_ID, 1),),
            "application/pdf",
            "synthetic",
            "extract",
            True,
            NativeLayer("application/pdf", "x", (), "pdf.native", "1.0.0"),
            False,
        ),
        required_fields=frozenset({"name"}),
    )
    assert result.disposition == PreflightDisposition.EXTERNAL_ROUTE_DENIED


def test_pdf_native_extractor_uses_exact_one_based_pages(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with path.open("wb") as stream:
        writer.write(stream)
    layer = PdfNativeExtractor("pypdf-6").extract(
        path.read_bytes(), (Locator(SOURCE, LOCATOR_ID, 1),)
    )
    assert layer.text == "" and layer.structured_fields == ()
    with pytest.raises(ValueError, match="outside"):
        PdfNativeExtractor("pypdf-6").extract(path.read_bytes(), (Locator(SOURCE, LOCATOR_ID, 2),))


def test_source_change_is_typed_stale() -> None:
    result = NativePreflight().evaluate(
        PreflightInput(
            "a",
            "b",
            (Locator(SOURCE, LOCATOR_ID, 1),),
            "application/pdf",
            "synthetic",
            "extract",
            True,
            None,
            False,
        ),
        required_fields=frozenset(),
    )
    assert result.disposition == PreflightDisposition.SOURCE_STALE


@pytest.mark.parametrize("classification", [None, "ambiguous", "expired", "unset"])
def test_external_route_is_default_deny_for_bad_classification(classification: str | None) -> None:
    policy = RoutingPolicy(
        "routing.dev",
        "1.0.0",
        "development",
        True,
        frozenset({"synthetic"}),
        frozenset({"batch"}),
        True,
        "no_raw_storage",
    )
    decision = route(
        RoutingContext(
            Scope(ORG, WORKSPACE),
            classification,
            "batch",
            True,
            False,
            False,
            False,
            True,
            True,
            True,
            True,
            False,
            True,
        ),
        policy,
        authorization_ref="auth:1",
    )
    assert decision.route.value == "no_execution"


def test_local_unavailable_does_not_expand_local_only_egress() -> None:
    policy = RoutingPolicy(
        "routing.dev",
        "1.0.0",
        "development",
        True,
        frozenset({"legal"}),
        frozenset({"legal"}),
        True,
        "no_raw_storage",
    )
    decision = route(
        RoutingContext(
            Scope(ORG, WORKSPACE),
            "legal",
            "legal",
            True,
            False,
            False,
            False,
            True,
            True,
            True,
            True,
            True,
            True,
        ),
        policy,
        authorization_ref="auth:1",
    )
    assert decision.route.value == "no_execution"


def test_provider_result_is_not_candidate() -> None:
    result = ProviderExecutionResult(
        uuid7(),
        uuid7(),
        uuid7(),
        Scope(ORG, WORKSPACE),
        identity(),
        ProviderState.COMPLETED,
        "ok",
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
        {"confidence": 1.0},
        datetime.now(UTC),
    )
    assert not isinstance(result, CandidateVersion)


def test_high_confidence_remains_candidate() -> None:
    value = candidate(
        fields=(
            FieldCandidate("/confidence", "number", 1.0, (Locator(SOURCE, LOCATOR_ID, 1),), ()),
        )
    )
    assert value.status == CandidateStatus.UNVERIFIED
    assert not hasattr(value, "confirmed")


def test_validated_candidate_requires_material_locators() -> None:
    with pytest.raises(ValueError, match="locator"):
        candidate(
            status=CandidateStatus.VALIDATED_CANDIDATE,
            fields=(FieldCandidate("/name", "string", "x", (), ()),),
        )


def test_validator_registry_reports_missing_locator_unit_and_skipped() -> None:
    value = candidate(fields=(FieldCandidate("/quantity", "number", 2, (), ()),))
    registry = ValidatorRegistry()
    registry.register("common", "1.0.0", common_validator)
    context = ValidationContext(
        frozenset({str(LOCATOR_ID)}),
        frozenset({"/name"}),
        frozenset({"/quantity"}),
        frozenset(),
        frozenset(),
    )
    result = registry.validate(
        value, context, (("common", "1.0.0"), ("mandatory.missing", "1.0.0"))
    )
    assert result.status == "indeterminate"
    assert {item.code for item in result.failures} == {
        "SCHEMA_REQUIRED_FIELD_MISSING",
        "LOCATOR_INVALID",
        "UNIT_MISSING",
    }


def test_required_validation_failure_vocabulary_is_registered() -> None:
    assert len(VALIDATION_FAILURE_CODES) == 18
    assert {
        "EDITION_UNAVAILABLE",
        "PROVIDER_RESULT_INTEGRITY_FAILED",
        "SOURCE_STALE",
    } <= VALIDATION_FAILURE_CODES


def test_legal_and_geometry_are_not_model_decided() -> None:
    value = candidate(
        fields=(
            FieldCandidate(
                "/legal/citation", "string", "invented", (Locator(SOURCE, LOCATOR_ID, 1),), ()
            ),
            FieldCandidate(
                "/geometry/value", "number", 10, (Locator(SOURCE, LOCATOR_ID, 1),), (), "mm"
            ),
        )
    )
    context = ValidationContext(
        frozenset({str(LOCATOR_ID)}), frozenset(), frozenset(), frozenset(), frozenset()
    )
    assert {item.code for item in legal_validator(value, context)} == {"LEGAL_LOCATOR_UNVERIFIED"}
    assert {item.code for item in geometry_validator(value, context)} == {
        "GEOMETRY_INPUT_UNCONFIRMED"
    }


def test_targeted_repair_is_immutable_and_restricted() -> None:
    parent = candidate()
    failure = ValidationFailure(
        "TYPE_MISMATCH",
        "type",
        "1.0.0",
        "/name",
        "blocker",
        (Locator(SOURCE, LOCATOR_ID, 1),),
        (),
        Repairability.TARGETED_REPAIR,
        True,
    )
    controller = RepairController(2, 1)
    plan = controller.plan(repair_id=uuid7(), candidate=parent, failures=(failure,), cycle=1)
    child, conflicts = controller.reconcile(
        parent=parent,
        plan=plan,
        replacements=(
            FieldCandidate("/name", "string", "repaired", (Locator(SOURCE, LOCATOR_ID, 1),), ()),
        ),
        new_attempt_id=uuid7(),
    )
    assert parent.fields[0].value == "synthetic"
    assert child.version == 2 and child.fields[0].value == "repaired" and not conflicts


def test_repeated_repair_failure_stops() -> None:
    parent = candidate()
    failure = ValidationFailure(
        "TYPE_MISMATCH",
        "type",
        "1.0.0",
        "/name",
        "blocker",
        (Locator(SOURCE, LOCATOR_ID, 1),),
        (),
        Repairability.TARGETED_REPAIR,
        True,
    )
    with pytest.raises(HarnessError) as captured:
        RepairController(2, 1).plan(
            repair_id=uuid7(),
            candidate=parent,
            failures=(failure,),
            cycle=2,
            prior_failure_sets=(frozenset({failure.fingerprint}),),
        )
    assert captured.value.code == HarnessErrorCode.REPAIR_NO_PROGRESS


def test_conflicting_repairs_create_field_conflict() -> None:
    parent = candidate()
    failure = ValidationFailure(
        "TYPE_MISMATCH",
        "type",
        "1.0.0",
        "/name",
        "blocker",
        (Locator(SOURCE, LOCATOR_ID, 1),),
        (),
        Repairability.TARGETED_REPAIR,
        True,
    )
    controller = RepairController(2, 1)
    plan = controller.plan(repair_id=uuid7(), candidate=parent, failures=(failure,), cycle=1)
    values = (
        FieldCandidate("/name", "string", "a", (Locator(SOURCE, LOCATOR_ID, 1),), ()),
        FieldCandidate("/name", "string", "b", (Locator(SOURCE, LOCATOR_ID, 1),), ()),
    )
    child, conflicts = controller.reconcile(
        parent=parent, plan=plan, replacements=values, new_attempt_id=uuid7()
    )
    assert child.status == CandidateStatus.UNRESOLVED_UNCERTAINTY and len(conflicts) == 1


def test_fake_external_async_idempotency_unknown_cancel_and_reconcile() -> None:
    provider = DeterministicExternalProvider(lambda _: {"field": "synthetic"})
    value = request()
    first = provider.submit(value)
    duplicate = provider.submit(value)
    assert duplicate.duplicate and duplicate.execution_id == first.execution_id
    provider.mark_unknown(first.execution_id)
    with pytest.raises(HarnessError) as captured:
        provider.fetch_result(first.execution_id)
    assert captured.value.code == HarnessErrorCode.PROVIDER_UNKNOWN_OUTCOME
    completed = provider.complete(first.execution_id)
    assert provider.fetch_result(first.execution_id) == completed


def test_batch_rejects_cross_workspace_and_never_false_success() -> None:
    provider = DeterministicExternalProvider(lambda _: {"ok": True})
    with pytest.raises(HarnessError):
        BatchManifest(
            uuid7(),
            Scope(ORG, WORKSPACE),
            (BatchItem(uuid7(), request(workspace=uuid7())),),
            1,
            "1.0.0",
        )
    manifest = BatchManifest(
        uuid7(),
        Scope(ORG, WORKSPACE),
        (BatchItem(uuid7(), request()), BatchItem(uuid7(), request(idempotency="request-2"))),
        1,
        "1.0.0",
    )
    running = BatchCoordinator(provider).submit_pending(manifest)
    assert sum(item.state == BatchItemState.SUBMITTED for item in running.items) == 1
    assert not BatchCoordinator.terminal_success(running)


def test_cost_reservation_precedes_side_effect() -> None:
    now = datetime.now(UTC)
    ledger = CostLedger(
        CostEnvelope(
            uuid7(),
            "1.0.0",
            Scope(ORG, WORKSPACE),
            "synthetic",
            "fake",
            "TEST",
            Decimal("10"),
            Decimal("5"),
            Decimal("1"),
            now + timedelta(hours=1),
            "human:test",
        )
    )
    assert ledger.reserve("item-1", Decimal("4"), now)
    assert not ledger.reserve("item-2", Decimal("5"), now)
    ledger.commit("item-1", Decimal("3"))
    assert ledger.remaining == Decimal("7")


def test_exact_profile_tuple_prevents_qualification_inheritance() -> None:
    now = datetime.now(UTC)
    metrics = (MetricObservation("critical", 1.0, 1.0, True),)
    blockers = tuple((key, 0) for key in sorted(ZERO_TOLERANCE_BLOCKERS))
    profile = QualificationProfile(
        "q",
        "1.0.0",
        identity(),
        "corpus-1.0.0",
        ("synthetic",),
        metrics,
        blockers,
        now,
        now + timedelta(days=1),
        "qualification",
        "qualified",
        "human:approver",
    )
    assert profile.is_qualified(identity(), now)
    assert not profile.is_qualified(identity(revision="sha256:other"), now)
    assert not profile.is_qualified(identity(quantization="bf16"), now)


def test_average_cannot_override_critical_floor_or_blocker() -> None:
    now = datetime.now(UTC)
    blockers = tuple(
        (key, 1 if key == "invented_locator" else 0) for key in sorted(ZERO_TOLERANCE_BLOCKERS)
    )
    profile = QualificationProfile(
        "q",
        "1.0.0",
        identity(),
        "corpus",
        ("synthetic",),
        (
            MetricObservation("average", 0.99, 0.5, False),
            MetricObservation("critical", 0.9, 1.0, True),
        ),
        blockers,
        now,
        now + timedelta(days=1),
        "qualification",
        "qualified",
        "human",
    )
    assert not profile.is_qualified(identity(), now)


@pytest.mark.parametrize("blocker", sorted(ZERO_TOLERANCE_BLOCKERS))
def test_each_zero_tolerance_blocker_denies_qualification(blocker: str) -> None:
    now = datetime.now(UTC)
    profile = QualificationProfile(
        "q",
        "1.0.0",
        identity(),
        "corpus",
        ("synthetic",),
        (MetricObservation("critical", 1.0, 1.0, True),),
        tuple((key, int(key == blocker)) for key in sorted(ZERO_TOLERANCE_BLOCKERS)),
        now,
        now + timedelta(days=1),
        "qualification",
        "qualified",
        "human",
    )
    assert not profile.is_qualified(identity(), now)


def test_local_process_boundary_uses_typed_files_and_no_shell(tmp_path: Path) -> None:
    runner = tmp_path / "runner.py"
    model = tmp_path / "model"
    model.mkdir()
    runner.write_text(
        "import argparse,json\np=argparse.ArgumentParser();p.add_argument('--model');p.add_argument('--request');p.add_argument('--result');a=p.parse_args();r=json.load(open(a.request));json.dump({'request_digest':r['request_digest'],'identity_fingerprint':r['identity_fingerprint'],'structured_payload':{'ok':True}},open(a.result,'w'))",
        encoding="utf-8",
    )
    provider = LocalQwenProcessProvider(
        LocalProcessProfile(Path(sys.executable), runner, model, identity(), 5)
    )
    assert provider.health("profile").available
    assert not provider.health("profile").qualified
    receipt = provider.submit(request())
    assert receipt.state == ProviderState.COMPLETED
    assert provider.fetch_result(receipt.execution_id).structured_payload == {"ok": True}


def test_local_bounded_batch_uses_one_managed_session(tmp_path: Path) -> None:
    runner = tmp_path / "batch_runner.py"
    model = tmp_path / "model"
    model.mkdir()
    runner.write_text(
        "import argparse,json\np=argparse.ArgumentParser();p.add_argument('--model');p.add_argument('--request');p.add_argument('--result');a=p.parse_args();r=json.load(open(a.request));json.dump({'results':[{'request_digest':i['request_digest'],'identity_fingerprint':i['identity_fingerprint'],'structured_payload':{'page':n+1}} for n,i in enumerate(r['requests'])]},open(a.result,'w'))",
        encoding="utf-8",
    )
    provider = LocalQwenProcessProvider(
        LocalProcessProfile(Path(sys.executable), runner, model, identity(), 5)
    )
    receipts = provider.submit_bounded_batch((request(), request(idempotency="request-2")))
    assert len(receipts) == 2
    assert [provider.fetch_result(item.execution_id).structured_payload for item in receipts] == [
        {"page": 1},
        {"page": 2},
    ]


def test_local_process_can_be_cancelled_and_terminated(tmp_path: Path) -> None:
    runner = tmp_path / "slow_runner.py"
    model = tmp_path / "model"
    model.mkdir()
    runner.write_text("import time\ntime.sleep(30)", encoding="utf-8")
    provider = LocalQwenProcessProvider(
        LocalProcessProfile(Path(sys.executable), runner, model, identity(), 60)
    )
    value = request()
    outcome: list[object] = []
    thread = Thread(target=lambda: outcome.append(provider.submit(value)))
    thread.start()
    deadline = time.monotonic() + 5
    while not provider._processes and time.monotonic() < deadline:
        time.sleep(0.01)
    execution_id = next(iter(provider._processes))
    receipt = provider.cancel(execution_id, "synthetic.cancel")
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert receipt.state == ProviderState.CANCELLED
    assert provider.poll(execution_id) == ProviderState.CANCELLED


def test_hostile_source_data_cannot_mutate_envelope() -> None:
    value = request()
    hostile = {
        "workspace_id": "other",
        "provider": "external",
        "authority": "model",
        "terminal_outcome": "fact",
    }
    assert digest_of(hostile) != value.request_digest
    assert value.scope.workspace_id == WORKSPACE and value.route.value == "local_vlm"
