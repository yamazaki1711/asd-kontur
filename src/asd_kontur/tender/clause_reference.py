"""Source-grounded labels for contract clauses in professional outputs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SOURCE_CLAUSE_NUMBER = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){0,4})\.(?=\s|$)")


def display_clause_reference(clause: Mapping[str, Any]) -> str:
    """Never present a model working key as an official contract clause number."""

    source_match = _SOURCE_CLAUSE_NUMBER.match(str(clause.get("source_text") or ""))
    if source_match:
        return source_match.group(1)
    page = clause.get("source_page") or clause.get("page_number")
    return f"Пункт без номера (стр./лист {page})" if page else "Пункт без номера — см. источник"


def display_protocol_clause_reference(clause: Mapping[str, Any]) -> str:
    """Bind a proposal to its document even when clause numbers repeat."""

    reference = display_clause_reference(clause)
    source_name = str(clause.get("source_name") or "").strip()
    return f"{source_name}: {reference}" if source_name else reference
