"""Create the G-05 platform knowledge foundation.

Revision ID: 0002_g05
Revises: 0001_g04
Create Date: 2026-08-23
"""

from __future__ import annotations

import os

from alembic import op

revision = "0002_g05"
down_revision = "0001_g04"
branch_labels = None
depends_on = None


PLATFORM_TABLES = (
    "promotion_publications",
    "evidence_capsules",
    "rule_set_memberships",
    "rule_set_versions",
    "conflict_policy_versions",
    "rule_approvals",
    "rule_reviews",
    "rule_version_states",
    "rule_evidence",
    "rule_versions",
    "rules",
    "knowledge_gaps",
    "normative_conflicts",
    "cross_references",
    "exceptions",
    "requirements",
    "definitions",
    "assertion_evidence",
    "knowledge_assertions",
    "applicability_contexts",
    "structural_units",
    "normative_edition_states",
    "normative_editions",
    "normative_documents",
    "evidence_links",
    "source_locators",
    "source_versions",
    "acquisition_attempts",
    "source_artifacts",
    "object_receipts",
    "objects",
    "official_source_registry_entries",
)

WORKSPACE_TABLES = (
    "promotion_decisions",
    "promotion_regression_results",
    "promotion_anonymization_results",
    "promotion_candidates",
    "controlled_rule_set_upgrades",
    "rule_traces",
    "rule_evaluations",
    "rule_evidence",
    "rule_version_states",
    "rule_versions",
    "rules",
    "evidence_links",
    "source_locators",
    "source_versions",
    "acquisition_attempts",
    "source_object_receipts",
    "source_artifacts",
)


def upgrade() -> None:
    _create_roles_and_extensions()
    _create_platform_source_ledger()
    _create_workspace_source_ledger()
    _create_normative_canon()
    _create_projection_plane()
    _create_rule_registry()
    _create_workspace_rules()
    _create_promotion_gate()
    _create_platform_audit()
    _apply_grants_and_rls()


def _create_roles_and_extensions() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asd_platform_curator') THEN "
        "CREATE ROLE asd_platform_curator NOLOGIN NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOINHERIT; END IF; "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asd_projection_builder') THEN "
        "CREATE ROLE asd_projection_builder NOLOGIN NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOINHERIT; END IF; END $$"
    )
    op.execute("CREATE SCHEMA IF NOT EXISTS projection")
    op.execute(
        "CREATE OR REPLACE FUNCTION platform.reject_immutable_mutation() "
        "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
        "RAISE EXCEPTION 'immutable platform record' USING ERRCODE = '55000'; END $$"
    )


def _create_platform_source_ledger() -> None:
    op.execute(
        """
        CREATE TABLE platform.official_source_registry_entries (
          registry_entry_id uuid PRIMARY KEY,
          source_family_key text NOT NULL UNIQUE,
          official_url text NOT NULL UNIQUE,
          issuer text NOT NULL,
          jurisdiction text NOT NULL,
          registry_metadata_digest text NOT NULL CHECK (registry_metadata_digest ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('registered','observed_changed','suspended','retired')),
          revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
          created_by_identity_id text NOT NULL,
          correlation_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          observed_at timestamptz NOT NULL
        );
        CREATE TABLE platform.objects (
          object_id uuid PRIMARY KEY,
          object_version bigint NOT NULL CHECK (object_version >= 1),
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
          media_type text NOT NULL,
          storage_adapter_key text NOT NULL,
          access_capability_ref text NOT NULL,
          classification text NOT NULL,
          retention_class text NOT NULL,
          created_by_identity_id text NOT NULL,
          correlation_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (object_id, object_version),
          UNIQUE (content_digest, size_bytes)
        );
        CREATE TABLE platform.object_receipts (
          object_receipt_id uuid PRIMARY KEY,
          object_id uuid NOT NULL,
          object_version bigint NOT NULL,
          adapter_key text NOT NULL,
          operation_id text NOT NULL UNIQUE,
          status text NOT NULL CHECK (status IN ('verified','failed','residue_detected')),
          observed_digest text NOT NULL CHECK (observed_digest ~ '^sha256:[a-f0-9]{64}$'),
          observed_size_bytes bigint NOT NULL CHECK (observed_size_bytes >= 0),
          residue_state text NOT NULL CHECK (residue_state IN ('none','present','unknown')),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (object_id, object_version)
            REFERENCES platform.objects(object_id, object_version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.source_artifacts (
          source_artifact_id uuid PRIMARY KEY,
          source_kind text NOT NULL CHECK (source_kind IN ('normative_document','legal_act','official_reference','universal_template')),
          title text NOT NULL,
          issuer text NOT NULL,
          jurisdiction text NOT NULL,
          stable_designation text NOT NULL,
          status text NOT NULL CHECK (status IN ('registered','active','suspended','retired')),
          revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
          retention_class text NOT NULL,
          created_by_identity_id text NOT NULL,
          correlation_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (issuer, jurisdiction, stable_designation)
        );
        CREATE TABLE platform.acquisition_attempts (
          acquisition_attempt_id uuid PRIMARY KEY,
          registry_entry_id uuid,
          source_artifact_id uuid,
          acquisition_method text NOT NULL,
          external_locator text NOT NULL,
          requested_at timestamptz NOT NULL,
          retrieved_at timestamptz,
          status text NOT NULL CHECK (status IN ('started','bytes_written','accepted','failed','reconciliation_required')),
          observed_metadata_digest text CHECK (observed_metadata_digest ~ '^sha256:[a-f0-9]{64}$'),
          observed_content_digest text CHECK (observed_content_digest ~ '^sha256:[a-f0-9]{64}$'),
          object_receipt_id uuid,
          error_code text,
          correlation_id uuid NOT NULL,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (registry_entry_id) REFERENCES platform.official_source_registry_entries(registry_entry_id) ON DELETE RESTRICT,
          FOREIGN KEY (source_artifact_id) REFERENCES platform.source_artifacts(source_artifact_id) ON DELETE RESTRICT,
          FOREIGN KEY (object_receipt_id) REFERENCES platform.object_receipts(object_receipt_id) ON DELETE RESTRICT
        );
        CREATE TABLE platform.source_versions (
          source_version_id uuid PRIMARY KEY,
          source_artifact_id uuid NOT NULL REFERENCES platform.source_artifacts(source_artifact_id) ON DELETE RESTRICT,
          version_ordinal bigint NOT NULL CHECK (version_ordinal >= 1),
          external_version_label text NOT NULL,
          object_id uuid NOT NULL,
          object_version bigint NOT NULL,
          object_receipt_id uuid NOT NULL REFERENCES platform.object_receipts(object_receipt_id) ON DELETE RESTRICT,
          acquisition_attempt_id uuid NOT NULL REFERENCES platform.acquisition_attempts(acquisition_attempt_id) ON DELETE RESTRICT,
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          semantic_metadata_digest text NOT NULL CHECK (semantic_metadata_digest ~ '^sha256:[a-f0-9]{64}$'),
          acquisition_method text NOT NULL,
          retrieved_at timestamptz NOT NULL,
          admission_status text NOT NULL CHECK (admission_status = 'accepted'),
          admitted_by_identity_id text NOT NULL,
          admitted_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          retention_class text NOT NULL,
          FOREIGN KEY (object_id, object_version) REFERENCES platform.objects(object_id, object_version) ON DELETE RESTRICT,
          UNIQUE (source_artifact_id, version_ordinal),
          UNIQUE (source_artifact_id, external_version_label),
          UNIQUE (source_artifact_id, content_digest)
        );
        CREATE TABLE platform.source_locators (
          source_locator_id uuid PRIMARY KEY,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          locator_kind text NOT NULL,
          locator_key text NOT NULL,
          locator_value jsonb NOT NULL,
          fragment_digest text CHECK (fragment_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (source_version_id, locator_kind, locator_key)
        );
        CREATE TABLE platform.evidence_links (
          evidence_link_id uuid PRIMARY KEY,
          subject_type text NOT NULL,
          subject_id uuid NOT NULL,
          subject_version text NOT NULL,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          source_locator_id uuid NOT NULL REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          evidence_role text NOT NULL,
          validity_status text NOT NULL CHECK (validity_status IN ('verified','disputed','withdrawn')),
          decision_ref text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (subject_type, subject_id, subject_version, source_locator_id, evidence_role)
        );
        """
    )


