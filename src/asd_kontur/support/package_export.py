"""Deterministic, editable export of a formed ID package.

The archive is intentionally a delivery candidate: it contains the current
register first, the available generated/finalized documents in package order,
and a separate missing-items schedule.  It never fabricates a document,
signature, field fact, or finalization state.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Callable, Iterable, Mapping
from typing import Any

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def build_editable_id_package_archive(
    *,
    package: Mapping[str, Any],
    register_manifest: Mapping[str, Any],
    memberships: Iterable[Mapping[str, Any]],
    read_object: Callable[[str], bytes],
) -> bytes:
    """Build a register-first ZIP from the exact current package version."""

    members = sorted((dict(item) for item in memberships), key=lambda item: int(item["ordinal"]))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        _write(archive, "01_register.csv", _register_csv(register_manifest))
        _write(archive, "00_package_status.txt", _status_text(package, members))
        missing: list[dict[str, str]] = []
        for member in members:
            if str(member.get("role")) == "register":
                continue
            object_key = member.get("object_reference")
            state = _membership_state(member)
            if not object_key:
                missing.append(
                    {
                        "ordinal": str(member.get("ordinal", "")),
                        "role": str(member.get("role", "")),
                        "state": state,
                        "blockers": ";".join(str(item) for item in member.get("blocker_codes", [])),
                    }
                )
                continue
            extension = _extension(str(member.get("format", "")))
            role = _safe_component(str(member.get("role", "document")))
            suffix = "finalized" if member.get("finalized_document_id") else "candidate"
            name = f"{int(member['ordinal']):02d}_{role}_{suffix}.{extension}"
            _write(archive, name, read_object(str(object_key)))
        _write(archive, "99_missing_or_blocked_items.csv", _missing_csv(missing))
    return output.getvalue()


def _register_csv(manifest: Mapping[str, Any]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=("ordinal", "role", "state", "copies", "basis"))
    writer.writeheader()
    for item in manifest.get("documents", []):
        if not isinstance(item, Mapping):
            continue
        writer.writerow(
            {
                "ordinal": item.get("ordinal", ""),
                "role": item.get("role", ""),
                "state": item.get("state", ""),
                "copies": item.get("copies", ""),
                "basis": ";".join(str(value) for value in item.get("evidence_refs", [])),
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _missing_csv(rows: Iterable[Mapping[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=("ordinal", "role", "state", "blockers"))
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _status_text(package: Mapping[str, Any], members: Iterable[Mapping[str, Any]]) -> bytes:
    finalized = sum(1 for item in members if item.get("finalized_document_id"))
    generated = sum(1 for item in members if item.get("generated_candidate_id"))
    lines = (
        f"Package ID: {package.get('id_package_id', '')}",
        f"Version: {package.get('version', '')}",
        "Authority: current package is an evidence-bound delivery candidate.",
        f"Generated candidates: {generated}",
        f"Finalized documents: {finalized}",
        "Missing or blocked requirements are listed in 99_missing_or_blocked_items.csv.",
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _write(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, payload)


def _membership_state(member: Mapping[str, Any]) -> str:
    if member.get("finalized_document_id"):
        return "finalized"
    if member.get("generated_candidate_id"):
        return "generated_candidate"
    return str(member.get("state", "missing"))


def _extension(value: str) -> str:
    return {"DOCX": "docx", "PDF_OVERLAY": "pdf", "PDF": "pdf"}.get(value.upper(), "bin")


def _safe_component(value: str) -> str:
    return _SAFE_NAME.sub("-", value).strip("-") or "document"
