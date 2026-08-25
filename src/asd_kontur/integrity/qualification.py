"""An anonymized multi-work fixture executed identically by every integrity cycle."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from asd_kontur.construction_harness.assembly import ConstructionHarnessContextAssembler
from asd_kontur.construction_harness.evaluation import (
    evaluate_audit,
    evaluate_restoration,
    evaluate_support,
    evaluate_tender,
)
from asd_kontur.construction_harness.models import (
    ConstructionWorkPackage,
    DocumentAssessment,
    EstimateQuantity,
    HarnessMemorySnapshot,
    MaterialRequirement,
    NormativeReferenceStatus,
    PresentedIDDocument,
    ProjectDefinition,
    ProjectNormativeReference,
    RequiredEvidence,
    RequiredIDDocument,
    RequirementAuthority,
    SourceEvidence,
    WorkControlRequirement,
    WorkQuantity,
    WorkRequirementMatrix,
    WorkRequirementRow,
)
from asd_kontur.domain import deterministic_uuid

from .models import canonical_digest

ZERO = "sha256:" + "0" * 64
ORGANIZATION_ID = UUID("018ff001-0000-7000-8000-000000000001")
WORKSPACE_ID = UUID("018ff001-0000-7000-8000-000000000002")
SOURCE_VERSION_ID = UUID("018ff001-0000-7000-8000-000000000010")
FIXED_TIME = datetime(2026, 8, 25, tzinfo=UTC)


def _id(value: str) -> UUID:
    return deterministic_uuid(f"system-integrity-cycle:{value}")


def _evidence(locator: str) -> SourceEvidence:
    return SourceEvidence(
        SOURCE_VERSION_ID,
        locator,
        ZERO,
        _id(f"evidence:{locator}"),
    )


def build_fixture() -> tuple[ProjectDefinition, WorkRequirementMatrix]:
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
        (
            "pipeline-installation",
            "Монтаж трубопровода",
            "80",
            "m",
            ("steel-pipe",),
            None,
        ),
    )
    packages: list[ConstructionWorkPackage] = []
    rows: list[WorkRequirementRow] = []
    previous: UUID | None = None
    for index, (key, title, quantity, unit, materials, ntd) in enumerate(work_specs, 1):
        package_id = _id(f"package:{key}")
        locator = f"synthetic-pd:page={10 + index};work={key}"
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
            WORKSPACE_ID,
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
        rows.append(
            WorkRequirementRow(
                package_id,
                (
                    WorkControlRequirement(
                        _id(f"control:{key}"),
                        "inspection",
                        ("rule:synthetic-qualified",),
                    ),
                ),
                (
                    RequiredEvidence(
                        _id(f"required-evidence:{key}"),
                        "source-record",
                        (f"fact:{key}",),
                    ),
                ),
                (
                    RequiredIDDocument(
                        _id(f"document:{key}"),
                        f"ID-{key}",
                        1,
                        "form-v1.0.0",
                        ("practice:verified",),
                        RequirementAuthority.NORMATIVE_GAP,
                    ),
                ),
                ("official_ntd_subset_empty",) if ntd else (),
            )
        )
        packages.append(package)
        previous = package_id
    project = ProjectDefinition(
        _id("project"),
        1,
        ORGANIZATION_ID,
        WORKSPACE_ID,
        "Строительство",
        "Линейно-площадочный объект",
        (),
        tuple(packages),
        (SOURCE_VERSION_ID,),
        FIXED_TIME,
    )
    matrix = WorkRequirementMatrix(
        _id("matrix"),
        1,
        ORGANIZATION_ID,
        WORKSPACE_ID,
        project.project_definition_id,
        project.version,
        tuple(rows),
        (),
        None,
        FIXED_TIME,
    )
    return project, matrix


def execute_four_mode_fixture() -> dict[str, object]:
    project, matrix = build_fixture()
    estimate = (
        EstimateQuantity(
            project.work_packages[0].work_package_id,
            "earthworks",
            Decimal("100"),
            "m3",
            (),
            _evidence("synthetic-estimate:line=1"),
        ),
        EstimateQuantity(
            project.work_packages[1].work_package_id,
            "reinforced-concrete",
            Decimal("24"),
            "m3",
            ("concrete",),
            _evidence("synthetic-estimate:line=2"),
        ),
        EstimateQuantity(
            project.work_packages[2].work_package_id,
            "pipeline-installation",
            Decimal("80"),
            "m",
            ("steel-pipe",),
            _evidence("synthetic-estimate:line=3"),
        ),
    )
    tender = evaluate_tender(matrix=matrix, work_packages=project.work_packages, estimate=estimate)
    support = evaluate_support(matrix)
    audit = evaluate_audit(
        matrix,
        (
            PresentedIDDocument(
                _id("presented-earth"),
                "ID-earthworks",
                "form-v1.0.0",
                1,
                True,
                True,
                ("evidence:earthworks",),
            ),
            PresentedIDDocument(
                _id("presented-rc"),
                "ID-reinforced-concrete",
                "form-v1.0.0",
                1,
                False,
                True,
                ("evidence:rc",),
            ),
        ),
    )
    restoration = evaluate_restoration(matrix, frozenset({"fact:earthworks"}))
    context = ConstructionHarnessContextAssembler().assemble(
        project=project,
        matrix=matrix,
        memory=HarnessMemorySnapshot(
            ("practice-guide-edition:qualification:v1",),
            ("practice-unit:qualification:v1",),
            ("practice-playbook:qualification:v1",),
            (),
            (),
            ("rule-version:synthetic-qualified:v1",),
            ({"code": "official_ntd_subset_empty"},),
        ),
    )
    matrix_fingerprints = {
        tender.matrix_fingerprint,
        support.matrix_fingerprint,
        audit.matrix_fingerprint,
        restoration.matrix_fingerprint,
    }
    if matrix_fingerprints != {matrix.fingerprint}:
        raise ValueError("four modes did not use one WorkRequirementMatrix")
    mode_payload = {
        "Tender": {
            "quantity_deltas": tender.quantity_deltas,
            "missing_materials": tender.missing_materials,
            "unresolved_ntd_references": tender.unresolved_ntd_references,
            "conclusion": tender.conclusion,
            "normative_confirmed": tender.normative_confirmed,
        },
        "Support": {
            "controls": tuple(map(str, support.control_requirement_ids)),
            "evidence": tuple(map(str, support.evidence_requirement_ids)),
            "documents": tuple(map(str, support.document_requirement_ids)),
            "blockers": support.presentation_blockers,
        },
        "Audit": {
            "assessments": tuple(
                (str(identity), status.value) for identity, status in audit.document_assessments
            ),
            "required_states": sorted(
                {
                    DocumentAssessment.PRESENT.value,
                    DocumentAssessment.INCOMPLETE.value,
                    DocumentAssessment.MISSING.value,
                }
            ),
        },
        "Restoration": {
            "recoverability": tuple(
                (str(identity), status.value, missing)
                for identity, status, missing in restoration.document_recoverability
            ),
            "order": tuple(map(str, restoration.ordered_document_ids)),
            "fabrication_prohibited": restoration.fabrication_prohibited,
        },
    }
    return {
        "fixture_source_fingerprint": canonical_digest(
            {
                "project": project.fingerprint,
                "source_versions": tuple(map(str, project.source_version_ids)),
            }
        ),
        "project_fingerprint": project.fingerprint,
        "matrix_fingerprint": matrix.fingerprint,
        "four_mode_output_fingerprint": canonical_digest(mode_payload),
        "mode_output_fingerprints": {
            key: canonical_digest(value) for key, value in mode_payload.items()
        },
        "context_pack_fingerprint": context.fingerprint,
        "knowledge_gap_codes": tuple(sorted(str(item["code"]) for item in context.knowledge_gaps)),
        "automatic_rule_promotion": False,
    }
