"""Create the WP-13 Support implementation slice.

Revision ID: 0007_wp13
Revises: 0006_wp12
Create Date: 2026-08-23
"""

from __future__ import annotations

import os

from alembic import op

revision = "0007_wp13"
down_revision = "0006_wp12"
branch_labels = None
depends_on = None

PLATFORM_TABLES = (
    "template_sources",
    "field_schema_versions",
    "template_versions",
)

WORKSPACE_TABLES = (
    "support_processes",
    "support_scope_versions",
    "support_professional_grants",
    "support_work_readiness_evaluations",
    "support_material_admissions",
    "support_control_results",
    "support_offline_observations",
    "support_offline_reconciliations",
    "support_id_completeness_evaluations",
    "support_generation_requests",
    "support_binding_plan_versions",
    "support_generation_runs",
    "support_generation_field_resolutions",
    "support_generation_evidence_bindings",
    "support_generated_document_candidates",
    "support_render_artifacts",
    "support_print_validation_results",
    "support_document_review_decisions",
    "support_finalized_document_versions",
    "support_geometry_input_versions",
    "support_executive_scheme_versions",
    "support_presented_volume_readiness",
    "support_payment_readiness",
    "support_deliverable_versions",
    "support_terminal_outcomes",
)

READ_TABLES = (
    "workspaces",
    "mode_executions",
    "source_versions",
    "source_locators",
    "evidence_links",
    "workspace_fact_versions",
    "confirmation_decisions",
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
    "rule_traces",
)


def upgrade() -> None:
    _create_role_and_platform_templates()
    _create_support_process_and_field_chain()
    _create_generation_pipeline()
    _create_geometry_and_commercial_chain()
    _apply_guards_grants_and_rls()


def _create_role_and_platform_templates() -> None:
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_support_service') "
        "THEN CREATE ROLE asd_support_service NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; "
        "END IF; END $$"
    )
    op.execute(
        """
        CREATE TABLE platform.template_sources (
          template_source_id uuid PRIMARY KEY, stable_key text NOT NULL UNIQUE,
          format text NOT NULL CHECK (format IN ('DOCX','XLSX','PDF_FILLABLE','PDF_OVERLAY','DXF','SVG','PDF_SCHEME')),
          source_kind text NOT NULL CHECK (source_kind IN ('synthetic_qualification','official_candidate','universal')),
          source_digest text NOT NULL CHECK (source_digest ~ '^sha256:[a-f0-9]{64}$'),
          provenance_ref text NOT NULL, rights_status text NOT NULL CHECK (rights_status IN ('synthetic_permitted','unverified','verified','rejected')),
          authority_status text NOT NULL CHECK (authority_status IN ('candidate','verified','rejected')),
          created_at timestamptz NOT NULL,
          CHECK (source_kind<>'synthetic_qualification' OR rights_status='synthetic_permitted')
        );
        CREATE TABLE platform.field_schema_versions (
          field_schema_id uuid NOT NULL, version text NOT NULL CHECK (lower(version)<>'latest'),
          schema_key text NOT NULL, field_manifest_digest text NOT NULL CHECK (field_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('candidate','qualified','active','superseded','withdrawn')),
          created_at timestamptz NOT NULL, PRIMARY KEY (field_schema_id,version),
          UNIQUE (schema_key,version)
        );
        CREATE TABLE platform.template_versions (
          template_id uuid NOT NULL, version text NOT NULL CHECK (lower(version)<>'latest'),
          template_source_id uuid NOT NULL REFERENCES platform.template_sources(template_source_id) ON DELETE RESTRICT,
          format text NOT NULL CHECK (format IN ('DOCX','XLSX','PDF_FILLABLE','PDF_OVERLAY','DXF','SVG','PDF_SCHEME')),
          field_schema_id uuid NOT NULL, field_schema_version text NOT NULL,
          binding_profile_version text NOT NULL CHECK (lower(binding_profile_version)<>'latest'),
          renderer_profile_version text NOT NULL CHECK (lower(renderer_profile_version)<>'latest'),
          validator_profile_version text NOT NULL CHECK (lower(validator_profile_version)<>'latest'),
          qualification_state text NOT NULL CHECK (qualification_state IN ('candidate','qualified','active','blocked','withdrawn','rejected')),
          assurance_class text NOT NULL CHECK (assurance_class IN ('synthetic_development','production')),
          official_status text NOT NULL CHECK (official_status IN ('synthetic_only','unverified','verified')),
          template_digest text NOT NULL CHECK (template_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL, PRIMARY KEY (template_id,version),
          FOREIGN KEY (field_schema_id,field_schema_version) REFERENCES platform.field_schema_versions(field_schema_id,version) ON DELETE RESTRICT,
          CHECK (assurance_class<>'production' OR (qualification_state='active' AND official_status='verified')),
          CHECK (assurance_class<>'synthetic_development' OR official_status='synthetic_only')
        );
        """
    )


