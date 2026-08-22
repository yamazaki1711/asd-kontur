"""Create the G-06 workspace lifecycle foundation.

Revision ID: 0003_g06
Revises: 0002_g05
Create Date: 2026-08-23
"""

from __future__ import annotations

import os

from alembic import op

revision = "0003_g06"
down_revision = "0002_g05"
branch_labels = None
depends_on = None


WORKSPACE_TABLES = (
    "lifecycle_commands",
    "lifecycle_transition_history",
    "freeze_manifests",
    "finalization_reports",
    "export_operations",
    "export_items",
    "archive_packages",
    "archive_items",
    "archive_verifications",
    "archive_imports",
    "legal_holds",
    "deletion_plans",
    "destructive_authorizations",
    "destructive_authorization_invalidations",
    "adapter_receipts",
    "recovery_checkpoints",
    "residual_verifications",
    "destruction_attestations",
)

MATERIAL_TABLES = (
    "objects",
    "object_links",
    "mode_executions",
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


def upgrade() -> None:
    _create_roles()
    _upgrade_workspace_aggregate()
    _create_policy_registries()
    _create_lifecycle_relations()
    _create_guards_and_transition_function()
    _apply_grants_and_rls()


def _create_roles() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_lifecycle_service') THEN "
        "CREATE ROLE asd_lifecycle_service NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_destruction_executor') THEN "
        "CREATE ROLE asd_destruction_executor NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_lifecycle_verifier') THEN "
        "CREATE ROLE asd_lifecycle_verifier NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; "
        "END $$"
    )


def _upgrade_workspace_aggregate() -> None:
    op.execute("ALTER TABLE workspace.workspaces DROP CONSTRAINT ck_workspace_lifecycle_state")
    op.execute("UPDATE workspace.workspaces SET lifecycle_state=upper(lifecycle_state)")
    op.execute("UPDATE workspace.workspace_revisions SET lifecycle_state=upper(lifecycle_state)")
    op.execute(
        "ALTER TABLE workspace.workspaces "
        "ADD COLUMN lifecycle_version bigint NOT NULL DEFAULT 1 CHECK (lifecycle_version >= 1), "
        "ADD COLUMN workspace_revision bigint NOT NULL DEFAULT 1 CHECK (workspace_revision >= 1), "
        "ADD COLUMN write_fenced boolean NOT NULL DEFAULT false, "
        "ADD COLUMN legal_hold_active boolean NOT NULL DEFAULT false, "
        "ADD COLUMN purge_started_at timestamptz, "
        "ADD COLUMN destroyed_at timestamptz"
    )
    states = (
        "'PROVISIONING','ACTIVE','FREEZING','FROZEN','FINALIZING','FINALIZED',"
        "'EXPORTING','EXPORTED','ARCHIVING','ARCHIVED','CLOSED','REOPENING',"
        "'RESET_PLANNING','RESET_AUTHORIZED','PURGING','VERIFYING_RESET',"
        "'RESET_VERIFIED','DESTROYING','DESTROYED','RECOVERY_REQUIRED','QUARANTINED'"
    )
    op.execute(
        f"ALTER TABLE workspace.workspaces ADD CONSTRAINT ck_workspace_lifecycle_state "
        f"CHECK (lifecycle_state IN ({states}))"
    )
    op.execute(
        "ALTER TABLE workspace.workspace_revisions ADD CONSTRAINT "
        f"ck_workspace_revision_lifecycle_state CHECK (lifecycle_state IN ({states}))"
    )
    op.execute(
        "ALTER TABLE workspace.mode_executions "
        "ADD COLUMN process_definition_key text NOT NULL DEFAULT 'process.synthetic', "
        "ADD COLUMN process_definition_version text NOT NULL DEFAULT '0.1.0', "
        "ADD COLUMN authority_profile_key text NOT NULL DEFAULT 'authority.synthetic', "
        "ADD COLUMN authority_profile_version text NOT NULL DEFAULT '0.1.0', "
        "ADD COLUMN output_contract_key text NOT NULL DEFAULT 'mode.terminal-result', "
        "ADD COLUMN output_contract_version text NOT NULL DEFAULT '0.1.0'"
    )
    op.execute(
        "ALTER TABLE workspace.mode_executions ADD CONSTRAINT ck_mode_execution_g06_exact_versions "
        "CHECK (lower(process_definition_version)<>'latest' AND "
        "lower(authority_profile_version)<>'latest' AND lower(output_contract_version)<>'latest')"
    )


def _create_policy_registries() -> None:
    op.execute(
        """
        CREATE TABLE platform.retention_profile_versions (
          retention_profile_id uuid PRIMARY KEY,
          profile_key text NOT NULL,
          version text NOT NULL,
          environment text NOT NULL CHECK (environment IN ('development','qualification','production')),
          complete boolean NOT NULL,
          production_approved boolean NOT NULL,
          data_class_policies jsonb NOT NULL,
          owner_identity_id text NOT NULL,
          approver_identity_id text,
          effective_from timestamptz NOT NULL,
          effective_until timestamptz,
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          UNIQUE (profile_key, version),
          CHECK (lower(version) <> 'latest'),
          CHECK (environment <> 'production' OR NOT production_approved OR approver_identity_id IS NOT NULL)
        );
        CREATE TABLE platform.basis_registry_versions (
          basis_registry_version_id uuid PRIMARY KEY,
          registry_key text NOT NULL,
          version text NOT NULL,
          basis_code text NOT NULL,
          environment text NOT NULL CHECK (environment IN ('development','qualification','production')),
          evidence_refs jsonb NOT NULL,
          owner_identity_id text NOT NULL,
          approver_identity_id text,
          effective_from timestamptz NOT NULL,
          effective_until timestamptz,
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          UNIQUE (registry_key, version, basis_code),
          CHECK (lower(version) <> 'latest'),
          CHECK (jsonb_array_length(evidence_refs) > 0)
        );
        CREATE TABLE platform.storage_adapter_registry_versions (
          adapter_registry_version_id uuid PRIMARY KEY,
          registry_key text NOT NULL,
          version text NOT NULL,
          environment text NOT NULL CHECK (environment IN ('development','qualification','production')),
          status text NOT NULL CHECK (status IN ('draft','active','blocked','retired')),
          owner_identity_id text NOT NULL,
          approved_by_identity_id text,
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          UNIQUE (registry_key, version),
          CHECK (lower(version) <> 'latest')
        );
        CREATE TABLE platform.storage_adapter_registry_entries (
          adapter_registry_version_id uuid NOT NULL REFERENCES platform.storage_adapter_registry_versions(adapter_registry_version_id) ON DELETE RESTRICT,
          adapter_key text NOT NULL,
          adapter_version text NOT NULL,
          storage_class text NOT NULL,
          data_plane text NOT NULL CHECK (data_plane IN ('authoritative','derived','operational','archive','recovery','external_residue')),
          scope text NOT NULL CHECK (scope IN ('platform','workspace','external')),
          required boolean NOT NULL,
          inventory_capable boolean NOT NULL,
          purge_capable boolean NOT NULL,
          residue_verification_capable boolean NOT NULL,
          destroy_capable boolean NOT NULL,
          receipt_schema_version text NOT NULL,
          health text NOT NULL CHECK (health IN ('available','unavailable','degraded')),
          PRIMARY KEY (adapter_registry_version_id, adapter_key),
          CHECK (lower(adapter_version) <> 'latest' AND lower(receipt_schema_version) <> 'latest')
        );
        """
    )
    for table in (
        "retention_profile_versions",
        "basis_registry_versions",
        "storage_adapter_registry_versions",
        "storage_adapter_registry_entries",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON platform.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )


