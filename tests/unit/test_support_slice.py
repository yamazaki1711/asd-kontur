from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from asd_kontur.harness.models import digest_of
from asd_kontur.kernel.models import Applicability, Quantity
from asd_kontur.support.errors import SupportError, SupportErrorCode
from asd_kontur.support.evaluation import (
    evaluate_commercial_readiness,
    evaluate_control,
    evaluate_id_completeness,
    evaluate_material_admission,
    evaluate_work_readiness,
)
from asd_kontur.support.generation import (
    SyntheticOoxmlGenerationPipeline,
    validate_docx,
    validate_xlsx,
)
from asd_kontur.support.geometry import form_executive_scheme
from asd_kontur.support.models import (
    CalibrationEvidence,
    CommercialReadinessInput,
    ControlEvidence,
    ControlOutcome,
    DocumentCoverageEvidence,
    DocumentRequirementEvidence,
    FieldResolution,
    GenerationRequest,
    GeometryInput,
    GeometryOutcome,
    MaterialAdmission,
    MaterialBatchEvidence,
    OfflineDisposition,
    OfflineFactEnvelope,
    ProfessionalAuthority,
    ResolutionState,
    SupportState,
    SupportTerminalResult,
    WorkReadiness,
    WorkReadinessInput,
    require_independent_authorities,
)
from asd_kontur.support.offline import OfflineFactReconciler
from asd_kontur.support.process import (
    SupportCommand,
    SupportCommandType,
    SupportProcessStateMachine,
)


def uid(value: int) -> UUID:
    return UUID(int=value)


def authority(
    capability: str = "support.engineering.confirm", identity: str = "human:engineer"
) -> ProfessionalAuthority:
    return ProfessionalAuthority(identity, uid(100), 1, capability, "qualification:synthetic@1")


def quantity(value: str, unit: str = "m3") -> Quantity:
    return Quantity(Decimal(value), unit, 3, "rounding@1.0.0")


def work_input(**changes: object) -> WorkReadinessInput:
    base = WorkReadinessInput(
        uid(1),
        1,
        True,
        uid(2),
        1,
        ("performed",),
        ("passed",),
        (MaterialAdmission.ADMITTED,),
        ("satisfied",),
        (),
        uid(3),
    )
    return replace(base, **changes)


def material(**changes: object) -> MaterialBatchEvidence:
    base = MaterialBatchEvidence(
        uid(4),
        1,
        "material:synthetic@1",
        "batch-synthetic-01",
        "manufacturer:synthetic",
        "supplier:synthetic",
        quantity("10", "kg"),
        (uid(5),),
        (uid(6),),
        uid(7),
        True,
        True,
        authority("support.material.admit", "human:incoming-control"),
    )
    return replace(base, **changes)


def control(**changes: object) -> ControlEvidence:
    observed = datetime(2026, 8, 23, tzinfo=UTC)
    calibration = CalibrationEvidence(
        uid(8),
        "instrument:synthetic",
        observed - timedelta(days=1),
        observed + timedelta(days=1),
        uid(9),
    )
    base = ControlEvidence(
        uid(10),
        1,
        "method@1.0.0",
        "absolute deviation <= tolerance",
        Decimal("1.0"),
        Decimal("1.0"),
        "mm",
        observed,
        uid(11),
        1,
        uid(12),
        uid(13),
        authority("support.control.confirm", "human:control"),
        calibration,
        True,
    )
    return replace(base, **changes)


def confirmed_field(key: str, value: str, suffix: int) -> FieldResolution:
    return FieldResolution(
        key,
        ResolutionState.CONFIRMED,
        value,
        value,
        uid(1000 + suffix),
        1,
        (uid(2000 + suffix),),
        (uid(3000 + suffix),),
    )


def generation_request(format_name: str, fields: tuple[FieldResolution, ...]) -> GenerationRequest:
    return GenerationRequest(
        uid(20),
        uid(21),
        "required-document:synthetic-aosr@1.0.0",
        f"template:synthetic-{format_name.lower()}@1.0.0",
        "field-schema@1.0.0",
        "binding-plan@1",
        "renderer:synthetic-ooxml@1.0.0",
        "validator:synthetic-structural@1.0.0",
        format_name,
        fields,
        uid(22),
        ("support-development@1.0.0",),
        f"generation:{format_name.lower()}:1",
    )


