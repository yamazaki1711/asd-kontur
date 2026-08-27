"""Add evidence-bound industrial document understanding.

Revision ID: 0021_document_understanding
Revises: 0020_knowledge_status
Create Date: 2026-08-26
"""

from __future__ import annotations

from alembic import op

revision = "0021_document_understanding"
down_revision = "0020_knowledge_status"
branch_labels = None
depends_on = None

WORKSPACE_TABLES = (
    "project_understanding_runs",
    "project_understanding_stage_results",
    "document_format_inventories",
    "document_page_health_versions",
    "native_layout_element_versions",
    "ocr_extraction_versions",
    "document_page_role_candidates",
    "document_role_decisions",
    "project_field_candidates",
    "project_field_decisions",
    "project_structure_node_versions",
    "work_type_candidates",
    "quantity_candidates",
    "material_candidates",
    "estimate_position_candidates",
    "source_cross_references",
    "project_reconciliation_defects",
    "project_understanding_reconciliations",
)

JOB_KINDS = (
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


def upgrade() -> None:
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    quoted = ",".join(f"'{value}'" for value in JOB_KINDS)
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        f"CHECK (job_kind IN ({quoted}))"
    )
    _create_platform_catalog_boundary()
    _create_workspace_relations()
    _create_projection()
    _apply_security()


def _create_platform_catalog_boundary() -> None:
    op.execute(
        """
        CREATE TABLE platform.work_type_catalog_versions (
          catalog_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          source_identity text NOT NULL,
          source_version text NOT NULL CHECK (lower(source_version) <> 'latest'),
          source_digest text NOT NULL CHECK (source_digest ~ '^sha256:[a-f0-9]{64}$'),
          provenance jsonb NOT NULL,
          status text NOT NULL CHECK (status IN ('candidate','verified','retired','blocked')),
          catalog_fingerprint text NOT NULL UNIQUE CHECK (catalog_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (catalog_id,version),
          UNIQUE (source_identity,source_version,source_digest)
        );
        CREATE TABLE platform.work_type_catalog_entries (
          catalog_id uuid NOT NULL,
          catalog_version bigint NOT NULL,
          work_type_id uuid NOT NULL,
          stable_key text NOT NULL,
          printed_name text NOT NULL,
          normalized_name text NOT NULL,
          aliases text[] NOT NULL,
          parent_work_type_id uuid,
          applicability jsonb NOT NULL,
          state text NOT NULL CHECK (state IN ('effective','retired')),
          provenance jsonb NOT NULL,
          semantic_digest text NOT NULL CHECK (semantic_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (catalog_id,catalog_version,work_type_id),
          UNIQUE (catalog_id,catalog_version,stable_key),
          UNIQUE (catalog_id,catalog_version,semantic_digest),
          FOREIGN KEY (catalog_id,catalog_version)
            REFERENCES platform.work_type_catalog_versions(catalog_id,version) ON DELETE RESTRICT
        );
        CREATE TRIGGER work_type_catalog_versions_immutable BEFORE UPDATE OR DELETE
          ON platform.work_type_catalog_versions FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();
        CREATE TRIGGER work_type_catalog_entries_immutable BEFORE UPDATE OR DELETE
          ON platform.work_type_catalog_entries FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();
        GRANT SELECT ON platform.work_type_catalog_versions,platform.work_type_catalog_entries
          TO asd_app,asd_document_worker,asd_harness_service;
        """
    )


