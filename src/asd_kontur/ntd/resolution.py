"""Bounded exact official-source resolution for an NTD seed manifest."""

from __future__ import annotations

import hashlib
import urllib.parse
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from asd_kontur.domain import uuid7
from asd_kontur.harness.models import digest_of

from .manifest import PracticeGuideNormativeReference, PracticeGuideNtdSeedManifest
from .minstroy import (
    MINSTROY_BASE_URL,
    MINSTROY_CATALOGUE_PROFILE_VERSION,
    MinstroyCatalogueClient,
    OfficialCatalogueError,
)
from .models import (
    AcquisitionReceipt,
    AcquisitionTerminalStatus,
    CatalogueCandidate,
    OfficialCatalogueRecord,
    OfficialHttpMetadata,
)


@dataclass(frozen=True, slots=True)
class ResolvedArtifactBytes:
    official_url: str
    media_type: str
    content: bytes
    content_digest: str
    receipt: AcquisitionReceipt


@dataclass(frozen=True, slots=True)
class IdentityResolution:
    stable_identity_key: str
    normalized_designation: str
    reference_ids: tuple[UUID, ...]
    printed_editions: tuple[str, ...]
    terminal_status: AcquisitionTerminalStatus
    terminal_receipt: AcquisitionReceipt
    catalogue_record: OfficialCatalogueRecord | None
    artifacts: tuple[ResolvedArtifactBytes, ...]
    uncertainty_codes: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        payload = {
            "stable_identity_key": self.stable_identity_key,
            "normalized_designation": self.normalized_designation,
            "reference_ids": self.reference_ids,
            "printed_editions": self.printed_editions,
            "terminal_status": self.terminal_status,
            "terminal_receipt": self.terminal_receipt.fingerprint,
            "catalogue_record_digest": (
                self.catalogue_record.metadata_digest if self.catalogue_record else None
            ),
            "artifact_digests": [artifact.content_digest for artifact in self.artifacts],
            "uncertainty_codes": self.uncertainty_codes,
        }
        return digest_of(payload)


@dataclass(frozen=True, slots=True)
class NtdSeedResolutionReport:
    seed_manifest_fingerprint: str
    client_profile_version: str
    started_at: datetime
    completed_at: datetime
    identities: tuple[IdentityResolution, ...]
    report_fingerprint: str

    @property
    def terminal_count(self) -> int:
        return len(self.identities)

    def safe_receipt(self) -> dict[str, Any]:
        """Serialize lineage without embedding downloaded official bytes."""

        return {
            "seed_manifest_fingerprint": self.seed_manifest_fingerprint,
            "client_profile_version": self.client_profile_version,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "terminal_count": self.terminal_count,
            "identities": [
                {
                    "stable_identity_key": item.stable_identity_key,
                    "normalized_designation": item.normalized_designation,
                    "reference_ids": [str(value) for value in item.reference_ids],
                    "printed_editions": list(item.printed_editions),
                    "terminal_status": item.terminal_status.value,
                    "terminal_receipt": _receipt_dict(item.terminal_receipt),
                    "catalogue_record": (
                        {
                            **asdict(item.catalogue_record),
                            "published_at": (
                                item.catalogue_record.published_at.isoformat()
                                if item.catalogue_record.published_at
                                else None
                            ),
                            "effective_from": (
                                item.catalogue_record.effective_from.isoformat()
                                if item.catalogue_record.effective_from
                                else None
                            ),
                            "effective_to": (
                                item.catalogue_record.effective_to.isoformat()
                                if item.catalogue_record.effective_to
                                else None
                            ),
                        }
                        if item.catalogue_record
                        else None
                    ),
                    "artifacts": [
                        {
                            "official_url": artifact.official_url,
                            "media_type": artifact.media_type,
                            "byte_length": len(artifact.content),
                            "content_digest": artifact.content_digest,
                            "receipt": _receipt_dict(artifact.receipt),
                        }
                        for artifact in item.artifacts
                    ],
                    "uncertainty_codes": list(item.uncertainty_codes),
                    "fingerprint": item.fingerprint,
                }
                for item in self.identities
            ],
            "report_fingerprint": self.report_fingerprint,
        }