def _create_workspace_source_ledger() -> None:
    op.execute(
        """
        CREATE TABLE workspace.source_artifacts (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          source_artifact_id uuid NOT NULL,
          source_kind text NOT NULL CHECK (source_kind IN ('pd','rd','contract','customer_regulation','project_evidence','field_document')),
          title text NOT NULL,
          issuer text,
          status text NOT NULL CHECK (status IN ('registered','active','suspended','retired')),
          revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
          retention_class text NOT NULL,
          created_by_identity_id text NOT NULL,
          correlation_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, source_artifact_id),
          FOREIGN KEY (organization_id, workspace_id)
            REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.source_object_receipts (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          object_receipt_id uuid NOT NULL,
          object_id uuid NOT NULL,
          object_version bigint NOT NULL,
          adapter_key text NOT NULL,
          operation_id text NOT NULL,
          status text NOT NULL CHECK (status IN ('verified','failed','residue_detected')),
          observed_digest text NOT NULL CHECK (observed_digest ~ '^sha256:[a-f0-9]{64}$'),
          observed_size_bytes bigint NOT NULL CHECK (observed_size_bytes >= 0),
          residue_state text NOT NULL CHECK (residue_state IN ('none','present','unknown')),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, object_receipt_id),
          UNIQUE (organization_id, workspace_id, operation_id),
          FOREIGN KEY (organization_id, workspace_id, object_id, object_version)
            REFERENCES workspace.objects(organization_id, workspace_id, object_id, object_version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.acquisition_attempts (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          acquisition_attempt_id uuid NOT NULL,
          source_artifact_id uuid,
          acquisition_method text NOT NULL,
          external_locator text NOT NULL,
          requested_at timestamptz NOT NULL,
          retrieved_at timestamptz,
          status text NOT NULL CHECK (status IN ('started','bytes_written','accepted','failed','reconciliation_required')),
          observed_content_digest text CHECK (observed_content_digest ~ '^sha256:[a-f0-9]{64}$'),
          object_receipt_id uuid,
          error_code text,
          correlation_id uuid NOT NULL,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, acquisition_attempt_id),
          FOREIGN KEY (organization_id, workspace_id, source_artifact_id)
            REFERENCES workspace.source_artifacts(organization_id, workspace_id, source_artifact_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id, workspace_id, object_receipt_id)
            REFERENCES workspace.source_object_receipts(organization_id, workspace_id, object_receipt_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.source_versions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          source_version_id uuid NOT NULL,
          source_artifact_id uuid NOT NULL,
          version_ordinal bigint NOT NULL CHECK (version_ordinal >= 1),
          external_version_label text NOT NULL,
          object_id uuid NOT NULL,
          object_receipt_id uuid NOT NULL,
          acquisition_attempt_id uuid NOT NULL,
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          semantic_metadata_digest text NOT NULL CHECK (semantic_metadata_digest ~ '^sha256:[a-f0-9]{64}$'),
          acquisition_method text NOT NULL,
          retrieved_at timestamptz NOT NULL,
          admission_status text NOT NULL CHECK (admission_status = 'accepted'),
          admitted_by_identity_id text NOT NULL,
          admitted_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          retention_class text NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, source_version_id),
          FOREIGN KEY (organization_id, workspace_id, source_artifact_id)
            REFERENCES workspace.source_artifacts(organization_id, workspace_id, source_artifact_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id, workspace_id, object_id)
            REFERENCES workspace.objects(organization_id, workspace_id, object_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id, workspace_id, object_receipt_id)
            REFERENCES workspace.source_object_receipts(organization_id, workspace_id, object_receipt_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id, workspace_id, acquisition_attempt_id)
            REFERENCES workspace.acquisition_attempts(organization_id, workspace_id, acquisition_attempt_id) ON DELETE RESTRICT,
          UNIQUE (organization_id, workspace_id, source_artifact_id, version_ordinal),
          UNIQUE (organization_id, workspace_id, source_artifact_id, external_version_label),
          UNIQUE (organization_id, workspace_id, source_artifact_id, content_digest)
        );
        CREATE TABLE workspace.source_locators (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          source_locator_id uuid NOT NULL,
          source_version_id uuid NOT NULL,
          locator_kind text NOT NULL,
          locator_key text NOT NULL,
          locator_value jsonb NOT NULL,
          fragment_digest text CHECK (fragment_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, source_locator_id),
          FOREIGN KEY (organization_id, workspace_id, source_version_id)
            REFERENCES workspace.source_versions(organization_id, workspace_id, source_version_id) ON DELETE RESTRICT,
          UNIQUE (organization_id, workspace_id, source_version_id, locator_kind, locator_key)
        );
        CREATE TABLE workspace.evidence_links (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          evidence_link_id uuid NOT NULL,
          subject_type text NOT NULL,
          subject_id uuid NOT NULL,
          subject_version text NOT NULL,
          source_version_id uuid NOT NULL,
          source_locator_id uuid NOT NULL,
          evidence_role text NOT NULL,
          validity_status text NOT NULL CHECK (validity_status IN ('verified','disputed','withdrawn')),
          decision_ref text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, evidence_link_id),
          FOREIGN KEY (organization_id, workspace_id, source_version_id)
            REFERENCES workspace.source_versions(organization_id, workspace_id, source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id, workspace_id, source_locator_id)
            REFERENCES workspace.source_locators(organization_id, workspace_id, source_locator_id) ON DELETE RESTRICT,
          UNIQUE (organization_id, workspace_id, subject_type, subject_id, subject_version, source_locator_id, evidence_role)
        );
        """
    )
    for table in (
        "source_object_receipts",
        "source_versions",
        "source_locators",
        "evidence_links",
    ):
        _immutable_trigger("workspace", table)


