"""Resolve the seven exact seed GOST identities through official Rosstandart cards."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa

from asd_kontur.ntd.models import OfficialProvider
from asd_kontur.ntd.official_sources import (
    BoundedOfficialTransport,
    OfficialSourceError,
    RosstandartSpdsClient,
    TransportProfile,
    parse_rosstandart_card,
)
from asd_kontur.ntd.remediation import (
    NtdRemediationRepository,
    load_historical_seed_identities,
    remediation_environment_fingerprint,
)

CARD_BY_IDENTITY = {
    "ru:gost-r:51872": "201cb77e-3cec-42a6-a47e-bad3caac224b",
    "ru:gost-r:58973": "b680e94c-dee5-4618-9d64-69bd8a9388d4",
    "ru:gost-r:59492": "435edb0a-318f-4b52-9af2-fedffefa1ee5",
    "ru:gost-r:70108": "23f0a882-4624-475d-86c0-e4ae8f262177",
    "ru:gost:31937": "150801aa-be38-4abc-98d6-6f0d0aadb977",
    "ru:gost:32755": "19ae0203-a683-4fb8-b17b-f26d7e0ba4d9",
    "ru:gost:32756": "d1aa26d7-7835-4e18-977b-2ffa947c85d3",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--historical-manifest", type=Path, required=True)
    parser.add_argument("--canonical-commit", required=True)
    args = parser.parse_args()
    _require_private_directory(args.receipt_dir)
    identities = {
        value.canonical_stable_identity_key: value
        for value in load_historical_seed_identities(args.historical_manifest)
    }
    if set(CARD_BY_IDENTITY) - set(identities):
        raise ValueError("ROSSTANDART_SEED_CARD_MAP_OUTSIDE_MANIFEST")
    engine = sa.create_engine(args.database_url)
    with engine.connect() as connection:
        database_version = str(connection.scalar(sa.text("SHOW server_version")))
    environment = remediation_environment_fingerprint(
        code_commit=args.canonical_commit,
        lock_digest="sha256:" + hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
        python_version=platform.python_version(),
        database_version=database_version,
    )
    client = RosstandartSpdsClient(
        BoundedOfficialTransport(
            OfficialProvider.ROSSTANDART_FUND,
            profile=TransportProfile.DIRECT,
            timeout_seconds=20,
            max_attempts=2,
            max_response_bytes=4 * 1024 * 1024,
        )
    )
    repository = NtdRemediationRepository(engine)
    results: list[dict[str, object]] = []
    for identity_key, card_id in sorted(CARD_BY_IDENTITY.items()):
        identity = identities[identity_key]
        card_url = f"https://protect.gost.ru/gost/details/{card_id}"
        try:
            card_response = client.fetch_card(card_id)
            card = parse_rosstandart_card(card_response.body)
            card_digest = "sha256:" + hashlib.sha256(card_response.body).hexdigest()
            _assert_card_identity(identity.normalized.normalized_designation, card.designation)
            diagnostic: dict[str, object] = {
                "designation": card.designation,
                "title": card.title,
                "approval_order": card.approval_order,
                "approval_date": card.approval_date.isoformat() if card.approval_date else None,
                "effective_from": card.effective_from.isoformat() if card.effective_from else None,
                "card_response_digest": card_digest,
            }
            try:
                viewer = client.resolve_view_manifest(card_id)
                probe = client.probe_viewer_access(viewer)
                status = probe.status.value
                failure_code = (
                    "ROSSTANDART_VIEWER_INVALID_PLACEHOLDER"
                    if status == "invalid_response"
                    else None
                )
                diagnostic.update(
                    {
                        "viewer_page_denominator": len(viewer.pages),
                        "viewer_manifest_fingerprint": viewer.semantic_fingerprint,
                        "viewer_probe_status": status,
                        "sampled_page_numbers": probe.sampled_page_numbers,
                        "sampled_digests": probe.sampled_digests,
                        "declared_media_types": probe.declared_media_types,
                        "detected_media_types": probe.detected_media_types,
                        "observations": probe.observations,
                    }
                )
                resolution_status = (
                    "official_artifact_unavailable"
                    if failure_code is not None
                    else "official_metadata_only"
                )
            except OfficialSourceError as exc:
                resolution_status = "official_artifact_unavailable"
                failure_code = exc.code
                diagnostic["viewer_error"] = exc.code
            repository.record_identity_resolution(
                identity=identity,
                provider="rosstandart_fund",
                transport_profile="direct",
                official_record_id=card_id,
                official_record_url=card_url,
                official_record_digest=card_digest,
                resolution_status=resolution_status,
                failure_code=failure_code,
                diagnostic=diagnostic,
                environment_fingerprint=environment,
                recorded_at=datetime.now(UTC),
            )
            results.append(
                {
                    "identity": identity_key,
                    "printed_editions": identity.printed_editions,
                    "official_designation": card.designation,
                    "official_title": card.title,
                    "official_record_url": card_url,
                    "official_record_digest": card_digest,
                    "terminal_state": resolution_status,
                    "failure_code": failure_code,
                    "diagnostic": diagnostic,
                }
            )
        except (OfficialSourceError, ValueError) as exc:
            code = exc.code if isinstance(exc, OfficialSourceError) else str(exc)
            repository.record_identity_resolution(
                identity=identity,
                provider="rosstandart_fund",
                transport_profile="direct",
                official_record_id=card_id,
                official_record_url=card_url,
                official_record_digest=None,
                resolution_status="blocked_deterministic_failure",
                failure_code=code,
                diagnostic={"exception_type": type(exc).__name__},
                environment_fingerprint=environment,
                recorded_at=datetime.now(UTC),
            )
            results.append(
                {
                    "identity": identity_key,
                    "printed_editions": identity.printed_editions,
                    "official_record_url": card_url,
                    "terminal_state": "blocked_deterministic_failure",
                    "failure_code": code,
                }
            )
    payload = {
        "schema": "ntd-seed-rosstandart-resolution-v1",
        "logical_manifest_fingerprint": (
            "sha256:071960850be497aa6cff032a64375f9cacacadc9fed1a36b136fddfb862ca4b6"
        ),
        "identity_denominator": 7,
        "environment_fingerprint": environment,
        "results": results,
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.receipt_dir / f"ntd-seed-rosstandart-resolution-v1-{stamp}.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output.chmod(0o600)
    print(
        json.dumps(
            {
                "identity_denominator": 7,
                "statuses": _counts(results),
                "environment_fingerprint": environment,
            },
            sort_keys=True,
        )
    )
    engine.dispose()
    return 0


def _assert_card_identity(expected: str, actual: str) -> None:
    def number(value: str) -> str:
        match = re.search(r"(?i)ГОСТ(?:\s+\u0420)?\s+(\d+)", value)
        return match.group(1) if match is not None else ""

    if not number(expected) or number(expected) != number(actual):
        raise ValueError("ROSSTANDART_CARD_DESIGNATION_CONFLICT")


def _counts(results: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in results:
        state = str(value["terminal_state"])
        counts[state] = counts.get(state, 0) + 1
    return counts


def _require_private_directory(path: Path) -> None:
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError("NTD_EXTERNAL_DIRECTORY_INVALID")
    if path.stat().st_mode & 0o077:
        raise ValueError("NTD_EXTERNAL_DIRECTORY_NOT_PRIVATE")


if __name__ == "__main__":
    raise SystemExit(main())
