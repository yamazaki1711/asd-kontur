"""Add evidence-bound normative rule candidate and decision lineage.

Revision ID: 0024_rule_activation_vertical
Revises: 0023_ntd_remediation
Create Date: 2026-08-26
"""

from __future__ import annotations

from alembic import op

revision = "0024_rule_activation_vertical"
down_revision = "0023_ntd_remediation"
branch_labels = None
depends_on = None

TABLES = (
    "normative_rule_candidates",
    "normative_rule_qualification_decisions",
    "normative_rule_activation_outcomes",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform.normative_rule_candidates (
          normative_rule_candidate_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          normative_document_id uuid NOT NULL
            REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          normative_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL
            REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          normative_provision_id uuid NOT NULL,
          normative_provision_version bigint NOT NULL,
          source_locator_id uuid NOT NULL
            REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          structural_path text NOT NULL,
          verbatim_text text NOT NULL,
          verbatim_digest text NOT NULL CHECK (verbatim_digest ~ '^sha256:[a-f0-9]{64}$'),
          deontic_type text NOT NULL CHECK (deontic_type IN ('obligation','prohibition','permission')),
          actor jsonb NOT NULL,
          regulated_object jsonb NOT NULL,
          required_action jsonb NOT NULL,
          applicability_predicate jsonb NOT NULL,
          conditions jsonb NOT NULL,
          exceptions jsonb NOT NULL,
          output_contract jsonb NOT NULL,
          semantic_evidence_bindings jsonb NOT NULL,
          interpretation_profile_version text NOT NULL CHECK (lower(interpretation_profile_version)<>'latest'),
          semantic_fingerprint text NOT NULL UNIQUE CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL,
          supersedes_version bigint,
          PRIMARY KEY (normative_rule_candidate_id,version),
          FOREIGN KEY (normative_provision_id,normative_provision_version)
            REFERENCES platform.normative_provision_versions(normative_provision_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (normative_rule_candidate_id,supersedes_version)
            REFERENCES platform.normative_rule_candidates(normative_rule_candidate_id,version)
            ON DELETE RESTRICT,
          CHECK (length(structural_path)>0 AND length(verbatim_text)>0),
          CHECK (jsonb_typeof(semantic_evidence_bindings)='array' AND jsonb_array_length(semantic_evidence_bindings)>=4),
          CHECK ((version=1 AND supersedes_version IS NULL) OR (version>1 AND supersedes_version=version-1)),
          UNIQUE (normative_provision_id,normative_provision_version,semantic_fingerprint)
        );
        CREATE TABLE platform.normative_rule_qualification_decisions (
          qualification_decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          normative_rule_candidate_id uuid NOT NULL,
          normative_rule_candidate_version bigint NOT NULL,
          status text NOT NULL CHECK (status IN ('qualified','blocked','rejected')),
          gate_results jsonb NOT NULL CHECK (jsonb_typeof(gate_results)='array'),
          qualification_profile_version text NOT NULL CHECK (lower(qualification_profile_version)<>'latest'),
          test_manifest_digest text NOT NULL CHECK (test_manifest_digest ~ '^sha256:[a-f0-9]{64}$'),
          decision_fingerprint text NOT NULL UNIQUE CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          qualified_by_identity_id text NOT NULL,
          qualification_decision_ref text NOT NULL,
          decided_at timestamptz NOT NULL,
          supersedes_version bigint,
          PRIMARY KEY (qualification_decision_id,version),
          FOREIGN KEY (normative_rule_candidate_id,normative_rule_candidate_version)
            REFERENCES platform.normative_rule_candidates(normative_rule_candidate_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (qualification_decision_id,supersedes_version)
            REFERENCES platform.normative_rule_qualification_decisions(qualification_decision_id,version)
            ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR (version>1 AND supersedes_version=version-1))
        );
        CREATE TABLE platform.normative_rule_activation_outcomes (
          rule_activation_outcome_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          normative_rule_candidate_id uuid NOT NULL,
          normative_rule_candidate_version bigint NOT NULL,
          qualification_decision_id uuid NOT NULL,
          qualification_decision_version bigint NOT NULL,
          rule_version_id uuid REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          edition_activation_decision_id uuid,
          edition_activation_decision_version bigint,
          status text NOT NULL CHECK (status IN ('active','not_activated','blocked')),
          reason_code text NOT NULL,
          edition_activation_status text NOT NULL,
          rule_lifecycle_status text,
          decision_fingerprint text NOT NULL UNIQUE CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          authority_identity_id text,
          authority_decision_ref text NOT NULL,
          decided_at timestamptz NOT NULL,
          supersedes_version bigint,
          PRIMARY KEY (rule_activation_outcome_id,version),
          FOREIGN KEY (normative_rule_candidate_id,normative_rule_candidate_version)
            REFERENCES platform.normative_rule_candidates(normative_rule_candidate_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (qualification_decision_id,qualification_decision_version)
            REFERENCES platform.normative_rule_qualification_decisions(qualification_decision_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (edition_activation_decision_id,edition_activation_decision_version)
            REFERENCES platform.normative_activation_decisions(activation_decision_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (rule_activation_outcome_id,supersedes_version)
            REFERENCES platform.normative_rule_activation_outcomes(rule_activation_outcome_id,version)
            ON DELETE RESTRICT,
          CHECK ((edition_activation_decision_id IS NULL)=(edition_activation_decision_version IS NULL)),
          CHECK (status<>'active' OR (rule_version_id IS NOT NULL AND edition_activation_decision_id IS NOT NULL AND authority_identity_id IS NOT NULL)),
          CHECK ((version=1 AND supersedes_version IS NULL) OR (version>1 AND supersedes_version=version-1))
        );
        """
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON platform.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )
        op.execute(f"GRANT SELECT,INSERT ON platform.{table} TO asd_ntd_ingestion_service")
        op.execute(
            f"GRANT SELECT ON platform.{table} TO "
            "asd_ntd_gateway_service,asd_platform_curator,asd_app"
        )
    op.execute(
        "ALTER TABLE platform.ntd_backup_manifests "
        "ADD COLUMN rule_candidate_fingerprints jsonb NOT NULL DEFAULT '[]'::jsonb, "
        "ADD COLUMN rule_qualification_fingerprints jsonb NOT NULL DEFAULT '[]'::jsonb, "
        "ADD COLUMN rule_activation_fingerprints jsonb NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE platform.ntd_backup_manifests "
        "DROP COLUMN rule_activation_fingerprints, "
        "DROP COLUMN rule_qualification_fingerprints, "
        "DROP COLUMN rule_candidate_fingerprints"
    )
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE platform.{table}")
