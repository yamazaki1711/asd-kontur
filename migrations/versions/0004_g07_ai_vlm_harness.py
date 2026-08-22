"""Create the G-07 Candidate-only AI/VLM verification harness.

Revision ID: 0004_g07
Revises: 0003_g06
Create Date: 2026-08-23
"""

from __future__ import annotations

import os

from alembic import op

revision = "0004_g07"
down_revision = "0003_g06"
branch_labels = None
depends_on = None

PLATFORM_TABLES = (
    "vlm_provider_versions",
    "vlm_execution_profile_versions",
    "vlm_routing_policy_versions",
    "vlm_execution_budget_versions",
    "vlm_qualification_profiles",
)

WORKSPACE_TABLES = (
    "vlm_execution_requests",
    "vlm_routing_decisions",
    "vlm_execution_attempts",
    "vlm_provider_results",
    "vlm_provider_failures",
    "vlm_render_artifacts",
    "candidates",
    "candidate_versions",
    "candidate_fields",
    "candidate_field_evidence",
    "vlm_validation_runs",
    "vlm_validation_failures",
    "vlm_repair_plans",
    "vlm_repair_cycles",
    "vlm_batches",
    "vlm_batch_items",
    "vlm_cost_envelopes",
    "vlm_cost_ledger",
    "vlm_raw_artifacts",
)


def upgrade() -> None:
    _create_role()
    _create_platform_registry()
    _create_workspace_records()
    _apply_guards_grants_and_rls()


def _create_role() -> None:
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_harness_service') "
        "THEN CREATE ROLE asd_harness_service NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; "
        "END IF; END $$"
    )


