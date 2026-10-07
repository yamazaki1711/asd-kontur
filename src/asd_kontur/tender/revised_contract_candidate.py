"""Format-preserving revised-contract candidate for admitted DOCX contracts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, cast
from xml.etree import ElementTree as ET

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from asd_kontur.tender.clause_reference import (
    display_clause_reference,
    display_protocol_clause_reference,
)
from asd_kontur.tender.qwen_contract_analysis import contract_proposed_wording_has_placeholder

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_OFFICE_DOCUMENT_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)
_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MARKUP_COMPATIBILITY_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_TEXT = f"{{{_WORD_NS}}}t"
_PARAGRAPH = f"{{{_WORD_NS}}}p"
_TABLE = f"{{{_WORD_NS}}}tbl"
_ROW = f"{{{_WORD_NS}}}tr"
_CELL = f"{{{_WORD_NS}}}tc"
_TRACKED_CHANGE_TAGS = frozenset(
    f"{{{_WORD_NS}}}{name}" for name in ("ins", "del", "moveFrom", "moveTo")
)
_VISIBLE_WORD_PART = re.compile(
    r"word/(?:document|header[1-9]\d*|footer[1-9]\d*|footnotes|endnotes)\.xml\Z"
)
_CLAUSE_NUMBER = re.compile(r"^(?P<prefix>\s*(?P<number>\d+(?:\.\d+){1,5})\.?\s+)")


class RevisedContractCandidateError(ValueError):
    """A full revised contract cannot be produced without changing unsupported content."""


def _validate_unchanged_pdf(content: bytes) -> None:
    """Check readability without changing a source appendix or implying editability."""

    if not content.startswith(b"%PDF-"):
        raise RevisedContractCandidateError("revised_contract_source_pdf_invalid")
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted or len(reader.pages) < 1:
            raise RevisedContractCandidateError("revised_contract_source_pdf_invalid")
    except (PdfReadError, ValueError, OSError) as exc:
        raise RevisedContractCandidateError("revised_contract_source_pdf_invalid") from exc


def render_revised_contract_source_package(
    sources: Sequence[Mapping[str, Any]],
    view: Mapping[str, Any],
    *,
    protocol_docx: bytes | None = None,
) -> bytes:
    """Return every admitted DOCX contract source, editing only selected clauses.

    The package is a human-review candidate, not an agreed or signed contract.
    A revision whose exact source is absent fails the whole package closed.
    """

    clauses = {
        (str(item.get("clause_id", "")), str(item.get("clause_version", ""))): item
        for item in _records(view.get("clauses"))
    }
    revisions_by_source: dict[str, list[Mapping[str, Any]]] = {}
    for revision in _records(view.get("revised_clauses")):
        clause = clauses.get(
            (
                str(revision.get("source_clause_id", "")),
                str(revision.get("source_clause_version", "")),
            )
        )
        source_id = str(clause.get("source_version_id") or "") if clause else ""
        if not source_id:
            raise RevisedContractCandidateError("revised_contract_clause_source_unavailable")
        revisions_by_source.setdefault(source_id, []).append(revision)
    if not revisions_by_source:
        raise RevisedContractCandidateError("revised_contract_revisions_unavailable")

    source_ids = [str(item.get("source_version_id") or "") for item in sources]
    if (
        not source_ids
        or len(source_ids) != len(set(source_ids))
        or any(not item for item in source_ids)
    ):
        raise RevisedContractCandidateError("revised_contract_source_roster_invalid")
    if not set(revisions_by_source).issubset(source_ids):
        raise RevisedContractCandidateError("revised_contract_clause_source_unavailable")

    files: list[tuple[str, bytes]] = []
    manifest_sources: list[dict[str, Any]] = []
    change_rows: list[tuple[str, ...]] = []
    protocol_rows: list[tuple[str, str, str]] = []
    for ordinal, source in enumerate(sources, start=1):
        source_id = str(source["source_version_id"])
        original = source.get("content")
        if not isinstance(original, bytes):
            raise RevisedContractCandidateError("revised_contract_source_docx_invalid")
        selected = revisions_by_source.get(source_id, [])
        media_type = str(source.get("media_type") or _DOCX_MEDIA_TYPE)
        if media_type == "application/pdf":
            if selected:
                raise RevisedContractCandidateError("revised_contract_pdf_revision_unsupported")
            _validate_unchanged_pdf(original)
            output = original
            entry_name = f"contract-source-{ordinal:02d}.pdf"
            editable = False
        elif media_type == _DOCX_MEDIA_TYPE:
            try:
                with zipfile.ZipFile(io.BytesIO(original)) as package:
                    if (
                        package.testzip() is not None
                        or "word/document.xml" not in package.namelist()
                    ):
                        raise RevisedContractCandidateError("revised_contract_source_docx_invalid")
                    _require_office_document_relationship(package.read("_rels/.rels"))
                    _require_word_content_type(package.read("[Content_Types].xml"))
                    _validate_visible_word_parts(package)
            except (zipfile.BadZipFile, KeyError) as exc:
                raise RevisedContractCandidateError("revised_contract_source_docx_invalid") from exc
            output = (
                render_revised_contract_candidate_docx(
                    original,
                    {"clauses": list(clauses.values()), "revised_clauses": selected},
                )
                if selected
                else original
            )
            entry_name = f"contract-source-{ordinal:02d}.docx"
            editable = True
        else:
            raise RevisedContractCandidateError("revised_contract_source_format_unsupported")
        files.append((entry_name, output))
        for revision in selected:
            clause = clauses[
                (
                    str(revision.get("source_clause_id", "")),
                    str(revision.get("source_clause_version", "")),
                )
            ]
            change_rows.append(
                (
                    str(len(change_rows) + 1),
                    str(source.get("safe_display_name") or entry_name),
                    str(clause.get("source_page") or ""),
                    display_clause_reference(clause),
                    str(revision.get("replacement_source_text") or clause.get("source_text") or ""),
                    str(revision.get("revised_text") or ""),
                    "Проект редакции; требует согласования",
                )
            )
            protocol_rows.append(
                (
                    display_protocol_clause_reference(clause),
                    str(clause.get("source_text") or ""),
                    str(revision.get("revised_text") or ""),
                )
            )
        manifest_sources.append(
            {
                "source_version_id": source_id,
                "source_name": str(source.get("safe_display_name") or ""),
                "entry": entry_name,
                "media_type": media_type,
                "editable": editable,
                "revision_count": len(selected),
                "original_sha256": hashlib.sha256(original).hexdigest(),
                "candidate_sha256": hashlib.sha256(output).hexdigest(),
            }
        )
    change_register = _render_change_register(change_rows)
    unresolved_references = sorted(
        (
            item
            for item in _records(view.get("attachment_references"))
            if item.get("match_decision") != "matched"
        ),
        key=lambda item: (
            str(item.get("source_name") or ""),
            str(item.get("source_page") or ""),
            str(item.get("reference_id") or ""),
        ),
    )
    unresolved_register = (
        render_unresolved_reference_register(unresolved_references)
        if unresolved_references
        else None
    )
    coherence = view.get("coherence_review")
    coherence = coherence if isinstance(coherence, Mapping) else {}
    conflicts = _records(coherence.get("conflicts"))
    manifest = {
        "contract": "revised-contract-source-package@1.0.0",
        "status": "human_review_candidate",
        "warning": (
            "Candidate only; no approval or signature. Unchanged PDF appendices are "
            "not editable. Check unresolved references and cross-clause coherence "
            "before agreement."
        ),
        "coherence_review": {
            "status": str(coherence.get("status") or "not_performed"),
            "scope": "selected_related_clauses_only",
            "accepted_contexts": int(coherence.get("accepted_contexts") or 0),
            "scheduled_contexts": int(coherence.get("scheduled_contexts") or 0),
            "potential_conflict_count": len(conflicts),
        },
        "unresolved_reference_count": len(unresolved_references),
        "unchanged_pdf_appendix_count": sum(
            item["media_type"] == "application/pdf" for item in manifest_sources
        ),
        "analysis_gaps": [
            str(item)
            for item in (view.get("gaps") or ())
            if isinstance(item, str)
            and item != "REVISED_CONTRACT_EXCLUDES_NON_PRIMARY_SOURCE_REVISIONS"
        ],
        "sources": manifest_sources,
        "change_register": {
            "entry": "change-register.csv",
            "sha256": hashlib.sha256(change_register).hexdigest(),
            "revision_count": len(change_rows),
        },
    }
    if unresolved_register is not None:
        manifest["unresolved_references"] = {
            "entry": "unresolved-references.csv",
            "sha256": hashlib.sha256(unresolved_register).hexdigest(),
            "reference_count": len(unresolved_references),
            "status": "inventory_match_unresolved_not_proven_missing",
        }
    if protocol_docx is not None:
        try:
            with zipfile.ZipFile(io.BytesIO(protocol_docx)) as protocol:
                if protocol.testzip() is not None or "word/document.xml" not in protocol.namelist():
                    raise RevisedContractCandidateError("reviewed_contract_protocol_invalid")
                _validate_protocol_rows(protocol.read("word/document.xml"), protocol_rows)
        except zipfile.BadZipFile as exc:
            raise RevisedContractCandidateError("reviewed_contract_protocol_invalid") from exc
        manifest["reviewed_protocol"] = {
            "entry": "reviewed-disagreement-protocol.docx",
            "sha256": hashlib.sha256(protocol_docx).hexdigest(),
            "proposal_count": len(_records(view.get("revised_clauses"))),
        }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for entry_name, output in files:
            member = zipfile.ZipInfo(entry_name, (1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(member, output)
        member = zipfile.ZipInfo("change-register.csv", (1980, 1, 1, 0, 0, 0))
        member.compress_type = zipfile.ZIP_DEFLATED
        package.writestr(member, change_register)
        if unresolved_register is not None:
            member = zipfile.ZipInfo("unresolved-references.csv", (1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(member, unresolved_register)
        if protocol_docx is not None:
            member = zipfile.ZipInfo("reviewed-disagreement-protocol.docx", (1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(member, protocol_docx)
        member = zipfile.ZipInfo("manifest.json", (1980, 1, 1, 0, 0, 0))
        member.compress_type = zipfile.ZIP_DEFLATED
        package.writestr(
            member,
            json.dumps(
                manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode(),
        )
    return archive.getvalue()


def _validate_protocol_rows(document: bytes, expected_rows: Sequence[tuple[str, str, str]]) -> None:
    """Bind the editable protocol to the exact revisions in this package.

    A valid DOCX can still be stale or refer to another selected subset. The
    disagreement table must contain exactly one row per applied clause edit,
    including the original source wording and the proposed replacement.
    """

    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise RevisedContractCandidateError("reviewed_contract_protocol_invalid") from exc
    matched_tables: list[list[tuple[str, ...]]] = []
    for table in root.iter(_TABLE):
        rows = [
            tuple(
                "".join(node.text or "" for node in cell.iter(_TEXT)) for cell in row.findall(_CELL)
            )
            for row in table.findall(_ROW)
        ]
        if (
            rows
            and len(rows[0]) == 5
            and rows[0][1:4]
            == (
                "Пункт договора / документа",
                "Редакция Заказчика",
                "Редакция Подрядчика",
            )
        ):
            matched_tables.append(rows)
    if len(matched_tables) != 1:
        raise RevisedContractCandidateError("reviewed_contract_protocol_mapping_invalid")
    actual_rows = [tuple(row[1:4]) for row in matched_tables[0][1:] if len(row) == 5]
    if len(actual_rows) != len(matched_tables[0]) - 1 or Counter(actual_rows) != Counter(
        expected_rows
    ):
        raise RevisedContractCandidateError("reviewed_contract_protocol_mapping_invalid")


def _render_change_register(rows: Sequence[tuple[str, ...]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        (
            "№",
            "Документ",
            "Страница/лист",
            "Пункт договора",
            "Исходная редакция",
            "Редакция Подрядчика",
            "Статус",
        )
    )
    for row in rows:
        writer.writerow(
            tuple(
                "'" + value if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) else value
                for value in row
            )
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def render_unresolved_reference_register(
    references: Sequence[Mapping[str, Any]],
) -> bytes:
    """Make Qwen's unresolved contract references actionable without claiming absence."""

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        (
            "№",
            "Документ договора",
            "Страница/лист",
            "Дословная ссылка",
            "Какой документ требуется установить",
            "Частично сопоставленные файлы",
            "Причина неопределённости",
            "Идентификатор источника",
        )
    )
    for ordinal, item in enumerate(references, start=1):
        row = (
            str(ordinal),
            str(item.get("source_name") or ""),
            str(item.get("source_page") or ""),
            str(item.get("source_quote") or ""),
            str(item.get("target_description") or ""),
            ", ".join(str(name) for name in (item.get("matched_source_names") or [])),
            str(item.get("uncertainty") or ""),
            str(item.get("source_locator_id") or ""),
        )
        writer.writerow(
            tuple(
                "'" + value if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) else value
                for value in row
            )
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def render_revised_contract_candidate_docx(source_docx: bytes, view: Mapping[str, Any]) -> bytes:
    """Apply only exact, uniquely located clause replacements to the source DOCX.

    The source package remains the document of record.  A candidate is emitted only
    when every proposed revision maps to one complete source paragraph.  Ambiguous,
    partial, or missing matches fail closed instead of producing a deceptively complete
    contract.
    """

    clauses = {
        (str(item.get("clause_id", "")), str(item.get("clause_version", ""))): item
        for item in _records(view.get("clauses"))
    }
    replacements: list[tuple[str, str]] = []
    for revision in _records(view.get("revised_clauses")):
        identity = (
            str(revision.get("source_clause_id", "")),
            str(revision.get("source_clause_version", "")),
        )
        clause = clauses.get(identity)
        source_text = str(revision.get("replacement_source_text") or "")
        if not source_text and clause is not None:
            source_text = str(clause.get("source_text") or "")
        revised_text = str(revision.get("revised_text") or "")
        if not source_text.strip() or not revised_text.strip():
            raise RevisedContractCandidateError("revised_contract_exact_clause_text_unavailable")
        if contract_proposed_wording_has_placeholder(revised_text):
            raise RevisedContractCandidateError("revised_contract_unresolved_placeholder")
        replacements.append((source_text, revised_text))
    if not replacements:
        raise RevisedContractCandidateError("revised_contract_revisions_unavailable")

    try:
        with zipfile.ZipFile(io.BytesIO(source_docx), "r") as source:
            infos = source.infolist()
            if any(
                info.filename.startswith("_xmlsignatures/") or info.filename.endswith(".sigs")
                for info in infos
            ):
                raise RevisedContractCandidateError("revised_contract_signed_source_unsupported")
            _validate_visible_word_parts(source)
            payloads = {info.filename: source.read(info.filename) for info in infos}
    except (zipfile.BadZipFile, KeyError) as exc:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid") from exc
    document = payloads.get("word/document.xml")
    relationships = payloads.get("_rels/.rels")
    content_types = payloads.get("[Content_Types].xml")
    if document is None or relationships is None or content_types is None:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid")
    _require_office_document_relationship(relationships)
    _require_word_content_type(content_types)

    source_namespaces = _register_source_namespaces(document)
    root = _parse_source_document(document)

    paragraphs = list(root.iter(_PARAGRAPH))
    original_tags = tuple(node.tag for node in root.iter())
    paragraph_texts = [_paragraph_text(paragraph) for paragraph in paragraphs]
    edited_paragraphs: set[int] = set()
    for source_text, revised_text in replacements:
        matches = [
            (index, span)
            for index, paragraph_text in enumerate(paragraph_texts)
            if (span := _exact_fragment_span(paragraph_text, source_text)) is not None
        ]
        if len(matches) != 1:
            raise RevisedContractCandidateError("revised_contract_clause_match_not_unique")
        paragraph_index, (start, end) = matches[0]
        if paragraph_index in edited_paragraphs:
            raise RevisedContractCandidateError("revised_contract_overlapping_clause_edits")
        edited_paragraphs.add(paragraph_index)
        original_paragraph = paragraph_texts[paragraph_index]
        suffix = original_paragraph[end:]
        normalized_revision = revised_text.strip()
        source_number = _CLAUSE_NUMBER.match(source_text)
        if source_number is not None:
            proposed_number = _CLAUSE_NUMBER.match(normalized_revision)
            if proposed_number is None:
                normalized_revision = source_number.group("prefix") + normalized_revision
            elif proposed_number.group("number") != source_number.group("number"):
                raise RevisedContractCandidateError("revised_contract_clause_number_changed")
        if (
            normalized_revision
            and suffix
            and normalized_revision[-1] == suffix[0]
            and suffix[0] in ".;:!?"
        ):
            suffix = suffix[1:]
            end += 1
        revised_paragraph = original_paragraph[:start] + normalized_revision + suffix
        _replace_paragraph_span(
            paragraphs[paragraph_index],
            start=start,
            end=end,
            replacement=normalized_revision,
        )
        paragraph_texts[paragraph_index] = revised_paragraph

    serialized_document = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    payloads["word/document.xml"] = _restore_ignorable_namespaces(
        serialized_document,
        source_namespaces=source_namespaces,
    )
    try:
        checked = ET.fromstring(payloads["word/document.xml"])
    except ET.ParseError as exc:
        raise RevisedContractCandidateError("revised_contract_post_edit_integrity_failed") from exc
    if (
        tuple(node.tag for node in checked.iter()) != original_tags
        or [_paragraph_text(paragraph) for paragraph in checked.iter(_PARAGRAPH)] != paragraph_texts
    ):
        raise RevisedContractCandidateError("revised_contract_post_edit_integrity_failed")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for info in infos:
            copied = zipfile.ZipInfo(info.filename, info.date_time)
            copied.compress_type = info.compress_type
            copied.comment = info.comment
            copied.extra = info.extra
            copied.internal_attr = info.internal_attr
            copied.external_attr = info.external_attr
            copied.create_system = info.create_system
            target.writestr(copied, payloads[info.filename])
    return output.getvalue()


