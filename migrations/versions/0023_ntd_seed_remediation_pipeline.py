"""Add the source-first durable NTD remediation processing lineage.

Revision ID: 0023_ntd_remediation
Revises: 0022_pd_rd_normative_authority
Create Date: 2026-08-26
"""

from __future__ import annotations

from alembic import op

revision = "0023_ntd_remediation"
down_revision = "0022_pd_rd_normative_authority"
branch_labels = None
depends_on = None

PLATFORM_TABLES = (
    "ntd_seed_remediation_decisions",
    "ntd_seed_identity_reconciliations",
    "ntd_identity_resolution_versions",
    "ntd_processing_job_attempts",
    "normative_artifact_validations",
    "normative_representation_pages",
    "normative_structural_fragments",
    "normative_table_cells",
    "normative_provision_semantics",
    "normative_provision_verification_outcomes",
    "normative_amendment_operations",
    "ntd_external_extraction_receipts",
    "ntd_publication_manifests",
    "ntd_document_acceptance_receipts",
)


def upgrade() -> None:
    _extend_structure_contracts()
    _create_decision_and_resolution_lineage()
    _create_durable_processing_lineage()
    _create_representation_and_structure_lineage()
    _create_verification_and_publication_lineage()
    _apply_security()


def _extend_structure_contracts() -> None:
    op.execute(
        """
        ALTER TABLE platform.structural_units
          DROP CONSTRAINT structural_units_ntd_seed_unit_type_ck;
        ALTER TABLE platform.structural_units
          ADD CONSTRAINT structural_units_ntd_remediation_unit_type_ck
          CHECK (unit_type IN (
            'document','section','subsection','clause','subclause','item','table',
            'table_row','table_cell','figure','formula','note','appendix',
            'definition_scope','form','edition_metadata','other'
          ));
        ALTER TABLE platform.cross_references DROP CONSTRAINT cross_references_relation_type_check;
        ALTER TABLE platform.cross_references ADD CONSTRAINT cross_references_relation_type_check
          CHECK (relation_type IN (
            'references','defines','requires','excepts','applies_if','amends','replaces',
            'supersedes','implements','conflicts_with'
          ));
        """
    )


