"""Add the Product Application Spine persistence boundary.

Revision ID: 0018_product_spine
Revises: 0017_unified_harness
Create Date: 2026-08-26
"""

from __future__ import annotations

from alembic import op

revision = "0018_product_spine"
down_revision = "0017_unified_harness"
branch_labels = None
depends_on = None


WORKSPACE_TABLES = (
    "intake_manifests",
    "intake_manifest_items",
    "document_records",
    "document_versions",
    "document_processing_states",
    "document_version_activation_decisions",
    "document_pages",
    "durable_jobs",
    "durable_job_attempts",
    "durable_job_dependencies",
    "job_progress_events",
    "job_leases",
    "job_cancellations",
    "job_terminal_receipts",
    "reset_confirmation_challenges",
)


def upgrade() -> None:
    _create_roles_and_schema()
    _create_authentication_relations()
    _create_document_relations()
    _create_job_relations()
    _create_reset_relations()
    _create_authorization_functions()
    _create_worker_claim_function()
    _apply_guards_grants_and_rls()


def _create_roles_and_schema() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_document_worker') THEN "
        "CREATE ROLE asd_document_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; "
        "END IF; END $$"
    )
    op.execute("CREATE SCHEMA application")


def _create_authentication_relations() -> None:
    op.execute(
        """
        CREATE TABLE application.owner_identities (
          owner_identity_id text PRIMARY KEY,
          normalized_username text NOT NULL UNIQUE,
          display_name text NOT NULL,
          password_hash text NOT NULL,
          status text NOT NULL CHECK (status IN ('active','locked','revoked')),
          auth_version bigint NOT NULL CHECK (auth_version >= 1),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE application.sessions (
          session_id_digest text PRIMARY KEY CHECK (session_id_digest ~ '^sha256:[a-f0-9]{64}$'),
          owner_identity_id text NOT NULL REFERENCES application.owner_identities(owner_identity_id) ON DELETE RESTRICT,
          csrf_secret_digest text NOT NULL CHECK (csrf_secret_digest ~ '^sha256:[a-f0-9]{64}$'),
          profile text NOT NULL CHECK (profile IN ('development_loopback','protected_remote')),
          issued_at timestamptz NOT NULL,
          last_seen_at timestamptz NOT NULL,
          inactivity_expires_at timestamptz NOT NULL,
          absolute_expires_at timestamptz NOT NULL,
          revoked_at timestamptz,
          rotation_parent_digest text CHECK (rotation_parent_digest IS NULL OR rotation_parent_digest ~ '^sha256:[a-f0-9]{64}$'),
          client_fingerprint_digest text NOT NULL CHECK (client_fingerprint_digest ~ '^sha256:[a-f0-9]{64}$'),
          CHECK (inactivity_expires_at > issued_at),
          CHECK (absolute_expires_at > issued_at)
        );
        CREATE INDEX ix_sessions_owner_active
          ON application.sessions(owner_identity_id, absolute_expires_at)
          WHERE revoked_at IS NULL;
        CREATE TABLE application.owner_organization_grants (
          owner_identity_id text NOT NULL REFERENCES application.owner_identities(owner_identity_id) ON DELETE RESTRICT,
          organization_id uuid NOT NULL REFERENCES organization.organizations(organization_id) ON DELETE RESTRICT,
          capability_set text[] NOT NULL,
          grant_version bigint NOT NULL CHECK (grant_version = 1),
          granted_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (owner_identity_id,organization_id)
        );
        CREATE TABLE application.login_attempts (
          login_attempt_id uuid PRIMARY KEY,
          username_digest text NOT NULL CHECK (username_digest ~ '^sha256:[a-f0-9]{64}$'),
          client_fingerprint_digest text NOT NULL CHECK (client_fingerprint_digest ~ '^sha256:[a-f0-9]{64}$'),
          outcome text NOT NULL CHECK (outcome IN ('accepted','invalid_credentials','rate_limited','account_blocked')),
          occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          correlation_id uuid NOT NULL
        );
        CREATE INDEX ix_login_attempt_rate_limit
          ON application.login_attempts(username_digest, client_fingerprint_digest, occurred_at DESC);
        CREATE TABLE application.auth_audit_events (
          auth_audit_event_id uuid PRIMARY KEY,
          owner_identity_id text,
          event_type text NOT NULL,
          outcome text NOT NULL,
          correlation_id uuid NOT NULL,
          safe_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          event_digest text NOT NULL UNIQUE CHECK (event_digest ~ '^sha256:[a-f0-9]{64}$'),
          occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE application.workspace_reset_terminal_receipts (
          reset_receipt_id uuid PRIMARY KEY,
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          target_lifecycle_version bigint NOT NULL,
          archive_package_digest text NOT NULL CHECK (archive_package_digest ~ '^sha256:[a-f0-9]{64}$'),
          platform_fingerprint_before text NOT NULL CHECK (platform_fingerprint_before ~ '^sha256:[a-f0-9]{64}$'),
          platform_fingerprint_after text NOT NULL CHECK (platform_fingerprint_after ~ '^sha256:[a-f0-9]{64}$'),
          deleted_relation_row_count bigint NOT NULL CHECK (deleted_relation_row_count >= 0),
          deleted_object_count bigint NOT NULL CHECK (deleted_object_count >= 0),
          assurance_profile text NOT NULL CHECK (assurance_profile='development_single_owner_confirmation'),
          outcome text NOT NULL CHECK (outcome IN ('verified','reconciliation_required')),
          receipt_digest text NOT NULL UNIQUE CHECK (receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          correlation_id uuid NOT NULL,
          completed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _create_document_relations() -> None:
    op.execute(
        """
        CREATE TABLE workspace.intake_manifests (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          intake_manifest_id uuid NOT NULL,
          manifest_version bigint NOT NULL CHECK (manifest_version = 1),
          manifest_digest text NOT NULL CHECK (manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          declared_file_count bigint NOT NULL CHECK (declared_file_count >= 1),
          declared_total_bytes bigint NOT NULL CHECK (declared_total_bytes >= 0),
          accepted_file_count bigint NOT NULL CHECK (accepted_file_count >= 0),
          rejected_file_count bigint NOT NULL CHECK (rejected_file_count >= 0),
          status text NOT NULL CHECK (status IN ('admitted','partial','rejected')),
          created_by_identity_id text NOT NULL,
          correlation_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id, workspace_id, intake_manifest_id),
          UNIQUE (organization_id, workspace_id, manifest_digest),
          FOREIGN KEY (organization_id,workspace_id)
            REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.intake_manifest_items (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          intake_manifest_id uuid NOT NULL,
          item_ordinal bigint NOT NULL CHECK (item_ordinal >= 1),
          safe_display_name text NOT NULL,
          sanitized_relative_path text NOT NULL,
          client_media_type text,
          client_size_bytes bigint CHECK (client_size_bytes IS NULL OR client_size_bytes >= 0),
          client_digest text,
          outcome text NOT NULL CHECK (outcome IN ('accepted','rejected','duplicate')),
          reason_code text,
          document_id uuid,
          PRIMARY KEY (organization_id,workspace_id,intake_manifest_id,item_ordinal),
          FOREIGN KEY (organization_id,workspace_id,intake_manifest_id)
            REFERENCES workspace.intake_manifests(organization_id,workspace_id,intake_manifest_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.document_records (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          document_id uuid NOT NULL,
          semantic_key_digest text NOT NULL CHECK (semantic_key_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_by_identity_id text NOT NULL,
          correlation_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,document_id),
          UNIQUE (organization_id,workspace_id,semantic_key_digest),
          FOREIGN KEY (organization_id,workspace_id)
            REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.document_versions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          document_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          source_artifact_id uuid NOT NULL,
          source_version_id uuid NOT NULL,
          object_id uuid NOT NULL,
          object_version bigint NOT NULL DEFAULT 1,
          safe_display_name text NOT NULL,
          sanitized_relative_path text NOT NULL,
          media_type text NOT NULL,
          size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          object_key text NOT NULL,
          provenance jsonb NOT NULL,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,document_id,version),
          UNIQUE (organization_id,workspace_id,document_id,content_digest),
          FOREIGN KEY (organization_id,workspace_id,document_id)
            REFERENCES workspace.document_records(organization_id,workspace_id,document_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,object_id,object_version)
            REFERENCES workspace.objects(organization_id,workspace_id,object_id,object_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_artifact_id)
            REFERENCES workspace.source_artifacts(organization_id,workspace_id,source_artifact_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id)
            REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.document_processing_states (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          document_id uuid NOT NULL,
          document_version bigint NOT NULL,
          state_sequence bigint NOT NULL CHECK (state_sequence >= 1),
          admission_status text NOT NULL CHECK (admission_status IN ('pending','accepted','rejected','reconciliation_required')),
          extraction_status text NOT NULL CHECK (extraction_status IN ('not_started','running','complete','partial_with_capability_gap','failed')),
          page_count bigint CHECK (page_count IS NULL OR page_count >= 0),
          capability_gaps text[] NOT NULL DEFAULT '{}',
          caused_by_job_id uuid,
          state_fingerprint text NOT NULL UNIQUE CHECK (state_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,document_id,document_version,state_sequence),
          FOREIGN KEY (organization_id,workspace_id,document_id,document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.document_version_activation_decisions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          activation_decision_id uuid NOT NULL,
          document_id uuid NOT NULL,
          decision_version bigint NOT NULL CHECK (decision_version >= 1),
          selected_document_version bigint NOT NULL,
          supersedes_decision_version bigint,
          reason_code text NOT NULL,
          decision_digest text NOT NULL UNIQUE CHECK (decision_digest ~ '^sha256:[a-f0-9]{64}$'),
          decided_by_identity_id text NOT NULL,
          decided_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,activation_decision_id,decision_version),
          FOREIGN KEY (organization_id,workspace_id,document_id,selected_document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,activation_decision_id,supersedes_decision_version)
            REFERENCES workspace.document_version_activation_decisions(organization_id,workspace_id,activation_decision_id,decision_version) ON DELETE RESTRICT
        );
        CREATE UNIQUE INDEX uq_document_one_initial_activation
          ON workspace.document_version_activation_decisions(organization_id,workspace_id,document_id)
          WHERE supersedes_decision_version IS NULL;
        CREATE INDEX ix_document_versions_registry_order
          ON workspace.document_versions(
            organization_id,workspace_id,recorded_at,document_id
          ) INCLUDE (version,media_type,safe_display_name);
        CREATE INDEX ix_document_activation_current_lookup
          ON workspace.document_version_activation_decisions(
            organization_id,workspace_id,document_id,decision_version DESC
          ) INCLUDE (selected_document_version);
        CREATE INDEX ix_document_processing_state_current_lookup
          ON workspace.document_processing_states(
            organization_id,workspace_id,document_id,document_version,state_sequence DESC
          ) INCLUDE (admission_status,extraction_status,page_count,capability_gaps);
        CREATE TABLE workspace.document_pages (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          document_id uuid NOT NULL,
          document_version bigint NOT NULL,
          page_number bigint NOT NULL CHECK (page_number >= 1),
          width_points numeric(14,6) NOT NULL CHECK (width_points > 0),
          height_points numeric(14,6) NOT NULL CHECK (height_points > 0),
          rotation_degrees integer NOT NULL CHECK (rotation_degrees IN (0,90,180,270)),
          crop_box jsonb NOT NULL,
          native_text_digest text CHECK (native_text_digest IS NULL OR native_text_digest ~ '^sha256:[a-f0-9]{64}$'),
          native_text_object_key text,
          extraction_method text NOT NULL CHECK (extraction_method IN ('native_pdf','none')),
          evidence_locator_id uuid,
          page_fingerprint text NOT NULL CHECK (page_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,document_id,document_version,page_number),
          UNIQUE (organization_id,workspace_id,page_fingerprint),
          FOREIGN KEY (organization_id,workspace_id,document_id,document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_locator_id)
            REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          CHECK ((native_text_digest IS NULL) = (native_text_object_key IS NULL))
        );
        """
    )


def _create_job_relations() -> None:
    op.execute(
        """
        CREATE TABLE workspace.durable_jobs (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          job_id uuid NOT NULL,
          subject_document_id uuid,
          job_kind text NOT NULL CHECK (job_kind IN ('DOCUMENT_ADMISSION','DOCUMENT_HASH','PDF_INVENTORY','NATIVE_TEXT_EXTRACTION','EVIDENCE_INDEX_UPDATE','WORKSPACE_RESET_RECONCILIATION')),
          input_manifest jsonb NOT NULL,
          input_digest text NOT NULL CHECK (input_digest ~ '^sha256:[a-f0-9]{64}$'),
          idempotency_key text NOT NULL,
          state text NOT NULL CHECK (state IN ('queued','leased','running','succeeded','failed','cancelled','reconciliation_required')),
          priority integer NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          eligible_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          started_at timestamptz,
          heartbeat_at timestamptz,
          completed_at timestamptz,
          attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
          retry_policy_version text NOT NULL CHECK (lower(retry_policy_version) <> 'latest'),
          lease_owner text,
          lease_generation bigint NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
          lease_expires_at timestamptz,
          cancellation_state text NOT NULL DEFAULT 'none' CHECK (cancellation_state IN ('none','requested','acknowledged')),
          typed_failure_code text,
          result_receipt_id uuid,
          provenance jsonb NOT NULL,
          correlation_id uuid NOT NULL,
          causation_id uuid,
          created_by_identity_id text NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,job_id),
          UNIQUE (organization_id,workspace_id,job_kind,idempotency_key),
          FOREIGN KEY (organization_id,workspace_id)
            REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,subject_document_id)
            REFERENCES workspace.document_records(organization_id,workspace_id,document_id) ON DELETE RESTRICT,
          CHECK (state NOT IN ('succeeded','failed','cancelled','reconciliation_required') OR completed_at IS NOT NULL),
          CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL))
        );
        CREATE INDEX ix_durable_job_claim
          ON workspace.durable_jobs(state,eligible_at,priority DESC,created_at,job_id);
        CREATE INDEX ix_durable_job_document_history
          ON workspace.durable_jobs(organization_id,workspace_id,subject_document_id,created_at,job_id);
        CREATE TABLE workspace.durable_job_attempts (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          job_id uuid NOT NULL,
          attempt_number integer NOT NULL CHECK (attempt_number >= 1),
          attempt_id uuid NOT NULL,
          worker_identity text NOT NULL,
          lease_generation bigint NOT NULL CHECK (lease_generation >= 1),
          execution_profile_version text NOT NULL CHECK (lower(execution_profile_version) <> 'latest'),
          input_digest text NOT NULL CHECK (input_digest ~ '^sha256:[a-f0-9]{64}$'),
          started_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,job_id,attempt_number),
          UNIQUE (attempt_id),
          FOREIGN KEY (organization_id,workspace_id,job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.durable_job_dependencies (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          job_id uuid NOT NULL,
          depends_on_job_id uuid NOT NULL,
          dependency_kind text NOT NULL CHECK (dependency_kind IN ('success_required','terminal_required')),
          PRIMARY KEY (organization_id,workspace_id,job_id,depends_on_job_id),
          FOREIGN KEY (organization_id,workspace_id,job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,depends_on_job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id) ON DELETE RESTRICT,
          CHECK (job_id <> depends_on_job_id)
        );
        CREATE TABLE workspace.job_progress_events (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          job_id uuid NOT NULL,
          progress_event_id bigint GENERATED ALWAYS AS IDENTITY,
          event_sequence bigint NOT NULL CHECK (event_sequence >= 1),
          event_type text NOT NULL,
          progress_current bigint CHECK (progress_current IS NULL OR progress_current >= 0),
          progress_total bigint CHECK (progress_total IS NULL OR progress_total >= 0),
          safe_message_code text NOT NULL,
          terminal boolean NOT NULL DEFAULT false,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          retention_until timestamptz NOT NULL,
          event_digest text NOT NULL UNIQUE CHECK (event_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,job_id,event_sequence),
          UNIQUE (progress_event_id),
          FOREIGN KEY (organization_id,workspace_id,job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id) ON DELETE RESTRICT
        );
        CREATE INDEX ix_job_progress_resume
          ON workspace.job_progress_events(organization_id,workspace_id,progress_event_id);
        CREATE TABLE workspace.job_leases (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          job_id uuid NOT NULL,
          lease_generation bigint NOT NULL CHECK (lease_generation >= 1),
          lease_id uuid NOT NULL UNIQUE,
          worker_identity text NOT NULL,
          acquired_at timestamptz NOT NULL,
          initial_expires_at timestamptz NOT NULL,
          lease_digest text NOT NULL UNIQUE CHECK (lease_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,job_id,lease_generation),
          FOREIGN KEY (organization_id,workspace_id,job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.job_cancellations (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          cancellation_id uuid NOT NULL,
          job_id uuid NOT NULL,
          requested_by_identity_id text NOT NULL,
          reason_code text NOT NULL,
          requested_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          cancellation_digest text NOT NULL UNIQUE CHECK (cancellation_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,cancellation_id),
          FOREIGN KEY (organization_id,workspace_id,job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.job_terminal_receipts (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          terminal_receipt_id uuid NOT NULL,
          job_id uuid NOT NULL,
          lease_generation bigint NOT NULL CHECK (lease_generation >= 0),
          terminal_state text NOT NULL CHECK (terminal_state IN ('succeeded','failed','cancelled','reconciliation_required')),
          typed_outcome_code text NOT NULL,
          result_manifest jsonb NOT NULL,
          result_digest text NOT NULL CHECK (result_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,terminal_receipt_id),
          UNIQUE (organization_id,workspace_id,job_id),
          UNIQUE (result_digest),
          FOREIGN KEY (organization_id,workspace_id,job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id) ON DELETE RESTRICT
        );
        """
    )


def _create_reset_relations() -> None:
    op.execute(
        """
        CREATE TABLE workspace.reset_confirmation_challenges (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          challenge_id uuid NOT NULL,
          deletion_plan_id uuid,
          deletion_plan_version bigint CHECK (deletion_plan_version IS NULL OR deletion_plan_version >= 1),
          target_lifecycle_version bigint NOT NULL CHECK (target_lifecycle_version >= 1),
          archive_package_digest text NOT NULL CHECK (archive_package_digest ~ '^sha256:[a-f0-9]{64}$'),
          challenge_digest text NOT NULL UNIQUE CHECK (challenge_digest ~ '^sha256:[a-f0-9]{64}$'),
          issued_to_identity_id text NOT NULL,
          expires_at timestamptz NOT NULL,
          consumed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,challenge_id),
          FOREIGN KEY (organization_id,workspace_id)
            REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,deletion_plan_id,deletion_plan_version)
            REFERENCES workspace.deletion_plans(organization_id,workspace_id,deletion_plan_id,plan_version) ON DELETE RESTRICT,
          CHECK ((deletion_plan_id IS NULL) = (deletion_plan_version IS NULL))
        );
        """
    )


def _create_authorization_functions() -> None:
    op.execute(
        """
        CREATE FUNCTION application.resolve_workspace_scope(
          p_owner_identity_id text, p_workspace_id uuid
        ) RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, application, workspace
        AS $$
          SELECT w.organization_id
          FROM workspace.workspaces w
          JOIN application.owner_organization_grants g
            ON g.organization_id=w.organization_id
          WHERE g.owner_identity_id=p_owner_identity_id
            AND w.workspace_id=p_workspace_id
            AND w.lifecycle_state <> 'DESTROYED'
        $$;
        CREATE FUNCTION application.list_authorized_workspaces(p_owner_identity_id text)
        RETURNS TABLE (
          organization_id uuid, workspace_id uuid, construction_object_id uuid,
          display_name text, lifecycle_state text, lifecycle_version bigint,
          workspace_revision bigint, write_fenced boolean, created_at timestamptz
        )
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, application, organization, workspace
        AS $$
          SELECT w.organization_id,w.workspace_id,w.construction_object_id,c.display_name,
                 w.lifecycle_state,w.lifecycle_version,w.workspace_revision,w.write_fenced,w.created_at
          FROM workspace.workspaces w
          JOIN application.owner_organization_grants g ON g.organization_id=w.organization_id
          JOIN organization.construction_objects c
            ON c.organization_id=w.organization_id AND c.construction_object_id=w.construction_object_id
          WHERE g.owner_identity_id=p_owner_identity_id
            AND w.lifecycle_state <> 'DESTROYED'
          ORDER BY w.created_at,w.workspace_id
        $$;
        CREATE FUNCTION application.get_platform_knowledge_status()
        RETURNS jsonb
        LANGUAGE plpgsql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, application, platform, projection
        AS $$
        DECLARE active_release record;
        DECLARE practice_backup record;
        DECLARE ntd_backup record;
        DECLARE guide_count bigint;
        DECLARE edition_count bigint;
        DECLARE normative_count bigint;
        DECLARE verified_editions bigint;
        DECLARE verified_provisions bigint;
        DECLARE active_rules bigint;
        DECLARE active_gaps bigint := 0;
        DECLARE conflicts bigint := 0;
        DECLARE quarantined bigint;
        DECLARE ntd_open_gaps bigint;
        BEGIN
          SELECT count(*) INTO guide_count FROM platform.practice_guides;
          SELECT count(*) INTO edition_count FROM platform.practice_guide_editions;
          SELECT count(*) INTO normative_count FROM platform.normative_documents;
          SELECT count(DISTINCT e.normative_edition_id) INTO verified_editions
            FROM platform.normative_editions e
            JOIN LATERAL (
              SELECT status FROM platform.normative_edition_states s
              WHERE s.normative_edition_id=e.normative_edition_id
              ORDER BY s.state_sequence DESC LIMIT 1
            ) state ON true WHERE state.status IN ('active','verified','effective');
          SELECT count(*) INTO verified_provisions
            FROM platform.normative_provision_versions WHERE verification_status='verified';
          SELECT count(DISTINCT v.rule_version_id) INTO active_rules
            FROM platform.rule_versions v
            JOIN LATERAL (
              SELECT status FROM platform.rule_version_states s
              WHERE s.rule_version_id=v.rule_version_id ORDER BY s.state_sequence DESC LIMIT 1
            ) state ON true WHERE state.status='active';
          SELECT count(*) INTO ntd_open_gaps FROM platform.ntd_gaps g
            WHERE NOT EXISTS (
              SELECT 1 FROM platform.ntd_gaps newer
              WHERE newer.normative_gap_id=g.normative_gap_id AND newer.version>g.version
            ) AND g.status='open';
          SELECT count(DISTINCT (v.guidance_candidate_id,v.candidate_version)) INTO quarantined
            FROM platform.practice_guide_validation_results v WHERE v.blocking=true
              AND NOT EXISTS (
                SELECT 1 FROM platform.practice_guidance_units u
                WHERE u.guidance_candidate_id=v.guidance_candidate_id
                  AND u.candidate_version=v.candidate_version
              );
          SELECT r.*,m.source_guidance_count,m.intelligence_unit_count,m.playbook_count,
                 m.coverage_manifest_id INTO active_release
            FROM platform.practice_intelligence_releases r
            JOIN platform.practice_intelligence_construction_manifests m
              ON m.construction_manifest_id=r.construction_manifest_id
            JOIN platform.practice_guide_edition_activation_decisions d
              ON d.activation_decision_id=r.activation_decision_id
             AND d.version=r.activation_decision_version
             AND d.selected_edition_id=r.practice_guide_edition_id
            WHERE NOT EXISTS (
              SELECT 1 FROM platform.practice_guide_edition_activation_decisions newer
              WHERE newer.practice_guide_id=d.practice_guide_id AND newer.version>d.version
            ) ORDER BY r.published_at DESC,r.release_id,r.version DESC LIMIT 1;
          IF FOUND THEN
            SELECT count(*) INTO active_gaps FROM platform.practice_guidance_gaps
              WHERE coverage_manifest_id=active_release.coverage_manifest_id;
            SELECT count(*) INTO conflicts FROM platform.practice_guidance_conflicts c
              JOIN platform.practice_guidance_units u
                ON u.guidance_unit_id=c.guidance_unit_id AND u.version=c.guidance_unit_version
              WHERE u.practice_guide_edition_id=active_release.practice_guide_edition_id
                AND c.state='open';
          END IF;
          SELECT recorded_at,canonical_semantic_fingerprint INTO practice_backup
            FROM platform.practice_memory_backup_manifests WHERE integrity_status='verified'
            ORDER BY recorded_at DESC LIMIT 1;
          SELECT created_at,canonical_semantic_fingerprint INTO ntd_backup
            FROM platform.ntd_backup_manifests ORDER BY created_at DESC LIMIT 1;
          RETURN jsonb_build_object(
            'practice_guide_count',guide_count,
            'practice_edition_count',edition_count,
            'active_practice_release_count',CASE WHEN active_release.release_id IS NULL THEN 0 ELSE 1 END,
            'source_guidance_count',COALESCE(active_release.source_guidance_count,0),
            'active_intelligence_count',COALESCE(active_release.intelligence_unit_count,0),
            'active_playbook_count',COALESCE(active_release.playbook_count,0),
            'active_gap_count',active_gaps,
            'conflict_count',conflicts,
            'quarantine_count',quarantined,
            'normative_identity_count',normative_count,
            'verified_normative_edition_count',verified_editions,
            'verified_normative_provision_count',verified_provisions,
            'rule_version_count',active_rules,
            'projection_states',jsonb_build_object(
              'practice_lexical',CASE WHEN to_regclass('projection.practice_intelligence_lexical_versions')
                IS NULL THEN 'rebuild_required' ELSE 'available' END,
              'ntd_exact',CASE WHEN to_regclass('projection.ntd_lexical_versions')
                IS NULL THEN 'rebuild_required' ELSE 'available' END,
              'model_broker','capability_unavailable_in_spine_v0.1'
            ),
            'last_verified_backup_at',CASE
              WHEN practice_backup.recorded_at IS NULL THEN ntd_backup.created_at
              WHEN ntd_backup.created_at IS NULL THEN practice_backup.recorded_at
              ELSE greatest(practice_backup.recorded_at,ntd_backup.created_at) END,
            'semantic_fingerprints',jsonb_build_object(
              'active_practice_release',active_release.canonical_semantic_fingerprint,
              'practice_backup',practice_backup.canonical_semantic_fingerprint,
              'ntd_backup',ntd_backup.canonical_semantic_fingerprint
            ),
            'memory_data_defect',true,
            'knowledge_ready',false,
            'blockers',to_jsonb(array_remove(ARRAY[
              'MEMORY_DATA_DEFECT',
              CASE WHEN active_release.release_id IS NULL THEN 'PRACTICE_RELEASE_UNAVAILABLE' END,
              CASE WHEN verified_editions=0 THEN 'VERIFIED_NTD_UNAVAILABLE' END,
              CASE WHEN active_rules=0 THEN 'ACTIVE_RULE_VERSION_UNAVAILABLE' END,
              CASE WHEN ntd_open_gaps>0 THEN 'NTD_GAPS_OPEN' END
            ],NULL))
          );
        END $$;
        REVOKE ALL ON FUNCTION application.resolve_workspace_scope(text,uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION application.list_authorized_workspaces(text) FROM PUBLIC;
        REVOKE ALL ON FUNCTION application.get_platform_knowledge_status() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION application.resolve_workspace_scope(text,uuid) TO asd_app;
        GRANT EXECUTE ON FUNCTION application.list_authorized_workspaces(text) TO asd_app;
        GRANT EXECUTE ON FUNCTION application.get_platform_knowledge_status() TO asd_app;
        """
    )


def _create_worker_claim_function() -> None:
    op.execute(
        """
        CREATE FUNCTION workspace.claim_next_durable_job(p_worker_identity text, p_lease_seconds integer)
        RETURNS TABLE (
          organization_id uuid, workspace_id uuid, job_id uuid, job_kind text,
          input_manifest jsonb, input_digest text, attempt_number integer,
          lease_generation bigint, cancellation_state text
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        DECLARE
          claimed workspace.durable_jobs%ROWTYPE;
          next_generation bigint;
          next_attempt integer;
          next_sequence bigint;
          lease_uuid uuid;
          now_at timestamptz := clock_timestamp();
          lease_until timestamptz;
          lease_fingerprint text;
          event_fingerprint text;
        BEGIN
          IF p_worker_identity IS NULL OR length(p_worker_identity) < 3 OR p_lease_seconds < 5 OR p_lease_seconds > 3600 THEN
            RAISE EXCEPTION 'invalid durable job lease request' USING ERRCODE='22023';
          END IF;
          UPDATE workspace.durable_jobs j
             SET state='queued', lease_owner=NULL, lease_expires_at=NULL,
                 typed_failure_code='stale_lease_recovered'
           WHERE j.state IN ('leased','running')
             AND j.lease_expires_at < now_at
             AND j.attempt_count < j.max_attempts
             AND j.cancellation_state='none';

          SELECT j.* INTO claimed
            FROM workspace.durable_jobs j
           WHERE j.state='queued' AND j.eligible_at <= now_at
             AND j.cancellation_state='none'
             AND j.attempt_count < j.max_attempts
             AND NOT EXISTS (
               SELECT 1 FROM workspace.durable_job_dependencies d
               JOIN workspace.durable_jobs prerequisite
                 ON prerequisite.organization_id=d.organization_id
                AND prerequisite.workspace_id=d.workspace_id
                AND prerequisite.job_id=d.depends_on_job_id
               WHERE d.organization_id=j.organization_id AND d.workspace_id=j.workspace_id
                 AND d.job_id=j.job_id
                 AND ((d.dependency_kind='success_required' AND prerequisite.state<>'succeeded')
                   OR (d.dependency_kind='terminal_required' AND prerequisite.state NOT IN ('succeeded','failed','cancelled','reconciliation_required')))
             )
           ORDER BY j.priority DESC, j.created_at, j.job_id
           FOR UPDATE OF j SKIP LOCKED LIMIT 1;
          IF NOT FOUND THEN RETURN; END IF;

          next_generation := claimed.lease_generation + 1;
          next_attempt := claimed.attempt_count + 1;
          next_sequence := COALESCE((SELECT max(e.event_sequence)+1
            FROM workspace.job_progress_events e
            WHERE e.organization_id=claimed.organization_id AND e.workspace_id=claimed.workspace_id
              AND e.job_id=claimed.job_id),1);
          lease_uuid := gen_random_uuid();
          lease_until := now_at + make_interval(secs => p_lease_seconds);
          lease_fingerprint := 'sha256:' || encode(public.digest(
            claimed.job_id::text || '-' || next_generation::text || '-' || p_worker_identity || '-' || now_at::text,
            'sha256'),'hex');
          event_fingerprint := 'sha256:' || encode(public.digest(
            claimed.job_id::text || '-' || next_sequence::text || '-job.leased-' || next_generation::text,
            'sha256'),'hex');

          UPDATE workspace.durable_jobs j SET
            state='leased', attempt_count=next_attempt, lease_owner=p_worker_identity,
            lease_generation=next_generation, lease_expires_at=lease_until,
            heartbeat_at=now_at, started_at=COALESCE(j.started_at,now_at)
          WHERE j.organization_id=claimed.organization_id AND j.workspace_id=claimed.workspace_id
            AND j.job_id=claimed.job_id;
          INSERT INTO workspace.durable_job_attempts VALUES (
            claimed.organization_id,claimed.workspace_id,claimed.job_id,next_attempt,
            gen_random_uuid(),p_worker_identity,next_generation,'spine-worker-v0.1',
            claimed.input_digest,now_at);
          INSERT INTO workspace.job_leases VALUES (
            claimed.organization_id,claimed.workspace_id,claimed.job_id,next_generation,
            lease_uuid,p_worker_identity,now_at,lease_until,lease_fingerprint);
          INSERT INTO workspace.job_progress_events
            (organization_id,workspace_id,job_id,event_sequence,event_type,progress_current,
             progress_total,safe_message_code,terminal,recorded_at,retention_until,event_digest)
          VALUES (claimed.organization_id,claimed.workspace_id,claimed.job_id,next_sequence,
                  'job.leased',NULL,NULL,'job.leased',false,now_at,
                  now_at + interval '24 hours',event_fingerprint);
          RETURN QUERY SELECT claimed.organization_id,claimed.workspace_id,claimed.job_id,
            claimed.job_kind,claimed.input_manifest,claimed.input_digest,next_attempt,
            next_generation,claimed.cancellation_state;
        END $$;
        REVOKE ALL ON FUNCTION workspace.claim_next_durable_job(text,integer) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.claim_next_durable_job(text,integer) TO asd_document_worker;
        CREATE FUNCTION workspace.reconcile_unclaimable_durable_jobs()
        RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        DECLARE
          candidate record;
          receipt_uuid uuid;
          receipt_digest text;
          event_sequence bigint;
          event_digest text;
          reconciled integer := 0;
        BEGIN
          FOR candidate IN
            SELECT j.organization_id,j.workspace_id,j.job_id,j.lease_generation,
              CASE WHEN j.cancellation_state='requested'
                THEN 'cancelled' ELSE 'reconciliation_required' END AS terminal_state,
              CASE
                WHEN j.cancellation_state='requested' THEN 'job_cancelled_after_worker_loss'
                WHEN j.state IN ('leased','running') AND j.lease_expires_at < clock_timestamp()
                  AND j.attempt_count >= j.max_attempts THEN 'retry_exhausted'
                ELSE 'dependency_terminal_failure'
              END AS outcome_code
            FROM workspace.durable_jobs j
            WHERE (j.state IN ('leased','running') AND j.lease_expires_at < clock_timestamp()
                   AND (j.attempt_count >= j.max_attempts OR j.cancellation_state='requested'))
               OR (j.state='queued' AND EXISTS (
                 SELECT 1 FROM workspace.durable_job_dependencies d
                 JOIN workspace.durable_jobs prerequisite
                   ON prerequisite.organization_id=d.organization_id
                  AND prerequisite.workspace_id=d.workspace_id
                  AND prerequisite.job_id=d.depends_on_job_id
                 WHERE d.organization_id=j.organization_id AND d.workspace_id=j.workspace_id
                   AND d.job_id=j.job_id AND d.dependency_kind='success_required'
                   AND prerequisite.state IN ('failed','cancelled','reconciliation_required')
               ))
            FOR UPDATE OF j SKIP LOCKED
          LOOP
            receipt_uuid := gen_random_uuid();
            receipt_digest := 'sha256:' || encode(public.digest(
              candidate.job_id::text || '-' || candidate.terminal_state || '-' || candidate.outcome_code,
              'sha256'),'hex');
            INSERT INTO workspace.job_terminal_receipts
              (organization_id,workspace_id,terminal_receipt_id,job_id,lease_generation,
               terminal_state,typed_outcome_code,result_manifest,result_digest)
            VALUES (candidate.organization_id,candidate.workspace_id,receipt_uuid,candidate.job_id,
              candidate.lease_generation,candidate.terminal_state,candidate.outcome_code,
              jsonb_build_object('outcome_code',candidate.outcome_code),receipt_digest)
            ON CONFLICT (organization_id,workspace_id,job_id) DO NOTHING;
            SELECT terminal_receipt_id INTO receipt_uuid
              FROM workspace.job_terminal_receipts
              WHERE organization_id=candidate.organization_id
                AND workspace_id=candidate.workspace_id AND job_id=candidate.job_id;
            UPDATE workspace.durable_jobs SET state=candidate.terminal_state,
              completed_at=clock_timestamp(),typed_failure_code=candidate.outcome_code,
              result_receipt_id=receipt_uuid,lease_owner=NULL,lease_expires_at=NULL,
              cancellation_state=CASE WHEN cancellation_state='requested' THEN 'acknowledged' ELSE cancellation_state END
            WHERE organization_id=candidate.organization_id AND workspace_id=candidate.workspace_id
              AND job_id=candidate.job_id AND state NOT IN ('succeeded','failed','cancelled','reconciliation_required');
            SELECT COALESCE(max(e.event_sequence),0)+1 INTO event_sequence
              FROM workspace.job_progress_events e
              WHERE e.organization_id=candidate.organization_id
                AND e.workspace_id=candidate.workspace_id AND e.job_id=candidate.job_id;
            event_digest := 'sha256:' || encode(public.digest(
              candidate.job_id::text || '-' || event_sequence::text || '-job.' ||
              candidate.terminal_state || '-' || candidate.outcome_code,'sha256'),'hex');
            INSERT INTO workspace.job_progress_events
              (organization_id,workspace_id,job_id,event_sequence,event_type,progress_current,
               progress_total,safe_message_code,terminal,recorded_at,retention_until,event_digest)
            VALUES (candidate.organization_id,candidate.workspace_id,candidate.job_id,event_sequence,
              'job.' || candidate.terminal_state,1,1,candidate.outcome_code,true,
              clock_timestamp(),clock_timestamp() + interval '24 hours',event_digest);
            reconciled := reconciled + 1;
          END LOOP;
          RETURN reconciled;
        END $$;
        REVOKE ALL ON FUNCTION workspace.reconcile_unclaimable_durable_jobs() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.reconcile_unclaimable_durable_jobs() TO asd_document_worker;
        """
    )


def _apply_guards_grants_and_rls() -> None:
    op.execute(
        """
        CREATE FUNCTION application.reject_spine_mutation_except_destruction()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF TG_OP='DELETE'
             AND pg_has_role(session_user,'asd_destruction_executor','member')
             AND NULLIF(current_setting('asd.lifecycle_operation_id',true),'') IS NOT NULL THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'immutable Product Spine record' USING ERRCODE='55000';
        END $$;
        """
    )
    for table in (
        "auth_audit_events",
        "login_attempts",
        "workspace_reset_terminal_receipts",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON application.{table} "
            "FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation()"
        )
    for table in (
        "intake_manifests",
        "intake_manifest_items",
        "document_records",
        "document_versions",
        "document_processing_states",
        "document_version_activation_decisions",
        "document_pages",
        "durable_job_attempts",
        "durable_job_dependencies",
        "job_progress_events",
        "job_leases",
        "job_cancellations",
        "job_terminal_receipts",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction()"
        )
    op.execute(
        """
        CREATE FUNCTION workspace.require_job_terminal_receipt()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.state IN ('succeeded','failed','cancelled','reconciliation_required')
             AND OLD.state IS DISTINCT FROM NEW.state
             AND NOT EXISTS (
               SELECT 1 FROM workspace.job_terminal_receipts r
               WHERE r.organization_id=NEW.organization_id AND r.workspace_id=NEW.workspace_id
                 AND r.job_id=NEW.job_id AND r.terminal_state=NEW.state
             ) THEN
            RAISE EXCEPTION 'terminal durable job state requires exact receipt' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER durable_job_terminal_receipt_guard
          BEFORE UPDATE ON workspace.durable_jobs FOR EACH ROW
          EXECUTE FUNCTION workspace.require_job_terminal_receipt();
        """
    )
    op.execute("GRANT USAGE ON SCHEMA application TO asd_app,asd_lifecycle_service")
    op.execute("GRANT USAGE ON SCHEMA workspace TO asd_document_worker")
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON application.owner_identities,application.sessions,"
        "application.owner_organization_grants TO asd_app"
    )
    op.execute(
        "GRANT SELECT,INSERT ON application.login_attempts,application.auth_audit_events TO asd_app"
    )
    op.execute(
        "GRANT SELECT,INSERT ON application.workspace_reset_terminal_receipts TO asd_lifecycle_service"
    )
    op.execute(
        "GRANT USAGE,SELECT ON SEQUENCE workspace.job_progress_events_progress_event_id_seq "
        "TO asd_app,asd_document_worker"
    )
    op.execute("GRANT SELECT,INSERT ON workspace.source_locators TO asd_document_worker")
    op.execute(
        "CREATE POLICY source_locators_document_worker_scope ON workspace.source_locators "
        "FOR SELECT TO asd_document_worker USING ("
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute(
        "CREATE POLICY source_locators_document_worker_insert_scope ON workspace.source_locators "
        "FOR INSERT TO asd_document_worker WITH CHECK ("
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    for table in WORKSPACE_TABLES:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_scope ON workspace.{table} USING ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
            "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) WITH CHECK ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
            "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
        )
        op.execute(f"GRANT SELECT,INSERT,UPDATE ON workspace.{table} TO asd_app")
        op.execute(f"GRANT SELECT,INSERT,UPDATE ON workspace.{table} TO asd_document_worker")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS source_locators_document_worker_insert_scope "
        "ON workspace.source_locators"
    )
    op.execute(
        "DROP POLICY IF EXISTS source_locators_document_worker_scope ON workspace.source_locators"
    )
    op.execute("DROP FUNCTION workspace.reconcile_unclaimable_durable_jobs()")
    op.execute("DROP FUNCTION workspace.claim_next_durable_job(text,integer)")
    op.execute("DROP FUNCTION application.list_authorized_workspaces(text)")
    op.execute("DROP FUNCTION IF EXISTS application.get_platform_knowledge_status()")
    op.execute("DROP FUNCTION application.resolve_workspace_scope(text,uuid)")
    for table in reversed(WORKSPACE_TABLES):
        op.execute(f"DROP TABLE workspace.{table} CASCADE")
    op.execute("DROP FUNCTION workspace.require_job_terminal_receipt()")
    op.execute("DROP FUNCTION application.reject_spine_mutation_except_destruction()")
    op.execute("REVOKE SELECT,INSERT ON workspace.source_locators FROM asd_document_worker")
    op.execute("REVOKE USAGE ON SCHEMA workspace FROM asd_document_worker")
    op.execute("DROP SCHEMA application CASCADE")
    # Cluster roles are shared by every database. Keep the NOLOGIN capability role
    # on per-database downgrade so another ASD-KONTUR database is never broken.
