from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from asd_kontur.ntd.identifiers import normalize_identifier
from asd_kontur.ntd.manifest import (
    PracticeGuideNormativeReference,
    PracticeGuideNtdSeedManifest,
)
from asd_kontur.ntd.minstroy import (
    MINSTROY_BASE_URL,
    MinstroyCatalogueClient,
    OfficialCatalogueError,
    OfficialResponse,
)
from asd_kontur.ntd.models import AcquisitionTerminalStatus, OfficialHttpMetadata
from asd_kontur.ntd.resolution import resolve_seed_manifest


class FakeOfficialTransport:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str) -> OfficialResponse:
        self.urls.append(url)
        if "/docs/419099/" in url:
            body = """<!doctype html><html><h1>СП 543.1325800.2024 synthetic title</h1>
            <div>Опубликовано: 27 декабря 2024 Минстрой</div>
            <a href='/upload/sp543.pdf'>Download</a>
            <a href='/upload/appendix.zip'>Download attachment</a></html>""".encode()
            content_type = "text/html"
        elif "/upload/sp543.pdf" in url:
            body = b"%PDF-1.7\nsynthetic"
            content_type = "application/pdf"
        else:
            body = """<!doctype html><html><a href='/docs/419099/'>
            СП 543.1325800.2024 synthetic title</a></html>""".encode()
            content_type = "text/html"
        return OfficialResponse(
            OfficialHttpMetadata(
                request_url=url,
                final_url=url,
                status_code=200,
                content_type=content_type,
                etag='"synthetic"',
                last_modified="Tue, 25 Aug 2026 00:00:00 GMT",
                byte_length=len(body),
                retrieved_at=datetime(2026, 8, 25, tzinfo=UTC),
            ),
            body,
        )


def test_exact_official_search_card_and_multiple_attachments() -> None:
    transport = FakeOfficialTransport()
    client = MinstroyCatalogueClient(transport, max_search_pages=1)
    identifier = normalize_identifier("СП 543.1325800.2024")

    search = client.search_exact(identifier)

    assert [candidate.catalog_id for candidate in search.candidates] == ["419099"]
    record = client.fetch_record(search.candidates[0])
    assert record.catalog_url == f"{MINSTROY_BASE_URL}/docs/419099/"
    assert record.metadata_digest.startswith("sha256:")
    assert record.artifact_urls == (
        f"{MINSTROY_BASE_URL}/upload/appendix.zip",
        f"{MINSTROY_BASE_URL}/upload/sp543.pdf",
    )
    artifact = client.download_artifact(f"{MINSTROY_BASE_URL}/upload/sp543.pdf")
    assert artifact.body.startswith(b"%PDF-")
    assert all(url.startswith(MINSTROY_BASE_URL) for url in transport.urls)


def test_download_rejects_mismatched_pdf_signature() -> None:
    class InvalidPdfTransport(FakeOfficialTransport):
        def get(self, url: str) -> OfficialResponse:
            response = super().get(url)
            if url.endswith(".pdf"):
                return OfficialResponse(response.metadata, b"not-a-pdf")
            return response

    client = MinstroyCatalogueClient(InvalidPdfTransport())
    with pytest.raises(OfficialCatalogueError, match="PDF signature") as error:
        client.download_artifact(f"{MINSTROY_BASE_URL}/upload/sp543.pdf")
    assert error.value.code == "ARTIFACT_INVALID"


def test_client_rejects_non_official_endpoint() -> None:
    with pytest.raises(OfficialCatalogueError) as error:
        MinstroyCatalogueClient(FakeOfficialTransport(), base_url="https://example.invalid")
    assert error.value.code == "OFFICIAL_ENDPOINT_NOT_ALLOWED"


def _one_identity_manifest() -> PracticeGuideNtdSeedManifest:
    identifier = normalize_identifier("СП 543.1325800.2024")
    reference = PracticeGuideNormativeReference(
        reference_id=UUID("26cdb5e5-a3f3-4a90-888e-76a15dd5fe55"),
        practice_guide_edition_id=UUID("50891ccf-8dc7-4efb-91df-2c5811d57814"),
        source_version_id=UUID("c068cffd-35dc-4437-9078-6f8262498929"),
        pdf_page=16,
        region=(0.1, 0.1, 0.9, 0.2),
        occurrence_ordinal=1,
        raw_designation=identifier.raw,
        raw_title="synthetic title",
        raw_context="synthetic context",
        normalized=identifier,
        extraction_method="native_pdf_three_column_row_v0.1",
        extraction_receipt_digest="sha256:" + "a" * 64,
        source_fragment_digest="sha256:" + "b" * 64,
    )
    return PracticeGuideNtdSeedManifest(
        "synthetic-seed-v0.1",
        reference.practice_guide_edition_id,
        reference.source_version_id,
        (reference,),
        (identifier.stable_identity_key,),
        ((15, 0), (16, 1), (17, 0), (18, 0), (19, 0)),
        "sha256:" + "c" * 64,
    )


def test_seed_resolution_has_one_terminal_outcome_per_identity() -> None:
    report = resolve_seed_manifest(
        MinstroyCatalogueClient(FakeOfficialTransport(), max_search_pages=1),
        _one_identity_manifest(),
    )
    assert report.terminal_count == 1
    assert report.identities[0].terminal_status is AcquisitionTerminalStatus.RESOLVED_EXACT
    assert len(report.identities[0].artifacts) == 2
    assert report.report_fingerprint.startswith("sha256:")


def test_seed_resolution_terminalizes_unavailable_official_endpoint() -> None:
    class BlockedTransport:
        def get(self, url: str) -> OfficialResponse:
            del url
            raise OfficialCatalogueError("OFFICIAL_ACCESS_BLOCKED", "synthetic timeout")

    report = resolve_seed_manifest(
        MinstroyCatalogueClient(BlockedTransport(), max_search_pages=1),
        _one_identity_manifest(),
    )
    resolution = report.identities[0]
    assert resolution.terminal_status is AcquisitionTerminalStatus.OFFICIAL_ACCESS_BLOCKED
    assert resolution.catalogue_record is None
    assert resolution.artifacts == ()
