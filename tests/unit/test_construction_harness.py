from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from asd_kontur.construction_harness.assembly import (
    ConstructionAIContextGate,
    ConstructionHarnessContextAssembler,
    apply_customer_regulation_additions,
)
from asd_kontur.construction_harness.durability import (
    build_harness_backup_manifest,
    rebuild_projection_entries,
    verify_restored_harness,
)
from asd_kontur.construction_harness.evaluation import (
    evaluate_audit,
    evaluate_restoration,
    evaluate_support,
    evaluate_tender,
)
from asd_kontur.construction_harness.gateway import ConstructionHarnessQueryService
from asd_kontur.construction_harness.models import (
    ConstructionWorkPackage,
    CustomerRegulationAddition,
    DocumentAssessment,
    EstimateQuantity,
    HarnessError,
    HarnessErrorCode,
    HarnessMemorySnapshot,
    KnowledgeConsistencyDefect,
    MaterialRequirement,
    NormativeReferenceStatus,
    PresentedIDDocument,
    ProjectCharacteristicCandidate,
    ProjectDefinition,
    ProjectNormativeReference,
    Recoverability,
    RequiredEvidence,
    RequiredIDDocument,
    RequirementAuthority,
    SourceEvidence,
    VerifiedProjectCharacteristic,
    WorkControlRequirement,
    WorkPackageCandidate,
    WorkQuantity,
    WorkRequirementMatrix,
    WorkRequirementRow,
)
from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import (
    ExecutionBudget,
    ExecutionIdentity,
    ExecutionRequest,
    Locator,
    Route,
    Scope,
)
from asd_kontur.knowledge.gateway import (
    HARNESS_CONTRACT_VERSION,
    HARNESS_SCHEMA_ID,
    CompositeKnowledgeQueryService,
    GatewayContext,
    GatewayRequest,
    KnowledgeGateway,
)

ZERO = "sha256:" + "0" * 64
ORG = UUID("018ff001-0000-7000-8000-000000000001")
WORKSPACE = UUID("018ff001-0000-7000-8000-000000000002")
OTHER_WORKSPACE = UUID("018ff001-0000-7000-8000-000000000003")
SOURCE = UUID("018ff001-0000-7000-8000-000000000010")
NOW = datetime(2026, 8, 25, tzinfo=UTC)


class _Audit:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def record(self, **values: object) -> None:
        self.calls.append((str(values["tool"]), values["status"]))


def _id(value: str) -> UUID:
    return deterministic_uuid(f"test-construction-harness:{value}")


def _evidence(locator: str) -> SourceEvidence:
    return SourceEvidence(SOURCE, locator, ZERO, _id(f"evidence:{locator}"))


def _fixture() -> tuple[ProjectDefinition, WorkRequirementMatrix]:
    candidate = ProjectCharacteristicCandidate(
        _id("characteristic-candidate"),
        1,
        "object.purpose",
        "Линейно-площадочный объект",
        "pd-native-text-v1.0.0",
        _evidence("pdf:page=7;section=ПЗ"),
    )
    verified = VerifiedProjectCharacteristic.from_candidate(
        characteristic_id=_id("characteristic"),
        candidate=candidate,
        validation_profile_version="project-characteristic-v1.0.0",
        validation_receipt_digest=ZERO,
        deterministic_validation_passed=True,
    )
    work_specs = (
        ("earthworks", "Земляные работы", "120", "m3", (), "СП unresolved"),
        (
            "reinforced-concrete",
            "Железобетонная конструкция",
            "24",
            "m3",
            ("concrete", "rebar"),
            None,
        ),
        ("pipeline-installation", "Монтаж трубопровода", "80", "m", ("steel-pipe",), None),
    )
    packages: list[ConstructionWorkPackage] = []
    rows: list[WorkRequirementRow] = []
    previous: UUID | None = None
    for index, (key, title, quantity, unit, materials, ntd) in enumerate(work_specs, 1):
        package_id = _id(f"package:{key}")
        locator = f"pdf:page={10 + index};work={key}"
        references = (
            (
                ProjectNormativeReference(
                    _id(f"ntd:{key}"),
                    str(ntd),
                    str(ntd),
                    NormativeReferenceStatus.UNRESOLVED,
                    _evidence(locator),
                ),
            )
            if ntd
            else ()
        )
        package = ConstructionWorkPackage(
            package_id,
            1,
            WORKSPACE,
            key,
            "work-taxonomy-v1.0.0",
            title,
            (WorkQuantity(_id(f"quantity:{key}"), Decimal(quantity), unit, _evidence(locator)),),
            tuple(
                MaterialRequirement(
                    _id(f"material:{key}:{material}"),
                    material,
                    Decimal("1"),
                    "item",
                    _evidence(locator),
                )
                for material in materials
            ),
            references,
            (previous,) if previous else (),
            (_evidence(locator),),
        )
        document = RequiredIDDocument(
            _id(f"document:{key}"),
            f"ID-{key}",
            1,
            "form-v1.0.0",
            ("practice:verified",),
            RequirementAuthority.NORMATIVE_GAP,
        )
        rows.append(
            WorkRequirementRow(
                package_id,
                (WorkControlRequirement(_id(f"control:{key}"), "inspection", ("rule:active",)),),
                (
                    RequiredEvidence(
                        _id(f"required-evidence:{key}"), "source-record", (f"fact:{key}",)
                    ),
                ),
                (document,),
                ("official_ntd_subset_empty",) if ntd else (),
            )
        )
        packages.append(package)
        previous = package_id
    project = ProjectDefinition(
        _id("project"),
        1,
        ORG,
        WORKSPACE,
        "Строительство",
        "Линейно-площадочный объект",
        (verified,),
        tuple(packages),
        (SOURCE,),
        NOW,
    )
    matrix = WorkRequirementMatrix(
        _id("matrix"),
        1,
        ORG,
        WORKSPACE,
        project.project_definition_id,
        1,
        tuple(rows),
        (),
        None,
        NOW,
    )
    return project, matrix