def geometry(kind: str, points: tuple[tuple[Decimal, Decimal], ...]) -> GeometryInput:
    return GeometryInput(
        uid(30 if kind == "design" else 31),
        kind,
        uid(32 if kind == "design" else 33),
        1,
        uid(34),
        uid(35),
        "crs:synthetic-local@1",
        "frame:synthetic@1",
        "mm",
        1,
        points,
        True,
        "human",
        "measurement:synthetic@1",
        True,
    )


def test_model_identity_cannot_hold_professional_authority() -> None:
    with pytest.raises(ValueError, match="human identity"):
        authority(identity="model:qwen")


def test_professional_review_and_finalization_require_independent_people() -> None:
    reviewer = authority("support.document.review", "human:reviewer")
    with pytest.raises(ValueError, match="Independent"):
        require_independent_authorities(
            reviewer,
            replace(reviewer, capability="support.deliverable.finalize"),
        )
    require_independent_authorities(
        reviewer,
        ProfessionalAuthority(
            "human:finalizer",
            uid(101),
            1,
            "support.deliverable.finalize",
            "qualification:synthetic@1",
        ),
    )


def test_planned_work_is_not_performed_and_missing_predecessor_blocks() -> None:
    missing_fact = evaluate_work_readiness(
        work_input(performed_fact_id=None, performed_fact_version=None)
    )
    assert missing_fact.outcome is WorkReadiness.INDETERMINATE
    blocked = evaluate_work_readiness(work_input(predecessor_states=("planned",)))
    assert blocked.outcome is WorkReadiness.BLOCKED
    assert "PREDECESSOR_NOT_COMPLETE" in blocked.reason_codes


def test_hidden_work_requires_evidence_before_covering_checkpoint() -> None:
    due = datetime(2026, 8, 23, 10, tzinfo=UTC)
    result = evaluate_work_readiness(
        work_input(
            hidden_work=True,
            checkpoint_due_at=due,
            evidence_recorded_at=due + timedelta(minutes=1),
        )
    )
    assert result.outcome is WorkReadiness.BLOCKED
    assert result.reason_codes == ("HIDDEN_WORK_EVIDENCE_LATE",)


def test_complete_work_readiness_is_reproducible() -> None:
    first = evaluate_work_readiness(work_input())
    second = evaluate_work_readiness(work_input())
    assert first.outcome is WorkReadiness.READY
    assert first.fingerprint == second.fingerprint


def test_material_requires_quality_documents_custody_and_control() -> None:
    waiting = evaluate_material_admission(
        material(certificate_evidence_ids=(), custody_chain_complete=False)
    )
    assert waiting.outcome is MaterialAdmission.WAITING_FOR_DOCUMENTS
    assert set(waiting.reason_codes) == {"QUALITY_DOCUMENT_MISSING", "CUSTODY_GAP"}
    admitted = evaluate_material_admission(material())
    assert admitted.outcome is MaterialAdmission.ADMITTED


def test_material_conflict_quarantines_instead_of_fuzzy_match() -> None:
    result = evaluate_material_admission(material(conflict_ids=(uid(99),)))
    assert result.outcome is MaterialAdmission.QUARANTINED


def test_control_tolerance_boundary_is_inclusive_and_negative_is_preserved() -> None:
    boundary = evaluate_control(control())
    failed = evaluate_control(control(observed_value=Decimal("1.1")))
    retest = evaluate_control(
        control(observed_value=Decimal("0.5"), supersedes_control_result_id=uid(999))
    )
    assert boundary.outcome is ControlOutcome.PASSED
    assert failed.outcome is ControlOutcome.FAILED
    assert retest.outcome is ControlOutcome.PASSED
    assert failed.fingerprint != retest.fingerprint


def test_missing_or_expired_calibration_is_indeterminate() -> None:
    missing = evaluate_control(control(calibration=None))
    observed = datetime(2026, 8, 23, tzinfo=UTC)
    expired_calibration = CalibrationEvidence(
        uid(8), "instrument:synthetic", observed - timedelta(days=2), observed, uid(9)
    )
    expired = evaluate_control(control(calibration=expired_calibration))
    assert missing.reason_codes == ("CALIBRATION_MISSING",)
    assert expired.reason_codes == ("CALIBRATION_EXPIRED",)


