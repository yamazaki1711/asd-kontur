# ruff: noqa: RUF001 -- Russian normative critical-token fixtures are intentional.

from __future__ import annotations

import json
import subprocess
import urllib.request
from decimal import Decimal
from uuid import UUID

import pytest

from asd_kontur.document_understanding.native import NativeDocument, NativePage, analyze_page_health
from asd_kontur.ntd.file_processing import inventory_pages
from asd_kontur.ntd.polza import (
    POLZA_ENDPOINT,
    POLZA_MODEL,
    PolzaExtractionError,
    PolzaHttpRequest,
    PolzaHttpResponse,
    PolzaPageRequest,
    PolzaPublicNtdPageExtractor,
    UrllibPolzaTransport,
    polza_profile_version,
    polza_request_digest,
    polza_schema_version,
    resolve_polza_credential,
)

PNG = b"\x89PNG\r\n\x1a\nsynthetic-public-ntd-page"
DIGEST = "sha256:233f3ef7f405bec2d2d352430ad13d84a55ddf20e8af5833d9537485fd3fdb5d"


class FakeTransport:
    def __init__(self, responses: list[PolzaHttpResponse]) -> None:
        self.responses = responses
        self.requests: list[PolzaHttpRequest] = []

    def send(self, request: PolzaHttpRequest) -> PolzaHttpResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def _request(*, classification: str = "public_normative_authority") -> PolzaPageRequest:
    return PolzaPageRequest(
        "ru:sp:543.1325800.2024",
        UUID("10000000-0000-4000-8000-000000000001"),
        UUID("10000000-0000-4000-8000-000000000002"),
        UUID("10000000-0000-4000-8000-000000000003"),
        "1",
        Decimal("595"),
        Decimal("842"),
        DIGEST,
        PNG,
        classification,
    )