def _create_support_process_and_field_chain() -> None:
    op.execute(
        """
        CREATE TABLE workspace.support_processes (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, support_process_id uuid NOT NULL,
          mode_execution_id uuid NOT NULL, state text NOT NULL CHECK (state IN ('requested','scope_configured','executing','waiting_for_evidence','ready_for_deliverable','waiting_for_authority','blocked','finalized')),
          revision bigint NOT NULL CHECK (revision>=1), process_definition_version text NOT NULL CHECK (lower(process_definition_version)<>'latest'),
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          authority_profile_version text NOT NULL CHECK (lower(authority_profile_version)<>'latest'),
          contract_registry_version text NOT NULL CHECK (lower(contract_registry_version)<>'latest'),
          input_manifest_digest text NOT NULL CHECK (input_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          current_fingerprint text NOT NULL CHECK (current_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          correlation_id uuid NOT NULL, causation_id uuid, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,support_process_id),
          FOREIGN KEY (organization_id,workspace_id,mode_execution_id) REFERENCES workspace.mode_executions(organization_id,workspace_id,mode_execution_id) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,mode_execution_id)
        );
        CREATE TABLE workspace.support_scope_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, support_process_id uuid NOT NULL, scope_version bigint NOT NULL CHECK (scope_version>=1),
          deliverable_scope text[] NOT NULL CHECK (cardinality(deliverable_scope)>0),
          source_class_allowlist text[] NOT NULL CHECK (cardinality(source_class_allowlist)>0),
          policy_versions text[] NOT NULL CHECK (cardinality(policy_versions)>0 AND NOT ('latest'=ANY(policy_versions))),
          classification text NOT NULL, purpose text NOT NULL, authority_profile_version text NOT NULL CHECK (lower(authority_profile_version)<>'latest'),
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          scope_digest text NOT NULL CHECK (scope_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,support_process_id,scope_version),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.support_professional_grants (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, grant_id uuid NOT NULL, grant_version bigint NOT NULL CHECK (grant_version>=1),
          human_identity_id text NOT NULL CHECK (human_identity_id !~ '^(model|service|integration):'),
          capability text NOT NULL CHECK (capability IN ('support.scope.configure','support.work.plan','support.work.evaluate','support.engineering.confirm','support.material.admit','support.material.apply','support.control.confirm','support.evidence.verify','support.id.evaluate','support.document.generate','support.id.form-package','support.volume.review','support.geometry.finalize','support.ks.trace','support.payment.review','support.document.review','support.deliverable.finalize')),
          professional_qualification_ref text NOT NULL, authority_reference text NOT NULL,
          status text NOT NULL CHECK (status IN ('active','suspended','revoked','expired')),
          effective_from timestamptz NOT NULL, effective_until timestamptz,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,grant_id,grant_version),
          FOREIGN KEY (organization_id,workspace_id) REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT,
          CHECK (effective_until IS NULL OR effective_until>effective_from)
        );
        CREATE TABLE workspace.support_work_readiness_evaluations (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, readiness_id uuid NOT NULL, support_process_id uuid NOT NULL,
          work_instance_id uuid NOT NULL, work_instance_version bigint NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('ready','blocked','indeterminate')), reason_codes text[] NOT NULL,
          performed_fact_id uuid, performed_fact_version bigint, rule_trace_id uuid NOT NULL,
          evaluation_fingerprint text NOT NULL CHECK (evaluation_fingerprint ~ '^sha256:[a-f0-9]{64}$'), evaluated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,readiness_id),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,work_instance_id,work_instance_version) REFERENCES workspace.work_instance_versions(organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,performed_fact_id,performed_fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK (outcome<>'ready' OR (performed_fact_id IS NOT NULL AND cardinality(reason_codes)=0)),
          CHECK (outcome='ready' OR cardinality(reason_codes)>0)
        );
        CREATE TABLE workspace.support_material_admissions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, admission_id uuid NOT NULL, support_process_id uuid NOT NULL,
          material_batch_id uuid NOT NULL, material_batch_version bigint NOT NULL, work_instance_id uuid NOT NULL, work_instance_version bigint NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('admitted','rejected','quarantined','waiting_for_documents')),
          certificate_evidence_ids uuid[] NOT NULL, passport_evidence_ids uuid[] NOT NULL,
          incoming_control_id uuid, custody_complete boolean NOT NULL, reason_codes text[] NOT NULL,
          authority_grant_id uuid NOT NULL, authority_grant_version bigint NOT NULL,
          admission_fingerprint text NOT NULL CHECK (admission_fingerprint ~ '^sha256:[a-f0-9]{64}$'), admitted_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,admission_id),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,material_batch_id,material_batch_version) REFERENCES workspace.material_batch_versions(organization_id,workspace_id,material_batch_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,work_instance_id,work_instance_version) REFERENCES workspace.work_instance_versions(organization_id,workspace_id,work_instance_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,authority_grant_id,authority_grant_version) REFERENCES workspace.support_professional_grants(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT,
          CHECK (outcome<>'admitted' OR (cardinality(certificate_evidence_ids)>0 AND cardinality(passport_evidence_ids)>0 AND incoming_control_id IS NOT NULL AND custody_complete AND cardinality(reason_codes)=0)),
          CHECK (outcome='admitted' OR cardinality(reason_codes)>0)
        );
        CREATE TABLE workspace.support_control_results (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, control_result_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          support_process_id uuid NOT NULL, control_operation_id uuid NOT NULL, control_operation_version bigint NOT NULL,
          performed_fact_id uuid NOT NULL, performed_fact_version bigint NOT NULL, evidence_link_id uuid NOT NULL,
          method_version text NOT NULL CHECK (lower(method_version)<>'latest'), criterion text NOT NULL,
          observed_value numeric, tolerance numeric, unit_code text, calibration_id uuid, calibration_valid_at_event boolean NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('passed','failed','indeterminate')), reason_codes text[] NOT NULL,
          supersedes_result_id uuid, supersedes_result_version bigint,
          authority_grant_id uuid NOT NULL, authority_grant_version bigint NOT NULL, rule_trace_id uuid NOT NULL,
          result_fingerprint text NOT NULL CHECK (result_fingerprint ~ '^sha256:[a-f0-9]{64}$'), performed_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,control_result_id,version),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,control_operation_id,control_operation_version) REFERENCES workspace.control_operation_versions(organization_id,workspace_id,control_operation_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,performed_fact_id,performed_fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id) REFERENCES workspace.evidence_links(organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,supersedes_result_id,supersedes_result_version) REFERENCES workspace.support_control_results(organization_id,workspace_id,control_result_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,authority_grant_id,authority_grant_version) REFERENCES workspace.support_professional_grants(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK (outcome<>'passed' OR (observed_value IS NOT NULL AND tolerance IS NOT NULL AND unit_code IS NOT NULL AND calibration_valid_at_event AND cardinality(reason_codes)=0)),
          CHECK (outcome='passed' OR cardinality(reason_codes)>0)
        );
        CREATE TABLE workspace.support_offline_observations (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, observation_id uuid NOT NULL,
          device_identity text NOT NULL, acquisition_method text NOT NULL, observed_at timestamptz NOT NULL, timestamp_authority_ref text NOT NULL,
          actor_identity text NOT NULL, source_locator_id uuid NOT NULL, evidence_link_id uuid NOT NULL,
          payload_digest text NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'), semantic_fingerprint text NOT NULL CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          sync_lineage_id uuid NOT NULL, status text NOT NULL CHECK (status IN ('accepted','conflict','quarantined')),
          imported_at timestamptz NOT NULL, PRIMARY KEY (organization_id,workspace_id,observation_id),
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id) REFERENCES workspace.evidence_links(organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.support_offline_reconciliations (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, reconciliation_id uuid NOT NULL, observation_id uuid NOT NULL,
          incoming_fingerprint text NOT NULL CHECK (incoming_fingerprint ~ '^sha256:[a-f0-9]{64}$'), canonical_fingerprint text NOT NULL CHECK (canonical_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          disposition text NOT NULL CHECK (disposition IN ('accepted','duplicate','conflict','quarantined')),
          conflict_id uuid, reconciled_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,reconciliation_id),
          FOREIGN KEY (organization_id,workspace_id,observation_id) REFERENCES workspace.support_offline_observations(organization_id,workspace_id,observation_id) ON DELETE RESTRICT,
          CHECK (disposition NOT IN ('conflict','quarantined') OR conflict_id IS NOT NULL)
        );
        CREATE TABLE workspace.support_id_completeness_evaluations (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, evaluation_id uuid NOT NULL, support_process_id uuid NOT NULL,
          id_package_id uuid NOT NULL, id_package_version bigint NOT NULL, required_ids uuid[] NOT NULL, covered_ids uuid[] NOT NULL,
          missing_ids uuid[] NOT NULL, indeterminate_ids uuid[] NOT NULL, blocked_ids uuid[] NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('complete','incomplete','indeterminate','blocked')),
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          evaluation_fingerprint text NOT NULL CHECK (evaluation_fingerprint ~ '^sha256:[a-f0-9]{64}$'), evaluated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,evaluation_id),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,id_package_id,id_package_version) REFERENCES workspace.id_package_versions(organization_id,workspace_id,id_package_id,version) ON DELETE RESTRICT,
          CHECK (outcome<>'complete' OR (cardinality(missing_ids)=0 AND cardinality(indeterminate_ids)=0 AND cardinality(blocked_ids)=0))
        );
        """
    )


