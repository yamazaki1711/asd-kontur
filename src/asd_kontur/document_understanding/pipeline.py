"""Durable-job handlers for the source-first project-understanding pipeline."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import BinaryIO

from asd_kontur.application_spine.models import ClaimedJob, JobKind

from .models import (
    CLASSIFICATION_PROFILE_VERSION,
    NATIVE_LAYOUT_PROFILE_VERSION,
    OCR_ROUTING_PROFILE_VERSION,
    PAGE_HEALTH_PROFILE_VERSION,
    PROJECT_EXTRACTION_PROFILE_VERSION,
    UNDERSTANDING_PROFILE_VERSION,
    WORK_EXTRACTION_PROFILE_VERSION,
    OcrRoute,
    StructureNodeCandidate,
)
from .native import NativeExtractionFailure, inspect_and_extract
from .ocr import (
    OcrAdapter,
    OcrAdapterResult,
    OcrFailure,
    QwenVisionOcrAdapter,
    render_pdf_page,
    select_adapters,
)
from .postgres import IndustrialUnderstandingRepository
from .qwen_semantic import QwenDocumentSemanticAdapter, QwenSemanticFailure
from .semantic import (
    ClassificationBundle,
    StructuredCandidates,
    classify_pages,
    extract_structured_candidates,
)

MAX_BOUNDED_PROCESSING_BYTES = 256 * 1024 * 1024


class UnderstandingStageFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class IndustrialDocumentUnderstandingPipeline:
    """Executes one idempotent stage against exact document/source versions."""

    def __init__(
        self,
        repository: IndustrialUnderstandingRepository,
        *,
        qwen_vision: QwenVisionOcrAdapter,
        qwen_semantic: QwenDocumentSemanticAdapter | None = None,
    ) -> None:
        self._repository = repository
        self._qwen_vision = qwen_vision
        self._qwen_semantic = qwen_semantic

    def execute(self, claimed: ClaimedJob, source: BinaryIO) -> dict[str, object]:
        handlers = {
            JobKind.DOCUMENT_FORMAT_INVENTORY: self._native,
            JobKind.PDF_PAGE_HEALTH_ANALYSIS: self._page_health,
            JobKind.NATIVE_LAYOUT_EXTRACTION: self._native_layout,
            JobKind.OCR_ROUTING: self._ocr_routing,
            JobKind.OCR_EXTRACTION: self._ocr,
            JobKind.DOCUMENT_PAGE_CLASSIFICATION: self._classification,
            JobKind.DOCUMENT_AGGREGATION: self._aggregation,
            JobKind.PROJECT_DEFINITION_EXTRACTION: self._project_fields,
            JobKind.WORK_QUANTITY_MATERIAL_EXTRACTION: self._work_values,
            JobKind.WORK_PACKAGE_ASSEMBLY: self._assembly,
            JobKind.REQUIREMENT_MATRIX_ASSEMBLY: self._assembly,
            JobKind.PROJECT_UNDERSTANDING_RECONCILIATION: self._reconciliation,
        }
        handler = handlers.get(claimed.job_kind)
        if handler is None:
            raise UnderstandingStageFailure("understanding_stage_not_supported")
        result = handler(claimed, source)
        self._repository.record_stage_result(
            claimed,
            stage_kind=claimed.job_kind.value,
            profile_version=_profile_for(claimed.job_kind),
            output_manifest=result,
        )
        return result

    def _native(self, claimed: ClaimedJob, source: BinaryIO) -> dict[str, object]:
        document_id, document_version, source_version_id = self._repository.document_identity(
            claimed
        )
        document = inspect_and_extract(
            content=_read_bounded(source),
            media_type=str(claimed.input_manifest["media_type"]),
            document_id=document_id,
            document_version=document_version,
            source_version_id=source_version_id,
        )
        self._repository.persist_native_document(claimed, document)
        return {
            "format_kind": document.format_kind,
            "media_type": document.media_type,
            "page_count": len(document.pages),
            "parser_key": document.parser_key,
            "parser_version": document.parser_version,
            "capability_gaps": list(document.capability_gaps),
            "document_fingerprint": document.fingerprint,
        }

    def _page_health(self, claimed: ClaimedJob, _source: BinaryIO) -> dict[str, object]:
        routes = self._repository.load_ocr_routes(claimed)
        if not routes:
            raise UnderstandingStageFailure("page_health_unavailable")
        return {
            "page_count": len(routes),
            "ocr_routed_page_count": sum(
                route != OcrRoute.NOT_REQUIRED.value for _, route in routes
            ),
            "route_fingerprint": _digest(routes),
        }

    def _native_layout(self, claimed: ClaimedJob, _source: BinaryIO) -> dict[str, object]:
        elements = self._repository.load_elements(claimed)
        return {
            "element_count": len(elements),
            "evidence_fingerprint": _digest(
                tuple(item.locator.evidence_digest for item in elements)
            ),
        }

    def _ocr_routing(self, claimed: ClaimedJob, _source: BinaryIO) -> dict[str, object]:
        routes = self._repository.load_ocr_routes(claimed)
        if not routes:
            raise UnderstandingStageFailure("ocr_routing_input_unavailable")
        return {
            "routes": [{"page": page, "route": route} for page, route in routes],
            "primary_adapter": self._qwen_vision.adapter_key
            if self._qwen_vision.available()
            else None,
            "fallback_adapter": None,
        }

    def _ocr(self, claimed: ClaimedJob, source: BinaryIO) -> dict[str, object]:
        routes = self._repository.load_ocr_routes(claimed)
        routed = [
            (page, OcrRoute(route)) for page, route in routes if route != OcrRoute.NOT_REQUIRED
        ]
        if not routed:
            return {"routed_page_count": 0, "extracted_page_count": 0, "status": "not_required"}
        blocked = [page for page, route in routed if route is OcrRoute.BLOCKED]
        completed_pages = self._repository.load_completed_ocr_pages(
            claimed, adapter_key=self._qwen_vision.adapter_key
        )
        actionable = [
            (page, route)
            for page, route in routed
            if page not in blocked and page not in completed_pages
        ]
        if blocked and not actionable:
            raise UnderstandingStageFailure(
                "drawing_or_encrypted_content_requires_unavailable_capability"
            )
        content = _read_bounded(source)
        media_type = str(claimed.input_manifest["media_type"])
        extracted: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory(prefix="asd-ocr-") as directory:
            root = Path(directory)
            for page_number, route in actionable:
                image = root / f"page-{page_number}.png"
                if media_type == "application/pdf":
                    render_pdf_page(content, page_number, image)
                elif media_type.startswith("image/") and page_number == 1:
                    image.write_bytes(content)
                else:
                    raise UnderstandingStageFailure("ocr_source_format_unsupported")
                result = self._run_ocr_adapters(
                    select_adapters(route, qwen=self._qwen_vision),
                    image,
                    claimed,
                    page_number,
                )
                self._repository.persist_ocr_result(claimed, page_number=page_number, result=result)
                extracted.append(
                    {
                        "page": page_number,
                        "adapter": result.adapter_key,
                        "element_count": len(result.elements),
                        "output_digest": result.output_digest,
                    }
                )
        return {
            "routed_page_count": len(routed),
            "extracted_page_count": len(extracted),
            "already_complete_page_count": len(completed_pages),
            "blocked_pages": blocked,
            "results": extracted,
        }

    def _run_ocr_adapters(
        self,
        adapters: tuple[OcrAdapter, ...],
        image: Path,
        claimed: ClaimedJob,
        page_number: int,
    ) -> OcrAdapterResult:
        document_id, document_version, source_version_id = self._repository.document_identity(
            claimed
        )
        failures: list[str] = []
        for adapter in adapters:
            try:
                return adapter.extract(
                    image,
                    document_id=document_id,
                    document_version=document_version,
                    source_version_id=source_version_id,
                    page_number=page_number,
                )
            except OcrFailure as exc:
                failures.append(exc.code)
        raise UnderstandingStageFailure(
            "ocr_adapters_exhausted:" + ",".join(failures or ["none_available"])
        )

    def _classification(self, claimed: ClaimedJob, _source: BinaryIO) -> dict[str, object]:
        elements = self._repository.load_elements(claimed)
        if not elements:
            raise UnderstandingStageFailure("classification_evidence_unavailable")
        bundle = classify_pages(elements)
        qwen_candidate_count = 0
        if self._qwen_semantic is not None:
            try:
                semantic = self._qwen_semantic.classify(elements)
            except QwenSemanticFailure as exc:
                raise UnderstandingStageFailure(exc.code) from exc
            bundle = ClassificationBundle(
                candidates=(*bundle.candidates, *semantic.candidates),
                decisions=(*bundle.decisions, *semantic.decisions),
            )
            qwen_candidate_count = len(semantic.candidates)
        self._repository.persist_classification(claimed, bundle.candidates, bundle.decisions)
        return {
            "candidate_count": len(bundle.candidates),
            "decision_count": len(bundle.decisions),
            "qwen_semantic_candidate_count": qwen_candidate_count,
            "selected_roles": sorted(
                {role.value for decision in bundle.decisions for role in decision.selected_roles}
            ),
        }

    def _aggregation(self, claimed: ClaimedJob, _source: BinaryIO) -> dict[str, object]:
        decisions = self._repository.load_role_decisions(claimed)
        if not decisions:
            raise UnderstandingStageFailure("document_aggregation_input_unavailable")
        return {
            "page_decision_count": len(decisions),
            "multi_role_page_count": sum(len(item.selected_roles) > 1 for item in decisions),
            "role_fingerprint": _digest(
                tuple(
                    (item.scope, tuple(role.value for role in item.selected_roles))
                    for item in decisions
                )
            ),
        }

    def _project_fields(self, claimed: ClaimedJob, _source: BinaryIO) -> dict[str, object]:
        bundle = self._structured(claimed)
        structures: tuple[StructureNodeCandidate, ...] = ()
        if self._qwen_semantic is not None:
            try:
                semantic = self._qwen_semantic.extract_engineering(
                    self._repository.load_elements(claimed)
                )
            except QwenSemanticFailure as exc:
                raise UnderstandingStageFailure(exc.code) from exc
            bundle = StructuredCandidates(
                (*bundle.project_fields, *semantic.project_fields),
                semantic.works,
                semantic.quantities,
                semantic.materials,
                (),
                (),
                structures=(*structures, *semantic.structures),
            )
        self._repository.persist_structured(claimed, bundle)
        return {
            "project_field_candidate_count": len(bundle.project_fields),
            "structure_candidate_count": len(bundle.structures),
            "work_candidate_count": len(bundle.works),
            "quantity_candidate_count": len(bundle.quantities),
            "material_candidate_count": len(bundle.materials),
        }

    def _work_values(self, claimed: ClaimedJob, _source: BinaryIO) -> dict[str, object]:
        bundle = self._structured(claimed)
        values_only = StructuredCandidates(
            (), bundle.works, bundle.quantities, bundle.materials, bundle.estimates, bundle.defects
        )
        self._repository.persist_structured(claimed, values_only)
        return {
            "work_candidate_count": len(bundle.works),
            "quantity_candidate_count": len(bundle.quantities),
            "material_candidate_count": len(bundle.materials),
            "estimate_position_candidate_count": len(bundle.estimates),
            "reconciliation_defect_count": len(bundle.defects),
        }

    def _structured(self, claimed: ClaimedJob) -> StructuredCandidates:
        elements = self._repository.load_elements(claimed)
        decisions = self._repository.load_role_decisions(claimed)
        if not elements or not decisions:
            raise UnderstandingStageFailure("structured_extraction_evidence_unavailable")
        return extract_structured_candidates(elements, decisions)

    def _assembly(self, claimed: ClaimedJob, _source: BinaryIO) -> dict[str, object]:
        return self._repository.assemble_workspace(claimed)

    def _reconciliation(self, claimed: ClaimedJob, _source: BinaryIO) -> dict[str, object]:
        result = self._repository.assemble_workspace(claimed)
        if result["terminal_status"] == "complete":
            raise UnderstandingStageFailure("project_understanding_must_expose_authority_gaps")
        return result


def _read_bounded(source: BinaryIO) -> bytes:
    content = source.read(MAX_BOUNDED_PROCESSING_BYTES + 1)
    if len(content) > MAX_BOUNDED_PROCESSING_BYTES:
        raise UnderstandingStageFailure("bounded_processing_body_limit_exceeded")
    return content


def _digest(value: object) -> str:
    from asd_kontur.application_spine.models import semantic_digest

    return semantic_digest(value)


def _profile_for(kind: JobKind) -> str:
    return {
        JobKind.DOCUMENT_FORMAT_INVENTORY: NATIVE_LAYOUT_PROFILE_VERSION,
        JobKind.PDF_PAGE_HEALTH_ANALYSIS: PAGE_HEALTH_PROFILE_VERSION,
        JobKind.NATIVE_LAYOUT_EXTRACTION: NATIVE_LAYOUT_PROFILE_VERSION,
        JobKind.OCR_ROUTING: OCR_ROUTING_PROFILE_VERSION,
        JobKind.OCR_EXTRACTION: "qualified-local-ocr-v0.1",
        JobKind.DOCUMENT_PAGE_CLASSIFICATION: CLASSIFICATION_PROFILE_VERSION,
        JobKind.DOCUMENT_AGGREGATION: CLASSIFICATION_PROFILE_VERSION,
        JobKind.PROJECT_DEFINITION_EXTRACTION: PROJECT_EXTRACTION_PROFILE_VERSION,
        JobKind.WORK_QUANTITY_MATERIAL_EXTRACTION: WORK_EXTRACTION_PROFILE_VERSION,
        JobKind.WORK_PACKAGE_ASSEMBLY: UNDERSTANDING_PROFILE_VERSION,
        JobKind.REQUIREMENT_MATRIX_ASSEMBLY: UNDERSTANDING_PROFILE_VERSION,
        JobKind.PROJECT_UNDERSTANDING_RECONCILIATION: UNDERSTANDING_PROFILE_VERSION,
    }[kind]


def translate_stage_error(exc: BaseException) -> str:
    if isinstance(exc, (UnderstandingStageFailure, NativeExtractionFailure, OcrFailure)):
        return exc.code
    return "document_understanding_stage_failed"