def test_project_characteristic_candidate_requires_deterministic_validation() -> None:
    candidate = ProjectCharacteristicCandidate(
        _id("candidate-negative"), 1, "object.class", "candidate", "profile-v1", _evidence("p:1")
    )
    with pytest.raises(HarnessError) as raised:
        VerifiedProjectCharacteristic.from_candidate(
            characteristic_id=_id("verified-negative"),
            candidate=candidate,
            validation_profile_version="validator-v1",
            validation_receipt_digest=ZERO,
            deterministic_validation_passed=False,
        )
    assert raised.value.code is HarnessErrorCode.UNVERIFIED_CANDIDATE
    work_candidate = WorkPackageCandidate(
        _id("work-candidate"),
        1,
        WORKSPACE,
        "earthworks",
        "work-taxonomy-v1.0.0",
        "Земляные работы",
        (),
        (),
        (),
        (),
        "pd-native-text-v1.0.0",
        (_evidence("pd:work=earthworks"),),
    )
    with pytest.raises(HarnessError) as work_raised:
        ConstructionWorkPackage.from_candidate(
            work_package_id=_id("unverified-work"),
            candidate=work_candidate,
            deterministic_validation_passed=False,
        )
    assert work_raised.value.code is HarnessErrorCode.UNVERIFIED_CANDIDATE


def test_one_matrix_drives_all_four_modes_with_explicit_ntd_gap() -> None:
    project, matrix = _fixture()
    estimate = (
        EstimateQuantity(
            project.work_packages[0].work_package_id,
            "earthworks",
            Decimal("100"),
            "m3",
            (),
            _evidence("estimate:line=1"),
        ),
        EstimateQuantity(
            project.work_packages[1].work_package_id,
            "reinforced-concrete",
            Decimal("24"),
            "m3",
            ("concrete",),
            _evidence("estimate:line=2"),
        ),
        EstimateQuantity(
            project.work_packages[2].work_package_id,
            "pipeline-installation",
            Decimal("80"),
            "m",
            ("steel-pipe",),
            _evidence("estimate:line=3"),
        ),
    )
    tender = evaluate_tender(matrix=matrix, work_packages=project.work_packages, estimate=estimate)
    support = evaluate_support(matrix)
    presented = (
        PresentedIDDocument(
            _id("presented-earth"), "ID-earthworks", "form-v1.0.0", 1, True, True, ("e:1",)
        ),
        PresentedIDDocument(
            _id("presented-rc"), "ID-reinforced-concrete", "form-v1.0.0", 1, False, True, ("e:2",)
        ),
    )
    audit = evaluate_audit(matrix, presented)
    restoration = evaluate_restoration(matrix, frozenset({"fact:earthworks"}))
    assert {view.matrix_fingerprint for view in (tender, support, audit, restoration)} == {
        matrix.fingerprint
    }
    assert tender.quantity_deltas and tender.missing_materials
    assert tender.unresolved_ntd_references == ("СП unresolved",)
    assert not tender.normative_confirmed and tender.conclusion is not None
    assert len(support.document_requirement_ids) == 3 and support.presentation_blockers
    assert set(dict(audit.document_assessments).values()) >= {
        DocumentAssessment.PRESENT,
        DocumentAssessment.INCOMPLETE,
        DocumentAssessment.MISSING,
    }
    recovery = {item[1] for item in restoration.document_recoverability}
    assert recovery == {Recoverability.RECOVERABLE, Recoverability.NON_RECOVERABLE}
    assert restoration.fabrication_prohibited