def _create_decision_and_resolution_lineage() -> None:
    op.execute(
        """
        CREATE TABLE platform.ntd_seed_remediation_decisions (
          remediation_decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          prior_seed_manifest_id uuid NOT NULL,
          prior_seed_manifest_version bigint NOT NULL,
          logical_manifest_fingerprint text NOT NULL
            CHECK (logical_manifest_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          decision_key text NOT NULL,
          status text NOT NULL CHECK (status IN ('in_progress','partial','pass','blocked','data_defect')),
          reopened_defect_codes text[] NOT NULL CHECK (cardinality(reopened_defect_codes)>0),
          reason text NOT NULL,
          canonical_commit text NOT NULL CHECK (canonical_commit ~ '^[a-f0-9]{40}$'),
          environment_fingerprint text NOT NULL
            CHECK (environment_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          prior_receipt_fingerprints text[] NOT NULL,
          supersedes_version bigint,
          decision_fingerprint text NOT NULL UNIQUE
            CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          decided_at timestamptz NOT NULL,
          PRIMARY KEY (remediation_decision_id,version),
          FOREIGN KEY (prior_seed_manifest_id,prior_seed_manifest_version)
            REFERENCES platform.ntd_seed_manifests(seed_manifest_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (remediation_decision_id,supersedes_version)
            REFERENCES platform.ntd_seed_remediation_decisions(remediation_decision_id,version)
            ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR
                 (version>1 AND supersedes_version=version-1))
        );
        CREATE TABLE platform.ntd_seed_identity_reconciliations (
          identity_reconciliation_id uuid PRIMARY KEY,
          remediation_decision_id uuid NOT NULL,
          remediation_decision_version bigint NOT NULL,
          legacy_stable_identity_key text NOT NULL,
          canonical_stable_identity_key text NOT NULL,
          practice_guide_reference_ids uuid[] NOT NULL
            CHECK (cardinality(practice_guide_reference_ids)>0),
          printed_designations text[] NOT NULL CHECK (cardinality(printed_designations)>0),
          identity_status text NOT NULL CHECK (identity_status IN ('resolved','ambiguous','conflicted')),
          decision_basis jsonb NOT NULL,
          reconciliation_fingerprint text NOT NULL UNIQUE
            CHECK (reconciliation_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          FOREIGN KEY (remediation_decision_id,remediation_decision_version)
            REFERENCES platform.ntd_seed_remediation_decisions(remediation_decision_id,version)
            ON DELETE RESTRICT,
          UNIQUE (remediation_decision_id,remediation_decision_version,canonical_stable_identity_key)
        );
        CREATE TABLE platform.ntd_identity_resolution_versions (
          identity_resolution_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          identity_reconciliation_id uuid NOT NULL
            REFERENCES platform.ntd_seed_identity_reconciliations(identity_reconciliation_id)
            ON DELETE RESTRICT,
          provider text NOT NULL CHECK (provider IN (
            'minstroy_catalogue','rosstandart_fund','official_legal_publication',
            'government_portal','discovery_reference_only'
          )),
          transport_profile text NOT NULL CHECK (transport_profile IN ('direct','environment_proxy')),
          official_record_id text,
          official_record_url text,
          official_record_digest text
            CHECK (official_record_digest IS NULL OR official_record_digest ~ '^sha256:[a-f0-9]{64}$'),
          resolution_status text NOT NULL CHECK (resolution_status IN (
            'resolved_exact','resolved_superseded','ambiguous_official_records',
            'official_metadata_only','official_artifact_unavailable','official_access_blocked',
            'not_found_official','exact_edition_not_found','edition_conflict',
            'supersession_unresolved','download_failed','artifact_invalid','parse_partial',
            'parsed_verified','blocked_deterministic_failure'
          )),
          normative_document_id uuid
            REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          normative_edition_id uuid
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          normative_artifact_ids uuid[] NOT NULL DEFAULT '{}',
          failure_code text,
          diagnostic jsonb NOT NULL,
          environment_fingerprint text NOT NULL
            CHECK (environment_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          supersedes_version bigint,
          resolution_fingerprint text NOT NULL UNIQUE
            CHECK (resolution_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (identity_resolution_id,version),
          FOREIGN KEY (identity_resolution_id,supersedes_version)
            REFERENCES platform.ntd_identity_resolution_versions(identity_resolution_id,version)
            ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR
                 (version>1 AND supersedes_version=version-1)),
          CHECK ((normative_edition_id IS NULL) OR (normative_document_id IS NOT NULL))
        );
        """
    )


def _create_durable_processing_lineage() -> None:
    op.execute(
        """
        CREATE TABLE platform.ntd_processing_jobs (
          ntd_processing_job_id uuid PRIMARY KEY,
          identity_reconciliation_id uuid NOT NULL
            REFERENCES platform.ntd_seed_identity_reconciliations(identity_reconciliation_id)
            ON DELETE RESTRICT,
          normative_artifact_id uuid
            REFERENCES platform.normative_artifacts(normative_artifact_id) ON DELETE RESTRICT,
          stage text NOT NULL CHECK (stage IN (
            'admission','representation_inventory','native_extraction','selective_recovery',
            'structural_reconstruction','provision_extraction','reference_resolution',
            'amendment_resolution','deterministic_verification','canonical_publication',
            'projection_rebuild','gateway_acceptance','rule_qualification'
          )),
          input_manifest_digest text NOT NULL CHECK (input_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          idempotency_key text NOT NULL,
          state text NOT NULL CHECK (state IN (
            'queued','leased','running','succeeded','failed','cancelled','reconciliation_required'
          )),
          priority integer NOT NULL DEFAULT 100,
          eligible_at timestamptz NOT NULL,
          started_at timestamptz,
          heartbeat_at timestamptz,
          completed_at timestamptz,
          attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count>=0),
          max_attempts integer NOT NULL CHECK (max_attempts BETWEEN 1 AND 5),
          retry_policy_version text NOT NULL CHECK (lower(retry_policy_version)<>'latest'),
          lease_owner text,
          lease_generation bigint NOT NULL DEFAULT 0 CHECK (lease_generation>=0),
          lease_expires_at timestamptz,
          cancellation_state text NOT NULL DEFAULT 'none'
            CHECK (cancellation_state IN ('none','requested','acknowledged')),
          typed_failure_code text,
          terminal_receipt_fingerprint text
            CHECK (terminal_receipt_fingerprint IS NULL OR
                   terminal_receipt_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          CHECK ((state IN ('leased','running'))=(lease_owner IS NOT NULL)),
          CHECK ((state IN ('succeeded','failed','cancelled','reconciliation_required'))=
                 (terminal_receipt_fingerprint IS NOT NULL)),
          UNIQUE (identity_reconciliation_id,normative_artifact_id,stage,input_manifest_digest),
          UNIQUE (idempotency_key)
        );
        CREATE INDEX ntd_processing_jobs_claim_idx ON platform.ntd_processing_jobs
          (priority,eligible_at,ntd_processing_job_id)
          WHERE state='queued';
        CREATE TABLE platform.ntd_processing_job_attempts (
          ntd_processing_attempt_id uuid PRIMARY KEY,
          ntd_processing_job_id uuid NOT NULL
            REFERENCES platform.ntd_processing_jobs(ntd_processing_job_id) ON DELETE RESTRICT,
          attempt_number integer NOT NULL CHECK (attempt_number>=1),
          lease_generation bigint NOT NULL CHECK (lease_generation>=1),
          processor_identity text NOT NULL,
          tool_profile_version text NOT NULL CHECK (lower(tool_profile_version)<>'latest'),
          input_digest text NOT NULL CHECK (input_digest ~ '^sha256:[a-f0-9]{64}$'),
          output_digest text CHECK (output_digest ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN (
            'started','succeeded','failed','cancelled','reconciliation_required'
          )),
          failure_code text,
          usage_receipt jsonb NOT NULL DEFAULT '{}',
          started_at timestamptz NOT NULL,
          completed_at timestamptz,
          attempt_fingerprint text NOT NULL UNIQUE
            CHECK (attempt_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          UNIQUE (ntd_processing_job_id,attempt_number),
          CHECK ((status='started')=(completed_at IS NULL))
        );
        """
    )