def _create_lifecycle_relations() -> None:
    op.execute(
        """
        CREATE TABLE workspace.lifecycle_commands (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          operation_key text NOT NULL,
          semantic_digest text NOT NULL CHECK (semantic_digest ~ '^sha256:[a-f0-9]{64}$'),
          target_state text NOT NULL,
          expected_version bigint NOT NULL,
          outcome_state text,
          outcome_version bigint,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          completed_at timestamptz,
          PRIMARY KEY (organization_id, workspace_id, operation_key),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.lifecycle_transition_history (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          lifecycle_version bigint NOT NULL,
          transition_id uuid NOT NULL,
          operation_key text NOT NULL,
          prior_state text NOT NULL,
          new_state text NOT NULL,
          actor_identity_id text,
          service_identity_id text,
          authority_reference text NOT NULL,
          correlation_id uuid NOT NULL,
          causation_id uuid,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, lifecycle_version),
          UNIQUE (transition_id),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT,
          CHECK (actor_identity_id IS NOT NULL OR service_identity_id IS NOT NULL)
        );
        CREATE TABLE workspace.freeze_manifests (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          freeze_manifest_id uuid NOT NULL,
          lifecycle_version bigint NOT NULL,
          workspace_revision bigint NOT NULL,
          canonical_revision_digest text NOT NULL CHECK (canonical_revision_digest ~ '^sha256:[a-f0-9]{64}$'),
          writer_count integer NOT NULL CHECK (writer_count=0),
          job_inventory jsonb NOT NULL,
          result text NOT NULL CHECK (result IN ('verified','blocked','failed')),
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, freeze_manifest_id),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.finalization_reports (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          finalization_report_id uuid NOT NULL,
          lifecycle_version bigint NOT NULL,
          result_manifest_digest text NOT NULL CHECK (result_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          blockers jsonb NOT NULL,
          uncertainties jsonb NOT NULL,
          mode_terminal_statuses jsonb NOT NULL,
          production_ready_claim boolean NOT NULL DEFAULT false CHECK (production_ready_claim=false),
          outcome text NOT NULL CHECK (outcome IN ('verified','blocked','failed')),
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, finalization_report_id),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.export_operations (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          export_operation_id uuid NOT NULL,
          idempotency_key text NOT NULL,
          workspace_revision bigint NOT NULL,
          package_digest text CHECK (package_digest ~ '^sha256:[a-f0-9]{64}$'),
          manifest_digest text CHECK (manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          state text NOT NULL CHECK (state IN ('staging','verified','failed','quarantined')),
          verification_report jsonb,
          receipt_ref text,
          contract_version text NOT NULL,
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          completed_at timestamptz,
          PRIMARY KEY (organization_id, workspace_id, export_operation_id),
          UNIQUE (organization_id, workspace_id, idempotency_key),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT,
          CHECK (lower(contract_version)<>'latest'),
          CHECK (state<>'verified' OR (package_digest IS NOT NULL AND manifest_digest IS NOT NULL AND receipt_ref IS NOT NULL))
        );
        CREATE TABLE workspace.export_items (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          export_operation_id uuid NOT NULL,
          export_item_id uuid NOT NULL,
          source_version_ref text NOT NULL,
          object_version_ref text NOT NULL,
          logical_path text NOT NULL CHECK (logical_path !~ '(^/|(^|/)\\.\\.(/|$))'),
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          size_bytes bigint NOT NULL CHECK (size_bytes>=0),
          media_type text NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, export_operation_id, export_item_id),
          UNIQUE (organization_id, workspace_id, export_operation_id, logical_path),
          FOREIGN KEY (organization_id, workspace_id, export_operation_id) REFERENCES workspace.export_operations(organization_id, workspace_id, export_operation_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.archive_packages (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          archive_package_id uuid NOT NULL,
          export_operation_id uuid NOT NULL,
          package_version text NOT NULL,
          workspace_revision bigint NOT NULL,
          package_digest text NOT NULL CHECK (package_digest ~ '^sha256:[a-f0-9]{64}$'),
          manifest_digest text NOT NULL CHECK (manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          storage_adapter_key text NOT NULL,
          sealed_at timestamptz NOT NULL,
          import_compatibility text NOT NULL CHECK (import_compatibility IN ('not_importable','read_only_import','new_workspace_seed')),
          state text NOT NULL CHECK (state IN ('sealed','verified','failed','destroyed','quarantined')),
          PRIMARY KEY (organization_id, workspace_id, archive_package_id),
          UNIQUE (archive_package_id),
          FOREIGN KEY (organization_id, workspace_id, export_operation_id) REFERENCES workspace.export_operations(organization_id, workspace_id, export_operation_id) ON DELETE RESTRICT,
          CHECK (lower(package_version)<>'latest')
        );
        CREATE TABLE workspace.archive_items (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          archive_package_id uuid NOT NULL,
          archive_item_id uuid NOT NULL,
          logical_path text NOT NULL CHECK (logical_path !~ '(^/|(^|/)\\.\\.(/|$))'),
          new_import_identity_required boolean NOT NULL DEFAULT true CHECK (new_import_identity_required),
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          size_bytes bigint NOT NULL CHECK (size_bytes>=0),
          media_type text NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, archive_package_id, archive_item_id),
          UNIQUE (organization_id, workspace_id, archive_package_id, logical_path),
          FOREIGN KEY (organization_id, workspace_id, archive_package_id) REFERENCES workspace.archive_packages(organization_id, workspace_id, archive_package_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.archive_verifications (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          archive_verification_id uuid NOT NULL,
          archive_package_id uuid NOT NULL,
          expected_count bigint NOT NULL,
          observed_count bigint NOT NULL,
          missing_count bigint NOT NULL,
          extra_count bigint NOT NULL,
          changed_count bigint NOT NULL,
          readability_passed boolean NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('verified','failed','quarantined')),
          verifier_identity_id text NOT NULL,
          verified_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, archive_verification_id),
          FOREIGN KEY (organization_id, workspace_id, archive_package_id) REFERENCES workspace.archive_packages(organization_id, workspace_id, archive_package_id) ON DELETE RESTRICT,
          CHECK (outcome<>'verified' OR (expected_count=observed_count AND missing_count=0 AND extra_count=0 AND changed_count=0 AND readability_passed))
        );
        CREATE TABLE workspace.archive_imports (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          archive_import_id uuid NOT NULL,
          source_archive_package_id uuid NOT NULL,
          source_workspace_id uuid NOT NULL,
          new_workspace_revision bigint NOT NULL,
          id_mapping_digest text NOT NULL CHECK (id_mapping_digest ~ '^sha256:[a-f0-9]{64}$'),
          schema_compatibility text NOT NULL CHECK (schema_compatibility IN ('compatible','requires_migration','incompatible')),
          authorization_reference text NOT NULL,
          status text NOT NULL CHECK (status IN ('planned','verified','imported','blocked','failed','quarantined')),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, archive_import_id),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT,
          CHECK (workspace_id <> source_workspace_id)
        );
        CREATE TABLE workspace.legal_holds (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          legal_hold_id uuid NOT NULL,
          hold_version bigint NOT NULL CHECK (hold_version>=1),
          basis_code text NOT NULL,
          evidence_refs jsonb NOT NULL CHECK (jsonb_array_length(evidence_refs)>0),
          authority_identity_id text NOT NULL,
          suspended_state text NOT NULL,
          reason_code text NOT NULL,
          effective_from timestamptz NOT NULL,
          effective_until timestamptz,
          released_by_identity_id text,
          release_decision_ref text,
          PRIMARY KEY (organization_id, workspace_id, legal_hold_id, hold_version),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT,
          CHECK ((effective_until IS NULL) = (released_by_identity_id IS NULL))
        );
        CREATE TABLE workspace.deletion_plans (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          deletion_plan_id uuid NOT NULL,
          plan_version bigint NOT NULL CHECK (plan_version>=1),
          operation_kind text NOT NULL CHECK (operation_kind IN ('reset','destroy')),
          lifecycle_version bigint NOT NULL,
          workspace_revision bigint NOT NULL,
          retention_profile_key text NOT NULL,
          retention_profile_version text NOT NULL,
          basis_registry_key text NOT NULL,
          basis_registry_version text NOT NULL,
          basis_code text NOT NULL,
          basis_evidence_refs jsonb NOT NULL CHECK (jsonb_array_length(basis_evidence_refs)>0),
          legal_hold_checked_at timestamptz NOT NULL,
          adapter_registry_key text NOT NULL,
          adapter_registry_version text NOT NULL,
          inventory_digest text NOT NULL CHECK (inventory_digest ~ '^sha256:[a-f0-9]{64}$'),
          deletion_items jsonb NOT NULL,
          expected_residue_classes jsonb NOT NULL,
          requester_identity_id text NOT NULL,
          dry_run_result text NOT NULL CHECK (dry_run_result IN ('complete','blocked','failed')),
          expires_at timestamptz NOT NULL,
          plan_digest text NOT NULL CHECK (plan_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, deletion_plan_id, plan_version),
          UNIQUE (organization_id, workspace_id, plan_digest),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT,
          CHECK (lower(retention_profile_version)<>'latest' AND lower(basis_registry_version)<>'latest' AND lower(adapter_registry_version)<>'latest')
        );
        CREATE TABLE workspace.destructive_authorizations (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          authorization_id uuid NOT NULL,
          deletion_plan_id uuid NOT NULL,
          plan_version bigint NOT NULL,
          plan_digest text NOT NULL,
          requester_identity_id text NOT NULL,
          confirmer_identity_id text NOT NULL,
          executor_identity_id text NOT NULL,
          verifier_identity_id text NOT NULL,
          legal_hold_check_id uuid NOT NULL,
          authorized_at timestamptz NOT NULL,
          expires_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, authorization_id),
          FOREIGN KEY (organization_id, workspace_id, deletion_plan_id, plan_version) REFERENCES workspace.deletion_plans(organization_id, workspace_id, deletion_plan_id, plan_version) ON DELETE RESTRICT,
          CHECK (requester_identity_id<>confirmer_identity_id AND requester_identity_id<>executor_identity_id AND requester_identity_id<>verifier_identity_id AND confirmer_identity_id<>executor_identity_id AND confirmer_identity_id<>verifier_identity_id AND executor_identity_id<>verifier_identity_id),
          CHECK (expires_at>authorized_at)
        );
        CREATE TABLE workspace.destructive_authorization_invalidations (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          authorization_id uuid NOT NULL,
          invalidation_id uuid NOT NULL,
          reason_code text NOT NULL,
          invalidated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, invalidation_id),
          UNIQUE (organization_id, workspace_id, authorization_id),
          FOREIGN KEY (organization_id, workspace_id, authorization_id) REFERENCES workspace.destructive_authorizations(organization_id, workspace_id, authorization_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.adapter_receipts (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          adapter_receipt_id uuid NOT NULL,
          deletion_plan_id uuid NOT NULL,
          plan_version bigint NOT NULL,
          operation_id uuid NOT NULL,
          adapter_key text NOT NULL,
          item_id text NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('deleted','already_absent','failed','incomplete','residue_detected')),
          before_count bigint NOT NULL CHECK (before_count>=0),
          after_count bigint NOT NULL CHECK (after_count>=0),
          receipt_schema_version text NOT NULL,
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, adapter_receipt_id),
          UNIQUE (organization_id, workspace_id, operation_id, adapter_key, item_id),
          FOREIGN KEY (organization_id, workspace_id, deletion_plan_id, plan_version) REFERENCES workspace.deletion_plans(organization_id, workspace_id, deletion_plan_id, plan_version) ON DELETE RESTRICT,
          CHECK (lower(receipt_schema_version)<>'latest')
        );
        CREATE TABLE workspace.recovery_checkpoints (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          recovery_checkpoint_id uuid NOT NULL,
          operation_id uuid NOT NULL,
          plan_digest text NOT NULL,
          failed_operation text NOT NULL,
          affected_adapters jsonb NOT NULL,
          completed_effects jsonb NOT NULL,
          pending_items jsonb NOT NULL,
          status text NOT NULL CHECK (status IN ('required','retrying','compensating','superseded','resolved','quarantined')),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, recovery_checkpoint_id),
          FOREIGN KEY (organization_id, workspace_id) REFERENCES workspace.workspaces(organization_id, workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.residual_verifications (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          residual_verification_id uuid NOT NULL,
          deletion_plan_id uuid NOT NULL,
          plan_version bigint NOT NULL,
          adapter_key text NOT NULL,
          scan_methods jsonb NOT NULL,
          found_count bigint NOT NULL CHECK (found_count>=0),
          foreign_workspace_count bigint NOT NULL CHECK (foreign_workspace_count>=0),
          allowed_residue_classes jsonb NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('verified','incomplete','failed','quarantined')),
          verifier_identity_id text NOT NULL,
          verified_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, residual_verification_id),
          UNIQUE (organization_id, workspace_id, deletion_plan_id, plan_version, adapter_key),
          FOREIGN KEY (organization_id, workspace_id, deletion_plan_id, plan_version) REFERENCES workspace.deletion_plans(organization_id, workspace_id, deletion_plan_id, plan_version) ON DELETE RESTRICT,
          CHECK (outcome<>'verified' OR
            (foreign_workspace_count=0 AND
             (found_count=0 OR jsonb_array_length(allowed_residue_classes)>0)))
        );
        CREATE TABLE workspace.destruction_attestations (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          destruction_attestation_id uuid NOT NULL,
          attestation_version bigint NOT NULL CHECK (attestation_version>=1),
          lifecycle_revision bigint NOT NULL,
          deletion_plan_id uuid NOT NULL,
          plan_version bigint NOT NULL,
          plan_digest text NOT NULL,
          retention_profile_key text NOT NULL,
          retention_profile_version text NOT NULL,
          basis_registry_key text NOT NULL,
          basis_registry_version text NOT NULL,
          basis_code text NOT NULL,
          requester_identity_id text NOT NULL,
          confirmer_identity_id text NOT NULL,
          executor_identity_id text NOT NULL,
          verifier_identity_id text NOT NULL,
          adapter_registry_key text NOT NULL,
          adapter_registry_version text NOT NULL,
          receipt_count bigint NOT NULL CHECK (receipt_count>=0),
          scan_count bigint NOT NULL CHECK (scan_count>=0),
          aggregate_deleted_count bigint NOT NULL CHECK (aggregate_deleted_count>=0),
          aggregate_residue_count bigint NOT NULL CHECK (aggregate_residue_count>=0),
          residue_classes jsonb NOT NULL,
          platform_integrity_result text NOT NULL CHECK (platform_integrity_result IN ('unchanged','changed','not_checked')),
          assurance_class text NOT NULL CHECK (assurance_class IN ('development/disposable','production')),
          outcome text NOT NULL CHECK (outcome IN ('verified','incomplete','failed','quarantined')),
          verified_at timestamptz NOT NULL,
          contract_key text NOT NULL DEFAULT 'lifecycle.destruction-attestation',
          contract_version text NOT NULL,
          content_free_payload jsonb NOT NULL,
          PRIMARY KEY (organization_id, workspace_id, destruction_attestation_id, attestation_version),
          FOREIGN KEY (organization_id, workspace_id, deletion_plan_id, plan_version) REFERENCES workspace.deletion_plans(organization_id, workspace_id, deletion_plan_id, plan_version) ON DELETE RESTRICT,
          CHECK (requester_identity_id<>confirmer_identity_id AND requester_identity_id<>executor_identity_id AND requester_identity_id<>verifier_identity_id AND confirmer_identity_id<>executor_identity_id AND confirmer_identity_id<>verifier_identity_id AND executor_identity_id<>verifier_identity_id),
          CHECK (lower(contract_version)<>'latest'),
          CHECK (outcome<>'verified' OR (aggregate_residue_count=0 AND platform_integrity_result='unchanged')),
          CHECK (NOT (assurance_class='production' AND contract_version='0.1.0')),
          CHECK (NOT (content_free_payload ?| ARRAY['filename','file_name','project_text','source_fragment','source_hash','payload','prompt','response','embedding','graph_content','construction_object_name']))
        );
        """
    )
    immutable = (
        "lifecycle_transition_history",
        "freeze_manifests",
        "finalization_reports",
        "export_items",
        "archive_items",
        "archive_verifications",
        "archive_imports",
        "deletion_plans",
        "destructive_authorizations",
        "destructive_authorization_invalidations",
        "adapter_receipts",
        "recovery_checkpoints",
        "residual_verifications",
        "destruction_attestations",
    )
    for table in immutable:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )


