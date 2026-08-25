"""Add the unified construction harness workspace process layer.

Revision ID: 0017_unified_harness
Revises: 0016_ntd_seed
"""

from __future__ import annotations

import os

from alembic import op

revision = "0017_unified_harness"
down_revision = "0016_ntd_seed"
branch_labels = None
depends_on = None

WORKSPACE_TABLES = (
    "project_definition_versions",
    "project_characteristic_candidates",
    "verified_project_characteristics",
    "construction_work_package_versions",
    "work_requirement_matrix_versions",
    "customer_regulation_additions",
    "construction_harness_context_packs",
    "knowledge_consistency_defects",
    "construction_harness_mode_views",
    "construction_harness_backup_manifests",
)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_harness_service') "
        "THEN CREATE ROLE asd_harness_service NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        "NOINHERIT; END IF; END $$"
    )
    op.execute(
        """
        CREATE TABLE workspace.project_definition_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          project_definition_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          purpose text NOT NULL, object_class text NOT NULL,
          source_version_ids uuid[] NOT NULL CHECK (cardinality(source_version_ids)>0),
          definition jsonb NOT NULL,
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,project_definition_id,version),
          FOREIGN KEY (organization_id,workspace_id) REFERENCES
            workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,fingerprint)
        );
        CREATE TABLE workspace.project_characteristic_candidates (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          candidate_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          project_definition_id uuid NOT NULL, project_definition_version bigint NOT NULL,
          characteristic_key text NOT NULL, candidate_value jsonb NOT NULL,
          extraction_profile_version text NOT NULL CHECK (lower(extraction_profile_version)<>'latest'),
          source_version_id uuid NOT NULL, source_locator text NOT NULL,
          evidence_link_id uuid NOT NULL, content_digest text NOT NULL
            CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('candidate','rejected','needs_evidence')),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,candidate_id,version),
          FOREIGN KEY (organization_id,workspace_id,project_definition_id,project_definition_version)
            REFERENCES workspace.project_definition_versions
              (organization_id,workspace_id,project_definition_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.verified_project_characteristics (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          characteristic_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          candidate_id uuid NOT NULL, candidate_version bigint NOT NULL,
          characteristic_key text NOT NULL, verified_value jsonb NOT NULL,
          validation_profile_version text NOT NULL CHECK (lower(validation_profile_version)<>'latest'),
          validation_receipt_digest text NOT NULL
            CHECK (validation_receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          source_version_id uuid NOT NULL, source_locator text NOT NULL,
          evidence_link_id uuid NOT NULL, created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,characteristic_id,version),
          FOREIGN KEY (organization_id,workspace_id,candidate_id,candidate_version)
            REFERENCES workspace.project_characteristic_candidates
              (organization_id,workspace_id,candidate_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.construction_work_package_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          work_package_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          project_definition_id uuid NOT NULL, project_definition_version bigint NOT NULL,
          work_type_key text NOT NULL, work_type_version text NOT NULL
            CHECK (lower(work_type_version)<>'latest'), package jsonb NOT NULL,
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,work_package_id,version),
          FOREIGN KEY (organization_id,workspace_id,project_definition_id,project_definition_version)
            REFERENCES workspace.project_definition_versions
              (organization_id,workspace_id,project_definition_id,version) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,fingerprint)
        );
        CREATE TABLE workspace.work_requirement_matrix_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          matrix_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          project_definition_id uuid NOT NULL, project_definition_version bigint NOT NULL,
          rule_set_version_id uuid,
          matrix jsonb NOT NULL,
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,matrix_id,version),
          FOREIGN KEY (organization_id,workspace_id,project_definition_id,project_definition_version)
            REFERENCES workspace.project_definition_versions
              (organization_id,workspace_id,project_definition_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (rule_set_version_id) REFERENCES platform.rule_set_versions(rule_set_version_id)
            ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,fingerprint)
        );
        CREATE TABLE workspace.customer_regulation_additions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          addition_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          matrix_id uuid NOT NULL, matrix_version bigint NOT NULL,
          document_requirement_id uuid NOT NULL,
          target_authority_status text NOT NULL CHECK (target_authority_status='normative_verified'),
          additional_copies integer NOT NULL CHECK (additional_copies>=0),
          additional_evidence_kinds text[] NOT NULL,
          source_version_id uuid NOT NULL, source_locator text NOT NULL,
          evidence_link_id uuid NOT NULL, created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,addition_id,version),
          FOREIGN KEY (organization_id,workspace_id,matrix_id,matrix_version)
            REFERENCES workspace.work_requirement_matrix_versions
              (organization_id,workspace_id,matrix_id,version) ON DELETE RESTRICT,
          CHECK (additional_copies>0 OR cardinality(additional_evidence_kinds)>0)
        );
        CREATE TABLE workspace.construction_harness_context_packs (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          context_pack_id uuid NOT NULL, contract_version text NOT NULL
            CHECK (contract_version='1.8.0'),
          project_definition_id uuid NOT NULL, project_definition_version bigint NOT NULL,
          matrix_id uuid NOT NULL, matrix_version bigint NOT NULL,
          matrix_fingerprint text NOT NULL CHECK (matrix_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          context_pack jsonb NOT NULL,
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          assembled_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,context_pack_id),
          FOREIGN KEY (organization_id,workspace_id,project_definition_id,project_definition_version)
            REFERENCES workspace.project_definition_versions
              (organization_id,workspace_id,project_definition_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,matrix_id,matrix_version)
            REFERENCES workspace.work_requirement_matrix_versions
              (organization_id,workspace_id,matrix_id,version) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,fingerprint)
        );
        CREATE TABLE workspace.knowledge_consistency_defects (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          defect_id uuid NOT NULL, code text NOT NULL, affected_reference text NOT NULL,
          evidence_refs text[] NOT NULL, blocking_rule_version_ids uuid[] NOT NULL,
          status text NOT NULL CHECK (status IN ('open','resolved','superseded')),
          detected_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,defect_id)
        );
        CREATE TABLE workspace.construction_harness_mode_views (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          mode_view_id uuid NOT NULL, mode text NOT NULL
            CHECK (mode IN ('Tender','Support','Audit','Restoration')),
          matrix_id uuid NOT NULL, matrix_version bigint NOT NULL,
          matrix_fingerprint text NOT NULL CHECK (matrix_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          result jsonb NOT NULL, result_fingerprint text NOT NULL
            CHECK (result_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,mode_view_id),
          FOREIGN KEY (organization_id,workspace_id,matrix_id,matrix_version)
            REFERENCES workspace.work_requirement_matrix_versions
              (organization_id,workspace_id,matrix_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.construction_harness_backup_manifests (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          backup_manifest_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          project_definition_fingerprint text NOT NULL,
          matrix_fingerprint text NOT NULL, context_pack_fingerprint text NOT NULL,
          platform_memory_fingerprints text[] NOT NULL,
          projection_profile_version text NOT NULL CHECK (lower(projection_profile_version)<>'latest'),
          semantic_fingerprint text NOT NULL CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,backup_manifest_id,version)
        );
        CREATE TABLE projection.construction_harness_matrix_entries (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          matrix_id uuid NOT NULL, matrix_version bigint NOT NULL,
          work_package_id uuid NOT NULL, matrix_fingerprint text NOT NULL,
          projection_profile_version text NOT NULL CHECK (lower(projection_profile_version)<>'latest'),
          entry jsonb NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,matrix_id,matrix_version,work_package_id)
        );
        ALTER TABLE workspace.vlm_execution_requests
          ADD COLUMN base_context_pack_id uuid,
          ADD CONSTRAINT vlm_execution_requests_base_context_pack_fk
            FOREIGN KEY (organization_id,workspace_id,base_context_pack_id)
            REFERENCES workspace.construction_harness_context_packs
              (organization_id,workspace_id,context_pack_id) ON DELETE RESTRICT,
          ADD CONSTRAINT vlm_execution_requests_mandatory_construction_context_ck
            CHECK (
              (purpose NOT LIKE 'id.%' AND purpose NOT LIKE 'construction.%')
              OR base_context_pack_id IS NOT NULL
            ) NOT VALID;
        """
    )
    op.execute(
        """
        CREATE FUNCTION workspace.enforce_customer_regulation_additive()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM workspace.work_requirement_matrix_versions m,
                 jsonb_array_elements(m.matrix->'rows') row_value,
                 jsonb_array_elements(row_value->'documents') document_value
            WHERE m.organization_id=NEW.organization_id
              AND m.workspace_id=NEW.workspace_id
              AND m.matrix_id=NEW.matrix_id
              AND m.version=NEW.matrix_version
              AND document_value->>'document_requirement_id'=NEW.document_requirement_id::text
              AND document_value->>'authority_status'='normative_verified'
          ) THEN
            RAISE EXCEPTION 'customer regulation requires exact verified normative minimum'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_customer_regulation_additive
          BEFORE INSERT ON workspace.customer_regulation_additions
          FOR EACH ROW EXECUTE FUNCTION workspace.enforce_customer_regulation_additive();
        """
    )
    predicate = (
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid"
    )
    op.execute("GRANT USAGE ON SCHEMA workspace,platform TO asd_harness_service")
    op.execute(
        "GRANT SELECT ON platform.practice_guide_editions,platform.practice_guidance_units,"
        "platform.practice_playbooks,platform.normative_editions,"
        "platform.normative_provision_versions,platform.rule_versions,"
        "platform.rule_version_states,platform.rule_set_versions,platform.ntd_gaps "
        "TO asd_harness_service"
    )
    for table in WORKSPACE_TABLES:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_harness_scope_policy ON workspace.{table} "
            f"FOR ALL TO asd_harness_service USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_app_scope_policy ON workspace.{table} "
            f"FOR SELECT TO asd_app USING ({predicate})"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_harness_service")
        op.execute(f"GRANT SELECT ON workspace.{table} TO asd_app")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE POLICY {table}_destruction_scope_policy ON workspace.{table} "
            f"FOR ALL TO asd_destruction_executor USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE "
            f"ON workspace.{table} FOR EACH ROW EXECUTE FUNCTION "
            "workspace.reject_workspace_immutable_unless_destroy()"
        )
    op.execute(
        "GRANT USAGE ON SCHEMA projection TO asd_projection_builder,asd_destruction_executor"
    )
    op.execute(
        "ALTER TABLE projection.construction_harness_matrix_entries ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE projection.construction_harness_matrix_entries FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "CREATE POLICY construction_harness_projection_builder_scope_policy ON "
        "projection.construction_harness_matrix_entries FOR ALL TO asd_projection_builder "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(
        "CREATE POLICY construction_harness_projection_destruction_scope_policy ON "
        "projection.construction_harness_matrix_entries FOR ALL TO asd_destruction_executor "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE,DELETE ON projection.construction_harness_matrix_entries "
        "TO asd_projection_builder"
    )
    op.execute(
        "GRANT SELECT,DELETE ON projection.construction_harness_matrix_entries "
        "TO asd_destruction_executor"
    )
    op.execute(
        "GRANT SELECT ON workspace.work_requirement_matrix_versions TO asd_projection_builder"
    )
    op.execute(
        "CREATE POLICY work_requirement_matrix_projection_scope_policy ON "
        "workspace.work_requirement_matrix_versions FOR SELECT TO asd_projection_builder "
        f"USING ({predicate})"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Harness downgrade requires an explicitly disposable database")
    op.execute(
        "ALTER TABLE workspace.vlm_execution_requests "
        "DROP CONSTRAINT vlm_execution_requests_mandatory_construction_context_ck, "
        "DROP CONSTRAINT vlm_execution_requests_base_context_pack_fk, "
        "DROP COLUMN base_context_pack_id"
    )
    op.execute("DROP TABLE projection.construction_harness_matrix_entries")
    for table in reversed(WORKSPACE_TABLES):
        op.execute(f"DROP TABLE workspace.{table}")
    op.execute("DROP FUNCTION workspace.enforce_customer_regulation_additive()")
    # asd_harness_service is owned by the earlier G-07 migration and remains shared.
