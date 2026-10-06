"""Format-preserving revised-contract candidate for admitted DOCX contracts."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Mapping
from typing import Any, cast
from xml.etree import ElementTree as ET

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_MARKUP_COMPATIBILITY_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_TEXT = f"{{{_WORD_NS}}}t"
_PARAGRAPH = f"{{{_WORD_NS}}}p"


class RevisedContractCandidateError(ValueError):
    """A full revised contract cannot be produced without changing unsupported content."""


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
        replacements.append((source_text, revised_text))
    if not replacements:
        raise RevisedContractCandidateError("revised_contract_revisions_unavailable")

    try:
        with zipfile.ZipFile(io.BytesIO(source_docx), "r") as source:
            infos = source.infolist()
            payloads = {info.filename: source.read(info.filename) for info in infos}
    except (zipfile.BadZipFile, KeyError) as exc:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid") from exc
    document = payloads.get("word/document.xml")
    if document is None:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid")

    source_namespaces = _register_source_namespaces(document)
    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid") from exc

    paragraphs = list(root.iter(_PARAGRAPH))
    paragraph_texts = [_paragraph_text(paragraph) for paragraph in paragraphs]
    for source_text, revised_text in replacements:
        matches = [
            (index, span)
            for index, paragraph_text in enumerate(paragraph_texts)
            if (span := _exact_fragment_span(paragraph_text, source_text)) is not None
        ]
        if len(matches) != 1:
            raise RevisedContractCandidateError("revised_contract_clause_match_not_unique")
        paragraph_index, (start, end) = matches[0]
        original_paragraph = paragraph_texts[paragraph_index]
        suffix = original_paragraph[end:]
        normalized_revision = revised_text.strip()
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


def _exact_fragment_span(paragraph_text: str, source_text: str) -> tuple[int, int] | None:
    """Locate one exact source fragment while tolerating Word whitespace runs."""

    words = source_text.split()
    if not words:
        return None
    pattern = re.compile(r"\s+".join(re.escape(word) for word in words))
    matches = list(pattern.finditer(paragraph_text))
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
