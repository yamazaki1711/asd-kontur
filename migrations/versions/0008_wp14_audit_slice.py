"""Create the shared corpus capability and WP-14 Audit slice.

Revision ID: 0008_wp14
Revises: 0007_wp13
Create Date: 2026-08-23
"""

from __future__ import annotations

import os

from alembic import op

revision = "0008_wp14"
down_revision = "0007_wp13"
branch_labels = None
depends_on = None

PLATFORM_TABLES = ("corpus_processing_profile_versions",)

WORKSPACE_TABLES = (
    "collection_missions",
    "collection_scope_versions",
    "collection_sources",
    "corpus_acquisition_batches",
    "corpus_collected_items",
    "corpus_custody_receipts",
    "physical_object_inspections",
    "corpus_page_manifests",
    "corpus_processing_plan_versions",
    "corpus_processing_shards",
    "corpus_processing_receipts",
    "corpus_boundary_candidate_versions",
    "corpus_boundary_evidence_receipts",
    "corpus_boundary_validations",
    "logical_document_occurrences",
    "corpus_reconciliations",
    "corpus_snapshot_versions",
    "corpus_snapshot_reconciliations",
    "corpus_snapshot_object_memberships",
    "corpus_snapshot_page_memberships",
    "corpus_snapshot_occurrence_memberships",
    "corpus_snapshot_duplicate_memberships",
    "corpus_snapshot_conflict_memberships",
    "corpus_unresolved_items",
    "audit_processes",
    "audit_denominator_versions",
    "audit_delta_versions",
    "audit_delta_items",
    "audit_package_versions",
    "audit_package_memberships",
    "audit_action_request_versions",
    "audit_classification_versions",
    "audit_report_versions",
    "audit_projection_versions",
)

READ_TABLES = (
    "workspaces",
    "mode_executions",
    "objects",
    "source_artifacts",
    "source_versions",
    "source_locators",
    "evidence_links",
    "vlm_execution_attempts",
    "vlm_provider_results",
    "vlm_render_artifacts",
    "candidate_versions",
    "vlm_validation_runs",
    "workspace_fact_versions",
    "rule_traces",
    "material_batch_versions",
    "material_applications",
    "control_operation_versions",
    "document_requirement_versions",
    "id_package_versions",
    "presented_volume_versions",
    "ks_document_versions",
    "payment_claim_versions",
)


def upgrade() -> None:
    _create_role_and_platform_profile()
    _create_collection_and_preflight()
    _create_processing_and_boundary()
    _create_snapshot_and_audit()
    _apply_guards_grants_and_rls()


def _create_role_and_platform_profile() -> None:
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_audit_service') "
        "THEN CREATE ROLE asd_audit_service NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; "
        "END IF; END $$"
    )
    op.execute(
        """
        CREATE TABLE platform.corpus_processing_profile_versions (
          processing_profile_id uuid NOT NULL,
          version text NOT NULL CHECK (lower(version)<>'latest'),
          purpose text NOT NULL,
          policy_digest text NOT NULL CHECK (policy_digest ~ '^sha256:[a-f0-9]{64}$'),
          max_local_pages integer NOT NULL CHECK (max_local_pages>0),
          max_local_bytes bigint NOT NULL CHECK (max_local_bytes>0),
          max_pages_per_shard integer NOT NULL CHECK (max_pages_per_shard>0),
          max_raster_pages_per_shard integer NOT NULL CHECK (max_raster_pages_per_shard>0),
          external_egress_state text NOT NULL CHECK (external_egress_state IN ('denied','development_synthetic','production_authorized')),
          assurance_class text NOT NULL CHECK (assurance_class IN ('development_synthetic','production')),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (processing_profile_id,version),
          CHECK (assurance_class<>'development_synthetic' OR external_egress_state<>'production_authorized')
        );
        CREATE TRIGGER corpus_processing_profile_immutable BEFORE UPDATE OR DELETE
          ON platform.corpus_processing_profile_versions
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        GRANT SELECT ON platform.corpus_processing_profile_versions TO asd_audit_service;
        """
    )


