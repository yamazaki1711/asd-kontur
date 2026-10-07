"""Exact-byte duplicate triage for uploaded as-built documents.

This is an actionable inventory check, not proof that two documents are the
same legal form or that either copy is invalid. Only active document versions
selected by the workspace repository may enter this projection.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


def review_uploaded_id_duplicates(documents: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = tuple(dict(document) for document in documents)
    field_rows = tuple(row for row in rows if str(row.get("source_kind")) == "field_document")
    by_digest: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in field_rows:
        digest = str(row.get("content_digest") or "")
        document_id = str(row.get("document_id") or "")
        if (
            not digest.startswith("sha256:")
            or len(digest) != 71
            or any(char not in "0123456789abcdef" for char in digest[7:])
            or not document_id
        ):
            continue
        by_digest[digest].append(row)

    groups: list[dict[str, Any]] = []
    for digest, members in sorted(by_digest.items()):
        distinct = {str(member["document_id"]): member for member in members}
        if len(distinct) < 2:
            continue
        groups.append(
            {
                "finding_kind": "EXACT_BYTES_MULTIPLE_ID_RECORDS_REVIEW",
                "content_digest": digest,
                "members": [
                    {
                        "document_id": document_id,
                        "version": int(member["version"]),
                        "safe_display_name": str(member["safe_display_name"]),
                    }
                    for document_id, member in sorted(distinct.items())
                ],
                "practical_consequence": "possible_repeated_id_registration",
                "recommended_action": "confirm_copy_purpose_and_authoritative_record",
                "uncertainty": "identical_bytes_do_not_prove_duplicate_document_purpose",
            }
        )
    return {
        "review_kind": "uploaded_id_exact_duplicate_triage",
        "status": "partial",
        "document_count": len(rows),
        "field_document_count": len(field_rows),
        "duplicate_group_count": len(groups),
        "duplicate_document_count": sum(len(group["members"]) for group in groups),
        "groups": groups,
        "authority_boundary": "content_identity_only_independent_document_audit_not_performed",
    }
