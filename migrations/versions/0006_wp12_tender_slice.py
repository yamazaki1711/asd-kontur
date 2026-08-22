"""Create the WP-12 Tender implementation slice.

Revision ID: 0006_wp12
Revises: 0005_wp11
Create Date: 2026-08-23
"""

from __future__ import annotations

import os

from alembic import op

revision = "0006_wp12"
down_revision = "0005_wp11"
branch_labels = None
depends_on = None

WORKSPACE_TABLES = (
    "tender_processes",
    "tender_scope_versions",
    "tender_corpus_items",
    "tender_completeness_assessments",
    "tender_clause_versions",
    "tender_requirement_versions",
    "tender_issue_versions",
    "tender_issue_evidence",
    "tender_professional_grants",
    "tender_finding_confirmation_decisions",
    "tender_disagreement_protocol_versions",
    "tender_disagreement_items",
    "tender_revised_contract_versions",
    "tender_revised_clause_versions",
    "tender_deliverable_versions",
    "tender_review_decisions",
    "tender_terminal_outcomes",
)

READ_TABLES = (
    "workspaces",
    "mode_executions",
    "source_versions",
    "source_locators",
    "evidence_links",
    "workspace_facts",
    "workspace_fact_versions",
    "rule_evaluations",
    "rule_traces",
    "kernel_finding_versions",
    "deliverable_inputs",
)


def upgrade() -> None:
    _create_role()
    _create_process_and_inputs()
    _create_analysis()
    _create_outputs_and_authority()
    _apply_guards_grants_and_rls()


def _create_role() -> None:
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_tender_service') "
        "THEN CREATE ROLE asd_tender_service NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; "
        "END IF; END $$"
    )


def _create_process_and_inputs() -> None:
    op.execute(
        """
        CREATE TABLE workspace.tender_processes (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, tender_process_id uuid NOT NULL,
          mode_execution_id uuid NOT NULL, process_definition_version text NOT NULL CHECK (lower(process_definition_version)<>'latest'),
          state text NOT NULL CHECK (state IN ('requested','corpus_assessed','requirements_determined','analyzed','drafted','waiting_for_authority','blocked','finalized')),
          revision bigint NOT NULL CHECK (revision>=1), rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          authority_profile_version text NOT NULL CHECK (lower(authority_profile_version)<>'latest'),
          contract_registry_version text NOT NULL CHECK (lower(contract_registry_version)<>'latest'),
          input_manifest_digest text NOT NULL CHECK (input_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          current_fingerprint text NOT NULL CHECK (current_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          correlation_id uuid NOT NULL, causation_id uuid, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,tender_process_id),
          FOREIGN KEY (organization_id,workspace_id,mode_execution_id) REFERENCES workspace.mode_executions(organization_id,workspace_id,mode_execution_id) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,mode_execution_id),
          CHECK (cardinality(ARRAY[process_definition_version,authority_profile_version,contract_registry_version])=3)
        );
        CREATE TABLE workspace.tender_scope_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, tender_process_id uuid NOT NULL, scope_version bigint NOT NULL CHECK (scope_version>=1),
          analysis_scope_version text NOT NULL CHECK (lower(analysis_scope_version)<>'latest'),
          source_class_allowlist text[] NOT NULL CHECK (cardinality(source_class_allowlist)>0),
          policy_versions text[] NOT NULL CHECK (cardinality(policy_versions)>0 AND NOT ('latest'=ANY(policy_versions))),
          purpose text NOT NULL, classification text NOT NULL, authority_profile_version text NOT NULL CHECK (lower(authority_profile_version)<>'latest'),
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          scope_digest text NOT NULL CHECK (scope_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,tender_process_id,scope_version),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.tender_corpus_items (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, tender_process_id uuid NOT NULL, corpus_item_id uuid NOT NULL,
          source_class text NOT NULL CHECK (source_class IN ('tender_documentation','draft_contract','contract_appendix','project_documentation','working_documentation','volume_sheet','specification','estimate','customer_regulation')),
          source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL, evidence_link_id uuid NOT NULL,
          admission_state text NOT NULL CHECK (admission_state IN ('accepted','rejected','unavailable')),
          item_digest text NOT NULL CHECK (item_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,corpus_item_id),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id) REFERENCES workspace.evidence_links(organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,tender_process_id,source_class,source_version_id,source_locator_id)
        );
        CREATE TABLE workspace.tender_completeness_assessments (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, assessment_id uuid NOT NULL, tender_process_id uuid NOT NULL,
          assessment_version bigint NOT NULL CHECK (assessment_version>=1), required_source_classes text[] NOT NULL,
          available_source_classes text[] NOT NULL, missing_source_classes text[] NOT NULL,
          optional_absent_source_classes text[] NOT NULL,
          status text NOT NULL CHECK (status IN ('complete','assessed_with_explicit_limits','blocked')),
          assessment_fingerprint text NOT NULL CHECK (assessment_fingerprint ~ '^sha256:[a-f0-9]{64}$'), assessed_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,assessment_id,assessment_version),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          CHECK (status<>'complete' OR cardinality(missing_source_classes)=0),
          CHECK (status<>'blocked' OR cardinality(missing_source_classes)>0)
        );
        """
    )


