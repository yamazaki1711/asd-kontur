"""Format-preserving revised-contract candidate for admitted DOCX contracts."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Mapping
from typing import Any, cast
from xml.etree import ElementTree as ET

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
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

    _register_source_namespaces(document)
    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise RevisedContractCandidateError("revised_contract_source_docx_invalid") from exc

    paragraphs = list(root.iter(_PARAGRAPH))
    paragraph_texts = [_paragraph_text(paragraph) for paragraph in paragraphs]
    used_paragraphs: set[int] = set()
    for source_text, revised_text in replacements:
        normalized_source = _normalized(source_text)
        matches = [
            index
            for index, paragraph_text in enumerate(paragraph_texts)
            if _normalized(paragraph_text) == normalized_source
        ]
        if len(matches) != 1 or matches[0] in used_paragraphs:
            raise RevisedContractCandidateError("revised_contract_clause_match_not_unique")
        paragraph_index = matches[0]
        _replace_paragraph_text(paragraphs[paragraph_index], revised_text)
        used_paragraphs.add(paragraph_index)

    payloads["word/document.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
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


def _replace_paragraph_text(paragraph: ET.Element, revised_text: str) -> None:
    text_nodes = list(paragraph.iter(_TEXT))
    if not text_nodes:
        raise RevisedContractCandidateError("revised_contract_source_paragraph_empty")
    original = "".join(node.text or "" for node in text_nodes)
    leading = original[: len(original) - len(original.lstrip())]
    trailing = original[len(original.rstrip()) :]
    text_nodes[0].text = f"{leading}{revised_text.strip()}{trailing}"
    text_nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for node in text_nodes[1:]:
        node.text = ""


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(_TEXT))


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _register_source_namespaces(document: bytes) -> None:
    for _, namespace in ET.iterparse(io.BytesIO(document), events=("start-ns",)):
        prefix, uri = cast(tuple[str, str], namespace)
        if prefix != "xml":
            ET.register_namespace(prefix or "", uri)


def _records(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))
