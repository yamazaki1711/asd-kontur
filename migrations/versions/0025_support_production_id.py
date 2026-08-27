"""Connect WorkRequirementMatrix to production-shaped ID package generation.

Revision ID: 0025_support_production_id
Revises: 0024_rule_activation_vertical
Create Date: 2026-08-27
"""

from __future__ import annotations

import os

from alembic import op

revision = "0025_support_production_id"
down_revision = "0024_rule_activation_vertical"
branch_labels = None
depends_on = None

OLD_JOB_KINDS = (
    "DOCUMENT_ADMISSION",
    "DOCUMENT_HASH",
    "PDF_INVENTORY",
    "NATIVE_TEXT_EXTRACTION",
    "DOCUMENT_FORMAT_INVENTORY",
    "PDF_PAGE_HEALTH_ANALYSIS",
    "NATIVE_LAYOUT_EXTRACTION",
    "OCR_ROUTING",
    "OCR_EXTRACTION",
    "DOCUMENT_PAGE_CLASSIFICATION",
    "DOCUMENT_AGGREGATION",
    "PROJECT_DEFINITION_EXTRACTION",
    "WORK_QUANTITY_MATERIAL_EXTRACTION",
    "WORK_PACKAGE_ASSEMBLY",
    "REQUIREMENT_MATRIX_ASSEMBLY",
    "PROJECT_UNDERSTANDING_RECONCILIATION",
    "EVIDENCE_INDEX_UPDATE",
    "WORKSPACE_RESET_RECONCILIATION",
)

WORKSPACE_TABLES = (
    "id_package_volume_book_versions",
    "id_package_document_membership_versions",
    "support_register_candidates",
    "id_package_readiness_evaluations",
    "support_generation_job_bindings",
)


