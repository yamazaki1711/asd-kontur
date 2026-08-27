#!/usr/bin/env python3
"""Publish the official Order 344/pr AOSR form as a qualified TemplateVersion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.support import OfficialTemplatePublisher, load_official_pdf_form_profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--object-store-root", required=True, type=Path)
    parser.add_argument("--official-source", required=True, type=Path)
    parser.add_argument("--font", required=True, type=Path)
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("contracts/templates/support-aosr-344pr-2023-pdf-overlay-v1.json"),
    )
    parser.add_argument("--required-document-type-id", type=UUID)
    parser.add_argument("--required-document-type-version")
    args = parser.parse_args()
    profile = load_official_pdf_form_profile(args.profile)
    engine = sa.create_engine(args.database_url, pool_pre_ping=True)
    store = WorkspaceObjectStore(
        args.object_store_root, chunk_bytes=65536, max_file_bytes=64_000_000
    )
    try:
        publication = OfficialTemplatePublisher(engine, store).publish_pdf_overlay(
            stable_key="support.aosr.344pr-2023.official-form",
            template_version="344pr-2023@1.0.0",
            field_schema_version="344pr-2023@1.0.0",
            source_bytes=args.official_source.read_bytes(),
            font_bytes=args.font.read_bytes(),
            font_media_type="font/ttf",
            profile=profile,
            required_document_type_id=args.required_document_type_id,
            required_document_type_version=args.required_document_type_version,
        )
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "template_source_id": str(publication.template_source_id),
                "template_id": str(publication.template_id),
                "template_version": publication.template_version,
                "source_digest": publication.source_digest,
                "template_digest": publication.template_digest,
                "font_digest": publication.font_digest,
                "qualification_receipt_digest": publication.qualification_receipt_digest,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
