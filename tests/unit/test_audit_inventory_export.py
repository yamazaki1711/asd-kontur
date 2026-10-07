from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from uuid import uuid4

from asd_kontur.application_spine.models import DocumentSummary
from asd_kontur.application_spine.services import ProductSpineService
from asd_kontur.audit.duplicate_review import review_uploaded_id_duplicates
from asd_kontur.audit.inventory_export import render_uploaded_document_inventory_csv


def test_inventory_export_keeps_review_unperformed_and_escapes_formula() -> None:
    rendered = render_uploaded_document_inventory_csv(
        (
            {
                "document_id": "document-1",
                "version": 2,
                "source_version_id": "source-2",
                "safe_display_name": '=HYPERLINK("https://example.invalid")',
                "source_kind": "field_document",
                "document_roles": ("executive_documentation",),
                "page_count": 3,
                "admission_status": "accepted",
                "extraction_status": "complete",
            },
        )
    )
    rows = list(csv.DictReader(io.StringIO(rendered.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["safe_display_name"].startswith("'=")
    assert rows[0]["preliminary_document_roles"] == "executive_documentation"
    assert rows[0]["independent_content_review"] == "not_performed"
    assert rows[0]["signature_review"] == ""


def test_service_inventory_export_reaches_later_pages() -> None:
    organization_id, workspace_id = uuid4(), uuid4()

    def document() -> DocumentSummary:
        return DocumentSummary(
            organization_id=organization_id,
            workspace_id=workspace_id,
            document_id=uuid4(),
            version=1,
            prior_versions=(),
            job_ids=(),
            source_artifact_id=None,
            source_version_id=uuid4(),
            source_kind="field_document",
            safe_display_name="act.pdf",
            relative_path="act.pdf",
            media_type="application/pdf",
            size_bytes=8,
            content_digest="sha256:" + "0" * 64,
            page_count=1,
            admission_status="accepted",
            extraction_status="complete",
            capability_gaps=(),
            recorded_at=datetime.now(UTC),
            document_roles=("executive_documentation",),
        )

    first, second = document(), document()
    seen: list[str | None] = []
    service = object.__new__(ProductSpineService)

    def page(**kwargs: object) -> tuple[tuple[DocumentSummary, ...], str | None]:
        cursor = kwargs["cursor"]
        assert cursor is None or cursor == "next"
        seen.append(cursor)
        return ((first,), "next") if cursor is None else ((second,), None)

    service.list_documents = page  # type: ignore[method-assign]
    exported = service.audit_uploaded_document_inventory_export(
        owner_identity_id="owner", workspace_id=workspace_id
    )
    rows = list(csv.DictReader(io.StringIO(b"".join(exported.chunks).decode("utf-8-sig"))))
    assert seen == [None, "next"]
    assert {row["document_id"] for row in rows} == {
        str(first.document_id),
        str(second.document_id),
    }


def test_exact_duplicate_review_requires_distinct_active_field_documents() -> None:
    digest = "sha256:" + "a" * 64
    rows = [
        {
            "document_id": "field-a",
            "version": 2,
            "safe_display_name": "Акт.pdf",
            "source_kind": "field_document",
            "content_digest": digest,
        },
        {
            "document_id": "field-a",
            "version": 1,
            "safe_display_name": "Акт-старый.pdf",
            "source_kind": "field_document",
            "content_digest": digest,
        },
        {
            "document_id": "design-a",
            "version": 1,
            "safe_display_name": "Чертёж.pdf",
            "source_kind": "project_evidence",
            "content_digest": digest,
        },
    ]
    assert review_uploaded_id_duplicates(rows)["duplicate_group_count"] == 0
    rows.append(
        {
            "document_id": "field-b",
            "version": 1,
            "safe_display_name": "Копия акта.pdf",
            "source_kind": "field_document",
            "content_digest": digest,
        }
    )
    reviewed = review_uploaded_id_duplicates(rows)
    assert reviewed["duplicate_group_count"] == 1
    assert reviewed["duplicate_document_count"] == 2
    assert reviewed["groups"][0]["uncertainty"] == (
        "identical_bytes_do_not_prove_duplicate_document_purpose"
    )