def resolve_seed_manifest(
    client: MinstroyCatalogueClient,
    manifest: PracticeGuideNtdSeedManifest,
    *,
    clock: Callable[[], datetime] | None = None,
) -> NtdSeedResolutionReport:
    """Resolve each deduplicated identity once; no recursive cross-reference expansion."""

    now = clock or (lambda: datetime.now(UTC))
    started_at = now()
    by_identity: dict[str, list[PracticeGuideNormativeReference]] = {}
    for reference in manifest.references:
        by_identity.setdefault(reference.normalized.stable_identity_key, []).append(reference)
    resolutions: list[IdentityResolution] = []
    for identity_key in sorted(by_identity):
        references = by_identity[identity_key]
        first = references[0]
        identifier = first.normalized
        reference_ids = tuple(reference.reference_id for reference in references)
        printed_editions = tuple(
            sorted(
                {
                    reference.normalized.printed_edition
                    for reference in references
                    if reference.normalized.printed_edition is not None
                }
            )
        )
        requested_at = now()
        initial_endpoint = _initial_endpoint(identifier.normalized_designation)
        try:
            search = client.search_exact(identifier, title_hint=first.raw_title)
        except OfficialCatalogueError as error:
            status = (
                AcquisitionTerminalStatus.OFFICIAL_ACCESS_BLOCKED
                if error.code in {"OFFICIAL_ACCESS_BLOCKED", "OFFICIAL_HTTP_ERROR"}
                else AcquisitionTerminalStatus.BLOCKED_DETERMINISTIC_FAILURE
            )
            terminal = AcquisitionReceipt(
                receipt_id=uuid7(),
                normalized_query=identifier.normalized_designation,
                official_endpoint=initial_endpoint,
                requested_at=requested_at,
                returned_catalog_ids=(),
                selected_catalog_id=None,
                selection_reason=None,
                rejected_candidates=(),
                artifact_url=None,
                http_metadata=None,
                content_digest=None,
                parser_version=MINSTROY_CATALOGUE_PROFILE_VERSION,
                terminal_status=status,
                failure_code=error.code,
            )
            resolutions.append(
                IdentityResolution(
                    identity_key,
                    identifier.normalized_designation,
                    reference_ids,
                    printed_editions,
                    status,
                    terminal,
                    None,
                    (),
                    (error.code,),
                )
            )
            continue
        candidates = search.candidates
        if not candidates:
            status = AcquisitionTerminalStatus.NOT_FOUND_OFFICIAL
            terminal = _terminal_receipt(
                identifier.normalized_designation,
                search.official_endpoints[-1],
                requested_at,
                candidates,
                status,
                "NO_EXACT_OFFICIAL_RECORD",
                search.responses[-1] if search.responses else None,
            )
            resolutions.append(
                IdentityResolution(
                    identity_key,
                    identifier.normalized_designation,
                    reference_ids,
                    printed_editions,
                    status,
                    terminal,
                    None,
                    (),
                    ("NO_EXACT_OFFICIAL_RECORD",),
                )
            )
            continue
        if len(candidates) != 1:
            status = AcquisitionTerminalStatus.AMBIGUOUS_OFFICIAL_RECORDS
            terminal = _terminal_receipt(
                identifier.normalized_designation,
                search.official_endpoints[-1],
                requested_at,
                candidates,
                status,
                "MULTIPLE_EXACT_OFFICIAL_RECORDS",
                search.responses[-1] if search.responses else None,
            )
            resolutions.append(
                IdentityResolution(
                    identity_key,
                    identifier.normalized_designation,
                    reference_ids,
                    printed_editions,
                    status,
                    terminal,
                    None,
                    (),
                    ("MULTIPLE_EXACT_OFFICIAL_RECORDS",),
                )
            )
            continue
        selected = candidates[0]
        try:
            record = client.fetch_record(selected)
        except OfficialCatalogueError as error:
            status = AcquisitionTerminalStatus.OFFICIAL_ACCESS_BLOCKED
            terminal = _terminal_receipt(
                identifier.normalized_designation,
                selected.catalog_url,
                requested_at,
                candidates,
                status,
                error.code,
                None,
                selected_catalog_id=selected.catalog_id,
            )
            resolutions.append(
                IdentityResolution(
                    identity_key,
                    identifier.normalized_designation,
                    reference_ids,
                    printed_editions,
                    status,
                    terminal,
                    None,
                    (),
                    (error.code,),
                )
            )
            continue
        if not record.artifact_urls:
            status = AcquisitionTerminalStatus.OFFICIAL_METADATA_ONLY
            terminal = _terminal_receipt(
                identifier.normalized_designation,
                record.catalog_url,
                requested_at,
                candidates,
                status,
                "OFFICIAL_CARD_HAS_NO_ARTIFACT",
                record.metadata,
                selected_catalog_id=record.catalog_id,
                content_digest=record.metadata_digest,
            )
            resolutions.append(
                IdentityResolution(
                    identity_key,
                    identifier.normalized_designation,
                    reference_ids,
                    printed_editions,
                    status,
                    terminal,
                    record,
                    (),
                    ("OFFICIAL_CARD_HAS_NO_ARTIFACT",),
                )
            )
            continue
        artifacts: list[ResolvedArtifactBytes] = []
        artifact_failure: OfficialCatalogueError | None = None
        for artifact_url in record.artifact_urls:
            artifact_requested_at = now()
            try:
                response = client.download_artifact(artifact_url)
            except OfficialCatalogueError as error:
                artifact_failure = error
                break
            content_digest = "sha256:" + hashlib.sha256(response.body).hexdigest()
            artifact_receipt = AcquisitionReceipt(
                receipt_id=uuid7(),
                normalized_query=identifier.normalized_designation,
                official_endpoint=artifact_url,
                requested_at=artifact_requested_at,
                returned_catalog_ids=(record.catalog_id,),
                selected_catalog_id=record.catalog_id,
                selection_reason="EXACT_IDENTIFIER_CARD_ARTIFACT",
                rejected_candidates=(),
                artifact_url=artifact_url,
                http_metadata=response.metadata,
                content_digest=content_digest,
                parser_version=MINSTROY_CATALOGUE_PROFILE_VERSION,
                terminal_status=AcquisitionTerminalStatus.RESOLVED_EXACT,
                failure_code=None,
            )
            artifacts.append(
                ResolvedArtifactBytes(
                    artifact_url,
                    response.metadata.content_type or "application/octet-stream",
                    response.body,
                    content_digest,
                    artifact_receipt,
                )
            )
        if artifact_failure is not None:
            status = (
                AcquisitionTerminalStatus.ARTIFACT_INVALID
                if artifact_failure.code == "ARTIFACT_INVALID"
                else AcquisitionTerminalStatus.DOWNLOAD_FAILED
            )
            terminal = _terminal_receipt(
                identifier.normalized_designation,
                record.catalog_url,
                requested_at,
                candidates,
                status,
                artifact_failure.code,
                record.metadata,
                selected_catalog_id=record.catalog_id,
                content_digest=record.metadata_digest,
            )
            resolutions.append(
                IdentityResolution(
                    identity_key,
                    identifier.normalized_designation,
                    reference_ids,
                    printed_editions,
                    status,
                    terminal,
                    record,
                    tuple(artifacts),
                    (artifact_failure.code,),
                )
            )
            continue
        status = AcquisitionTerminalStatus.RESOLVED_EXACT
        terminal = _terminal_receipt(
            identifier.normalized_designation,
            record.catalog_url,
            requested_at,
            candidates,
            status,
            None,
            record.metadata,
            selected_catalog_id=record.catalog_id,
            content_digest=record.metadata_digest,
        )
        resolutions.append(
            IdentityResolution(
                identity_key,
                identifier.normalized_designation,
                reference_ids,
                printed_editions,
                status,
                terminal,
                record,
                tuple(artifacts),
                (),
            )
        )
    completed_at = now()
    report_payload = {
        "seed_manifest_fingerprint": manifest.fingerprint,
        "client_profile_version": MINSTROY_CATALOGUE_PROFILE_VERSION,
        "started_at": started_at,
        "completed_at": completed_at,
        "identities": [item.fingerprint for item in resolutions],
    }
    return NtdSeedResolutionReport(
        manifest.fingerprint,
        MINSTROY_CATALOGUE_PROFILE_VERSION,
        started_at,
        completed_at,
        tuple(resolutions),
        digest_of(report_payload),
    )