def _create_generation_pipeline() -> None:
    op.execute(
        """
        CREATE TABLE workspace.support_generation_requests (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, generation_request_id uuid NOT NULL, support_process_id uuid NOT NULL,
          mode_execution_id uuid NOT NULL, required_document_type_id uuid NOT NULL, required_document_type_version text NOT NULL,
          requested_format text NOT NULL CHECK (requested_format IN ('DOCX','XLSX','PDF_FILLABLE','PDF_OVERLAY','DXF','SVG','PDF_SCHEME')),
          purpose text NOT NULL, authority_grant_id uuid NOT NULL, authority_grant_version bigint NOT NULL,
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          policy_versions text[] NOT NULL CHECK (cardinality(policy_versions)>0 AND NOT ('latest'=ANY(policy_versions))),
          idempotency_key text NOT NULL, request_digest text NOT NULL CHECK (request_digest ~ '^sha256:[a-f0-9]{64}$'), requested_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,generation_request_id),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,mode_execution_id) REFERENCES workspace.mode_executions(organization_id,workspace_id,mode_execution_id) ON DELETE RESTRICT,
          FOREIGN KEY (required_document_type_id,required_document_type_version) REFERENCES platform.required_document_type_versions(required_document_type_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,authority_grant_id,authority_grant_version) REFERENCES workspace.support_professional_grants(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,idempotency_key)
        );
        CREATE TABLE workspace.support_binding_plan_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, binding_plan_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          generation_request_id uuid NOT NULL, template_id uuid NOT NULL, template_version text NOT NULL,
          field_schema_id uuid NOT NULL, field_schema_version text NOT NULL, binding_profile_version text NOT NULL CHECK (lower(binding_profile_version)<>'latest'),
          target_manifest_digest text NOT NULL CHECK (target_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          applicability_rule_trace_id uuid NOT NULL, plan_digest text NOT NULL CHECK (plan_digest ~ '^sha256:[a-f0-9]{64}$'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,binding_plan_id,version),
          FOREIGN KEY (organization_id,workspace_id,generation_request_id) REFERENCES workspace.support_generation_requests(organization_id,workspace_id,generation_request_id) ON DELETE RESTRICT,
          FOREIGN KEY (template_id,template_version) REFERENCES platform.template_versions(template_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (field_schema_id,field_schema_version) REFERENCES platform.field_schema_versions(field_schema_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,applicability_rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.support_generation_runs (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, generation_run_id uuid NOT NULL,
          generation_request_id uuid NOT NULL, binding_plan_id uuid NOT NULL, binding_plan_version bigint NOT NULL,
          renderer_profile_version text NOT NULL CHECK (lower(renderer_profile_version)<>'latest'), validator_profile_version text NOT NULL CHECK (lower(validator_profile_version)<>'latest'),
          input_fingerprint text NOT NULL CHECK (input_fingerprint ~ '^sha256:[a-f0-9]{64}$'), fresh_document_instance boolean NOT NULL CHECK (fresh_document_instance),
          status text NOT NULL CHECK (status IN ('planned','resolving','rendering','validating','blocked','failed','candidate_created')),
          blocker_codes text[] NOT NULL, started_at timestamptz NOT NULL, completed_at timestamptz,
          PRIMARY KEY (organization_id,workspace_id,generation_run_id),
          FOREIGN KEY (organization_id,workspace_id,generation_request_id) REFERENCES workspace.support_generation_requests(organization_id,workspace_id,generation_request_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,binding_plan_id,binding_plan_version) REFERENCES workspace.support_binding_plan_versions(organization_id,workspace_id,binding_plan_id,version) ON DELETE RESTRICT,
          CHECK (status<>'candidate_created' OR cardinality(blocker_codes)=0),
          CHECK (status NOT IN ('blocked','failed') OR cardinality(blocker_codes)>0)
        );
        CREATE TABLE workspace.support_generation_field_resolutions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, generation_run_id uuid NOT NULL, field_key text NOT NULL,
          state text NOT NULL CHECK (state IN ('confirmed','candidate','conflict','missing','not_applicable','redacted_for_view')),
          material boolean NOT NULL, normalized_value text, display_value text, fact_id uuid, fact_version bigint,
          field_fingerprint text NOT NULL CHECK (field_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,generation_run_id,field_key),
          FOREIGN KEY (organization_id,workspace_id,generation_run_id) REFERENCES workspace.support_generation_runs(organization_id,workspace_id,generation_run_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,fact_id,fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          CHECK (state<>'confirmed' OR (fact_id IS NOT NULL AND fact_version IS NOT NULL)),
          CHECK (NOT material OR state IN ('confirmed','not_applicable') OR normalized_value IS NULL)
        );
        CREATE TABLE workspace.support_generation_evidence_bindings (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, binding_id uuid NOT NULL, generation_run_id uuid NOT NULL, field_key text NOT NULL,
          fact_id uuid NOT NULL, fact_version bigint NOT NULL, evidence_link_id uuid NOT NULL, source_locator_id uuid NOT NULL,
          confirmation_decision_id uuid NOT NULL, resolver_rule_trace_id uuid NOT NULL,
          binding_digest text NOT NULL CHECK (binding_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,binding_id),
          FOREIGN KEY (organization_id,workspace_id,generation_run_id,field_key) REFERENCES workspace.support_generation_field_resolutions(organization_id,workspace_id,generation_run_id,field_key) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,fact_id,fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id) REFERENCES workspace.evidence_links(organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,confirmation_decision_id) REFERENCES workspace.confirmation_decisions(organization_id,workspace_id,confirmation_decision_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,resolver_rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.support_generated_document_candidates (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, generated_candidate_id uuid NOT NULL, generation_run_id uuid NOT NULL,
          object_reference text NOT NULL, format text NOT NULL CHECK (format IN ('DOCX','XLSX','PDF','DXF','SVG')),
          semantic_fingerprint text NOT NULL CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          bytes_digest text NOT NULL CHECK (bytes_digest ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status='non_final_candidate'), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,generated_candidate_id),
          FOREIGN KEY (organization_id,workspace_id,generation_run_id) REFERENCES workspace.support_generation_runs(organization_id,workspace_id,generation_run_id) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,generation_run_id,bytes_digest)
        );
        CREATE TABLE workspace.support_render_artifacts (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, render_artifact_id uuid NOT NULL, generated_candidate_id uuid NOT NULL,
          renderer_profile_version text NOT NULL CHECK (lower(renderer_profile_version)<>'latest'), format text NOT NULL,
          object_reference text NOT NULL, content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          assurance_class text NOT NULL CHECK (assurance_class IN ('synthetic_structural_only','production_qualified')),
          status text NOT NULL CHECK (status IN ('created','verified','failed','quarantined')), created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,render_artifact_id),
          FOREIGN KEY (organization_id,workspace_id,generated_candidate_id) REFERENCES workspace.support_generated_document_candidates(organization_id,workspace_id,generated_candidate_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.support_print_validation_results (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, print_validation_id uuid NOT NULL, generated_candidate_id uuid NOT NULL,
          render_artifact_id uuid NOT NULL, validator_profile_version text NOT NULL CHECK (lower(validator_profile_version)<>'latest'),
          check_codes text[] NOT NULL CHECK (cardinality(check_codes)>0), blocker_codes text[] NOT NULL,
          result text NOT NULL CHECK (result IN ('synthetic_validated','print_ready','blocked','failed','indeterminate')),
          assurance_class text NOT NULL CHECK (assurance_class IN ('synthetic_development','production')),
          result_digest text NOT NULL CHECK (result_digest ~ '^sha256:[a-f0-9]{64}$'), validated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,print_validation_id),
          FOREIGN KEY (organization_id,workspace_id,generated_candidate_id) REFERENCES workspace.support_generated_document_candidates(organization_id,workspace_id,generated_candidate_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,render_artifact_id) REFERENCES workspace.support_render_artifacts(organization_id,workspace_id,render_artifact_id) ON DELETE RESTRICT,
          CHECK (result<>'print_ready' OR assurance_class='production'),
          CHECK (result NOT IN ('synthetic_validated','print_ready') OR cardinality(blocker_codes)=0),
          CHECK (result IN ('synthetic_validated','print_ready') OR cardinality(blocker_codes)>0)
        );
        CREATE TABLE workspace.support_document_review_decisions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, review_decision_id uuid NOT NULL, generated_candidate_id uuid NOT NULL,
          print_validation_id uuid NOT NULL, human_identity_id text NOT NULL CHECK (human_identity_id !~ '^(model|service|integration):'),
          authority_grant_id uuid NOT NULL, authority_grant_version bigint NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('approved','rejected','needs_correction')),
          candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[a-f0-9]{64}$'),
          decision_digest text NOT NULL CHECK (decision_digest ~ '^sha256:[a-f0-9]{64}$'), decided_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,review_decision_id),
          FOREIGN KEY (organization_id,workspace_id,generated_candidate_id) REFERENCES workspace.support_generated_document_candidates(organization_id,workspace_id,generated_candidate_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,print_validation_id) REFERENCES workspace.support_print_validation_results(organization_id,workspace_id,print_validation_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,authority_grant_id,authority_grant_version) REFERENCES workspace.support_professional_grants(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.support_finalized_document_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, finalized_document_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          generated_candidate_id uuid NOT NULL, print_validation_id uuid NOT NULL, review_decision_id uuid NOT NULL,
          finalizer_identity_id text NOT NULL CHECK (finalizer_identity_id !~ '^(model|service|integration):'),
          finalizer_grant_id uuid NOT NULL, finalizer_grant_version bigint NOT NULL,
          qualification_level text NOT NULL CHECK (qualification_level IN ('synthetic_semantic_final','production_print_ready')),
          document_digest text NOT NULL CHECK (document_digest ~ '^sha256:[a-f0-9]{64}$'), finalized_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,finalized_document_id,version),
          FOREIGN KEY (organization_id,workspace_id,generated_candidate_id) REFERENCES workspace.support_generated_document_candidates(organization_id,workspace_id,generated_candidate_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,print_validation_id) REFERENCES workspace.support_print_validation_results(organization_id,workspace_id,print_validation_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,review_decision_id) REFERENCES workspace.support_document_review_decisions(organization_id,workspace_id,review_decision_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,finalizer_grant_id,finalizer_grant_version) REFERENCES workspace.support_professional_grants(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT,
          CHECK (qualification_level<>'production_print_ready' OR finalizer_identity_id<>'' )
        );
        """
    )