def _create_representation_and_structure_lineage() -> None:
    op.execute(
        """
        CREATE TABLE platform.normative_artifact_validations (
          artifact_validation_id uuid PRIMARY KEY,
          normative_artifact_id uuid NOT NULL
            REFERENCES platform.normative_artifacts(normative_artifact_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL
            REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          declared_media_type text,
          detected_media_type text NOT NULL,
          byte_length bigint NOT NULL CHECK (byte_length>0),
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          representation_version text,
          encryption_status text NOT NULL,
          signature_status text NOT NULL,
          page_count integer CHECK (page_count>=1),
          embedded_file_count integer NOT NULL DEFAULT 0 CHECK (embedded_file_count>=0),
          active_content_status text NOT NULL,
          title_identity_status text NOT NULL,
          validation_status text NOT NULL CHECK (validation_status IN (
            'supported','insufficient','quarantined','rejected'
          )),
          observations text[] NOT NULL,
          validator_version text NOT NULL CHECK (lower(validator_version)<>'latest'),
          validation_fingerprint text NOT NULL UNIQUE
            CHECK (validation_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          validated_at timestamptz NOT NULL,
          UNIQUE (normative_artifact_id,validator_version)
        );
        CREATE TABLE platform.normative_representation_pages (
          normative_page_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          normative_artifact_id uuid NOT NULL
            REFERENCES platform.normative_artifacts(normative_artifact_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL
            REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          page_index integer NOT NULL CHECK (page_index>=1),
          printed_page_label text,
          representation_kind text NOT NULL CHECK (representation_kind IN (
            'native_text','vector','raster','mixed','existing_ocr','damaged_native',
            'rotated','table_heavy','formula_heavy','blank','render_failure','unsupported'
          )),
          width_points numeric NOT NULL CHECK (width_points>0),
          height_points numeric NOT NULL CHECK (height_points>0),
          rotation_degrees integer NOT NULL CHECK (rotation_degrees IN (0,90,180,270)),
          native_text_character_count bigint NOT NULL CHECK (native_text_character_count>=0),
          native_text_coverage numeric NOT NULL CHECK (native_text_coverage BETWEEN 0 AND 1),
          render_digest text CHECK (render_digest ~ '^sha256:[a-f0-9]{64}$'),
          extraction_route text NOT NULL CHECK (extraction_route IN (
            'native','polza_candidate','local_targeted_qwen_candidate','blocked','not_required'
          )),
          terminal_outcome text NOT NULL CHECK (terminal_outcome IN (
            'native_complete','recovery_complete','blank_verified','unsupported','failed','quarantined'
          )),
          inventory_profile_version text NOT NULL CHECK (lower(inventory_profile_version)<>'latest'),
          page_fingerprint text NOT NULL UNIQUE CHECK (page_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          supersedes_version bigint,
          PRIMARY KEY (normative_page_id,version),
          UNIQUE (normative_artifact_id,page_index,version),
          FOREIGN KEY (normative_page_id,supersedes_version)
            REFERENCES platform.normative_representation_pages(normative_page_id,version)
            ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR
                 (version>1 AND supersedes_version=version-1))
        );
        CREATE TABLE platform.normative_structural_fragments (
          structural_fragment_id uuid PRIMARY KEY,
          structural_unit_id uuid NOT NULL
            REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL
            REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          source_locator_ids uuid[] NOT NULL CHECK (cardinality(source_locator_ids)>0),
          exact_heading text,
          exact_number text,
          raw_text text NOT NULL,
          normalized_search_text text NOT NULL,
          source_fragment_digest text NOT NULL CHECK (source_fragment_digest ~ '^sha256:[a-f0-9]{64}$'),
          extraction_method text NOT NULL CHECK (extraction_method IN (
            'native_pdf_layout','native_html_structure','polza_public_ntd_page',
            'local_targeted_qwen_verification','deterministic_amendment_materialization'
          )),
          extraction_profile_version text NOT NULL CHECK (lower(extraction_profile_version)<>'latest'),
          extraction_lineage jsonb NOT NULL,
          fragment_fingerprint text NOT NULL UNIQUE CHECK (fragment_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL
        );
        CREATE TABLE platform.normative_table_cells (
          normative_table_cell_id uuid PRIMARY KEY,
          table_structural_unit_id uuid NOT NULL
            REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          source_locator_id uuid NOT NULL
            REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          row_index integer NOT NULL CHECK (row_index>=1),
          column_index integer NOT NULL CHECK (column_index>=1),
          row_span integer NOT NULL DEFAULT 1 CHECK (row_span>=1),
          column_span integer NOT NULL DEFAULT 1 CHECK (column_span>=1),
          raw_text text NOT NULL,
          normalized_search_text text NOT NULL,
          unit_text text,
          cell_fingerprint text NOT NULL UNIQUE CHECK (cell_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          UNIQUE (table_structural_unit_id,row_index,column_index)
        );
        """
    )