def _require_office_document_relationship(payload: bytes) -> None:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid") from exc
    if root.tag != f"{{{_PACKAGE_REL_NS}}}Relationships" or not any(
        item.tag == f"{{{_PACKAGE_REL_NS}}}Relationship"
        and item.get("Type") == _OFFICE_DOCUMENT_REL
        and str(item.get("Target") or "").lstrip("/") == "word/document.xml"
        for item in root
    ):
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid")


def _require_word_content_type(payload: bytes) -> None:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid") from exc
    if root.tag != f"{{{_CONTENT_TYPES_NS}}}Types" or not any(
        item.tag == f"{{{_CONTENT_TYPES_NS}}}Override"
        and item.get("PartName") == "/word/document.xml"
        and item.get("ContentType")
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        for item in root
    ):
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid")


def _replace_paragraph_span(
    paragraph: ET.Element, *, start: int, end: int, replacement: str
) -> None:
    """Preserve untouched run formatting on both sides of an exact edit.

    Word routinely splits a clause over styled runs. Replacing the entire
    paragraph in its first run would silently erase formatting and hyperlinks
    outside the proposed change. Only text nodes intersecting the validated
    source span are changed; replacement takes the first affected run's style.
    """

    text_nodes = list(paragraph.iter(_TEXT))
    if not text_nodes:
        raise RevisedContractCandidateError("revised_contract_source_paragraph_empty")
    offset = 0
    inserted = False
    for node in text_nodes:
        original = node.text or ""
        node_start, node_end = offset, offset + len(original)
        offset = node_end
        if node_end <= start or node_start >= end:
            continue
        prefix = original[: max(0, start - node_start)]
        suffix = original[max(0, end - node_start) :] if end <= node_end else ""
        if not inserted:
            node.text = prefix + replacement + suffix
            inserted = True
        else:
            node.text = suffix
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    if not inserted:
        raise RevisedContractCandidateError("revised_contract_clause_match_not_unique")


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(_TEXT))


