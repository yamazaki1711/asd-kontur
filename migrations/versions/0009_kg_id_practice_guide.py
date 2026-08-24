"""Create permanent methodological-practice-guide knowledge layer.

Revision ID: 0009_kg_id
Revises: 0008_wp14
Create Date: 2026-08-23
"""

from __future__ import annotations

import os

from alembic import op

revision = "0009_kg_id"
down_revision = "0008_wp14"
branch_labels = None
depends_on = None

PLATFORM_TABLES = (
    "practice_guides",
    "practice_guide_editions",
    "practice_guide_edition_states",
    "practice_guide_structural_units",
    "practice_guide_page_manifests",
    "practice_guide_execution_profiles",
    "practice_guide_ingestion_runs",
    "practice_guide_ingestion_run_states",
    "practice_guide_candidate_versions",
    "practice_guide_validation_results",
    "practice_guide_verifications",
    "practice_guide_page_terminal_receipts",
    "practice_guide_ingestion_reconciliations",
    "practice_guidance_units",
    "practice_guidance_evidence",
    "practice_guidance_conflicts",
    "practice_guidance_uncertainties",
)

PROJECTION_TABLES = (
    "practice_guidance_lexical_versions",
    "practice_guidance_lexical_entries",
)


def upgrade() -> None:
    _extend_platform_source_kind()
    _create_roles()
    _create_guide_canon()
    _create_ingestion_ledger()
    _create_guidance_canon()
    _create_projection()
    _apply_guards_and_grants()


def _extend_platform_source_kind() -> None:
    op.execute(
        "ALTER TABLE platform.source_artifacts DROP CONSTRAINT source_artifacts_source_kind_check"
    )
    op.execute(
        "ALTER TABLE platform.source_artifacts ADD CONSTRAINT source_artifacts_source_kind_check "
        "CHECK (source_kind IN ('normative_document','legal_act','official_reference',"
        "'universal_template','methodological_practice_guide'))"
    )


def _create_roles() -> None:
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_guidance_ingestion_service') "
        "THEN CREATE ROLE asd_guidance_ingestion_service NOLOGIN NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOINHERIT; END IF; END $$"
    )
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_guidance_gateway_service') "
        "THEN CREATE ROLE asd_guidance_gateway_service NOLOGIN NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOINHERIT; END IF; END $$"
    )


def _create_guide_canon() -> None:
    op.execute(
        """
        CREATE TABLE platform.practice_guides (
          practice_guide_id uuid PRIMARY KEY,
          source_artifact_id uuid NOT NULL UNIQUE REFERENCES platform.source_artifacts(source_artifact_id) ON DELETE RESTRICT,
          guide_key text NOT NULL UNIQUE,
          title text NOT NULL,
          authority_layer text NOT NULL CHECK (authority_layer='methodological_guidance'),
          status text NOT NULL CHECK (status IN ('registered','active','suspended','retired')),
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE platform.practice_guide_editions (
          practice_guide_edition_id uuid PRIMARY KEY,
          practice_guide_id uuid NOT NULL REFERENCES platform.practice_guides(practice_guide_id) ON DELETE RESTRICT,
          edition_ordinal bigint NOT NULL CHECK (edition_ordinal>=1),
          edition_label text NOT NULL,
          source_version_id uuid NOT NULL UNIQUE REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          source_digest text NOT NULL CHECK (source_digest ~ '^sha256:[a-f0-9]{64}$'),
          page_count integer NOT NULL CHECK (page_count>0),
          status text NOT NULL CHECK (status IN ('admitted','processing','verified','partial','suspended')),
          provenance_payload jsonb NOT NULL,
          provenance_digest text NOT NULL CHECK (provenance_digest ~ '^sha256:[a-f0-9]{64}$'),
          admitted_by_identity_id text NOT NULL,
          admitted_at timestamptz NOT NULL,
          UNIQUE (practice_guide_id,edition_ordinal),
          UNIQUE (practice_guide_id,edition_label)
        );
        CREATE TABLE platform.practice_guide_structural_units (
          structural_unit_id uuid PRIMARY KEY,
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          parent_structural_unit_id uuid REFERENCES platform.practice_guide_structural_units(structural_unit_id) ON DELETE RESTRICT,
          unit_kind text NOT NULL CHECK (unit_kind IN ('book','part','chapter','section','topic','page_region')),
          structural_path text NOT NULL,
          title text NOT NULL,
          start_page integer NOT NULL CHECK (start_page>=1),
          end_page integer NOT NULL CHECK (end_page>=start_page),
          ordinal bigint NOT NULL CHECK (ordinal>=1),
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          UNIQUE (practice_guide_edition_id,structural_path)
        );
        CREATE TABLE platform.practice_guide_edition_states (
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
        CREATE TABLE platform.practice_guide_page_manifests (
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          page_number integer NOT NULL CHECK (page_number>=1),
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          page_digest text NOT NULL CHECK (page_digest ~ '^sha256:[a-f0-9]{64}$'),
          width_points double precision NOT NULL CHECK (width_points>0),
          height_points double precision NOT NULL CHECK (height_points>0),
          rotation integer NOT NULL,
          native_text_characters integer NOT NULL CHECK (native_text_characters>=0),
          image_count integer NOT NULL CHECK (image_count>=0),
          content_kind text NOT NULL CHECK (content_kind IN ('native_text','raster_image','mixed','blank_or_technical')),
          render_required boolean NOT NULL,
          previous_page integer,
          next_page integer,
          technical_flags text[] NOT NULL,
          manifest_fingerprint text NOT NULL CHECK (manifest_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (practice_guide_edition_id,page_number),
          CHECK (previous_page IS NULL OR previous_page=page_number-1),
          CHECK (next_page IS NULL OR next_page=page_number+1)
        );
        """
    )