def _create_verification_and_publication_lineage() -> None:
    op.execute(
        """
        CREATE TABLE platform.normative_provision_semantics (
          provision_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL,
          normalized_proposition jsonb NOT NULL,
          subject jsonb NOT NULL,
          predicate jsonb NOT NULL,
          object_value jsonb NOT NULL,
          modality text NOT NULL CHECK (modality IN (
            'mandatory','prohibition','permission','recommendation','definition',
            'condition','exception','procedure','deadline','tolerance','formula','reference','amendment'
          )),
          conditions jsonb NOT NULL,
          exclusions jsonb NOT NULL,
          applicability jsonb NOT NULL,
          units_dimensions jsonb NOT NULL,
          referenced_designations text[] NOT NULL,
          uncertainty_codes text[] NOT NULL,
          semantics_fingerprint text NOT NULL UNIQUE
            CHECK (semantics_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (provision_candidate_id,candidate_version),
          FOREIGN KEY (provision_candidate_id,candidate_version)
            REFERENCES platform.normative_provision_candidates(provision_candidate_id,candidate_version)
            ON DELETE RESTRICT
        );
        CREATE TABLE platform.normative_provision_verification_outcomes (
          provision_verification_id uuid PRIMARY KEY,
          provision_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL,
          outcome text NOT NULL CHECK (outcome IN (
            'supported','contradicted','insufficient','superseded','quarantined'
          )),
          critical_token_checks jsonb NOT NULL,
          structural_checks jsonb NOT NULL,
          conflict_refs jsonb NOT NULL,
          verification_method text NOT NULL,
          verifier_version text NOT NULL CHECK (lower(verifier_version)<>'latest'),
          verification_fingerprint text NOT NULL UNIQUE
            CHECK (verification_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          verified_by_identity_id text NOT NULL,
          verified_at timestamptz NOT NULL,
          FOREIGN KEY (provision_candidate_id,candidate_version)
            REFERENCES platform.normative_provision_candidates(provision_candidate_id,candidate_version)
            ON DELETE RESTRICT,
          UNIQUE (provision_candidate_id,candidate_version,verifier_version)
        );
        CREATE TABLE platform.normative_amendment_operations (
          amendment_operation_id uuid PRIMARY KEY,
          amending_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          source_provision_id uuid NOT NULL,
          source_provision_version bigint NOT NULL,
          target_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          target_structural_path text NOT NULL,
          operation_kind text NOT NULL CHECK (operation_kind IN (
            'replace_text','exclude','add','restate','modify_table','modify_appendix',
            'modify_applicability','modify_effective_date'
          )),
          expected_source_digest text NOT NULL CHECK (expected_source_digest ~ '^sha256:[a-f0-9]{64}$'),
          operation_payload jsonb NOT NULL,
          resolution_status text NOT NULL CHECK (resolution_status IN (
            'resolved','ambiguous_target','source_mismatch','blocked'
          )),
          operation_fingerprint text NOT NULL UNIQUE
            CHECK (operation_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          FOREIGN KEY (source_provision_id,source_provision_version)
            REFERENCES platform.normative_provision_versions(normative_provision_id,version)
            ON DELETE RESTRICT
        );
        CREATE TABLE platform.ntd_external_extraction_receipts (
          external_extraction_receipt_id uuid PRIMARY KEY,
          normative_page_id uuid NOT NULL,
          normative_page_version bigint NOT NULL CHECK (normative_page_version>=1),
          provider_key text NOT NULL CHECK (provider_key='provider.external.polza'),
          provider_model text NOT NULL,
          provider_profile_version text NOT NULL CHECK (lower(provider_profile_version)<>'latest'),
          prompt_version text NOT NULL CHECK (lower(prompt_version)<>'latest'),
          schema_version text NOT NULL CHECK (lower(schema_version)<>'latest'),
          request_digest text NOT NULL CHECK (request_digest ~ '^sha256:[a-f0-9]{64}$'),
          response_digest text NOT NULL CHECK (response_digest ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('candidate','rejected','failed','quarantined')),
          retry_count integer NOT NULL CHECK (retry_count BETWEEN 0 AND 3),
          usage_receipt jsonb NOT NULL,
          candidate_manifest jsonb NOT NULL,
          receipt_fingerprint text NOT NULL UNIQUE
            CHECK (receipt_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          FOREIGN KEY (normative_page_id,normative_page_version)
            REFERENCES platform.normative_representation_pages(normative_page_id,version)
            ON DELETE RESTRICT,
          UNIQUE (normative_page_id,normative_page_version,provider_profile_version,prompt_version,
                  schema_version,request_digest)
        );
        CREATE TABLE platform.ntd_publication_manifests (
          publication_manifest_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          normative_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          source_version_ids uuid[] NOT NULL CHECK (cardinality(source_version_ids)>0),
          page_denominator integer NOT NULL CHECK (page_denominator>=1),
          terminal_page_count integer NOT NULL CHECK (terminal_page_count>=0),
          structural_node_count bigint NOT NULL CHECK (structural_node_count>=0),
          table_count bigint NOT NULL CHECK (table_count>=0),
          formula_count bigint NOT NULL CHECK (formula_count>=0),
          provision_candidate_count bigint NOT NULL CHECK (provision_candidate_count>=0),
          supported_count bigint NOT NULL CHECK (supported_count>=0),
          contradicted_count bigint NOT NULL CHECK (contradicted_count>=0),
          insufficient_count bigint NOT NULL CHECK (insufficient_count>=0),
          quarantined_count bigint NOT NULL CHECK (quarantined_count>=0),
          unresolved_reference_count bigint NOT NULL CHECK (unresolved_reference_count>=0),
          publication_status text NOT NULL CHECK (publication_status IN (
            'published_verified_subset','blocked','superseded'
          )),
          semantic_fingerprint text NOT NULL UNIQUE
            CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          activation_decision_ref text,
          supersedes_version bigint,
          published_at timestamptz NOT NULL,
          PRIMARY KEY (publication_manifest_id,version),
          FOREIGN KEY (publication_manifest_id,supersedes_version)
            REFERENCES platform.ntd_publication_manifests(publication_manifest_id,version)
            ON DELETE RESTRICT,
          CHECK (terminal_page_count<=page_denominator),
          CHECK (publication_status<>'published_verified_subset' OR
                 (terminal_page_count=page_denominator AND supported_count>0)),
          CHECK ((version=1 AND supersedes_version IS NULL) OR
                 (version>1 AND supersedes_version=version-1))
        );
        CREATE TABLE platform.ntd_document_acceptance_receipts (
          document_acceptance_receipt_id uuid PRIMARY KEY,
          identity_reconciliation_id uuid NOT NULL
            REFERENCES platform.ntd_seed_identity_reconciliations(identity_reconciliation_id)
            ON DELETE RESTRICT,
          normative_edition_id uuid
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          source_byte_digests text[] NOT NULL,
          page_count integer NOT NULL CHECK (page_count>=0),
          native_page_count integer NOT NULL CHECK (native_page_count>=0),
          raster_page_count integer NOT NULL CHECK (raster_page_count>=0),
          mixed_page_count integer NOT NULL CHECK (mixed_page_count>=0),
          damaged_page_count integer NOT NULL CHECK (damaged_page_count>=0),
          polza_page_count integer NOT NULL CHECK (polza_page_count>=0),
          local_targeted_qwen_page_count integer NOT NULL CHECK (local_targeted_qwen_page_count>=0),
          table_count bigint NOT NULL CHECK (table_count>=0),
          formula_count bigint NOT NULL CHECK (formula_count>=0),
          structural_node_count bigint NOT NULL CHECK (structural_node_count>=0),
          provision_candidate_count bigint NOT NULL CHECK (provision_candidate_count>=0),
          verified_provision_count bigint NOT NULL CHECK (verified_provision_count>=0),
          conflict_count bigint NOT NULL CHECK (conflict_count>=0),
          gap_count bigint NOT NULL CHECK (gap_count>=0),
          unresolved_reference_count bigint NOT NULL CHECK (unresolved_reference_count>=0),
          qualified_rule_count bigint NOT NULL CHECK (qualified_rule_count>=0),
          gateway_acceptance jsonb NOT NULL,
          final_status text NOT NULL CHECK (final_status IN (
            'gateway_published','processed_partial','downloaded_only','metadata_only',
            'blocked','quarantined'
          )),
          semantic_fingerprint text NOT NULL UNIQUE
            CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          CHECK (native_page_count+raster_page_count+mixed_page_count+damaged_page_count<=page_count),
          CHECK (final_status<>'gateway_published' OR verified_provision_count>0)
        );
        """
    )


