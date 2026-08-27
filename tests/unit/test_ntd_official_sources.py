# ruff: noqa: RUF001 -- exact Cyrillic normative designations are test evidence.

from __future__ import annotations

import struct
import zlib
from datetime import UTC, datetime, timedelta

import pytest

from asd_kontur.ntd.identifiers import NormativeDocumentKind, normalize_identifier
from asd_kontur.ntd.models import OfficialHttpMetadata, OfficialProvider
from asd_kontur.ntd.official_sources import (
    NTD_PRIORITY_SEARCH_SOURCES,
    OFFICIAL_NTD_RESOLUTION_ORDER,
    GovernmentResolutionClient,
    OfficialSourceError,
    OfficialSourceResponse,
    RosstandartPageDescriptor,
    RosstandartSpdsClient,
    parse_rosstandart_card,
    parse_rosstandart_viewer_manifest,
    validate_rosstandart_page_image,
)


class _Transport:
    provider = OfficialProvider.ROSSTANDART_FUND

    def __init__(self, pages: dict[str, bytes]) -> None:
        self.pages = pages

    def get(self, url: str) -> OfficialSourceResponse:
        body = self.pages[url]
        return OfficialSourceResponse(
            OfficialHttpMetadata(url, url, 200, "text/html", None, None, len(body), _now()),
            body,
        )


def _now() -> datetime:
    return datetime(2026, 8, 26, tzinfo=UTC)


def _record(catalog_id: str, designation: str, title: str, status: str) -> str:
    return f"""
    <tr><td><a href="/gost/details/{catalog_id}"><span>{designation}</span></a></td>
    <td>{title}</td><td>10</td><td>{status}</td></tr>
    """


def _png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(payload, zlib.crc32(kind)) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    rows = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def test_government_resolution_identity_requires_exact_authority_date_and_number() -> None:
    value = normalize_identifier(
        "Постановление Правительства Российской Федерации от 16.02.2008 № 87"
    )
    assert value.document_kind is NormativeDocumentKind.GOVERNMENT_RESOLUTION
    assert value.stable_identity_key == "ru:government:resolution:16.02.2008:87"
    assert value.printed_edition == "16.02.2008"
    with pytest.raises(ValueError, match="REQUIRES_EXACT_DATE"):
        normalize_identifier("ПП РФ № 87")


def test_ntd_search_starts_with_minstroy_and_reference_sources_cannot_be_authority() -> None:
    assert OFFICIAL_NTD_RESOLUTION_ORDER == (
        OfficialProvider.MINSTROY_CATALOGUE,
        OfficialProvider.ROSSTANDART_FUND,
    )
    assert NTD_PRIORITY_SEARCH_SOURCES == (
        (1, "https://minstroyrf.gov.ru/docs/", "official_authority_candidate"),
        (2, "https://docs.cntd.ru/", "discovery_reference_only"),
        (3, "https://meganorm.ru/", "discovery_reference_only"),
    )


def test_gost_spds_identifier_has_document_identity_separate_from_edition() -> None:
    old = normalize_identifier("ГОСТ Р 21.101-2020")
    current = normalize_identifier("ГОСТ Р 21.101-2026")
    assert old.stable_identity_key == current.stable_identity_key == "ru:gost-r:21.101"
    assert (old.printed_edition, current.printed_edition) == ("2020", "2026")


def test_historical_two_digit_gost_edition_is_preserved_without_century_inference() -> None:
    value = normalize_identifier("ГОСТ 21.112-87")
    assert value.stable_identity_key == "ru:gost:21.112"
    assert value.normalized_designation == "ГОСТ 21.112-87"
    assert value.printed_edition == "87"


def test_spds_manifest_reconciles_official_denominator_and_preserves_editions() -> None:
    base = (
        "https://protect.gost.ru/gost?year=0&month=0&search="
        "%D0%A1%D0%B8%D1%81%D1%82%D0%B5%D0%BC%D0%B0+%D0%BF%D1%80%D0%BE%D0%B5%D0%BA%D1%82%D0%BD%D0%BE%D0%B9+"
        "%D0%B4%D0%BE%D0%BA%D1%83%D0%BC%D0%B5%D0%BD%D1%82%D0%B0%D1%86%D0%B8%D0%B8+%D0%B4%D0%BB%D1%8F+"
        "%D1%81%D1%82%D1%80%D0%BE%D0%B8%D1%82%D0%B5%D0%BB%D1%8C%D1%81%D1%82%D0%B2%D0%B0"
    )
    ids = [f"00000000-0000-0000-0000-{index:012d}" for index in range(1, 22)]
    first_records = "".join(
        _record(
            item, f"ГОСТ Р 21.101-{2020 if index == 1 else 2026}", f"title {index}", "Действует"
        )
        for index, item in enumerate(ids[:20], start=1)
    )
    second_record = _record(ids[20], "ГОСТ Р 21.501-2018", "title 21", "Заменен")
    pages = {
        base: f"<p>Найдено: <strong>21</strong></p><table>{first_records}</table>".encode(),
        f"{base}&page=2": (
            f"<p>Найдено: <strong>21</strong></p><table>{second_record}</table>"
        ).encode(),
    }
    manifest = RosstandartSpdsClient(_Transport(pages)).build_manifest(created_at=_now())
    assert manifest.denominator == 21
    assert len(manifest.members) == 21
    assert manifest.members[0].ordinal == 1
    assert {
        member.stable_identity_key for member in manifest.members if "21.101" in member.designation
    } == {"ru:gost-r:21.101"}
    later = RosstandartSpdsClient(_Transport(pages)).build_manifest(
        created_at=_now() + timedelta(days=1)
    )
    assert later.manifest_id == manifest.manifest_id
    assert later.fingerprint == manifest.fingerprint