def _create_guards_and_transition_function() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION workspace.enforce_material_write_fence()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace AS $$
        DECLARE current_state text;
        DECLARE target_organization_id uuid;
        DECLARE target_workspace_id uuid;
        BEGIN
          IF TG_OP='DELETE' THEN
            target_organization_id := OLD.organization_id;
            target_workspace_id := OLD.workspace_id;
          ELSE
            target_organization_id := NEW.organization_id;
            target_workspace_id := NEW.workspace_id;
          END IF;
          SELECT lifecycle_state INTO current_state FROM workspace.workspaces
          WHERE organization_id=target_organization_id AND workspace_id=target_workspace_id;
          IF current_state NOT IN ('PROVISIONING','ACTIVE')
             AND NOT pg_has_role(session_user,'asd_destruction_executor','member') THEN
            RAISE EXCEPTION 'workspace is write fenced in state %',current_state USING ERRCODE='55000';
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END $$;
        CREATE OR REPLACE FUNCTION workspace.guard_lifecycle_columns()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (OLD.lifecycle_state,OLD.lifecycle_version,OLD.workspace_revision,OLD.write_fenced,OLD.legal_hold_active)
             IS DISTINCT FROM
             (NEW.lifecycle_state,NEW.lifecycle_version,NEW.workspace_revision,NEW.write_fenced,NEW.legal_hold_active)
             AND (NOT pg_has_role(session_user,'asd_lifecycle_service','member')
                  OR NULLIF(current_setting('asd.lifecycle_operation_id',true),'') IS NULL) THEN
            RAISE EXCEPTION 'direct lifecycle mutation is forbidden' USING ERRCODE='42501';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_workspaces_lifecycle_guard BEFORE UPDATE ON workspace.workspaces
        FOR EACH ROW EXECUTE FUNCTION workspace.guard_lifecycle_columns();
        """
    )
    for table in MATERIAL_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_write_fence BEFORE INSERT OR UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION workspace.enforce_material_write_fence()"
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION workspace.transition_lifecycle(
          p_organization_id uuid,
          p_workspace_id uuid,
          p_expected_version bigint,
          p_target_state text,
          p_operation_key text,
          p_semantic_digest text,
          p_actor_identity_id text,
          p_service_identity_id text,
          p_authority_reference text,
          p_correlation_id uuid,
          p_causation_id uuid DEFAULT NULL
        ) RETURNS TABLE(outcome_state text,outcome_version bigint,duplicate boolean)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace, messaging AS $$
        DECLARE current_row workspace.workspaces%ROWTYPE;
        DECLARE prior_command workspace.lifecycle_commands%ROWTYPE;
        DECLARE allowed boolean;
        DECLARE next_revision bigint;
        DECLARE transition_id uuid;
        DECLARE event_id uuid;
        BEGIN
          IF p_organization_id<>NULLIF(current_setting('asd.organization_id',true),'')::uuid
             OR p_workspace_id<>NULLIF(current_setting('asd.workspace_id',true),'')::uuid THEN
            RAISE EXCEPTION 'lifecycle scope mismatch' USING ERRCODE='42501';
          END IF;
          PERFORM set_config('asd.lifecycle_operation_id',p_operation_key,true);
          SELECT * INTO prior_command FROM workspace.lifecycle_commands
          WHERE organization_id=p_organization_id AND workspace_id=p_workspace_id
            AND operation_key=p_operation_key;
          IF FOUND THEN
            IF prior_command.semantic_digest<>p_semantic_digest OR prior_command.target_state<>p_target_state THEN
              RAISE EXCEPTION 'idempotency conflict' USING ERRCODE='23505';
            END IF;
            RETURN QUERY SELECT prior_command.outcome_state,prior_command.outcome_version,true;
            RETURN;
          END IF;
          SELECT * INTO current_row FROM workspace.workspaces
          WHERE organization_id=p_organization_id AND workspace_id=p_workspace_id FOR UPDATE;
          IF NOT FOUND THEN RAISE EXCEPTION 'workspace not found' USING ERRCODE='P0002'; END IF;
          IF current_row.lifecycle_version<>p_expected_version THEN
            RAISE EXCEPTION 'lifecycle optimistic concurrency conflict' USING ERRCODE='40001';
          END IF;
          SELECT EXISTS (SELECT 1 FROM (VALUES
            ('PROVISIONING','ACTIVE'),('ACTIVE','FREEZING'),('FREEZING','FROZEN'),
            ('FREEZING','RECOVERY_REQUIRED'),('FROZEN','FINALIZING'),
            ('FINALIZING','FINALIZED'),('FINALIZING','RECOVERY_REQUIRED'),
            ('FINALIZED','EXPORTING'),('EXPORTING','EXPORTED'),
            ('EXPORTING','RECOVERY_REQUIRED'),('EXPORTED','ARCHIVING'),
            ('ARCHIVING','ARCHIVED'),('ARCHIVING','RECOVERY_REQUIRED'),
            ('ARCHIVED','CLOSED'),('CLOSED','REOPENING'),('REOPENING','ACTIVE'),
            ('REOPENING','RECOVERY_REQUIRED'),('CLOSED','RESET_PLANNING'),
            ('RESET_PLANNING','RESET_AUTHORIZED'),('RESET_PLANNING','CLOSED'),
            ('RESET_AUTHORIZED','PURGING'),('RESET_AUTHORIZED','RECOVERY_REQUIRED'),
            ('PURGING','VERIFYING_RESET'),('PURGING','RECOVERY_REQUIRED'),
            ('VERIFYING_RESET','RESET_VERIFIED'),('VERIFYING_RESET','RECOVERY_REQUIRED'),
            ('VERIFYING_RESET','QUARANTINED'),('RESET_VERIFIED','DESTROYING'),
            ('DESTROYING','DESTROYED'),('DESTROYING','RECOVERY_REQUIRED'),
            ('DESTROYING','QUARANTINED'),('RECOVERY_REQUIRED','PURGING'),
            ('RECOVERY_REQUIRED','DESTROYING'),('RECOVERY_REQUIRED','RECOVERY_REQUIRED'),
            ('RECOVERY_REQUIRED','QUARANTINED'),('QUARANTINED','RECOVERY_REQUIRED')
          ) AS transitions(old_state,new_state)
          WHERE old_state=current_row.lifecycle_state AND new_state=p_target_state) INTO allowed;
          IF NOT allowed THEN RAISE EXCEPTION 'invalid lifecycle transition' USING ERRCODE='55000'; END IF;
          IF current_row.legal_hold_active AND p_target_state IN ('RESET_AUTHORIZED','PURGING','DESTROYING','DESTROYED') THEN
            RAISE EXCEPTION 'legal hold blocks destructive transition' USING ERRCODE='55000';
          END IF;
          IF current_row.purge_started_at IS NOT NULL AND p_target_state='REOPENING' THEN
            RAISE EXCEPTION 'reopen after purge is forbidden' USING ERRCODE='55000';
          END IF;
          IF current_row.lifecycle_state='RECOVERY_REQUIRED'
             AND p_target_state IN ('PURGING','DESTROYING')
             AND NOT EXISTS (
               SELECT 1 FROM workspace.recovery_checkpoints c
               JOIN workspace.deletion_plans d ON
                 d.organization_id=c.organization_id AND d.workspace_id=c.workspace_id
                 AND d.plan_digest=c.plan_digest
               WHERE c.organization_id=p_organization_id AND c.workspace_id=p_workspace_id
                 AND c.status='required'
                 AND c.failed_operation=CASE WHEN p_target_state='PURGING' THEN 'reset' ELSE 'destroy' END
             ) THEN
            RAISE EXCEPTION 'immutable recovery checkpoint required' USING ERRCODE='55000';
          END IF;
          IF p_target_state='FROZEN' AND NOT EXISTS (
            SELECT 1 FROM workspace.freeze_manifests f
            WHERE f.organization_id=p_organization_id AND f.workspace_id=p_workspace_id
              AND f.lifecycle_version=p_expected_version AND f.result='verified'
          ) THEN RAISE EXCEPTION 'verified freeze manifest required' USING ERRCODE='55000'; END IF;
          IF p_target_state='FINALIZED' AND NOT EXISTS (
            SELECT 1 FROM workspace.finalization_reports f
            WHERE f.organization_id=p_organization_id AND f.workspace_id=p_workspace_id
              AND f.lifecycle_version=p_expected_version AND f.outcome='verified'
          ) THEN RAISE EXCEPTION 'verified finalization report required' USING ERRCODE='55000'; END IF;
          IF p_target_state='EXPORTED' AND NOT EXISTS (
            SELECT 1 FROM workspace.export_operations e
            WHERE e.organization_id=p_organization_id AND e.workspace_id=p_workspace_id
              AND e.workspace_revision=current_row.workspace_revision AND e.state='verified'
          ) THEN RAISE EXCEPTION 'verified export receipt required' USING ERRCODE='55000'; END IF;
          IF p_target_state='ARCHIVED' AND NOT EXISTS (
            SELECT 1 FROM workspace.archive_packages p JOIN workspace.archive_verifications v
              ON (v.organization_id,v.workspace_id,v.archive_package_id)=
                 (p.organization_id,p.workspace_id,p.archive_package_id)
            WHERE p.organization_id=p_organization_id AND p.workspace_id=p_workspace_id
              AND p.state='verified' AND v.outcome='verified'
          ) THEN RAISE EXCEPTION 'verified portable archive required' USING ERRCODE='55000'; END IF;
          IF p_target_state='RESET_AUTHORIZED' AND NOT EXISTS (
            SELECT 1 FROM workspace.destructive_authorizations a
            WHERE a.organization_id=p_organization_id AND a.workspace_id=p_workspace_id
              AND a.expires_at>CURRENT_TIMESTAMP
              AND NOT EXISTS (SELECT 1 FROM workspace.destructive_authorization_invalidations i
                WHERE (i.organization_id,i.workspace_id,i.authorization_id)=
                      (a.organization_id,a.workspace_id,a.authorization_id))
          ) THEN RAISE EXCEPTION 'valid dual authorization required' USING ERRCODE='55000'; END IF;
          IF p_target_state='PURGING' AND NOT EXISTS (
            SELECT 1 FROM workspace.destructive_authorizations a
            JOIN workspace.deletion_plans d ON
              (d.organization_id,d.workspace_id,d.deletion_plan_id,d.plan_version)=
              (a.organization_id,a.workspace_id,a.deletion_plan_id,a.plan_version)
            WHERE a.organization_id=p_organization_id AND a.workspace_id=p_workspace_id
              AND d.operation_kind='reset' AND d.plan_digest=a.plan_digest
              AND a.expires_at>CURRENT_TIMESTAMP
              AND NOT EXISTS (SELECT 1 FROM workspace.destructive_authorization_invalidations i
                WHERE (i.organization_id,i.workspace_id,i.authorization_id)=
                      (a.organization_id,a.workspace_id,a.authorization_id))
              AND d.lifecycle_version<=current_row.lifecycle_version
          ) THEN RAISE EXCEPTION 'fresh reset authorization required' USING ERRCODE='55000'; END IF;
          IF p_target_state='VERIFYING_RESET' AND NOT EXISTS (
            SELECT 1 FROM workspace.deletion_plans d
            WHERE d.organization_id=p_organization_id AND d.workspace_id=p_workspace_id
              AND d.operation_kind='reset'
              AND (SELECT count(*) FROM workspace.adapter_receipts r
                   WHERE (r.organization_id,r.workspace_id,r.deletion_plan_id,r.plan_version)=
                         (d.organization_id,d.workspace_id,d.deletion_plan_id,d.plan_version)
                     AND r.outcome IN ('deleted','already_absent'))
                  >= jsonb_array_length(d.deletion_items)
              AND NOT EXISTS (
                SELECT 1 FROM workspace.adapter_receipts bad
                WHERE (bad.organization_id,bad.workspace_id,bad.deletion_plan_id,bad.plan_version)=
                      (d.organization_id,d.workspace_id,d.deletion_plan_id,d.plan_version)
                  AND bad.outcome NOT IN ('deleted','already_absent'))
          ) THEN RAISE EXCEPTION 'complete adapter receipts required' USING ERRCODE='55000'; END IF;
          IF p_target_state='RESET_VERIFIED' AND NOT EXISTS (
            SELECT 1 FROM workspace.destruction_attestations a
            JOIN workspace.deletion_plans d ON
              (d.organization_id,d.workspace_id,d.deletion_plan_id,d.plan_version)=
              (a.organization_id,a.workspace_id,a.deletion_plan_id,a.plan_version)
            WHERE a.organization_id=p_organization_id AND a.workspace_id=p_workspace_id
              AND d.operation_kind='reset' AND a.outcome='verified'
              AND a.platform_integrity_result='unchanged'
          ) THEN RAISE EXCEPTION 'verified reset attestation required' USING ERRCODE='55000'; END IF;
          IF p_target_state='DESTROYING' AND NOT EXISTS (
            SELECT 1 FROM workspace.destructive_authorizations a
            JOIN workspace.deletion_plans d ON
              (d.organization_id,d.workspace_id,d.deletion_plan_id,d.plan_version)=
              (a.organization_id,a.workspace_id,a.deletion_plan_id,a.plan_version)
            WHERE a.organization_id=p_organization_id AND a.workspace_id=p_workspace_id
              AND d.operation_kind='destroy' AND a.expires_at>CURRENT_TIMESTAMP
              AND NOT EXISTS (SELECT 1 FROM workspace.destructive_authorization_invalidations i
                WHERE (i.organization_id,i.workspace_id,i.authorization_id)=
                      (a.organization_id,a.workspace_id,a.authorization_id))
          ) THEN RAISE EXCEPTION 'fresh destroy authorization required' USING ERRCODE='55000'; END IF;
          IF p_target_state='DESTROYED' AND NOT EXISTS (
            SELECT 1 FROM workspace.destruction_attestations a
            JOIN workspace.deletion_plans d ON
              (d.organization_id,d.workspace_id,d.deletion_plan_id,d.plan_version)=
              (a.organization_id,a.workspace_id,a.deletion_plan_id,a.plan_version)
            WHERE a.organization_id=p_organization_id AND a.workspace_id=p_workspace_id
              AND d.operation_kind='destroy' AND a.outcome='verified'
              AND a.platform_integrity_result='unchanged'
          ) THEN RAISE EXCEPTION 'verified destroy attestation required' USING ERRCODE='55000'; END IF;
          INSERT INTO workspace.lifecycle_commands VALUES
            (p_organization_id,p_workspace_id,p_operation_key,p_semantic_digest,p_target_state,
             p_expected_version,NULL,NULL,CURRENT_TIMESTAMP,NULL);
          next_revision := current_row.workspace_revision + CASE WHEN current_row.lifecycle_state='REOPENING' AND p_target_state='ACTIVE' THEN 1 ELSE 0 END;
          UPDATE workspace.workspaces SET lifecycle_state=p_target_state,
            lifecycle_version=lifecycle_version+1, workspace_revision=next_revision,
            revision=revision+1,
            write_fenced=(p_target_state NOT IN ('PROVISIONING','ACTIVE')),
            purge_started_at=CASE WHEN p_target_state='PURGING' THEN CURRENT_TIMESTAMP ELSE purge_started_at END,
            destroyed_at=CASE WHEN p_target_state='DESTROYED' THEN CURRENT_TIMESTAMP ELSE destroyed_at END
          WHERE organization_id=p_organization_id AND workspace_id=p_workspace_id;
          transition_id := gen_random_uuid(); event_id := gen_random_uuid();
          INSERT INTO workspace.lifecycle_transition_history
            (organization_id,workspace_id,lifecycle_version,transition_id,operation_key,
             prior_state,new_state,actor_identity_id,service_identity_id,authority_reference,
             correlation_id,causation_id)
          VALUES (p_organization_id,p_workspace_id,p_expected_version+1,transition_id,p_operation_key,
             current_row.lifecycle_state,p_target_state,p_actor_identity_id,p_service_identity_id,
             p_authority_reference,p_correlation_id,p_causation_id);
          IF current_row.lifecycle_state='REOPENING' AND p_target_state='ACTIVE' THEN
            INSERT INTO workspace.workspace_revisions
              (organization_id,workspace_id,revision,workspace_version_id,lifecycle_state,reason_code,
               retention_profile_key,retention_profile_version,policy_assignment_key,policy_assignment_version,
               rule_set_key,rule_set_version,contract_registry_version,created_by_identity_id,
               correlation_id,causation_id,recorded_at)
            VALUES (p_organization_id,p_workspace_id,next_revision,gen_random_uuid(),p_target_state,
               'workspace.reopened',current_row.retention_profile_key,current_row.retention_profile_version,
               current_row.policy_assignment_key,current_row.policy_assignment_version,current_row.rule_set_key,
               current_row.rule_set_version,current_row.contract_registry_version,
               COALESCE(p_actor_identity_id,p_service_identity_id),p_correlation_id,p_causation_id,CURRENT_TIMESTAMP);
          END IF;
          INSERT INTO messaging.workspace_outbox
            (organization_id,workspace_id,outbox_record_id,event_id,aggregate_id,aggregate_version,
             destination,state,attempt_count,contract_key,contract_version,schema_id,schema_version,
             payload,payload_digest,retention_class,correlation_id,causation_id,created_at)
          VALUES (p_organization_id,p_workspace_id,gen_random_uuid(),event_id,p_workspace_id,p_expected_version+1,
             'lifecycle','pending',0,'event.domain','0.1.0',
             'urn:asd-kontur:contracts:v0.1:schema:message','0.1.0',
             jsonb_build_object('event_type','workspace.lifecycle-transitioned','prior_state',current_row.lifecycle_state,
                                'new_state',p_target_state,'operation_key',p_operation_key),
             p_semantic_digest,'workspace.lifecycle',p_correlation_id,p_causation_id,CURRENT_TIMESTAMP);
          UPDATE workspace.lifecycle_commands SET outcome_state=p_target_state,
            outcome_version=p_expected_version+1,completed_at=CURRENT_TIMESTAMP
          WHERE organization_id=p_organization_id AND workspace_id=p_workspace_id
            AND operation_key=p_operation_key;
          RETURN QUERY SELECT p_target_state,p_expected_version+1,false;
        END $$;
        """
    )


