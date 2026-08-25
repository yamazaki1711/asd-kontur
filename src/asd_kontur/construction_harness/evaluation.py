"""Four deterministic views over one WorkRequirementMatrix."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from asd_kontur.kernel.models import Mode

from .models import (
    AuditView,
    ConstructionWorkPackage,
    DocumentAssessment,
    EstimateQuantity,
    PresentedIDDocument,
    Recoverability,
    RestorationView,
    SupportView,
    TenderView,
    WorkRequirementMatrix,
)


def evaluate_tender(
    *,
    matrix: WorkRequirementMatrix,
    work_packages: tuple[ConstructionWorkPackage, ...],
    estimate: tuple[EstimateQuantity, ...],
) -> TenderView:
    estimate_by_work = {item.work_package_id: item for item in estimate}
    quantity_deltas: list[dict[str, str]] = []
    missing_materials: list[dict[str, str]] = []
    unresolved: list[str] = []
    for work in work_packages:
        estimate_item = estimate_by_work.get(work.work_package_id)
        if estimate_item is None:
            for quantity in work.quantities:
                quantity_deltas.append(
                    {
                        "work_package_id": str(work.work_package_id),
                        "project": str(quantity.value),
                        "estimate": "0",
                        "unit": quantity.unit_code,
                    }
                )
        else:
            project_total = sum((item.value for item in work.quantities), Decimal("0"))
            if project_total != estimate_item.value:
                quantity_deltas.append(
                    {
                        "work_package_id": str(work.work_package_id),
                        "project": str(project_total),
                        "estimate": str(estimate_item.value),
                        "unit": estimate_item.unit_code,
                    }
                )
            for material in work.materials:
                if material.material_key not in estimate_item.material_keys:
                    missing_materials.append(
                        {
                            "work_package_id": str(work.work_package_id),
                            "material_key": material.material_key,
                            "quantity": str(material.quantity),
                            "unit": material.unit_code,
                        }
                    )
        unresolved.extend(
            item.normalized_identifier
            for item in work.normative_references
            if item.status.value != "resolved"
        )
    has_deterministic_delta = bool(quantity_deltas or missing_materials)
    conclusion = None
    if has_deterministic_delta:
        conclusion = (
            "Обнаружены неучтённые объёмы работ или материалы; срок и сметная стоимость "
            "требуют дополнительного согласования по приложенной трассе доказательств."
        )
    return TenderView(
        Mode.TENDER,
        (matrix.matrix_id, matrix.version),
        matrix.fingerprint,
        tuple(quantity_deltas),
        tuple(missing_materials),
        tuple(dict.fromkeys(unresolved)),
        conclusion,
        not unresolved,
    )


def evaluate_support(matrix: WorkRequirementMatrix) -> SupportView:
    blockers = tuple(
        f"normative_gap:{row.work_package_id}:{gap}"
        for row in matrix.rows
        for gap in row.normative_gaps
    )
    return SupportView(
        Mode.SUPPORT,
        (matrix.matrix_id, matrix.version),
        matrix.fingerprint,
        tuple(item.control_requirement_id for row in matrix.rows for item in row.controls),
        tuple(item.evidence_requirement_id for row in matrix.rows for item in row.evidence),
        tuple(item.document_requirement_id for row in matrix.rows for item in row.documents),
        blockers,
    )


def evaluate_audit(
    matrix: WorkRequirementMatrix, presented: tuple[PresentedIDDocument, ...]
) -> AuditView:
    by_type: dict[str, list[PresentedIDDocument]] = {}
    for item in presented:
        by_type.setdefault(item.document_type, []).append(item)
    assessments: list[tuple[UUID, DocumentAssessment]] = []
    for row in matrix.rows:
        for expected in row.documents:
            actual = by_type.get(expected.document_type, [])
            if not actual:
                status = DocumentAssessment.MISSING
            elif len(actual) > 1:
                status = DocumentAssessment.DUPLICATE
            elif actual[0].form_edition != expected.form_edition:
                status = DocumentAssessment.WRONG_EDITION_OR_FORM
            elif not actual[0].valid:
                status = DocumentAssessment.INVALID
            elif not actual[0].complete or actual[0].copy_count < expected.minimum_copies:
                status = DocumentAssessment.INCOMPLETE
            elif not actual[0].evidence_refs:
                status = DocumentAssessment.EVIDENCE_GAP
            else:
                status = DocumentAssessment.PRESENT
            assessments.append((expected.document_requirement_id, status))
    return AuditView(
        Mode.AUDIT,
        (matrix.matrix_id, matrix.version),
        matrix.fingerprint,
        tuple(assessments),
    )


def evaluate_restoration(
    matrix: WorkRequirementMatrix, preserved_fact_keys: frozenset[str]
) -> RestorationView:
    results: list[tuple[UUID, Recoverability, tuple[str, ...]]] = []
    ordered: list[UUID] = []
    for row in matrix.rows:
        for document in row.documents:
            required_keys = {key for evidence in row.evidence for key in evidence.source_fact_keys}
            missing = tuple(sorted(required_keys - preserved_fact_keys))
            status = Recoverability.NON_RECOVERABLE if missing else Recoverability.RECOVERABLE
            results.append((document.document_requirement_id, status, missing))
            ordered.append(document.document_requirement_id)
    return RestorationView(
        Mode.RESTORATION,
        (matrix.matrix_id, matrix.version),
        matrix.fingerprint,
        tuple(results),
        tuple(ordered),
    )