def upgrade() -> None:
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    kinds = (*OLD_JOB_KINDS, "ID_DOCUMENT_GENERATION")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check CHECK "
        f"(job_kind IN ({','.join(repr(value) for value in kinds)}))"
    )
    # A package candidate is allowed to expose an unresolved RuleSet blocker.
    # Final/authoritative transitions continue to require an exact active RuleSet.
    op.execute(
        "ALTER TABLE workspace.id_package_versions ALTER COLUMN rule_set_version_id DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE platform.template_versions DROP CONSTRAINT "
        "template_versions_assurance_class_check"
    )
    op.execute(
        "ALTER TABLE platform.template_versions ADD CONSTRAINT "
        "template_versions_assurance_class_check CHECK "
        "(assurance_class IN ('synthetic_development','development_candidate','production'))"
    )
    op.execute(
        "ALTER TABLE workspace.support_render_artifacts DROP CONSTRAINT "
        "support_render_artifacts_assurance_class_check"
    )
    op.execute(
        "ALTER TABLE workspace.support_render_artifacts ADD CONSTRAINT "
        "support_render_artifacts_assurance_class_check CHECK "
        "(assurance_class IN ('synthetic_structural_only','template_candidate','production_qualified'))"
    )
    op.execute(
        """
        CREATE TABLE platform.template_artifacts (
          template_id uuid NOT NULL,
          template_version text NOT NULL,
          artifact_version bigint NOT NULL CHECK (artifact_version>=1),
          object_key text NOT NULL,
          media_type text NOT NULL,
          byte_length bigint NOT NULL CHECK (byte_length>0),
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          source_provenance jsonb NOT NULL,
          validation_status text NOT NULL CHECK (validation_status IN ('candidate','qualified','blocked','rejected')),
          validation_receipt_digest text NOT NULL CHECK (validation_receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (template_id,template_version,artifact_version),
          UNIQUE (content_digest),
          FOREIGN KEY (template_id,template_version)
            REFERENCES platform.template_versions(template_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.template_field_definitions (
          field_schema_id uuid NOT NULL,
          field_schema_version text NOT NULL,
          field_key text NOT NULL,
          value_type text NOT NULL,
          material boolean NOT NULL,
          required boolean NOT NULL,
          repeatable boolean NOT NULL,
          binding_token text NOT NULL,
          display_order integer NOT NULL CHECK (display_order>=1),
          definition_digest text NOT NULL CHECK (definition_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (field_schema_id,field_schema_version,field_key),
          UNIQUE (field_schema_id,field_schema_version,display_order),
          FOREIGN KEY (field_schema_id,field_schema_version)
            REFERENCES platform.field_schema_versions(field_schema_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.required_document_type_templates (
          required_document_type_id uuid NOT NULL,
          required_document_type_version text NOT NULL,
          template_id uuid NOT NULL,
          template_version text NOT NULL,
          applicability_status text NOT NULL CHECK (applicability_status IN ('candidate','qualified','active','blocked','retired')),
          mapping_digest text NOT NULL CHECK (mapping_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (required_document_type_id,required_document_type_version,template_id,template_version),
          FOREIGN KEY (required_document_type_id,required_document_type_version)
            REFERENCES platform.required_document_type_versions(required_document_type_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (template_id,template_version)
            REFERENCES platform.template_versions(template_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.id_package_volume_book_versions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          id_package_id uuid NOT NULL,
          id_package_version bigint NOT NULL,
          volume_book_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          ordinal integer NOT NULL CHECK (ordinal>=1),
          title text NOT NULL,
          register_level text NOT NULL,
          required_copy_count integer NOT NULL CHECK (required_copy_count>=1),
          semantic_fingerprint text NOT NULL CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,volume_book_id,version),
          UNIQUE (organization_id,workspace_id,id_package_id,id_package_version,ordinal),
          FOREIGN KEY (organization_id,workspace_id,id_package_id,id_package_version)
            REFERENCES workspace.id_package_versions(organization_id,workspace_id,id_package_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.id_package_document_membership_versions (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          membership_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          id_package_id uuid NOT NULL,
          id_package_version bigint NOT NULL,
          volume_book_id uuid NOT NULL,
          volume_book_version bigint NOT NULL,
          matrix_id uuid NOT NULL,
          matrix_version bigint NOT NULL,
          document_requirement_id uuid,
          document_requirement_version bigint,
          role text NOT NULL,
          ordinal integer NOT NULL CHECK (ordinal>=1),
          required_copy_count integer NOT NULL CHECK (required_copy_count>=1),
          stage text NOT NULL,
          subject_kind text NOT NULL CHECK (subject_kind IN ('package_register','required_document','generated_document_candidate','finalized_document','source_version','executive_scheme')),
          subject_ref text NOT NULL,
          state text NOT NULL CHECK (state IN ('required','generated_candidate','finalized','covered','missing','conflict','indeterminate','blocked','not_applicable')),
          evidence_refs text[] NOT NULL CHECK (cardinality(evidence_refs)>0),
          blocker_codes text[] NOT NULL,
          semantic_fingerprint text NOT NULL CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,membership_id,version),
          UNIQUE (organization_id,workspace_id,id_package_id,id_package_version,volume_book_id,volume_book_version,ordinal),
          FOREIGN KEY (organization_id,workspace_id,id_package_id,id_package_version)
            REFERENCES workspace.id_package_versions(organization_id,workspace_id,id_package_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,volume_book_id,volume_book_version)
            REFERENCES workspace.id_package_volume_book_versions(organization_id,workspace_id,volume_book_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,matrix_id,matrix_version)
            REFERENCES workspace.work_requirement_matrix_versions(organization_id,workspace_id,matrix_id,version) ON DELETE RESTRICT,
          CHECK ((role='register')=(ordinal=1)),
          CHECK ((document_requirement_id IS NULL)=(document_requirement_version IS NULL))
        );
        CREATE TABLE workspace.support_register_candidates (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          register_candidate_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          id_package_id uuid NOT NULL,
          id_package_version bigint NOT NULL,
          volume_book_id uuid NOT NULL,
          volume_book_version bigint NOT NULL,
          register_membership_id uuid NOT NULL,
          register_membership_version bigint NOT NULL,
          register_manifest jsonb NOT NULL,
          manifest_fingerprint text NOT NULL CHECK (manifest_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('structured_candidate','generated_candidate','finalized','blocked')),
          blocker_codes text[] NOT NULL,
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,register_candidate_id,version),
          UNIQUE (organization_id,workspace_id,id_package_id,id_package_version,volume_book_id,volume_book_version),
          FOREIGN KEY (organization_id,workspace_id,register_membership_id,register_membership_version)
            REFERENCES workspace.id_package_document_membership_versions(organization_id,workspace_id,membership_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.id_package_readiness_evaluations (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          evaluation_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          id_package_id uuid NOT NULL,
          id_package_version bigint NOT NULL,
          required_count integer NOT NULL CHECK (required_count>=0),
          covered_count integer NOT NULL CHECK (covered_count>=0),
          generated_candidate_count integer NOT NULL CHECK (generated_candidate_count>=0),
          finalized_count integer NOT NULL CHECK (finalized_count>=0),
          missing_count integer NOT NULL CHECK (missing_count>=0),
          conflict_count integer NOT NULL CHECK (conflict_count>=0),
          indeterminate_count integer NOT NULL CHECK (indeterminate_count>=0),
          blocked_count integer NOT NULL CHECK (blocked_count>=0),
          not_applicable_count integer NOT NULL CHECK (not_applicable_count>=0),
          blocker_codes text[] NOT NULL,
          status text NOT NULL CHECK (status IN ('ready','incomplete','blocked','indeterminate')),
          evaluation_fingerprint text NOT NULL CHECK (evaluation_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          evaluated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,evaluation_id,version),
          FOREIGN KEY (organization_id,workspace_id,id_package_id,id_package_version)
            REFERENCES workspace.id_package_versions(organization_id,workspace_id,id_package_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.support_generation_job_bindings (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          job_id uuid NOT NULL,
          generation_run_id uuid NOT NULL,
          membership_id uuid NOT NULL,
          membership_version bigint NOT NULL,
          template_id uuid NOT NULL,
          template_version text NOT NULL,
          semantic_input_digest text NOT NULL CHECK (semantic_input_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,job_id),
          UNIQUE (organization_id,workspace_id,generation_run_id),
          FOREIGN KEY (organization_id,workspace_id,job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,generation_run_id)
            REFERENCES workspace.support_generation_runs(organization_id,workspace_id,generation_run_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,membership_id,membership_version)
            REFERENCES workspace.id_package_document_membership_versions(organization_id,workspace_id,membership_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (template_id,template_version)
            REFERENCES platform.template_versions(template_id,version) ON DELETE RESTRICT
        );
        """
    )
    _security()
    _generation_security_bridge()


