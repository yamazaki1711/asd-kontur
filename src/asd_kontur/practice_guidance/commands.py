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
    GuidanceCandidateVersion,
    GuidanceCuratorAuthority,
    GuidanceKind,
    GuidanceVerification,
    GuideExecutionProfile,
    GuideLocator,
    GuidePageTerminalReceipt,
    GuideTerminalState,
    GuideValidationFailure,
    VerificationDisposition,
    reconcile_page_receipts,
)
from .pipeline import (
    QwenJob,
    candidate_to_wire,
    load_receipts,
    parse_pass_a,
    parse_pass_b,
    parse_pass_b_batch,
    pass_a_job,
    pass_b_batch_job,
    render_page,
    write_job_manifest,
)
from .postgres import PracticeGuideRepository
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
