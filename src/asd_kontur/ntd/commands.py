"""Application commands for bounded NTD seed terminal reconciliation."""

from __future__ import annotations

from datetime import datetime

from .manifest import PracticeGuideNtdSeedManifest
from .models import AcquisitionTerminalStatus
from .postgres import NtdRepository
from .resolution import NtdSeedResolutionReport

_GAP_CODE = {
    AcquisitionTerminalStatus.AMBIGUOUS_OFFICIAL_RECORDS: "identity_ambiguous",
    AcquisitionTerminalStatus.OFFICIAL_METADATA_ONLY: "metadata_only",
    AcquisitionTerminalStatus.OFFICIAL_ARTIFACT_UNAVAILABLE: "official_artifact_unavailable",
    AcquisitionTerminalStatus.OFFICIAL_ACCESS_BLOCKED: "official_access_blocked",
    AcquisitionTerminalStatus.NOT_FOUND_OFFICIAL: "exact_edition_not_found",
    AcquisitionTerminalStatus.EXACT_EDITION_NOT_FOUND: "exact_edition_not_found",
    AcquisitionTerminalStatus.EDITION_CONFLICT: "edition_conflict",
    AcquisitionTerminalStatus.SUPERSESSION_UNRESOLVED: "supersession_unresolved",
    AcquisitionTerminalStatus.DOWNLOAD_FAILED: "official_artifact_unavailable",
    AcquisitionTerminalStatus.ARTIFACT_INVALID: "official_artifact_unavailable",
    AcquisitionTerminalStatus.PARSE_PARTIAL: "parse_partial",
    AcquisitionTerminalStatus.BLOCKED_DETERMINISTIC_FAILURE: "parse_partial",
}


def persist_terminal_gap_report(
    repository: NtdRepository,
    *,
    manifest: PracticeGuideNtdSeedManifest,
    report: NtdSeedResolutionReport,
    created_by_identity_id: str,
    recorded_at: datetime,
) -> tuple[int, int]:
    """Persist only terminal gaps; resolved bytes require the publication command."""

    if report.seed_manifest_fingerprint != manifest.fingerprint:
        raise ValueError("NTD_RESOLUTION_REPORT_MANIFEST_MISMATCH")
    manifest_id, _ = repository.register_seed_manifest(
        manifest,
        created_by_identity_id=created_by_identity_id,
        created_at=recorded_at,
    )
    manifest_version = repository.seed_manifest_version(manifest_id, manifest.fingerprint)
    references = {reference.reference_id: reference for reference in manifest.references}
    gap_count = 0
    decision_count = 0
    for resolution in report.identities:
        if resolution.terminal_status in {
            AcquisitionTerminalStatus.RESOLVED_EXACT,
            AcquisitionTerminalStatus.RESOLVED_SUPERSEDED,
            AcquisitionTerminalStatus.PARSED_VERIFIED,
        }:
            raise ValueError("RESOLVED_IDENTITY_REQUIRES_NTD_PUBLICATION_PIPELINE")
        repository.record_acquisition_receipt(
            resolution.terminal_receipt,
            practice_guide_reference_id=resolution.reference_ids[0],
        )
        gap_code = _GAP_CODE[resolution.terminal_status]
        repository.record_gap(
            stable_identity_key=resolution.stable_identity_key,
            gap_code=gap_code,
            blocker_scope="ntd_seed_identity",
            evidence_refs=(str(resolution.terminal_receipt.receipt_id),),
            recorded_at=recorded_at,
        )
        gap_count += 1
        for reference_id in resolution.reference_ids:
            if reference_id not in references:
                raise ValueError("NTD_RESOLUTION_REFERENCE_LINEAGE_MISMATCH")
            repository.record_reference_resolution(
                reference_id=reference_id,
                acquisition_receipt_id=resolution.terminal_receipt.receipt_id,
                resolution_status=resolution.terminal_status.value,
                decision_reason=resolution.terminal_receipt.failure_code
                or resolution.terminal_status.value,
                uncertainty_codes=resolution.uncertainty_codes,
                decided_at=recorded_at,
            )
            decision_count += 1
        repository.insert_seed_outcome(
            seed_manifest_id=manifest_id,
            seed_manifest_version=manifest_version,
            stable_identity_key=resolution.stable_identity_key,
            normalized_designation=resolution.normalized_designation,
            terminal_status=resolution.terminal_status.value,
            terminal_receipt_id=resolution.terminal_receipt.receipt_id,
            recorded_at=recorded_at,
        )
    return gap_count, decision_count