def test_spds_manifest_fails_closed_on_denominator_mismatch() -> None:
    base = (
        "https://protect.gost.ru/gost?year=0&month=0&search="
        "%D0%A1%D0%B8%D1%81%D1%82%D0%B5%D0%BC%D0%B0+%D0%BF%D1%80%D0%BE%D0%B5%D0%BA%D1%82%D0%BD%D0%BE%D0%B9+"
        "%D0%B4%D0%BE%D0%BA%D1%83%D0%BC%D0%B5%D0%BD%D1%82%D0%B0%D1%86%D0%B8%D0%B8+%D0%B4%D0%BB%D1%8F+"
        "%D1%81%D1%82%D1%80%D0%BE%D0%B8%D1%82%D0%B5%D0%BB%D1%8C%D1%81%D1%82%D0%B2%D0%B0"
    )
    pages = {
        base: b"<p>\xd0\x9d\xd0\xb0\xd0\xb9\xd0\xb4\xd0\xb5\xd0\xbd\xd0\xbe: <strong>1</strong></p>"
    }
    with pytest.raises(OfficialSourceError, match="Official denominator 1"):
        RosstandartSpdsClient(_Transport(pages)).build_manifest(created_at=_now())


def test_lost_force_in_rf_is_a_terminal_catalog_state_not_unknown() -> None:
    base = (
        "https://protect.gost.ru/gost?year=0&month=0&search="
        "%D0%A1%D0%B8%D1%81%D1%82%D0%B5%D0%BC%D0%B0+%D0%BF%D1%80%D0%BE%D0%B5%D0%BA%D1%82%D0%BD%D0%BE%D0%B9+"
        "%D0%B4%D0%BE%D0%BA%D1%83%D0%BC%D0%B5%D0%BD%D1%82%D0%B0%D1%86%D0%B8%D0%B8+%D0%B4%D0%BB%D1%8F+"
        "%D1%81%D1%82%D1%80%D0%BE%D0%B8%D1%82%D0%B5%D0%BB%D1%8C%D1%81%D1%82%D0%B2%D0%B0"
    )
    record = _record(
        "00000000-0000-0000-0000-000000000001",
        "ГОСТ 21.001-2013",
        "title",
        "⊘ Утратил силу в РФ",
    )
    manifest = RosstandartSpdsClient(
        _Transport({base: f"<p>Найдено: <strong>1</strong></p><table>{record}</table>".encode()})
    ).build_manifest(created_at=_now())
    assert manifest.members[0].status.value == "not_effective_in_rf"


def test_official_viewer_accepts_strict_png_despite_declared_jpeg() -> None:
    catalog_id = "17bc12e8-6579-4145-b141-56855e772e7f"
    manifest_url = f"https://protect.gost.ru/api/docview/gostdoc/{catalog_id}/pages"
    manifest_body = b'{"token":"0123456789abcdef","pages":[{"n":1,"w":2,"h":3}]}'
    manifest = parse_rosstandart_viewer_manifest(
        catalog_id,
        OfficialSourceResponse(
            OfficialHttpMetadata(
                manifest_url,
                manifest_url,
                200,
                "application/json",
                None,
                None,
                len(manifest_body),
                _now(),
            ),
            manifest_body,
        ),
    )
    page_url = "https://protect.gost.ru/api/docview/img/redacted/1"
    body = _png(2, 3)
    validated = validate_rosstandart_page_image(
        catalog_id=catalog_id,
        descriptor=RosstandartPageDescriptor(1, 2, 3),
        total_pages=1,
        response=OfficialSourceResponse(
            OfficialHttpMetadata(
                page_url, page_url, 200, "image/jpeg", None, None, len(body), _now()
            ),
            body,
        ),
    )
    assert manifest.semantic_fingerprint.startswith("sha256:")
    assert validated.detected_media_type == "image/png"
    assert validated.validation_observations == ("DECLARED_DETECTED_MIME_MISMATCH",)


