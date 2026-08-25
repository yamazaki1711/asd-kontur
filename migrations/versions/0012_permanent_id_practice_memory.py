"""Add permanent practice-memory releases, context policy and backup contracts.

Revision ID: 0012_id_memory
Revises: 0011_id_intelligence
"""

from __future__ import annotations

import os

from alembic import op

revision = "0012_id_memory"
down_revision = "0011_id_intelligence"
branch_labels = None
depends_on = None

PLATFORM_TABLES = (
    "context_assembly_policies",
    "practice_intelligence_releases",
    "practice_memory_backup_manifests",
)

PROJECTION_TABLES = ("practice_intelligence_projection_manifests",)


def upgrade() -> None:
    op.execute(
        """
        DO $$ DECLARE constraint_name name; BEGIN
          SELECT conname INTO constraint_name FROM pg_constraint
          WHERE conrelid='platform.practice_intelligence_construction_manifests'::regclass
            AND contype='c' AND pg_get_constraintdef(oid) LIKE '%authority_layer%';
          IF constraint_name IS NOT NULL THEN
            EXECUTE format('ALTER TABLE platform.practice_intelligence_construction_manifests DROP CONSTRAINT %I', constraint_name);
          END IF;
        END $$;
        ALTER TABLE platform.practice_intelligence_construction_manifests
          ADD CONSTRAINT pi_construct_authority_ck
          CHECK (authority_layer IN ('methodological_guidance','methodological_practice'));
        DO $$ DECLARE constraint_name name; BEGIN
          SELECT conname INTO constraint_name FROM pg_constraint
          WHERE conrelid='platform.practice_intelligence_units'::regclass
            AND contype='c' AND pg_get_constraintdef(oid) LIKE '%authority_layer%';
          IF constraint_name IS NOT NULL THEN
            EXECUTE format('ALTER TABLE platform.practice_intelligence_units DROP CONSTRAINT %I', constraint_name);
          END IF;
        END $$;
        ALTER TABLE platform.practice_intelligence_units
          ADD CONSTRAINT pi_unit_authority_ck
          CHECK (authority_layer IN ('methodological_guidance','methodological_practice'));
        DO $$ DECLARE constraint_name name; BEGIN
          SELECT conname INTO constraint_name FROM pg_constraint
          WHERE conrelid='platform.practice_playbooks'::regclass
            AND contype='c' AND pg_get_constraintdef(oid) LIKE '%authority_layer%';
          IF constraint_name IS NOT NULL THEN
            EXECUTE format('ALTER TABLE platform.practice_playbooks DROP CONSTRAINT %I', constraint_name);
          END IF;
        END $$;
        ALTER TABLE platform.practice_playbooks
          ADD CONSTRAINT pi_playbook_authority_ck
          CHECK (authority_layer IN ('methodological_guidance','methodological_practice'));
        DO $$ DECLARE constraint_name name; BEGIN
          SELECT conname INTO constraint_name FROM pg_constraint
          WHERE conrelid='platform.practice_intelligence_units'::regclass
            AND contype='c' AND pg_get_constraintdef(oid) LIKE '%intelligence_kind%';
          IF constraint_name IS NOT NULL THEN
            EXECUTE format('ALTER TABLE platform.practice_intelligence_units DROP CONSTRAINT %I', constraint_name);
          END IF;
        END $$;
        ALTER TABLE platform.practice_intelligence_units
          ADD CONSTRAINT pi_unit_kind_ck
          CHECK (intelligence_kind IN (
            'id_practice_principle','id_workflow_step','form_completion_guidance',
            'field_completion_guidance','attention_point','allowed_practice_variant',
            'practice_rationale','common_failure_pattern','verification_checklist',
            'completeness_guidance','journal_selection_guidance',
            'document_dependency_guidance','completion_instruction',
            'signer_role_guidance','visual_completion_example'));

        CREATE TABLE platform.context_assembly_policies (
          policy_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          policy_key text NOT NULL,
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          allowed_modes jsonb NOT NULL,
          allowed_purposes jsonb NOT NULL,
          selector_dimensions jsonb NOT NULL,
          max_intelligence_units integer NOT NULL CHECK (max_intelligence_units BETWEEN 1 AND 100),
          max_playbooks integer NOT NULL CHECK (max_playbooks BETWEEN 0 AND 20),
          authority_layer text NOT NULL CHECK (authority_layer='methodological_practice'),
          retention_class text NOT NULL CHECK (retention_class='permanent_platform_core'),
          state text NOT NULL CHECK (state IN ('active','superseded','suspended')),
          policy_fingerprint text NOT NULL UNIQUE CHECK (policy_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          owner_decision_ref text NOT NULL,
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (policy_id,version),
          UNIQUE (policy_key,version)
        );
        CREATE TABLE platform.practice_intelligence_releases (
          release_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          construction_manifest_id uuid NOT NULL REFERENCES platform.practice_intelligence_construction_manifests(construction_manifest_id) ON DELETE RESTRICT,
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          context_assembly_policy_id uuid NOT NULL,
          context_assembly_policy_version bigint NOT NULL,
          authority_layer text NOT NULL CHECK (authority_layer='methodological_practice'),
          retention_class text NOT NULL CHECK (retention_class='permanent_platform_core'),
          canonical_semantic_fingerprint text NOT NULL UNIQUE CHECK (canonical_semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          publication_status text NOT NULL CHECK (publication_status IN ('partial_with_explicit_gaps','complete')),
          product_ready boolean NOT NULL DEFAULT false CHECK (product_ready=false),
          owner_decision_ref text NOT NULL,
          published_at timestamptz NOT NULL,
          PRIMARY KEY (release_id,version),
          UNIQUE (construction_manifest_id,context_assembly_policy_id,context_assembly_policy_version),
          FOREIGN KEY (context_assembly_policy_id,context_assembly_policy_version)
            REFERENCES platform.context_assembly_policies(policy_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.practice_memory_backup_manifests (
          backup_manifest_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          release_id uuid NOT NULL,
          release_version bigint NOT NULL,
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          source_object_digest text NOT NULL CHECK (source_object_digest ~ '^sha256:[a-f0-9]{64}$'),
          construction_manifest_id uuid NOT NULL REFERENCES platform.practice_intelligence_construction_manifests(construction_manifest_id) ON DELETE RESTRICT,
          construction_fingerprint text NOT NULL CHECK (construction_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          context_assembly_policy_id uuid NOT NULL,
          context_assembly_policy_version bigint NOT NULL,
          context_assembly_policy_fingerprint text NOT NULL CHECK (context_assembly_policy_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          canonical_semantic_fingerprint text NOT NULL CHECK (canonical_semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          projection_fingerprints jsonb NOT NULL,
          backup_object_reference text NOT NULL,
          retention_class text NOT NULL CHECK (retention_class='permanent_platform_core'),
          integrity_status text NOT NULL CHECK (integrity_status IN ('recorded','verified','failed')),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (backup_manifest_id,version),
          FOREIGN KEY (release_id,release_version) REFERENCES platform.practice_intelligence_releases(release_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (context_assembly_policy_id,context_assembly_policy_version)
            REFERENCES platform.context_assembly_policies(policy_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE projection.practice_intelligence_projection_manifests (
          projection_manifest_id uuid PRIMARY KEY,
          release_id uuid NOT NULL,
          release_version bigint NOT NULL,
          projection_kind text NOT NULL CHECK (projection_kind IN ('exact','fts','vector','sparse','typed_graph')),
          projection_version text NOT NULL,
          source_semantic_fingerprint text NOT NULL CHECK (source_semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          projection_fingerprint text CHECK (projection_fingerprint IS NULL OR projection_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          state text NOT NULL CHECK (state IN ('absent','building','ready','stale','failed')),
          rebuilt_at timestamptz,
          UNIQUE (release_id,release_version,projection_kind,projection_version),
          FOREIGN KEY (release_id,release_version) REFERENCES platform.practice_intelligence_releases(release_id,version) ON DELETE RESTRICT,
          CHECK (state<>'ready' OR (projection_fingerprint IS NOT NULL AND rebuilt_at IS NOT NULL))
        );
        """
    )
    op.execute(
        "GRANT USAGE ON SCHEMA platform,projection TO "
        "asd_guidance_ingestion_service,asd_guidance_gateway_service"
    )
    for table in PLATFORM_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON platform.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )
        op.execute(f"GRANT SELECT ON platform.{table} TO asd_guidance_gateway_service")
        op.execute(f"GRANT SELECT,INSERT ON platform.{table} TO asd_guidance_ingestion_service")
    for table in PROJECTION_TABLES:
        op.execute(f"GRANT SELECT ON projection.{table} TO asd_guidance_gateway_service")
        op.execute(
            f"GRANT SELECT,INSERT,UPDATE,DELETE ON projection.{table} "
            "TO asd_guidance_ingestion_service"
        )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Permanent practice-memory downgrade requires a disposable database")
    for table in reversed(PROJECTION_TABLES):
        op.execute(f"DROP TABLE projection.{table}")
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE platform.{table}")
    op.execute(
        """
        ALTER TABLE platform.practice_intelligence_units
          DROP CONSTRAINT pi_unit_kind_ck;
        ALTER TABLE platform.practice_intelligence_units
          ADD CONSTRAINT practice_intelligence_units_intelligence_kind_check
          CHECK (intelligence_kind IN (
            'id_practice_principle','id_workflow_step','form_completion_guidance',
            'field_completion_guidance','attention_point','allowed_practice_variant',
            'practice_rationale','common_failure_pattern','verification_checklist',
            'completeness_guidance','journal_selection_guidance',
            'document_dependency_guidance','visual_completion_example'));
        ALTER TABLE platform.practice_intelligence_construction_manifests
          DROP CONSTRAINT pi_construct_authority_ck;
        ALTER TABLE platform.practice_intelligence_construction_manifests
          ADD CONSTRAINT practice_intelligence_construction_manifests_authority_layer_check
          CHECK (authority_layer='methodological_guidance');
        ALTER TABLE platform.practice_intelligence_units
          DROP CONSTRAINT pi_unit_authority_ck;
        ALTER TABLE platform.practice_intelligence_units
          ADD CONSTRAINT practice_intelligence_units_authority_layer_check
          CHECK (authority_layer='methodological_guidance');
        ALTER TABLE platform.practice_playbooks
          DROP CONSTRAINT pi_playbook_authority_ck;
        ALTER TABLE platform.practice_playbooks
          ADD CONSTRAINT practice_playbooks_authority_layer_check
          CHECK (authority_layer='methodological_guidance');
        """
    )