def _parse_source_document(document: bytes) -> ET.Element:
    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid") from exc
    if any(node.tag in _TRACKED_CHANGE_TAGS for node in root.iter()):
        raise RevisedContractCandidateError("revised_contract_source_tracked_changes_unsupported")
    return root


def _validate_visible_word_parts(package: zipfile.ZipFile) -> None:
    """Reject unresolved edits in any visible contract story, not just its body.

    Headers, footers and notes can contain operative terms. Preserving those
    parts byte-for-byte while editing the body must not be described as a
    clean revised contract if their tracked-change state is unresolved.
    """

    for name in package.namelist():
        if _VISIBLE_WORD_PART.fullmatch(name):
            _parse_source_document(package.read(name))


def _exact_fragment_span(paragraph_text: str, source_text: str) -> tuple[int, int] | None:
    """Locate one exact source fragment while tolerating Word whitespace runs."""

    words = source_text.split()
    if not words:
        return None
    pattern = re.compile(r"\s+".join(re.escape(word) for word in words))
    matches = [
        match
        for match in pattern.finditer(paragraph_text)
        if (
            match.start() == 0
            or not (
                paragraph_text[match.start() - 1].isalnum()
                or (source_text[0].isdigit() and paragraph_text[match.start() - 1] == ".")
            )
        )
        and (
            match.end() == len(paragraph_text)
            or not (source_text[-1].isalnum() and paragraph_text[match.end()].isalnum())
        )
    ]
    if len(matches) != 1:
        return None
    return matches[0].span()