def _apply_grants_and_rls() -> None:
    op.execute(
        "GRANT USAGE ON SCHEMA platform, workspace, messaging, audit TO asd_lifecycle_service, asd_lifecycle_verifier"
    )
    op.execute("GRANT USAGE ON SCHEMA workspace, messaging, audit TO asd_destruction_executor")
    op.execute(
        "GRANT SELECT ON platform.retention_profile_versions, platform.basis_registry_versions, "
        "platform.storage_adapter_registry_versions, platform.storage_adapter_registry_entries "
        "TO asd_lifecycle_service, asd_lifecycle_verifier"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON platform.retention_profile_versions, platform.basis_registry_versions, "
        "platform.storage_adapter_registry_versions, platform.storage_adapter_registry_entries TO asd_platform_curator"
    )
    op.execute("REVOKE UPDATE ON workspace.workspaces FROM asd_app")
    op.execute(
        "GRANT SELECT ON workspace.workspaces TO asd_lifecycle_service, asd_lifecycle_verifier"
    )
    op.execute(
        "GRANT UPDATE (legal_hold_active,revision) ON workspace.workspaces TO asd_lifecycle_service"
    )
    op.execute("GRANT SELECT, INSERT ON workspace.workspace_revisions TO asd_lifecycle_service")
    predicate = _scope_predicate()
    for table in ("workspaces", "workspace_revisions"):
        op.execute(
            f"CREATE POLICY {table}_lifecycle_scope_policy ON workspace.{table} FOR ALL "
            f"TO asd_lifecycle_service USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_verifier_scope_policy ON workspace.{table} FOR SELECT "
            f"TO asd_lifecycle_verifier USING ({predicate})"
        )
    for table in WORKSPACE_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON workspace.{table} TO asd_lifecycle_service")
        op.execute(f"GRANT SELECT ON workspace.{table} TO asd_lifecycle_verifier")
        _enable_workspace_rls(table)
    quarantine_states = (
        "'RESET_AUTHORIZED','PURGING','VERIFYING_RESET','RESET_VERIFIED',"
        "'DESTROYING','DESTROYED','QUARANTINED'"
    )
    for table in MATERIAL_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_scope_policy ON workspace.{table}")
        guarded = (
            f"{predicate} AND EXISTS (SELECT 1 FROM workspace.workspaces lifecycle_workspace "
            f"WHERE lifecycle_workspace.organization_id=workspace.{table}.organization_id "
            f"AND lifecycle_workspace.workspace_id=workspace.{table}.workspace_id "
            f"AND lifecycle_workspace.lifecycle_state NOT IN ({quarantine_states}))"
        )
        op.execute(
            f"CREATE POLICY {table}_scope_policy ON workspace.{table} FOR ALL TO asd_app "
            f"USING ({guarded}) WITH CHECK ({guarded})"
        )
    op.execute("GRANT UPDATE ON workspace.lifecycle_commands TO asd_lifecycle_service")
    op.execute("GRANT SELECT, INSERT ON messaging.workspace_outbox TO asd_lifecycle_service")
    op.execute(
        "CREATE POLICY workspace_outbox_lifecycle_scope_policy ON messaging.workspace_outbox "
        f"FOR ALL TO asd_lifecycle_service USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION workspace.transition_lifecycle(uuid,uuid,bigint,text,text,text,text,text,text,uuid,uuid) TO asd_lifecycle_service"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION workspace.transition_lifecycle(uuid,uuid,bigint,text,text,text,text,text,text,uuid,uuid) FROM PUBLIC, asd_app"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION workspace.transition_lifecycle(uuid,uuid,bigint,text,text,text,text,text,text,uuid,uuid) TO asd_lifecycle_service"
    )
    operational = (
        "object_links",
        "objects",
        "mode_executions",
        "source_locators",
        "evidence_links",
        "source_versions",
        "acquisition_attempts",
        "source_object_receipts",
        "source_artifacts",
        "rule_traces",
        "rule_evaluations",
        "rule_evidence",
        "rule_version_states",
        "rule_versions",
        "rules",
        "controlled_rule_set_upgrades",
        "promotion_decisions",
        "promotion_regression_results",
        "promotion_anonymization_results",
        "promotion_candidates",
    )
    for table in operational:
        op.execute(f"GRANT SELECT, DELETE ON workspace.{table} TO asd_destruction_executor")
    op.execute(
        "GRANT SELECT, DELETE ON messaging.workspace_outbox, messaging.workspace_inbox_receipts, messaging.workspace_idempotency TO asd_destruction_executor"
    )
    for table in ("workspace_outbox", "workspace_inbox_receipts", "workspace_idempotency"):
        qualified = f"messaging.{table}"
        predicate = _scope_predicate()
        op.execute(
            f"CREATE POLICY {table}_destruction_scope_policy ON {qualified} FOR ALL TO asd_destruction_executor USING ({predicate}) WITH CHECK ({predicate})"
        )
    for table in operational:
        predicate = _scope_predicate()
        op.execute(
            f"CREATE POLICY {table}_destruction_scope_policy ON workspace.{table} FOR ALL TO asd_destruction_executor USING ({predicate}) WITH CHECK ({predicate})"
        )