def _security() -> None:
    predicate = (
        "organization_id=nullif(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=nullif(current_setting('asd.workspace_id',true),'')::uuid"
    )
    op.execute(
        "GRANT SELECT ON platform.template_artifacts,platform.template_field_definitions,"
        "platform.required_document_type_templates,platform.required_document_types,"
        "platform.required_document_type_versions,platform.template_sources,"
        "platform.template_versions,platform.field_schema_versions "
        "TO asd_app,asd_document_worker,asd_support_service"
    )
    for table in WORKSPACE_TABLES:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_app_scope ON workspace.{table} FOR ALL TO asd_app "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_worker_scope ON workspace.{table} FOR ALL TO asd_document_worker "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_support_scope ON workspace.{table} FOR ALL TO asd_support_service "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_destruction_scope ON workspace.{table} FOR ALL TO asd_destruction_executor "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"GRANT SELECT,INSERT,UPDATE ON workspace.{table} TO asd_app,asd_document_worker"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_support_service")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE TRIGGER {table}_write_fence BEFORE INSERT OR UPDATE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION workspace.enforce_material_write_fence()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction()"
        )


def _generation_security_bridge() -> None:
    predicate = (
        "organization_id=nullif(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=nullif(current_setting('asd.workspace_id',true),'')::uuid"
    )
    app_write = (
        "support_generation_requests",
        "support_binding_plan_versions",
        "support_generation_runs",
        "support_generation_field_resolutions",
        "support_generation_evidence_bindings",
    )
    worker_write = (
        "support_generation_runs",
        "support_generated_document_candidates",
        "support_render_artifacts",
        "support_print_validation_results",
    )
    for role in ("asd_app", "asd_document_worker"):
        policy = (
            "id_package_versions_product_app_scope"
            if role == "asd_app"
            else "id_package_versions_product_worker_scope"
        )
        op.execute(
            f"CREATE POLICY {policy} ON workspace.id_package_versions FOR ALL TO {role} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.id_package_versions TO {role}")
    for table in (
        "support_processes",
        "support_scope_versions",
        "support_professional_grants",
    ):
        op.execute(
            f"CREATE POLICY {table}_product_app_read_scope ON workspace.{table} "
            f"FOR SELECT TO asd_app USING ({predicate})"
        )
        op.execute(f"GRANT SELECT ON workspace.{table} TO asd_app")
    for table in set((*app_write, *worker_write)):
        op.execute(
            f"CREATE POLICY {table}_product_app_scope ON workspace.{table} FOR ALL TO asd_app "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_product_worker_scope ON workspace.{table} FOR ALL TO asd_document_worker "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(f"GRANT SELECT ON workspace.{table} TO asd_app,asd_document_worker")
    for table in app_write:
        op.execute(f"GRANT INSERT ON workspace.{table} TO asd_app")
    for table in worker_write:
        op.execute(f"GRANT INSERT ON workspace.{table} TO asd_document_worker")
    op.execute(
        "DROP TRIGGER support_generation_runs_immutable_guard ON workspace.support_generation_runs"
    )
    op.execute(
        """
        CREATE FUNCTION workspace.guard_support_generation_run_progress()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member')
          THEN RETURN OLD; END IF;
          IF TG_OP<>'UPDATE' OR
             nullif(current_setting('asd.generation_operation_id',true),'') IS NULL THEN
            RAISE EXCEPTION 'generation progress requires a fenced operation';
          END IF;
          IF ROW(NEW.organization_id,NEW.workspace_id,NEW.generation_run_id,
                 NEW.generation_request_id,NEW.binding_plan_id,NEW.binding_plan_version,
                 NEW.renderer_profile_version,NEW.validator_profile_version,
                 NEW.input_fingerprint,NEW.fresh_document_instance,NEW.started_at)
             IS DISTINCT FROM
             ROW(OLD.organization_id,OLD.workspace_id,OLD.generation_run_id,
                 OLD.generation_request_id,OLD.binding_plan_id,OLD.binding_plan_version,
                 OLD.renderer_profile_version,OLD.validator_profile_version,
                 OLD.input_fingerprint,OLD.fresh_document_instance,OLD.started_at) THEN
            RAISE EXCEPTION 'generation immutable inputs cannot change';
          END IF;
          IF NOT ((OLD.status='planned' AND NEW.status IN ('resolving','rendering','blocked','failed')) OR
                  (OLD.status='resolving' AND NEW.status IN ('rendering','blocked','failed')) OR
                  (OLD.status='rendering' AND NEW.status IN ('validating','blocked','failed')) OR
                  (OLD.status='validating' AND NEW.status IN ('candidate_created','blocked','failed'))) THEN
            RAISE EXCEPTION 'invalid generation status transition';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER support_generation_runs_progress_guard
          BEFORE UPDATE OR DELETE ON workspace.support_generation_runs
          FOR EACH ROW EXECUTE FUNCTION workspace.guard_support_generation_run_progress();
        GRANT UPDATE (status,blocker_codes,completed_at)
          ON workspace.support_generation_runs TO asd_document_worker;
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("support production downgrade is allowed only in a disposable database")
    op.execute(
        "DROP TRIGGER support_generation_runs_progress_guard ON workspace.support_generation_runs"
    )
    op.execute("DROP FUNCTION workspace.guard_support_generation_run_progress()")
    op.execute(
        "CREATE TRIGGER support_generation_runs_immutable_guard BEFORE UPDATE OR DELETE "
        "ON workspace.support_generation_runs FOR EACH ROW EXECUTE FUNCTION "
        "workspace.reject_support_version_mutation()"
    )
    for table in (
        "support_generation_requests",
        "support_binding_plan_versions",
        "support_generation_runs",
        "support_generation_field_resolutions",
        "support_generation_evidence_bindings",
        "support_generated_document_candidates",
        "support_render_artifacts",
        "support_print_validation_results",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_product_app_scope ON workspace.{table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_product_worker_scope ON workspace.{table}")
    op.execute(
        "DROP POLICY IF EXISTS id_package_versions_product_app_scope "
        "ON workspace.id_package_versions"
    )
    op.execute(
        "DROP POLICY IF EXISTS id_package_versions_product_worker_scope "
        "ON workspace.id_package_versions"
    )
    for table in (
        "support_processes",
        "support_scope_versions",
        "support_professional_grants",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_product_app_read_scope ON workspace.{table}")
    for table in reversed(WORKSPACE_TABLES):
        op.execute(f"DROP TABLE workspace.{table}")
    op.execute("DROP TABLE platform.required_document_type_templates")
    op.execute("DROP TABLE platform.template_field_definitions")
    op.execute("DROP TABLE platform.template_artifacts")
    op.execute(
        "ALTER TABLE workspace.id_package_versions ALTER COLUMN rule_set_version_id SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE platform.template_versions DROP CONSTRAINT "
        "template_versions_assurance_class_check"
    )
    op.execute(
        "ALTER TABLE platform.template_versions ADD CONSTRAINT "
        "template_versions_assurance_class_check CHECK "
        "(assurance_class IN ('synthetic_development','production'))"
    )
    op.execute(
        "ALTER TABLE workspace.support_render_artifacts DROP CONSTRAINT "
        "support_render_artifacts_assurance_class_check"
    )
    op.execute(
        "ALTER TABLE workspace.support_render_artifacts ADD CONSTRAINT "
        "support_render_artifacts_assurance_class_check CHECK "
        "(assurance_class IN ('synthetic_structural_only','production_qualified'))"
    )
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check CHECK "
        f"(job_kind IN ({','.join(repr(value) for value in OLD_JOB_KINDS)}))"
    )