def _create_workspace_relations() -> None:
    op.execute(
        """
        CREATE TABLE workspace.project_understanding_runs (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          run_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          corpus_manifest_digest text NOT NULL CHECK (corpus_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          state text NOT NULL CHECK (state IN ('assembling','partial','reconciled','failed','superseded')),
          source_version_ids uuid[] NOT NULL,
          structural_fingerprint text CHECK (structural_fingerprint IS NULL OR structural_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          gaps text[] NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,run_id,version),
          UNIQUE (organization_id,workspace_id,corpus_manifest_digest,profile_version),
          FOREIGN KEY (organization_id,workspace_id) REFERENCES
            workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.project_understanding_stage_results (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          stage_result_id uuid NOT NULL, job_id uuid NOT NULL,
          document_id uuid NOT NULL, document_version bigint NOT NULL,
          source_version_id uuid NOT NULL, stage_kind text NOT NULL,
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          input_digest text NOT NULL CHECK (input_digest ~ '^sha256:[a-f0-9]{64}$'),
          output_manifest jsonb NOT NULL,
          output_digest text NOT NULL CHECK (output_digest ~ '^sha256:[a-f0-9]{64}$'),
          terminal_status text NOT NULL CHECK (terminal_status IN ('complete','partial','gap','failed')),
          typed_failure_code text,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,stage_result_id),
          UNIQUE (organization_id,workspace_id,job_id),
          UNIQUE (organization_id,workspace_id,document_id,document_version,stage_kind,output_digest),
          FOREIGN KEY (organization_id,workspace_id,job_id)
            REFERENCES workspace.durable_jobs(organization_id,workspace_id,job_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,document_id,document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id)
            REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.document_format_inventories (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          inventory_id uuid NOT NULL, document_id uuid NOT NULL, document_version bigint NOT NULL,
          source_version_id uuid NOT NULL, media_type text NOT NULL, format_kind text NOT NULL,
          parser_key text NOT NULL, parser_version text NOT NULL CHECK (lower(parser_version) <> 'latest'),
          page_count bigint NOT NULL CHECK (page_count >= 1),
          capability_gaps text[] NOT NULL, inventory_digest text NOT NULL
            CHECK (inventory_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,inventory_id),
          UNIQUE (organization_id,workspace_id,document_id,document_version,inventory_digest),
          FOREIGN KEY (organization_id,workspace_id,document_id,document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.document_page_health_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          document_id uuid NOT NULL, document_version bigint NOT NULL, page_number bigint NOT NULL CHECK (page_number >= 1),
          health_version bigint NOT NULL CHECK (health_version >= 1), page_health_id uuid NOT NULL,
          primary_kind text NOT NULL, signals text[] NOT NULL,
          text_character_count bigint NOT NULL CHECK (text_character_count >= 0),
          replacement_character_ratio numeric NOT NULL CHECK (replacement_character_ratio BETWEEN 0 AND 1),
          image_count bigint NOT NULL CHECK (image_count >= 0), rotation_degrees integer NOT NULL,
          width_points numeric NOT NULL CHECK (width_points > 0), height_points numeric NOT NULL CHECK (height_points > 0),
          ocr_route text NOT NULL, profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,document_id,document_version,page_number,health_version),
          UNIQUE (organization_id,workspace_id,page_health_id),
          UNIQUE (organization_id,workspace_id,fingerprint),
          FOREIGN KEY (organization_id,workspace_id,document_id,document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.native_layout_element_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          element_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          document_id uuid NOT NULL, document_version bigint NOT NULL, source_version_id uuid NOT NULL,
          source_locator_id uuid NOT NULL, page_number bigint NOT NULL CHECK (page_number >= 1),
          element_kind text NOT NULL, raw_text text NOT NULL, normalized_text text NOT NULL,
          reading_order bigint NOT NULL CHECK (reading_order >= 1), region jsonb NOT NULL,
          cell_locator text, row_index bigint, column_index bigint,
          evidence_digest text NOT NULL CHECK (evidence_digest ~ '^sha256:[a-f0-9]{64}$'),
          extraction_method text NOT NULL, profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          semantic_digest text NOT NULL CHECK (semantic_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,element_id,version),
          UNIQUE (organization_id,workspace_id,semantic_digest),
          FOREIGN KEY (organization_id,workspace_id,document_id,document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id)
            REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.ocr_extraction_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          ocr_extraction_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          document_id uuid NOT NULL, document_version bigint NOT NULL, page_number bigint NOT NULL,
          source_version_id uuid NOT NULL, source_image_digest text NOT NULL,
          adapter_key text NOT NULL, adapter_version text NOT NULL CHECK (lower(adapter_version) <> 'latest'),
          language_profile text NOT NULL, output_digest text NOT NULL CHECK (output_digest ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('complete','insufficient','failed','not_required')),
          failure_code text, recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,ocr_extraction_id,version),
          UNIQUE (organization_id,workspace_id,document_id,document_version,page_number,adapter_key,output_digest),
          FOREIGN KEY (organization_id,workspace_id,document_id,document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.document_page_role_candidates (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          candidate_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          document_id uuid NOT NULL, document_version bigint NOT NULL, scope text NOT NULL,
          role text NOT NULL, score numeric NOT NULL CHECK (score BETWEEN 0 AND 1),
          signal_codes text[] NOT NULL, source_locator_ids uuid[] NOT NULL,
          extraction_profile_version text NOT NULL CHECK (lower(extraction_profile_version) <> 'latest'),
          model_attempt_id uuid, candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,candidate_id,version),
          UNIQUE (organization_id,workspace_id,candidate_digest),
          FOREIGN KEY (organization_id,workspace_id,document_id,document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.document_role_decisions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          decision_id uuid NOT NULL, decision_version bigint NOT NULL CHECK (decision_version >= 1),
          document_id uuid NOT NULL, document_version bigint NOT NULL, scope text NOT NULL,
          selected_roles text[] NOT NULL, candidate_ids uuid[] NOT NULL, decision_code text NOT NULL,
          validator_version text NOT NULL CHECK (lower(validator_version) <> 'latest'),
          source_locator_ids uuid[] NOT NULL, decision_digest text NOT NULL CHECK (decision_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,decision_id,decision_version),
          UNIQUE (organization_id,workspace_id,decision_digest),
          FOREIGN KEY (organization_id,workspace_id,document_id,document_version)
            REFERENCES workspace.document_versions(organization_id,workspace_id,document_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.project_field_candidates (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          candidate_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          field_key text NOT NULL, raw_value text NOT NULL, normalized_value jsonb NOT NULL,
          value_type text NOT NULL, source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL,
          extraction_method text NOT NULL, confidence numeric, uncertainty_codes text[] NOT NULL,
          conflicts text[] NOT NULL DEFAULT '{}', status text NOT NULL,
          extraction_profile_version text NOT NULL CHECK (lower(extraction_profile_version) <> 'latest'),
          candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,candidate_id,version),
          UNIQUE (organization_id,workspace_id,candidate_digest),
          FOREIGN KEY (organization_id,workspace_id,source_locator_id)
            REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.project_field_decisions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          decision_id uuid NOT NULL, decision_version bigint NOT NULL CHECK (decision_version >= 1),
          field_key text NOT NULL, selected_candidate_id uuid, selected_candidate_version bigint,
          status text NOT NULL CHECK (status IN ('verified','rejected','gap','conflict','superseded')),
          validation_profile_version text NOT NULL CHECK (lower(validation_profile_version) <> 'latest'),
          decision_receipt_digest text NOT NULL CHECK (decision_receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          supersedes_decision_version bigint, recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,decision_id,decision_version),
          FOREIGN KEY (organization_id,workspace_id,selected_candidate_id,selected_candidate_version)
            REFERENCES workspace.project_field_candidates(organization_id,workspace_id,candidate_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.project_structure_node_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          structure_node_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          node_kind text NOT NULL, raw_name text NOT NULL, normalized_name text NOT NULL,
          parent_node_id uuid, source_locator_id uuid NOT NULL, status text NOT NULL,
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,structure_node_id,version),
          UNIQUE (organization_id,workspace_id,fingerprint),
          FOREIGN KEY (organization_id,workspace_id,source_locator_id)
            REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT
        );
        """
    )
    _create_work_candidate_relations()