def _register_source_namespaces(document: bytes) -> dict[str, str]:
    namespaces: dict[str, str] = {}
    for _, namespace in ET.iterparse(io.BytesIO(document), events=("start-ns",)):
        prefix, uri = cast(tuple[str, str], namespace)
        namespaces[prefix] = uri
        if prefix != "xml":
            ET.register_namespace(prefix or "", uri)
    return namespaces


def _restore_ignorable_namespaces(
    document: bytes,
    *,
    source_namespaces: Mapping[str, str],
) -> bytes:
    """Keep namespace declarations referenced only by ``mc:Ignorable``.

    ``xml.etree`` drops unused namespace declarations during serialization. In
    Word documents some extension prefixes are intentionally used only as
    tokens in ``mc:Ignorable``; dropping their declarations makes an otherwise
    unchanged DOCX schema-invalid. Restore only those declarations from the
    admitted source package and fail closed if the source did not define one.
    """

    text = document.decode("utf-8")
    root_match = re.search(r"<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?document\b", text)
    if root_match is None:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid")
    root_end = text.find(">", root_match.start())
    if root_end < 0:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid")
    root_opening = text[root_match.start() : root_end]
    mc_prefix = next(
        (prefix for prefix, uri in source_namespaces.items() if uri == _MARKUP_COMPATIBILITY_NS),
        None,
    )
    if not mc_prefix:
        return document
    match = re.search(rf'\s{re.escape(mc_prefix)}:Ignorable="([^"]*)"', root_opening)
    if match is None:
        return document
    additions: list[str] = []
    for prefix in match.group(1).split():
        if re.search(rf"\sxmlns:{re.escape(prefix)}=", root_opening):
            continue
        uri = source_namespaces.get(prefix)
        if uri is None or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", prefix):
            raise RevisedContractCandidateError("revised_contract_source_docx_invalid")
        additions.append(f' xmlns:{prefix}="{uri}"')
    if not additions:
        return document
    return (text[:root_end] + "".join(additions) + text[root_end:]).encode("utf-8")


def _records(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))