def _terminal_receipt(
    normalized_query: str,
    endpoint: str,
    requested_at: datetime,
    candidates: tuple[CatalogueCandidate, ...],
    status: AcquisitionTerminalStatus,
    failure_code: str | None,
    metadata: OfficialHttpMetadata | None,
    *,
    selected_catalog_id: str | None = None,
    content_digest: str | None = None,
) -> AcquisitionReceipt:
    candidate_ids = tuple(str(candidate.catalog_id) for candidate in candidates)
    rejected = tuple(
        {
            "catalog_id": str(candidate.catalog_id),
            "title": str(candidate.title),
            "reason": "NOT_SELECTED_OR_AMBIGUOUS",
        }
        for candidate in candidates
        if str(candidate.catalog_id) != selected_catalog_id
    )
    return AcquisitionReceipt(
        receipt_id=uuid7(),
        normalized_query=normalized_query,
        official_endpoint=urllib.parse.urljoin(f"{MINSTROY_BASE_URL}/", endpoint),
        requested_at=requested_at,
        returned_catalog_ids=candidate_ids,
        selected_catalog_id=selected_catalog_id,
        selection_reason="EXACT_IDENTIFIER_MATCH" if selected_catalog_id else None,
        rejected_candidates=rejected,
        artifact_url=None,
        http_metadata=metadata,
        content_digest=content_digest,
        parser_version=MINSTROY_CATALOGUE_PROFILE_VERSION,
        terminal_status=status,
        failure_code=failure_code,
    )


def _initial_endpoint(normalized_designation: str) -> str:
    return f"{MINSTROY_BASE_URL}/docs/?q={urllib.parse.quote(normalized_designation)}"


def _receipt_dict(receipt: AcquisitionReceipt) -> dict[str, Any]:
    value = asdict(receipt)
    value["receipt_id"] = str(receipt.receipt_id)
    value["requested_at"] = receipt.requested_at.isoformat()
    value["terminal_status"] = receipt.terminal_status.value
    value["previous_receipt_id"] = (
        str(receipt.previous_receipt_id) if receipt.previous_receipt_id else None
    )
    return value