def _create_work_candidate_relations() -> None:
    op.execute(
        """
        CREATE TABLE workspace.work_type_candidates (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          candidate_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          raw_name text NOT NULL, normalized_name text NOT NULL, scope_key text NOT NULL,
          source_role text NOT NULL, source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL,
          canonical_mapping_status text NOT NULL CHECK (canonical_mapping_status IN ('resolved','unresolved','ambiguous')),
          canonical_work_type_id uuid, extraction_profile_version text NOT NULL,
          candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,candidate_id,version),
          UNIQUE (organization_id,workspace_id,candidate_digest),
          FOREIGN KEY (organization_id,workspace_id,source_locator_id)
            REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.quantity_candidates (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          candidate_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          work_candidate_id uuid NOT NULL, work_candidate_version bigint NOT NULL,
          raw_value text NOT NULL, parsed_value numeric, raw_unit text NOT NULL,
          normalized_value numeric, normalized_unit text, conversion_rule_version text,
          scope_key text NOT NULL, source_locator_id uuid NOT NULL, status text NOT NULL,
          candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,candidate_id,version),
          UNIQUE (organization_id,workspace_id,candidate_digest),
          FOREIGN KEY (organization_id,workspace_id,work_candidate_id,work_candidate_version)
            REFERENCES workspace.work_type_candidates(organization_id,workspace_id,candidate_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id)
            REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.material_candidates (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          candidate_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          work_candidate_id uuid NOT NULL, work_candidate_version bigint NOT NULL,
          raw_name text NOT NULL, normalized_name text NOT NULL, raw_quantity text,
          parsed_quantity numeric, raw_unit text, normalized_unit text,
          source_locator_id uuid NOT NULL, status text NOT NULL,
          candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,candidate_id,version),
          UNIQUE (organization_id,workspace_id,candidate_digest),
          FOREIGN KEY (organization_id,workspace_id,work_candidate_id,work_candidate_version)
            REFERENCES workspace.work_type_candidates(organization_id,workspace_id,candidate_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id)
            REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.estimate_position_candidates (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          candidate_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          raw_position text NOT NULL, normalized_description text NOT NULL,
          raw_quantity text, parsed_quantity numeric, raw_unit text,
          source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL,
          candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,candidate_id,version),
          UNIQUE (organization_id,workspace_id,candidate_digest),
          FOREIGN KEY (organization_id,workspace_id,source_locator_id)
            REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.source_cross_references (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          cross_reference_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          source_identity text NOT NULL, target_identity text NOT NULL,
          relation_kind text NOT NULL, source_locator_ids uuid[] NOT NULL,
          status text NOT NULL CHECK (status IN ('resolved','unresolved','ambiguous','conflict')),
          fingerprint text NOT NULL CHECK (fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,cross_reference_id,version),
          UNIQUE (organization_id,workspace_id,fingerprint)
        );
        CREATE TABLE workspace.project_reconciliation_defects (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          defect_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          defect_kind text NOT NULL, subject_identity text NOT NULL, related_identity text,
          source_locator_ids uuid[] NOT NULL, parameters jsonb NOT NULL,
          blocking boolean NOT NULL, status text NOT NULL CHECK (status IN ('open','resolved','superseded')),
          defect_digest text NOT NULL CHECK (defect_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,defect_id,version),
          UNIQUE (organization_id,workspace_id,defect_digest)
        );
        CREATE TABLE workspace.project_understanding_reconciliations (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          reconciliation_id uuid NOT NULL, version bigint NOT NULL CHECK (version >= 1),
          run_id uuid NOT NULL, run_version bigint NOT NULL,
          project_definition_id uuid, project_definition_version bigint,
          matrix_id uuid, matrix_version bigint,
          source_count bigint NOT NULL, page_count bigint NOT NULL,
          accepted_candidate_count bigint NOT NULL, unresolved_candidate_count bigint NOT NULL,
          open_defect_count bigint NOT NULL, gaps text[] NOT NULL,
          structural_fingerprint text NOT NULL CHECK (structural_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          terminal_status text NOT NULL CHECK (terminal_status IN ('complete','partial','failed')),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (organization_id,workspace_id,reconciliation_id,version),
          UNIQUE (organization_id,workspace_id,structural_fingerprint),
          FOREIGN KEY (organization_id,workspace_id,run_id,run_version)
            REFERENCES workspace.project_understanding_runs(organization_id,workspace_id,run_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,project_definition_id,project_definition_version)
            REFERENCES workspace.project_definition_versions(organization_id,workspace_id,project_definition_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,matrix_id,matrix_version)
            REFERENCES workspace.work_requirement_matrix_versions(organization_id,workspace_id,matrix_id,version) ON DELETE RESTRICT,
          CHECK ((project_definition_id IS NULL) = (project_definition_version IS NULL)),
          CHECK ((matrix_id IS NULL) = (matrix_version IS NULL))
        );
        """
    )