def _create_platform_registry() -> None:
    op.execute(
        """
        CREATE TABLE platform.vlm_provider_versions (
          provider_id uuid NOT NULL,
          version text NOT NULL,
          provider_key text NOT NULL,
          provider_kind text NOT NULL CHECK (provider_kind IN ('local','external','synthetic')),
          network_egress boolean NOT NULL,
          status text NOT NULL CHECK (status IN ('draft','evaluation','active','suspended','blocked','retired')),
          capabilities_digest text NOT NULL CHECK (capabilities_digest ~ '^sha256:[a-f0-9]{64}$'),
          owner_identity_id text NOT NULL,
          effective_from timestamptz NOT NULL,
          effective_until timestamptz,
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (provider_id,version),
          UNIQUE (provider_key,version),
          CHECK (lower(version)<>'latest')
        );
        CREATE TABLE platform.vlm_execution_profile_versions (
          execution_profile_id uuid NOT NULL,
          version text NOT NULL,
          profile_key text NOT NULL,
          provider_id uuid NOT NULL,
          provider_version text NOT NULL,
          model_identity text NOT NULL,
          model_revision text NOT NULL,
          execution_format text NOT NULL,
          quantization text NOT NULL CHECK (quantization<>'4bit'),
          runtime_version text NOT NULL,
          prompt_version text NOT NULL,
          output_schema_version text NOT NULL,
          preprocessing_version text NOT NULL,
          rendering_version text NOT NULL,
          verification_policy_version text NOT NULL,
          heavy_resource_class text NOT NULL,
          status text NOT NULL CHECK (status IN ('draft','evaluation','active','suspended','blocked','retired')),
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (execution_profile_id,version),
          UNIQUE (profile_key,version),
          FOREIGN KEY (provider_id,provider_version) REFERENCES platform.vlm_provider_versions(provider_id,version) ON DELETE RESTRICT,
          CHECK (lower(version)<>'latest' AND lower(model_revision)<>'latest')
        );
        CREATE TABLE platform.vlm_routing_policy_versions (
          routing_policy_id uuid NOT NULL,
          version text NOT NULL,
          policy_key text NOT NULL,
          environment text NOT NULL CHECK (environment IN ('development','qualification','production')),
          external_active boolean NOT NULL,
          provider_terms_ref text,
          raw_artifact_policy text NOT NULL CHECK (raw_artifact_policy IN ('workspace_encrypted','no_raw_storage')),
          decision_table jsonb NOT NULL,
          approved_by_identity_id text,
          effective_from timestamptz NOT NULL,
          effective_until timestamptz,
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (routing_policy_id,version),
          UNIQUE (policy_key,version),
          CHECK (lower(version)<>'latest'),
          CHECK (environment<>'production' OR NOT external_active OR (provider_terms_ref IS NOT NULL AND approved_by_identity_id IS NOT NULL))
        );
        CREATE TABLE platform.vlm_execution_budget_versions (
          budget_id uuid NOT NULL,
          version text NOT NULL,
          budget_key text NOT NULL,
          environment text NOT NULL CHECK (environment IN ('development','qualification','production')),
          purpose text NOT NULL,
          execution_profile_ref text NOT NULL,
          failure_class text NOT NULL,
          max_attempts integer,
          max_repair_cycles integer,
          timeout_seconds numeric,
          token_limit bigint,
          page_limit integer,
          payload_bytes bigint,
          no_progress_threshold integer,
          provider_switch_allowed boolean,
          cost_limit numeric,
          currency text,
          status text NOT NULL CHECK (status IN ('draft','active','unset','blocked','retired')),
          approved_by_identity_id text,
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (budget_id,version),
          UNIQUE (budget_key,version,purpose,execution_profile_ref,failure_class),
          CHECK (lower(version)<>'latest'),
          CHECK (status<>'active' OR (max_attempts IS NOT NULL AND max_repair_cycles IS NOT NULL AND timeout_seconds>0 AND token_limit>0 AND page_limit>0 AND payload_bytes>0 AND no_progress_threshold>0)),
          CHECK (environment<>'production' OR status<>'active' OR approved_by_identity_id IS NOT NULL)
        );
        CREATE TABLE platform.vlm_qualification_profiles (
          qualification_profile_id uuid NOT NULL,
          version text NOT NULL,
          execution_profile_id uuid NOT NULL,
          execution_profile_version text NOT NULL,
          corpus_version text NOT NULL,
          strata_manifest_digest text NOT NULL CHECK (strata_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          metrics jsonb NOT NULL,
          blocker_results jsonb NOT NULL,
          environment text NOT NULL CHECK (environment IN ('development','qualification','production')),
          decision text NOT NULL CHECK (decision IN ('unqualified','evaluation_only','qualified','suspended','revoked','blocked')),
          approved_by_identity_id text,
          valid_from timestamptz NOT NULL,
          valid_until timestamptz NOT NULL,
          regression_parent_ref text,
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (qualification_profile_id,version),
          FOREIGN KEY (execution_profile_id,execution_profile_version) REFERENCES platform.vlm_execution_profile_versions(execution_profile_id,version) ON DELETE RESTRICT,
          CHECK (valid_until>valid_from),
          CHECK (lower(version)<>'latest'),
          CHECK (decision<>'qualified' OR approved_by_identity_id IS NOT NULL)
        );
        """
    )
    for table in PLATFORM_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON platform.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )


def _create_workspace_records() -> None:
    op.execute(
        """
        CREATE TABLE workspace.vlm_execution_requests (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          request_id uuid NOT NULL,
          source_version_id uuid NOT NULL,
          purpose text NOT NULL,
          purpose_version text NOT NULL,
          classification text NOT NULL,
          authorized_locator_ids uuid[] NOT NULL CHECK (cardinality(authorized_locator_ids)>0),
          route text NOT NULL CHECK (route IN ('native_only','local_ocr','local_vlm','authorized_external_vlm','no_execution')),
          execution_profile_id uuid NOT NULL,
          execution_profile_version text NOT NULL,
          rule_set_version text NOT NULL,
          authorization_decision_id uuid NOT NULL,
          routing_policy_version text NOT NULL,
          budget_version text NOT NULL,
          idempotency_key text NOT NULL,
          correlation_id uuid NOT NULL,
          causation_id uuid NOT NULL,
          source_digest text NOT NULL CHECK (source_digest ~ '^sha256:[a-f0-9]{64}$'),
          payload_digest text NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
          request_digest text NOT NULL CHECK (request_digest ~ '^sha256:[a-f0-9]{64}$'),
          retention_class text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,request_id),
          UNIQUE (organization_id,workspace_id,idempotency_key),
          FOREIGN KEY (organization_id,workspace_id) REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (execution_profile_id,execution_profile_version) REFERENCES platform.vlm_execution_profile_versions(execution_profile_id,version) ON DELETE RESTRICT,
          CHECK (lower(purpose_version)<>'latest' AND lower(execution_profile_version)<>'latest' AND lower(rule_set_version)<>'latest' AND lower(routing_policy_version)<>'latest' AND lower(budget_version)<>'latest')
        );
        CREATE TABLE workspace.vlm_routing_decisions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, routing_decision_id uuid NOT NULL,
          request_id uuid NOT NULL, considered_routes text[] NOT NULL, selected_route text NOT NULL,
          rejected_reasons jsonb NOT NULL, decision text NOT NULL CHECK (decision IN ('allowed','denied','blocked')),
          authorization_decision_id uuid, policy_versions text[] NOT NULL,
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'), decided_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,routing_decision_id),
          FOREIGN KEY (organization_id,workspace_id,request_id) REFERENCES workspace.vlm_execution_requests(organization_id,workspace_id,request_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.vlm_execution_attempts (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, attempt_id uuid NOT NULL,
          request_id uuid NOT NULL, parent_attempt_id uuid, attempt_kind text NOT NULL CHECK (attempt_kind IN ('initial','retry','repair','fallback')),
          provider_execution_id text, status text NOT NULL CHECK (status IN ('accepted','pending','running','completed','failed','cancelled','unknown')),
          expected_source_digest text NOT NULL CHECK (expected_source_digest ~ '^sha256:[a-f0-9]{64}$'),
          started_at timestamptz NOT NULL, finished_at timestamptz, failure_code text,
          PRIMARY KEY (organization_id,workspace_id,attempt_id),
          FOREIGN KEY (organization_id,workspace_id,request_id) REFERENCES workspace.vlm_execution_requests(organization_id,workspace_id,request_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,parent_attempt_id) REFERENCES workspace.vlm_execution_attempts(organization_id,workspace_id,attempt_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.vlm_provider_results (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, provider_result_id uuid NOT NULL,
          request_id uuid NOT NULL, attempt_id uuid NOT NULL, provider_execution_id text NOT NULL,
          provider_status text NOT NULL CHECK (provider_status IN ('completed','failed','cancelled','unknown')),
          finish_reason text NOT NULL, structured_output jsonb, response_schema_version text NOT NULL,
          request_digest text NOT NULL CHECK (request_digest ~ '^sha256:[a-f0-9]{64}$'),
          response_digest text NOT NULL CHECK (response_digest ~ '^sha256:[a-f0-9]{64}$'), received_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,provider_result_id),
          UNIQUE (organization_id,workspace_id,attempt_id),
          FOREIGN KEY (organization_id,workspace_id,attempt_id) REFERENCES workspace.vlm_execution_attempts(organization_id,workspace_id,attempt_id) ON DELETE RESTRICT,
          CHECK (lower(response_schema_version)<>'latest')
        );
        CREATE TABLE workspace.vlm_provider_failures (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, provider_failure_id uuid NOT NULL,
          attempt_id uuid NOT NULL, failure_code text NOT NULL, retryability text NOT NULL,
          terminal boolean NOT NULL, diagnostic_ref text, recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,provider_failure_id),
          FOREIGN KEY (organization_id,workspace_id,attempt_id) REFERENCES workspace.vlm_execution_attempts(organization_id,workspace_id,attempt_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.vlm_render_artifacts (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, render_id uuid NOT NULL,
          source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL, parent_render_id uuid,
          source_digest text NOT NULL CHECK (source_digest ~ '^sha256:[a-f0-9]{64}$'),
          renderer text NOT NULL, renderer_version text NOT NULL, rendering_profile_version text NOT NULL,
          page_number integer NOT NULL CHECK (page_number>=1), page_box double precision[] NOT NULL CHECK (cardinality(page_box)=4),
          source_rotation integer NOT NULL, applied_rotation integer NOT NULL, dpi integer NOT NULL CHECK (dpi>0),
          pixel_width integer NOT NULL CHECK (pixel_width>0), pixel_height integer NOT NULL CHECK (pixel_height>0),
          color_space text NOT NULL, image_format text NOT NULL, preprocessing_version text NOT NULL,
          source_to_render double precision[] NOT NULL CHECK (cardinality(source_to_render)=9),
          render_to_source double precision[] NOT NULL CHECK (cardinality(render_to_source)=9),
          crop double precision[], overlap integer NOT NULL DEFAULT 0, padding integer NOT NULL DEFAULT 0,
          render_digest text NOT NULL CHECK (render_digest ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,render_id),
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,parent_render_id) REFERENCES workspace.vlm_render_artifacts(organization_id,workspace_id,render_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.candidates (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, candidate_id uuid NOT NULL,
          purpose text NOT NULL, source_version_id uuid NOT NULL, retention_class text NOT NULL,
          created_at timestamptz NOT NULL, PRIMARY KEY (organization_id,workspace_id,candidate_id),
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.candidate_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, candidate_id uuid NOT NULL,
          candidate_version integer NOT NULL CHECK (candidate_version>=1), parent_version integer,
          attempt_id uuid, origin text NOT NULL CHECK (origin IN ('native_parser','ocr','vlm','repair','import','human_draft')),
          status text NOT NULL CHECK (status IN ('unverified','validating','repair_planned','validated_candidate','unresolved_uncertainty','rejected_extraction','provider_model_failure')),
          output_schema_version text NOT NULL, digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,candidate_id,candidate_version),
          FOREIGN KEY (organization_id,workspace_id,candidate_id) REFERENCES workspace.candidates(organization_id,workspace_id,candidate_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,attempt_id) REFERENCES workspace.vlm_execution_attempts(organization_id,workspace_id,attempt_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,candidate_id,parent_version) REFERENCES workspace.candidate_versions(organization_id,workspace_id,candidate_id,candidate_version) ON DELETE RESTRICT,
          CHECK (lower(output_schema_version)<>'latest'), CHECK (parent_version IS NULL OR parent_version<candidate_version)
        );
        CREATE TABLE workspace.candidate_fields (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, candidate_id uuid NOT NULL,
          candidate_version integer NOT NULL, field_path text NOT NULL CHECK (field_path LIKE '/%'),
          value_type text NOT NULL, typed_value jsonb NOT NULL, unit text, validation_state text NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,candidate_id,candidate_version,field_path),
          FOREIGN KEY (organization_id,workspace_id,candidate_id,candidate_version) REFERENCES workspace.candidate_versions(organization_id,workspace_id,candidate_id,candidate_version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.candidate_field_evidence (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, candidate_id uuid NOT NULL,
          candidate_version integer NOT NULL, field_path text NOT NULL, source_version_id uuid NOT NULL,
          source_locator_id uuid NOT NULL, evidence_link_id uuid, evidence_role text NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,candidate_id,candidate_version,field_path,source_locator_id),
          FOREIGN KEY (organization_id,workspace_id,candidate_id,candidate_version,field_path) REFERENCES workspace.candidate_fields(organization_id,workspace_id,candidate_id,candidate_version,field_path) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id) REFERENCES workspace.evidence_links(organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.vlm_validation_runs (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, validation_run_id uuid NOT NULL,
          candidate_id uuid NOT NULL, candidate_version integer NOT NULL, validator_profile_version text NOT NULL,
          required_validators text[] NOT NULL, skipped_validators text[] NOT NULL,
          status text NOT NULL CHECK (status IN ('passed','failed','blocked','indeterminate')),
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'), validated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,validation_run_id),
          FOREIGN KEY (organization_id,workspace_id,candidate_id,candidate_version) REFERENCES workspace.candidate_versions(organization_id,workspace_id,candidate_id,candidate_version) ON DELETE RESTRICT,
          CHECK (lower(validator_profile_version)<>'latest'),
          CHECK (status<>'passed' OR cardinality(skipped_validators)=0)
        );
        CREATE TABLE workspace.vlm_validation_failures (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, validation_failure_id uuid NOT NULL,
          validation_run_id uuid NOT NULL, failure_code text NOT NULL, failure_code_version text NOT NULL,
          validator_key text NOT NULL, validator_version text NOT NULL, field_path text NOT NULL,
          severity text NOT NULL, repairability text NOT NULL, blocking boolean NOT NULL,
          source_locator_ids uuid[] NOT NULL, parameters jsonb NOT NULL,
          failure_fingerprint text NOT NULL CHECK (failure_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,validation_failure_id),
          FOREIGN KEY (organization_id,workspace_id,validation_run_id) REFERENCES workspace.vlm_validation_runs(organization_id,workspace_id,validation_run_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.vlm_repair_plans (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, repair_plan_id uuid NOT NULL,
          candidate_id uuid NOT NULL, parent_candidate_version integer NOT NULL, allowed_fields text[] NOT NULL,
          allowed_locator_ids uuid[] NOT NULL, failure_fingerprints text[] NOT NULL,
          budget_version text NOT NULL, rule_set_version text NOT NULL, policy_versions text[] NOT NULL,
          plan_digest text NOT NULL CHECK (plan_digest ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,repair_plan_id),
          FOREIGN KEY (organization_id,workspace_id,candidate_id,parent_candidate_version) REFERENCES workspace.candidate_versions(organization_id,workspace_id,candidate_id,candidate_version) ON DELETE RESTRICT,
          CHECK (cardinality(allowed_fields)>0 AND cardinality(allowed_locator_ids)>0)
        );
        CREATE TABLE workspace.vlm_repair_cycles (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, repair_plan_id uuid NOT NULL,
          cycle integer NOT NULL CHECK (cycle>=1), attempt_id uuid NOT NULL, child_candidate_version integer,
          prior_failure_set_digest text NOT NULL CHECK (prior_failure_set_digest ~ '^sha256:[a-f0-9]{64}$'),
          result_failure_set_digest text CHECK (result_failure_set_digest ~ '^sha256:[a-f0-9]{64}$'),
          outcome text NOT NULL CHECK (outcome IN ('improved','completed','no_progress','exhausted','failed')),
          PRIMARY KEY (organization_id,workspace_id,repair_plan_id,cycle),
          FOREIGN KEY (organization_id,workspace_id,repair_plan_id) REFERENCES workspace.vlm_repair_plans(organization_id,workspace_id,repair_plan_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,attempt_id) REFERENCES workspace.vlm_execution_attempts(organization_id,workspace_id,attempt_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.vlm_batches (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, batch_id uuid NOT NULL,
          manifest_digest text NOT NULL CHECK (manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          execution_profile_version text NOT NULL, concurrency_limit integer NOT NULL CHECK (concurrency_limit>=1),
          state text NOT NULL CHECK (state IN ('pending','running','partial','completed','stopped','cancelled','unknown','failed')),
          created_at timestamptz NOT NULL, PRIMARY KEY (organization_id,workspace_id,batch_id)
        );
        CREATE TABLE workspace.vlm_batch_items (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, batch_id uuid NOT NULL,
          item_id uuid NOT NULL, request_id uuid NOT NULL, attempt_id uuid,
          state text NOT NULL CHECK (state IN ('pending','submitted','completed','failed','cancelled','unknown')),
          result_digest text CHECK (result_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,batch_id,item_id),
          FOREIGN KEY (organization_id,workspace_id,batch_id) REFERENCES workspace.vlm_batches(organization_id,workspace_id,batch_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,request_id) REFERENCES workspace.vlm_execution_requests(organization_id,workspace_id,request_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,attempt_id) REFERENCES workspace.vlm_execution_attempts(organization_id,workspace_id,attempt_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.vlm_cost_envelopes (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, cost_envelope_id uuid NOT NULL,
          envelope_version text NOT NULL, purpose text NOT NULL, provider_profile_ref text NOT NULL,
          currency text NOT NULL, committed_maximum numeric NOT NULL CHECK (committed_maximum>=0),
          per_item_maximum numeric NOT NULL CHECK (per_item_maximum>=0), stop_threshold numeric NOT NULL CHECK (stop_threshold>=0),
          valid_until timestamptz NOT NULL, authorizing_principal text NOT NULL,
          environment text NOT NULL CHECK (environment IN ('development','qualification','production')),
          status text NOT NULL CHECK (status IN ('active','exhausted','expired','blocked','retired')),
          digest text NOT NULL CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,cost_envelope_id,envelope_version),
          CHECK (lower(envelope_version)<>'latest'),
          CHECK (environment<>'production' OR status<>'active')
        );
        CREATE TABLE workspace.vlm_cost_ledger (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, cost_record_id uuid NOT NULL,
          cost_envelope_id uuid NOT NULL, envelope_version text NOT NULL, item_key text NOT NULL,
          operation text NOT NULL CHECK (operation IN ('reserve','commit','release','reconcile')),
          amount numeric NOT NULL CHECK (amount>=0), status text NOT NULL, attempt_id uuid,
          recorded_at timestamptz NOT NULL, PRIMARY KEY (organization_id,workspace_id,cost_record_id),
          FOREIGN KEY (organization_id,workspace_id,cost_envelope_id,envelope_version) REFERENCES workspace.vlm_cost_envelopes(organization_id,workspace_id,cost_envelope_id,envelope_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,attempt_id) REFERENCES workspace.vlm_execution_attempts(organization_id,workspace_id,attempt_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.vlm_raw_artifacts (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, raw_artifact_id uuid NOT NULL,
          artifact_kind text NOT NULL CHECK (artifact_kind IN ('request','provider_response','prompt','render','candidate','validation','repair','batch','cost','cache')),
          scoped_object_ref text, content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          classification text NOT NULL, retention_class text NOT NULL,
          storage_policy text NOT NULL CHECK (storage_policy IN ('workspace_encrypted','no_raw_storage')),
          encryption_key_ref text, created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,raw_artifact_id),
          FOREIGN KEY (organization_id,workspace_id) REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT,
          CHECK ((storage_policy='no_raw_storage' AND scoped_object_ref IS NULL AND encryption_key_ref IS NULL) OR (storage_policy='workspace_encrypted' AND scoped_object_ref IS NOT NULL))
        );
        """
    )