def test_required_vs_actual_id_delta_is_deterministic() -> None:
    requirements = (
        DocumentRequirementEvidence(
            uid(40),
            1,
            Applicability.APPLICABLE,
            "rule@1",
            uid(41),
            uid(42),
            uid(43),
            "before_cover",
            "pto",
        ),
        DocumentRequirementEvidence(
            uid(44),
            1,
            Applicability.APPLICABLE,
            "rule@1",
            uid(45),
            uid(46),
            uid(47),
            "presentation",
            "control",
        ),
        DocumentRequirementEvidence(
            uid(48),
            1,
            Applicability.INDETERMINATE,
            "rule@1",
            uid(49),
            uid(50),
            uid(51),
            "presentation",
            "pto",
        ),
    )
    coverages = (DocumentCoverageEvidence(uid(40), 1, "covered", (uid(52),), True),)
    first = evaluate_id_completeness(requirements, coverages)
    second = evaluate_id_completeness(tuple(reversed(requirements)), coverages)
    assert first.missing == (uid(44),)
    assert first.indeterminate == (uid(48),)
    assert first.fingerprint == second.fingerprint


def test_missing_generation_field_is_gap_not_placeholder() -> None:
    missing = FieldResolution(
        "unknown_signer",
        ResolutionState.MISSING,
        None,
        None,
        None,
        None,
        (),
        (),
    )
    with pytest.raises(SupportError) as failure:
        SyntheticOoxmlGenerationPipeline().generate(generation_request("DOCX", (missing,)))
    assert failure.value.code is SupportErrorCode.GENERATION_BLOCKED


def test_generation_rejects_mutable_latest_version() -> None:
    with pytest.raises(ValueError, match="latest"):
        replace(
            generation_request("DOCX", (confirmed_field("work", "Work A", 1),)),
            template_version_ref="latest",
        )


@pytest.mark.parametrize("format_name", ["DOCX", "XLSX"])
def test_generation_is_fresh_stateless_and_deterministic(format_name: str) -> None:
    pipeline = SyntheticOoxmlGenerationPipeline()
    first_request = generation_request(format_name, (confirmed_field("work", "Work A", 1),))
    first = pipeline.generate(first_request)
    second = pipeline.generate(replace(first_request, generation_run_id=uid(9999)))
    assert first.package_bytes == second.package_bytes
    assert first.bytes_digest == second.bytes_digest
    changed = pipeline.generate(
        replace(
            first_request,
            generation_run_id=uid(9998),
            fields=(confirmed_field("work", "Work B", 1),),
        )
    )
    assert b"Work A" not in changed.package_bytes
    assert changed.bytes_digest != first.bytes_digest