def _create_ingestion_ledger() -> None:
    op.execute(
        """
        CREATE TABLE platform.practice_guide_execution_profiles (
          execution_profile_id uuid PRIMARY KEY,
          profile_version text NOT NULL CHECK (lower(profile_version)<>'latest'),
          provider text NOT NULL,
          model_identity text NOT NULL,
          model_revision text NOT NULL CHECK (lower(model_revision)<>'latest'),
          model_digest text NOT NULL CHECK (model_digest ~ '^sha256:[a-f0-9]{64}$'),
          execution_format text NOT NULL,
          quantization text NOT NULL CHECK (quantization IN ('8bit','bf16')),
          runtime_version text NOT NULL,
          prompt_version text NOT NULL,
          schema_version text NOT NULL,
          preprocessing_version text NOT NULL,
          renderer_version text NOT NULL,
          verification_policy_version text NOT NULL,
          deterministic_decoding boolean NOT NULL CHECK (deterministic_decoding),
          qualification_state text NOT NULL CHECK (qualification_state IN ('evaluation','qualified_development','suspended','revoked')),
          qualification_evidence_digest text CHECK (qualification_evidence_digest ~ '^sha256:[a-f0-9]{64}$'),
          profile_fingerprint text NOT NULL UNIQUE CHECK (profile_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          UNIQUE (provider,model_revision,quantization,profile_version)
        );
        CREATE TABLE platform.practice_guide_ingestion_runs (
          ingestion_run_id uuid PRIMARY KEY,
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          execution_profile_id uuid NOT NULL REFERENCES platform.practice_guide_execution_profiles(execution_profile_id) ON DELETE RESTRICT,
          expected_page_count integer NOT NULL CHECK (expected_page_count>0),
          pass_a_prompt_version text NOT NULL,
          pass_b_prompt_version text NOT NULL,
          validator_version text NOT NULL,
          idempotency_key text NOT NULL UNIQUE,
          state text NOT NULL CHECK (state IN ('qualifying','qualified','processing','reconciling','complete','partial','blocked','failed')),
          started_by_identity_id text NOT NULL,
          started_at timestamptz NOT NULL,
          completed_at timestamptz,
          run_fingerprint text NOT NULL CHECK (run_fingerprint ~ '^sha256:[a-f0-9]{64}$')
        );
        CREATE TABLE platform.practice_guide_ingestion_run_states (
          ingestion_run_state_id uuid PRIMARY KEY,
          ingestion_run_id uuid NOT NULL REFERENCES platform.practice_guide_ingestion_runs(ingestion_run_id) ON DELETE RESTRICT,
          state_sequence bigint NOT NULL CHECK (state_sequence>=1),
          state text NOT NULL CHECK (state IN ('qualifying','qualified','processing','reconciling','complete','partial','blocked','failed')),
          reason_code text NOT NULL,
          authority_identity_id text NOT NULL,
          state_fingerprint text NOT NULL CHECK (state_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          UNIQUE (ingestion_run_id,state_sequence)
        );
        CREATE TABLE platform.practice_guide_candidate_versions (
          guidance_candidate_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          ingestion_run_id uuid NOT NULL REFERENCES platform.practice_guide_ingestion_runs(ingestion_run_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          page_number integer NOT NULL CHECK (page_number>=1),
          region double precision[] NOT NULL CHECK (cardinality(region)=4),
          guidance_kind text NOT NULL,
          section text NOT NULL,
          topic text NOT NULL,
          document_or_form_type text,
          workflow_stage text,
          field_or_element text,
          instruction text NOT NULL,
          required_inputs jsonb NOT NULL,
          evidence_requirements jsonb NOT NULL,
          author_role_claims jsonb NOT NULL,
          common_error text,
          recommended_practice text,
          visual_example_region double precision[],
          applicability_conditions jsonb NOT NULL,
          limitations jsonb NOT NULL,
          uncertainties jsonb NOT NULL,
          model_profile_fingerprint text NOT NULL CHECK (model_profile_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          parent_version bigint,
          candidate_fingerprint text NOT NULL CHECK (candidate_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (guidance_candidate_id,version),
          FOREIGN KEY (guidance_candidate_id,parent_version) REFERENCES platform.practice_guide_candidate_versions(guidance_candidate_id,version) ON DELETE RESTRICT,
          CHECK (parent_version IS NULL OR parent_version<version),
          CHECK (visual_example_region IS NULL OR cardinality(visual_example_region)=4)
        );
        CREATE TABLE platform.practice_guide_validation_results (
          validation_result_id uuid PRIMARY KEY,
          guidance_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL,
          validator_identity text NOT NULL,
          validator_version text NOT NULL,
          failure_code text NOT NULL,
          field_path text NOT NULL,
          blocking boolean NOT NULL,
          repairable boolean NOT NULL,
          content_minimal_parameters jsonb NOT NULL,
          recorded_at timestamptz NOT NULL,
          UNIQUE (guidance_candidate_id,candidate_version,validator_version,failure_code,field_path),
          FOREIGN KEY (guidance_candidate_id,candidate_version) REFERENCES platform.practice_guide_candidate_versions(guidance_candidate_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.practice_guide_verifications (
          verification_id uuid PRIMARY KEY,
          guidance_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL,
          disposition text NOT NULL CHECK (disposition IN ('supported','contradicted','insufficient')),
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          page_number integer NOT NULL CHECK (page_number>=1),
          region double precision[] NOT NULL CHECK (cardinality(region)=4),
          model_profile_fingerprint text NOT NULL CHECK (model_profile_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          verification_prompt_version text NOT NULL,
          result_digest text NOT NULL CHECK (result_digest ~ '^sha256:[a-f0-9]{64}$'),
          verified_at timestamptz NOT NULL,
          UNIQUE (guidance_candidate_id,candidate_version),
          FOREIGN KEY (guidance_candidate_id,candidate_version) REFERENCES platform.practice_guide_candidate_versions(guidance_candidate_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.practice_guide_page_terminal_receipts (
          ingestion_run_id uuid NOT NULL REFERENCES platform.practice_guide_ingestion_runs(ingestion_run_id) ON DELETE RESTRICT,
          page_number integer NOT NULL CHECK (page_number>=1),
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          terminal_state text NOT NULL CHECK (terminal_state IN ('verified','no_methodological_content','unresolved','model_failed','technically_blocked')),
          pass_a_attempt_ref text,
          pass_b_attempt_refs text[] NOT NULL,
          candidate_count integer NOT NULL CHECK (candidate_count>=0),
          verified_count integer NOT NULL CHECK (verified_count>=0),
          unresolved_count integer NOT NULL CHECK (unresolved_count>=0),
          receipt_digest text NOT NULL CHECK (receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (ingestion_run_id,page_number),
          CHECK (verified_count+unresolved_count<=candidate_count),
          CHECK (terminal_state<>'verified' OR verified_count>0),
          CHECK (terminal_state<>'no_methodological_content' OR candidate_count=0)
        );
        CREATE TABLE platform.practice_guide_ingestion_reconciliations (
          ingestion_reconciliation_id uuid PRIMARY KEY,
          ingestion_run_id uuid NOT NULL UNIQUE REFERENCES platform.practice_guide_ingestion_runs(ingestion_run_id) ON DELETE RESTRICT,
          expected_page_count integer NOT NULL CHECK (expected_page_count>0),
          terminal_page_count integer NOT NULL CHECK (terminal_page_count>=0),
          state_counts jsonb NOT NULL,
          complete boolean NOT NULL,
          reconciliation_fingerprint text NOT NULL CHECK (reconciliation_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          reconciled_by_identity_id text NOT NULL,
          reconciled_at timestamptz NOT NULL,
          CHECK (NOT complete OR expected_page_count=terminal_page_count)
        );
        """
    )


