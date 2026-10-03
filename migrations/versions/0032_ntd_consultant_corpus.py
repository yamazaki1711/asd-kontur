"""Add searchable document/page NTD corpus without changing source artifacts.

Revision ID: 0032_ntd_consultant
Revises: 0031_assistant_reasoning
Create Date: 2026-08-30
"""

from __future__ import annotations

import os

from alembic import op

revision = "0032_ntd_consultant"
down_revision = "0031_assistant_reasoning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform.ntd_search_documents (
          search_document_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          authority_class text NOT NULL CHECK (authority_class IN ('official','legacy_reference')),
          normative_document_id uuid REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          normative_edition_id uuid REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          normative_artifact_id uuid REFERENCES platform.normative_artifacts(normative_artifact_id) ON DELETE RESTRICT,
          source_version_id uuid REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          stable_designation text NOT NULL,
          normalized_designation text NOT NULL,
          alternative_designations text[] NOT NULL DEFAULT '{}',
          title text NOT NULL,
          edition_label text,
          artifact_digest text NOT NULL CHECK (artifact_digest ~ '^sha256:[a-f0-9]{64}$'),
          bytes_status text NOT NULL CHECK (bytes_status IN ('present','missing')),
          page_inventory_status text NOT NULL CHECK (page_inventory_status IN ('not_inventory','inventoried')),
          text_status text NOT NULL CHECK (text_status IN ('none','partial','complete')),
          search_status text NOT NULL CHECK (search_status IN ('not_searchable','partially_searchable','searchable')),
          structure_status text NOT NULL CHECK (structure_status IN ('not_structured','structured','verified_provisions')),
          edition_currency_status text NOT NULL CHECK (edition_currency_status IN ('checked','not_checked')),
          page_count integer NOT NULL CHECK (page_count >= 0),
          searchable_page_count integer NOT NULL CHECK (searchable_page_count >= 0 AND searchable_page_count <= page_count),
          native_text_characters bigint NOT NULL CHECK (native_text_characters >= 0),
          ocr_page_count integer NOT NULL CHECK (ocr_page_count >= 0 AND ocr_page_count <= page_count),
          ocr_text_characters bigint NOT NULL CHECK (ocr_text_characters >= 0),
          structured_fragment_count bigint NOT NULL CHECK (structured_fragment_count >= 0),
          verified_provision_count bigint NOT NULL CHECK (verified_provision_count >= 0),
          origin_manifest_digest text CHECK (origin_manifest_digest IS NULL OR origin_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          source_access_href text,
          source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          index_profile_version text NOT NULL CHECK (lower(index_profile_version) <> 'latest'),
          document_fingerprint text NOT NULL CHECK (document_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          search_text text NOT NULL,
          search_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian',search_text)) STORED,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (search_document_id,version),
          UNIQUE (document_fingerprint),
          CHECK (
            authority_class='legacy_reference' OR
            (normative_document_id IS NOT NULL AND normative_edition_id IS NOT NULL AND
             normative_artifact_id IS NOT NULL AND source_version_id IS NOT NULL)
          )
        );
        CREATE INDEX ntd_search_documents_vector_gin ON platform.ntd_search_documents USING gin(search_vector);
        CREATE INDEX ntd_search_documents_designation_idx ON platform.ntd_search_documents(normalized_designation);

        CREATE TABLE platform.ntd_search_pages (
          search_document_id uuid NOT NULL,
          search_document_version bigint NOT NULL,
          page_number integer NOT NULL CHECK (page_number >= 1),
          source_locator_id uuid REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          page_text text NOT NULL,
          page_text_digest text NOT NULL CHECK (page_text_digest ~ '^sha256:[a-f0-9]{64}$'),
          text_status text NOT NULL CHECK (text_status IN ('no_text','searchable')),
          extraction_method text NOT NULL CHECK (extraction_method IN (
            'admitted_native_pdf','admitted_native_plus_ocr_pdf','recovered_legacy_native_pdf'
          )),
          page_fingerprint text NOT NULL CHECK (page_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          search_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian',page_text)) STORED,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (search_document_id,search_document_version,page_number),
          UNIQUE (page_fingerprint),
          FOREIGN KEY (search_document_id,search_document_version)
            REFERENCES platform.ntd_search_documents(search_document_id,version) ON DELETE RESTRICT
        );
        CREATE INDEX ntd_search_pages_vector_gin ON platform.ntd_search_pages USING gin(search_vector);

        CREATE TABLE platform.ntd_search_index_build_receipts (
          build_receipt_id uuid PRIMARY KEY,
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          official_denominator integer NOT NULL CHECK (official_denominator >= 0),
          reference_denominator integer NOT NULL CHECK (reference_denominator >= 0),
          document_count integer NOT NULL CHECK (document_count >= 0),
          searchable_document_count integer NOT NULL CHECK (searchable_document_count >= 0),
          partially_searchable_document_count integer NOT NULL CHECK (partially_searchable_document_count >= 0),
          document_without_text_count integer NOT NULL CHECK (document_without_text_count >= 0),
          page_count integer NOT NULL CHECK (page_count >= 0),
          searchable_page_count integer NOT NULL CHECK (searchable_page_count >= 0),
          source_manifest_digests jsonb NOT NULL,
          build_fingerprint text NOT NULL UNIQUE CHECK (build_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TRIGGER ntd_search_documents_immutable BEFORE UPDATE OR DELETE ON platform.ntd_search_documents
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_search_pages_immutable BEFORE UPDATE OR DELETE ON platform.ntd_search_pages
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_search_index_build_receipts_immutable BEFORE UPDATE OR DELETE ON platform.ntd_search_index_build_receipts
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();

        GRANT SELECT ON platform.ntd_search_documents,platform.ntd_search_pages,
          platform.ntd_search_index_build_receipts TO asd_app,asd_document_worker;
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("NTD consultant corpus downgrade requires a disposable database")
    op.execute("DROP TABLE platform.ntd_search_index_build_receipts")
    op.execute("DROP TABLE platform.ntd_search_pages")
    op.execute("DROP TABLE platform.ntd_search_documents")
