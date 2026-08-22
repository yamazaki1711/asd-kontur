"""Create the WP-11 common domain process kernel.

Revision ID: 0005_wp11
Revises: 0004_g07
Create Date: 2026-08-23
"""

from __future__ import annotations

import os

from alembic import op

revision = "0005_wp11"
down_revision = "0004_g07"
branch_labels = None
depends_on = None

PLATFORM_TABLES = (
    "work_type_versions",
    "work_types",
    "material_class_versions",
    "material_classes",
    "required_document_type_versions",
    "required_document_types",
    "confirmation_policy_versions",
)

KERNEL_READ_TABLES = (
    "workspaces",
    "mode_executions",
    "source_versions",
    "source_locators",
    "evidence_links",
    "candidate_versions",
    "candidate_fields",
    "candidate_field_evidence",
    "vlm_validation_runs",
    "vlm_validation_failures",
    "rule_evaluations",
    "rule_traces",
)

G05_IMMUTABLE_WORKSPACE_TABLES = (
    "source_object_receipts",
    "source_versions",
    "source_locators",
    "evidence_links",
    "rule_versions",
    "rule_version_states",
    "rule_evidence",
    "rule_evaluations",
    "rule_traces",
    "promotion_anonymization_results",
    "promotion_regression_results",
    "promotion_decisions",
)

WORKSPACE_TABLES = (
    "confirmation_authority_grants",
    "confirmation_decisions",
    "workspace_facts",
    "workspace_fact_versions",
    "workspace_fact_evidence",
    "kernel_process_instances",
    "mode_kernel_bindings",
    "construction_structure_versions",
    "construction_element_versions",
    "work_instance_versions",
    "work_dependencies",
    "work_volume_versions",
    "material_requirement_versions",
    "material_batch_versions",
    "material_applications",
    "control_operation_versions",
    "evidence_requirement_versions",
    "document_requirement_versions",
    "document_coverages",
    "id_package_versions",
    "id_package_items",
    "presented_volume_versions",
    "ks_document_versions",
    "ks_line_versions",
    "payment_claim_versions",
    "kernel_issue_versions",
    "kernel_finding_versions",
    "deliverable_inputs",
)

MUTABLE_HEADERS = ("workspace_facts", "kernel_process_instances")


def upgrade() -> None:
    _create_role()
    _create_platform_definitions()
    _create_fact_authority_boundary()
    _create_common_chain()
    _apply_guards_grants_and_rls()


def _create_role() -> None:
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_kernel_service') "
        "THEN CREATE ROLE asd_kernel_service NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; "
        "END IF; END $$"
    )


def _create_platform_definitions() -> None:
    op.execute(
        """
        CREATE TABLE platform.work_types (
          work_type_id uuid PRIMARY KEY,
          work_type_key text NOT NULL UNIQUE,
          identity_namespace_version text NOT NULL CHECK (lower(identity_namespace_version)<>'latest'),
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE platform.work_type_versions (
          work_type_id uuid NOT NULL REFERENCES platform.work_types(work_type_id) ON DELETE RESTRICT,
          version text NOT NULL CHECK (lower(version)<>'latest'),
          taxonomy_version text NOT NULL CHECK (lower(taxonomy_version)<>'latest'),
          title text NOT NULL,
          status text NOT NULL CHECK (status IN ('draft','active','suspended','superseded','retired')),
          evidence_manifest_digest text NOT NULL CHECK (evidence_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          effective_from date,
          effective_to date,
          PRIMARY KEY (work_type_id,version),
          CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to>effective_from)
        );
        CREATE TABLE platform.material_classes (
          material_class_id uuid PRIMARY KEY,
          material_key text NOT NULL UNIQUE,
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE platform.material_class_versions (
          material_class_id uuid NOT NULL REFERENCES platform.material_classes(material_class_id) ON DELETE RESTRICT,
          version text NOT NULL CHECK (lower(version)<>'latest'),
          classifier_version text NOT NULL CHECK (lower(classifier_version)<>'latest'),
          title text NOT NULL,
          status text NOT NULL CHECK (status IN ('draft','active','suspended','superseded','retired')),
          evidence_manifest_digest text NOT NULL CHECK (evidence_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (material_class_id,version)
        );
        CREATE TABLE platform.required_document_types (
          required_document_type_id uuid PRIMARY KEY,
          document_type_key text NOT NULL UNIQUE,
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE platform.required_document_type_versions (
          required_document_type_id uuid NOT NULL REFERENCES platform.required_document_types(required_document_type_id) ON DELETE RESTRICT,
          version text NOT NULL CHECK (lower(version)<>'latest'),
          purpose text NOT NULL,
          format_family text NOT NULL CHECK (format_family IN ('DOCX','XLSX','PDF_FILLABLE','PDF_NON_FILLABLE','DXF','SVG','PDF_GEOMETRY','OTHER')),
          status text NOT NULL CHECK (status IN ('draft','active','suspended','superseded','retired')),
          applicability_rule_version_id uuid NOT NULL REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (required_document_type_id,version)
        );
        CREATE TABLE platform.confirmation_policy_versions (
          confirmation_policy_id uuid NOT NULL,
          version text NOT NULL CHECK (lower(version)<>'latest'),
          policy_key text NOT NULL,
          environment text NOT NULL CHECK (environment IN ('development','qualification','production')),
          auto_confirm_fact_classes text[] NOT NULL,
          professional_fact_classes text[] NOT NULL,
          validator_profile_version text NOT NULL CHECK (lower(validator_profile_version)<>'latest'),
          status text NOT NULL CHECK (status IN ('draft','active','suspended','superseded','retired','unset','blocked')),
          approved_by_identity_id text,
          effective_from timestamptz NOT NULL,
          effective_until timestamptz,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (confirmation_policy_id,version),
          UNIQUE (policy_key,version),
          CHECK (environment<>'production' OR status<>'active' OR approved_by_identity_id IS NOT NULL),
          CHECK (NOT auto_confirm_fact_classes && professional_fact_classes)
        );
        """
    )
    for table in PLATFORM_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON platform.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )


def _create_fact_authority_boundary() -> None:
    op.execute(
        """
        CREATE TABLE workspace.confirmation_authority_grants (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL,
          grant_id uuid NOT NULL, grant_version bigint NOT NULL CHECK (grant_version>=1),
          human_identity_id text NOT NULL CHECK (human_identity_id !~ '^(model|service|integration):'),
          capability text NOT NULL CHECK (capability='fact.confirm'),
          fact_classes text[] NOT NULL CHECK (cardinality(fact_classes)>0),
          professional_qualification_ref text,
          status text NOT NULL CHECK (status IN ('active','suspended','revoked','expired')),
          effective_from timestamptz NOT NULL, effective_until timestamptz,
          authority_reference text NOT NULL,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,grant_id,grant_version),
          FOREIGN KEY (organization_id,workspace_id) REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT,
          CHECK (effective_until IS NULL OR effective_until>effective_from),
          CHECK (NOT fact_classes && ARRAY['legal_effect','contractual_obligation','geometry','measurement','payable_volume','signer_authority','material_blocker','professional_finalization']::text[]
                 OR professional_qualification_ref IS NOT NULL)
        );
        CREATE TABLE workspace.confirmation_decisions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, confirmation_decision_id uuid NOT NULL,
          candidate_id uuid NOT NULL, candidate_version integer NOT NULL, field_path text NOT NULL CHECK (field_path LIKE '/%'),
          validation_run_id uuid NOT NULL, fact_class text NOT NULL CHECK (fact_class IN ('observation','classification','legal_effect','contractual_obligation','geometry','measurement','payable_volume','signer_authority','material_blocker','professional_finalization')),
          outcome text NOT NULL CHECK (outcome IN ('confirmed','rejected','needs_evidence','conflict')),
          authority_kind text NOT NULL CHECK (authority_kind IN ('qualified_human','deterministic_rule')),
          actor_identity_id text, service_identity_id text,
          grant_id uuid, grant_version bigint,
          confirmation_policy_id uuid NOT NULL, confirmation_policy_version text NOT NULL,
          rule_set_version_id uuid, rule_version_id uuid, rule_evaluation_id uuid, rule_trace_id uuid,
          authority_reference text NOT NULL, reason_code text NOT NULL,
          decision_fingerprint text NOT NULL CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          correlation_id uuid NOT NULL, causation_id uuid NOT NULL, decided_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,confirmation_decision_id),
          UNIQUE (organization_id,workspace_id,candidate_id,candidate_version,field_path,confirmation_decision_id),
          FOREIGN KEY (organization_id,workspace_id,candidate_id,candidate_version,field_path)
            REFERENCES workspace.candidate_fields(organization_id,workspace_id,candidate_id,candidate_version,field_path) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,validation_run_id)
            REFERENCES workspace.vlm_validation_runs(organization_id,workspace_id,validation_run_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,grant_id,grant_version)
            REFERENCES workspace.confirmation_authority_grants(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT,
          FOREIGN KEY (confirmation_policy_id,confirmation_policy_version)
            REFERENCES platform.confirmation_policy_versions(confirmation_policy_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (rule_set_version_id) REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (rule_version_id) REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_evaluation_id)
            REFERENCES workspace.rule_evaluations(organization_id,workspace_id,rule_evaluation_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id)
            REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK ((authority_kind='qualified_human' AND actor_identity_id IS NOT NULL AND actor_identity_id !~ '^(model|service|integration):' AND grant_id IS NOT NULL AND service_identity_id IS NULL)
              OR (authority_kind='deterministic_rule' AND actor_identity_id IS NULL AND service_identity_id IS NOT NULL AND grant_id IS NULL AND rule_set_version_id IS NOT NULL AND rule_version_id IS NOT NULL AND rule_evaluation_id IS NOT NULL AND rule_trace_id IS NOT NULL))
        );
        CREATE TABLE workspace.workspace_facts (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, fact_id uuid NOT NULL,
          fact_type text NOT NULL CHECK (length(fact_type)>0),
          fact_class text NOT NULL CHECK (fact_class IN ('observation','classification','legal_effect','contractual_obligation','geometry','measurement','payable_volume','signer_authority','material_blocker','professional_finalization')),
          current_version bigint NOT NULL CHECK (current_version>=1), revision bigint NOT NULL CHECK (revision>=1),
          retention_class text NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,fact_id),
          FOREIGN KEY (organization_id,workspace_id) REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.workspace_fact_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, fact_id uuid NOT NULL,
          fact_version bigint NOT NULL CHECK (fact_version>=1), value_kind text NOT NULL CHECK (value_kind IN ('text','boolean','decimal_quantity','date','reference','measurement')),
          text_value text, boolean_value boolean, numeric_value numeric, date_value date, reference_value uuid,
          unit_code text, precision_scale integer CHECK (precision_scale IS NULL OR precision_scale>=0),
          rounding_policy_version text, crs_reference text, measurement_authority_ref text,
          source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL,
          confirmation_decision_id uuid NOT NULL UNIQUE,
          effective_from timestamptz NOT NULL, recorded_at timestamptz NOT NULL,
          supersedes_fact_version bigint, value_digest text NOT NULL CHECK (value_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,fact_id,fact_version),
          FOREIGN KEY (organization_id,workspace_id,fact_id) REFERENCES workspace.workspace_facts(organization_id,workspace_id,fact_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,confirmation_decision_id) REFERENCES workspace.confirmation_decisions(organization_id,workspace_id,confirmation_decision_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,fact_id,supersedes_fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          CHECK (supersedes_fact_version IS NULL OR supersedes_fact_version<fact_version),
          CHECK ((value_kind='text' AND text_value IS NOT NULL AND boolean_value IS NULL AND numeric_value IS NULL AND date_value IS NULL AND reference_value IS NULL)
              OR (value_kind='boolean' AND boolean_value IS NOT NULL AND text_value IS NULL AND numeric_value IS NULL AND date_value IS NULL AND reference_value IS NULL)
              OR (value_kind='date' AND date_value IS NOT NULL AND text_value IS NULL AND boolean_value IS NULL AND numeric_value IS NULL AND reference_value IS NULL)
              OR (value_kind='reference' AND reference_value IS NOT NULL AND text_value IS NULL AND boolean_value IS NULL AND numeric_value IS NULL AND date_value IS NULL)
              OR (value_kind='decimal_quantity' AND numeric_value IS NOT NULL AND unit_code IS NOT NULL AND precision_scale IS NOT NULL AND rounding_policy_version IS NOT NULL AND crs_reference IS NULL)
              OR (value_kind='measurement' AND numeric_value IS NOT NULL AND unit_code IS NOT NULL AND precision_scale IS NOT NULL AND rounding_policy_version IS NOT NULL AND crs_reference IS NOT NULL AND measurement_authority_ref IS NOT NULL))
        );
        CREATE TABLE workspace.workspace_fact_evidence (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, fact_id uuid NOT NULL, fact_version bigint NOT NULL,
          evidence_link_id uuid NOT NULL, source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL, evidence_role text NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,fact_id,fact_version,evidence_link_id),
          FOREIGN KEY (organization_id,workspace_id,fact_id,fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id) REFERENCES workspace.evidence_links(organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT
        );
        """
    )