def _create_analysis() -> None:
    op.execute(
        """
        CREATE TABLE workspace.tender_clause_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, clause_id uuid NOT NULL, clause_version bigint NOT NULL CHECK (clause_version>=1),
          tender_process_id uuid NOT NULL, clause_key text NOT NULL, locator_label text NOT NULL,
          authority_layer text NOT NULL CHECK (authority_layer IN ('ntd','legislation','contract','customer_regulation','judicial_practice','expert_opinion')),
          source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL, evidence_link_id uuid NOT NULL,
          fact_id uuid NOT NULL, fact_version bigint NOT NULL CHECK (fact_version>=1), effective_edition_ref text,
          text_digest text NOT NULL CHECK (text_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,clause_id,clause_version),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id) REFERENCES workspace.evidence_links(organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,fact_id,fact_version) REFERENCES workspace.workspace_fact_versions(organization_id,workspace_id,fact_id,fact_version) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,tender_process_id,clause_key,clause_version)
        );
        CREATE TABLE workspace.tender_requirement_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, requirement_id uuid NOT NULL, requirement_version bigint NOT NULL CHECK (requirement_version>=1),
          tender_process_id uuid NOT NULL, requirement_key text NOT NULL, subject text NOT NULL CHECK (subject IN ('responsibility','deadline','acceptance','payment','price','volume','material','technical_requirement','authority','termination','geometry','source_completeness')),
          applicability text NOT NULL CHECK (applicability IN ('applicable','not_applicable','indeterminate')),
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          rule_trace_id uuid NOT NULL, required_source_classes text[] NOT NULL, evidence_link_ids uuid[] NOT NULL,
          uncertainty_code text, requirement_digest text NOT NULL CHECK (requirement_digest ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,requirement_id,requirement_version),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK (applicability<>'indeterminate' OR uncertainty_code IS NOT NULL)
        );
        CREATE TABLE workspace.tender_issue_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, issue_id uuid NOT NULL, issue_version bigint NOT NULL CHECK (issue_version>=1),
          tender_process_id uuid NOT NULL, issue_kind text NOT NULL CHECK (issue_kind IN ('contract_risk','conflict','gap','uncertainty','blocker','missing_work','missing_material','geometry_blocker')),
          subject text NOT NULL CHECK (subject IN ('responsibility','deadline','acceptance','payment','price','volume','material','technical_requirement','authority','termination','geometry','source_completeness')),
          severity text NOT NULL CHECK (severity IN ('info','low','medium','high','blocking')),
          applicability text NOT NULL CHECK (applicability IN ('applicable','not_applicable','indeterminate')),
          clause_id uuid, clause_version bigint, requirement_id uuid, requirement_version bigint,
          kernel_finding_id uuid, kernel_finding_version bigint,
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          rule_trace_id uuid, uncertainty_code text, recommendation_code text, recommendation_text text, consequence_code text NOT NULL,
          status text NOT NULL CHECK (status IN ('draft','validated','blocked','resolved','superseded')),
          finding_fingerprint text NOT NULL CHECK (finding_fingerprint ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,issue_id,issue_version),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,clause_id,clause_version) REFERENCES workspace.tender_clause_versions(organization_id,workspace_id,clause_id,clause_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,requirement_id,requirement_version) REFERENCES workspace.tender_requirement_versions(organization_id,workspace_id,requirement_id,requirement_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,kernel_finding_id,kernel_finding_version) REFERENCES workspace.kernel_finding_versions(organization_id,workspace_id,finding_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          CHECK (applicability<>'indeterminate' OR uncertainty_code IS NOT NULL),
          CHECK (issue_kind IN ('gap','uncertainty','missing_work','missing_material','geometry_blocker') OR (clause_id IS NOT NULL AND rule_trace_id IS NOT NULL)),
          CHECK (issue_kind NOT IN ('missing_work','missing_material','geometry_blocker') OR kernel_finding_id IS NOT NULL)
        );
        CREATE TABLE workspace.tender_issue_evidence (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, issue_id uuid NOT NULL, issue_version bigint NOT NULL,
          evidence_link_id uuid NOT NULL, source_version_id uuid NOT NULL, source_locator_id uuid NOT NULL, evidence_role text NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,issue_id,issue_version,evidence_link_id),
          FOREIGN KEY (organization_id,workspace_id,issue_id,issue_version) REFERENCES workspace.tender_issue_versions(organization_id,workspace_id,issue_id,issue_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,evidence_link_id) REFERENCES workspace.evidence_links(organization_id,workspace_id,evidence_link_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_locator_id) REFERENCES workspace.source_locators(organization_id,workspace_id,source_locator_id) ON DELETE RESTRICT
        );
        """
    )