def test_customer_regulation_is_additive_and_workspace_bound() -> None:
    _, matrix = _fixture()
    original = matrix.rows[0].documents[0]
    target = replace(
        original,
        basis_refs=("normative:synthetic-verified-provision",),
        authority_status=RequirementAuthority.NORMATIVE_VERIFIED,
    )
    matrix = replace(
        matrix,
        rows=(replace(matrix.rows[0], documents=(target,)), *matrix.rows[1:]),
    )
    addition = CustomerRegulationAddition(
        _id("addition"),
        1,
        ORG,
        WORKSPACE,
        target.document_requirement_id,
        2,
        ("customer-copy-log",),
        _evidence("regulation:p=2"),
    )
    overlaid = apply_customer_regulation_additions(matrix, (addition,))
    assert overlaid.rows[0].documents[0].minimum_copies == target.minimum_copies + 2
    assert overlaid.rows[0].documents[0].form_edition == target.form_edition
    with pytest.raises(HarnessError) as raised:
        apply_customer_regulation_additions(
            matrix, (replace(addition, workspace_id=OTHER_WORKSPACE),)
        )
    assert raised.value.code is HarnessErrorCode.SCOPE_VIOLATION
    with pytest.raises(HarnessError) as weakening:
        replace(addition, additional_copies=-1)
    assert weakening.value.code is HarnessErrorCode.REGULATORY_WEAKENING
    with pytest.raises(HarnessError) as unverified_basis:
        apply_customer_regulation_additions(
            replace(
                matrix,
                rows=(replace(matrix.rows[0], documents=(original,)), *matrix.rows[1:]),
            ),
            (addition,),
        )
    assert unverified_basis.value.code is HarnessErrorCode.REGULATORY_WEAKENING


def test_context_assembly_is_mandatory_separated_and_model_independent() -> None:
    project, matrix = _fixture()
    blocked_rule = _id("blocked-rule")
    defect = KnowledgeConsistencyDefect(
        _id("defect"), "rule_evidence_mismatch", "rule:blocked", ("e:1",), (blocked_rule,), NOW
    )
    memory = HarnessMemorySnapshot(
        ("practice-guide-edition:v1",),
        ("practice-unit:1:v1",),
        ("playbook:1:v1",),
        (),
        (),
        (str(blocked_rule), "rule:safe:v1"),
        ({"code": "official_ntd_subset_empty"},),
        (defect,),
    )
    pack = ConstructionHarnessContextAssembler().assemble(
        project=project, matrix=matrix, memory=memory
    )
    assert str(blocked_rule) not in pack.active_rule_version_refs
    assert pack.practice_intelligence_refs and pack.workspace_fact_refs
    assert pack.normative_provision_refs == () and pack.knowledge_gaps
    gate = ConstructionAIContextGate()
    with pytest.raises(HarnessError) as raised:
        gate.prepare(context_pack=None, model_profile_fingerprint="local-qwen")
    assert raised.value.code is HarnessErrorCode.CONTEXT_REQUIRED
    local = gate.prepare(context_pack=pack, model_profile_fingerprint="local-qwen")
    external = gate.prepare(context_pack=pack, model_profile_fingerprint="other-provider")
    assert local.context_pack_fingerprint == external.context_pack_fingerprint
    assert (
        local.evidence_pack["methodological_practice"] != local.evidence_pack["normative_authority"]
    )


def test_context_assembly_and_customer_overlay_are_semantically_deterministic() -> None:
    project, matrix = _fixture()
    memory = HarnessMemorySnapshot(
        ("practice-guide-edition:v1",),
        ("practice-unit:v1",),
        ("playbook:v1",),
        (),
        (),
        (),
        ({"code": "official_ntd_subset_empty"},),
    )
    assembler = ConstructionHarnessContextAssembler()
    first = assembler.assemble(project=project, matrix=matrix, memory=memory)
    second = assembler.assemble(project=project, matrix=matrix, memory=memory)
    assert first.context_pack_id == second.context_pack_id
    assert first.fingerprint == second.fingerprint
    assert first.assembled_at == second.assembled_at == matrix.created_at

    changed = assembler.assemble(
        project=project,
        matrix=matrix,
        memory=replace(memory, normative_edition_refs=("normative-edition:v1",)),
    )
    assert changed.context_pack_id != first.context_pack_id
    assert changed.fingerprint != first.fingerprint

    original = replace(
        matrix.rows[0].documents[0],
        authority_status=RequirementAuthority.NORMATIVE_VERIFIED,
    )
    normative_matrix = replace(
        matrix,
        rows=(replace(matrix.rows[0], documents=(original,)), *matrix.rows[1:]),
    )
    addition = CustomerRegulationAddition(
        _id("deterministic-addition"),
        1,
        ORG,
        WORKSPACE,
        original.document_requirement_id,
        1,
        (),
        _evidence("customer-regulation:p=2"),
    )
    overlaid_first = apply_customer_regulation_additions(normative_matrix, (addition,))
    overlaid_second = apply_customer_regulation_additions(normative_matrix, (addition,))
    assert overlaid_first.fingerprint == overlaid_second.fingerprint
    assert overlaid_first.created_at == overlaid_second.created_at == matrix.created_at