def _create_collection_and_preflight() -> None:
    op.execute(
        """
        CREATE TABLE workspace.collection_missions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, collection_mission_id uuid NOT NULL,
          mode_execution_id uuid NOT NULL, state text NOT NULL CHECK (state IN ('collecting','reconciling','snapshotted','blocked','quarantined')),
          revision bigint NOT NULL CHECK (revision>=1), current_fingerprint text NOT NULL CHECK (current_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          collector_identity_id text NOT NULL, correlation_id uuid NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,collection_mission_id),
          FOREIGN KEY (organization_id,workspace_id,mode_execution_id) REFERENCES workspace.mode_executions(organization_id,workspace_id,mode_execution_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.collection_scope_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, collection_scope_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          collection_mission_id uuid NOT NULL, included_locations jsonb NOT NULL, included_media jsonb NOT NULL,
          completeness_claim text NOT NULL CHECK (completeness_claim IN ('claimed_complete','known_partial','unknown')),
          authority_profile_version text NOT NULL CHECK (lower(authority_profile_version)<>'latest'),
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,collection_scope_id,version),
          FOREIGN KEY (organization_id,workspace_id,collection_mission_id) REFERENCES workspace.collection_missions(organization_id,workspace_id,collection_mission_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.collection_sources (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, collection_source_id uuid NOT NULL,
          collection_mission_id uuid NOT NULL, source_medium text NOT NULL CHECK (source_medium IN ('paper','digital','unknown')),
          physical_location_kind text NOT NULL, physical_location_locator text NOT NULL,
          media_source_ref text NOT NULL, custody_claim text NOT NULL CHECK (custody_claim IN ('original','copy','unverified')),
          available boolean NOT NULL, readable boolean NOT NULL, acquired_by text NOT NULL, acquired_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,collection_source_id),
          FOREIGN KEY (organization_id,workspace_id,collection_mission_id) REFERENCES workspace.collection_missions(organization_id,workspace_id,collection_mission_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_acquisition_batches (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, acquisition_batch_id uuid NOT NULL,
          collection_source_id uuid NOT NULL, idempotency_key text NOT NULL, status text NOT NULL CHECK (status IN ('collecting','admitting','accepted','partial','failed','reconciliation_required')),
          item_count bigint NOT NULL CHECK (item_count>=0), manifest_digest text NOT NULL CHECK (manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          acquired_by text NOT NULL, acquired_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,acquisition_batch_id),
          UNIQUE (organization_id,workspace_id,idempotency_key),
          FOREIGN KEY (organization_id,workspace_id,collection_source_id) REFERENCES workspace.collection_sources(organization_id,workspace_id,collection_source_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_collected_items (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, collected_item_id uuid NOT NULL,
          acquisition_batch_id uuid NOT NULL, physical_object_id uuid NOT NULL, physical_object_version bigint NOT NULL,
          original_locator text NOT NULL, digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          size_bytes bigint NOT NULL CHECK (size_bytes>=0), media_type text NOT NULL, readable boolean NOT NULL,
          completeness_claim text NOT NULL CHECK (completeness_claim IN ('complete','partial','unknown')),
          admission_state text NOT NULL CHECK (admission_state IN ('collected','object_verified','source_admitted','rejected','reconciliation_required')),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,collected_item_id),
          UNIQUE (organization_id,workspace_id,acquisition_batch_id,original_locator),
          FOREIGN KEY (organization_id,workspace_id,acquisition_batch_id) REFERENCES workspace.corpus_acquisition_batches(organization_id,workspace_id,acquisition_batch_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,physical_object_id,physical_object_version) REFERENCES workspace.objects(organization_id,workspace_id,object_id,object_version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_custody_receipts (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, custody_receipt_id uuid NOT NULL,
          collected_item_id uuid NOT NULL, actor_identity_id text NOT NULL, method text NOT NULL,
          observed_digest text NOT NULL CHECK (observed_digest ~ '^sha256:[a-f0-9]{64}$'), observed_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,custody_receipt_id),
          FOREIGN KEY (organization_id,workspace_id,collected_item_id) REFERENCES workspace.corpus_collected_items(organization_id,workspace_id,collected_item_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.physical_object_inspections (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, inspection_id uuid NOT NULL,
          physical_object_id uuid NOT NULL, physical_object_version bigint NOT NULL,
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'), size_bytes bigint NOT NULL CHECK (size_bytes>=0), media_type text NOT NULL,
          encrypted boolean NOT NULL, readable boolean NOT NULL, page_count integer NOT NULL CHECK (page_count>=0),
          composition text NOT NULL CHECK (composition IN ('native','raster','mixed','unknown')),
          embedded_attachment_count integer NOT NULL CHECK (embedded_attachment_count>=0), signature_claim_count integer NOT NULL CHECK (signature_claim_count>=0),
          inspection_profile_version text NOT NULL CHECK (lower(inspection_profile_version)<>'latest'), error_codes text[] NOT NULL,
          inspected_at timestamptz NOT NULL, fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,inspection_id),
          FOREIGN KEY (organization_id,workspace_id,physical_object_id,physical_object_version) REFERENCES workspace.objects(organization_id,workspace_id,object_id,object_version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_page_manifests (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, inspection_id uuid NOT NULL, page_number integer NOT NULL CHECK (page_number>=1),
          page_digest text NOT NULL CHECK (page_digest ~ '^sha256:[a-f0-9]{64}$'), width_points double precision NOT NULL CHECK (width_points>0), height_points double precision NOT NULL CHECK (height_points>0),
          rotation integer NOT NULL, native_text_characters integer NOT NULL CHECK (native_text_characters>=0), raster_objects integer NOT NULL CHECK (raster_objects>=0),
          composition text NOT NULL CHECK (composition IN ('native','raster','mixed','unknown')), readable boolean NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,inspection_id,page_number),
          FOREIGN KEY (organization_id,workspace_id,inspection_id) REFERENCES workspace.physical_object_inspections(organization_id,workspace_id,inspection_id) ON DELETE RESTRICT
        );
        """
    )