def _create_guidance_canon() -> None:
    op.execute(
        """
        CREATE TABLE platform.practice_guidance_units (
          guidance_unit_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          structural_unit_id uuid NOT NULL REFERENCES platform.practice_guide_structural_units(structural_unit_id) ON DELETE RESTRICT,
          guidance_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL,
          guidance_kind text NOT NULL,
          normalized_instruction text NOT NULL,
          section text NOT NULL,
          topic text NOT NULL,
          document_or_form_type text,
          workflow_stage text,
          field_or_element text,
          required_inputs jsonb NOT NULL,
          evidence_requirements jsonb NOT NULL,
          author_role_claims jsonb NOT NULL,
          common_error text,
          recommended_practice text,
          applicability_conditions jsonb NOT NULL,
          limitations jsonb NOT NULL,
          authority_layer text NOT NULL CHECK (authority_layer='methodological_guidance'),
          validation_status text NOT NULL CHECK (validation_status='verified'),
          publication_decision_ref text NOT NULL,
          curator_identity_id text NOT NULL,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          published_at timestamptz NOT NULL,
          PRIMARY KEY (guidance_unit_id,version),
          UNIQUE (guidance_candidate_id,candidate_version),
          FOREIGN KEY (guidance_candidate_id,candidate_version) REFERENCES platform.practice_guide_candidate_versions(guidance_candidate_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.practice_guidance_evidence (
          guidance_evidence_id uuid PRIMARY KEY,
          guidance_unit_id uuid NOT NULL,
          guidance_unit_version bigint NOT NULL,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          source_locator_id uuid NOT NULL REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          page_number integer NOT NULL CHECK (page_number>=1),
          region double precision[] NOT NULL CHECK (cardinality(region)=4),
          fragment_digest text NOT NULL CHECK (fragment_digest ~ '^sha256:[a-f0-9]{64}$'),
          evidence_role text NOT NULL CHECK (evidence_role IN ('primary','visual_example','cross_reference')),
          verified_at timestamptz NOT NULL,
          UNIQUE (guidance_unit_id,guidance_unit_version,source_locator_id,evidence_role),
          FOREIGN KEY (guidance_unit_id,guidance_unit_version) REFERENCES platform.practice_guidance_units(guidance_unit_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.practice_guidance_conflicts (
          guidance_conflict_id uuid PRIMARY KEY,
          guidance_unit_id uuid NOT NULL,
          guidance_unit_version bigint NOT NULL,
          conflicting_authority_layer text NOT NULL,
          conflicting_subject_ref text NOT NULL,
          conflict_type text NOT NULL,
          state text NOT NULL CHECK (state IN ('open','resolved','superseded')),
          uncertainty_ref text NOT NULL,
          decision_ref text,
          recorded_at timestamptz NOT NULL,
          FOREIGN KEY (guidance_unit_id,guidance_unit_version) REFERENCES platform.practice_guidance_units(guidance_unit_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.practice_guidance_uncertainties (
          guidance_uncertainty_id uuid PRIMARY KEY,
          guidance_unit_id uuid NOT NULL,
          guidance_unit_version bigint NOT NULL,
          uncertainty_code text NOT NULL,
          state text NOT NULL CHECK (state IN ('open','resolved','superseded')),
          content_minimal_parameters jsonb NOT NULL,
          recorded_at timestamptz NOT NULL,
          FOREIGN KEY (guidance_unit_id,guidance_unit_version) REFERENCES platform.practice_guidance_units(guidance_unit_id,version) ON DELETE RESTRICT
        );
        """
    )