def test_provider_harness_rejects_construction_request_without_base_pack() -> None:
    identity = ExecutionIdentity(
        "local",
        "1.0.0",
        "qwen",
        "exact-revision",
        "mlx",
        "bf16",
        "runtime-v1",
        "profile-v1",
        "prompt-v1",
        "schema-v1",
        "preprocess-v1",
        "render-v1",
        "verify-v1",
    )
    budget = ExecutionBudget("test", "1.0.0", 1, 0, 5, 100, 1, 4096, 1, False, "0")
    with pytest.raises(ValueError, match="base ContextPack"):
        ExecutionRequest(
            _id("request"),
            _id("attempt"),
            Scope(ORG, WORKSPACE),
            SOURCE,
            ZERO,
            (Locator(SOURCE, _id("locator"), 1),),
            "construction.analysis",
            "1.0.0",
            "synthetic",
            Route.LOCAL_VLM,
            identity,
            "rules-v1",
            _id("authorization"),
            ("policy-v1",),
            budget,
            "key",
            _id("correlation-request"),
            _id("causation-request"),
        )


def test_common_gateway_exposes_harness_context_without_direct_sql() -> None:
    project, matrix = _fixture()
    pack = ConstructionHarnessContextAssembler().assemble(
        project=project,
        matrix=matrix,
        memory=HarnessMemorySnapshot((), ("practice:1",), (), (), (), (), ({"code": "ntd_gap"},)),
    )
    query = ConstructionHarnessQueryService({pack.context_pack_id: pack})
    gateway = KnowledgeGateway(
        CompositeKnowledgeQueryService({"knowledge.get_construction_harness_context": query}),
        _Audit(),
    )
    context = GatewayContext(
        "model:qwen",
        "knowledge.get_construction_harness_context.invoke",
        "construction.analysis",
        _id("correlation"),
        ORG,
        WORKSPACE,
    )
    response = gateway.invoke(
        GatewayRequest(
            "knowledge.get_construction_harness_context",
            HARNESS_CONTRACT_VERSION,
            HARNESS_SCHEMA_ID,
            HARNESS_CONTRACT_VERSION,
            {"context_pack_id": str(pack.context_pack_id)},
        ),
        context,
    )
    assert response.status.value == "knowledge_incomplete"
    assert response.result["authority_layers"]["workspace_facts"]
    with pytest.raises(HarnessError):
        query.execute(
            "knowledge.get_construction_harness_context",
            {"context_pack_id": str(pack.context_pack_id)},
            replace(context, workspace_id=OTHER_WORKSPACE),
        )


def test_backup_and_projection_rebuild_preserve_semantic_fingerprints() -> None:
    project, matrix = _fixture()
    pack = ConstructionHarnessContextAssembler().assemble(
        project=project,
        matrix=matrix,
        memory=HarnessMemorySnapshot((), ("practice:1",), (), (), (), (), ({"code": "ntd_gap"},)),
    )
    manifest = build_harness_backup_manifest(
        manifest_id=_id("backup"),
        project=project,
        matrix=matrix,
        context_pack=pack,
        platform_memory_fingerprints=("practice-memory-fingerprint", "ntd-memory-fingerprint"),
        projection_profile_version="harness-exact-v1.0.0",
        created_on=date(2026, 8, 25),
    )
    first = rebuild_projection_entries(matrix)
    second = rebuild_projection_entries(matrix)
    assert first == second and all(
        item["matrix_fingerprint"] == matrix.fingerprint for item in first
    )
    assert manifest.context_pack_fingerprint == pack.fingerprint
    assert manifest.semantic_fingerprint.startswith("sha256:")
    verify_restored_harness(
        manifest=manifest,
        project=project,
        matrix=matrix,
        context_pack=pack,
    )
    with pytest.raises(ValueError, match="semantic fingerprint mismatch"):
        verify_restored_harness(
            manifest=replace(manifest, matrix_fingerprint=ZERO),
            project=project,
            matrix=matrix,
            context_pack=pack,
        )