def _create_processing_and_boundary() -> None:
    op.execute(
        """
        CREATE TABLE workspace.corpus_processing_plan_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, processing_plan_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          inspection_id uuid NOT NULL, purpose text NOT NULL, classification text NOT NULL,
          processing_profile_id uuid NOT NULL, processing_profile_version text NOT NULL,
          page_count integer NOT NULL CHECK (page_count>=1), estimated_cost_units bigint NOT NULL CHECK (estimated_cost_units>=0), estimated_seconds bigint NOT NULL CHECK (estimated_seconds>=0),
          state text NOT NULL CHECK (state IN ('complete','partial','blocked','unresolved')),
          plan_digest text NOT NULL CHECK (plan_digest ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,processing_plan_id,version),
          FOREIGN KEY (organization_id,workspace_id,inspection_id) REFERENCES workspace.physical_object_inspections(organization_id,workspace_id,inspection_id) ON DELETE RESTRICT,
          FOREIGN KEY (processing_profile_id,processing_profile_version) REFERENCES platform.corpus_processing_profile_versions(processing_profile_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_processing_shards (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, processing_plan_id uuid NOT NULL, plan_version bigint NOT NULL,
          shard_id uuid NOT NULL, ordinal integer NOT NULL CHECK (ordinal>=1), page_numbers integer[] NOT NULL CHECK (cardinality(page_numbers)>0),
          context_overlap_pages integer[] NOT NULL, route text NOT NULL CHECK (route IN ('native','deterministic','local_vlm','external_eligible')),
          expected_output_contract text NOT NULL CHECK (lower(expected_output_contract)<>'latest'), idempotency_key text NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,shard_id),
          UNIQUE (organization_id,workspace_id,processing_plan_id,plan_version,ordinal),
          UNIQUE (organization_id,workspace_id,idempotency_key),
          FOREIGN KEY (organization_id,workspace_id,processing_plan_id,plan_version) REFERENCES workspace.corpus_processing_plan_versions(organization_id,workspace_id,processing_plan_id,version) ON DELETE RESTRICT,
          CHECK (context_overlap_pages <@ page_numbers)
        );
        CREATE TABLE workspace.corpus_processing_receipts (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, processing_receipt_id uuid NOT NULL,
          processing_plan_id uuid NOT NULL, plan_version bigint NOT NULL, shard_id uuid NOT NULL, page_number integer NOT NULL CHECK (page_number>=1),
          attempt_id uuid, idempotency_key text NOT NULL, status text NOT NULL CHECK (status IN ('validated','failed','unknown','cancelled','rejected')),
          result_digest text CHECK (result_digest ~ '^sha256:[a-f0-9]{64}$'), validation_codes text[] NOT NULL,
          context_only boolean NOT NULL DEFAULT false,
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,processing_receipt_id),
          UNIQUE (organization_id,workspace_id,idempotency_key),
          FOREIGN KEY (organization_id,workspace_id,processing_plan_id,plan_version) REFERENCES workspace.corpus_processing_plan_versions(organization_id,workspace_id,processing_plan_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,shard_id) REFERENCES workspace.corpus_processing_shards(organization_id,workspace_id,shard_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,attempt_id) REFERENCES workspace.vlm_execution_attempts(organization_id,workspace_id,attempt_id) ON DELETE RESTRICT,
          CHECK (status<>'validated' OR result_digest IS NOT NULL)
        );
        CREATE TABLE workspace.corpus_boundary_candidate_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, boundary_candidate_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          container_source_version_id uuid NOT NULL, start_page integer NOT NULL CHECK (start_page>=1), end_page integer NOT NULL CHECK (end_page>=1),
          proposed_document_type text NOT NULL, method text NOT NULL CHECK (method IN ('deterministic','model_candidate','human')),
          confidence double precision CHECK (confidence>=0 AND confidence<=1), status text NOT NULL CHECK (status IN ('candidate','validating','rejected','unresolved')),
          supersedes_version bigint, fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,boundary_candidate_id,version),
          FOREIGN KEY (organization_id,workspace_id,container_source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,boundary_candidate_id,supersedes_version) REFERENCES workspace.corpus_boundary_candidate_versions(organization_id,workspace_id,boundary_candidate_id,version) ON DELETE RESTRICT,
          CHECK (start_page<=end_page), CHECK (supersedes_version IS NULL OR supersedes_version<version)
        );
        CREATE TABLE workspace.corpus_boundary_evidence_receipts (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, boundary_candidate_id uuid NOT NULL, boundary_candidate_version bigint NOT NULL,
          processing_receipt_id uuid NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,boundary_candidate_id,boundary_candidate_version,processing_receipt_id),
          FOREIGN KEY (organization_id,workspace_id,boundary_candidate_id,boundary_candidate_version) REFERENCES workspace.corpus_boundary_candidate_versions(organization_id,workspace_id,boundary_candidate_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,processing_receipt_id) REFERENCES workspace.corpus_processing_receipts(organization_id,workspace_id,processing_receipt_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_boundary_validations (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, boundary_validation_id uuid NOT NULL,
          boundary_candidate_id uuid NOT NULL, boundary_candidate_version bigint NOT NULL,
          disposition text NOT NULL CHECK (disposition IN ('accepted','rejected','unresolved')),
          validator_version text NOT NULL CHECK (lower(validator_version)<>'latest'), failure_codes text[] NOT NULL,
          authority_decision_ref text, validated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,boundary_validation_id),
          UNIQUE (organization_id,workspace_id,boundary_candidate_id,boundary_candidate_version),
          FOREIGN KEY (organization_id,workspace_id,boundary_candidate_id,boundary_candidate_version) REFERENCES workspace.corpus_boundary_candidate_versions(organization_id,workspace_id,boundary_candidate_id,version) ON DELETE RESTRICT,
          CHECK (disposition<>'accepted' OR (authority_decision_ref IS NOT NULL AND cardinality(failure_codes)=0))
        );
        CREATE TABLE workspace.logical_document_occurrences (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, logical_occurrence_id uuid NOT NULL,
          source_artifact_id uuid NOT NULL, source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL,
          container_source_version_id uuid NOT NULL, start_page integer NOT NULL CHECK (start_page>=1), end_page integer NOT NULL CHECK (end_page>=1),
          boundary_validation_id uuid NOT NULL, occurrence_digest text NOT NULL CHECK (occurrence_digest ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,logical_occurrence_id),
          FOREIGN KEY (organization_id,workspace_id,source_artifact_id) REFERENCES workspace.source_artifacts(organization_id,workspace_id,source_artifact_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,container_source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,boundary_validation_id) REFERENCES workspace.corpus_boundary_validations(organization_id,workspace_id,boundary_validation_id) ON DELETE RESTRICT,
          CHECK (start_page<=end_page)
        );
        CREATE TABLE workspace.corpus_reconciliations (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, reconciliation_id uuid NOT NULL,
          processing_plan_id uuid NOT NULL, plan_version bigint NOT NULL, expected_pages integer[] NOT NULL CHECK (cardinality(expected_pages)>0),
          validated_pages integer[] NOT NULL, failed_pages integer[] NOT NULL, unknown_pages integer[] NOT NULL, duplicate_pages integer[] NOT NULL,
          unresolved_segments jsonb NOT NULL, accepted_occurrence_ids uuid[] NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('complete','partial','blocked','unresolved','provider_failed','recovery_required','quarantined')),
          receipt_fingerprint text NOT NULL CHECK (receipt_fingerprint ~ '^sha256:[a-f0-9]{64}$'), reconciled_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,reconciliation_id),
          FOREIGN KEY (organization_id,workspace_id,processing_plan_id,plan_version) REFERENCES workspace.corpus_processing_plan_versions(organization_id,workspace_id,processing_plan_id,version) ON DELETE RESTRICT,
          CHECK (outcome<>'complete' OR (cardinality(failed_pages)=0 AND cardinality(unknown_pages)=0 AND cardinality(duplicate_pages)=0 AND jsonb_array_length(unresolved_segments)=0))
        );
        """
    )