def test_docx_structural_validation_detects_unresolved_token() -> None:
    candidate = SyntheticOoxmlGenerationPipeline().generate(
        generation_request("DOCX", (confirmed_field("work", "Work A", 1),))
    )
    with zipfile.ZipFile(io.BytesIO(candidate.package_bytes)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    members["word/document.xml"] = members["word/document.xml"].replace(b"Work A", b"{{missing}}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for name, payload in members.items():
            target.writestr(name, payload)
    result = validate_docx(buffer.getvalue(), required_fields=("work",))
    assert "DOCX_UNRESOLVED_TOKEN" in result.blockers


def test_xlsx_structural_validation_checks_formula_merge_print_and_protection() -> None:
    candidate = SyntheticOoxmlGenerationPipeline().generate(
        generation_request("XLSX", (confirmed_field("volume", "10.000", 1),))
    )
    result = validate_xlsx(candidate.package_bytes, required_fields=("volume",))
    assert result.valid
    assert {
        "XLSX_FORMULA_PRESENT",
        "XLSX_LAYOUT_CONTROLS_PRESENT",
        "XLSX_PRINT_DEFINITIONS_PRESENT",
    }.issubset(result.checks)


def test_generation_candidate_is_not_template_or_print_ready() -> None:
    candidate = SyntheticOoxmlGenerationPipeline().generate(
        generation_request("DOCX", (confirmed_field("work", "Work A", 1),))
    )
    assert candidate.print_validation_level == "synthetic_structural_only"
    assert "template" not in candidate.__dataclass_fields__


def test_geometry_requires_confirmed_crs_units_and_calibration() -> None:
    design = geometry("design", ((Decimal("0"), Decimal("0")),))
    actual = geometry("as_built", ((Decimal("0.5"), Decimal("0.5")),))
    assert (
        form_executive_scheme(
            design=design,
            as_built=actual,
            tolerance=Decimal("1.0"),
            tolerance_unit="mm",
            boundary_inclusive=True,
        ).outcome
        is GeometryOutcome.ELIGIBLE
    )
    blocked = form_executive_scheme(
        design=design,
        as_built=replace(actual, crs_ref=None, calibration_valid=False),
        tolerance=Decimal("1.0"),
        tolerance_unit="mm",
        boundary_inclusive=True,
    )
    assert blocked.outcome is GeometryOutcome.BLOCKED
    assert {"AS_BUILT_CRS_MISSING", "AS_BUILT_CALIBRATION_INVALID"}.issubset(blocked.blocker_codes)


def test_vlm_geometry_and_incompatible_units_are_blocked() -> None:
    design = geometry("design", ((Decimal("0"), Decimal("0")),))
    actual = replace(
        geometry("as_built", ((Decimal("0"), Decimal("0")),)),
        confirmation_identity_kind="model",
        unit_code="m",
    )
    result = form_executive_scheme(
        design=design,
        as_built=actual,
        tolerance=Decimal("1.0"),
        tolerance_unit="mm",
        boundary_inclusive=True,
    )
    assert "AS_BUILT_AUTHORITY_INVALID" in result.blocker_codes
    assert "GEOMETRY_UNIT_MISMATCH" in result.blocker_codes


def test_geometry_tolerance_boundary_and_fingerprint_are_deterministic() -> None:
    design = geometry("design", ((Decimal("0"), Decimal("0")),))
    actual = geometry("as_built", ((Decimal("1.0"), Decimal("0")),))
    inclusive = form_executive_scheme(
        design=design,
        as_built=actual,
        tolerance=Decimal("1.0"),
        tolerance_unit="mm",
        boundary_inclusive=True,
    )
    exclusive = form_executive_scheme(
        design=design,
        as_built=actual,
        tolerance=Decimal("1.0"),
        tolerance_unit="mm",
        boundary_inclusive=False,
    )
    assert inclusive.tolerance_outcomes == ("within_tolerance",)
    assert exclusive.tolerance_outcomes == ("outside_tolerance",)
    assert inclusive.scheme_fingerprint != exclusive.scheme_fingerprint


def test_offline_duplicate_is_idempotent_and_conflict_quarantines() -> None:
    reconciler = OfflineFactReconciler()
    base = OfflineFactEnvelope(
        uid(60),
        "device:synthetic",
        "offline_manual_entry@1",
        datetime(2026, 8, 23, tzinfo=UTC),
        "device_clock_confirmed@1",
        "human:foreman",
        "sha256:" + "a" * 64,
        uid(61),
        uid(62),
        uid(63),
        unit_code="m3",
        precision_scale=3,
    )
    assert reconciler.reconcile(base).disposition is OfflineDisposition.ACCEPTED
    assert reconciler.reconcile(base).disposition is OfflineDisposition.DUPLICATE
    conflict = reconciler.reconcile(replace(base, fact_payload_digest="sha256:" + "b" * 64))
    assert conflict.disposition is OfflineDisposition.QUARANTINED
    assert len(conflict.conflict_fingerprints) == 2


def test_presented_volume_ks_and_payment_trace_is_deterministic() -> None:
    value = CommercialReadinessInput(
        quantity("10"),
        quantity("8"),
        True,
        True,
        True,
        quantity("8"),
        Decimal("125.00"),
        Decimal("1000.00"),
        "TST",
    )
    first = evaluate_commercial_readiness(value)
    second = evaluate_commercial_readiness(replace(value, payment_recorded=True))
    assert first.payment_ready
    assert first.fingerprint == second.fingerprint


def test_missing_id_or_excess_presented_volume_blocks_payment() -> None:
    result = evaluate_commercial_readiness(
        CommercialReadinessInput(
            quantity("10"),
            quantity("11"),
            False,
            True,
            True,
            quantity("11"),
            Decimal("1"),
            Decimal("11"),
            "TST",
        )
    )
    assert not result.payment_ready
    assert {"PRESENTED_VOLUME_EXCEEDS_CONFIRMED", "ID_PACKAGE_INCOMPLETE"}.issubset(
        result.blocker_codes
    )


def test_support_command_requires_exact_capability_and_rejection_has_no_event() -> None:
    machine = SupportProcessStateMachine()
    command = SupportCommand(
        uid(70),
        SupportCommandType.FINALIZE_SUPPORT_DELIVERABLE,
        uid(71),
        3,
        "support:finalize:1",
        uid(72),
        uid(73),
        {"deliverables": ["id-package:1"]},
        authority("support.deliverable.finalize", "human:finalizer"),
    )
    outcome = machine.execute(
        current_state=SupportState.READY_FOR_DELIVERABLE,
        current_revision=3,
        command=command,
        blockers=("ID_PACKAGE_INCOMPLETE",),
    )
    assert outcome.outcome == "rejected"
    assert outcome.event is None


def test_support_terminal_never_sets_product_ready() -> None:
    completed = SupportTerminalResult(
        "completed",
        uid(80),
        ("id-package:1",),
        (),
        ("PRODUCTION_PRINT_RENDER_BLOCKED",),
        "sha256:" + "c" * 64,
    )
    assert not completed.product_ready
    with pytest.raises(ValueError, match="ProductReady"):
        replace(completed, product_ready=True)


def test_at_pe_42_full_support_chain_is_deterministic_and_not_product_ready() -> None:
    readiness = evaluate_work_readiness(work_input())
    admission = evaluate_material_admission(material())
    control_result = evaluate_control(control())
    requirement = DocumentRequirementEvidence(
        uid(90),
        1,
        Applicability.APPLICABLE,
        "rule:synthetic-id@1",
        uid(91),
        uid(92),
        uid(93),
        "presentation",
        "pto",
    )
    completeness = evaluate_id_completeness(
        (requirement,),
        (DocumentCoverageEvidence(uid(90), 1, "covered", (uid(94),), True),),
    )
    generated = SyntheticOoxmlGenerationPipeline().generate(
        generation_request(
            "DOCX",
            (
                confirmed_field("work", "Synthetic work", 1),
                confirmed_field("volume", "10.000 m3", 2),
                confirmed_field("material", "Synthetic batch", 3),
            ),
        )
    )
    scheme = form_executive_scheme(
        design=geometry("design", ((Decimal("0"), Decimal("0")),)),
        as_built=geometry("as_built", ((Decimal("0.5"), Decimal("0")),)),
        tolerance=Decimal("1.0"),
        tolerance_unit="mm",
        boundary_inclusive=True,
    )
    commercial = evaluate_commercial_readiness(
        CommercialReadinessInput(
            quantity("10"),
            quantity("10"),
            True,
            True,
            True,
            quantity("10"),
            Decimal("100"),
            Decimal("1000"),
            "TST",
        )
    )
    trace = {
        "work": readiness.fingerprint,
        "material": admission.fingerprint,
        "control": control_result.fingerprint,
        "id_completeness": completeness.fingerprint,
        "generation": generated.semantic_fingerprint,
        "geometry": scheme.scheme_fingerprint,
        "commercial": commercial.fingerprint,
        "rule_set_version": "rules.synthetic@0.1.0",
    }
    assert readiness.outcome is WorkReadiness.READY
    assert admission.outcome is MaterialAdmission.ADMITTED
    assert control_result.outcome is ControlOutcome.PASSED
    assert completeness.complete
    assert scheme.outcome is GeometryOutcome.ELIGIBLE
    assert commercial.payment_ready
    assert digest_of(trace) == digest_of(dict(trace))
    assert (
        SupportTerminalResult(
            "completed",
            uid(96),
            ("id-package:synthetic@1", "payment-trace:synthetic@1"),
            (),
            ("PRODUCTION_PRINT_RENDER_BLOCKED",),
            "sha256:" + "d" * 64,
        ).product_ready
        is False
    )