def _scope_predicate() -> str:
    return (
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid"
    )


def _enable_workspace_rls(table: str) -> None:
    predicate = _scope_predicate()
    op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_lifecycle_scope_policy ON workspace.{table} FOR ALL "
        f"TO asd_lifecycle_service USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(
        f"CREATE POLICY {table}_verifier_scope_policy ON workspace.{table} FOR SELECT "
        f"TO asd_lifecycle_verifier USING ({predicate})"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "destructive downgrade is forbidden; set ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1 "
            "only for a disposable development/test database"
        )
    for table in ("workspaces", "workspace_revisions"):
        op.execute(f"DROP POLICY IF EXISTS {table}_lifecycle_scope_policy ON workspace.{table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_verifier_scope_policy ON workspace.{table}")
    op.execute(
        "DROP POLICY IF EXISTS workspace_outbox_lifecycle_scope_policy "
        "ON messaging.workspace_outbox"
    )
    for table in (
        "workspace_outbox",
        "workspace_inbox_receipts",
        "workspace_idempotency",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_destruction_scope_policy ON messaging.{table}")
    for table in (
        "object_links",
        "objects",
        "mode_executions",
        "source_locators",
        "evidence_links",
        "source_versions",
        "acquisition_attempts",
        "source_object_receipts",
        "source_artifacts",
        "rule_traces",
        "rule_evaluations",
        "rule_evidence",
        "rule_version_states",
        "rule_versions",
        "rules",
        "controlled_rule_set_upgrades",
        "promotion_decisions",
        "promotion_regression_results",
        "promotion_anonymization_results",
        "promotion_candidates",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_destruction_scope_policy ON workspace.{table}")
    predicate = _scope_predicate()
    for table in MATERIAL_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_scope_policy ON workspace.{table}")
        op.execute(
            f"CREATE POLICY {table}_scope_policy ON workspace.{table} FOR ALL TO asd_app "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    op.execute(
        "DROP FUNCTION IF EXISTS workspace.transition_lifecycle(uuid,uuid,bigint,text,text,text,text,text,text,uuid,uuid)"
    )
    op.execute("DROP FUNCTION IF EXISTS workspace.guard_lifecycle_columns() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS workspace.enforce_material_write_fence() CASCADE")
    for table in reversed(WORKSPACE_TABLES):
        op.execute(f"DROP TABLE IF EXISTS workspace.{table} CASCADE")
    for table in (
        "storage_adapter_registry_entries",
        "storage_adapter_registry_versions",
        "basis_registry_versions",
        "retention_profile_versions",
    ):
        op.execute(f"DROP TABLE IF EXISTS platform.{table} CASCADE")
    op.execute(
        "ALTER TABLE workspace.workspace_revisions DROP CONSTRAINT IF EXISTS "
        "ck_workspace_revision_lifecycle_state"
    )
    op.execute(
        "ALTER TABLE workspace.mode_executions DROP CONSTRAINT IF EXISTS "
        "ck_mode_execution_g06_exact_versions"
    )
    op.execute(
        "ALTER TABLE workspace.mode_executions DROP COLUMN IF EXISTS output_contract_version"
    )
    op.execute("ALTER TABLE workspace.mode_executions DROP COLUMN IF EXISTS output_contract_key")
    op.execute(
        "ALTER TABLE workspace.mode_executions DROP COLUMN IF EXISTS authority_profile_version"
    )
    op.execute("ALTER TABLE workspace.mode_executions DROP COLUMN IF EXISTS authority_profile_key")
    op.execute(
        "ALTER TABLE workspace.mode_executions DROP COLUMN IF EXISTS process_definition_version"
    )
    op.execute("ALTER TABLE workspace.mode_executions DROP COLUMN IF EXISTS process_definition_key")
    op.execute("ALTER TABLE workspace.workspaces DROP COLUMN IF EXISTS destroyed_at")
    op.execute("ALTER TABLE workspace.workspaces DROP COLUMN IF EXISTS purge_started_at")
    op.execute("ALTER TABLE workspace.workspaces DROP COLUMN IF EXISTS legal_hold_active")
    op.execute("ALTER TABLE workspace.workspaces DROP COLUMN IF EXISTS write_fenced")
    op.execute("ALTER TABLE workspace.workspaces DROP COLUMN IF EXISTS workspace_revision")
    op.execute("ALTER TABLE workspace.workspaces DROP COLUMN IF EXISTS lifecycle_version")
    op.execute("GRANT UPDATE ON workspace.workspaces TO asd_app")
    # Cluster roles remain; production rollback is a forward repair or verified restore.