def _response(page: PolzaPageRequest) -> PolzaHttpResponse:
    candidate = {
        "document_identity": page.document_identity,
        "edition_identity": str(page.edition_identity),
        "artifact_identity": str(page.artifact_identity),
        "page_identity": str(page.page_identity),
        "printed_page_label": page.printed_page_label,
        "blocks": [
            {
                "region": [0.1, 0.2, 0.9, 0.3],
                "raw_transcription": "1.1 Не допускается ± 5 мм",
                "normalized_transcription": "1.1 Не допускается ± 5 мм",
                "block_type": "clause",
                "hierarchy": {
                    "section": "1",
                    "clause": "1.1",
                    "table": None,
                    "row": None,
                    "column": None,
                },
                "critical_tokens": ["1.1", "Не допускается", "±", "5", "мм"],
                "confidence": 0.99,
                "ambiguity_flags": [],
            }
        ],
        "page_ambiguity_flags": [],
    }
    body = {
        "id": "redacted-provider-request-id",
        "model": POLZA_MODEL,
        "choices": [{"message": {"content": json.dumps(candidate)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    return PolzaHttpResponse(200, (), json.dumps(body).encode(), POLZA_ENDPOINT)


def test_public_page_candidate_is_strict_bounded_and_redacted() -> None:
    page = _request()
    transport = FakeTransport([_response(page)])
    adapter = PolzaPublicNtdPageExtractor(
        transport=transport,
        credential_resolver=lambda _: "unit-secret-never-persist",
        sleeper=lambda _: None,
    )

    result = adapter.extract(page)

    assert result.candidate_manifest["page_identity"] == str(page.page_identity)
    assert result.usage_receipt == {
        "reported": True,
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
    }
    wire = json.loads(transport.requests[0].body)
    assert wire["provider"] == {"allow_fallbacks": False}
    assert wire["temperature"] == 0
    assert "unit-secret-never-persist" not in repr(transport.requests[0])
    assert PNG not in repr(result).encode()
    assert result.request_digest == polza_request_digest(page)


def test_outcome_unknown_timeout_is_not_retried() -> None:
    page = _request()

    class TimeoutTransport:
        def __init__(self) -> None:
            self.calls = 0

        def send(self, request: PolzaHttpRequest) -> PolzaHttpResponse:
            del request
            self.calls += 1
            raise PolzaExtractionError("POLZA_TIMEOUT", retryable=True, outcome_unknown=True)

    transport = TimeoutTransport()
    adapter = PolzaPublicNtdPageExtractor(
        transport=transport,
        credential_resolver=lambda _: "unit-secret-never-persist",
        sleeper=lambda _: None,
    )

    with pytest.raises(PolzaExtractionError, match="POLZA_TIMEOUT"):
        adapter.extract(page)

    assert transport.calls == 1


def test_region_candidate_maps_crop_boxes_back_to_source_page() -> None:
    base = _request()
    page = PolzaPageRequest(
        base.document_identity,
        base.edition_identity,
        base.artifact_identity,
        base.page_identity,
        base.printed_page_label,
        base.source_width_points,
        base.source_height_points,
        base.render_digest,
        base.render_png,
        source_region=(Decimal("0.25"), Decimal("0.20"), Decimal("0.75"), Decimal("0.60")),
    )
    response = _response(page)
    wire = json.loads(response.body)
    structured = json.loads(wire["choices"][0]["message"]["content"])
    structured["input_source_region"] = [0.25, 0.2, 0.75, 0.6]
    wire["choices"][0]["message"]["content"] = json.dumps(structured)
    transport = FakeTransport(
        [PolzaHttpResponse(200, (), json.dumps(wire).encode(), POLZA_ENDPOINT)]
    )
    adapter = PolzaPublicNtdPageExtractor(
        transport=transport,
        credential_resolver=lambda _: "unit-secret-never-persist",
    )

    result = adapter.extract(page)

    assert result.candidate_manifest["blocks"][0]["region"] == [0.3, 0.28, 0.7, 0.32]
    assert polza_profile_version(page) == "polza-public-ntd-region-v0.1"
    assert polza_schema_version(page) == "ntd-raster-region-candidate-v0.1"
    assert result.request_digest != polza_request_digest(base)


def test_rotated_region_candidate_uses_affine_source_coordinates() -> None:
    base = _request()
    render_region = (Decimal("0.08"), Decimal("0.68"), Decimal("0.92"), Decimal("0.80"))
    render_to_source = (
        Decimal("0"),
        Decimal("-0.12"),
        Decimal("0.32"),
        Decimal("0.84"),
        Decimal("0"),
        Decimal("0.08"),
        Decimal("0"),
        Decimal("0"),
        Decimal("1"),
    )
    page = PolzaPageRequest(
        base.document_identity,
        base.edition_identity,
        base.artifact_identity,
        base.page_identity,
        base.printed_page_label,
        base.source_width_points,
        base.source_height_points,
        base.render_digest,
        base.render_png,
        source_region=render_region,
        render_to_source=render_to_source,
    )
    response = _response(page)
    wire = json.loads(response.body)
    structured = json.loads(wire["choices"][0]["message"]["content"])
    structured["input_render_region"] = [0.08, 0.68, 0.92, 0.8]
    wire["choices"][0]["message"]["content"] = json.dumps(structured)
    transport = FakeTransport(
        [PolzaHttpResponse(200, (), json.dumps(wire).encode(), POLZA_ENDPOINT)]
    )
    adapter = PolzaPublicNtdPageExtractor(
        transport=transport,
        credential_resolver=lambda _: "unit-secret-never-persist",
    )

    result = adapter.extract(page)

    assert result.candidate_manifest["blocks"][0]["region"] == pytest.approx(
        [0.284, 0.164, 0.296, 0.836]
    )
    assert polza_profile_version(page) == "polza-public-ntd-rotated-region-v0.1"
    assert polza_schema_version(page) == "ntd-raster-rotated-region-candidate-v0.1"


def test_non_public_data_and_missing_credential_fail_closed() -> None:
    with pytest.raises(ValueError, match="POLZA_NTD_PUBLIC_DATA_ONLY"):
        _request(classification="workspace_project_data")

    adapter = PolzaPublicNtdPageExtractor(credential_resolver=lambda _: None)
    with pytest.raises(PolzaExtractionError, match="POLZA_CREDENTIAL_UNAVAILABLE"):
        adapter.extract(_request())


def test_polza_transport_does_not_inherit_environment_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    captured_handlers: list[object] = []

    def build_opener(*handlers: object) -> object:
        captured_handlers.extend(handlers)
        return object()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)

    UrllibPolzaTransport()

    proxy_handlers = [
        handler for handler in captured_handlers if isinstance(handler, urllib.request.ProxyHandler)
    ]

    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}


def test_polza_keychain_resolver_is_bounded_and_does_not_log_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASD_POLZA_API_KEY", raising=False)
    monkeypatch.setenv("USER", "qualification-owner")
    monkeypatch.setattr("asd_kontur.ntd.polza._is_macos", lambda: True)
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs == {
            "check": False,
            "capture_output": True,
            "text": True,
            "timeout": 5,
        }
        return subprocess.CompletedProcess(command, 0, stdout="keychain-secret\n", stderr="")

    monkeypatch.setattr("asd_kontur.ntd.polza.subprocess.run", run)

    assert resolve_polza_credential("ASD_POLZA_API_KEY") == "keychain-secret"
    assert calls == [
        [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            "qualification-owner",
            "-s",
            "ASD_POLZA_API_KEY",
            "-w",
        ]
    ]


def test_normative_vector_page_routes_to_textual_recovery_without_cad_authority() -> None:
    document_id = UUID("10000000-0000-4000-8000-000000000010")
    health = analyze_page_health(
        document_id=document_id,
        document_version=1,
        page_number=1,
        text="Масштаб 1:100. Условные обозначения",
        image_count=0,
        width_points=Decimal("595"),
        height_points=Decimal("842"),
        rotation_degrees=0,
    )
    document = NativeDocument(
        "application/pdf",
        "pdf",
        "synthetic",
        "1",
        (NativePage(1, Decimal("595"), Decimal("842"), 0, 0, (), health),),
        (),
        "sha256:" + "0" * 64,
    )

    page = inventory_pages(
        document,
        normative_artifact_id=UUID("10000000-0000-4000-8000-000000000011"),
    )[0]

    assert page.kind == "vector"
    assert page.extraction_route == "polza_candidate"
    assert page.terminal_outcome == "failed"