def test_official_viewer_quarantines_png_with_trailing_payload() -> None:
    body = _png(2, 3) + b"embedded-payload"
    url = "https://protect.gost.ru/api/docview/img/redacted/1"
    with pytest.raises(OfficialSourceError, match="trailing payload") as error:
        validate_rosstandart_page_image(
            catalog_id="17bc12e8-6579-4145-b141-56855e772e7f",
            descriptor=RosstandartPageDescriptor(1, 2, 3),
            total_pages=1,
            response=OfficialSourceResponse(
                OfficialHttpMetadata(url, url, 200, "image/jpeg", None, None, len(body), _now()),
                body,
            ),
        )
    assert error.value.code == "OFFICIAL_INVALID_BYTES"


def test_official_viewer_repeated_wrong_geometry_is_invalid_placeholder() -> None:
    catalog_id = "17bc12e8-6579-4145-b141-56855e772e7f"
    manifest_url = f"https://protect.gost.ru/api/docview/gostdoc/{catalog_id}/pages"
    token = "0123456789abcdef"
    page_body = _png(4, 3)

    class ViewerTransport:
        provider = OfficialProvider.ROSSTANDART_FUND

        def get(self, url: str) -> OfficialSourceResponse:
            if url == manifest_url:
                body = (
                    b'{"token":"0123456789abcdef","pages":['
                    b'{"n":1,"w":2,"h":3},{"n":2,"w":2,"h":3}]}'
                )
                media_type = "application/json"
            else:
                assert url in {
                    f"https://protect.gost.ru/api/docview/img/{token}/1",
                    f"https://protect.gost.ru/api/docview/img/{token}/2",
                }
                body = page_body
                media_type = "image/jpeg"
            return OfficialSourceResponse(
                OfficialHttpMetadata(url, url, 200, media_type, None, None, len(body), _now()),
                body,
            )

    client = RosstandartSpdsClient(ViewerTransport())
    probe = client.probe_viewer_access(client.resolve_view_manifest(catalog_id))
    assert probe.status.value == "invalid_response"
    assert probe.sampled_page_numbers == (1, 2)
    assert "REPEATED_VIEWER_PLACEHOLDER" in probe.observations


def test_official_viewer_empty_page_manifest_is_artifact_unavailable() -> None:
    catalog_id = "17bc12e8-6579-4145-b141-56855e772e7f"
    url = f"https://protect.gost.ru/api/docview/gostdoc/{catalog_id}/pages"
    body = b'{"token":"0123456789abcdef","pages":[]}'
    with pytest.raises(OfficialSourceError, match="no viewer page") as error:
        parse_rosstandart_viewer_manifest(
            catalog_id,
            OfficialSourceResponse(
                OfficialHttpMetadata(
                    url, url, 200, "application/json", None, None, len(body), _now()
                ),
                body,
            ),
        )
    assert error.value.code == "OFFICIAL_ARTIFACT_UNAVAILABLE"


def test_provider_clients_reject_cross_provider_transport() -> None:
    with pytest.raises(ValueError, match="Government client"):
        GovernmentResolutionClient(_Transport({}))


def test_rosstandart_card_parses_exact_scope_dates_and_replacement() -> None:
    card = b"""
    <span class="text-xs tracking-wider">Designation</span><p>ignored</p>
    """.replace(b"Designation", "Обозначение".encode())
    card += (
        """
        <span class="tracking-wider">Заглавие на русском языке</span>
        <p>Система проектной документации для строительства. Общие положения</p>
        <span class="tracking-wider">Номер приказа</span><p>1762-ст</p>
        <span class="tracking-wider">Дата приказа</span><p>10.12.2021</p>
        <span class="tracking-wider">Дата введения в действие</span><p>01.09.2022</p>
        <span class="tracking-wider">Область применения</span><p>Точный scope</p>
        <span class="tracking-wider">Обозначение заменяемого(ых)</span><p>-</p>
        <span class="tracking-wider">Обозначение заменяющего</span><p>ГОСТ Р 21.001-2030</p>
        """
    ).encode()
    metadata = parse_rosstandart_card(card)
    assert metadata.designation == "ignored"
    assert metadata.approval_order == "1762-ст"
    assert metadata.approval_date.isoformat() == "2021-12-10"
    assert metadata.effective_from.isoformat() == "2022-09-01"
    assert metadata.scope_text == "Точный scope"
    assert metadata.replaces_designation is None
    assert metadata.replaced_by_designation == "ГОСТ Р 21.001-2030"