def _apply_guards_grants_and_rls() -> None:
    predicate = (
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid"
    )
    op.execute("GRANT USAGE ON SCHEMA platform,workspace TO asd_harness_service")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION workspace.reject_harness_mutation_unless_destroy()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member') THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'immutable harness record cannot be mutated' USING ERRCODE='55000';
        END $$
        """
    )
    op.execute(
        "GRANT SELECT ON "
        + ",".join(f"platform.{table}" for table in PLATFORM_TABLES)
        + " TO asd_harness_service"
    )
    op.execute(
        "GRANT SELECT,INSERT ON "
        + ",".join(f"platform.{table}" for table in PLATFORM_TABLES)
        + " TO asd_platform_curator"
    )
    for table in WORKSPACE_TABLES:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_harness_scope_policy ON workspace.{table} FOR ALL TO asd_harness_service "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_app_scope_policy ON workspace.{table} FOR SELECT TO asd_app "
            f"USING ({predicate})"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_harness_service")
        op.execute(f"GRANT SELECT ON workspace.{table} TO asd_app")
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION workspace.reject_harness_mutation_unless_destroy()"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_write_fence BEFORE INSERT ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION workspace.enforce_material_write_fence()"
        )
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE POLICY {table}_destruction_scope_policy ON workspace.{table} FOR ALL TO asd_destruction_executor "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "destructive downgrade is allowed only for a disposable development/test database"
        )
    for table in reversed(WORKSPACE_TABLES):
        op.execute(f"DROP TABLE IF EXISTS workspace.{table} CASCADE")
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE IF EXISTS platform.{table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS workspace.reject_harness_mutation_unless_destroy()")
    op.execute("REVOKE USAGE ON SCHEMA platform,workspace FROM asd_harness_service")
    # Cluster roles remain, matching migrations 0001-0003. A production rollback
    # is a forward repair or verified restore, never automatic role destruction.