def _create_outputs_and_authority() -> None:
    op.execute(
        """
        CREATE TABLE workspace.tender_professional_grants (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, grant_id uuid NOT NULL, grant_version bigint NOT NULL CHECK (grant_version>=1),
          human_identity_id text NOT NULL CHECK (human_identity_id !~ '^(model|service|integration):'),
          capability text NOT NULL CHECK (capability IN ('tender.legal.review','tender.legal.finalize')),
          professional_qualification_ref text NOT NULL, authority_reference text NOT NULL,
          status text NOT NULL CHECK (status IN ('active','suspended','revoked','expired')),
          effective_from timestamptz NOT NULL, effective_until timestamptz,
          integrity_digest text NOT NULL CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,grant_id,grant_version),
          FOREIGN KEY (organization_id,workspace_id) REFERENCES workspace.workspaces(organization_id,workspace_id) ON DELETE RESTRICT,
          CHECK (effective_until IS NULL OR effective_until>effective_from)
        );
        CREATE TABLE workspace.tender_finding_confirmation_decisions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, decision_id uuid NOT NULL,
          tender_process_id uuid NOT NULL, issue_id uuid NOT NULL, issue_version bigint NOT NULL,
          human_identity_id text NOT NULL CHECK (human_identity_id !~ '^(model|service|integration):'),
          grant_id uuid NOT NULL, grant_version bigint NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('confirmed','rejected','needs_evidence','conflict')),
          reason_code text NOT NULL, authority_reference text NOT NULL,
          decision_fingerprint text NOT NULL CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          correlation_id uuid NOT NULL, causation_id uuid NOT NULL, decided_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,decision_id),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,issue_id,issue_version) REFERENCES workspace.tender_issue_versions(organization_id,workspace_id,issue_id,issue_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,grant_id,grant_version) REFERENCES workspace.tender_professional_grants(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,issue_id,issue_version,outcome,grant_id,grant_version)
        );
        CREATE TABLE workspace.tender_disagreement_protocol_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, protocol_id uuid NOT NULL, protocol_version bigint NOT NULL CHECK (protocol_version>=1),
          tender_process_id uuid NOT NULL, source_manifest_digest text NOT NULL CHECK (source_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          evidence_manifest_digest text NOT NULL CHECK (evidence_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          state text NOT NULL CHECK (state IN ('draft','reviewed','finalized','blocked','superseded')),
          blocker_issue_ids uuid[] NOT NULL, uncertainty_issue_ids uuid[] NOT NULL,
          protocol_fingerprint text NOT NULL CHECK (protocol_fingerprint ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,protocol_id,protocol_version),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          CHECK (state<>'finalized' OR cardinality(blocker_issue_ids)=0)
        );
        CREATE TABLE workspace.tender_disagreement_items (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, protocol_id uuid NOT NULL, protocol_version bigint NOT NULL,
          item_id uuid NOT NULL, ordinal integer NOT NULL CHECK (ordinal>=1), clause_id uuid NOT NULL, clause_version bigint NOT NULL,
          issue_id uuid NOT NULL, issue_version bigint NOT NULL, proposed_clause_text text NOT NULL,
          consequence_code text NOT NULL, rule_trace_id uuid NOT NULL, evidence_link_ids uuid[] NOT NULL CHECK (cardinality(evidence_link_ids)>0),
          uncertainty_issue_ids uuid[] NOT NULL, finding_decision_id uuid NOT NULL,
          item_fingerprint text NOT NULL CHECK (item_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,protocol_id,protocol_version,item_id),
          FOREIGN KEY (organization_id,workspace_id,protocol_id,protocol_version) REFERENCES workspace.tender_disagreement_protocol_versions(organization_id,workspace_id,protocol_id,protocol_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,clause_id,clause_version) REFERENCES workspace.tender_clause_versions(organization_id,workspace_id,clause_id,clause_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,issue_id,issue_version) REFERENCES workspace.tender_issue_versions(organization_id,workspace_id,issue_id,issue_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,rule_trace_id) REFERENCES workspace.rule_traces(organization_id,workspace_id,rule_trace_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,finding_decision_id) REFERENCES workspace.tender_finding_confirmation_decisions(organization_id,workspace_id,decision_id) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,protocol_id,protocol_version,ordinal)
        );
        CREATE TABLE workspace.tender_revised_contract_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, revised_contract_id uuid NOT NULL, revised_contract_version bigint NOT NULL CHECK (revised_contract_version>=1),
          tender_process_id uuid NOT NULL, protocol_id uuid NOT NULL, protocol_version bigint NOT NULL,
          source_contract_version_id uuid NOT NULL, state text NOT NULL CHECK (state IN ('draft','reviewed','finalized','blocked','superseded')),
          source_manifest_digest text NOT NULL CHECK (source_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          contract_fingerprint text NOT NULL CHECK (contract_fingerprint ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,revised_contract_id,revised_contract_version),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,protocol_id,protocol_version) REFERENCES workspace.tender_disagreement_protocol_versions(organization_id,workspace_id,protocol_id,protocol_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_contract_version_id) REFERENCES workspace.source_versions(organization_id,workspace_id,source_version_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.tender_revised_clause_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, revised_contract_id uuid NOT NULL, revised_contract_version bigint NOT NULL,
          revised_clause_id uuid NOT NULL, ordinal integer NOT NULL CHECK (ordinal>=1), source_clause_id uuid NOT NULL, source_clause_version bigint NOT NULL,
          issue_id uuid NOT NULL, issue_version bigint NOT NULL, disagreement_item_id uuid NOT NULL, decision_id uuid NOT NULL,
          revised_text text NOT NULL, revised_text_digest text NOT NULL CHECK (revised_text_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (organization_id,workspace_id,revised_contract_id,revised_contract_version,revised_clause_id),
          FOREIGN KEY (organization_id,workspace_id,revised_contract_id,revised_contract_version) REFERENCES workspace.tender_revised_contract_versions(organization_id,workspace_id,revised_contract_id,revised_contract_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,source_clause_id,source_clause_version) REFERENCES workspace.tender_clause_versions(organization_id,workspace_id,clause_id,clause_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,issue_id,issue_version) REFERENCES workspace.tender_issue_versions(organization_id,workspace_id,issue_id,issue_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,decision_id) REFERENCES workspace.tender_finding_confirmation_decisions(organization_id,workspace_id,decision_id) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.tender_deliverable_versions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, deliverable_id uuid NOT NULL, deliverable_version bigint NOT NULL CHECK (deliverable_version>=1),
          tender_process_id uuid NOT NULL, deliverable_kind text NOT NULL CHECK (deliverable_kind IN ('disagreement_protocol','revised_contract','tender_risk_register','tender_gap_register','tender_pd_rd_analysis')),
          typed_item_ids uuid[] NOT NULL CHECK (cardinality(typed_item_ids)>0),
          source_manifest_digest text NOT NULL CHECK (source_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          evidence_manifest_digest text NOT NULL CHECK (evidence_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          rule_set_version_id uuid NOT NULL REFERENCES platform.rule_set_versions(rule_set_version_id) ON DELETE RESTRICT,
          contract_key text NOT NULL, contract_version text NOT NULL CHECK (lower(contract_version)<>'latest'),
          schema_id text NOT NULL, schema_version text NOT NULL CHECK (lower(schema_version)<>'latest'),
          state text NOT NULL CHECK (state IN ('draft','reviewed','finalized','blocked','superseded')),
          blocker_issue_ids uuid[] NOT NULL, uncertainty_issue_ids uuid[] NOT NULL,
          review_decision_id uuid, finalization_decision_id uuid,
          deliverable_fingerprint text NOT NULL CHECK (deliverable_fingerprint ~ '^sha256:[a-f0-9]{64}$'), recorded_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,deliverable_id,deliverable_version),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,tender_process_id,deliverable_kind,deliverable_version),
          CHECK (state<>'finalized' OR (cardinality(blocker_issue_ids)=0 AND review_decision_id IS NOT NULL AND finalization_decision_id IS NOT NULL))
        );
        CREATE TABLE workspace.tender_review_decisions (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, decision_id uuid NOT NULL, tender_process_id uuid NOT NULL,
          decision_kind text NOT NULL CHECK (decision_kind IN ('legal_review','finalization')),
          deliverable_id uuid NOT NULL, deliverable_version bigint NOT NULL,
          human_identity_id text NOT NULL CHECK (human_identity_id !~ '^(model|service|integration):'),
          grant_id uuid NOT NULL, grant_version bigint NOT NULL, outcome text NOT NULL CHECK (outcome IN ('approved','rejected','needs_revision','blocked')),
          reason_code text NOT NULL, authority_reference text NOT NULL,
          decision_fingerprint text NOT NULL CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'), correlation_id uuid NOT NULL, causation_id uuid NOT NULL, decided_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,decision_id),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,deliverable_id,deliverable_version) REFERENCES workspace.tender_deliverable_versions(organization_id,workspace_id,deliverable_id,deliverable_version) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,grant_id,grant_version) REFERENCES workspace.tender_professional_grants(organization_id,workspace_id,grant_id,grant_version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.tender_terminal_outcomes (
          organization_id uuid NOT NULL, workspace_id uuid NOT NULL, terminal_outcome_id uuid NOT NULL, tender_process_id uuid NOT NULL,
          process_revision bigint NOT NULL CHECK (process_revision>=1),
          outcome text NOT NULL CHECK (outcome IN ('successful','blocked_incomplete_corpus','blocked_unresolved_conflict','blocked_material_uncertainty','blocked_authority')),
          deliverable_ids uuid[] NOT NULL, limitation_codes text[] NOT NULL, reviewer_decision_id uuid, finalization_decision_id uuid,
          product_ready boolean NOT NULL DEFAULT false CHECK (product_ready=false),
          outcome_fingerprint text NOT NULL CHECK (outcome_fingerprint ~ '^sha256:[a-f0-9]{64}$'), completed_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,terminal_outcome_id),
          UNIQUE (organization_id,workspace_id,tender_process_id,process_revision),
          FOREIGN KEY (organization_id,workspace_id,tender_process_id) REFERENCES workspace.tender_processes(organization_id,workspace_id,tender_process_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,reviewer_decision_id) REFERENCES workspace.tender_review_decisions(organization_id,workspace_id,decision_id) ON DELETE RESTRICT,
          FOREIGN KEY (organization_id,workspace_id,finalization_decision_id) REFERENCES workspace.tender_review_decisions(organization_id,workspace_id,decision_id) ON DELETE RESTRICT,
          CHECK (outcome<>'successful' OR (reviewer_decision_id IS NOT NULL AND finalization_decision_id IS NOT NULL AND cardinality(deliverable_ids)=5))
        );
        """
    )