def _create_snapshot_and_audit() -> None:
    op.execute(
        """
        CREATE TABLE workspace.corpus_snapshot_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, corpus_snapshot_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          collection_scope_id uuid NOT NULL, collection_scope_version bigint NOT NULL,
          rule_set_version_id uuid NOT NULL, coverage_denominator_version text NOT NULL CHECK (lower(coverage_denominator_version)<>'latest'),
          discovered_object_count bigint NOT NULL CHECK (discovered_object_count>=0), admitted_object_count bigint NOT NULL CHECK (admitted_object_count>=0),
          expected_page_count bigint NOT NULL CHECK (expected_page_count>=0), readable_page_count bigint NOT NULL CHECK (readable_page_count>=0),
          validated_page_count bigint NOT NULL CHECK (validated_page_count>=0), accepted_document_count bigint NOT NULL CHECK (accepted_document_count>=0),
          unresolved_item_count bigint NOT NULL CHECK (unresolved_item_count>=0),
          outcome text NOT NULL CHECK (outcome IN ('complete','partial','blocked','unresolved','provider_failed','recovery_required','quarantined')),
          claims_complete_oks boolean NOT NULL DEFAULT false CHECK (claims_complete_oks=false),
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,corpus_snapshot_id,version),
          FOREIGN KEY (organization_id,workspace_id,collection_scope_id,collection_scope_version) REFERENCES workspace.collection_scope_versions(organization_id,workspace_id,collection_scope_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (rule_set_version_id) REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          CHECK (admitted_object_count<=discovered_object_count),
          CHECK (validated_page_count<=readable_page_count AND readable_page_count<=expected_page_count),
          CHECK (outcome<>'complete' OR unresolved_item_count=0)
        );
        CREATE TABLE workspace.corpus_snapshot_object_memberships (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, corpus_snapshot_id uuid NOT NULL, snapshot_version bigint NOT NULL,
          physical_object_id uuid NOT NULL, physical_object_version bigint NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version,physical_object_id,physical_object_version),
          FOREIGN KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version) REFERENCES workspace.corpus_snapshot_versions(organization_id,workspace_id,corpus_snapshot_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,physical_object_id,physical_object_version) REFERENCES workspace.objects(organization_id,workspace_id,object_id,object_version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_snapshot_reconciliations (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, corpus_snapshot_id uuid NOT NULL, snapshot_version bigint NOT NULL,
          reconciliation_id uuid NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version,reconciliation_id),
          FOREIGN KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version) REFERENCES workspace.corpus_snapshot_versions(organization_id,workspace_id,corpus_snapshot_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,reconciliation_id) REFERENCES workspace.corpus_reconciliations(organization_id,workspace_id,reconciliation_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_snapshot_page_memberships (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, corpus_snapshot_id uuid NOT NULL, snapshot_version bigint NOT NULL,
          inspection_id uuid NOT NULL, page_number integer NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version,inspection_id,page_number),
          FOREIGN KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version) REFERENCES workspace.corpus_snapshot_versions(organization_id,workspace_id,corpus_snapshot_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,inspection_id,page_number) REFERENCES workspace.corpus_page_manifests(organization_id,workspace_id,inspection_id,page_number) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_snapshot_occurrence_memberships (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, corpus_snapshot_id uuid NOT NULL, snapshot_version bigint NOT NULL,
          logical_occurrence_id uuid NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version,logical_occurrence_id),
          FOREIGN KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version) REFERENCES workspace.corpus_snapshot_versions(organization_id,workspace_id,corpus_snapshot_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,logical_occurrence_id) REFERENCES workspace.logical_document_occurrences(organization_id,workspace_id,logical_occurrence_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_snapshot_duplicate_memberships (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, corpus_snapshot_id uuid NOT NULL, snapshot_version bigint NOT NULL,
          duplicate_group_id uuid NOT NULL, physical_object_id uuid NOT NULL, physical_object_version bigint NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version,duplicate_group_id,physical_object_id,physical_object_version),
          FOREIGN KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version) REFERENCES workspace.corpus_snapshot_versions(organization_id,workspace_id,corpus_snapshot_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,physical_object_id,physical_object_version) REFERENCES workspace.objects(organization_id,workspace_id,object_id,object_version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_snapshot_conflict_memberships (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, corpus_snapshot_id uuid NOT NULL, snapshot_version bigint NOT NULL,
          conflicting_source_version_id uuid NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version,conflicting_source_version_id),
          FOREIGN KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version) REFERENCES workspace.corpus_snapshot_versions(organization_id,workspace_id,corpus_snapshot_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,conflicting_source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.corpus_unresolved_items (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, unresolved_item_id uuid NOT NULL,
          corpus_snapshot_id uuid NOT NULL, snapshot_version bigint NOT NULL, reason_code text NOT NULL,
          affected_locator text NOT NULL, blocking boolean NOT NULL, recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,unresolved_item_id),
          FOREIGN KEY (organization_id,workspace_id,corpus_snapshot_id,snapshot_version) REFERENCES workspace.corpus_snapshot_versions(organization_id,workspace_id,corpus_snapshot_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.audit_processes (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, audit_process_id uuid NOT NULL,
          mode_execution_id uuid NOT NULL, corpus_snapshot_id uuid NOT NULL, corpus_snapshot_version bigint NOT NULL,
          state text NOT NULL CHECK (state IN ('requested','evaluating','blocked','completed','failed','quarantined')),
          revision bigint NOT NULL CHECK (revision>=1), current_fingerprint text NOT NULL CHECK (current_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          rule_set_version_id uuid NOT NULL, conflict_policy_version text NOT NULL CHECK (lower(conflict_policy_version)<>'latest'),
          authority_profile_version text NOT NULL CHECK (lower(authority_profile_version)<>'latest'),
          contract_registry_version text NOT NULL CHECK (lower(contract_registry_version)<>'latest'),
          correlation_id uuid NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,audit_process_id),
          FOREIGN KEY (organization_id,workspace_id,mode_execution_id) REFERENCES workspace.mode_executions(organization_id,workspace_id,mode_execution_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,corpus_snapshot_id,corpus_snapshot_version) REFERENCES workspace.corpus_snapshot_versions(organization_id,workspace_id,corpus_snapshot_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (rule_set_version_id) REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.audit_denominator_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, denominator_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          audit_process_id uuid NOT NULL, delta_kind text NOT NULL CHECK (delta_kind IN ('document','causal_readiness','package_signing_handover')),
          exact_scope jsonb NOT NULL, required_item_keys text[] NOT NULL, rule_set_version_id uuid NOT NULL,
          evidence_refs text[] NOT NULL, fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,denominator_id,version),
          FOREIGN KEY (organization_id,workspace_id,audit_process_id) REFERENCES workspace.audit_processes(organization_id,workspace_id,audit_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (rule_set_version_id) REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.audit_delta_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, audit_delta_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          audit_process_id uuid NOT NULL, delta_kind text NOT NULL CHECK (delta_kind IN ('document','causal_readiness','package_signing_handover')),
          denominator_id uuid NOT NULL, denominator_version bigint NOT NULL,
          satisfied_count bigint NOT NULL CHECK (satisfied_count>=0), missing_count bigint NOT NULL CHECK (missing_count>=0),
          conflict_count bigint NOT NULL CHECK (conflict_count>=0), indeterminate_count bigint NOT NULL CHECK (indeterminate_count>=0), blocked_count bigint NOT NULL CHECK (blocked_count>=0),
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'), evaluated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,audit_delta_id,version),
          UNIQUE (organization_id,workspace_id,audit_process_id,delta_kind,version),
          FOREIGN KEY (organization_id,workspace_id,audit_process_id) REFERENCES workspace.audit_processes(organization_id,workspace_id,audit_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,denominator_id,denominator_version) REFERENCES workspace.audit_denominator_versions(organization_id,workspace_id,denominator_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.audit_delta_items (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, audit_delta_id uuid NOT NULL, delta_version bigint NOT NULL,
          item_key text NOT NULL, state text NOT NULL CHECK (state IN ('satisfied','missing','conflict','indeterminate','not_applicable','blocked')),
          source_version_ids uuid[] NOT NULL, source_locator_ids uuid[] NOT NULL, rule_trace_ids uuid[] NOT NULL,
          authority_decision_refs text[] NOT NULL, uncertainty_codes text[] NOT NULL, blocker_codes text[] NOT NULL, downstream_impacts text[] NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,audit_delta_id,delta_version,item_key),
          FOREIGN KEY (organization_id,workspace_id,audit_delta_id,delta_version) REFERENCES workspace.audit_delta_versions(organization_id,workspace_id,audit_delta_id,version) ON DELETE RESTRICT,
          CHECK (state<>'satisfied' OR (cardinality(source_locator_ids)>0 AND cardinality(authority_decision_refs)>0))
        );
        CREATE TABLE workspace.audit_package_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, package_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          audit_process_id uuid NOT NULL, volume_or_book_id uuid, section_ref text,
          professional_review_state text NOT NULL, signer_authority_state text NOT NULL, signature_state text NOT NULL,
          handover_state text NOT NULL, acceptance_state text NOT NULL, blocker_codes text[] NOT NULL,
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'), evaluated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,package_id,version),
          FOREIGN KEY (organization_id,workspace_id,audit_process_id) REFERENCES workspace.audit_processes(organization_id,workspace_id,audit_process_id) ON DELETE RESTRICT,
          CHECK (professional_review_state IN ('satisfied','missing','conflict','indeterminate','not_applicable','blocked')),
          CHECK (signer_authority_state IN ('satisfied','missing','conflict','indeterminate','not_applicable','blocked')),
          CHECK (signature_state IN ('satisfied','missing','conflict','indeterminate','not_applicable','blocked')),
          CHECK (handover_state IN ('satisfied','missing','conflict','indeterminate','not_applicable','blocked')),
          CHECK (acceptance_state IN ('satisfied','missing','conflict','indeterminate','not_applicable','blocked'))
        );
        CREATE TABLE workspace.audit_package_memberships (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, package_id uuid NOT NULL, package_version bigint NOT NULL,
          logical_occurrence_id uuid NOT NULL, ordinal integer NOT NULL CHECK (ordinal>=1), required_copies integer NOT NULL CHECK (required_copies>=1),
          actual_copies integer NOT NULL CHECK (actual_copies>=0), register_level integer CHECK (register_level>=1),
          PRIMARY KEY (organization_id,workspace_id,package_id,package_version,logical_occurrence_id),
          UNIQUE (organization_id,workspace_id,package_id,package_version,ordinal),
          FOREIGN KEY (organization_id,workspace_id,package_id,package_version) REFERENCES workspace.audit_package_versions(organization_id,workspace_id,package_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,logical_occurrence_id) REFERENCES workspace.logical_document_occurrences(organization_id,workspace_id,logical_occurrence_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.audit_action_request_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, action_request_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          audit_process_id uuid NOT NULL, action_code text NOT NULL, addressee_identity_id text NOT NULL, affected_object_ref text NOT NULL,
          evidence_refs text[] NOT NULL, deadline timestamptz, blocking_impacts text[] NOT NULL,
          initiator_identity_id text NOT NULL, verifier_identity_id text NOT NULL,
          executor_identity_id text,
          state text NOT NULL CHECK (state IN ('open','in_progress','evidence_submitted','verified_closed','rejected','superseded','overdue','cancelled')),
          supersedes_version bigint, created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,action_request_id,version),
          FOREIGN KEY (organization_id,workspace_id,audit_process_id) REFERENCES workspace.audit_processes(organization_id,workspace_id,audit_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,action_request_id,supersedes_version) REFERENCES workspace.audit_action_request_versions(organization_id,workspace_id,action_request_id,version) ON DELETE RESTRICT,
          CHECK (initiator_identity_id<>verifier_identity_id),
          CHECK (state<>'verified_closed' OR cardinality(evidence_refs)>0),
          CHECK (state<>'verified_closed' OR executor_identity_id IS NOT NULL),
          CHECK (executor_identity_id IS NULL OR executor_identity_id<>verifier_identity_id),
          CHECK (supersedes_version IS NULL OR supersedes_version<version)
        );
        CREATE TABLE workspace.audit_classification_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, classification_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          logical_occurrence_id uuid NOT NULL, document_type text NOT NULL, type_specific_attributes jsonb NOT NULL,
          validator_version text NOT NULL CHECK (lower(validator_version)<>'latest'), validation_failure_codes text[] NOT NULL,
          authority_decision_ref text, supersedes_version bigint, created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,classification_id,version),
          FOREIGN KEY (organization_id,workspace_id,logical_occurrence_id) REFERENCES workspace.logical_document_occurrences(organization_id,workspace_id,logical_occurrence_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,classification_id,supersedes_version) REFERENCES workspace.audit_classification_versions(organization_id,workspace_id,classification_id,version) ON DELETE RESTRICT,
          CHECK (supersedes_version IS NULL OR supersedes_version<version)
        );
        CREATE TABLE workspace.audit_report_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, audit_report_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          audit_process_id uuid NOT NULL, corpus_snapshot_id uuid NOT NULL, corpus_snapshot_version bigint NOT NULL,
          document_delta_id uuid NOT NULL, document_delta_version bigint NOT NULL,
          causal_delta_id uuid NOT NULL, causal_delta_version bigint NOT NULL,
          package_delta_id uuid NOT NULL, package_delta_version bigint NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('complete','partial','blocked','unresolved')),
          unresolved_codes text[] NOT NULL, product_ready boolean NOT NULL DEFAULT false CHECK (product_ready=false),
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,audit_report_id,version),
          FOREIGN KEY (organization_id,workspace_id,audit_process_id) REFERENCES workspace.audit_processes(organization_id,workspace_id,audit_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,corpus_snapshot_id,corpus_snapshot_version) REFERENCES workspace.corpus_snapshot_versions(organization_id,workspace_id,corpus_snapshot_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,document_delta_id,document_delta_version) REFERENCES workspace.audit_delta_versions(organization_id,workspace_id,audit_delta_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,causal_delta_id,causal_delta_version) REFERENCES workspace.audit_delta_versions(organization_id,workspace_id,audit_delta_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,package_delta_id,package_delta_version) REFERENCES workspace.audit_delta_versions(organization_id,workspace_id,audit_delta_id,version) ON DELETE RESTRICT,
          CHECK (outcome<>'complete' OR cardinality(unresolved_codes)=0)
        );
        CREATE TABLE workspace.audit_projection_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, projection_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          audit_report_id uuid NOT NULL, audit_report_version bigint NOT NULL,
          projection_kind text NOT NULL CHECK (projection_kind IN ('customer','pto')),
          source_fingerprint text NOT NULL CHECK (source_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          projection_payload jsonb NOT NULL, projection_fingerprint text NOT NULL CHECK (projection_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          state text NOT NULL CHECK (state IN ('building','current','stale','failed','empty')),
          built_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,projection_id,version),
          FOREIGN KEY (organization_id,workspace_id,audit_report_id,audit_report_version) REFERENCES workspace.audit_report_versions(organization_id,workspace_id,audit_report_id,version) ON DELETE RESTRICT
        );
        """
    )