def _create_projection() -> None:
    op.execute(
        """
        CREATE TABLE projection.practice_guidance_lexical_versions (
          lexical_version_id uuid PRIMARY KEY,
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          projection_contract_version text NOT NULL,
          source_fingerprint text NOT NULL CHECK (source_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          state text NOT NULL CHECK (state IN ('building','ready','stale','failed','empty')),
          entry_count bigint NOT NULL CHECK (entry_count>=0),
          built_at timestamptz,
          CHECK (state<>'ready' OR built_at IS NOT NULL)
        );
        CREATE TABLE projection.practice_guidance_lexical_entries (
          lexical_version_id uuid NOT NULL REFERENCES projection.practice_guidance_lexical_versions(lexical_version_id) ON DELETE CASCADE,
          guidance_unit_id uuid NOT NULL,
          guidance_unit_version bigint NOT NULL,
          searchable_text text NOT NULL,
          search_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian',searchable_text)) STORED,
          entry_digest text NOT NULL CHECK (entry_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (lexical_version_id,guidance_unit_id,guidance_unit_version),
          FOREIGN KEY (guidance_unit_id,guidance_unit_version) REFERENCES platform.practice_guidance_units(guidance_unit_id,version) ON DELETE RESTRICT
        );
        CREATE INDEX practice_guidance_lexical_search_idx
          ON projection.practice_guidance_lexical_entries USING gin(search_vector);
        """
    )


