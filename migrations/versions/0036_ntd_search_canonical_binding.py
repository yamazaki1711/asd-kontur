"""Bind canonical NTD corpus objects to the production search projection."""

from alembic import op

revision = "0036_ntd_search_binding"
down_revision = "0035_ntd_processing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE platform.ntd_search_documents ADD COLUMN corpus_object_id uuid")

    op.execute(
        "ALTER TABLE platform.ntd_search_documents "
        "DROP CONSTRAINT ntd_search_documents_authority_class_check"
    )

    op.execute(
        "ALTER TABLE platform.ntd_search_documents DROP CONSTRAINT ntd_search_documents_check2"
    )

    op.execute(
        "ALTER TABLE platform.ntd_search_documents "
        "ADD CONSTRAINT ntd_search_documents_authority_class_check "
        "CHECK (authority_class IN ('official', 'official_binding_recovered', 'legacy_reference'))"
    )

    op.execute(
        "ALTER TABLE platform.ntd_search_documents "
        "ADD CONSTRAINT ntd_search_documents_identity_check "
        "CHECK ("
        "corpus_object_id IS NOT NULL "
        "OR authority_class = 'legacy_reference' "
        "OR (normative_document_id IS NOT NULL "
        "AND normative_edition_id IS NOT NULL "
        "AND normative_artifact_id IS NOT NULL "
        "AND source_version_id IS NOT NULL)"
        ")"
    )

    op.execute(
        "ALTER TABLE platform.ntd_search_documents "
        "ADD CONSTRAINT ntd_search_documents_corpus_object_id_fkey "
        "FOREIGN KEY (corpus_object_id) "
        "REFERENCES platform.ntd_corpus_objects (corpus_object_id) "
        "ON DELETE RESTRICT"
    )

    op.execute(
        "CREATE UNIQUE INDEX ntd_search_documents_corpus_object_version_idx "
        "ON platform.ntd_search_documents (corpus_object_id, version) "
        "WHERE corpus_object_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM platform.ntd_search_documents
                WHERE authority_class = 'official_binding_recovered'
            ) THEN
                RAISE EXCEPTION 'NTD_SEARCH_BINDING_DOWNGRADE_BLOCKED';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM platform.ntd_search_documents
                WHERE corpus_object_id IS NOT NULL
                  AND authority_class <> 'legacy_reference'
                  AND (
                      normative_document_id IS NULL
                      OR normative_edition_id IS NULL
                      OR normative_artifact_id IS NULL
                      OR source_version_id IS NULL
                  )
            ) THEN
                RAISE EXCEPTION 'NTD_SEARCH_BINDING_DOWNGRADE_BLOCKED';
            END IF;
        END;
        $$;
        """
    )

    op.execute("DROP INDEX platform.ntd_search_documents_corpus_object_version_idx")

    op.execute(
        "ALTER TABLE platform.ntd_search_documents "
        "DROP CONSTRAINT ntd_search_documents_identity_check"
    )

    op.execute(
        "ALTER TABLE platform.ntd_search_documents "
        "DROP CONSTRAINT ntd_search_documents_corpus_object_id_fkey"
    )

    op.execute("ALTER TABLE platform.ntd_search_documents DROP COLUMN corpus_object_id")

    op.execute(
        "ALTER TABLE platform.ntd_search_documents "
        "DROP CONSTRAINT ntd_search_documents_authority_class_check"
    )

    op.execute(
        "ALTER TABLE platform.ntd_search_documents "
        "ADD CONSTRAINT ntd_search_documents_authority_class_check "
        "CHECK (authority_class IN ('official', 'legacy_reference'))"
    )

    op.execute(
        "ALTER TABLE platform.ntd_search_documents "
        "ADD CONSTRAINT ntd_search_documents_check2 "
        "CHECK ("
        "authority_class = 'legacy_reference' "
        "OR (normative_document_id IS NOT NULL "
        "AND normative_edition_id IS NOT NULL "
        "AND normative_artifact_id IS NOT NULL "
        "AND source_version_id IS NOT NULL)"
        ")"
    )