def _create_normative_canon() -> None:
    op.execute(
        """
        CREATE TABLE platform.normative_documents (
          normative_document_id uuid PRIMARY KEY,
          designation_namespace text NOT NULL,
          designation text NOT NULL,
          title text NOT NULL,
          issuer text NOT NULL,
          jurisdiction text NOT NULL,
          document_class text NOT NULL,
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (designation_namespace, designation, issuer, jurisdiction)
        );
        CREATE TABLE platform.normative_editions (
          normative_edition_id uuid PRIMARY KEY,
          normative_document_id uuid NOT NULL REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          edition_label text NOT NULL,
          source_version_id uuid NOT NULL UNIQUE REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          effective_from date,
          effective_to date,
          boundary text NOT NULL DEFAULT '[from,to)' CHECK (boundary = '[from,to)'),
          supersedes_edition_id uuid REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          replaces_edition_id uuid REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          amends_edition_id uuid REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          applicability_context_id uuid,
          admitted_by_identity_id text NOT NULL,
          admitted_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from),
          CHECK (supersedes_edition_id IS NULL OR supersedes_edition_id <> normative_edition_id),
          UNIQUE (normative_document_id, edition_label)
        );
        CREATE TABLE platform.normative_edition_states (
          edition_state_id uuid PRIMARY KEY,
          normative_edition_id uuid NOT NULL REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          state_sequence bigint NOT NULL CHECK (state_sequence >= 1),
          status text NOT NULL CHECK (status IN ('draft','admitted','active','cancelled','superseded','indeterminate')),
          effective_at timestamptz NOT NULL,
          authority_reference text NOT NULL,
          evidence_ref text NOT NULL,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (normative_edition_id, state_sequence)
        );
        CREATE TABLE platform.structural_units (
          structural_unit_id uuid PRIMARY KEY,
          normative_edition_id uuid NOT NULL REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          parent_structural_unit_id uuid REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          unit_type text NOT NULL CHECK (unit_type IN ('section','clause','subclause','table','figure','appendix','definition_scope')),
          structural_path text NOT NULL,
          ordinal bigint NOT NULL CHECK (ordinal >= 0),
          source_locator_id uuid NOT NULL REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          normalized_text text NOT NULL,
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (normative_edition_id, structural_path),
          UNIQUE (structural_unit_id, normative_edition_id)
        );
        CREATE TABLE platform.applicability_contexts (
          applicability_context_id uuid PRIMARY KEY,
          context_version bigint NOT NULL CHECK (context_version >= 1),
          dimensions jsonb NOT NULL,
          unknown_behavior text NOT NULL CHECK (unknown_behavior IN ('indeterminate','block')),
          effective_from date,
          effective_to date,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from),
          UNIQUE (applicability_context_id, context_version)
        );
        ALTER TABLE platform.normative_editions ADD CONSTRAINT fk_edition_applicability
          FOREIGN KEY (applicability_context_id) REFERENCES platform.applicability_contexts(applicability_context_id) ON DELETE RESTRICT;
        CREATE TABLE platform.knowledge_assertions (
          knowledge_assertion_id uuid PRIMARY KEY,
          assertion_version bigint NOT NULL CHECK (assertion_version >= 1),
          assertion_type text NOT NULL CHECK (assertion_type IN ('definition','requirement','exception','permission','prohibition','reference_fact','promoted_knowledge')),
          normalized_proposition text NOT NULL,
          normative_edition_id uuid REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          structural_unit_id uuid REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          applicability_context_id uuid NOT NULL REFERENCES platform.applicability_contexts(applicability_context_id) ON DELETE RESTRICT,
          status text NOT NULL CHECK (status IN ('draft','reviewed','published','superseded','withdrawn')),
          reviewer_identity_id text NOT NULL,
          approval_decision_ref text NOT NULL,
          supersedes_assertion_id uuid REFERENCES platform.knowledge_assertions(knowledge_assertion_id) ON DELETE RESTRICT,
          evidence_capsule_id uuid,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          published_at timestamptz,
          UNIQUE (knowledge_assertion_id, assertion_version),
          CHECK (status <> 'published' OR (structural_unit_id IS NOT NULL OR evidence_capsule_id IS NOT NULL))
        );
        CREATE TABLE platform.assertion_evidence (
          assertion_evidence_id uuid PRIMARY KEY,
          knowledge_assertion_id uuid NOT NULL,
          assertion_version bigint NOT NULL,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          structural_unit_id uuid NOT NULL REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          source_locator_id uuid NOT NULL REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          evidence_role text NOT NULL,
          fragment_digest text NOT NULL CHECK (fragment_digest ~ '^sha256:[a-f0-9]{64}$'),
          verified_by_identity_id text NOT NULL,
          verified_at timestamptz NOT NULL,
          FOREIGN KEY (knowledge_assertion_id, assertion_version)
            REFERENCES platform.knowledge_assertions(knowledge_assertion_id, assertion_version) ON DELETE RESTRICT,
          UNIQUE (knowledge_assertion_id, assertion_version, source_locator_id, evidence_role)
        );
        CREATE FUNCTION platform.require_published_assertion_evidence()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.status = 'published' AND NOT EXISTS (
            SELECT 1 FROM platform.assertion_evidence ae
            WHERE ae.knowledge_assertion_id = NEW.knowledge_assertion_id
              AND ae.assertion_version = NEW.assertion_version
          ) THEN
            RAISE EXCEPTION 'published knowledge assertion requires exact evidence'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
        CREATE CONSTRAINT TRIGGER trg_published_assertion_requires_evidence
          AFTER INSERT OR UPDATE ON platform.knowledge_assertions
          DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION platform.require_published_assertion_evidence();
        CREATE TABLE platform.definitions (
          knowledge_assertion_id uuid PRIMARY KEY,
          term text NOT NULL,
          scope_qualifier text NOT NULL,
          FOREIGN KEY (knowledge_assertion_id) REFERENCES platform.knowledge_assertions(knowledge_assertion_id) ON DELETE RESTRICT
        );
        CREATE TABLE platform.requirements (
          knowledge_assertion_id uuid PRIMARY KEY,
          subject_type text NOT NULL,
          required_action text NOT NULL,
          condition_contract jsonb NOT NULL,
          outcome_contract text NOT NULL,
          FOREIGN KEY (knowledge_assertion_id) REFERENCES platform.knowledge_assertions(knowledge_assertion_id) ON DELETE RESTRICT
        );
        CREATE TABLE platform.exceptions (
          knowledge_assertion_id uuid PRIMARY KEY,
          affected_requirement_id uuid NOT NULL REFERENCES platform.requirements(knowledge_assertion_id) ON DELETE RESTRICT,
          exception_predicate jsonb NOT NULL,
          FOREIGN KEY (knowledge_assertion_id) REFERENCES platform.knowledge_assertions(knowledge_assertion_id) ON DELETE RESTRICT
        );
        CREATE TABLE platform.cross_references (
          cross_reference_id uuid PRIMARY KEY,
          source_structural_unit_id uuid NOT NULL REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          target_structural_unit_id uuid NOT NULL REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          relation_type text NOT NULL CHECK (relation_type IN ('references','defines','excepts','supersedes','amends','requires','conflicts_with')),
          evidence_locator_id uuid NOT NULL REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          UNIQUE (source_structural_unit_id, target_structural_unit_id, relation_type)
        );
        CREATE TABLE platform.normative_conflicts (
          normative_conflict_id uuid PRIMARY KEY,
          conflict_version bigint NOT NULL CHECK (conflict_version >= 1),
          subject_key text NOT NULL,
          participant_assertion_ids uuid[] NOT NULL,
          conflict_type text NOT NULL,
          conflict_policy_version_id uuid,
          state text NOT NULL CHECK (state IN ('open','indeterminate','resolved','superseded')),
          uncertainty_ref text,
          resolution_decision_ref text,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          UNIQUE (normative_conflict_id, conflict_version)
        );
        CREATE TABLE platform.knowledge_gaps (
          knowledge_gap_id uuid PRIMARY KEY,
          gap_type text NOT NULL CHECK (gap_type IN ('missing_source','missing_edition','edition_ambiguous','missing_locator','missing_evidence','projection_unavailable','applicability_indeterminate')),
          subject_key text NOT NULL,
          blocker_scope text NOT NULL,
          status text NOT NULL CHECK (status IN ('open','resolved','superseded')),
          evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    immutable = (
        "objects",
        "object_receipts",
        "source_versions",
        "source_locators",
        "evidence_links",
        "normative_editions",
        "normative_edition_states",
        "structural_units",
        "applicability_contexts",
        "knowledge_assertions",
        "assertion_evidence",
        "definitions",
        "requirements",
        "exceptions",
        "cross_references",
    )
    for table in immutable:
        _immutable_trigger("platform", table)


def _create_projection_plane() -> None:
    op.execute(
        """
        CREATE TABLE projection.lexical_index_versions (
          lexical_index_version_id uuid PRIMARY KEY,
          profile_key text NOT NULL,
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          canonical_snapshot_digest text NOT NULL CHECK (canonical_snapshot_digest ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('building','ready','empty','stale','failed')),
          build_revision bigint NOT NULL DEFAULT 1 CHECK (build_revision >= 1),
          built_at timestamptz,
          error_code text,
          UNIQUE (profile_key, profile_version, canonical_snapshot_digest)
        );
        CREATE TABLE projection.embedding_index_versions (
          embedding_index_version_id uuid PRIMARY KEY,
          profile_key text NOT NULL,
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          model_id text NOT NULL,
          model_revision text NOT NULL CHECK (lower(model_revision) <> 'latest'),
          dimension integer NOT NULL CHECK (dimension > 0 AND dimension <= 4096),
          dtype text NOT NULL CHECK (dtype IN ('float32','float16')),
          metric text NOT NULL CHECK (metric IN ('cosine','l2','inner_product')),
          index_profile text NOT NULL,
          chunker_version text NOT NULL CHECK (lower(chunker_version) <> 'latest'),
          instruction_version text NOT NULL CHECK (lower(instruction_version) <> 'latest'),
          canonical_snapshot_digest text NOT NULL CHECK (canonical_snapshot_digest ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('building','ready','empty','stale','failed')),
          built_at timestamptz,
          error_code text,
          UNIQUE (profile_key, profile_version, canonical_snapshot_digest)
        );
        CREATE TABLE projection.graph_projection_versions (
          graph_projection_version_id uuid PRIMARY KEY,
          profile_key text NOT NULL,
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          canonical_snapshot_digest text NOT NULL CHECK (canonical_snapshot_digest ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('building','ready','empty','stale','failed')),
          built_at timestamptz,
          error_code text,
          UNIQUE (profile_key, profile_version, canonical_snapshot_digest)
        );
        CREATE TABLE projection.lexical_entries (
          lexical_index_version_id uuid NOT NULL REFERENCES projection.lexical_index_versions(lexical_index_version_id) ON DELETE CASCADE,
          structural_unit_id uuid NOT NULL REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          normative_edition_id uuid NOT NULL REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          structural_path text NOT NULL,
          normalized_text text NOT NULL,
          search_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian', normalized_text)) STORED,
          PRIMARY KEY (lexical_index_version_id, structural_unit_id)
        );
        CREATE INDEX ix_g05_lexical_entries_fts ON projection.lexical_entries USING gin(search_vector);
        CREATE TABLE projection.embedding_entries (
          embedding_index_version_id uuid NOT NULL REFERENCES projection.embedding_index_versions(embedding_index_version_id) ON DELETE CASCADE,
          structural_unit_id uuid NOT NULL REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          dimension integer NOT NULL,
          embedding vector NOT NULL,
          vector_digest text NOT NULL CHECK (vector_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (embedding_index_version_id, structural_unit_id),
          CHECK (vector_dims(embedding) = dimension)
        );
        CREATE INDEX ix_g05_embedding_test_cosine_hnsw
          ON projection.embedding_entries USING hnsw ((embedding::vector(3)) vector_cosine_ops)
          WHERE dimension = 3;
        CREATE TABLE projection.typed_edges (
          graph_projection_version_id uuid NOT NULL REFERENCES projection.graph_projection_versions(graph_projection_version_id) ON DELETE CASCADE,
          typed_edge_id uuid NOT NULL,
          source_structural_unit_id uuid NOT NULL REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          target_structural_unit_id uuid NOT NULL REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          edge_type text NOT NULL,
          canonical_cross_reference_id uuid REFERENCES platform.cross_references(cross_reference_id) ON DELETE RESTRICT,
          derivation_profile_version text NOT NULL CHECK (lower(derivation_profile_version) <> 'latest'),
          PRIMARY KEY (graph_projection_version_id, typed_edge_id),
          UNIQUE (graph_projection_version_id, source_structural_unit_id, target_structural_unit_id, edge_type)
        );
        """
    )


def _create_rule_registry() -> None:
    op.execute(
        """
        CREATE TABLE platform.rules (
          rule_id uuid PRIMARY KEY,
          rule_key text NOT NULL UNIQUE,
          rule_class text NOT NULL,
          purpose text NOT NULL,
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE platform.rule_versions (
          rule_version_id uuid PRIMARY KEY,
          rule_id uuid NOT NULL REFERENCES platform.rules(rule_id) ON DELETE RESTRICT,
          version text NOT NULL CHECK (lower(version) <> 'latest'),
          predicate_contract jsonb NOT NULL,
          input_contract jsonb NOT NULL,
          output_contract jsonb NOT NULL,
          applicability_context_id uuid NOT NULL REFERENCES platform.applicability_contexts(applicability_context_id) ON DELETE RESTRICT,
          conflict_policy_version_id uuid,
          effective_from date,
          effective_to date,
          uncertainty_behavior text NOT NULL CHECK (uncertainty_behavior IN ('indeterminate','block')),
          failure_behavior text NOT NULL CHECK (failure_behavior = 'fail_closed'),
          implementation_binding text NOT NULL,
          test_manifest_digest text NOT NULL CHECK (test_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          author_identity_id text NOT NULL,
          supersedes_rule_version_id uuid REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from),
          UNIQUE (rule_id, version)
        );
        CREATE TABLE platform.rule_evidence (
          rule_evidence_id uuid PRIMARY KEY,
          rule_version_id uuid NOT NULL REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          assertion_evidence_id uuid NOT NULL REFERENCES platform.assertion_evidence(assertion_evidence_id) ON DELETE RESTRICT,
          source_authority_layer text NOT NULL,
          applicability_basis text NOT NULL,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          UNIQUE (rule_version_id, assertion_evidence_id)
        );
        CREATE TABLE platform.rule_version_states (
          rule_version_state_id uuid PRIMARY KEY,
          rule_version_id uuid NOT NULL REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          state_sequence bigint NOT NULL CHECK (state_sequence >= 1),
          status text NOT NULL CHECK (status IN ('drafted','evidence_attached','candidate','reviewed','approved','active','suspended','superseded','retired','rejected')),
          authority_identity_id text NOT NULL,
          decision_ref text NOT NULL,
          effective_at timestamptz NOT NULL,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (rule_version_id, state_sequence)
        );
        CREATE TABLE platform.rule_reviews (
          rule_review_id uuid PRIMARY KEY,
          rule_version_id uuid NOT NULL REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          reviewer_identity_id text NOT NULL,
          reviewer_qualification_ref text NOT NULL,
          test_manifest_digest text NOT NULL CHECK (test_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          outcome text NOT NULL CHECK (outcome IN ('passed','rejected','blocked')),
          reviewed_at timestamptz NOT NULL,
          UNIQUE (rule_version_id, reviewer_identity_id)
        );
        CREATE TABLE platform.rule_approvals (
          rule_approval_id uuid PRIMARY KEY,
          rule_version_id uuid NOT NULL UNIQUE REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          reviewer_identity_id text NOT NULL,
          approver_identity_id text NOT NULL,
          approver_qualification_ref text NOT NULL,
          authority_reference text NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('approved','rejected')),
          approved_at timestamptz NOT NULL,
          CHECK (reviewer_identity_id <> approver_identity_id)
        );
        CREATE TABLE platform.conflict_policy_versions (
          conflict_policy_version_id uuid PRIMARY KEY,
          conflict_group_key text NOT NULL,
          version text NOT NULL CHECK (lower(version) <> 'latest'),
          subject_domain text NOT NULL,
          predicate_contract jsonb NOT NULL,
          outcome_contract jsonb NOT NULL,
          authority_reference text NOT NULL,
          status text NOT NULL CHECK (status IN ('approved','active','suspended','superseded','retired')),
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          UNIQUE (conflict_group_key, version)
        );
        ALTER TABLE platform.rule_versions ADD CONSTRAINT fk_rule_conflict_policy
          FOREIGN KEY (conflict_policy_version_id) REFERENCES platform.conflict_policy_versions(conflict_policy_version_id) ON DELETE RESTRICT;
        ALTER TABLE platform.normative_conflicts ADD CONSTRAINT fk_normative_conflict_policy
          FOREIGN KEY (conflict_policy_version_id) REFERENCES platform.conflict_policy_versions(conflict_policy_version_id) ON DELETE RESTRICT;
        CREATE TABLE platform.rule_set_versions (
          rule_set_version_id uuid PRIMARY KEY,
          rule_set_key text NOT NULL,
          version text NOT NULL CHECK (lower(version) <> 'latest'),
          status text NOT NULL CHECK (status IN ('approved','active','suspended','superseded','retired')),
          manifest_digest text NOT NULL CHECK (manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          schema_version text NOT NULL CHECK (lower(schema_version) <> 'latest'),
          compatibility_contract jsonb NOT NULL,
          approval_decision_ref text NOT NULL,
          approved_by_identity_id text NOT NULL,
          effective_from date,
          effective_to date,
          supersedes_rule_set_version_id uuid REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          UNIQUE (rule_set_key, version),
          CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from)
        );
        CREATE TABLE platform.rule_set_memberships (
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          rule_version_id uuid NOT NULL REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          membership_role text NOT NULL,
          ordinal bigint NOT NULL CHECK (ordinal >= 0),
          rule_integrity_digest text NOT NULL CHECK (rule_integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (rule_set_version_id, rule_version_id, membership_role),
          UNIQUE (rule_set_version_id, ordinal)
        );
        """
    )
    for table in (
        "rule_versions",
        "rule_evidence",
        "rule_version_states",
        "rule_reviews",
        "rule_approvals",
        "conflict_policy_versions",
        "rule_set_versions",
        "rule_set_memberships",
    ):
        _immutable_trigger("platform", table)


def _create_workspace_rules() -> None:
    op.execute(
        """
        CREATE TABLE workspace.rules (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          rule_id uuid NOT NULL,
          rule_key text NOT NULL,
          rule_class text NOT NULL,
          purpose text NOT NULL,
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, rule_id),
          UNIQUE (organization_id, workspace_id, rule_key),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.rule_versions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          rule_version_id uuid NOT NULL,
          rule_id uuid NOT NULL,
          version text NOT NULL CHECK (lower(version) <> 'latest'),
          predicate_contract jsonb NOT NULL,
          input_contract jsonb NOT NULL,
          output_contract jsonb NOT NULL,
          effective_from date,
          effective_to date,
          failure_behavior text NOT NULL CHECK (failure_behavior = 'fail_closed'),
          test_manifest_digest text NOT NULL CHECK (test_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          author_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, rule_version_id),
          FOREIGN KEY (organization_id, workspace_id, rule_id) REFERENCES workspace.rules(organization_id, workspace_id, rule_id) ON DELETE RESTRICT,
          UNIQUE (organization_id, workspace_id, rule_id, version),
          CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from)
        );
        CREATE TABLE workspace.rule_version_states (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          rule_version_state_id uuid NOT NULL,
          rule_version_id uuid NOT NULL,
          state_sequence bigint NOT NULL CHECK (state_sequence >= 1),
          status text NOT NULL CHECK (status IN ('drafted','evidence_attached','candidate','reviewed','approved','active','suspended','superseded','retired','rejected')),
          authority_identity_id text NOT NULL,
          decision_ref text NOT NULL,
          effective_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, rule_version_state_id),
          FOREIGN KEY (organization_id, workspace_id, rule_version_id) REFERENCES workspace.rule_versions(organization_id, workspace_id, rule_version_id) ON DELETE RESTRICT,
          UNIQUE (organization_id, workspace_id, rule_version_id, state_sequence)
        );
        CREATE TABLE workspace.rule_evidence (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          rule_evidence_id uuid NOT NULL,
          rule_version_id uuid NOT NULL,
          source_version_id uuid NOT NULL,
          source_locator_id uuid NOT NULL,
          evidence_role text NOT NULL,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id, workspace_id, rule_evidence_id),
          FOREIGN KEY (organization_id, workspace_id, rule_version_id) REFERENCES workspace.rule_versions(organization_id, workspace_id, rule_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id, workspace_id, source_version_id) REFERENCES workspace.source_versions(organization_id, workspace_id, source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id, workspace_id, source_locator_id) REFERENCES workspace.source_locators(organization_id, workspace_id, source_locator_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.rule_evaluations (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          rule_evaluation_id uuid NOT NULL,
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          rule_version_id uuid NOT NULL REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          applicability text NOT NULL CHECK (applicability IN ('applicable','not_applicable','indeterminate')),
          outcome text NOT NULL CHECK (outcome IN ('pass','fail','blocked','conflict','not_evaluated')),
          input_snapshot jsonb NOT NULL,
          typed_output jsonb NOT NULL,
          deterministic_fingerprint text NOT NULL CHECK (deterministic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          policy_versions jsonb NOT NULL,
          evaluated_at timestamptz NOT NULL,
          correlation_id uuid NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, rule_evaluation_id),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.rule_traces (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          rule_trace_id uuid NOT NULL,
          rule_evaluation_id uuid NOT NULL,
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          rule_version_id uuid NOT NULL REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          trace_payload jsonb NOT NULL,
          deterministic_fingerprint text NOT NULL CHECK (deterministic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, rule_trace_id),
          UNIQUE (organization_id, workspace_id, rule_evaluation_id),
          FOREIGN KEY (organization_id, workspace_id, rule_evaluation_id) REFERENCES workspace.rule_evaluations(organization_id, workspace_id, rule_evaluation_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.controlled_rule_set_upgrades (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          upgrade_id uuid NOT NULL,
          source_rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          target_rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          impact_preview_digest text NOT NULL CHECK (impact_preview_digest ~ '^sha256:[a-f0-9]{64}$'),
          compatibility_result text NOT NULL CHECK (compatibility_result IN ('compatible','incompatible','indeterminate')),
          authority_reference text NOT NULL,
          status text NOT NULL CHECK (status IN ('previewed','approved','adopted','blocked','failed')),
          revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, upgrade_id),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT,
          CHECK (source_rule_set_version_id <> target_rule_set_version_id)
        );
        """
    )
    for table in (
        "rule_versions",
        "rule_version_states",
        "rule_evidence",
        "rule_evaluations",
        "rule_traces",
    ):
        _immutable_trigger("workspace", table)


def _create_promotion_gate() -> None:
    op.execute(
        """
        CREATE TABLE workspace.promotion_candidates (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          promotion_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL CHECK (candidate_version >= 1),
          intended_platform_kind text NOT NULL CHECK (intended_platform_kind IN ('knowledge_assertion','rule','template','classifier','fixture')),
          proposition_class text NOT NULL,
          sanitized_payload jsonb,
          state text NOT NULL CHECK (state IN ('workspace_observation','promotion_candidate','anonymized','evidence_verified','applicability_defined','regression_tested','approved','rejected','published')),
          revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
          confidence_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_by_identity_id text NOT NULL,
          correlation_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, promotion_candidate_id),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.promotion_anonymization_results (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          anonymization_result_id uuid NOT NULL,
          promotion_candidate_id uuid NOT NULL,
          transformation_version text NOT NULL CHECK (lower(transformation_version) <> 'latest'),
          prohibited_field_scan_passed boolean NOT NULL,
          reconstructive_content_detected boolean NOT NULL,
          sanitized_payload_digest text NOT NULL CHECK (sanitized_payload_digest ~ '^sha256:[a-f0-9]{64}$'),
          reviewer_identity_id text NOT NULL,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, anonymization_result_id),
          FOREIGN KEY (organization_id, workspace_id, promotion_candidate_id) REFERENCES workspace.promotion_candidates(organization_id, workspace_id, promotion_candidate_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.promotion_regression_results (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          regression_result_id uuid NOT NULL,
          promotion_candidate_id uuid NOT NULL,
          test_manifest_digest text NOT NULL CHECK (test_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          outcome text NOT NULL CHECK (outcome IN ('passed','failed','blocked')),
          leakage_tests_passed boolean NOT NULL,
          executed_by_service_id text NOT NULL,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, regression_result_id),
          FOREIGN KEY (organization_id, workspace_id, promotion_candidate_id) REFERENCES workspace.promotion_candidates(organization_id, workspace_id, promotion_candidate_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.promotion_decisions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          promotion_decision_id uuid NOT NULL,
          promotion_candidate_id uuid NOT NULL,
          decision text NOT NULL CHECK (decision IN ('approved','rejected')),
          approver_identity_id text NOT NULL,
          authority_reference text NOT NULL,
          reason_code text NOT NULL,
          decided_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, promotion_decision_id),
          UNIQUE (organization_id, workspace_id, promotion_candidate_id),
          FOREIGN KEY (organization_id, workspace_id, promotion_candidate_id) REFERENCES workspace.promotion_candidates(organization_id, workspace_id, promotion_candidate_id) ON DELETE RESTRICT
        );
        CREATE TABLE platform.evidence_capsules (
          evidence_capsule_id uuid PRIMARY KEY,
          capsule_version bigint NOT NULL CHECK (capsule_version >= 1),
          proposition_class text NOT NULL,
          non_reconstructive_summary jsonb NOT NULL,
          anonymization_profile_version text NOT NULL CHECK (lower(anonymization_profile_version) <> 'latest'),
          regression_manifest_digest text NOT NULL CHECK (regression_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          promotion_decision_digest text NOT NULL CHECK (promotion_decision_digest ~ '^sha256:[a-f0-9]{64}$'),
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          published_by_identity_id text NOT NULL,
          published_at timestamptz NOT NULL
        );
        ALTER TABLE platform.knowledge_assertions ADD CONSTRAINT fk_assertion_evidence_capsule
          FOREIGN KEY (evidence_capsule_id) REFERENCES platform.evidence_capsules(evidence_capsule_id) ON DELETE RESTRICT;
        CREATE TABLE platform.promotion_publications (
          promotion_publication_id uuid PRIMARY KEY,
          evidence_capsule_id uuid NOT NULL REFERENCES platform.evidence_capsules(evidence_capsule_id) ON DELETE RESTRICT,
          published_entity_kind text NOT NULL,
          published_entity_id uuid NOT NULL,
          content_free_lineage_digest text NOT NULL CHECK (content_free_lineage_digest ~ '^sha256:[a-f0-9]{64}$'),
          published_at timestamptz NOT NULL,
          UNIQUE (published_entity_kind, published_entity_id)
        );
        """
    )
    _immutable_trigger("platform", "evidence_capsules")
    _immutable_trigger("platform", "promotion_publications")
    for table in (
        "promotion_anonymization_results",
        "promotion_regression_results",
        "promotion_decisions",
    ):
        _immutable_trigger("workspace", table)


def _create_platform_audit() -> None:
    op.execute(
        """
        CREATE TABLE audit.platform_records (
          audit_record_id uuid PRIMARY KEY,
          audit_version integer NOT NULL CHECK (audit_version >= 1),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          actor_identity_id text,
          service_identity_id text,
          capability text NOT NULL,
          operation text NOT NULL,
          outcome_code text NOT NULL,
          contract_key text NOT NULL,
          contract_version text NOT NULL CHECK (lower(contract_version) <> 'latest'),
          policy_key text NOT NULL,
          policy_version text NOT NULL CHECK (lower(policy_version) <> 'latest'),
          correlation_id uuid NOT NULL,
          causation_id uuid,
          safe_message_key text NOT NULL,
          diagnostic_reference text,
          retention_class text NOT NULL,
          record_digest text NOT NULL CHECK (record_digest ~ '^sha256:[a-f0-9]{64}$'),
          CHECK (actor_identity_id IS NOT NULL OR service_identity_id IS NOT NULL)
        );
        CREATE TRIGGER trg_platform_audit_no_update BEFORE UPDATE ON audit.platform_records
          FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();
        CREATE TRIGGER trg_platform_audit_no_delete BEFORE DELETE ON audit.platform_records
          FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();
        """
    )


def _apply_grants_and_rls() -> None:
    op.execute("GRANT USAGE ON SCHEMA platform, projection, audit TO asd_platform_curator")
    op.execute("GRANT USAGE ON SCHEMA platform, projection TO asd_projection_builder")
    op.execute("GRANT USAGE ON SCHEMA projection TO asd_app")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA platform, projection TO asd_app")
    curator_tables = PLATFORM_TABLES
    for table in curator_tables:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON platform.{table} TO asd_platform_curator")
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE ON audit.platform_records FROM asd_platform_curator"
    )
    op.execute("GRANT SELECT, INSERT ON audit.platform_records TO asd_platform_curator")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA platform TO asd_projection_builder")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA projection TO asd_projection_builder"
    )
    workspace_tables = (
        "source_artifacts",
        "source_object_receipts",
        "acquisition_attempts",
        "source_versions",
        "source_locators",
        "evidence_links",
        "rules",
        "rule_versions",
        "rule_version_states",
        "rule_evidence",
        "rule_evaluations",
        "rule_traces",
        "controlled_rule_set_upgrades",
        "promotion_candidates",
        "promotion_anonymization_results",
        "promotion_regression_results",
        "promotion_decisions",
    )
    for table in workspace_tables:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON workspace.{table} TO asd_app")
        _enable_workspace_rls(table)


def _immutable_trigger(schema: str, table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {schema}.{table} "
        "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
    )


def _enable_workspace_rls(table: str) -> None:
    predicate = (
        "organization_id = NULLIF(current_setting('asd.organization_id', true), '')::uuid "
        "AND workspace_id = NULLIF(current_setting('asd.workspace_id', true), '')::uuid"
    )
    op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_scope_policy ON workspace.{table} FOR ALL TO asd_app "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "destructive downgrade is forbidden; set ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1 "
            "only for a disposable development/test database"
        )
    op.execute("DROP TABLE IF EXISTS audit.platform_records CASCADE")
    op.execute("DROP SCHEMA IF EXISTS projection CASCADE")
    for table in WORKSPACE_TABLES:
        op.execute(f"DROP TABLE IF EXISTS workspace.{table} CASCADE")
    for table in PLATFORM_TABLES:
        op.execute(f"DROP TABLE IF EXISTS platform.{table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS platform.reject_immutable_mutation() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS platform.require_published_assertion_evidence() CASCADE")
    # Cluster roles and vector extension are retained. Production rollback is
    # forward repair or verified restore, never this disposable downgrade.
