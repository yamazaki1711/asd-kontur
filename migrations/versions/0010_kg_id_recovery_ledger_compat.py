"""Additive KG-ID recovery-ledger compatibility for early 0009 instances.

Revision ID: 0010_kg_id_compat
Revises: 0009_kg_id
"""

from __future__ import annotations

from alembic import op

revision = "0010_kg_id_compat"
down_revision = "0009_kg_id"
branch_labels = None
depends_on = None


NEW_PLATFORM_TABLES = (
    "practice_guide_edition_states",
    "practice_guide_failed_candidate_versions",
    "practice_guide_source_rows",
    "practice_guide_normative_reference_candidates",
    "practice_guide_normative_reference_resolutions",
    "practice_guide_ntd_relevance_assertions",
    "practice_guidance_coverage_manifests",
    "practice_guidance_gaps",
)


def upgrade() -> None:
    """Repair an already-applied early 0009; clean current 0009 schemas are unchanged."""

    op.execute(
        "ALTER TABLE platform.practice_guide_candidate_versions DROP CONSTRAINT IF EXISTS "
        "practice_guide_candidate_vers_guidance_candidate_id_parent_fkey"
    )
    op.execute(
        "ALTER TABLE platform.practice_guide_verifications DROP CONSTRAINT IF EXISTS "
        "practice_guide_verifications_disposition_check; "
        "ALTER TABLE platform.practice_guide_verifications ADD CONSTRAINT "
        "practice_guide_verifications_disposition_check CHECK "
        "(disposition IN ('supported','contradicted','insufficient','model_failed'))"
    )
    op.execute(
        "ALTER TABLE platform.practice_guide_page_terminal_receipts DROP CONSTRAINT IF EXISTS "
        "practice_guide_page_terminal_receipts_terminal_state_check; "
        "ALTER TABLE platform.practice_guide_page_terminal_receipts ADD CONSTRAINT "
        "practice_guide_page_terminal_receipts_terminal_state_check CHECK "
        "(terminal_state IN ('verified','partial_with_gaps','no_methodological_content',"
        "'unresolved','insufficient_evidence','model_failed','technically_blocked'))"
    )
    op.execute(
        "ALTER TABLE platform.practice_guide_page_terminal_receipts DROP CONSTRAINT IF EXISTS "
        "practice_guide_page_terminal_receipts_check; "
        "ALTER TABLE platform.practice_guide_page_terminal_receipts DROP CONSTRAINT IF EXISTS "
        "practice_guide_page_terminal_receipts_counts_check; "
        "ALTER TABLE platform.practice_guide_page_terminal_receipts ADD CONSTRAINT "
        "practice_guide_page_terminal_receipts_counts_check CHECK "
        "(verified_count<=candidate_count)"
    )
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint "
        "WHERE conrelid='platform.practice_guide_validation_results'::regclass "
        "AND conname='practice_guide_validation_res_guidance_candidate_id_candida_key') "
        "THEN ALTER TABLE platform.practice_guide_validation_results ADD CONSTRAINT "
        "practice_guide_validation_res_guidance_candidate_id_candida_key UNIQUE "
        "(guidance_candidate_id,candidate_version,validator_version,failure_code,field_path); "
        "END IF; END $$"
    )
    op.execute(
        """
        ALTER TABLE platform.practice_guide_editions
          ADD COLUMN IF NOT EXISTS provenance_payload jsonb NOT NULL
          DEFAULT jsonb_build_object('compatibility_recovered',true);
        ALTER TABLE platform.practice_guide_editions
          ALTER COLUMN provenance_payload DROP DEFAULT;

        CREATE TABLE IF NOT EXISTS platform.practice_guide_edition_states (
          practice_guide_edition_state_id uuid PRIMARY KEY,
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          state_sequence bigint NOT NULL CHECK (state_sequence>=1),
          state text NOT NULL CHECK (state IN ('admitted','processing','verified','partial','suspended')),
          reason_code text NOT NULL,
          authority_identity_id text NOT NULL,
          state_fingerprint text NOT NULL CHECK (state_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          UNIQUE (practice_guide_edition_id,state_sequence)
        );
        INSERT INTO platform.practice_guide_edition_states
          (practice_guide_edition_state_id,practice_guide_edition_id,state_sequence,state,
           reason_code,authority_identity_id,state_fingerprint,recorded_at)
          SELECT gen_random_uuid(),e.practice_guide_edition_id,1,e.status,
            'compat.early_0009_state_recovered',e.admitted_by_identity_id,
            e.provenance_digest,e.admitted_at
          FROM platform.practice_guide_editions e
          WHERE NOT EXISTS (
            SELECT 1 FROM platform.practice_guide_edition_states s
            WHERE s.practice_guide_edition_id=e.practice_guide_edition_id
          );

        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='platform' AND table_name='practice_guidance_units'
              AND column_name='structural_unit_id'
          ) THEN
            IF EXISTS (SELECT 1 FROM platform.practice_guidance_units) THEN
              RAISE EXCEPTION 'Cannot infer structural_unit_id for already-published early 0009 guidance';
            END IF;
            ALTER TABLE platform.practice_guidance_units
              ADD COLUMN structural_unit_id uuid NOT NULL
              REFERENCES platform.practice_guide_structural_units(structural_unit_id)
              ON DELETE RESTRICT;
          END IF;
        END $$;

        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='platform' AND table_name='practice_guidance_conflicts'
              AND column_name='guidance_candidate_id'
          ) THEN
            ALTER TABLE platform.practice_guidance_conflicts
              ADD COLUMN guidance_candidate_id uuid,
              ADD COLUMN candidate_version bigint;
            UPDATE platform.practice_guidance_conflicts c
              SET guidance_candidate_id=u.guidance_candidate_id,
                  candidate_version=u.candidate_version
              FROM platform.practice_guidance_units u
              WHERE u.guidance_unit_id=c.guidance_unit_id
                AND u.version=c.guidance_unit_version;
            ALTER TABLE platform.practice_guidance_conflicts
              ALTER COLUMN guidance_unit_id DROP NOT NULL,
              ALTER COLUMN guidance_unit_version DROP NOT NULL,
              ALTER COLUMN guidance_candidate_id SET NOT NULL,
              ALTER COLUMN candidate_version SET NOT NULL,
              ADD CONSTRAINT practice_guidance_conflicts_candidate_version_fkey
                FOREIGN KEY (guidance_candidate_id,candidate_version)
                REFERENCES platform.practice_guide_candidate_versions(guidance_candidate_id,version)
                ON DELETE RESTRICT,
              ADD CONSTRAINT practice_guidance_conflicts_unit_identity_check
                CHECK ((guidance_unit_id IS NULL)=(guidance_unit_version IS NULL));
          END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS platform.practice_guide_failed_candidate_versions (
          guidance_candidate_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          ingestion_run_id uuid NOT NULL REFERENCES platform.practice_guide_ingestion_runs(ingestion_run_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          page_number integer NOT NULL CHECK (page_number>=1),
          ordinal integer NOT NULL CHECK (ordinal>=1),
          failure_code text NOT NULL,
          failure_field text NOT NULL,
          invalid_region jsonb,
          raw_candidate jsonb NOT NULL,
          failed_candidate_fingerprint text NOT NULL UNIQUE CHECK (failed_candidate_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (guidance_candidate_id,version),
          UNIQUE (ingestion_run_id,page_number,ordinal)
        );
        CREATE TABLE IF NOT EXISTS platform.practice_guide_source_rows (
          source_row_id uuid PRIMARY KEY,
          parent_guidance_candidate_id uuid NOT NULL,
          parent_candidate_version bigint NOT NULL,
          ingestion_run_id uuid NOT NULL REFERENCES platform.practice_guide_ingestion_runs(ingestion_run_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          page_number integer NOT NULL CHECK (page_number>=1),
          row_ordinal integer NOT NULL CHECK (row_ordinal>=1),
          region double precision[] NOT NULL CHECK (cardinality(region)=4),
          printed_ntd text NOT NULL,
          work_or_rd_sections text NOT NULL,
          id_note text NOT NULL,
          layout_profile_version text NOT NULL,
          extraction_digest text NOT NULL CHECK (extraction_digest ~ '^sha256:[a-f0-9]{64}$'),
          parent_failed_receipt_digest text NOT NULL CHECK (parent_failed_receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          source_row_fingerprint text NOT NULL UNIQUE CHECK (source_row_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          UNIQUE (ingestion_run_id,page_number,row_ordinal)
        );
        CREATE TABLE IF NOT EXISTS platform.practice_guide_normative_reference_candidates (
          normative_reference_candidate_id uuid PRIMARY KEY,
          source_row_id uuid NOT NULL UNIQUE REFERENCES platform.practice_guide_source_rows(source_row_id) ON DELETE RESTRICT,
          printed_identifier text NOT NULL,
          printed_title text,
          candidate_fingerprint text NOT NULL UNIQUE CHECK (candidate_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL
        );
        CREATE TABLE IF NOT EXISTS platform.practice_guide_normative_reference_resolutions (
          normative_reference_resolution_id uuid PRIMARY KEY,
          normative_reference_candidate_id uuid NOT NULL UNIQUE REFERENCES platform.practice_guide_normative_reference_candidates(normative_reference_candidate_id) ON DELETE RESTRICT,
          resolution_state text NOT NULL CHECK (resolution_state IN ('resolved','not_found','ambiguous')),
          normative_document_id uuid REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          normative_edition_id uuid REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          uncertainty_code text NOT NULL,
          resolver_version text NOT NULL,
          resolution_fingerprint text NOT NULL UNIQUE CHECK (resolution_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          resolved_at timestamptz NOT NULL,
          CHECK ((resolution_state='resolved')=(normative_document_id IS NOT NULL AND normative_edition_id IS NOT NULL)),
          CHECK ((normative_document_id IS NULL)=(normative_edition_id IS NULL))
        );
        CREATE TABLE IF NOT EXISTS platform.practice_guide_ntd_relevance_assertions (
          ntd_relevance_assertion_id uuid PRIMARY KEY,
          guidance_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL,
          source_row_id uuid NOT NULL UNIQUE REFERENCES platform.practice_guide_source_rows(source_row_id) ON DELETE RESTRICT,
          normative_reference_candidate_id uuid NOT NULL UNIQUE REFERENCES platform.practice_guide_normative_reference_candidates(normative_reference_candidate_id) ON DELETE RESTRICT,
          relevance_summary text NOT NULL,
          document_or_form_type text,
          workflow_stage text,
          applicability_conditions jsonb NOT NULL,
          uncertainty_codes jsonb NOT NULL,
          assertion_fingerprint text NOT NULL UNIQUE CHECK (assertion_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          FOREIGN KEY (guidance_candidate_id,candidate_version) REFERENCES platform.practice_guide_candidate_versions(guidance_candidate_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS platform.practice_guidance_coverage_manifests (
          coverage_manifest_id uuid PRIMARY KEY,
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          ingestion_run_id uuid NOT NULL REFERENCES platform.practice_guide_ingestion_runs(ingestion_run_id) ON DELETE RESTRICT,
          coverage_manifest_version integer NOT NULL CHECK (coverage_manifest_version>=1),
          publication_status text NOT NULL CHECK (publication_status IN ('complete','partial_with_explicit_gaps')),
          expected_page_count integer NOT NULL CHECK (expected_page_count>0),
          terminal_page_count integer NOT NULL CHECK (terminal_page_count>=0),
          page_state_counts jsonb NOT NULL,
          candidate_state_counts jsonb NOT NULL,
          guidance_unit_count integer NOT NULL CHECK (guidance_unit_count>=0),
          gap_count integer NOT NULL CHECK (gap_count>=0),
          conflict_count integer NOT NULL CHECK (conflict_count>=0),
          reconciliation_fingerprint text NOT NULL CHECK (reconciliation_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          manifest_fingerprint text NOT NULL UNIQUE CHECK (manifest_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          UNIQUE (practice_guide_edition_id,coverage_manifest_version),
          CHECK (terminal_page_count<=expected_page_count)
        );
        CREATE TABLE IF NOT EXISTS platform.practice_guidance_gaps (
          guidance_gap_id uuid PRIMARY KEY,
          coverage_manifest_id uuid NOT NULL REFERENCES platform.practice_guidance_coverage_manifests(coverage_manifest_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          page_number integer NOT NULL CHECK (page_number>=1),
          guidance_candidate_id uuid,
          candidate_version bigint,
          gap_code text NOT NULL,
          terminal_state text NOT NULL CHECK (terminal_state IN ('partial_with_gaps','insufficient_evidence','model_failed','technically_blocked')),
          topic text,
          document_or_form_type text,
          field_or_element text,
          searchable_text text NOT NULL,
          search_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian',searchable_text)) STORED,
          content_minimal_parameters jsonb NOT NULL,
          gap_fingerprint text NOT NULL UNIQUE CHECK (gap_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          CHECK ((guidance_candidate_id IS NULL)=(candidate_version IS NULL))
        );
        CREATE INDEX IF NOT EXISTS practice_guidance_gap_search_idx
          ON platform.practice_guidance_gaps USING gin(search_vector);
        """
    )
    for table in NEW_PLATFORM_TABLES:
        op.execute(
            f"DROP TRIGGER IF EXISTS {table}_immutable ON platform.{table}; "
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON platform.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )
        op.execute(f"GRANT SELECT ON platform.{table} TO asd_guidance_gateway_service")
        op.execute(f"GRANT SELECT,INSERT ON platform.{table} TO asd_guidance_ingestion_service")


def downgrade() -> None:
    """No-op: 0009 owns these additive relations on every clean installation."""