def _apply_guards_grants_and_rls() -> None:
    predicate = (
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid"
    )
    op.execute("GRANT USAGE ON SCHEMA platform,workspace,messaging,audit TO asd_tender_service")
    op.execute(
        "GRANT SELECT ON platform.rule_set_versions,platform.rule_versions,platform.rule_version_states,platform.rule_set_memberships TO asd_tender_service"
    )
    op.execute(
        "GRANT SELECT ON "
        + ",".join(f"workspace.{table}" for table in READ_TABLES)
        + " TO asd_tender_service"
    )
    for table in READ_TABLES:
        op.execute(
            f"CREATE POLICY {table}_tender_read_scope_policy ON workspace.{table} "
            f"FOR SELECT TO asd_tender_service USING ({predicate})"
        )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON messaging.workspace_idempotency TO asd_tender_service"
    )
    op.execute("GRANT SELECT,INSERT ON messaging.workspace_outbox TO asd_tender_service")
    op.execute("GRANT SELECT,INSERT ON audit.workspace_records TO asd_tender_service")
    for qualified in (
        "messaging.workspace_idempotency",
        "messaging.workspace_outbox",
        "audit.workspace_records",
    ):
        table = qualified.split(".")[1]
        op.execute(
            f"CREATE POLICY {table}_tender_scope_policy ON {qualified} FOR ALL TO asd_tender_service "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION workspace.guard_tender_process_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member') THEN RETURN OLD; END IF;
          IF TG_OP='UPDATE' AND pg_has_role(session_user,'asd_tender_service','member')
             AND NULLIF(current_setting('asd.tender_operation_id',true),'') IS NOT NULL
             AND NEW.revision=OLD.revision+1 THEN RETURN NEW; END IF;
          RAISE EXCEPTION 'Tender process mutation requires controlled service path' USING ERRCODE='42501';
        END $$;
        CREATE OR REPLACE FUNCTION workspace.reject_tender_version_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' AND pg_has_role(session_user,'asd_destruction_executor','member') THEN RETURN OLD; END IF;
          RAISE EXCEPTION 'immutable Tender record cannot be mutated' USING ERRCODE='55000';
        END $$;
        """
    )
    for table in WORKSPACE_TABLES:
        op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tender_scope_policy ON workspace.{table} FOR ALL TO asd_tender_service "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_app_scope_policy ON workspace.{table} FOR SELECT TO asd_app USING ({predicate})"
        )
        op.execute(
            f"CREATE POLICY {table}_destruction_scope_policy ON workspace.{table} FOR ALL TO asd_destruction_executor "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_tender_service")
        op.execute(f"GRANT SELECT ON workspace.{table} TO asd_app")
        op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
        op.execute(
            f"CREATE TRIGGER trg_{table}_write_fence BEFORE INSERT OR UPDATE OR DELETE ON workspace.{table} "
            "FOR EACH ROW EXECUTE FUNCTION workspace.enforce_material_write_fence()"
        )
        guard = (
            "workspace.guard_tender_process_mutation()"
            if table == "tender_processes"
            else "workspace.reject_tender_version_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_mutation_guard BEFORE UPDATE OR DELETE ON workspace.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION {guard}"
        )
    op.execute(
        "GRANT UPDATE (state,revision,current_fingerprint,updated_at) ON workspace.tender_processes TO asd_tender_service"
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "destructive downgrade is allowed only for a disposable development/test database"
        )
    for table in reversed(WORKSPACE_TABLES):
        op.execute(f"DROP TABLE IF EXISTS workspace.{table} CASCADE")
    for table in READ_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tender_read_scope_policy ON workspace.{table}")
    for qualified in (
        "messaging.workspace_idempotency",
        "messaging.workspace_outbox",
        "audit.workspace_records",
    ):
        table = qualified.split(".")[1]
        op.execute(f"DROP POLICY IF EXISTS {table}_tender_scope_policy ON {qualified}")
    op.execute("DROP FUNCTION IF EXISTS workspace.guard_tender_process_mutation()")
    op.execute("DROP FUNCTION IF EXISTS workspace.reject_tender_version_mutation()")