def _apply_guards_grants_and_rls() -> None:
    op.execute("GRANT USAGE ON SCHEMA platform,workspace,messaging,audit TO asd_audit_service")
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.reject_audit_version_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member') "
        "THEN RETURN OLD; END IF; RAISE EXCEPTION 'corpus and audit version records are immutable'; END $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.guard_audit_header_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member') THEN RETURN OLD; END IF; "
        "IF TG_OP='UPDATE' AND pg_has_role(session_user,'asd_audit_service','member') "
        "AND NULLIF(current_setting('asd.audit_operation_id',true),'') IS NOT NULL THEN "
        "IF NEW.revision<>OLD.revision+1 THEN RAISE EXCEPTION 'audit optimistic concurrency violation'; END IF; RETURN NEW; END IF; "
        "RAISE EXCEPTION 'corpus/audit state change requires service operation context'; END $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.require_audit_mode() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF NOT EXISTS (SELECT 1 FROM workspace.mode_executions m WHERE m.organization_id=NEW.organization_id "
        "AND m.workspace_id=NEW.workspace_id AND m.mode_execution_id=NEW.mode_execution_id AND m.mode='Audit') "
        "THEN RAISE EXCEPTION 'audit process requires Audit ModeExecution'; END IF; RETURN NEW; END $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.require_accepted_boundary() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF NOT EXISTS (SELECT 1 FROM workspace.corpus_boundary_validations v "
        "WHERE v.organization_id=NEW.organization_id AND v.workspace_id=NEW.workspace_id "
        "AND v.boundary_validation_id=NEW.boundary_validation_id AND v.disposition='accepted' "
        "AND v.authority_decision_ref IS NOT NULL) THEN RAISE EXCEPTION 'accepted boundary validation required'; "
        "END IF; RETURN NEW; END $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.require_three_audit_delta_kinds() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF NOT EXISTS (SELECT 1 FROM workspace.audit_delta_versions d WHERE d.organization_id=NEW.organization_id "
        "AND d.workspace_id=NEW.workspace_id AND d.audit_delta_id=NEW.document_delta_id AND d.version=NEW.document_delta_version AND d.delta_kind='document') "
        "OR NOT EXISTS (SELECT 1 FROM workspace.audit_delta_versions d WHERE d.organization_id=NEW.organization_id "
        "AND d.workspace_id=NEW.workspace_id AND d.audit_delta_id=NEW.causal_delta_id AND d.version=NEW.causal_delta_version AND d.delta_kind='causal_readiness') "
        "OR NOT EXISTS (SELECT 1 FROM workspace.audit_delta_versions d WHERE d.organization_id=NEW.organization_id "
        "AND d.workspace_id=NEW.workspace_id AND d.audit_delta_id=NEW.package_delta_id AND d.version=NEW.package_delta_version AND d.delta_kind='package_signing_handover') "
        "THEN RAISE EXCEPTION 'audit report requires exact independent delta kinds'; END IF; RETURN NEW; END $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.verify_corpus_snapshot_inventory() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "DECLARE object_count bigint; page_count bigint; occurrence_count bigint; unresolved_count bigint; reconciliation_count bigint; "
        "BEGIN SELECT count(*) INTO object_count FROM workspace.corpus_snapshot_object_memberships m WHERE m.organization_id=NEW.organization_id AND m.workspace_id=NEW.workspace_id AND m.corpus_snapshot_id=NEW.corpus_snapshot_id AND m.snapshot_version=NEW.version; "
        "SELECT count(*) INTO page_count FROM workspace.corpus_snapshot_page_memberships m WHERE m.organization_id=NEW.organization_id AND m.workspace_id=NEW.workspace_id AND m.corpus_snapshot_id=NEW.corpus_snapshot_id AND m.snapshot_version=NEW.version; "
        "SELECT count(*) INTO occurrence_count FROM workspace.corpus_snapshot_occurrence_memberships m WHERE m.organization_id=NEW.organization_id AND m.workspace_id=NEW.workspace_id AND m.corpus_snapshot_id=NEW.corpus_snapshot_id AND m.snapshot_version=NEW.version; "
        "SELECT count(*) INTO unresolved_count FROM workspace.corpus_unresolved_items m WHERE m.organization_id=NEW.organization_id AND m.workspace_id=NEW.workspace_id AND m.corpus_snapshot_id=NEW.corpus_snapshot_id AND m.snapshot_version=NEW.version; "
        "SELECT count(*) INTO reconciliation_count FROM workspace.corpus_snapshot_reconciliations m WHERE m.organization_id=NEW.organization_id AND m.workspace_id=NEW.workspace_id AND m.corpus_snapshot_id=NEW.corpus_snapshot_id AND m.snapshot_version=NEW.version; "
        "IF object_count<>NEW.discovered_object_count OR page_count<>NEW.expected_page_count OR occurrence_count<>NEW.accepted_document_count OR unresolved_count<>NEW.unresolved_item_count OR reconciliation_count=0 "
        "THEN RAISE EXCEPTION 'corpus snapshot inventory/count reconciliation failed'; END IF; RETURN NEW; END $$"
    )
    predicate = (
        "organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid"
    )
    for table in READ_TABLES:
        op.execute(
            f"CREATE POLICY {table}_audit_read_scope_policy ON workspace.{table} "
            f"FOR SELECT TO asd_audit_service USING ({predicate})"
        )
    op.execute(
        "GRANT SELECT ON "
        + ",".join(f"workspace.{table}" for table in READ_TABLES)
        + " TO asd_audit_service"
    )
    for qualified in (
        "messaging.workspace_idempotency",
        "messaging.workspace_outbox",
        "audit.workspace_records",
    ):
        table = qualified.split(".")[1]
        op.execute(
            f"CREATE POLICY {table}_audit_scope_policy ON {qualified} FOR ALL TO asd_audit_service "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    op.execute("GRANT SELECT,INSERT,UPDATE ON messaging.workspace_idempotency TO asd_audit_service")
    op.execute("GRANT SELECT,INSERT ON messaging.workspace_outbox TO asd_audit_service")
    op.execute("GRANT SELECT,INSERT ON audit.workspace_records TO asd_audit_service")
    for table in WORKSPACE_TABLES:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_audit_scope_policy ON workspace.{table} FOR ALL TO asd_audit_service "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_audit_service")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE POLICY {table}_destruction_scope_policy ON workspace.{table} FOR ALL TO asd_destruction_executor "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE TRIGGER {table}_audit_write_fence BEFORE INSERT OR UPDATE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION workspace.enforce_material_write_fence()"
        )
        if table in {"collection_missions", "audit_processes"}:
            op.execute(
                f"CREATE TRIGGER {table}_update_guard BEFORE UPDATE OR DELETE ON workspace.{table} "
                "FOR EACH ROW EXECUTE FUNCTION workspace.guard_audit_header_mutation()"
            )
        else:
            op.execute(
                f"CREATE TRIGGER {table}_immutable_guard BEFORE UPDATE OR DELETE ON workspace.{table} "
                "FOR EACH ROW EXECUTE FUNCTION workspace.reject_audit_version_mutation()"
            )
    op.execute(
        "GRANT UPDATE (state,revision,current_fingerprint,updated_at) ON workspace.collection_missions,workspace.audit_processes TO asd_audit_service"
    )
    op.execute(
        "CREATE TRIGGER audit_process_mode_guard BEFORE INSERT OR UPDATE ON workspace.audit_processes "
        "FOR EACH ROW EXECUTE FUNCTION workspace.require_audit_mode()"
    )
    op.execute(
        "CREATE TRIGGER logical_document_occurrence_boundary_guard BEFORE INSERT ON workspace.logical_document_occurrences "
        "FOR EACH ROW EXECUTE FUNCTION workspace.require_accepted_boundary()"
    )
    op.execute(
        "CREATE TRIGGER audit_report_delta_kind_guard BEFORE INSERT ON workspace.audit_report_versions "
        "FOR EACH ROW EXECUTE FUNCTION workspace.require_three_audit_delta_kinds()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER corpus_snapshot_inventory_guard AFTER INSERT ON workspace.corpus_snapshot_versions "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION workspace.verify_corpus_snapshot_inventory()"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "WP-14 downgrade is destructive and allowed only in an explicitly disposable database"
        )
    for table in reversed(WORKSPACE_TABLES):
        op.execute(f"DROP TABLE workspace.{table}")
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE platform.{table}")
    for table in READ_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_audit_read_scope_policy ON workspace.{table}")
    for qualified in (
        "messaging.workspace_idempotency",
        "messaging.workspace_outbox",
        "audit.workspace_records",
    ):
        table = qualified.split(".")[1]
        op.execute(f"DROP POLICY IF EXISTS {table}_audit_scope_policy ON {qualified}")
    op.execute("DROP FUNCTION IF EXISTS workspace.require_audit_mode()")
    op.execute("DROP FUNCTION IF EXISTS workspace.require_accepted_boundary()")
    op.execute("DROP FUNCTION IF EXISTS workspace.require_three_audit_delta_kinds()")
    op.execute("DROP FUNCTION IF EXISTS workspace.verify_corpus_snapshot_inventory()")
    op.execute("DROP FUNCTION IF EXISTS workspace.guard_audit_header_mutation()")
    op.execute("DROP FUNCTION IF EXISTS workspace.reject_audit_version_mutation()")