def _create_common_chain() -> None:
    op.execute(
        """
        CREATE TABLE workspace.kernel_process_instances (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, process_instance_id uuid NOT NULL,
          mode_execution_id uuid NOT NULL, process_key text NOT NULL, process_definition_version text NOT NULL CHECK (lower(process_definition_version)<>'latest'),
          state text NOT NULL CHECK (state IN ('pending','running','waiting_for_evidence','blocked','completed','failed','quarantined')),
          revision bigint NOT NULL CHECK (revision>=1), rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          input_manifest_digest text NOT NULL CHECK (input_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          current_fingerprint text NOT NULL CHECK (current_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          correlation_id uuid NOT NULL, causation_id uuid, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,process_instance_id),
          FOREIGN KEY (organization_id,workspace_id,mode_execution_id) REFERENCES workspace.mode_executions(organization_id,workspace_id,mode_execution_id) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,mode_execution_id,process_key)
        );
        CREATE TABLE workspace.mode_kernel_bindings (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, mode_execution_id uuid NOT NULL,
          fact_id uuid NOT NULL, fact_version bigint NOT NULL CHECK (fact_version>=1),
          access_kind text NOT NULL CHECK (access_kind IN ('read','use_as_input')),
          sharing_decision_ref text NOT NULL, created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,mode_execution_id,fact_id,fact_version),
          FOREIGN KEY (organization_id,workspace_id,mode_execution_id) REFERENCES workspace.mode_executions(organization_id,workspace_id,mode_execution_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,fact_id,fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.construction_structure_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, structure_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          source_fact_id uuid NOT NULL, source_fact_version bigint NOT NULL,
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          rule_trace_id uuid NOT NULL, status text NOT NULL CHECK (status IN ('draft','active','superseded','blocked')),
          structure_digest text NOT NULL CHECK (structure_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,structure_id,version),
          FOREIGN KEY (organization_id,workspace_id,source_fact_id,source_fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.construction_element_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, element_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          structure_id uuid NOT NULL, structure_version bigint NOT NULL, parent_element_id uuid,
          element_kind text NOT NULL, stable_label text NOT NULL, zone_key text NOT NULL,
          source_fact_id uuid NOT NULL, source_fact_version bigint NOT NULL,
          element_digest text NOT NULL CHECK (element_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,element_id,version),
          FOREIGN KEY (organization_id,workspace_id,structure_id,structure_version) REFERENCES workspace.construction_structure_versions(organization_id,workspace_id,structure_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_fact_id,source_fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,structure_id,structure_version,stable_label)
        );
        CREATE TABLE workspace.work_instance_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, work_instance_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          work_type_id uuid NOT NULL, work_type_version text NOT NULL,
          element_id uuid NOT NULL, element_version bigint NOT NULL,
          work_state text NOT NULL CHECK (work_state IN ('planned','ready','in_progress','performed','accepted','blocked','superseded')),
          source_fact_id uuid NOT NULL, source_fact_version bigint NOT NULL,
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          rule_trace_id uuid NOT NULL, work_digest text NOT NULL CHECK (work_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,work_instance_id,version),
          FOREIGN KEY (work_type_id,work_type_version) REFERENCES platform.work_type_versions(work_type_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,element_id,element_version) REFERENCES workspace.construction_element_versions(organization_id,workspace_id,element_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_fact_id,source_fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.work_dependencies (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, dependency_id uuid NOT NULL,
          prerequisite_work_id uuid NOT NULL, prerequisite_version bigint NOT NULL,
          successor_work_id uuid NOT NULL, successor_version bigint NOT NULL,
          dependency_kind text NOT NULL CHECK (dependency_kind IN ('finish_to_start','start_to_start','evidence_before','control_before')),
          rule_trace_id uuid NOT NULL, status text NOT NULL CHECK (status IN ('active','blocked','superseded')),
          dependency_digest text NOT NULL CHECK (dependency_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,dependency_id),
          FOREIGN KEY (organization_id,workspace_id,prerequisite_work_id,prerequisite_version) REFERENCES workspace.work_instance_versions(organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,successor_work_id,successor_version) REFERENCES workspace.work_instance_versions(organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK (prerequisite_work_id<>successor_work_id)
        );
        CREATE TABLE workspace.work_volume_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, work_volume_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          work_instance_id uuid NOT NULL, work_instance_version bigint NOT NULL,
          volume_kind text NOT NULL CHECK (volume_kind IN ('planned','performed','confirmed','presentable')),
          quantity numeric NOT NULL, unit_code text NOT NULL, precision_scale integer NOT NULL CHECK (precision_scale>=0),
          rounding_policy_version text NOT NULL CHECK (lower(rounding_policy_version)<>'latest'), calculation_ref text NOT NULL,
          source_fact_id uuid NOT NULL, source_fact_version bigint NOT NULL, rule_trace_id uuid NOT NULL,
          volume_digest text NOT NULL CHECK (volume_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,work_volume_id,version),
          FOREIGN KEY (organization_id,workspace_id,work_instance_id,work_instance_version) REFERENCES workspace.work_instance_versions(organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_fact_id,source_fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.material_requirement_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, material_requirement_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          work_instance_id uuid NOT NULL, work_instance_version bigint NOT NULL,
          material_class_id uuid NOT NULL, material_class_version text NOT NULL,
          quantity numeric, unit_code text, precision_scale integer CHECK (precision_scale IS NULL OR precision_scale>=0),
          applicability text NOT NULL CHECK (applicability IN ('applicable','not_applicable','indeterminate')),
          status text NOT NULL CHECK (status IN ('required','conditional','satisfied','missing','blocked','superseded')),
          rule_trace_id uuid NOT NULL, requirement_digest text NOT NULL CHECK (requirement_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,material_requirement_id,version),
          FOREIGN KEY (organization_id,workspace_id,work_instance_id,work_instance_version) REFERENCES workspace.work_instance_versions(organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (material_class_id,material_class_version) REFERENCES platform.material_class_versions(material_class_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK ((quantity IS NULL AND unit_code IS NULL AND precision_scale IS NULL) OR (quantity IS NOT NULL AND unit_code IS NOT NULL AND precision_scale IS NOT NULL))
        );
        CREATE TABLE workspace.material_batch_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, material_batch_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          material_class_id uuid NOT NULL, material_class_version text NOT NULL, batch_reference text NOT NULL,
          admission_state text NOT NULL CHECK (admission_state IN ('candidate','admitted','rejected','quarantined','consumed')),
          source_fact_id uuid NOT NULL, source_fact_version bigint NOT NULL,
          batch_digest text NOT NULL CHECK (batch_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,material_batch_id,version),
          FOREIGN KEY (material_class_id,material_class_version) REFERENCES platform.material_class_versions(material_class_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_fact_id,source_fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.material_applications (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, material_application_id uuid NOT NULL,
          material_batch_id uuid NOT NULL, material_batch_version bigint NOT NULL,
          work_instance_id uuid NOT NULL, work_instance_version bigint NOT NULL,
          quantity numeric NOT NULL, unit_code text NOT NULL, precision_scale integer NOT NULL CHECK (precision_scale>=0),
          evidence_link_id uuid NOT NULL, application_digest text NOT NULL CHECK (application_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,material_application_id),
          FOREIGN KEY (organization_id,workspace_id,material_batch_id,material_batch_version) REFERENCES workspace.material_batch_versions(organization_id,workspace_id,material_batch_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,work_instance_id,work_instance_version) REFERENCES workspace.work_instance_versions(organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id) REFERENCES workspace.evidence_links(organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.control_operation_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, control_operation_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          work_instance_id uuid NOT NULL, work_instance_version bigint NOT NULL,
          control_kind text NOT NULL, method_version text NOT NULL CHECK (lower(method_version)<>'latest'),
          applicability text NOT NULL CHECK (applicability IN ('applicable','not_applicable','indeterminate')),
          state text NOT NULL CHECK (state IN ('required','planned','performed','passed','failed','blocked','superseded')),
          authority_requirement_ref text NOT NULL, rule_trace_id uuid NOT NULL,
          control_digest text NOT NULL CHECK (control_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,control_operation_id,version),
          FOREIGN KEY (organization_id,workspace_id,work_instance_id,work_instance_version) REFERENCES workspace.work_instance_versions(organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.evidence_requirement_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, evidence_requirement_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          work_instance_id uuid NOT NULL, work_instance_version bigint NOT NULL, control_operation_id uuid, control_operation_version bigint,
          evidence_kind text NOT NULL, applicability text NOT NULL CHECK (applicability IN ('applicable','not_applicable','indeterminate')),
          status text NOT NULL CHECK (status IN ('required','conditional','satisfied','missing','blocked','superseded')),
          acceptance_contract_version text NOT NULL CHECK (lower(acceptance_contract_version)<>'latest'), rule_trace_id uuid NOT NULL,
          requirement_digest text NOT NULL CHECK (requirement_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,evidence_requirement_id,version),
          FOREIGN KEY (organization_id,workspace_id,work_instance_id,work_instance_version) REFERENCES workspace.work_instance_versions(organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,control_operation_id,control_operation_version) REFERENCES workspace.control_operation_versions(organization_id,workspace_id,control_operation_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.document_requirement_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, document_requirement_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          work_instance_id uuid NOT NULL, work_instance_version bigint NOT NULL,
          required_document_type_id uuid NOT NULL, required_document_type_version text NOT NULL,
          applicability text NOT NULL CHECK (applicability IN ('required','conditional','not_required','indeterminate')),
          status text NOT NULL CHECK (status IN ('open','covered','missing','blocked','superseded')),
          rule_evaluation_id uuid NOT NULL, rule_trace_id uuid NOT NULL,
          requirement_digest text NOT NULL CHECK (requirement_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,document_requirement_id,version),
          FOREIGN KEY (organization_id,workspace_id,work_instance_id,work_instance_version) REFERENCES workspace.work_instance_versions(organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (required_document_type_id,required_document_type_version) REFERENCES platform.required_document_type_versions(required_document_type_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_evaluation_id) REFERENCES workspace.rule_evaluations(organization_id,workspace_id,rule_evaluation_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.document_coverages (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, document_coverage_id uuid NOT NULL,
          document_requirement_id uuid NOT NULL, document_requirement_version bigint NOT NULL,
          subject_kind text NOT NULL CHECK (subject_kind IN ('candidate','generated_document_candidate','finalized_document','source_version')),
          subject_id uuid NOT NULL, subject_version text NOT NULL CHECK (lower(subject_version)<>'latest'),
          coverage_status text NOT NULL CHECK (coverage_status IN ('covered','partial','conflict','unverified','rejected')),
          evidence_link_id uuid NOT NULL, coverage_digest text NOT NULL CHECK (coverage_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,document_coverage_id),
          FOREIGN KEY (organization_id,workspace_id,document_requirement_id,document_requirement_version) REFERENCES workspace.document_requirement_versions(organization_id,workspace_id,document_requirement_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id) REFERENCES workspace.evidence_links(organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.id_package_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, id_package_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          scope_kind text NOT NULL CHECK (scope_kind IN ('work','period','presentation')),
          scope_subject_id uuid NOT NULL, completeness_status text NOT NULL CHECK (completeness_status IN ('complete','incomplete','indeterminate','blocked')),
          required_count integer NOT NULL CHECK (required_count>=0), covered_count integer NOT NULL CHECK (covered_count>=0),
          missing_count integer NOT NULL CHECK (missing_count>=0), indeterminate_count integer NOT NULL CHECK (indeterminate_count>=0),
          calculation_fingerprint text NOT NULL CHECK (calculation_fingerprint ~ '^sha256:[a-f0-9]{64}$'), rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          recorded_at timestamptz NOT NULL, PRIMARY KEY (organization_id,workspace_id,id_package_id,version),
          CHECK (covered_count+missing_count<=required_count)
        );
        CREATE TABLE workspace.id_package_items (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, id_package_id uuid NOT NULL, id_package_version bigint NOT NULL,
          document_requirement_id uuid NOT NULL, document_requirement_version bigint NOT NULL,
          document_coverage_id uuid, item_status text NOT NULL CHECK (item_status IN ('covered','missing','indeterminate','blocked')),
          PRIMARY KEY (organization_id,workspace_id,id_package_id,id_package_version,document_requirement_id,document_requirement_version),
          FOREIGN KEY (organization_id,workspace_id,id_package_id,id_package_version) REFERENCES workspace.id_package_versions(organization_id,workspace_id,id_package_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,document_requirement_id,document_requirement_version) REFERENCES workspace.document_requirement_versions(organization_id,workspace_id,document_requirement_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,document_coverage_id) REFERENCES workspace.document_coverages(organization_id,workspace_id,document_coverage_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.presented_volume_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, presented_volume_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          work_volume_id uuid NOT NULL, work_volume_version bigint NOT NULL, id_package_id uuid NOT NULL, id_package_version bigint NOT NULL,
          contract_context_ref text NOT NULL, status text NOT NULL CHECK (status IN ('draft','eligible','blocked','presented','accepted','rejected')),
          rule_trace_id uuid NOT NULL, presented_digest text NOT NULL CHECK (presented_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,presented_volume_id,version),
          FOREIGN KEY (organization_id,workspace_id,work_volume_id,work_volume_version) REFERENCES workspace.work_volume_versions(organization_id,workspace_id,work_volume_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,id_package_id,id_package_version) REFERENCES workspace.id_package_versions(organization_id,workspace_id,id_package_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.ks_document_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, ks_document_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          ks_type text NOT NULL CHECK (ks_type IN ('KS-2','KS-3','OTHER')), period_start date NOT NULL, period_end date NOT NULL,
          contract_context_ref text NOT NULL, status text NOT NULL CHECK (status IN ('draft','validated','finalized','rejected','superseded')),
          source_version_id uuid, finalized_document_ref text,
          document_digest text NOT NULL CHECK (document_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,ks_document_id,version),
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          CHECK (period_end>=period_start)
        );
        CREATE TABLE workspace.ks_line_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, ks_line_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          ks_document_id uuid NOT NULL, ks_document_version bigint NOT NULL, presented_volume_id uuid NOT NULL, presented_volume_version bigint NOT NULL,
          quantity numeric NOT NULL, unit_code text NOT NULL, precision_scale integer NOT NULL CHECK (precision_scale>=0),
          rate numeric NOT NULL, amount numeric NOT NULL, currency_code text NOT NULL, calculation_ref text NOT NULL,
          line_digest text NOT NULL CHECK (line_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,ks_line_id,version),
          FOREIGN KEY (organization_id,workspace_id,ks_document_id,ks_document_version) REFERENCES workspace.ks_document_versions(organization_id,workspace_id,ks_document_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,presented_volume_id,presented_volume_version) REFERENCES workspace.presented_volume_versions(organization_id,workspace_id,presented_volume_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.payment_claim_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, payment_claim_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          ks_document_id uuid NOT NULL, ks_document_version bigint NOT NULL,
          amount numeric NOT NULL, currency_code text NOT NULL, status text NOT NULL CHECK (status IN ('draft','eligible','blocked','submitted','accepted','rejected','paid')),
          authority_reference text, rule_trace_id uuid NOT NULL,
          claim_digest text NOT NULL CHECK (claim_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,payment_claim_id,version),
          FOREIGN KEY (organization_id,workspace_id,ks_document_id,ks_document_version) REFERENCES workspace.ks_document_versions(organization_id,workspace_id,ks_document_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.kernel_issue_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, issue_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          issue_kind text NOT NULL CHECK (issue_kind IN ('uncertainty','conflict','blocker')), issue_code text NOT NULL,
          subject_type text NOT NULL, subject_id uuid NOT NULL, subject_version text NOT NULL,
          required_inputs text[] NOT NULL, status text NOT NULL CHECK (status IN ('open','resolved','accepted_risk','superseded')),
          evidence_link_ids uuid[] NOT NULL, rule_trace_id uuid,
          issue_digest text NOT NULL CHECK (issue_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,issue_id,version),
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK (status<>'open' OR cardinality(required_inputs)>0)
        );
        CREATE TABLE workspace.kernel_finding_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, finding_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          finding_kind text NOT NULL CHECK (finding_kind IN ('missing_work','missing_material','missing_evidence','constructive_clash','geometric_clash','contract_risk','audit_delta','restoration_gap','payment_blocker')),
          subject_type text NOT NULL, subject_id uuid NOT NULL, subject_version text NOT NULL,
          applicability text NOT NULL CHECK (applicability IN ('applicable','not_applicable','indeterminate')),
          status text NOT NULL CHECK (status IN ('draft','validated','confirmed','blocked','superseded')),
          source_fact_ids uuid[] NOT NULL, evidence_link_ids uuid[] NOT NULL, issue_ids uuid[] NOT NULL,
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          rule_trace_id uuid NOT NULL, finding_digest text NOT NULL CHECK (finding_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,finding_id,version),
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK (status<>'confirmed' OR (cardinality(source_fact_ids)>0 AND cardinality(evidence_link_ids)>0 AND applicability='applicable'))
        );
        CREATE TABLE workspace.deliverable_inputs (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, deliverable_input_id uuid NOT NULL,
          deliverable_kind text NOT NULL CHECK (deliverable_kind IN ('disagreement_protocol','revised_contract','pd_rd_analysis','missing_work_material_finding','constructive_clash','geometric_clash','executive_scheme','id_document','audit_finding','restoration_finding')),
          input_kind text NOT NULL CHECK (input_kind IN ('fact','finding','id_package','presented_volume','ks_line','payment_claim','issue')),
          input_id uuid NOT NULL, input_version text NOT NULL CHECK (lower(input_version)<>'latest'),
          evidence_manifest_digest text NOT NULL CHECK (evidence_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          rule_trace_id uuid NOT NULL, readiness text NOT NULL CHECK (readiness IN ('eligible','blocked','indeterminate')),
          blocker_issue_ids uuid[] NOT NULL, created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,deliverable_input_id),
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK (readiness='eligible' OR cardinality(blocker_issue_ids)>0)
        );
        """
    )


