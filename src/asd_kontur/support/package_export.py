# ruff: noqa: E501, RUF001
"""Deterministic, editable export of a formed ID package.

The archive is intentionally a delivery candidate: it contains the current
register first, the available generated/finalized documents in package order,
and a separate missing-items schedule.  It never fabricates a document,
signature, field fact, or finalization state.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from xml.sax.saxutils import escape

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

_REGISTER_ROLE_LABELS = {
    "support.aosr": "Акт освидетельствования скрытых работ",
    "support.executive-scheme": "Исполнительная схема",
    "support.material-quality": "Документ о качестве материалов",
    "support.control-attachment": "Приложение контрольных материалов",
}

_REGISTER_STATE_LABELS = {
    "missing": "Отсутствует",
    "blocked": "Заблокирован",
    "generated_candidate": "Подготовлен кандидат",
    "finalized": "Финализирован",
}


def build_editable_id_package_archive(
    *,
    package: Mapping[str, Any],
    register_manifest: Mapping[str, Any],
    memberships: Iterable[Mapping[str, Any]],
    field_resolutions: Iterable[Mapping[str, Any]],
    read_object: Callable[[str], bytes],
    consistency: Mapping[str, Any] | None = None,
) -> bytes:
    """Build a register-first ZIP from the exact current package version.

    Field resolution is exported separately from document membership.  A
    generated document candidate must not hide a material field which is
    unavailable, conflicted, or only a candidate observation.
    """

    members = sorted((dict(item) for item in memberships), key=lambda item: int(item["ordinal"]))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        # The register is an editable document and intentionally occupies the
        # first position in the archive.  The CSV is retained as a convenient
        # tabular import/export projection; it is not the package register's
        # only representation.
        _write(archive, "01_register_candidate.docx", _register_docx(package, register_manifest))
        _write(archive, "01_register.csv", _register_csv(register_manifest))
        missing: list[dict[str, str]] = []
        manifest_members: list[dict[str, object]] = []
        for member in members:
            if str(member.get("role")) == "register":
                manifest_members.append(_manifest_member(member, state="register"))
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
                manifest_members.append(_manifest_member(member, state=state))
                continue
            extension = _extension(str(member.get("format", "")))
            role = _safe_component(str(member.get("role", "document")))
            suffix = "finalized" if member.get("finalized_document_id") else "candidate"
            name = f"{int(member['ordinal']):02d}_{role}_{suffix}.{extension}"
            payload = read_object(str(object_key))
            _write(archive, name, payload)
            representation_entries: list[dict[str, str]] = []
            for representation in member.get("editable_representations", []):
                if not isinstance(representation, Mapping):
                    continue
                representation_key = representation.get("object_reference")
                if not representation_key or str(representation_key) == str(object_key):
                    continue
                representation_format = str(representation.get("format", ""))
                if representation_format != "DOCX":
                    continue
                representation_name = f"{int(member['ordinal']):02d}_{role}_editable.docx"
                representation_payload = read_object(str(representation_key))
                _write(archive, representation_name, representation_payload)
                representation_entries.append(
                    {
                        "archive_member": representation_name,
                        "format": representation_format,
                        "content_digest": "sha256:"
                        + hashlib.sha256(representation_payload).hexdigest(),
                        "renderer_profile_version": str(
                            representation.get("renderer_profile_version", "")
                        ),
                        "assurance_class": str(representation.get("assurance_class", "")),
                    }
                )
            manifest_members.append(
                _manifest_member(
                    member,
                    state=state,
                    archive_member=name,
                    object_digest="sha256:" + hashlib.sha256(payload).hexdigest(),
                    representations=representation_entries,
                )
            )
        if consistency is not None:
            _write(
                archive,
                "95_package_consistency.json",
                (
                    json.dumps(consistency, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8"),
            )
        _write(
            archive,
            "96_package_manifest.json",
            _package_manifest(package, register_manifest, manifest_members),
        )
        _write(
            archive,
            "97_field_evidence_and_missing_inputs.csv",
            _field_evidence_csv(field_resolutions),
        )
        _write(archive, "98_package_status.txt", _status_text(package, members))
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


def _register_docx(package: Mapping[str, Any], manifest: Mapping[str, Any]) -> bytes:
    """Render the package register as an editable DOCX candidate.

    It deliberately records only the package manifest: roles, states, copies,
    and provenance references.  It does not manufacture dates, signatures, or
    field measurements when the package is incomplete.
    """

    rows = [
        ("№", "Документ", "Состояние", "Экземпляры", "Основание"),
        *(
            (
                str(item.get("ordinal", "")),
                _register_role_label(str(item.get("role", ""))),
                _register_state_label(str(item.get("state", ""))),
                str(item.get("copies", "")),
                "; ".join(str(value) for value in item.get("evidence_refs", [])),
            )
            for item in manifest.get("documents", [])
            if isinstance(item, Mapping)
        ),
    ]
    table = "<w:tbl>" + "".join(_docx_row(row) for row in rows) + "</w:tbl>"
    package_id = escape(str(package.get("id_package_id", "")))
    package_version = escape(str(package.get("version", "")))
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        '<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>'
        "Реестр исполнительной документации (кандидат)</w:t></w:r></w:p>"
        '<w:p><w:r><w:t xml:space="preserve">'
        f"Комплект: {package_id}; версия: {package_version}</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Этот редактируемый реестр является кандидатом, связанным с доказательствами. "
        "Он не подтверждает выполнение работ, подписи или фактические измерения.</w:t></w:r></w:p>"
        f"{table}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr></w:body></w:document>"
    ).encode()
    styles = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        b'<w:name w:val="Normal"/></w:style>'
        b'<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>'
        b'<w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr>'
        b"</w:style></w:styles>"
    )
    return _docx_package(document, styles)


def _register_role_label(role: str) -> str:
    """Keep a Russian editable register readable without hiding stable role IDs."""

    label = _REGISTER_ROLE_LABELS.get(role)
    return f"{label} ({role})" if label else role


def _register_state_label(state: str) -> str:
    return _REGISTER_STATE_LABELS.get(state, state)


def _docx_row(values: tuple[str, str, str, str, str]) -> str:
    cells = "".join(
        '<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>'
        f'<w:p><w:r><w:t xml:space="preserve">{escape(value)}</w:t></w:r></w:p></w:tc>'
        for value in values
    )
    return f"<w:tr>{cells}</w:tr>"


def _docx_package(document: bytes, styles: bytes) -> bytes:
    content_types = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        b'<Default Extension="xml" ContentType="application/xml"/>'
        b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        b'<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        b'<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
        b"</Types>"
    )
    root_rels = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        b"</Relationships>"
    )
    document_rels = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
        b"</Relationships>"
    )
    settings = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:compat/></w:settings>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, payload in (
            ("[Content_Types].xml", content_types),
            ("_rels/.rels", root_rels),
            ("word/document.xml", document),
            ("word/styles.xml", styles),
            ("word/settings.xml", settings),
            ("word/_rels/document.xml.rels", document_rels),
        ):
            _write(archive, name, payload)
    return output.getvalue()


def _missing_csv(rows: Iterable[Mapping[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=("ordinal", "role", "state", "blockers"))
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _field_evidence_csv(rows: Iterable[Mapping[str, Any]]) -> bytes:
    """Create an editable, deterministic field-readiness schedule.

    The same field can have more than one evidence binding.  It remains one
    field row with a semicolon-separated, stable set of evidence identifiers;
    emitting one row per join result would make an operator mistake evidence
    multiplicity for separate required inputs.
    """

    grouped: dict[tuple[str, str, str, str, str, str, str, str], set[tuple[str, str]]] = {}
    for item in rows:
        key = (
            _as_text(item.get("generation_run_id")),
            _as_text(item.get("field_key")),
            _as_text(item.get("state")),
            str(bool(item.get("material", False))).lower(),
            _as_text(item.get("normalized_value")),
            _as_text(item.get("display_value")),
            _as_text(item.get("fact_id")),
            _as_text(item.get("fact_version")),
        )
        grouped.setdefault(key, set()).add(
            (
                _as_text(item.get("evidence_link_id")),
                _as_text(item.get("source_locator_id")),
            )
        )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "generation_run_id",
            "field_key",
            "state",
            "material",
            "normalized_value",
            "display_value",
            "fact_id",
            "fact_version",
            "evidence_link_ids",
            "source_locator_ids",
        ),
    )
    writer.writeheader()
    for key in sorted(grouped):
        evidence = sorted(grouped[key])
        writer.writerow(
            {
                "generation_run_id": key[0],
                "field_key": key[1],
                "state": key[2],
                "material": key[3],
                "normalized_value": key[4],
                "display_value": key[5],
                "fact_id": key[6],
                "fact_version": key[7],
                "evidence_link_ids": ";".join(item[0] for item in evidence if item[0]),
                "source_locator_ids": ";".join(item[1] for item in evidence if item[1]),
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _as_text(value: object | None) -> str:
    return "" if value is None else str(value)


def _status_text(package: Mapping[str, Any], members: Iterable[Mapping[str, Any]]) -> bytes:
    finalized = sum(1 for item in members if item.get("finalized_document_id"))
    generated = sum(1 for item in members if item.get("generated_candidate_id"))
    lines = (
        f"Идентификатор комплекта: {package.get('id_package_id', '')}",
        f"Версия: {package.get('version', '')}",
        "Статус: текущий комплект является кандидатом, связанным с доказательствами.",
        f"Подготовлено кандидатов: {generated}",
        f"Финализировано документов: {finalized}",
        "Готовность полей и отсутствующие входные данные перечислены в "
        "97_field_evidence_and_missing_inputs.csv.",
        "Отсутствующие и заблокированные позиции перечислены в 99_missing_or_blocked_items.csv.",
        "Состав архива, версии и контрольные суммы включённых файлов приведены в "
        "96_package_manifest.json.",
        "Независимая сверка реестра, состава, файлов, шаблонов и полей приведена в "
        "95_package_consistency.json, если она была выполнена для этой версии.",
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


def _manifest_member(
    member: Mapping[str, Any],
    *,
    state: str,
    archive_member: str | None = None,
    object_digest: str | None = None,
    representations: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    """Describe one exact membership without treating it as a completed fact."""

    return {
        "ordinal": int(member.get("ordinal", 0)),
        "membership_id": _as_text(member.get("membership_id")),
        "membership_version": member.get("version"),
        "role": _as_text(member.get("role")),
        "state": state,
        "format": _as_text(member.get("format")),
        "archive_member": archive_member,
        "object_digest": object_digest,
        "representations": representations or [],
        "generated_candidate_id": _as_text(member.get("generated_candidate_id")),
        "finalized_document_id": _as_text(member.get("finalized_document_id")),
        "template_id": _as_text(member.get("template_id")),
        "template_version": _as_text(member.get("template_version")),
        "template_qualification_state": _as_text(member.get("template_qualification_state")),
        "template_official_status": _as_text(member.get("template_official_status")),
        "evidence_refs": sorted(str(item) for item in member.get("evidence_refs", [])),
        "blocker_codes": sorted(str(item) for item in member.get("blocker_codes", [])),
    }


def _package_manifest(
    package: Mapping[str, Any],
    register_manifest: Mapping[str, Any],
    members: list[dict[str, object]],
) -> bytes:
    """Write an auditable, deterministic archive manifest after the register.

    The manifest has no authority to finalise a document.  It merely lets a
    recipient verify exactly which candidate/finalized member and field-status
    schedules were delivered with this package version.
    """

    payload = {
        "manifest_kind": "support_id_package_delivery_manifest",
        "package": {
            "id_package_id": _as_text(package.get("id_package_id")),
            "version": package.get("version"),
            "status": "candidate_or_finalized_members_only",
        },
        "register_manifest_digest": "sha256:"
        + hashlib.sha256(
            json.dumps(register_manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "members": members,
        "limitations": [
            "A candidate document is not proof of executed work, signature, measurement, or test result.",
            "A missing or blocked membership remains outside the delivered document set.",
        ],
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _extension(value: str) -> str:
    return {"DOCX": "docx", "PDF_OVERLAY": "pdf", "PDF": "pdf"}.get(value.upper(), "bin")


def _safe_component(value: str) -> str:
    return _SAFE_NAME.sub("-", value).strip("-") or "document"
