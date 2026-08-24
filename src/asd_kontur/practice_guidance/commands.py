"""Local development commands for non-published guide ingestion artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from pypdf import PdfReader

from asd_kontur.domain import deterministic_uuid, uuid7
from asd_kontur.harness.models import digest_of
from asd_kontur.knowledge import LocalFilesystemObjectStore
from asd_kontur.knowledge.gateway import (
    GUIDANCE_CONTRACT_VERSION,
    GUIDANCE_SCHEMA_ID,
    GatewayContext,
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
    KnowledgeGateway,
)
from asd_kontur.knowledge.postgres import PostgresKnowledgeAudit, PostgresKnowledgeQuery
from asd_kontur.knowledge.source_ledger import PlatformSourceAdmission, PlatformSourceLedger

from .manifest import inspect_pdf
from .memory_acceptance import (
    SEED_QUERIES,
    MemoryAcceptanceScenario,
    MemoryScenarioKind,
    absent_guidance_identity,
    adversarial_memory_job,
    evaluate_memory_response,
    positive_memory_job,
)
from .models import (
    CandidateTerminalStatus,
    CoverageManifest,
    GuidanceCandidateVersion,
    GuidanceCuratorAuthority,
    GuidanceGap,
    GuidanceKind,
    GuidanceVerification,
    GuideExecutionProfile,
    GuideLocator,
    GuidePageTerminalReceipt,
    GuideSourceRow,
    GuideTerminalState,
    GuideValidationFailure,
    NormativeReferenceCandidate,
    NormativeReferenceResolutionState,
    VerificationDisposition,
    reconcile_page_receipts,
)
from .native_layout import (
    NATIVE_LAYOUT_PROFILE_VERSION,
    classify_native_recovery,
    extract_native_page_layouts,
    locate_source_phrase,
    native_layout_to_wire,
    reconstruct_ntd_source_rows,
)
from .pipeline import (
    PassAFailedCandidate,
    PassBItemFailureCode,
    PassBPageEvaluationState,
    QwenJob,
    QwenRawReceipt,
    candidate_to_wire,
    compact_candidate_verifier_job,
    corrected_candidate_from_native_locator,
    corrected_candidate_from_region_recovery,
    evaluate_pass_a_items,
    evaluate_pass_b_batch_items,
    load_receipts,
    ntd_assertion_candidate,
    ntd_row_assertion,
    ntd_row_candidate_id,
    ntd_row_semantic_job,
    parse_compact_candidate_verification,
    parse_ntd_row_semantics,
    parse_pass_a,
    parse_pass_b,
    parse_pass_b_batch,
    parse_region_recovery,
    pass_a_job,
    pass_b_batch_job,
    printed_ntd_identity,
    raw_candidate_id,
    region_recovery_job,
    render_page,
    write_job_manifest,
)
from .postgres import PracticeGuideRepository
from .reconciliation import candidate_conflict_pairs, latest_candidate_versions
from .validation import (
    GuideFailureCode,
    GuideValidationContext,
    detect_duplicate_candidates,
    validate_candidate,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def inspect_command(pdf_path: Path, source_version_id: UUID, output: Path) -> None:
    inspection = inspect_pdf(pdf_path, source_version_id)
    _write_json(
        output,
        {
            "source_version_id": str(source_version_id),
            "content_digest": inspection.content_digest,
            "size_bytes": inspection.size_bytes,
            "media_type": inspection.media_type,
            "encrypted": inspection.encrypted,
            "page_count": inspection.page_count,
            "pages": [asdict(page) for page in inspection.pages],
        },
    )


def prepare_pass_a_command(
    *,
    pdf_path: Path,
    source_version_id: UUID,
    output: Path,
    render_root: Path,
    page_numbers: tuple[int, ...],
    dpi: int,
) -> None:
    reader = PdfReader(str(pdf_path), strict=True)
    total = len(reader.pages)
    if len(set(page_numbers)) != len(page_numbers):
        raise ValueError("Pass A page selection contains duplicates")
    if any(page < 1 or page > total for page in page_numbers):
        raise ValueError("Pass A page selection is outside the source")
    jobs = []
    for page_number in page_numbers:
        page = reader.pages[page_number - 1]
        native_text = page.extract_text() or ""
        image_path = render_page(
            pdf_path=pdf_path,
            page_number=page_number,
            render_root=render_root,
            dpi=dpi,
        )
        jobs.append(
            pass_a_job(
                source_version_id=source_version_id,
                page_number=page_number,
                native_text=native_text,
                image_path=image_path,
            )
        )
    write_job_manifest(output, tuple(jobs))


def _parse_pages(value: str) -> tuple[int, ...]:
    pages: list[int] = []
    for part in value.split(","):
        if "-" in part:
            first, last = (int(item) for item in part.split("-", 1))
            pages.extend(range(first, last + 1))
        else:
            pages.append(int(part))
    return tuple(pages)


def evaluate_pass_a_command(
    *,
    pdf_path: Path,
    source_version_id: UUID,
    receipt_paths: tuple[Path, ...],
    render_root: Path,
    evaluation_output: Path,
    pass_b_output: Path,
    profile_path: Path,
) -> None:
    profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(profile_data, dict):
        raise ValueError("Execution profile must be a JSON object")
    profile = GuideExecutionProfile(**profile_data)
    manifest = inspect_pdf(pdf_path, source_version_id)
    manifests = {page.page_number: page for page in manifest.pages}
    reader = PdfReader(str(pdf_path), strict=True)
    all_candidates: list[GuidanceCandidateVersion] = []
    evaluations: list[dict[str, object]] = []
    integrity_errors: list[dict[str, str]] = []
    pass_b_jobs: list[QwenJob] = []
    receipts_by_job = {
        receipt.job_id: receipt
        for receipt_path in receipt_paths
        for receipt in load_receipts(receipt_path)
    }
    for receipt in receipts_by_job.values():
        try:
            prefix = "pass-a-page-"
            if not receipt.job_id.startswith(prefix):
                raise ValueError("Pass A receipt contains an unexpected job identity")
            page_number = int(receipt.job_id.removeprefix(prefix))
            native_text = reader.pages[page_number - 1].extract_text() or ""
            image_path = render_page(
                pdf_path=pdf_path,
                page_number=page_number,
                render_root=render_root,
            )
            raw_document = json.loads(receipt.response)
            if not isinstance(raw_document, dict):
                raise ValueError("Pass A response must be an object")
            candidates = parse_pass_a(
                receipt.response,
                source_version_id=source_version_id,
                page_number=page_number,
                profile=profile,
            )
        except (IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            integrity_errors.append({"job_id": receipt.job_id, "error_code": type(error).__name__})
            continue
        failures: list[GuideValidationFailure] = []
        failure_codes_by_candidate: dict[str, tuple[str, ...]] = {}
        for candidate in candidates:
            candidate_failures = validate_candidate(
                candidate,
                GuideValidationContext(
                    source_version_id,
                    manifests[page_number],
                    native_text,
                    (page_number,),
                ),
            )
            failures.extend(candidate_failures)
            failure_codes_by_candidate[str(candidate.candidate_id)] = tuple(
                str(failure.failure_code) for failure in candidate_failures
            )
        all_candidates.extend(candidates)
        pass_b_jobs.append(
            pass_b_batch_job(
                source_version_id=source_version_id,
                page_number=page_number,
                native_text=native_text,
                image_path=image_path,
                candidate_payloads=tuple(candidate_to_wire(candidate) for candidate in candidates),
                validation_failure_codes=failure_codes_by_candidate,
                no_methodological_content=raw_document.get("no_methodological_content") is True,
            )
        )
        evaluations.append(
            {
                "page_number": page_number,
                "attempt_ref": receipt.attempt_id
                or f"legacy:{receipt.job_id}:{receipt.request_digest}",
                "attempt_number": receipt.attempt_number,
                "request_digest": receipt.request_digest,
                "response_digest": receipt.response_digest,
                "no_methodological_content": raw_document.get("no_methodological_content"),
                "candidates": [asdict(candidate) for candidate in candidates],
                "validation_failures": [asdict(failure) for failure in failures],
            }
        )
    duplicate_failures = detect_duplicate_candidates(tuple(all_candidates))
    _write_json(
        evaluation_output,
        {
            "source_version_id": str(source_version_id),
            "profile_fingerprint": profile.fingerprint,
            "pages": evaluations,
            "duplicate_failures": [asdict(failure) for failure in duplicate_failures],
            "expected_receipts": len(receipts_by_job),
            "valid_receipts": len(evaluations),
            "integrity_errors": integrity_errors,
        },
    )
    write_job_manifest(pass_b_output, tuple(pass_b_jobs))


def _candidate_from_document(value: dict[str, object]) -> GuidanceCandidateVersion:
    def string_tuple(field: str) -> tuple[str, ...]:
        raw = value[field]
        if not isinstance(raw, list):
            raise ValueError(f"{field} must be an array")
        return tuple(str(item) for item in raw)

    def region_tuple(raw: object, field: str) -> tuple[float, float, float, float]:
        if not isinstance(raw, list) or len(raw) != 4:
            raise ValueError(f"{field} must contain four coordinates")
        return float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])

    def integer(field: str) -> int:
        raw = value[field]
        if not isinstance(raw, int):
            raise ValueError(f"{field} must be an integer")
        return raw

    locator_value = value["locator"]
    if not isinstance(locator_value, dict):
        raise ValueError("Candidate locator is malformed")
    region = locator_value["region"]
    if not isinstance(region, list) or len(region) != 4:
        raise ValueError("Candidate locator region is malformed")
    visual_value = value.get("visual_example_locator")
    visual_locator = None
    if visual_value is not None:
        if not isinstance(visual_value, dict):
            raise ValueError("Visual locator is malformed")
        visual_region = visual_value["region"]
        if not isinstance(visual_region, list) or len(visual_region) != 4:
            raise ValueError("Visual locator region is malformed")
        visual_page = visual_value["page_number"]
        if not isinstance(visual_page, int):
            raise ValueError("Visual locator page must be an integer")
        visual_locator = GuideLocator(visual_page, region_tuple(visual_region, "visual region"))
    return GuidanceCandidateVersion(
        candidate_id=UUID(str(value["candidate_id"])),
        version=integer("version"),
        source_version_id=UUID(str(value["source_version_id"])),
        locator=GuideLocator(
            int(str(locator_value["page_number"])), region_tuple(region, "locator region")
        ),
        kind=GuidanceKind(str(value["kind"])),
        section=str(value["section"]),
        topic=str(value["topic"]),
        document_or_form_type=(
            str(value["document_or_form_type"])
            if value.get("document_or_form_type") is not None
            else None
        ),
        workflow_stage=(
            str(value["workflow_stage"]) if value.get("workflow_stage") is not None else None
        ),
        field_or_element=(
            str(value["field_or_element"]) if value.get("field_or_element") is not None else None
        ),
        instruction=str(value["instruction"]),
        required_inputs=string_tuple("required_inputs"),
        evidence_requirements=string_tuple("evidence_requirements"),
        author_role_claims=string_tuple("author_role_claims"),
        common_error=str(value["common_error"]) if value.get("common_error") is not None else None,
        recommended_practice=(
            str(value["recommended_practice"])
            if value.get("recommended_practice") is not None
            else None
        ),
        visual_example_locator=visual_locator,
        applicability_conditions=string_tuple("applicability_conditions"),
        limitations=string_tuple("limitations"),
        uncertainties=string_tuple("uncertainties"),
        model_profile_fingerprint=str(value["model_profile_fingerprint"]),
        parent_version=(int(str(value["parent_version"])) if value.get("parent_version") else None),
    )


def _corrected_candidate_version(
    original: GuidanceCandidateVersion,
    value: dict[str, object],
) -> GuidanceCandidateVersion:
    candidate_id = UUID(str(value.get("candidate_id")))
    if candidate_id != original.candidate_id:
        raise ValueError("Corrected CandidateVersion cannot change candidate identity")
    corrected_wire = {
        **value,
        "candidate_id": str(original.candidate_id),
        "version": original.version + 1,
        "source_version_id": str(original.source_version_id),
        "locator": {
            "page_number": original.locator.page_number,
            "region": value.get("region"),
        },
        "visual_example_locator": (
            {
                "page_number": original.locator.page_number,
                "region": value.get("visual_example_region"),
            }
            if value.get("visual_example_region") is not None
            else None
        ),
        "model_profile_fingerprint": original.model_profile_fingerprint,
        "parent_version": original.version,
    }
    return _candidate_from_document(corrected_wire)


def _failed_candidate_from_document(value: dict[str, object]) -> PassAFailedCandidate:
    raw_candidate = value.get("raw_candidate")
    if not isinstance(raw_candidate, dict):
        raise ValueError("Failed candidate raw payload must be an object")
    return PassAFailedCandidate(
        candidate_id=UUID(str(value["candidate_id"])),
        candidate_version=int(str(value["candidate_version"])),
        page_number=int(str(value["page_number"])),
        ordinal=int(str(value["ordinal"])),
        failure_code=str(value["failure_code"]),
        failure_field=str(value["failure_field"]),
        invalid_region=value.get("invalid_region"),
        raw_candidate=raw_candidate,
    )


def _profile_from_path(path: Path) -> GuideExecutionProfile:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Execution profile must be a JSON object")
    return GuideExecutionProfile(**value)


def _source_row_from_document(value: dict[str, object]) -> GuideSourceRow:
    locator_value = value.get("locator")
    if not isinstance(locator_value, dict):
        raise ValueError("Guide source row locator is malformed")
    region = locator_value.get("region")
    if not isinstance(region, list) or len(region) != 4:
        raise ValueError("Guide source row region is malformed")
    region_tuple = (float(region[0]), float(region[1]), float(region[2]), float(region[3]))
    return GuideSourceRow(
        source_row_id=UUID(str(value["source_row_id"])),
        parent_candidate_id=UUID(str(value["parent_candidate_id"])),
        parent_candidate_version=int(str(value["parent_candidate_version"])),
        source_version_id=UUID(str(value["source_version_id"])),
        page_number=int(str(value["page_number"])),
        row_ordinal=int(str(value["row_ordinal"])),
        locator=GuideLocator(int(str(locator_value["page_number"])), region_tuple),
        printed_ntd=str(value["printed_ntd"]),
        work_or_rd_sections=str(value["work_or_rd_sections"]),
        id_note=str(value["id_note"]),
        layout_profile_version=str(value["layout_profile_version"]),
        extraction_digest=str(value["extraction_digest"]),
        parent_failed_receipt_digest=str(value["parent_failed_receipt_digest"]),
    )


def prepare_native_first_recovery_command(
    *,
    pdf_path: Path,
    source_version_id: UUID,
    failed_manifest_path: Path,
    receipt_paths: tuple[Path, ...],
    profile_path: Path,
    render_root: Path,
    layout_output: Path,
    classification_output: Path,
    source_rows_output: Path,
    semantic_jobs_output: Path,
    native_registry_output: Path,
    native_pass_b_output: Path,
    lineage_output: Path,
) -> None:
    selected_pages = (16, 17, 111, 269, 380, 394)
    table_pages = {16, 17}
    continuation_context_page = 15
    profile = _profile_from_path(profile_path)
    failed_manifest = json.loads(failed_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(failed_manifest, dict):
        raise ValueError("Failed-candidate manifest must be an object")
    failed_values = failed_manifest.get("failed_candidates")
    if not isinstance(failed_values, list):
        raise ValueError("Failed-candidate manifest has no failed candidates")
    failed_candidates = tuple(
        _failed_candidate_from_document(value) for value in failed_values if isinstance(value, dict)
    )
    by_page: dict[int, list[PassAFailedCandidate]] = {page: [] for page in selected_pages}
    for failed in failed_candidates:
        if failed.page_number in by_page:
            by_page[failed.page_number].append(failed)

    receipts: dict[str, QwenRawReceipt] = {}
    selected_job_ids = {f"pass-a-page-{page:04d}" for page in selected_pages}
    for receipt_path in receipt_paths:
        for receipt in load_receipts(receipt_path):
            if receipt.job_id in selected_job_ids:
                if receipt.job_id in receipts:
                    raise ValueError("Native recovery received duplicate failed page receipts")
                receipts[receipt.job_id] = receipt
    if set(receipts) != selected_job_ids:
        raise ValueError("Native recovery is missing a failed page receipt")

    manifest = inspect_pdf(pdf_path, source_version_id)
    page_manifests = {page.page_number: page for page in manifest.pages}
    reader = PdfReader(str(pdf_path), strict=True)
    layouts = {
        page: extract_native_page_layouts(pdf_path, first_page=page, last_page=page)[0]
        for page in (continuation_context_page, *selected_pages)
    }
    continuation_text = layouts[continuation_context_page].native_text
    continuation_markers = (
        "Нормативно-техническая база для оформления ИД",
        "Наименование НТД",
        "Виды работ или разделы РД",
        "Примечание",
    )
    if any(marker not in continuation_text for marker in continuation_markers):
        raise ValueError("Previous-page NTD table continuation context is incomplete")
    classifications = {page: classify_native_recovery(layouts[page]) for page in selected_pages}
    if any(
        classifications[page].recovery_route != "deterministic_native_locator"
        for page in selected_pages
    ):
        raise ValueError("At least one selected page requires a non-native recovery route")

    receipt_lineage = {
        page: {
            "job_id": receipts[f"pass-a-page-{page:04d}"].job_id,
            "attempt_id": receipts[f"pass-a-page-{page:04d}"].attempt_id,
            "request_digest": receipts[f"pass-a-page-{page:04d}"].request_digest,
            "response_digest": receipts[f"pass-a-page-{page:04d}"].response_digest,
            "receipt_digest": digest_of(asdict(receipts[f"pass-a-page-{page:04d}"])),
        }
        for page in selected_pages
    }
    table_parent_candidates: dict[int, dict[int, UUID]] = {}
    for page in sorted(table_pages):
        raw_page = json.loads(receipts[f"pass-a-page-{page:04d}"].response)
        raw_values = raw_page.get("candidates") if isinstance(raw_page, dict) else None
        if not isinstance(raw_values, list):
            raise ValueError("Continued-table failed receipt has no candidate array")
        ordinal_map: dict[int, UUID] = {}
        for ordinal, raw_value in enumerate(raw_values, start=1):
            if not isinstance(raw_value, dict):
                raise ValueError("Continued-table failed candidate is not an object")
            ordinal_map[ordinal] = raw_candidate_id(
                raw_value,
                source_version_id=source_version_id,
                page_number=page,
                ordinal=ordinal,
            )
        table_parent_candidates[page] = ordinal_map
    source_rows = tuple(
        row
        for page in sorted(table_pages)
        for row in reconstruct_ntd_source_rows(
            source_version_id=source_version_id,
            layout=layouts[page],
            parent_failed_receipt_digest=str(receipt_lineage[page]["receipt_digest"]),
            parent_candidates_by_ordinal=table_parent_candidates[page],
        )
    )
    semantic_jobs = tuple(ntd_row_semantic_job(row) for row in source_rows)

    native_candidates: list[GuidanceCandidateVersion] = []
    native_entries: list[dict[str, object]] = []
    native_pass_b_jobs: list[QwenJob] = []
    for page in selected_pages:
        if page in table_pages:
            continue
        native_text = reader.pages[page - 1].extract_text() or ""
        image_path = render_page(pdf_path=pdf_path, page_number=page, render_root=render_root)
        for failed in by_page[page]:
            locator = locate_source_phrase(layouts[page], str(failed.raw_candidate["instruction"]))
            corrected = corrected_candidate_from_native_locator(
                failed,
                locator=locator,
                source_version_id=source_version_id,
                profile=profile,
            )
            failures = validate_candidate(
                corrected,
                GuideValidationContext(
                    source_version_id, page_manifests[page], native_text, (page,)
                ),
            )
            native_candidates.append(corrected)
            native_entries.append(
                {
                    "candidate": asdict(corrected),
                    "parent_failed_candidate": asdict(failed),
                    "parent_failed_receipt": receipt_lineage[page],
                    "native_layout_digest": layouts[page].extraction_digest,
                    "locator_derivation": "deterministic_longest_contiguous_token_alignment",
                    "validation_failures": [asdict(failure) for failure in failures],
                }
            )
            native_pass_b_jobs.append(
                compact_candidate_verifier_job(
                    source_version_id=source_version_id,
                    native_text=native_text,
                    image_path=image_path,
                    candidate=corrected,
                    purpose="pass_a_salvage",
                    validation_failure_codes=tuple(
                        str(failure.failure_code) for failure in failures
                    ),
                )
            )

    _write_json(
        layout_output,
        {
            "profile_version": NATIVE_LAYOUT_PROFILE_VERSION,
            "source_version_id": str(source_version_id),
            "pages": [
                native_layout_to_wire(layouts[page])
                for page in (continuation_context_page, *selected_pages)
            ],
            "table_continuation": {
                "context_page": continuation_context_page,
                "recovered_pages": sorted(table_pages),
                "context_only": True,
                "separate_document": False,
                "markers": list(continuation_markers),
            },
        },
    )
    _write_json(
        classification_output,
        {
            "source_version_id": str(source_version_id),
            "pages": [asdict(classifications[page]) for page in selected_pages],
            "targeted_vlm_pages": [],
            "deterministic_native_pages": list(selected_pages),
        },
    )
    _write_json(
        source_rows_output,
        {
            "source_version_id": str(source_version_id),
            "row_count": len(source_rows),
            "pages": list(sorted(table_pages)),
            "rows": [asdict(row) for row in source_rows],
        },
    )
    write_job_manifest(semantic_jobs_output, semantic_jobs)
    _write_json(
        native_registry_output,
        {
            "source_version_id": str(source_version_id),
            "profile_fingerprint": profile.fingerprint,
            "candidate_count": len(native_candidates),
            "entries": native_entries,
        },
    )
    write_job_manifest(native_pass_b_output, tuple(native_pass_b_jobs))
    _write_json(
        lineage_output,
        {
            "recovery_profile": "guide_native_first_recovery_v0.1",
            "source_version_id": str(source_version_id),
            "supersedes_recovery_profile_for_pages": {
                "pages": [16, 17],
                "profile": "guide_region_candidate_recovery_v0.1",
                "reason_code": "OWNER_CONFIRMED_VECTOR_CONTINUED_TABLE",
            },
            "page_receipts": receipt_lineage,
            "source_row_ids": [str(row.source_row_id) for row in source_rows],
            "source_row_parent_candidate_versions": [
                {
                    "source_row_id": str(row.source_row_id),
                    "candidate_id": str(row.parent_candidate_id),
                    "candidate_version": row.parent_candidate_version,
                }
                for row in source_rows
            ],
            "native_corrected_candidate_ids": [
                str(candidate.candidate_id) for candidate in native_candidates
            ],
            "targeted_vlm_pages": [],
            "table_continuation": {
                "context_page": continuation_context_page,
                "recovered_pages": sorted(table_pages),
                "separate_document": False,
                "reason_code": "CONTINUED_TABLE_FROM_PREVIOUS_PAGE",
            },
        },
    )


def evaluate_ntd_row_semantics_command(
    *,
    pdf_path: Path,
    source_version_id: UUID,
    source_rows_path: Path,
    receipt_paths: tuple[Path, ...],
    profile_path: Path,
    render_root: Path,
    evaluation_output: Path,
    registry_output: Path,
    pass_b_output: Path,
) -> None:
    profile = _profile_from_path(profile_path)
    source_document = json.loads(source_rows_path.read_text(encoding="utf-8"))
    if not isinstance(source_document, dict) or not isinstance(source_document.get("rows"), list):
        raise ValueError("Source-row manifest is malformed")
    rows = tuple(
        _source_row_from_document(value)
        for value in source_document["rows"]
        if isinstance(value, dict)
    )
    expected_jobs = {
        f"ntd-row-semantic-page-{row.page_number:04d}-{row.source_row_id}": row for row in rows
    }
    receipts: dict[str, QwenRawReceipt] = {}
    for receipt_path in receipt_paths:
        for receipt in load_receipts(receipt_path):
            if receipt.job_id not in expected_jobs:
                raise ValueError("NTD row semantic receipts contain an unknown identity")
            if receipt.job_id in receipts:
                raise ValueError("NTD row semantic receipts contain a duplicate identity")
            receipts[receipt.job_id] = receipt

    inspection = inspect_pdf(pdf_path, source_version_id)
    page_manifests = {page.page_number: page for page in inspection.pages}
    reader = PdfReader(str(pdf_path), strict=True)
    results: list[dict[str, object]] = []
    registry_entries: list[dict[str, object]] = []
    pass_b_jobs: list[QwenJob] = []
    for job_id, row in expected_jobs.items():
        source_receipt = receipts.get(job_id)
        if source_receipt is None or source_receipt.state != "completed":
            results.append(
                {
                    "source_row_id": str(row.source_row_id),
                    "candidate_id": str(ntd_row_candidate_id(row)),
                    "state": "model_failed",
                    "failure_code": "NTD_ROW_SEMANTIC_RECEIPT_MISSING_OR_FAILED",
                    "parent_source_row_fingerprint": row.fingerprint,
                }
            )
            continue
        try:
            semantics = parse_ntd_row_semantics(source_receipt.response, row=row)
            printed_identifier, printed_title = printed_ntd_identity(row.printed_ntd)
            reference = NormativeReferenceCandidate(
                reference_candidate_id=deterministic_uuid(
                    f"guide-ntd-reference:{row.source_row_id}:{printed_identifier}"
                ),
                printed_identifier=printed_identifier,
                printed_title=printed_title,
                resolution_state=NormativeReferenceResolutionState.NOT_ATTEMPTED,
                uncertainty_code="NTD_EDITION_RESOLUTION_PENDING",
            )
            assertion = ntd_row_assertion(
                row=row,
                semantics=semantics,
                normative_reference=reference,
                model_profile_fingerprint=profile.fingerprint,
            )
            candidate = ntd_assertion_candidate(assertion)
            native_text = reader.pages[row.page_number - 1].extract_text() or ""
            failures = validate_candidate(
                candidate,
                GuideValidationContext(
                    source_version_id,
                    page_manifests[row.page_number],
                    native_text,
                    (row.page_number,),
                ),
            )
            image_path = render_page(
                pdf_path=pdf_path,
                page_number=row.page_number,
                render_root=render_root,
            )
            pass_b_jobs.append(
                compact_candidate_verifier_job(
                    source_version_id=source_version_id,
                    native_text=native_text,
                    image_path=image_path,
                    candidate=candidate,
                    purpose="pass_a_salvage",
                    validation_failure_codes=tuple(
                        str(failure.failure_code) for failure in failures
                    ),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            results.append(
                {
                    "source_row_id": str(row.source_row_id),
                    "candidate_id": str(ntd_row_candidate_id(row)),
                    "state": "model_failed",
                    "failure_code": "NTD_ROW_SEMANTIC_ITEM_INVALID",
                    "failure_type": type(error).__name__,
                    "response_digest": source_receipt.response_digest,
                    "parent_source_row_fingerprint": row.fingerprint,
                }
            )
            continue
        entry: dict[str, object] = {
            "source_row": asdict(row),
            "assertion": asdict(assertion),
            "candidate": asdict(candidate),
            "validation_failures": [asdict(failure) for failure in failures],
            "semantic_receipt": {
                "attempt_id": source_receipt.attempt_id,
                "request_digest": source_receipt.request_digest,
                "response_digest": source_receipt.response_digest,
            },
        }
        registry_entries.append(entry)
        results.append(
            {
                "source_row_id": str(row.source_row_id),
                "candidate_id": str(candidate.candidate_id),
                "state": "complete",
                "assertion_fingerprint": assertion.fingerprint,
                "candidate_fingerprint": candidate.fingerprint,
                "validation_failure_count": len(failures),
                "response_digest": source_receipt.response_digest,
            }
        )

    _write_json(
        evaluation_output,
        {
            "profile": "guide_ntd_row_semantic_v0.1",
            "source_version_id": str(source_version_id),
            "expected_rows": len(rows),
            "valid_rows": len(registry_entries),
            "failed_rows": len(rows) - len(registry_entries),
            "results": results,
        },
    )
    _write_json(
        registry_output,
        {
            "source_version_id": str(source_version_id),
            "profile_fingerprint": profile.fingerprint,
            "candidate_count": len(registry_entries),
            "entries": registry_entries,
        },
    )
    if not pass_b_jobs:
        raise ValueError("No valid NTD row candidates are available for targeted Pass B")
    write_job_manifest(pass_b_output, tuple(pass_b_jobs))


def prepare_candidate_recovery_command(
    *,
    pdf_path: Path,
    source_version_id: UUID,
    receipt_paths: tuple[Path, ...],
    page_numbers: tuple[int, ...],
    qualification_pages: tuple[int, ...],
    render_root: Path,
    profile_path: Path,
    salvage_output: Path,
    qualification_output: Path,
    remaining_output: Path,
    salvage_verifier_output: Path,
    lineage_output: Path,
) -> None:
    if not page_numbers or len(set(page_numbers)) != len(page_numbers):
        raise ValueError("Pass A recovery pages must be a non-empty unique selection")
    if not set(qualification_pages).issubset(page_numbers):
        raise ValueError("Recovery qualification pages must be selected Pass A pages")
    profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(profile_data, dict):
        raise ValueError("Execution profile must be a JSON object")
    profile = GuideExecutionProfile(**profile_data)
    manifest = inspect_pdf(pdf_path, source_version_id)
    manifests = {page.page_number: page for page in manifest.pages}
    reader = PdfReader(str(pdf_path), strict=True)
    selected_job_ids = {f"pass-a-page-{page_number:04d}" for page_number in page_numbers}
    receipts: dict[str, QwenRawReceipt] = {}
    for receipt_path in receipt_paths:
        for receipt in load_receipts(receipt_path):
            if receipt.job_id not in selected_job_ids:
                continue
            if receipt.job_id in receipts:
                raise ValueError("Pass A recovery has duplicate receipt identities")
            receipts[receipt.job_id] = receipt
    if set(receipts) != selected_job_ids:
        raise ValueError("Pass A recovery is missing selected source receipts")

    accepted_documents: list[dict[str, object]] = []
    failed_documents: list[dict[str, object]] = []
    lineage: list[dict[str, object]] = []
    qualification_jobs: list[QwenJob] = []
    remaining_jobs: list[QwenJob] = []
    salvage_verifier_jobs: list[QwenJob] = []
    qualification_selected_pages: set[int] = set()
    for page_number in page_numbers:
        job_id = f"pass-a-page-{page_number:04d}"
        receipt = receipts[job_id]
        if receipt.state != "completed":
            raise ValueError("Pass A recovery source receipt is not completed")
        native_text = reader.pages[page_number - 1].extract_text() or ""
        image_path = render_page(
            pdf_path=pdf_path,
            page_number=page_number,
            render_root=render_root,
        )
        accepted, failed = evaluate_pass_a_items(
            receipt.response,
            source_version_id=source_version_id,
            page_number=page_number,
            profile=profile,
        )
        for candidate in accepted:
            candidate_failures = validate_candidate(
                candidate,
                GuideValidationContext(
                    source_version_id,
                    manifests[page_number],
                    native_text,
                    (page_number,),
                ),
            )
            salvage_job = compact_candidate_verifier_job(
                source_version_id=source_version_id,
                native_text=native_text,
                image_path=image_path,
                candidate=candidate,
                purpose="pass_a_salvage",
                validation_failure_codes=tuple(
                    str(failure.failure_code) for failure in candidate_failures
                ),
            )
            accepted_documents.append(
                {
                    "job_id": salvage_job.job_id,
                    "purpose": "pass_a_salvage",
                    "candidate": asdict(candidate),
                    "validation_failures": [asdict(failure) for failure in candidate_failures],
                    "source_receipt": {
                        "job_id": receipt.job_id,
                        "attempt_ref": receipt.attempt_id
                        or f"legacy:{receipt.job_id}:{receipt.request_digest}",
                        "response_digest": receipt.response_digest,
                    },
                }
            )
            salvage_verifier_jobs.append(salvage_job)
        for failed_candidate in failed:
            failed_document = {
                **asdict(failed_candidate),
                "source_receipt": {
                    "job_id": receipt.job_id,
                    "attempt_ref": receipt.attempt_id
                    or f"legacy:{receipt.job_id}:{receipt.request_digest}",
                    "response_digest": receipt.response_digest,
                },
                "failed_candidate_fingerprint": digest_of(
                    {
                        "candidate_id": str(failed_candidate.candidate_id),
                        "candidate_version": failed_candidate.candidate_version,
                        "raw_candidate": failed_candidate.raw_candidate,
                        "failure_code": failed_candidate.failure_code,
                    }
                ),
            }
            failed_documents.append(failed_document)
            lineage.append(failed_document)
            recovery_job = region_recovery_job(
                source_version_id=source_version_id,
                native_text=native_text,
                image_path=image_path,
                failed_candidate=failed_candidate,
            )
            if (
                page_number in qualification_pages
                and page_number not in qualification_selected_pages
            ):
                qualification_jobs.append(recovery_job)
                qualification_selected_pages.add(page_number)
            else:
                remaining_jobs.append(recovery_job)
    if qualification_selected_pages != set(qualification_pages):
        raise ValueError("Each recovery qualification page must contain a failed candidate")
    _write_json(
        salvage_output,
        {
            "evaluation_policy_version": "pass-a-candidate-granular-v0.1.0",
            "selected_pages": page_numbers,
            "accepted_candidate_count": len(accepted_documents),
            "failed_candidate_count": len(failed_documents),
            "accepted_candidates": accepted_documents,
            "failed_candidates": failed_documents,
        },
    )
    _write_json(
        lineage_output,
        {
            "contract": "guide-region-recovery-lineage/0.1.0",
            "source_version_id": str(source_version_id),
            "failed_candidate_count": len(lineage),
            "failed_candidates": lineage,
            "fingerprint": digest_of(lineage),
        },
    )
    write_job_manifest(qualification_output, tuple(qualification_jobs))
    write_job_manifest(remaining_output, tuple(remaining_jobs))
    write_job_manifest(salvage_verifier_output, tuple(salvage_verifier_jobs))


def prepare_pass_b_candidate_recovery_command(
    *,
    pdf_path: Path,
    source_version_id: UUID,
    pass_a_evaluation_path: Path,
    unresolved_manifest_path: Path,
    render_root: Path,
    output: Path,
    registry_output: Path,
) -> None:
    pass_a = json.loads(pass_a_evaluation_path.read_text(encoding="utf-8"))
    unresolved = json.loads(unresolved_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(pass_a, dict) or not isinstance(pass_a.get("pages"), list):
        raise ValueError("Pass A evaluation is malformed")
    if not isinstance(unresolved, dict) or not isinstance(unresolved.get("candidates"), list):
        raise ValueError("Pass B unresolved manifest is malformed")
    requested = {
        str(value["candidate_id"]): value
        for value in unresolved["candidates"]
        if isinstance(value, dict)
    }
    if len(requested) != len(unresolved["candidates"]):
        raise ValueError("Pass B recovery manifest has duplicate or malformed identities")
    reader = PdfReader(str(pdf_path), strict=True)
    jobs: list[QwenJob] = []
    registry: list[dict[str, object]] = []
    found: set[str] = set()
    for page in pass_a["pages"]:
        if not isinstance(page, dict) or not isinstance(page.get("candidates"), list):
            raise ValueError("Pass A page is malformed")
        page_number = int(page["page_number"])
        failure_codes_by_candidate: dict[str, list[str]] = {}
        validation_failures = page.get("validation_failures", [])
        if not isinstance(validation_failures, list):
            raise ValueError("Pass A validation failures are malformed")
        for failure in validation_failures:
            if isinstance(failure, dict):
                failure_codes_by_candidate.setdefault(str(failure["candidate_id"]), []).append(
                    str(failure["failure_code"])
                )
        for value in page["candidates"]:
            if not isinstance(value, dict):
                raise ValueError("Pass A candidate is malformed")
            candidate_id = str(value["candidate_id"])
            if candidate_id not in requested:
                continue
            candidate = _candidate_from_document(value)
            request = requested[candidate_id]
            if candidate.version != int(str(request["candidate_version"])):
                raise ValueError("Pass B recovery CandidateVersion mismatch")
            if candidate.locator.page_number != int(str(request["page_number"])):
                raise ValueError("Pass B recovery page mismatch")
            native_text = reader.pages[page_number - 1].extract_text() or ""
            image_path = render_page(
                pdf_path=pdf_path,
                page_number=page_number,
                render_root=render_root,
            )
            failure_codes = tuple(failure_codes_by_candidate.get(candidate_id, ()))
            job = compact_candidate_verifier_job(
                source_version_id=source_version_id,
                native_text=native_text,
                image_path=image_path,
                candidate=candidate,
                purpose="recovery",
                validation_failure_codes=failure_codes,
            )
            jobs.append(job)
            registry.append(
                {
                    "job_id": job.job_id,
                    "purpose": "recovery",
                    "candidate": asdict(candidate),
                    "validation_failure_codes": failure_codes,
                }
            )
            found.add(candidate_id)
    if found != set(requested):
        raise ValueError("Pass B recovery could not resolve every exact candidate identity")
    write_job_manifest(output, tuple(jobs))
    _write_json(
        registry_output,
        {
            "contract": "guide-compact-verification-registry/0.1.0",
            "purpose": "recovery",
            "candidate_count": len(registry),
            "candidates": registry,
            "fingerprint": digest_of(registry),
        },
    )


def prepare_corrected_reverification_command(
    *,
    pdf_path: Path,
    source_version_id: UUID,
    pass_b_evaluation_path: Path,
    render_root: Path,
    output: Path,
    registry_output: Path,
) -> None:
    pass_b = json.loads(pass_b_evaluation_path.read_text(encoding="utf-8"))
    if not isinstance(pass_b, dict) or not isinstance(pass_b.get("results"), list):
        raise ValueError("Pass B evaluation is malformed")
    manifest = inspect_pdf(pdf_path, source_version_id)
    manifests = {page.page_number: page for page in manifest.pages}
    reader = PdfReader(str(pdf_path), strict=True)
    jobs: list[QwenJob] = []
    registry: list[dict[str, object]] = []
    identities: set[tuple[str, int]] = set()
    for result in pass_b["results"]:
        if not isinstance(result, dict) or result.get("kind") != "candidate":
            continue
        corrected = result.get("corrected_candidate")
        if corrected is None:
            continue
        if not isinstance(corrected, dict):
            raise ValueError("Corrected CandidateVersion must be an object")
        candidate = _candidate_from_document(corrected)
        identity = (str(candidate.candidate_id), candidate.version)
        if identity in identities:
            raise ValueError("Corrected re-verification manifest contains a duplicate identity")
        identities.add(identity)
        if candidate.source_version_id != source_version_id:
            raise ValueError("Corrected CandidateVersion source identity mismatch")
        if candidate.parent_version != candidate.version - 1:
            raise ValueError("Corrected CandidateVersion parent lineage mismatch")
        page_number = candidate.locator.page_number
        native_text = reader.pages[page_number - 1].extract_text() or ""
        image_path = render_page(
            pdf_path=pdf_path,
            page_number=page_number,
            render_root=render_root,
        )
        validation_failures = validate_candidate(
            candidate,
            GuideValidationContext(
                source_version_id,
                manifests[page_number],
                native_text,
                (page_number,),
            ),
        )
        failure_codes = tuple(str(failure.failure_code) for failure in validation_failures)
        job = compact_candidate_verifier_job(
            source_version_id=source_version_id,
            native_text=native_text,
            image_path=image_path,
            candidate=candidate,
            purpose="corrected_reverification",
            validation_failure_codes=failure_codes,
        )
        jobs.append(job)
        registry.append(
            {
                "job_id": job.job_id,
                "purpose": "corrected_reverification",
                "candidate": asdict(candidate),
                "parent_candidate": {
                    "candidate_id": str(candidate.candidate_id),
                    "candidate_version": candidate.parent_version,
                    "original_disposition": result["disposition"],
                },
                "validation_failures": [asdict(failure) for failure in validation_failures],
            }
        )
    write_job_manifest(output, tuple(jobs))
    _write_json(
        registry_output,
        {
            "contract": "guide-corrected-reverification-registry/0.1.0",
            "purpose": "corrected_reverification",
            "candidate_count": len(registry),
            "candidates": registry,
            "fingerprint": digest_of(registry),
        },
    )


def evaluate_compact_verification_command(
    *,
    registry_path: Path,
    receipt_paths: tuple[Path, ...],
    output: Path,
) -> None:
    registry_document = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry_document, dict):
        raise ValueError("Compact verification registry must be an object")
    entries = registry_document.get("candidates")
    if entries is None:
        entries = registry_document.get("accepted_candidates")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Compact verification registry has no candidates")
    registry: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("candidate"), dict):
            raise ValueError("Compact verification registry entry is malformed")
        job_id = str(entry["job_id"])
        if job_id in registry:
            raise ValueError("Compact verification registry contains duplicate jobs")
        registry[job_id] = entry
    receipts: dict[str, QwenRawReceipt] = {}
    for receipt_path in receipt_paths:
        for receipt in load_receipts(receipt_path):
            if receipt.job_id not in registry:
                continue
            if receipt.job_id in receipts:
                raise ValueError("Compact verification has duplicate receipt identities")
            receipts[receipt.job_id] = receipt

    results: list[dict[str, object]] = []
    counts = {disposition.value: 0 for disposition in VerificationDisposition}
    for job_id, entry in registry.items():
        candidate_document = entry["candidate"]
        if not isinstance(candidate_document, dict):
            raise ValueError("Compact verification candidate is malformed")
        candidate = _candidate_from_document(candidate_document)
        candidate_receipt = receipts.get(job_id)
        failure_codes: list[str] = []
        reason_codes: tuple[str, ...]
        if candidate_receipt is None:
            disposition = VerificationDisposition.MODEL_FAILED
            reason_codes = ("TERMINAL_RECEIPT_MISSING",)
            correction_required = False
            response_digest = digest_of("")
            attempt_ref = None
        elif candidate_receipt.state != "completed":
            disposition = VerificationDisposition.MODEL_FAILED
            reason_codes = ("MODEL_EXECUTION_FAILED",)
            correction_required = False
            response_digest = candidate_receipt.response_digest
            attempt_ref = candidate_receipt.attempt_id
        else:
            try:
                parsed = parse_compact_candidate_verification(
                    candidate_receipt.response,
                    candidate=candidate,
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                disposition = VerificationDisposition.MODEL_FAILED
                reason_codes = ("MODEL_RESPONSE_INTEGRITY_FAILED",)
                correction_required = False
                failure_codes.append("MODEL_RESPONSE_INTEGRITY_FAILED")
            else:
                disposition = parsed.disposition
                reason_codes = parsed.reason_codes
                correction_required = parsed.correction_required
            response_digest = candidate_receipt.response_digest
            attempt_ref = candidate_receipt.attempt_id

        blocking_failures = entry.get("validation_failures", ())
        blocking_failure_codes = entry.get("validation_failure_codes", ())
        has_blocking_failure = bool(blocking_failures) or bool(blocking_failure_codes)
        effective_disposition = disposition
        if disposition is VerificationDisposition.SUPPORTED and has_blocking_failure:
            effective_disposition = VerificationDisposition.INSUFFICIENT
            failure_codes.append("DETERMINISTIC_BLOCKING_FAILURE")
        counts[effective_disposition.value] += 1
        results.append(
            {
                "job_id": job_id,
                "purpose": entry.get("purpose"),
                "candidate_id": str(candidate.candidate_id),
                "candidate_version": candidate.version,
                "page_number": candidate.locator.page_number,
                "model_disposition": disposition,
                "disposition": effective_disposition,
                "reason_codes": reason_codes,
                "correction_required": correction_required,
                "failure_codes": failure_codes,
                "response_digest": response_digest,
                "attempt_ref": attempt_ref,
            }
        )
    _write_json(
        output,
        {
            "evaluation_policy_version": "compact-candidate-verifier-v0.1.0",
            "expected_candidates": len(registry),
            "terminal_candidates": len(results),
            "receipt_count": len(receipts),
            "disposition_counts": counts,
            "all_terminal": len(results) == len(registry),
            "results": results,
            "fingerprint": digest_of(results),
        },
    )


def evaluate_region_recovery_command(
    *,
    pdf_path: Path,
    source_version_id: UUID,
    lineage_path: Path,
    receipt_paths: tuple[Path, ...],
    profile_path: Path,
    output: Path,
    qualification: bool,
) -> None:
    lineage_document = json.loads(lineage_path.read_text(encoding="utf-8"))
    profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(lineage_document, dict) or not isinstance(
        lineage_document.get("failed_candidates"), list
    ):
        raise ValueError("Region recovery lineage is malformed")
    if not isinstance(profile_data, dict):
        raise ValueError("Region recovery profile is malformed")
    profile = GuideExecutionProfile(**profile_data)
    if profile.quantization != "bf16":
        raise ValueError("Region recovery requires the qualified BF16 profile")
    failed_by_job: dict[str, PassAFailedCandidate] = {}
    for value in lineage_document["failed_candidates"]:
        if not isinstance(value, dict):
            raise ValueError("Region recovery failed candidate is malformed")
        failed_candidate = _failed_candidate_from_document(value)
        job_id = (
            f"region-recovery-page-{failed_candidate.page_number:04d}-"
            f"{failed_candidate.candidate_id}-v{failed_candidate.candidate_version}"
        )
        if job_id in failed_by_job:
            raise ValueError("Region recovery lineage contains a duplicate identity")
        failed_by_job[job_id] = failed_candidate
    receipts: dict[str, QwenRawReceipt] = {}
    for receipt_path in receipt_paths:
        for receipt in load_receipts(receipt_path):
            if receipt.job_id not in failed_by_job:
                raise ValueError("Region recovery receipt has an unknown exact identity")
            if receipt.job_id in receipts:
                raise ValueError("Region recovery has duplicate receipt identities")
            receipts[receipt.job_id] = receipt
    if not receipts:
        raise ValueError("Region recovery evaluation requires receipts")
    manifest = inspect_pdf(pdf_path, source_version_id)
    manifests = {page.page_number: page for page in manifest.pages}
    reader = PdfReader(str(pdf_path), strict=True)
    results: list[dict[str, object]] = []
    corrected_count = insufficient_count = model_failed_count = 0
    for job_id, receipt in receipts.items():
        failed_candidate = failed_by_job[job_id]
        page_number = failed_candidate.page_number
        native_text = reader.pages[page_number - 1].extract_text() or ""
        corrected_candidate: GuidanceCandidateVersion | None = None
        validation_failures: tuple[GuideValidationFailure, ...] = ()
        reason_codes: tuple[str, ...]
        if receipt.state != "completed":
            outcome = "model_failed"
            reason_codes = ("MODEL_EXECUTION_FAILED",)
        else:
            try:
                parsed = parse_region_recovery(
                    receipt.response,
                    failed_candidate=failed_candidate,
                    native_text_required=len(native_text.strip()) >= 24,
                )
                outcome = parsed.outcome
                reason_codes = parsed.reason_codes
                if outcome == "corrected_candidate":
                    corrected_candidate = corrected_candidate_from_region_recovery(
                        failed_candidate,
                        parsed,
                        source_version_id=source_version_id,
                        profile=profile,
                    )
                    validation_failures = validate_candidate(
                        corrected_candidate,
                        GuideValidationContext(
                            source_version_id,
                            manifests[page_number],
                            native_text,
                            (page_number,),
                        ),
                    )
                    if any(failure.blocking for failure in validation_failures):
                        outcome = "insufficient_evidence"
                        corrected_candidate = None
                        reason_codes = (*reason_codes, "DETERMINISTIC_GROUNDING_FAILED")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                outcome = "model_failed"
                reason_codes = ("MODEL_RESPONSE_INTEGRITY_FAILED",)
        if outcome == "corrected_candidate":
            corrected_count += 1
        elif outcome == "insufficient_evidence":
            insufficient_count += 1
        else:
            model_failed_count += 1
        results.append(
            {
                "job_id": job_id,
                "candidate_id": str(failed_candidate.candidate_id),
                "parent_version": failed_candidate.candidate_version,
                "page_number": page_number,
                "outcome": outcome,
                "reason_codes": reason_codes,
                "corrected_candidate": (
                    asdict(corrected_candidate) if corrected_candidate is not None else None
                ),
                "validation_failures": [asdict(failure) for failure in validation_failures],
                "source_failed_candidate_fingerprint": digest_of(failed_candidate.raw_candidate),
                "response_digest": receipt.response_digest,
                "attempt_ref": receipt.attempt_id,
            }
        )
    qualified = (
        qualification
        and len(results) >= 3
        and corrected_count == len(results)
        and insufficient_count == 0
        and model_failed_count == 0
    )
    _write_json(
        output,
        {
            "profile_fingerprint": profile.fingerprint,
            "prompt_version": "guide_region_candidate_recovery_v0.1",
            "qualification": qualification,
            "qualified": qualified,
            "expected_receipts": len(receipts),
            "corrected_candidates": corrected_count,
            "insufficient_evidence": insufficient_count,
            "model_failed": model_failed_count,
            "results": results,
            "fingerprint": digest_of(results),
        },
    )


def prepare_region_reverification_command(
    *,
    pdf_path: Path,
    source_version_id: UUID,
    recovery_evaluation_paths: tuple[Path, ...],
    render_root: Path,
    output: Path,
    registry_output: Path,
) -> None:
    reader = PdfReader(str(pdf_path), strict=True)
    jobs: list[QwenJob] = []
    registry: list[dict[str, object]] = []
    identities: set[tuple[str, int]] = set()
    for evaluation_path in recovery_evaluation_paths:
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        if not isinstance(evaluation, dict) or not isinstance(evaluation.get("results"), list):
            raise ValueError("Region recovery evaluation is malformed")
        for result in evaluation["results"]:
            if not isinstance(result, dict) or result.get("corrected_candidate") is None:
                continue
            candidate_document = result["corrected_candidate"]
            if not isinstance(candidate_document, dict):
                raise ValueError("Region corrected CandidateVersion is malformed")
            candidate = _candidate_from_document(candidate_document)
            identity = (str(candidate.candidate_id), candidate.version)
            if identity in identities:
                raise ValueError("Region corrected re-verification identity is duplicated")
            identities.add(identity)
            page_number = candidate.locator.page_number
            native_text = reader.pages[page_number - 1].extract_text() or ""
            image_path = render_page(
                pdf_path=pdf_path,
                page_number=page_number,
                render_root=render_root,
            )
            job = compact_candidate_verifier_job(
                source_version_id=source_version_id,
                native_text=native_text,
                image_path=image_path,
                candidate=candidate,
                purpose="corrected_reverification",
            )
            jobs.append(job)
            registry.append(
                {
                    "job_id": job.job_id,
                    "purpose": "corrected_reverification",
                    "candidate": asdict(candidate),
                    "parent_candidate": {
                        "candidate_id": str(candidate.candidate_id),
                        "candidate_version": candidate.parent_version,
                        "original_disposition": "provider_result_integrity_failed",
                    },
                    "validation_failures": result.get("validation_failures", []),
                }
            )
    write_job_manifest(output, tuple(jobs))
    _write_json(
        registry_output,
        {
            "contract": "guide-region-corrected-reverification-registry/0.1.0",
            "candidate_count": len(registry),
            "candidates": registry,
            "fingerprint": digest_of(registry),
        },
    )


def reconcile_bounded_recovery_command(
    *,
    platform_identity_path: Path,
    pass_a_evaluation_path: Path,
    pass_a_recovery_path: Path,
    pass_b_evaluation_path: Path,
    pass_b_salvage_path: Path,
    compact_evaluation_paths: tuple[Path, ...],
    corrected_registry_paths: tuple[Path, ...],
    native_registry_paths: tuple[Path, ...],
    region_lineage_path: Path,
    region_recovery_evaluation_paths: tuple[Path, ...],
    coverage_output: Path,
    gaps_output: Path,
    publication_output: Path,
) -> None:
    identity = json.loads(platform_identity_path.read_text(encoding="utf-8"))
    pass_a = json.loads(pass_a_evaluation_path.read_text(encoding="utf-8"))
    pass_a_recovery = json.loads(pass_a_recovery_path.read_text(encoding="utf-8"))
    pass_b = json.loads(pass_b_evaluation_path.read_text(encoding="utf-8"))
    pass_b_salvage = json.loads(pass_b_salvage_path.read_text(encoding="utf-8"))
    region_lineage = json.loads(region_lineage_path.read_text(encoding="utf-8"))
    if not all(
        isinstance(value, dict)
        for value in (identity, pass_a, pass_a_recovery, pass_b, pass_b_salvage, region_lineage)
    ):
        raise ValueError("Bounded reconciliation inputs must be JSON objects")
    source_version_id = UUID(str(identity["source_version_id"]))
    edition_id = UUID(str(identity["practice_guide_edition_id"]))
    run_id = UUID(str(identity["ingestion_run_id"]))
    expected_pages = int(identity["page_count"])
    if expected_pages != 425:
        raise ValueError("KG-ID-01 reconciliation is pinned to 425 page identities")

    nodes: dict[tuple[str, int], dict[str, object]] = {}
    native_superseded_parent_keys: set[tuple[str, int]] = set()

    def add_candidate(
        candidate: GuidanceCandidateVersion,
        *,
        origin: str,
        validation_failures: object = (),
    ) -> None:
        key = (str(candidate.candidate_id), candidate.version)
        prior = nodes.get(key)
        document = {
            "candidate": candidate,
            "origin": origin,
            "page_number": candidate.locator.page_number,
            "parent_version": candidate.parent_version,
            "validation_failures": validation_failures,
        }
        if prior is not None:
            prior_candidate = prior.get("candidate")
            if not isinstance(prior_candidate, GuidanceCandidateVersion):
                raise ValueError("CandidateVersion conflicts with failed parent lineage")
            if prior_candidate.fingerprint != candidate.fingerprint:
                raise ValueError("Duplicate CandidateVersion identity has divergent content")
            return
        nodes[key] = document

    base_pages: dict[int, dict[str, object]] = {}
    base_validation_failures: dict[tuple[str, int], list[dict[str, object]]] = {}
    for page_value in pass_a.get("pages", []):
        if not isinstance(page_value, dict) or not isinstance(page_value.get("candidates"), list):
            raise ValueError("Pass A reconciliation page is malformed")
        page_number = int(page_value["page_number"])
        base_pages[page_number] = page_value
        page_failures = page_value.get("validation_failures", [])
        if not isinstance(page_failures, list):
            raise ValueError("Pass A validation failure collection is malformed")
        for failure in page_failures:
            if isinstance(failure, dict):
                key = (str(failure["candidate_id"]), int(str(failure["candidate_version"])))
                base_validation_failures.setdefault(key, []).append(failure)
        for candidate_value in page_value["candidates"]:
            if not isinstance(candidate_value, dict):
                raise ValueError("Pass A reconciliation candidate is malformed")
            candidate = _candidate_from_document(candidate_value)
            key = (str(candidate.candidate_id), candidate.version)
            add_candidate(
                candidate,
                origin="pass_a_original",
                validation_failures=base_validation_failures.get(key, ()),
            )

    accepted_recovery = pass_a_recovery.get("accepted_candidates")
    if not isinstance(accepted_recovery, list):
        raise ValueError("Pass A candidate recovery is malformed")
    for entry in accepted_recovery:
        if not isinstance(entry, dict) or not isinstance(entry.get("candidate"), dict):
            raise ValueError("Pass A recovered candidate is malformed")
        candidate = _candidate_from_document(entry["candidate"])
        add_candidate(
            candidate,
            origin="pass_a_candidate_salvage",
            validation_failures=entry.get("validation_failures", ()),
        )

    failed_parent_values = region_lineage.get("failed_candidates")
    if not isinstance(failed_parent_values, list):
        raise ValueError("Region recovery lineage is malformed")
    for value in failed_parent_values:
        if not isinstance(value, dict):
            raise ValueError("Region failed parent is malformed")
        failed = _failed_candidate_from_document(value)
        key = (str(failed.candidate_id), failed.candidate_version)
        if key in nodes:
            raise ValueError("Failed parent duplicates a valid CandidateVersion")
        nodes[key] = {
            "candidate": None,
            "failed_candidate": failed,
            "origin": "pass_a_failed_parent",
            "page_number": failed.page_number,
            "parent_version": None,
            "validation_failures": (failed.failure_code,),
        }

    for registry_path in corrected_registry_paths:
        registry_document = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(registry_document, dict) or not isinstance(
            registry_document.get("candidates"), list
        ):
            raise ValueError("Corrected CandidateVersion registry is malformed")
        for entry in registry_document["candidates"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("candidate"), dict):
                raise ValueError("Corrected CandidateVersion registry entry is malformed")
            candidate = _candidate_from_document(entry["candidate"])
            add_candidate(
                candidate,
                origin="corrected_candidate",
                validation_failures=entry.get("validation_failures", ()),
            )

    for registry_path in native_registry_paths:
        registry_document = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(registry_document, dict) or not isinstance(
            registry_document.get("entries"), list
        ):
            raise ValueError("Native recovery CandidateVersion registry is malformed")
        for entry in registry_document["entries"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("candidate"), dict):
                raise ValueError("Native recovery registry entry is malformed")
            candidate = _candidate_from_document(entry["candidate"])
            if candidate.parent_version is None:
                raise ValueError("Native recovery CandidateVersion lacks parent lineage")
            add_candidate(
                candidate,
                origin="native_first_recovery",
                validation_failures=entry.get("validation_failures", ()),
            )
            native_superseded_parent_keys.add(
                (str(candidate.candidate_id), candidate.parent_version)
            )

    statuses: dict[tuple[str, int], CandidateTerminalStatus] = {}
    model_dispositions: dict[tuple[str, int], str] = {}

    def apply_disposition(result: dict[str, object], *, source: str) -> None:
        key = (str(result["candidate_id"]), int(str(result["candidate_version"])))
        if key not in nodes:
            raise ValueError(f"{source} references an unknown CandidateVersion")
        disposition = VerificationDisposition(str(result["disposition"]))
        model_dispositions[key] = str(result.get("model_disposition", disposition))
        status = CandidateTerminalStatus(disposition.value)
        node_failures = nodes[key].get("validation_failures", ())
        if status is CandidateTerminalStatus.SUPPORTED and bool(node_failures):
            status = CandidateTerminalStatus.INSUFFICIENT
        prior = statuses.get(key)
        if prior is not None and prior is not status:
            raise ValueError("CandidateVersion received conflicting terminal dispositions")
        statuses[key] = status

    for result in pass_b.get("results", []):
        if isinstance(result, dict) and result.get("kind") == "candidate":
            apply_disposition(result, source="base Pass B")
    for result in pass_b_salvage.get("results", []):
        if isinstance(result, dict) and result.get("kind") == "candidate":
            apply_disposition(result, source="candidate-granular salvage")
    for evaluation_path in compact_evaluation_paths:
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        if not isinstance(evaluation, dict) or not isinstance(evaluation.get("results"), list):
            raise ValueError("Compact verification evaluation is malformed")
        for result in evaluation["results"]:
            if not isinstance(result, dict):
                raise ValueError("Compact verification result is malformed")
            apply_disposition(result, source="compact verification")

    for evaluation_path in region_recovery_evaluation_paths:
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        if not isinstance(evaluation, dict) or not isinstance(evaluation.get("results"), list):
            raise ValueError("Region recovery evaluation is malformed")
        for result in evaluation["results"]:
            if not isinstance(result, dict):
                raise ValueError("Region recovery result is malformed")
            parent_key = (str(result["candidate_id"]), int(str(result["parent_version"])))
            if parent_key not in nodes:
                raise ValueError("Region recovery result has unknown parent lineage")
            outcome = str(result["outcome"])
            if outcome == "corrected_candidate":
                statuses[parent_key] = CandidateTerminalStatus.SUPERSEDED
                corrected_value = result.get("corrected_candidate")
                if not isinstance(corrected_value, dict):
                    raise ValueError("Region recovery omitted corrected CandidateVersion")
                corrected = _candidate_from_document(corrected_value)
                add_candidate(
                    corrected,
                    origin="region_recovery_corrected",
                    validation_failures=result.get("validation_failures", ()),
                )
            elif outcome == "insufficient_evidence":
                statuses[parent_key] = CandidateTerminalStatus.INSUFFICIENT
            elif outcome == "model_failed":
                statuses[parent_key] = CandidateTerminalStatus.MODEL_FAILED
            else:
                raise ValueError("Region recovery outcome is not terminal")

    for parent_key in native_superseded_parent_keys:
        if parent_key not in nodes:
            raise ValueError("Native recovery parent CandidateVersion lineage is missing")
        prior = statuses.get(parent_key)
        if prior is not None and prior is not CandidateTerminalStatus.SUPERSEDED:
            raise ValueError("Native recovery parent already has a conflicting terminal status")
        statuses[parent_key] = CandidateTerminalStatus.SUPERSEDED

    for key, node in nodes.items():
        parent_version = node.get("parent_version")
        if parent_version is not None:
            parent_key = (key[0], int(str(parent_version)))
            if parent_key not in nodes:
                raise ValueError("CandidateVersion parent lineage is missing")
    missing_statuses = sorted(key for key in nodes if key not in statuses)
    if missing_statuses:
        raise ValueError(f"CandidateVersion terminal statuses missing: {len(missing_statuses)}")

    valid_candidate_values: list[GuidanceCandidateVersion] = []
    for node in nodes.values():
        node_candidate = node.get("candidate")
        if isinstance(node_candidate, GuidanceCandidateVersion):
            valid_candidate_values.append(node_candidate)
    valid_candidates = tuple(valid_candidate_values)
    latest = latest_candidate_versions(valid_candidates)
    latest_supported = tuple(
        candidate
        for candidate_id, candidate in latest.items()
        if statuses[(candidate_id, candidate.version)] is CandidateTerminalStatus.SUPPORTED
    )
    conflict_pairs = candidate_conflict_pairs(latest_supported)
    quarantined_keys = {
        (str(candidate.candidate_id), candidate.version)
        for pair in conflict_pairs
        for candidate in pair
    }
    conflict_records = [
        {
            "candidate_id": str(candidate.candidate_id),
            "candidate_version": candidate.version,
            "conflicting_candidate_id": str(other.candidate_id),
            "conflicting_candidate_version": other.version,
            "conflict_type": "overlapping_peer_guidance",
        }
        for left, right in conflict_pairs
        for candidate, other in ((left, right), (right, left))
    ]

    pass_b_page_results = {
        int(result["page_number"]): result
        for result in pass_b.get("results", [])
        if isinstance(result, dict) and result.get("kind") == "page"
    }
    logical_ids_by_page: dict[int, set[str]] = {page: set() for page in range(1, 426)}
    for key, node in nodes.items():
        logical_ids_by_page[int(str(node["page_number"]))].add(key[0])

    page_receipts: list[dict[str, object]] = []
    gap_drafts: list[dict[str, object]] = []
    for page_number in range(1, expected_pages + 1):
        logical_ids = logical_ids_by_page[page_number]
        latest_nodes: list[tuple[tuple[str, int], dict[str, object]]] = []
        for candidate_id in logical_ids:
            versions = [key for key in nodes if key[0] == candidate_id]
            latest_key = max(versions, key=lambda item: item[1])
            latest_nodes.append((latest_key, nodes[latest_key]))
        verified_count = 0
        unresolved_count = 0
        page_has_model_failure = False
        for key, node in latest_nodes:
            status = statuses[key]
            quarantined = key in quarantined_keys
            if status is CandidateTerminalStatus.SUPPORTED and not quarantined:
                verified_count += 1
                continue
            unresolved_count += 1
            if status is CandidateTerminalStatus.MODEL_FAILED:
                page_has_model_failure = True
            node_candidate = node.get("candidate")
            failed_candidate = node.get("failed_candidate")
            topic: str | None
            form_type: str | None
            field: str | None
            section: str
            if isinstance(node_candidate, GuidanceCandidateVersion):
                topic = node_candidate.topic
                form_type = node_candidate.document_or_form_type
                field = node_candidate.field_or_element
                section = node_candidate.section
            elif isinstance(failed_candidate, PassAFailedCandidate):
                topic = str(failed_candidate.raw_candidate.get("topic", "")) or None
                form_value = failed_candidate.raw_candidate.get("document_or_form_type")
                field_value = failed_candidate.raw_candidate.get("field_or_element")
                form_type = str(form_value) if form_value is not None else None
                field = str(field_value) if field_value is not None else None
                section = str(failed_candidate.raw_candidate.get("section", ""))
            else:
                raise ValueError("Candidate gap lacks source context")
            gap_code = (
                "GUIDANCE_CONFLICT_QUARANTINED"
                if quarantined
                else f"CANDIDATE_{status.value.upper()}"
            )
            gap_drafts.append(
                {
                    "page_number": page_number,
                    "candidate_id": key[0],
                    "candidate_version": key[1],
                    "gap_code": gap_code,
                    "topic": topic,
                    "document_or_form_type": form_type,
                    "field_or_element": field,
                    "searchable_text": " ".join(
                        value
                        for value in (section, topic or "", form_type or "", field or "")
                        if value
                    ),
                    "parameters": {
                        "candidate_status": status.value,
                        "quarantined": quarantined,
                    },
                }
            )
        candidate_count = len(logical_ids)
        if candidate_count == 0:
            page = base_pages.get(page_number)
            page_result = pass_b_page_results.get(page_number)
            if (
                page is not None
                and page.get("no_methodological_content") is True
                and page_result is not None
                and page_result.get("no_methodological_content") is True
                and str(page_result.get("disposition")) == VerificationDisposition.SUPPORTED
            ):
                state = GuideTerminalState.NO_METHODOLOGICAL_CONTENT
            elif page is None:
                state = GuideTerminalState.TECHNICALLY_BLOCKED
            else:
                state = GuideTerminalState.INSUFFICIENT_EVIDENCE
            if state is not GuideTerminalState.NO_METHODOLOGICAL_CONTENT:
                unresolved_count = 1
                gap_drafts.append(
                    {
                        "page_number": page_number,
                        "candidate_id": None,
                        "candidate_version": None,
                        "gap_code": f"PAGE_{state.value.upper()}",
                        "topic": None,
                        "document_or_form_type": None,
                        "field_or_element": None,
                        "searchable_text": f"страница {page_number} исполнительная документация",
                        "parameters": {"page_state": state.value},
                    }
                )
        elif verified_count and unresolved_count:
            state = GuideTerminalState.PARTIAL_WITH_GAPS
        elif verified_count:
            state = GuideTerminalState.VERIFIED
        elif page_has_model_failure:
            state = GuideTerminalState.MODEL_FAILED
        else:
            state = GuideTerminalState.INSUFFICIENT_EVIDENCE
        page_receipts.append(
            {
                "page_number": page_number,
                "state": state.value,
                "candidate_count": candidate_count,
                "verified_count": verified_count,
                "unresolved_count": unresolved_count,
            }
        )
    if len(page_receipts) != expected_pages or any(
        receipt["state"] == GuideTerminalState.UNRESOLVED for receipt in page_receipts
    ):
        raise ValueError("Final page reconciliation is not terminal")

    candidate_status_documents: list[dict[str, object]] = []
    for key, node in sorted(nodes.items()):
        node_candidate = node.get("candidate")
        failed_candidate = node.get("failed_candidate")
        if isinstance(node_candidate, GuidanceCandidateVersion):
            node_fingerprint = node_candidate.fingerprint
        elif isinstance(failed_candidate, PassAFailedCandidate):
            node_fingerprint = digest_of(asdict(failed_candidate))
        else:
            raise ValueError("CandidateVersion status lacks immutable content")
        candidate_status_documents.append(
            {
                "candidate_id": key[0],
                "candidate_version": key[1],
                "page_number": int(str(node["page_number"])),
                "parent_version": node.get("parent_version"),
                "origin": node["origin"],
                "status": statuses[key].value,
                "model_disposition": model_dispositions.get(key),
                "fingerprint": node_fingerprint,
            }
        )
    page_state_counts = {
        state.value: sum(receipt["state"] == state.value for receipt in page_receipts)
        for state in GuideTerminalState
    }
    candidate_state_counts = {
        status.value: sum(value is status for value in statuses.values())
        for status in CandidateTerminalStatus
    }
    reconciliation_fingerprint = digest_of(
        {
            "source_version_id": str(source_version_id),
            "pages": page_receipts,
            "candidates": candidate_status_documents,
            "conflicts": conflict_records,
        }
    )
    coverage_manifest_id = deterministic_uuid(
        f"kg-id-coverage:{edition_id}:1:{reconciliation_fingerprint}"
    )
    recorded_at = datetime.now(UTC)
    gaps: list[GuidanceGap] = []
    page_states = {
        int(str(receipt["page_number"])): str(receipt["state"]) for receipt in page_receipts
    }
    for ordinal, draft in enumerate(gap_drafts, start=1):
        page_number = int(str(draft["page_number"]))
        state = GuideTerminalState(page_states[page_number])
        if state is GuideTerminalState.VERIFIED:
            state = GuideTerminalState.PARTIAL_WITH_GAPS
        gap_payload = {
            "coverage_manifest_id": str(coverage_manifest_id),
            "ordinal": ordinal,
            **draft,
            "terminal_state": state.value,
        }
        gap_fingerprint = digest_of(gap_payload)
        gap_parameters = draft["parameters"]
        if not isinstance(gap_parameters, dict):
            raise ValueError("GuidanceGap parameters are malformed")
        gaps.append(
            GuidanceGap(
                guidance_gap_id=deterministic_uuid(f"kg-id-gap:{gap_fingerprint}"),
                coverage_manifest_id=coverage_manifest_id,
                source_version_id=source_version_id,
                page_number=page_number,
                candidate_id=(
                    UUID(str(draft["candidate_id"])) if draft["candidate_id"] is not None else None
                ),
                candidate_version=(
                    int(str(draft["candidate_version"]))
                    if draft["candidate_version"] is not None
                    else None
                ),
                gap_code=str(draft["gap_code"]),
                terminal_state=state,
                topic=str(draft["topic"]) if draft["topic"] is not None else None,
                document_or_form_type=(
                    str(draft["document_or_form_type"])
                    if draft["document_or_form_type"] is not None
                    else None
                ),
                field_or_element=(
                    str(draft["field_or_element"])
                    if draft["field_or_element"] is not None
                    else None
                ),
                searchable_text=str(draft["searchable_text"]),
                content_minimal_parameters=gap_parameters,
                gap_fingerprint=gap_fingerprint,
                recorded_at=recorded_at,
            )
        )

    publishable = tuple(
        candidate
        for candidate in latest_supported
        if (str(candidate.candidate_id), candidate.version) not in quarantined_keys
    )
    manifest_payload = {
        "coverage_manifest_id": str(coverage_manifest_id),
        "edition_id": str(edition_id),
        "run_id": str(run_id),
        "version": 1,
        "expected_pages": expected_pages,
        "page_state_counts": page_state_counts,
        "candidate_state_counts": candidate_state_counts,
        "guidance_unit_count": len(publishable),
        "gap_count": len(gaps),
        "conflict_count": len(conflict_records),
        "reconciliation_fingerprint": reconciliation_fingerprint,
    }
    coverage = CoverageManifest(
        coverage_manifest_id=coverage_manifest_id,
        practice_guide_edition_id=edition_id,
        ingestion_run_id=run_id,
        version=1,
        publication_status=(
            "partial_with_explicit_gaps" if gaps or conflict_records else "complete"
        ),
        expected_page_count=expected_pages,
        terminal_page_count=len(page_receipts),
        page_state_counts=page_state_counts,
        candidate_state_counts=candidate_state_counts,
        guidance_unit_count=len(publishable),
        gap_count=len(gaps),
        conflict_count=len(conflict_records),
        reconciliation_fingerprint=reconciliation_fingerprint,
        manifest_fingerprint=digest_of(manifest_payload),
        recorded_at=recorded_at,
    )
    _write_json(
        coverage_output,
        {
            **asdict(coverage),
            "page_receipts": page_receipts,
            "candidate_statuses": candidate_status_documents,
            "product_ready": False,
        },
    )
    _write_json(
        gaps_output,
        {
            "coverage_manifest_id": str(coverage_manifest_id),
            "gap_count": len(gaps),
            "gaps": [asdict(gap) for gap in gaps],
            "fingerprint": digest_of([gap.gap_fingerprint for gap in gaps]),
        },
    )
    _write_json(
        publication_output,
        {
            "coverage_manifest_id": str(coverage_manifest_id),
            "reconciliation_fingerprint": reconciliation_fingerprint,
            "publishable_candidate_count": len(publishable),
            "publishable_candidates": [asdict(candidate) for candidate in publishable],
            "quarantined_candidate_count": len(quarantined_keys),
            "quarantined_candidate_identities": [
                {"candidate_id": key[0], "candidate_version": key[1]}
                for key in sorted(quarantined_keys)
            ],
            "conflict_count": len(conflict_records),
            "conflicts": conflict_records,
            "raw_original_supported": sum(
                disposition == VerificationDisposition.SUPPORTED
                for key, disposition in (
                    (key, VerificationDisposition(value))
                    for key, value in model_dispositions.items()
                    if key[1] == 1
                )
            ),
            "corrected_supported": sum(
                statuses[key] is CandidateTerminalStatus.SUPPORTED for key in statuses if key[1] > 1
            ),
        },
    )


def evaluate_pass_b_command(
    *,
    pass_a_evaluation: Path,
    receipt_paths: tuple[Path, ...],
    output: Path,
) -> None:
    evaluation = json.loads(pass_a_evaluation.read_text(encoding="utf-8"))
    candidate_map: dict[str, GuidanceCandidateVersion] = {}
    page_candidate_counts: dict[int, int] = {}
    for page in evaluation["pages"]:
        page_number = int(page["page_number"])
        page_candidate_counts[page_number] = len(page["candidates"])
        for candidate_document in page["candidates"]:
            candidate = _candidate_from_document(candidate_document)
            candidate_map[str(candidate.candidate_id)] = candidate
    results: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    supported = contradicted = insufficient = page_supported = 0
    receipts_by_job = {
        receipt.job_id: receipt
        for receipt_path in receipt_paths
        for receipt in load_receipts(receipt_path)
    }
    for receipt in receipts_by_job.values():
        try:
            if receipt.job_id.endswith("-summary"):
                document = json.loads(receipt.response)
                if not isinstance(document, dict):
                    raise ValueError("Page verification must be an object")
                page_number = int(receipt.job_id[12:16])
                if document.get("page_number") != page_number:
                    raise ValueError("Page verification locator mismatch")
                if document.get("candidate_count") != page_candidate_counts[page_number]:
                    raise ValueError("Page verification candidate count mismatch")
                disposition = VerificationDisposition(str(document["disposition"]))
                if disposition is VerificationDisposition.SUPPORTED:
                    page_supported += 1
                results.append(
                    {
                        "job_id": receipt.job_id,
                        "kind": "page",
                        "page_number": page_number,
                        "disposition": disposition,
                        "response_digest": receipt.response_digest,
                        "attempt_ref": receipt.attempt_id
                        or f"legacy:{receipt.job_id}:{receipt.request_digest}",
                    }
                )
                continue
            parts = receipt.job_id.split("-")
            candidate_id = "-".join(parts[4:-1])
            candidate = candidate_map[candidate_id]
            disposition, reasons, corrected = parse_pass_b(receipt.response, candidate=candidate)
            corrected_version = (
                _corrected_candidate_version(candidate, corrected)
                if corrected is not None
                else None
            )
            if disposition is VerificationDisposition.SUPPORTED:
                supported += 1
            elif disposition is VerificationDisposition.CONTRADICTED:
                contradicted += 1
            else:
                insufficient += 1
            results.append(
                {
                    "job_id": receipt.job_id,
                    "kind": "candidate",
                    "candidate_id": candidate_id,
                    "candidate_version": candidate.version,
                    "page_number": candidate.locator.page_number,
                    "disposition": disposition,
                    "reasons": reasons,
                    "corrected_candidate": (
                        asdict(corrected_version) if corrected_version is not None else None
                    ),
                    "response_digest": receipt.response_digest,
                    "attempt_ref": receipt.attempt_id
                    or f"legacy:{receipt.job_id}:{receipt.request_digest}",
                }
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append({"job_id": receipt.job_id, "error_code": type(error).__name__})
    expected = len(page_candidate_counts) + len(candidate_map)
    qualified_development = (
        len(results) == expected
        and not errors
        and sum(result["kind"] == "page" for result in results) == len(page_candidate_counts)
        and supported > 0
    )
    _write_json(
        output,
        {
            "expected_jobs": expected,
            "terminal_jobs": len(results) + len(errors),
            "valid_results": len(results),
            "integrity_errors": errors,
            "page_supported": page_supported,
            "candidate_supported": supported,
            "candidate_contradicted": contradicted,
            "candidate_insufficient": insufficient,
            "qualified_development": qualified_development,
            "production_qualified": False,
            "results": results,
        },
    )


def evaluate_pass_b_batched_command(
    *,
    pass_a_evaluation: Path,
    receipt_paths: tuple[Path, ...],
    output: Path,
) -> None:
    evaluation = json.loads(pass_a_evaluation.read_text(encoding="utf-8"))
    if not isinstance(evaluation, dict) or not isinstance(evaluation.get("pages"), list):
        raise ValueError("Pass A evaluation is malformed")
    candidates_by_page: dict[int, tuple[GuidanceCandidateVersion, ...]] = {}
    for page in evaluation["pages"]:
        if not isinstance(page, dict) or not isinstance(page.get("candidates"), list):
            raise ValueError("Pass A page evaluation is malformed")
        page_number = int(page["page_number"])
        candidates_by_page[page_number] = tuple(
            _candidate_from_document(value)
            for value in page["candidates"]
            if isinstance(value, dict)
        )
    receipts_by_job = {
        receipt.job_id: receipt
        for receipt_path in receipt_paths
        for receipt in load_receipts(receipt_path)
    }
    results: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    supported = contradicted = insufficient = page_supported = 0
    for receipt in receipts_by_job.values():
        try:
            prefix = "pass-b-batch-page-"
            if not receipt.job_id.startswith(prefix):
                raise ValueError("Batched Pass B receipt has an unexpected job identity")
            page_number = int(receipt.job_id.removeprefix(prefix))
            candidates = candidates_by_page[page_number]
            page_disposition, no_content, candidate_results = parse_pass_b_batch(
                receipt.response,
                page_number=page_number,
                candidates=candidates,
            )
            if page_disposition is VerificationDisposition.SUPPORTED:
                page_supported += 1
            results.append(
                {
                    "job_id": receipt.job_id,
                    "kind": "page",
                    "page_number": page_number,
                    "disposition": page_disposition,
                    "no_methodological_content": no_content,
                    "candidate_count": len(candidates),
                    "response_digest": receipt.response_digest,
                    "attempt_ref": receipt.attempt_id
                    or f"legacy:{receipt.job_id}:{receipt.request_digest}",
                }
            )
            for candidate, disposition, reasons, corrected in candidate_results:
                corrected_version = (
                    _corrected_candidate_version(candidate, corrected)
                    if corrected is not None
                    else None
                )
                if disposition is VerificationDisposition.SUPPORTED:
                    supported += 1
                elif disposition is VerificationDisposition.CONTRADICTED:
                    contradicted += 1
                else:
                    insufficient += 1
                results.append(
                    {
                        "job_id": receipt.job_id,
                        "kind": "candidate",
                        "candidate_id": str(candidate.candidate_id),
                        "candidate_version": candidate.version,
                        "page_number": page_number,
                        "disposition": disposition,
                        "reasons": reasons,
                        "corrected_candidate": (
                            asdict(corrected_version) if corrected_version is not None else None
                        ),
                        "response_digest": receipt.response_digest,
                        "attempt_ref": receipt.attempt_id
                        or f"legacy:{receipt.job_id}:{receipt.request_digest}",
                    }
                )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append({"job_id": receipt.job_id, "error_code": type(error).__name__})
    expected_jobs = len(candidates_by_page)
    qualified_development = (
        len(receipts_by_job) == expected_jobs
        and len(results) >= expected_jobs
        and not errors
        and sum(result["kind"] == "page" for result in results) == expected_jobs
        and supported > 0
    )
    _write_json(
        output,
        {
            "expected_jobs": expected_jobs,
            "terminal_jobs": len(receipts_by_job),
            "valid_page_results": sum(result["kind"] == "page" for result in results),
            "integrity_errors": errors,
            "page_supported": page_supported,
            "candidate_supported": supported,
            "candidate_contradicted": contradicted,
            "candidate_insufficient": insufficient,
            "qualified_development": qualified_development,
            "production_qualified": False,
            "prompt_version": "kg-id-guide-pass-b-batched-v0.2.0",
            "results": results,
        },
    )


def salvage_pass_b_batched_command(
    *,
    pass_a_evaluation: Path,
    base_pass_b_evaluation: Path,
    receipt_paths: tuple[Path, ...],
    page_numbers: tuple[int, ...],
    output: Path,
    unresolved_output: Path,
) -> None:
    """Re-evaluate only selected Pass-B receipts at CandidateVersion granularity."""

    if not page_numbers or len(set(page_numbers)) != len(page_numbers):
        raise ValueError("Pass B salvage pages must be a non-empty unique selection")
    evaluation = json.loads(pass_a_evaluation.read_text(encoding="utf-8"))
    base_evaluation = json.loads(base_pass_b_evaluation.read_text(encoding="utf-8"))
    if not isinstance(evaluation, dict) or not isinstance(evaluation.get("pages"), list):
        raise ValueError("Pass A evaluation is malformed")
    if not isinstance(base_evaluation, dict) or not isinstance(
        base_evaluation.get("results"), list
    ):
        raise ValueError("Base Pass B evaluation is malformed")

    candidates_by_page: dict[int, tuple[GuidanceCandidateVersion, ...]] = {}
    all_candidates: dict[str, GuidanceCandidateVersion] = {}
    for page in evaluation["pages"]:
        if not isinstance(page, dict) or not isinstance(page.get("candidates"), list):
            raise ValueError("Pass A page evaluation is malformed")
        page_number = int(page["page_number"])
        candidates = tuple(
            _candidate_from_document(value)
            for value in page["candidates"]
            if isinstance(value, dict)
        )
        candidates_by_page[page_number] = candidates
        for candidate in candidates:
            candidate_id = str(candidate.candidate_id)
            if candidate_id in all_candidates:
                raise ValueError("Pass A contains duplicate CandidateVersion identity")
            all_candidates[candidate_id] = candidate
    if any(page_number not in candidates_by_page for page_number in page_numbers):
        raise ValueError("Pass B salvage selection references a missing Pass A page")

    selected_job_ids = {f"pass-b-batch-page-{page_number:04d}" for page_number in page_numbers}
    selected_receipts: dict[str, QwenRawReceipt] = {}
    for receipt_path in receipt_paths:
        for receipt in load_receipts(receipt_path):
            if receipt.job_id not in selected_job_ids:
                continue
            if receipt.job_id in selected_receipts:
                raise ValueError("Pass B salvage has duplicate receipt identities")
            selected_receipts[receipt.job_id] = receipt
    missing_receipts = sorted(selected_job_ids - set(selected_receipts))
    if missing_receipts:
        raise ValueError(f"Pass B salvage receipts missing: {','.join(missing_receipts)}")

    base_terminal_ids = {
        str(result["candidate_id"])
        for result in base_evaluation["results"]
        if isinstance(result, dict) and result.get("kind") == "candidate"
    }
    results: list[dict[str, object]] = []
    page_receipts: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    accepted_ids: set[str] = set()
    selected_candidate_ids = {
        str(candidate.candidate_id)
        for page_number in page_numbers
        for candidate in candidates_by_page[page_number]
    }
    corrected_versions = 0
    disposition_counts = {disposition.value: 0 for disposition in VerificationDisposition}

    for page_number in page_numbers:
        job_id = f"pass-b-batch-page-{page_number:04d}"
        receipt = selected_receipts[job_id]
        page_evaluation = evaluate_pass_b_batch_items(
            receipt.response,
            page_number=page_number,
            candidates=candidates_by_page[page_number],
        )
        page_failures = [asdict(failure) for failure in page_evaluation.failures]
        page_state = page_evaluation.state
        for result in page_evaluation.candidate_results:
            candidate_id = str(result.candidate.candidate_id)
            corrected_document: dict[str, object] | None = None
            if result.corrected_candidate is not None:
                try:
                    corrected_document = asdict(
                        _corrected_candidate_version(
                            result.candidate,
                            result.corrected_candidate,
                        )
                    )
                    corrected_versions += 1
                except (KeyError, TypeError, ValueError):
                    correction_failure = {
                        "failure_code": PassBItemFailureCode.CORRECTED_CANDIDATE_INVALID,
                        "field_path": (
                            f"candidate_results[{result.item_index}].corrected_candidate"
                        ),
                        "item_index": result.item_index,
                        "candidate_id": candidate_id,
                        "candidate_version": result.candidate.version,
                        "parameters": {"validation_stage": "candidate_construction"},
                    }
                    page_failures.append(correction_failure)
                    page_state = PassBPageEvaluationState.PARTIAL
            accepted_ids.add(candidate_id)
            disposition_counts[result.disposition.value] += 1
            results.append(
                {
                    "job_id": job_id,
                    "kind": "candidate",
                    "candidate_id": candidate_id,
                    "candidate_version": result.candidate.version,
                    "page_number": page_number,
                    "disposition": result.disposition,
                    "reasons": result.reasons,
                    "corrected_candidate": corrected_document,
                    "response_digest": receipt.response_digest,
                    "attempt_ref": receipt.attempt_id
                    or f"legacy:{receipt.job_id}:{receipt.request_digest}",
                    "item_lineage": {
                        "receipt_job_id": job_id,
                        "response_digest": receipt.response_digest,
                        "item_index": result.item_index,
                    },
                }
            )
        failures.extend(
            {
                "job_id": job_id,
                "page_number": page_number,
                **failure,
                "response_digest": receipt.response_digest,
                "attempt_ref": receipt.attempt_id
                or f"legacy:{receipt.job_id}:{receipt.request_digest}",
            }
            for failure in page_failures
        )
        page_receipts.append(
            {
                "job_id": job_id,
                "page_number": page_number,
                "state": page_state,
                "expected_candidate_count": len(candidates_by_page[page_number]),
                "accepted_candidate_count": len(page_evaluation.candidate_results),
                "failure_count": len(page_failures),
                "page_disposition": page_evaluation.page_disposition,
                "no_methodological_content": page_evaluation.no_methodological_content,
                "response_digest": receipt.response_digest,
                "attempt_ref": receipt.attempt_id
                or f"legacy:{receipt.job_id}:{receipt.request_digest}",
            }
        )

    terminal_ids_after_salvage = base_terminal_ids | accepted_ids
    unresolved_ids = sorted(set(all_candidates) - terminal_ids_after_salvage)
    unresolved_candidates = [
        {
            "candidate_id": candidate_id,
            "candidate_version": all_candidates[candidate_id].version,
            "page_number": all_candidates[candidate_id].locator.page_number,
            "failure_codes": sorted(
                {
                    str(failure["failure_code"])
                    for failure in failures
                    if failure.get("candidate_id") == candidate_id
                }
                or {str(PassBItemFailureCode.CANDIDATE_RESULT_MISSING)}
            ),
        }
        for candidate_id in unresolved_ids
    ]
    _write_json(
        unresolved_output,
        {
            "contract": "guide-pass-b-candidate-recovery-manifest/0.1.0",
            "source_pass_a_evaluation": str(pass_a_evaluation),
            "source_pass_b_evaluation": str(base_pass_b_evaluation),
            "candidate_count": len(unresolved_candidates),
            "candidates": unresolved_candidates,
        },
    )
    _write_json(
        output,
        {
            "prompt_version": "kg-id-guide-pass-b-batched-v0.2.0",
            "evaluation_policy_version": "candidate-granular-v0.1.0",
            "selected_pages": page_numbers,
            "selected_receipts": len(selected_receipts),
            "selected_candidates": len(selected_candidate_ids),
            "accepted_dispositions": len(accepted_ids),
            "newly_salvaged_dispositions": len(accepted_ids - base_terminal_ids),
            "remaining_candidate_ids_without_terminal_verdict": len(unresolved_ids),
            "disposition_counts": disposition_counts,
            "valid_corrected_candidate_versions": corrected_versions,
            "page_state_counts": {
                state.value: sum(receipt["state"] == state for receipt in page_receipts)
                for state in PassBPageEvaluationState
            },
            "page_receipts": page_receipts,
            "item_failures": failures,
            "results": results,
        },
    )


def select_retry_jobs_command(*, job_manifest: Path, evaluation: Path, output: Path) -> None:
    manifest = json.loads(job_manifest.read_text(encoding="utf-8"))
    decision = json.loads(evaluation.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(decision, dict):
        raise ValueError("Retry selection inputs must be JSON objects")
    failed_ids = {
        str(item["job_id"])
        for item in decision.get("integrity_errors", [])
        if isinstance(item, dict) and "job_id" in item
    }
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Original job manifest has no jobs array")
    selected = [job for job in jobs if isinstance(job, dict) and job.get("job_id") in failed_ids]
    if len(selected) != len(failed_ids):
        raise ValueError("Not every failed job exists in the immutable source manifest")
    _write_json(output, {"contract": manifest.get("contract"), "jobs": selected})


def initialize_platform_command(
    *,
    database_url: str,
    pdf_path: Path,
    object_root: Path,
    profile_path: Path,
    qualification_decision_path: Path,
    source_provenance_path: Path,
    output: Path,
) -> None:
    decision = json.loads(qualification_decision_path.read_text(encoding="utf-8"))
    if not isinstance(decision, dict) or decision.get("qualified_development") is not True:
        raise ValueError("A measured development qualification is required before full ingestion")
    profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(profile_data, dict):
        raise ValueError("Execution profile must be a JSON object")
    profile = GuideExecutionProfile(**profile_data)
    provenance = json.loads(source_provenance_path.read_text(encoding="utf-8"))
    if not isinstance(provenance, dict):
        raise ValueError("Source provenance must be a JSON object")
    inspection = inspect_pdf(pdf_path, UUID("019c8c13-9af0-7000-8000-000000000002"))
    if (
        provenance.get("remote_sha256") != inspection.content_digest
        or provenance.get("local_sha256") != inspection.content_digest
        or provenance.get("size_bytes") != inspection.size_bytes
        or provenance.get("page_count") != inspection.page_count
    ):
        raise ValueError("Source provenance does not match the exact admitted PDF bytes")
    engine = sa.create_engine(database_url)
    try:
        ledger = PlatformSourceLedger(engine, LocalFilesystemObjectStore(object_root))
        source = ledger.admit(
            PlatformSourceAdmission(
                None,
                "methodological-practice-guide:id-practice-guide",
                "ID Practice Guide",
                "Methodological practice source",
                "methodological",
                "source-digest-469b9fbe",
                "methodological_practice_guide",
                str(provenance.get("remote_path", "verified-local-custody-receipt")),
                str(provenance.get("acquisition_method", "ordinary-openssh-verified-copy")),
                json.dumps(provenance, ensure_ascii=False, sort_keys=True),
                "application/pdf",
                "platform-methodological",
                "platform-permanent",
                "identity.oleg-owner-curator",
                UUID("019c8c13-9af0-7000-8000-000000000001"),
            ),
            pdf_path.read_bytes(),
        )
        inspection = inspect_pdf(pdf_path, source.source_version_id)
        repository = PracticeGuideRepository(engine)
        guide_id, edition_id = repository.register_guide_edition(
            guide_key="id-practice-guide",
            title="ID Practice Guide",
            edition_label="source-digest-469b9fbe",
            source_artifact_id=source.source_artifact_id,
            source_version_id=source.source_version_id,
            source_digest=source.content_digest,
            page_count=inspection.page_count,
            provenance={
                **provenance,
                "source_digest": source.content_digest,
                "classification": "MethodologicalPracticeGuide",
            },
            actor_identity_id="identity.oleg-owner-curator",
        )
        repository.save_page_manifest(edition_id, inspection.pages)
        qualification_bytes = qualification_decision_path.read_bytes()
        qualification_digest = f"sha256:{hashlib.sha256(qualification_bytes).hexdigest()}"
        profile_id = repository.register_execution_profile(
            profile=profile,
            profile_version="0.1.0",
            qualification_state="qualified_development",
            qualification_evidence_digest=qualification_digest,
        )
        run_id = repository.start_ingestion_run(
            edition_id=edition_id,
            execution_profile_id=profile_id,
            expected_page_count=inspection.page_count,
            pass_a_prompt_version="kg-id-guide-pass-a-v0.1.0",
            pass_b_prompt_version="kg-id-guide-pass-b-batched-v0.2.0",
            validator_version="kg-id-guide-validator-v0.1.0",
            idempotency_key=f"kg-id-01:{source.content_digest}:{profile.fingerprint}",
            actor_identity_id="service.local-qwen-guide-ingestion",
        )
        _write_json(
            output,
            {
                "practice_guide_id": str(guide_id),
                "practice_guide_edition_id": str(edition_id),
                "source_artifact_id": str(source.source_artifact_id),
                "source_version_id": str(source.source_version_id),
                "source_digest": source.content_digest,
                "page_count": inspection.page_count,
                "execution_profile_id": str(profile_id),
                "profile_fingerprint": profile.fingerprint,
                "ingestion_run_id": str(run_id),
                "qualification_evidence_digest": qualification_digest,
            },
        )
    finally:
        engine.dispose()


def _validation_failure_from_document(value: dict[str, object]) -> GuideValidationFailure:
    parameters = value.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("ValidationFailure parameters must be an object")
    return GuideValidationFailure(
        failure_code=str(value["failure_code"]),
        validator_version=str(value["validator_version"]),
        candidate_id=UUID(str(value["candidate_id"])),
        candidate_version=int(str(value["candidate_version"])),
        field_path=str(value["field_path"]),
        blocking=bool(value["blocking"]),
        repairable=bool(value["repairable"]),
        parameters=parameters,
    )


def persist_verified_guidance_command(
    *,
    database_url: str,
    platform_identity_path: Path,
    pass_a_evaluation_path: Path,
    pass_b_evaluation_path: Path,
    output: Path,
) -> None:
    identity = json.loads(platform_identity_path.read_text(encoding="utf-8"))
    pass_a = json.loads(pass_a_evaluation_path.read_text(encoding="utf-8"))
    pass_b = json.loads(pass_b_evaluation_path.read_text(encoding="utf-8"))
    if not all(isinstance(value, dict) for value in (identity, pass_a, pass_b)):
        raise ValueError("Persistence inputs must be JSON objects")
    run_id = UUID(str(identity["ingestion_run_id"]))
    edition_id = UUID(str(identity["practice_guide_edition_id"]))
    source_version_id = UUID(str(identity["source_version_id"]))
    expected_pages = int(identity["page_count"])
    candidate_results = {
        str(result["candidate_id"]): result
        for result in pass_b["results"]
        if result.get("kind") == "candidate"
    }
    page_results = {
        int(result["page_number"]): result
        for result in pass_b["results"]
        if result.get("kind") == "page"
    }
    pass_b_error_jobs = {str(item["job_id"]) for item in pass_b.get("integrity_errors", [])}
    verification_prompt_version = str(pass_b.get("prompt_version", "kg-id-guide-pass-b-v0.1.0"))
    pass_a_error_pages = {
        int(str(item["job_id"]).removeprefix("pass-a-page-"))
        for item in pass_a.get("integrity_errors", [])
    }
    duplicate_failures_by_candidate: dict[UUID, list[GuideValidationFailure]] = {}
    for value in pass_a.get("duplicate_failures", []):
        if not isinstance(value, dict):
            raise ValueError("Duplicate validation result must be an object")
        failure = _validation_failure_from_document(value)
        duplicate_failures_by_candidate.setdefault(failure.candidate_id, []).append(failure)
    engine = sa.create_engine(database_url)
    repository = PracticeGuideRepository(engine)
    receipts: list[GuidePageTerminalReceipt] = []
    published = supported = contradicted = insufficient = 0
    try:
        pages_by_number = {int(page["page_number"]): page for page in pass_a["pages"]}
        for page_number in range(1, expected_pages + 1):
            page_document = pages_by_number.get(page_number)
            page_result: dict[str, object] | None = None
            if page_document is None or page_number in pass_a_error_pages:
                state = GuideTerminalState.MODEL_FAILED
                candidate_count = verified_count = unresolved_count = 0
            else:
                candidates = [
                    _candidate_from_document(value) for value in page_document["candidates"]
                ]
                failures = [
                    _validation_failure_from_document(value)
                    for value in page_document["validation_failures"]
                ]
                for candidate in candidates:
                    failures.extend(duplicate_failures_by_candidate.get(candidate.candidate_id, []))
                failures_by_candidate: dict[UUID, list[GuideValidationFailure]] = {}
                for failure in failures:
                    failures_by_candidate.setdefault(failure.candidate_id, []).append(failure)
                verified_count = unresolved_count = 0
                for candidate in candidates:
                    repository.save_candidate(run_id, candidate)
                    candidate_failures = tuple(
                        failures_by_candidate.get(candidate.candidate_id, [])
                    )
                    repository.save_validation_failures(
                        candidate_failures,
                        validator_identity="service.deterministic-guide-validator",
                    )
                    result = candidate_results.get(str(candidate.candidate_id))
                    job_id = (
                        f"pass-b-page-{page_number:04d}-"
                        f"{candidate.candidate_id}-v{candidate.version}"
                    )
                    if result is None or job_id in pass_b_error_jobs:
                        unresolved_count += 1
                        continue
                    model_disposition = VerificationDisposition(str(result["disposition"]))
                    effective_disposition = model_disposition
                    if model_disposition is VerificationDisposition.SUPPORTED and any(
                        failure.blocking for failure in candidate_failures
                    ):
                        effective_disposition = VerificationDisposition.INSUFFICIENT
                    if effective_disposition is VerificationDisposition.SUPPORTED:
                        supported += 1
                        verified_count += 1
                    elif effective_disposition is VerificationDisposition.CONTRADICTED:
                        contradicted += 1
                        unresolved_count += 1
                    else:
                        insufficient += 1
                        unresolved_count += 1
                    corrected_document = result.get("corrected_candidate")
                    if corrected_document is not None:
                        if not isinstance(corrected_document, dict):
                            raise ValueError("Corrected CandidateVersion must be an object")
                        corrected_candidate = _candidate_from_document(corrected_document)
                        repository.save_candidate(run_id, corrected_candidate)
                        repository.save_validation_failures(
                            (
                                GuideValidationFailure(
                                    GuideFailureCode.CORRECTED_CANDIDATE_REQUIRES_REVALIDATION,
                                    "kg-id-guide-validator-v0.1.0",
                                    corrected_candidate.candidate_id,
                                    corrected_candidate.version,
                                    "candidate",
                                    True,
                                    True,
                                    {
                                        "parent_version": candidate.version,
                                        "required_action": "targeted_pass_b_revalidation",
                                    },
                                ),
                            ),
                            validator_identity="service.deterministic-guide-validator",
                        )
                    verification = GuidanceVerification(
                        verification_id=uuid7(),
                        candidate_id=candidate.candidate_id,
                        candidate_version=candidate.version,
                        disposition=effective_disposition,
                        source_version_id=candidate.source_version_id,
                        locator=candidate.locator,
                        model_profile_fingerprint=candidate.model_profile_fingerprint,
                        verification_prompt_version=verification_prompt_version,
                        result_digest=str(result["response_digest"]),
                        failures=(
                            ()
                            if effective_disposition is VerificationDisposition.SUPPORTED
                            else candidate_failures
                        ),
                        verified_at=datetime.now(UTC),
                    )
                    repository.save_verification(verification)
                    if effective_disposition is VerificationDisposition.SUPPORTED:
                        repository.publish_verified_candidate(
                            edition_id=edition_id,
                            candidate=candidate,
                            verification=verification,
                            publication_decision_ref=(
                                "decision:kg-id-01-owner-authorized-curation"
                            ),
                            curator=GuidanceCuratorAuthority(
                                "human.oleg-owner",
                                True,
                                frozenset({"methodological_guidance.publish"}),
                            ),
                        )
                        published += 1
                candidate_count = len(candidates)
                page_result = page_results.get(page_number)
                summary_job = f"pass-b-page-{page_number:04d}-summary"
                if page_result is None or summary_job in pass_b_error_jobs:
                    state = GuideTerminalState.MODEL_FAILED
                elif (
                    VerificationDisposition(str(page_result["disposition"]))
                    is not VerificationDisposition.SUPPORTED
                ):
                    state = GuideTerminalState.UNRESOLVED
                elif (
                    page_document.get("no_methodological_content") is True
                    and page_result.get("no_methodological_content") is True
                    and candidate_count == 0
                    and str(page_result["disposition"]) == VerificationDisposition.SUPPORTED
                ):
                    state = GuideTerminalState.NO_METHODOLOGICAL_CONTENT
                elif verified_count:
                    state = GuideTerminalState.VERIFIED
                else:
                    state = GuideTerminalState.UNRESOLVED
            receipt_payload = {
                "run_id": str(run_id),
                "source_version_id": str(source_version_id),
                "page": page_number,
                "state": state,
                "candidate_count": candidate_count,
                "verified_count": verified_count,
                "unresolved_count": unresolved_count,
            }
            receipt = GuidePageTerminalReceipt(
                ingestion_run_id=run_id,
                source_version_id=source_version_id,
                page_number=page_number,
                state=state,
                pass_a_attempt_id=(
                    deterministic_uuid(f"runner-attempt:{page_document['attempt_ref']}")
                    if page_document is not None
                    else None
                ),
                pass_b_attempt_id=(
                    deterministic_uuid(f"runner-attempt:{page_result['attempt_ref']}")
                    if page_result is not None
                    else None
                ),
                candidate_count=candidate_count,
                verified_count=verified_count,
                unresolved_count=unresolved_count,
                receipt_digest=digest_of(receipt_payload),
                recorded_at=datetime.now(UTC),
            )
            repository.save_page_receipt(receipt)
            receipts.append(receipt)
        reconciliation = reconcile_page_receipts(run_id, expected_pages, tuple(receipts))
        repository.save_reconciliation(
            reconciliation,
            actor_identity_id="human.oleg-owner-independent-verifier",
        )
        lexical_version_id = repository.rebuild_lexical_projection(edition_id)
        _write_json(
            output,
            {
                "expected_pages": expected_pages,
                "terminal_pages": len(receipts),
                "terminal_state_counts": {
                    state.value: sum(receipt.state is state for receipt in receipts)
                    for state in GuideTerminalState
                },
                "supported_candidates": supported,
                "contradicted_candidates": contradicted,
                "insufficient_candidates": insufficient,
                "published_guidance_units": published,
                "lexical_version_id": str(lexical_version_id),
                "reconciliation_fingerprint": reconciliation.fingerprint,
                "page_reconciliation_complete": reconciliation.complete,
                "production_qualified": False,
            },
        )
    finally:
        engine.dispose()


def _guidance_gateway_invoke(
    gateway: KnowledgeGateway,
    tool: str,
    payload: dict[str, object],
    purpose: str,
) -> GatewayResponse:
    return gateway.invoke(
        GatewayRequest(
            tool,
            GUIDANCE_CONTRACT_VERSION,
            GUIDANCE_SCHEMA_ID,
            GUIDANCE_CONTRACT_VERSION,
            payload,
        ),
        GatewayContext(
            "service.local-qwen-independent-memory-acceptance",
            f"{tool}.invoke",
            purpose,
            uuid7(),
        ),
    )


def prepare_memory_acceptance_command(
    *,
    database_url: str,
    lexical_version_id: UUID,
    output: Path,
    scenarios_output: Path,
) -> None:
    engine = sa.create_engine(database_url)
    try:
        gateway = KnowledgeGateway(
            PostgresKnowledgeQuery(engine),
            PostgresKnowledgeAudit(
                engine,
                service_identity_id="service.local-qwen-independent-memory-acceptance",
            ),
        )
        discovered: dict[tuple[str, int], dict[str, object]] = {}
        for query in SEED_QUERIES:
            response = _guidance_gateway_invoke(
                gateway,
                "knowledge.get_id_guidance",
                {"query": query, "lexical_version_id": lexical_version_id},
                "independent methodological-guidance memory acceptance discovery",
            )
            if response.status is not GatewayStatus.OK:
                continue
            values = response.result.get("guidance")
            if not isinstance(values, list):
                raise ValueError("Guidance discovery result is malformed")
            for value in values:
                if not isinstance(value, dict):
                    raise ValueError("Guidance discovery unit is malformed")
                identity = (str(value["guidance_unit_id"]), int(value["version"]))
                discovered[identity] = value
        if len(discovered) < 25:
            raise ValueError(
                "At least 25 independently retrievable guidance units are required; "
                f"found {len(discovered)}"
            )
        ranked = sorted(
            discovered.items(),
            key=lambda item: (
                str(item[1].get("guidance_kind", "")),
                0 if item[1].get("field_or_element") else 1,
                0 if item[1].get("document_or_form_type") else 1,
                str(item[1].get("topic", "")),
                item[0],
            ),
        )
        selected: list[tuple[tuple[str, int], dict[str, object]]] = []
        by_kind: dict[str, list[tuple[tuple[str, int], dict[str, object]]]] = {}
        for item in ranked:
            by_kind.setdefault(str(item[1].get("guidance_kind", "")), []).append(item)
        while len(selected) < 25 and by_kind:
            for kind in tuple(sorted(by_kind)):
                items = by_kind[kind]
                if items:
                    selected.append(items.pop(0))
                if not items:
                    del by_kind[kind]
                if len(selected) == 25:
                    break
        jobs: list[QwenJob] = []
        scenarios: list[MemoryAcceptanceScenario] = []
        positive_traces: list[GatewayResponse] = []
        for ordinal, ((guidance_id, version), _) in enumerate(selected, start=1):
            trace = _guidance_gateway_invoke(
                gateway,
                "knowledge.trace_guidance",
                {"guidance_unit_id": guidance_id, "version": version},
                "independent methodological-guidance memory acceptance trace",
            )
            job, scenario = positive_memory_job(ordinal=ordinal, trace=trace)
            jobs.append(job)
            scenarios.append(scenario)
            positive_traces.append(trace)
        missing_field = _guidance_gateway_invoke(
            gateway,
            "knowledge.get_field_guidance",
            {
                "document_or_form_type": "synthetic-nonexistent-form",
                "field_or_element": "synthetic-nonexistent-field",
            },
            "negative invented-field memory acceptance",
        )
        missing_trace = _guidance_gateway_invoke(
            gateway,
            "knowledge.trace_guidance",
            {
                "guidance_unit_id": absent_guidance_identity("absent-page-and-unit"),
                "version": 1,
            },
            "negative absent-guidance memory acceptance",
        )
        missing_search = _guidance_gateway_invoke(
            gateway,
            "knowledge.get_id_guidance",
            {
                "query": "syntheticnonexistentguidance",
                "lexical_version_id": lexical_version_id,
            },
            "negative missing-evidence memory acceptance",
        )
        negative_inputs = (
            (MemoryScenarioKind.INVENTED_FIELD, missing_field),
            (MemoryScenarioKind.ABSENT_GUIDANCE, missing_trace),
            (MemoryScenarioKind.EXAMPLE_AS_NORM, positive_traces[0]),
            (MemoryScenarioKind.NORMATIVE_CONFLICT, positive_traces[1]),
            (MemoryScenarioKind.MISSING_EVIDENCE, missing_search),
            (MemoryScenarioKind.AUTHORITY_ESCALATION, positive_traces[2]),
        )
        for offset, (kind, response) in enumerate(negative_inputs, start=1):
            job, scenario = adversarial_memory_job(
                ordinal=offset,
                kind=kind,
                response=response,
            )
            jobs.append(job)
            scenarios.append(scenario)
        write_job_manifest(output, tuple(jobs))
        _write_json(
            scenarios_output,
            {
                "contract": "practice-guide-memory-acceptance/0.1.0",
                "positive_task_count": 25,
                "adversarial_task_count": len(negative_inputs),
                "source": "knowledge_gateway_only",
                "pdf_or_page_images_in_prompt": False,
                "scenarios": [asdict(scenario) for scenario in scenarios],
            },
        )
    finally:
        engine.dispose()


def evaluate_memory_acceptance_command(
    *,
    scenarios_path: Path,
    receipt_paths: tuple[Path, ...],
    output: Path,
) -> None:
    document = json.loads(scenarios_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("scenarios"), list):
        raise ValueError("Memory acceptance scenario manifest is malformed")
    scenarios = {
        str(value["task_id"]): MemoryAcceptanceScenario(
            task_id=str(value["task_id"]),
            kind=MemoryScenarioKind(str(value["kind"])),
            prompt=str(value["prompt"]),
            allowed_citations=tuple(str(item) for item in value["allowed_citations"]),
            expected_grounding_terms=tuple(str(item) for item in value["expected_grounding_terms"]),
            evidence_count=int(value["evidence_count"]),
        )
        for value in document["scenarios"]
        if isinstance(value, dict)
    }
    receipts = {
        receipt.job_id: receipt
        for receipt_path in receipt_paths
        for receipt in load_receipts(receipt_path)
    }
    results: list[dict[str, object]] = []
    for task_id, scenario in scenarios.items():
        receipt = receipts.get(task_id)
        if receipt is None:
            results.append(
                {
                    "task_id": task_id,
                    "valid": False,
                    "failure_codes": ["TERMINAL_RECEIPT_MISSING"],
                }
            )
            continue
        try:
            result = evaluate_memory_response(receipt.response, scenario)
            results.append(asdict(result))
        except (TypeError, ValueError, json.JSONDecodeError):
            results.append(
                {
                    "task_id": task_id,
                    "valid": False,
                    "failure_codes": ["MODEL_RESPONSE_INTEGRITY_FAILED"],
                }
            )
    positive = [
        result for result in results if str(result["task_id"]).startswith("memory-positive-")
    ]
    adversarial = [
        result for result in results if str(result["task_id"]).startswith("memory-negative-")
    ]
    _write_json(
        output,
        {
            "expected_tasks": len(scenarios),
            "terminal_receipts": sum(task_id in receipts for task_id in scenarios),
            "valid_positive_tasks": sum(result.get("valid") is True for result in positive),
            "expected_positive_tasks": len(positive),
            "valid_adversarial_tasks": sum(result.get("valid") is True for result in adversarial),
            "expected_adversarial_tasks": len(adversarial),
            "passed": bool(results) and all(result.get("valid") is True for result in results),
            "source": "knowledge_gateway_only",
            "fresh_model_session_required": True,
            "results": results,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--pdf", required=True, type=Path)
    inspect_parser.add_argument("--source-version-id", required=True, type=UUID)
    inspect_parser.add_argument("--output", required=True, type=Path)
    pass_a_parser = subparsers.add_parser("prepare-pass-a")
    pass_a_parser.add_argument("--pdf", required=True, type=Path)
    pass_a_parser.add_argument("--source-version-id", required=True, type=UUID)
    pass_a_parser.add_argument("--output", required=True, type=Path)
    pass_a_parser.add_argument("--render-root", required=True, type=Path)
    pass_a_parser.add_argument("--pages", required=True, type=_parse_pages)
    pass_a_parser.add_argument("--dpi", type=int, default=144)
    evaluate_parser = subparsers.add_parser("evaluate-pass-a")
    evaluate_parser.add_argument("--pdf", required=True, type=Path)
    evaluate_parser.add_argument("--source-version-id", required=True, type=UUID)
    evaluate_parser.add_argument("--receipts", required=True, type=Path, nargs="+")
    evaluate_parser.add_argument("--render-root", required=True, type=Path)
    evaluate_parser.add_argument("--evaluation-output", required=True, type=Path)
    evaluate_parser.add_argument("--pass-b-output", required=True, type=Path)
    evaluate_parser.add_argument("--profile", required=True, type=Path)
    pass_b_evaluate_parser = subparsers.add_parser("evaluate-pass-b")
    pass_b_evaluate_parser.add_argument("--pass-a-evaluation", required=True, type=Path)
    pass_b_evaluate_parser.add_argument("--receipts", required=True, type=Path, nargs="+")
    pass_b_evaluate_parser.add_argument("--output", required=True, type=Path)
    pass_b_batch_evaluate_parser = subparsers.add_parser("evaluate-pass-b-batched")
    pass_b_batch_evaluate_parser.add_argument("--pass-a-evaluation", required=True, type=Path)
    pass_b_batch_evaluate_parser.add_argument("--receipts", required=True, type=Path, nargs="+")
    pass_b_batch_evaluate_parser.add_argument("--output", required=True, type=Path)
    pass_b_salvage_parser = subparsers.add_parser("salvage-pass-b-batched")
    pass_b_salvage_parser.add_argument("--pass-a-evaluation", required=True, type=Path)
    pass_b_salvage_parser.add_argument("--base-pass-b-evaluation", required=True, type=Path)
    pass_b_salvage_parser.add_argument("--receipts", required=True, type=Path, nargs="+")
    pass_b_salvage_parser.add_argument("--pages", required=True, type=_parse_pages)
    pass_b_salvage_parser.add_argument("--output", required=True, type=Path)
    pass_b_salvage_parser.add_argument("--unresolved-output", required=True, type=Path)
    native_recovery_parser = subparsers.add_parser("prepare-native-first-recovery")
    native_recovery_parser.add_argument("--pdf", required=True, type=Path)
    native_recovery_parser.add_argument("--source-version-id", required=True, type=UUID)
    native_recovery_parser.add_argument("--failed-manifest", required=True, type=Path)
    native_recovery_parser.add_argument("--receipts", required=True, type=Path, nargs="+")
    native_recovery_parser.add_argument("--profile", required=True, type=Path)
    native_recovery_parser.add_argument("--render-root", required=True, type=Path)
    native_recovery_parser.add_argument("--layout-output", required=True, type=Path)
    native_recovery_parser.add_argument("--classification-output", required=True, type=Path)
    native_recovery_parser.add_argument("--source-rows-output", required=True, type=Path)
    native_recovery_parser.add_argument("--semantic-jobs-output", required=True, type=Path)
    native_recovery_parser.add_argument("--native-registry-output", required=True, type=Path)
    native_recovery_parser.add_argument("--native-pass-b-output", required=True, type=Path)
    native_recovery_parser.add_argument("--lineage-output", required=True, type=Path)
    row_evaluate_parser = subparsers.add_parser("evaluate-ntd-row-semantics")
    row_evaluate_parser.add_argument("--pdf", required=True, type=Path)
    row_evaluate_parser.add_argument("--source-version-id", required=True, type=UUID)
    row_evaluate_parser.add_argument("--source-rows", required=True, type=Path)
    row_evaluate_parser.add_argument("--receipts", required=True, type=Path, nargs="+")
    row_evaluate_parser.add_argument("--profile", required=True, type=Path)
    row_evaluate_parser.add_argument("--render-root", required=True, type=Path)
    row_evaluate_parser.add_argument("--evaluation-output", required=True, type=Path)
    row_evaluate_parser.add_argument("--registry-output", required=True, type=Path)
    row_evaluate_parser.add_argument("--pass-b-output", required=True, type=Path)
    recovery_prepare_parser = subparsers.add_parser("prepare-candidate-recovery")
    recovery_prepare_parser.add_argument("--pdf", required=True, type=Path)
    recovery_prepare_parser.add_argument("--source-version-id", required=True, type=UUID)
    recovery_prepare_parser.add_argument("--receipts", required=True, type=Path, nargs="+")
    recovery_prepare_parser.add_argument("--pages", required=True, type=_parse_pages)
    recovery_prepare_parser.add_argument("--qualification-pages", required=True, type=_parse_pages)
    recovery_prepare_parser.add_argument("--render-root", required=True, type=Path)
    recovery_prepare_parser.add_argument("--profile", required=True, type=Path)
    recovery_prepare_parser.add_argument("--salvage-output", required=True, type=Path)
    recovery_prepare_parser.add_argument("--qualification-output", required=True, type=Path)
    recovery_prepare_parser.add_argument("--remaining-output", required=True, type=Path)
    recovery_prepare_parser.add_argument("--salvage-verifier-output", required=True, type=Path)
    recovery_prepare_parser.add_argument("--lineage-output", required=True, type=Path)
    pass_b_recovery_parser = subparsers.add_parser("prepare-pass-b-candidate-recovery")
    pass_b_recovery_parser.add_argument("--pdf", required=True, type=Path)
    pass_b_recovery_parser.add_argument("--source-version-id", required=True, type=UUID)
    pass_b_recovery_parser.add_argument("--pass-a-evaluation", required=True, type=Path)
    pass_b_recovery_parser.add_argument("--unresolved-manifest", required=True, type=Path)
    pass_b_recovery_parser.add_argument("--render-root", required=True, type=Path)
    pass_b_recovery_parser.add_argument("--output", required=True, type=Path)
    pass_b_recovery_parser.add_argument("--registry-output", required=True, type=Path)
    corrected_prepare_parser = subparsers.add_parser("prepare-corrected-reverification")
    corrected_prepare_parser.add_argument("--pdf", required=True, type=Path)
    corrected_prepare_parser.add_argument("--source-version-id", required=True, type=UUID)
    corrected_prepare_parser.add_argument("--pass-b-evaluation", required=True, type=Path)
    corrected_prepare_parser.add_argument("--render-root", required=True, type=Path)
    corrected_prepare_parser.add_argument("--output", required=True, type=Path)
    corrected_prepare_parser.add_argument("--registry-output", required=True, type=Path)
    compact_evaluate_parser = subparsers.add_parser("evaluate-compact-verification")
    compact_evaluate_parser.add_argument("--registry", required=True, type=Path)
    compact_evaluate_parser.add_argument("--receipts", required=True, type=Path, nargs="+")
    compact_evaluate_parser.add_argument("--output", required=True, type=Path)
    region_evaluate_parser = subparsers.add_parser("evaluate-region-recovery")
    region_evaluate_parser.add_argument("--pdf", required=True, type=Path)
    region_evaluate_parser.add_argument("--source-version-id", required=True, type=UUID)
    region_evaluate_parser.add_argument("--lineage", required=True, type=Path)
    region_evaluate_parser.add_argument("--receipts", required=True, type=Path, nargs="+")
    region_evaluate_parser.add_argument("--profile", required=True, type=Path)
    region_evaluate_parser.add_argument("--output", required=True, type=Path)
    region_evaluate_parser.add_argument("--qualification", action="store_true")
    region_reverify_parser = subparsers.add_parser("prepare-region-reverification")
    region_reverify_parser.add_argument("--pdf", required=True, type=Path)
    region_reverify_parser.add_argument("--source-version-id", required=True, type=UUID)
    region_reverify_parser.add_argument(
        "--recovery-evaluations", required=True, type=Path, nargs="+"
    )
    region_reverify_parser.add_argument("--render-root", required=True, type=Path)
    region_reverify_parser.add_argument("--output", required=True, type=Path)
    region_reverify_parser.add_argument("--registry-output", required=True, type=Path)
    reconcile_parser = subparsers.add_parser("reconcile-bounded-recovery")
    reconcile_parser.add_argument("--platform-identity", required=True, type=Path)
    reconcile_parser.add_argument("--pass-a-evaluation", required=True, type=Path)
    reconcile_parser.add_argument("--pass-a-recovery", required=True, type=Path)
    reconcile_parser.add_argument("--pass-b-evaluation", required=True, type=Path)
    reconcile_parser.add_argument("--pass-b-salvage", required=True, type=Path)
    reconcile_parser.add_argument("--compact-evaluations", required=True, type=Path, nargs="+")
    reconcile_parser.add_argument("--corrected-registries", required=True, type=Path, nargs="+")
    reconcile_parser.add_argument("--native-registries", required=True, type=Path, nargs="+")
    reconcile_parser.add_argument("--region-lineage", required=True, type=Path)
    reconcile_parser.add_argument("--region-recovery-evaluations", type=Path, nargs="*", default=())
    reconcile_parser.add_argument("--coverage-output", required=True, type=Path)
    reconcile_parser.add_argument("--gaps-output", required=True, type=Path)
    reconcile_parser.add_argument("--publication-output", required=True, type=Path)
    retry_parser = subparsers.add_parser("select-retry-jobs")
    retry_parser.add_argument("--job-manifest", required=True, type=Path)
    retry_parser.add_argument("--evaluation", required=True, type=Path)
    retry_parser.add_argument("--output", required=True, type=Path)
    initialize_parser = subparsers.add_parser("initialize-platform")
    initialize_parser.add_argument("--database-url", required=True)
    initialize_parser.add_argument("--pdf", required=True, type=Path)
    initialize_parser.add_argument("--object-root", required=True, type=Path)
    initialize_parser.add_argument("--profile", required=True, type=Path)
    initialize_parser.add_argument("--qualification-decision", required=True, type=Path)
    initialize_parser.add_argument("--source-provenance", required=True, type=Path)
    initialize_parser.add_argument("--output", required=True, type=Path)
    persist_parser = subparsers.add_parser("persist-verified-guidance")
    persist_parser.add_argument("--database-url", required=True)
    persist_parser.add_argument("--platform-identity", required=True, type=Path)
    persist_parser.add_argument("--pass-a-evaluation", required=True, type=Path)
    persist_parser.add_argument("--pass-b-evaluation", required=True, type=Path)
    persist_parser.add_argument("--output", required=True, type=Path)
    memory_parser = subparsers.add_parser("prepare-memory-acceptance")
    memory_parser.add_argument("--database-url", required=True)
    memory_parser.add_argument("--lexical-version-id", required=True, type=UUID)
    memory_parser.add_argument("--output", required=True, type=Path)
    memory_parser.add_argument("--scenarios-output", required=True, type=Path)
    memory_evaluate_parser = subparsers.add_parser("evaluate-memory-acceptance")
    memory_evaluate_parser.add_argument("--scenarios", required=True, type=Path)
    memory_evaluate_parser.add_argument("--receipts", required=True, type=Path, nargs="+")
    memory_evaluate_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "inspect":
        inspect_command(args.pdf, args.source_version_id, args.output)
    elif args.command == "prepare-pass-a":
        prepare_pass_a_command(
            pdf_path=args.pdf,
            source_version_id=args.source_version_id,
            output=args.output,
            render_root=args.render_root,
            page_numbers=args.pages,
            dpi=args.dpi,
        )
    elif args.command == "evaluate-pass-a":
        evaluate_pass_a_command(
            pdf_path=args.pdf,
            source_version_id=args.source_version_id,
            receipt_paths=tuple(args.receipts),
            render_root=args.render_root,
            evaluation_output=args.evaluation_output,
            pass_b_output=args.pass_b_output,
            profile_path=args.profile,
        )
    elif args.command == "evaluate-pass-b":
        evaluate_pass_b_command(
            pass_a_evaluation=args.pass_a_evaluation,
            receipt_paths=tuple(args.receipts),
            output=args.output,
        )
    elif args.command == "evaluate-pass-b-batched":
        evaluate_pass_b_batched_command(
            pass_a_evaluation=args.pass_a_evaluation,
            receipt_paths=tuple(args.receipts),
            output=args.output,
        )
    elif args.command == "salvage-pass-b-batched":
        salvage_pass_b_batched_command(
            pass_a_evaluation=args.pass_a_evaluation,
            base_pass_b_evaluation=args.base_pass_b_evaluation,
            receipt_paths=tuple(args.receipts),
            page_numbers=args.pages,
            output=args.output,
            unresolved_output=args.unresolved_output,
        )
    elif args.command == "prepare-native-first-recovery":
        prepare_native_first_recovery_command(
            pdf_path=args.pdf,
            source_version_id=args.source_version_id,
            failed_manifest_path=args.failed_manifest,
            receipt_paths=tuple(args.receipts),
            profile_path=args.profile,
            render_root=args.render_root,
            layout_output=args.layout_output,
            classification_output=args.classification_output,
            source_rows_output=args.source_rows_output,
            semantic_jobs_output=args.semantic_jobs_output,
            native_registry_output=args.native_registry_output,
            native_pass_b_output=args.native_pass_b_output,
            lineage_output=args.lineage_output,
        )
    elif args.command == "evaluate-ntd-row-semantics":
        evaluate_ntd_row_semantics_command(
            pdf_path=args.pdf,
            source_version_id=args.source_version_id,
            source_rows_path=args.source_rows,
            receipt_paths=tuple(args.receipts),
            profile_path=args.profile,
            render_root=args.render_root,
            evaluation_output=args.evaluation_output,
            registry_output=args.registry_output,
            pass_b_output=args.pass_b_output,
        )
    elif args.command == "prepare-candidate-recovery":
        prepare_candidate_recovery_command(
            pdf_path=args.pdf,
            source_version_id=args.source_version_id,
            receipt_paths=tuple(args.receipts),
            page_numbers=args.pages,
            qualification_pages=args.qualification_pages,
            render_root=args.render_root,
            profile_path=args.profile,
            salvage_output=args.salvage_output,
            qualification_output=args.qualification_output,
            remaining_output=args.remaining_output,
            salvage_verifier_output=args.salvage_verifier_output,
            lineage_output=args.lineage_output,
        )
    elif args.command == "prepare-pass-b-candidate-recovery":
        prepare_pass_b_candidate_recovery_command(
            pdf_path=args.pdf,
            source_version_id=args.source_version_id,
            pass_a_evaluation_path=args.pass_a_evaluation,
            unresolved_manifest_path=args.unresolved_manifest,
            render_root=args.render_root,
            output=args.output,
            registry_output=args.registry_output,
        )
    elif args.command == "prepare-corrected-reverification":
        prepare_corrected_reverification_command(
            pdf_path=args.pdf,
            source_version_id=args.source_version_id,
            pass_b_evaluation_path=args.pass_b_evaluation,
            render_root=args.render_root,
            output=args.output,
            registry_output=args.registry_output,
        )
    elif args.command == "evaluate-compact-verification":
        evaluate_compact_verification_command(
            registry_path=args.registry,
            receipt_paths=tuple(args.receipts),
            output=args.output,
        )
    elif args.command == "evaluate-region-recovery":
        evaluate_region_recovery_command(
            pdf_path=args.pdf,
            source_version_id=args.source_version_id,
            lineage_path=args.lineage,
            receipt_paths=tuple(args.receipts),
            profile_path=args.profile,
            output=args.output,
            qualification=args.qualification,
        )
    elif args.command == "prepare-region-reverification":
        prepare_region_reverification_command(
            pdf_path=args.pdf,
            source_version_id=args.source_version_id,
            recovery_evaluation_paths=tuple(args.recovery_evaluations),
            render_root=args.render_root,
            output=args.output,
            registry_output=args.registry_output,
        )
    elif args.command == "reconcile-bounded-recovery":
        reconcile_bounded_recovery_command(
            platform_identity_path=args.platform_identity,
            pass_a_evaluation_path=args.pass_a_evaluation,
            pass_a_recovery_path=args.pass_a_recovery,
            pass_b_evaluation_path=args.pass_b_evaluation,
            pass_b_salvage_path=args.pass_b_salvage,
            compact_evaluation_paths=tuple(args.compact_evaluations),
            corrected_registry_paths=tuple(args.corrected_registries),
            native_registry_paths=tuple(args.native_registries),
            region_lineage_path=args.region_lineage,
            region_recovery_evaluation_paths=tuple(args.region_recovery_evaluations),
            coverage_output=args.coverage_output,
            gaps_output=args.gaps_output,
            publication_output=args.publication_output,
        )
    elif args.command == "select-retry-jobs":
        select_retry_jobs_command(
            job_manifest=args.job_manifest,
            evaluation=args.evaluation,
            output=args.output,
        )
    elif args.command == "initialize-platform":
        initialize_platform_command(
            database_url=args.database_url,
            pdf_path=args.pdf,
            object_root=args.object_root,
            profile_path=args.profile,
            qualification_decision_path=args.qualification_decision,
            source_provenance_path=args.source_provenance,
            output=args.output,
        )
    elif args.command == "persist-verified-guidance":
        persist_verified_guidance_command(
            database_url=args.database_url,
            platform_identity_path=args.platform_identity,
            pass_a_evaluation_path=args.pass_a_evaluation,
            pass_b_evaluation_path=args.pass_b_evaluation,
            output=args.output,
        )
    elif args.command == "prepare-memory-acceptance":
        prepare_memory_acceptance_command(
            database_url=args.database_url,
            lexical_version_id=args.lexical_version_id,
            output=args.output,
            scenarios_output=args.scenarios_output,
        )
    elif args.command == "evaluate-memory-acceptance":
        evaluate_memory_acceptance_command(
            scenarios_path=args.scenarios,
            receipt_paths=tuple(args.receipts),
            output=args.output,
        )


if __name__ == "__main__":
    main()