def _apply_guards_grants_and_rls() -> None:
    predicate = (
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid"
    )
    op.execute("GRANT USAGE ON SCHEMA platform,workspace,messaging,audit TO asd_kernel_service")
    op.execute(
        "GRANT SELECT ON "
        + ",".join(f"platform.{table}" for table in PLATFORM_TABLES)
        + ",platform.rule_versions,platform.rule_version_states,platform.rule_set_versions,platform.rule_set_memberships TO asd_kernel_service"
    )
    op.execute(
        "GRANT SELECT,INSERT ON "
        + ",".join(f"platform.{table}" for table in PLATFORM_TABLES)
        + " TO asd_platform_curator"
    )
    op.execute(
        "GRANT SELECT ON "
        + ",".join(f"workspace.{table}" for table in KERNEL_READ_TABLES)
        + " TO asd_kernel_service"
    )
    for table in KERNEL_READ_TABLES:
        op.execute(
            f"CREATE POLICY {table}_kernel_read_scope_policy ON workspace.{table} "
            f"FOR SELECT TO asd_kernel_service USING ({predicate})"
        )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON messaging.workspace_idempotency TO asd_kernel_service"
    )
    op.execute("GRANT SELECT,INSERT ON messaging.workspace_outbox TO asd_kernel_service")
    op.execute("GRANT SELECT,INSERT ON audit.workspace_records TO asd_kernel_service")
    for qualified in (
        "messaging.workspace_idempotency",
        "messaging.workspace_outbox",
        "audit.workspace_records",
    ):
        table = qualified.split(".")[1]
        op.execute(
            f"CREATE POLICY {table}_kernel_scope_policy ON {qualified} FOR ALL TO asd_kernel_service "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION workspace.reject_workspace_immutable_unless_destroy()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member') THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'immutable workspace record cannot be mutated' USING ERRCODE='55000';
        END $$;
        CREATE OR REPLACE FUNCTION workspace.reject_kernel_version_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member') THEN RETURN OLD; END IF;
          RAISE EXCEPTION 'immutable kernel version cannot be mutated' USING ERRCODE='55000';
        END $$;
        CREATE OR REPLACE FUNCTION workspace.guard_kernel_header_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member') THEN RETURN OLD; END IF;
          IF TG_OP='UPDATE' AND pg_has_role(session_user,'asd_kernel_service','member')
             AND NULLIF(current_setting('asd.kernel_operation_id',true),'') IS NOT NULL THEN RETURN NEW; END IF;
          RAISE EXCEPTION 'kernel header mutation requires controlled service path' USING ERRCODE='42501';
        END $$;
        """
    )
    for table in G05_IMMUTABLE_WORKSPACE_TABLES:
        op.execute(f"DROP TRIGGER trg_{table}_immutable ON workspace.{table}")
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION workspace.reject_workspace_immutable_unless_destroy()"
        )
    for table in WORKSPACE_TABLES:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_kernel_scope_policy ON workspace.{table} FOR ALL TO asd_kernel_service "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_app_scope_policy ON workspace.{table} FOR SELECT TO asd_app "
            f"USING ({predicate})"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_kernel_service")
        op.execute(f"GRANT SELECT ON workspace.{table} TO asd_app")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE POLICY {table}_destruction_scope_policy ON workspace.{table} FOR ALL TO asd_destruction_executor "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_write_fence BEFORE INSERT OR UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION workspace.enforce_material_write_fence()"
        )
        guard = (
            "workspace.guard_kernel_header_mutation()"
            if table in MUTABLE_HEADERS
            else "workspace.reject_kernel_version_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_mutation_guard BEFORE UPDATE OR DELETE ON workspace.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION {guard}"
        )
    op.execute(
        "GRANT UPDATE (current_version,revision,updated_at) ON workspace.workspace_facts TO asd_kernel_service"
    )
    op.execute(
        "GRANT UPDATE (state,revision,current_fingerprint,updated_at) ON workspace.kernel_process_instances TO asd_kernel_service"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "destructive downgrade is allowed only for a disposable development/test database"
        )
    for table in reversed(WORKSPACE_TABLES):
        op.execute(f"DROP TABLE IF EXISTS workspace.{table} CASCADE")
    for table in G05_IMMUTABLE_WORKSPACE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON workspace.{table}")
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )
    for table in KERNEL_READ_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_kernel_read_scope_policy ON workspace.{table}")
    for qualified in (
        "messaging.workspace_idempotency",
        "messaging.workspace_outbox",
        "audit.workspace_records",
    ):
        table = qualified.split(".")[1]
        op.execute(f"DROP POLICY IF EXISTS {table}_kernel_scope_policy ON {qualified}")
    op.execute(
        "REVOKE SELECT ON "
        + ",".join(f"workspace.{table}" for table in KERNEL_READ_TABLES)
        + " FROM asd_kernel_service"
    )
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE IF EXISTS platform.{table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS workspace.guard_kernel_header_mutation()")
    op.execute("DROP FUNCTION IF EXISTS workspace.reject_kernel_version_mutation()")
    op.execute("DROP FUNCTION IF EXISTS workspace.reject_workspace_immutable_unless_destroy()")
