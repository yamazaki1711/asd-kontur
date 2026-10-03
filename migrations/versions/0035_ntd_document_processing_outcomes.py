"""NTD document processing outcomes migration."""

from alembic import op

revision = "0035_ntd_processing"
down_revision = "0034_assistant_intent_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform.ntd_document_processing_outcomes (
          processing_outcome_id uuid PRIMARY KEY,
          corpus_object_id uuid NOT NULL REFERENCES platform.ntd_corpus_objects(corpus_object_id) ON DELETE RESTRICT,
          processing_profile_version text NOT NULL CHECK (lower(processing_profile_version) <> 'latest'),
          terminal_status text NOT NULL CHECK (terminal_status IN (
            'indexed_complete', 'indexed_partial', 'blocked_extraction', 'blocked_source', 'unsupported_content'
          )),
          pages_total integer NOT NULL CHECK (pages_total >= 0),
          pages_extracted integer NOT NULL CHECK (pages_extracted >= 0),
          pages_blocked integer NOT NULL CHECK (pages_blocked >= 0),
          structural_units_count integer NOT NULL CHECK (structural_units_count >= 0),
          contextual_chunks_count integer NOT NULL CHECK (contextual_chunks_count >= 0),
          embeddings_count integer NOT NULL CHECK (embeddings_count >= 0),
          fts_indexed boolean NOT NULL DEFAULT false,
          hnsw_indexed boolean NOT NULL DEFAULT false,
          typed_graph_indexed boolean NOT NULL DEFAULT false,
          gateway_registered boolean NOT NULL DEFAULT false,
          blocker_code text,
          metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
          processing_fingerprint text NOT NULL UNIQUE CHECK (processing_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (corpus_object_id, processing_profile_version),
          CHECK (pages_extracted + pages_blocked <= pages_total),
          CHECK (embeddings_count <= contextual_chunks_count)
        );

        CREATE INDEX ntd_document_processing_outcomes_status_idx
          ON platform.ntd_document_processing_outcomes (terminal_status);

        CREATE INDEX ntd_document_processing_outcomes_recorded_at_idx
          ON platform.ntd_document_processing_outcomes (recorded_at);

        CREATE TRIGGER ntd_document_processing_outcomes_immutable
          BEFORE UPDATE OR DELETE ON platform.ntd_document_processing_outcomes
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();

        REVOKE ALL ON platform.ntd_document_processing_outcomes FROM PUBLIC;

        GRANT SELECT ON platform.ntd_document_processing_outcomes TO asd_app, asd_document_worker;
        GRANT INSERT ON platform.ntd_document_processing_outcomes TO asd_document_worker;
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS ntd_document_processing_outcomes_immutable ON platform.ntd_document_processing_outcomes"
    )
    op.execute("DROP INDEX IF EXISTS platform.ntd_document_processing_outcomes_status_idx")
    op.execute("DROP INDEX IF EXISTS platform.ntd_document_processing_outcomes_recorded_at_idx")
    op.execute("DROP TABLE IF EXISTS platform.ntd_document_processing_outcomes")