def _create_geometry_and_commercial_chain() -> None:
    op.execute(
        """
        CREATE TABLE workspace.support_geometry_input_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, geometry_input_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          support_process_id uuid NOT NULL, geometry_kind text NOT NULL CHECK (geometry_kind IN ('design','as_built')),
          fact_id uuid NOT NULL, fact_version bigint NOT NULL, source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL,
          crs_ref text NOT NULL, reference_frame_ref text NOT NULL, unit_code text NOT NULL, precision_scale integer NOT NULL CHECK (precision_scale>=0),
          measurement_method_ref text NOT NULL, calibration_ref text, calibration_valid boolean NOT NULL,
          confirmation_decision_id uuid NOT NULL, confirmation_identity_kind text NOT NULL CHECK (confirmation_identity_kind='human'),
          coordinate_manifest_digest text NOT NULL CHECK (coordinate_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          input_digest text NOT NULL CHECK (input_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,geometry_input_id,version),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,fact_id,fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,confirmation_decision_id) REFERENCES workspace.confirmation_decisions(organization_id,workspace_id,confirmation_decision_id) ON DELETE RESTRICT,
          CHECK (geometry_kind<>'as_built' OR (calibration_ref IS NOT NULL AND calibration_valid))
        );
        CREATE TABLE workspace.support_executive_scheme_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, executive_scheme_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          support_process_id uuid NOT NULL, design_geometry_id uuid NOT NULL, design_geometry_version bigint NOT NULL,
          as_built_geometry_id uuid NOT NULL, as_built_geometry_version bigint NOT NULL,
          transformation_profile_version text NOT NULL CHECK (lower(transformation_profile_version)<>'latest'),
          tolerance_rule_trace_id uuid NOT NULL, semantic_geometry_fingerprint text NOT NULL CHECK (semantic_geometry_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('semantic_finalized','rendered_candidate','blocked')),
          blocker_codes text[] NOT NULL,
          finalizer_identity_id text NOT NULL CHECK (finalizer_identity_id !~ '^(model|service|integration):'),
          authority_grant_id uuid NOT NULL, authority_grant_version bigint NOT NULL,
          scheme_digest text NOT NULL CHECK (scheme_digest ~ '^sha256:[a-f0-9]{64}$'), finalized_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,executive_scheme_id,version),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,design_geometry_id,design_geometry_version) REFERENCES workspace.support_geometry_input_versions(organization_id,workspace_id,geometry_input_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,as_built_geometry_id,as_built_geometry_version) REFERENCES workspace.support_geometry_input_versions(organization_id,workspace_id,geometry_input_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,tolerance_rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,authority_grant_id,authority_grant_version) REFERENCES workspace.support_professional_grants(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT,
          CHECK (status='blocked' OR cardinality(blocker_codes)=0),
          CHECK (status<>'blocked' OR cardinality(blocker_codes)>0)
        );
        CREATE TABLE workspace.support_presented_volume_readiness (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, readiness_id uuid NOT NULL, support_process_id uuid NOT NULL,
          presented_volume_id uuid NOT NULL, presented_volume_version bigint NOT NULL, work_volume_id uuid NOT NULL, work_volume_version bigint NOT NULL,
          id_package_id uuid NOT NULL, id_package_version bigint NOT NULL, rule_trace_id uuid NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('eligible','blocked','indeterminate')), blocker_codes text[] NOT NULL,
          readiness_fingerprint text NOT NULL CHECK (readiness_fingerprint ~ '^sha256:[a-f0-9]{64}$'), evaluated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,readiness_id),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,presented_volume_id,presented_volume_version) REFERENCES workspace.presented_volume_versions(organization_id,workspace_id,presented_volume_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,work_volume_id,work_volume_version) REFERENCES workspace.work_volume_versions(organization_id,workspace_id,work_volume_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,id_package_id,id_package_version) REFERENCES workspace.id_package_versions(organization_id,workspace_id,id_package_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK (outcome='eligible' OR cardinality(blocker_codes)>0),
          CHECK (outcome<>'eligible' OR cardinality(blocker_codes)=0)
        );
        CREATE TABLE workspace.support_payment_readiness (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, payment_readiness_id uuid NOT NULL, support_process_id uuid NOT NULL,
          payment_claim_id uuid NOT NULL, payment_claim_version bigint NOT NULL,
          ks_document_id uuid NOT NULL, ks_document_version bigint NOT NULL,
          calculated_amount numeric NOT NULL, currency_code text NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('ready','blocked','indeterminate')), blocker_codes text[] NOT NULL,
          authority_grant_id uuid NOT NULL, authority_grant_version bigint NOT NULL, rule_trace_id uuid NOT NULL,
          readiness_fingerprint text NOT NULL CHECK (readiness_fingerprint ~ '^sha256:[a-f0-9]{64}$'), evaluated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,payment_readiness_id),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,payment_claim_id,payment_claim_version) REFERENCES workspace.payment_claim_versions(organization_id,workspace_id,payment_claim_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,ks_document_id,ks_document_version) REFERENCES workspace.ks_document_versions(organization_id,workspace_id,ks_document_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,authority_grant_id,authority_grant_version) REFERENCES workspace.support_professional_grants(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK (outcome='ready' OR cardinality(blocker_codes)>0),
          CHECK (outcome<>'ready' OR cardinality(blocker_codes)=0)
        );
        CREATE TABLE workspace.support_deliverable_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, deliverable_id uuid NOT NULL, version bigint NOT NULL CHECK (version>=1),
          support_process_id uuid NOT NULL, deliverable_kind text NOT NULL CHECK (deliverable_kind IN ('contract_execution_findings','pd_rd_analysis','id_package','executive_scheme','presented_volume_trace','ks_payment_trace')),
          input_manifest_digest text NOT NULL CHECK (input_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          status text NOT NULL CHECK (status IN ('draft','blocked','finalized')), blocker_codes text[] NOT NULL,
          finalization_decision_ref text, deliverable_digest text NOT NULL CHECK (deliverable_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,deliverable_id,version),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          CHECK (status<>'finalized' OR (finalization_decision_ref IS NOT NULL AND cardinality(blocker_codes)=0)),
          CHECK (status<>'blocked' OR cardinality(blocker_codes)>0)
        );
        CREATE TABLE workspace.support_terminal_outcomes (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, terminal_outcome_id uuid NOT NULL, support_process_id uuid NOT NULL,
          process_revision bigint NOT NULL, outcome text NOT NULL CHECK (outcome IN ('completed','blocked','failed','quarantined')),
          deliverable_refs text[] NOT NULL, blocker_codes text[] NOT NULL, uncertainty_codes text[] NOT NULL,
          archive_manifest_digest text, finalization_authority_ref text,
          product_ready boolean NOT NULL DEFAULT false CHECK (NOT product_ready),
          outcome_fingerprint text NOT NULL CHECK (outcome_fingerprint ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,terminal_outcome_id),
          FOREIGN KEY (organization_id,workspace_id,support_process_id) REFERENCES workspace.support_processes(organization_id,workspace_id,support_process_id) ON DELETE RESTRICT,
          CHECK (outcome<>'completed' OR (cardinality(deliverable_refs)>0 AND cardinality(blocker_codes)=0 AND archive_manifest_digest IS NOT NULL AND finalization_authority_ref IS NOT NULL)),
          CHECK (outcome='completed' OR cardinality(blocker_codes)>0)
        );
        """
    )