def _create_projection() -> None:
    op.execute(
        """
        CREATE TABLE projection.project_understanding_entries (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          run_id uuid NOT NULL, run_version bigint NOT NULL,
          entry_kind text NOT NULL, entry_identity text NOT NULL,
          source_locator_ids uuid[] NOT NULL, entry jsonb NOT NULL,
          projection_profile_version text NOT NULL CHECK (lower(projection_profile_version) <> 'latest'),
          entry_fingerprint text NOT NULL CHECK (entry_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,run_id,run_version,entry_kind,entry_identity)
        );
        """
    )


def _apply_security() -> None:
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
        op.execute(f"GRANT SELECT ON workspace.{table} TO asd_app")
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_document_worker")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction()"
        )
    op.execute("ALTER TABLE projection.project_understanding_entries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE projection.project_understanding_entries FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY project_understanding_entries_scope ON projection.project_understanding_entries "
        "USING (organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) WITH CHECK ("
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute("GRANT SELECT ON projection.project_understanding_entries TO asd_app")
    op.execute(
        "GRANT SELECT,INSERT,DELETE ON projection.project_understanding_entries TO asd_document_worker"
    )
    op.execute(
        "GRANT SELECT,DELETE ON projection.project_understanding_entries TO asd_destruction_executor"
    )
    for table in (
        "project_definition_versions",
        "construction_work_package_versions",
        "work_requirement_matrix_versions",
    ):
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_document_worker")
        op.execute(
            f"CREATE POLICY {table}_document_understanding_scope ON workspace.{table} "
            "FOR ALL TO asd_document_worker USING ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
            "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) WITH CHECK ("
            "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
            "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
        )


def downgrade() -> None:
    for table in (
        "project_definition_versions",
        "construction_work_package_versions",
        "work_requirement_matrix_versions",
    ):
        op.execute(
            f"DROP POLICY IF EXISTS {table}_document_understanding_scope ON workspace.{table}"
        )
        op.execute(f"REVOKE SELECT,INSERT ON workspace.{table} FROM asd_document_worker")
    op.execute("DROP TABLE projection.project_understanding_entries")
    for table in reversed(WORKSPACE_TABLES):
        op.execute(f"DROP TABLE workspace.{table}")
    op.execute("DROP TABLE platform.work_type_catalog_entries")
    op.execute("DROP TABLE platform.work_type_catalog_versions")
    op.execute("ALTER TABLE workspace.durable_jobs DROP CONSTRAINT durable_jobs_job_kind_check")
    old = (*JOB_KINDS[:4], "EVIDENCE_INDEX_UPDATE", "WORKSPACE_RESET_RECONCILIATION")
    quoted = ",".join(f"'{value}'" for value in old)
    op.execute(
        "ALTER TABLE workspace.durable_jobs ADD CONSTRAINT durable_jobs_job_kind_check "
        f"CHECK (job_kind IN ({quoted}))"
    )