def _apply_security() -> None:
    for table in PLATFORM_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON platform.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )
        op.execute(f"GRANT SELECT,INSERT ON platform.{table} TO asd_ntd_ingestion_service")
        op.execute(
            f"GRANT SELECT ON platform.{table} TO "
            "asd_ntd_gateway_service,asd_platform_curator,asd_app"
        )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON platform.ntd_processing_jobs TO asd_ntd_ingestion_service; "
        "GRANT SELECT ON platform.ntd_processing_jobs TO "
        "asd_ntd_gateway_service,asd_platform_curator,asd_app"
    )
    # The Product Spine exposes only typed NTD status/evidence responses, but its
    # repository needs read-only access to canonical artifact/publication lineage
    # introduced after the original broad platform grant in migration 0002.
    op.execute(
        "GRANT SELECT ON platform.normative_artifacts,"
        "platform.normative_provision_versions,platform.practice_ntd_alignments,"
        "platform.rule_normative_provision_evidence,platform.normative_activation_decisions,"
        "platform.source_locators TO asd_app"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT ON platform.normative_artifacts,"
        "platform.normative_provision_versions,platform.practice_ntd_alignments,"
        "platform.rule_normative_provision_evidence,platform.normative_activation_decisions,"
        "platform.source_locators FROM asd_app"
    )
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE platform.{table}")
        # Attempts depend on the mutable job relation; jobs in turn depend on the identity
        # lineage. Remove the relation between those two points in the reverse FK order.
        if table == "ntd_processing_job_attempts":
            op.execute("DROP TABLE platform.ntd_processing_jobs")
    op.execute(
        "ALTER TABLE platform.cross_references DROP CONSTRAINT cross_references_relation_type_check"
    )
    op.execute(
        "ALTER TABLE platform.cross_references ADD CONSTRAINT cross_references_relation_type_check "
        "CHECK (relation_type IN ('references','defines','excepts','supersedes','amends','requires','conflicts_with'))"
    )
    op.execute(
        "ALTER TABLE platform.structural_units DROP CONSTRAINT structural_units_ntd_remediation_unit_type_ck"
    )
    op.execute(
        "ALTER TABLE platform.structural_units ADD CONSTRAINT structural_units_ntd_seed_unit_type_ck "
        "CHECK (unit_type IN ('section','clause','subclause','table','figure','appendix',"
        "'definition_scope','form','other'))"
    )