def _apply_guards_grants_and_rls() -> None:
    op.execute("GRANT USAGE ON SCHEMA platform,workspace,messaging,audit TO asd_support_service")
    op.execute(
        "GRANT SELECT ON "
        + ",".join(f"platform.{table}" for table in PLATFORM_TABLES)
        + ",platform.rule_set_versions,platform.required_document_type_versions TO asd_support_service"
    )
    op.execute(
        "GRANT SELECT ON "
        + ",".join(f"workspace.{table}" for table in READ_TABLES)
        + " TO asd_support_service"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.reject_support_version_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member') "
        "THEN RETURN OLD; END IF; RAISE EXCEPTION 'support version records are immutable'; END $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.guard_support_header_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member') "
        "THEN RETURN OLD; END IF; IF TG_OP='UPDATE' AND pg_has_role(session_user,'asd_support_service','member') "
        "AND NULLIF(current_setting('asd.support_operation_id',true),'') IS NOT NULL "
        "THEN RETURN NEW; END IF; RAISE EXCEPTION 'support state changes require service operation context'; END $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.require_support_mode() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF NOT EXISTS (SELECT 1 FROM workspace.mode_executions m WHERE m.organization_id=NEW.organization_id "
        "AND m.workspace_id=NEW.workspace_id AND m.mode_execution_id=NEW.mode_execution_id AND m.mode='Support') "
        "THEN RAISE EXCEPTION 'support process requires Support ModeExecution'; END IF; RETURN NEW; END $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.require_support_review_authority() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF NOT EXISTS (SELECT 1 FROM workspace.support_professional_grants g "
        "WHERE g.organization_id=NEW.organization_id AND g.workspace_id=NEW.workspace_id "
        "AND g.grant_id=NEW.authority_grant_id AND g.grant_version=NEW.authority_grant_version "
        "AND g.human_identity_id=NEW.human_identity_id AND g.capability='support.document.review' "
        "AND g.status='active' AND g.effective_from<=NEW.decided_at "
        "AND (g.effective_until IS NULL OR g.effective_until>NEW.decided_at)) "
        "THEN RAISE EXCEPTION 'qualified document-review authority is required'; END IF; RETURN NEW; END $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.require_support_finalization_authority() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "DECLARE reviewer text; review_outcome text; BEGIN "
        "SELECT human_identity_id,outcome INTO reviewer,review_outcome FROM workspace.support_document_review_decisions "
        "WHERE organization_id=NEW.organization_id AND workspace_id=NEW.workspace_id "
        "AND review_decision_id=NEW.review_decision_id; "
        "IF review_outcome IS DISTINCT FROM 'approved' OR reviewer=NEW.finalizer_identity_id THEN "
        "RAISE EXCEPTION 'approved independent review is required'; END IF; "
        "IF NOT EXISTS (SELECT 1 FROM workspace.support_professional_grants g "
        "WHERE g.organization_id=NEW.organization_id AND g.workspace_id=NEW.workspace_id "
        "AND g.grant_id=NEW.finalizer_grant_id AND g.grant_version=NEW.finalizer_grant_version "
        "AND g.human_identity_id=NEW.finalizer_identity_id AND g.capability='support.deliverable.finalize' "
        "AND g.status='active' AND g.effective_from<=NEW.finalized_at "
        "AND (g.effective_until IS NULL OR g.effective_until>NEW.finalized_at)) "
        "THEN RAISE EXCEPTION 'qualified finalization authority is required'; END IF; RETURN NEW; END $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION workspace.require_support_geometry_authority() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF NOT EXISTS (SELECT 1 FROM workspace.support_professional_grants g "
        "WHERE g.organization_id=NEW.organization_id AND g.workspace_id=NEW.workspace_id "
        "AND g.grant_id=NEW.authority_grant_id AND g.grant_version=NEW.authority_grant_version "
        "AND g.human_identity_id=NEW.finalizer_identity_id AND g.capability='support.geometry.finalize' "
        "AND g.status='active' AND g.effective_from<=NEW.finalized_at "
        "AND (g.effective_until IS NULL OR g.effective_until>NEW.finalized_at)) "
        "THEN RAISE EXCEPTION 'qualified geometry authority is required'; END IF; RETURN NEW; END $$"
    )
    predicate = (
        "organization_id = nullif(current_setting('asd.organization_id',true),'')::uuid "
        "AND workspace_id = nullif(current_setting('asd.workspace_id',true),'')::uuid"
    )
    for table in READ_TABLES:
        op.execute(
            f"CREATE POLICY {table}_support_read_scope_policy ON workspace.{table} "
            f"FOR SELECT TO asd_support_service USING ({predicate})"
        )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON messaging.workspace_idempotency TO asd_support_service"
    )
    op.execute("GRANT SELECT,INSERT ON messaging.workspace_outbox TO asd_support_service")
    op.execute("GRANT SELECT,INSERT ON audit.workspace_records TO asd_support_service")
    for qualified in (
        "messaging.workspace_idempotency",
        "messaging.workspace_outbox",
        "audit.workspace_records",
    ):
        table = qualified.split(".")[1]
        op.execute(
            f"CREATE POLICY {table}_support_scope_policy ON {qualified} FOR ALL TO asd_support_service "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    for table in WORKSPACE_TABLES:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_support_scope_policy ON workspace.{table} FOR ALL TO asd_support_service "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        privileges = "SELECT" if table == "support_professional_grants" else "SELECT,INSERT"
        op.execute(f"GRANT {privileges} ON workspace.{table} TO asd_support_service")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE POLICY {table}_destruction_scope_policy ON workspace.{table} FOR ALL TO asd_destruction_executor "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE TRIGGER {table}_support_write_fence BEFORE INSERT OR UPDATE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION workspace.enforce_material_write_fence()"
        )
        if table == "support_processes":
            op.execute(
                "CREATE TRIGGER support_process_mode_guard BEFORE INSERT OR UPDATE ON workspace.support_processes "
                "FOR EACH ROW EXECUTE FUNCTION workspace.require_support_mode()"
            )
            op.execute(
                "CREATE TRIGGER support_process_update_guard BEFORE UPDATE OR DELETE ON workspace.support_processes "
                "FOR EACH ROW EXECUTE FUNCTION workspace.guard_support_header_mutation()"
            )
        else:
            op.execute(
                f"CREATE TRIGGER {table}_immutable_guard BEFORE UPDATE OR DELETE ON workspace.{table} "
                "FOR EACH ROW EXECUTE FUNCTION workspace.reject_support_version_mutation()"
            )
    op.execute(
        "GRANT UPDATE (state,revision,current_fingerprint,updated_at) ON workspace.support_processes TO asd_support_service"
    )
    op.execute(
        "CREATE TRIGGER support_document_review_authority_guard BEFORE INSERT ON workspace.support_document_review_decisions "
        "FOR EACH ROW EXECUTE FUNCTION workspace.require_support_review_authority()"
    )
    op.execute(
        "CREATE TRIGGER support_document_finalization_authority_guard BEFORE INSERT ON workspace.support_finalized_document_versions "
        "FOR EACH ROW EXECUTE FUNCTION workspace.require_support_finalization_authority()"
    )
    op.execute(
        "CREATE TRIGGER support_geometry_authority_guard BEFORE INSERT ON workspace.support_executive_scheme_versions "
        "FOR EACH ROW EXECUTE FUNCTION workspace.require_support_geometry_authority()"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "WP-13 downgrade is destructive and allowed only in an explicitly disposable database"
        )
    for table in reversed(WORKSPACE_TABLES):
        op.execute(f"DROP TABLE workspace.{table}")
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE platform.{table}")
    for table in READ_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_support_read_scope_policy ON workspace.{table}")
    for qualified in (
        "messaging.workspace_idempotency",
        "messaging.workspace_outbox",
        "audit.workspace_records",
    ):
        table = qualified.split(".")[1]
        op.execute(f"DROP POLICY IF EXISTS {table}_support_scope_policy ON {qualified}")
    op.execute("DROP FUNCTION IF EXISTS workspace.require_support_geometry_authority()")
    op.execute("DROP FUNCTION IF EXISTS workspace.require_support_finalization_authority()")
    op.execute("DROP FUNCTION IF EXISTS workspace.require_support_review_authority()")
    op.execute("DROP FUNCTION IF EXISTS workspace.require_support_mode()")
    op.execute("DROP FUNCTION IF EXISTS workspace.guard_support_header_mutation()")
    op.execute("DROP FUNCTION IF EXISTS workspace.reject_support_version_mutation()")