def _apply_guards_and_grants() -> None:
    op.execute(
        "GRANT USAGE ON SCHEMA platform,projection TO asd_guidance_ingestion_service,asd_guidance_gateway_service"
    )
    op.execute("GRANT USAGE ON SCHEMA audit TO asd_guidance_gateway_service")
    op.execute("GRANT INSERT ON audit.platform_records TO asd_guidance_gateway_service")
    for table in PLATFORM_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON platform.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )
        op.execute(f"GRANT SELECT ON platform.{table} TO asd_guidance_gateway_service")
        op.execute(f"GRANT SELECT,INSERT ON platform.{table} TO asd_guidance_ingestion_service")
    for table in PROJECTION_TABLES:
        op.execute(f"GRANT SELECT ON projection.{table} TO asd_guidance_gateway_service")
        op.execute(
            f"GRANT SELECT,INSERT,UPDATE,DELETE ON projection.{table} TO asd_guidance_ingestion_service"
        )
    op.execute(
        "GRANT SELECT,INSERT ON platform.source_artifacts,platform.acquisition_attempts,platform.objects,"
        "platform.object_receipts,platform.source_versions,platform.source_locators,platform.evidence_links "
        "TO asd_guidance_ingestion_service"
    )
    op.execute(
        "GRANT SELECT ON platform.source_versions,platform.source_locators,platform.objects "
        "TO asd_guidance_gateway_service"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "KG-ID-01 downgrade is destructive and allowed only in a disposable database"
        )
    for table in reversed(PROJECTION_TABLES):
        op.execute(f"DROP TABLE projection.{table}")
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE platform.{table}")
    op.execute(
        "ALTER TABLE platform.source_artifacts DROP CONSTRAINT source_artifacts_source_kind_check"
    )
    op.execute(
        "ALTER TABLE platform.source_artifacts ADD CONSTRAINT source_artifacts_source_kind_check "
        "CHECK (source_kind IN ('normative_document','legal_act','official_reference','universal_template'))"
    )
