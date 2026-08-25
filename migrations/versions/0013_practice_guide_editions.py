"""Add immutable PracticeGuide edition activation decisions.

Revision ID: 0013_guide_editions
Revises: 0012_id_memory
"""

from __future__ import annotations

import os

from alembic import op

revision = "0013_guide_editions"
down_revision = "0012_id_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ DECLARE constraint_name name; BEGIN
          SELECT conname INTO constraint_name FROM pg_constraint
          WHERE conrelid='platform.practice_guides'::regclass
            AND contype='c' AND pg_get_constraintdef(oid) LIKE '%authority_layer%';
          IF constraint_name IS NOT NULL THEN
            EXECUTE format(
              'ALTER TABLE platform.practice_guides DROP CONSTRAINT %I',
              constraint_name
            );
          END IF;
        END $$;
        ALTER TABLE platform.practice_guides
          ADD CONSTRAINT practice_guides_authority_ck
          CHECK (authority_layer IN ('methodological_guidance','methodological_practice'));

        ALTER TABLE platform.practice_guide_editions
          ADD CONSTRAINT practice_guide_editions_guide_identity_uk
          UNIQUE (practice_guide_id,practice_guide_edition_id);

        CREATE TABLE platform.practice_guide_edition_activation_decisions (
          activation_decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          practice_guide_id uuid NOT NULL
            REFERENCES platform.practice_guides(practice_guide_id) ON DELETE RESTRICT,
          selected_edition_id uuid NOT NULL,
          supersedes_version bigint,
          reason_code text NOT NULL,
          owner_decision_ref text NOT NULL,
          authority_identity_id text NOT NULL,
          decision_fingerprint text NOT NULL UNIQUE
            CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (activation_decision_id,version),
          UNIQUE (practice_guide_id,version),
          FOREIGN KEY (practice_guide_id,selected_edition_id)
            REFERENCES platform.practice_guide_editions(
              practice_guide_id,practice_guide_edition_id
            ) ON DELETE RESTRICT,
          FOREIGN KEY (activation_decision_id,supersedes_version)
            REFERENCES platform.practice_guide_edition_activation_decisions(
              activation_decision_id,version
            ) ON DELETE RESTRICT,
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          )
        );
        CREATE TRIGGER practice_guide_edition_activation_decisions_immutable
          BEFORE UPDATE OR DELETE
          ON platform.practice_guide_edition_activation_decisions
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        GRANT SELECT ON platform.practice_guide_edition_activation_decisions
          TO asd_guidance_gateway_service;
        GRANT SELECT,INSERT ON platform.practice_guide_edition_activation_decisions
          TO asd_guidance_ingestion_service;

        DO $$ DECLARE constraint_name name; BEGIN
          SELECT conname INTO constraint_name FROM pg_constraint
          WHERE conrelid='platform.practice_guide_verifications'::regclass
            AND contype='u'
            AND pg_get_constraintdef(oid) =
              'UNIQUE (guidance_candidate_id, candidate_version)';
          IF constraint_name IS NOT NULL THEN
            EXECUTE format(
              'ALTER TABLE platform.practice_guide_verifications DROP CONSTRAINT %I',
              constraint_name
            );
          END IF;
        END $$;
        ALTER TABLE platform.practice_guide_verifications
          ADD CONSTRAINT practice_guide_verification_result_uk UNIQUE (
            guidance_candidate_id,candidate_version,result_digest
          ),
          ADD CONSTRAINT practice_guide_verification_identity_uk UNIQUE (
            verification_id,guidance_candidate_id,candidate_version
          );
        CREATE TABLE platform.practice_guide_verification_selection_decisions (
          selection_decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          guidance_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL,
          selected_verification_id uuid NOT NULL,
          supersedes_version bigint,
          reason_code text NOT NULL,
          decision_fingerprint text NOT NULL UNIQUE
            CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (selection_decision_id,version),
          UNIQUE (guidance_candidate_id,candidate_version,version),
          FOREIGN KEY (selected_verification_id,guidance_candidate_id,candidate_version)
            REFERENCES platform.practice_guide_verifications(
              verification_id,guidance_candidate_id,candidate_version
            ) ON DELETE RESTRICT,
          FOREIGN KEY (selection_decision_id,supersedes_version)
            REFERENCES platform.practice_guide_verification_selection_decisions(
              selection_decision_id,version
            ) ON DELETE RESTRICT,
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          )
        );
        CREATE TRIGGER practice_guide_verification_selection_decisions_immutable
          BEFORE UPDATE OR DELETE
          ON platform.practice_guide_verification_selection_decisions
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        GRANT SELECT ON platform.practice_guide_verification_selection_decisions
          TO asd_guidance_gateway_service;
        GRANT SELECT,INSERT ON platform.practice_guide_verification_selection_decisions
          TO asd_guidance_ingestion_service;

        ALTER TABLE platform.practice_guide_page_terminal_receipts
          DROP CONSTRAINT practice_guide_page_terminal_receipts_pkey,
          ADD COLUMN receipt_version bigint NOT NULL DEFAULT 1 CHECK (receipt_version>=1),
          ADD COLUMN supersedes_receipt_version bigint,
          ADD COLUMN supersession_reason text NOT NULL DEFAULT 'INITIAL_TERMINAL_RECEIPT',
          ADD CONSTRAINT practice_guide_page_terminal_receipts_pkey PRIMARY KEY (
            ingestion_run_id,page_number,receipt_version
          ),
          ADD CONSTRAINT practice_guide_page_terminal_receipt_digest_uk UNIQUE (
            ingestion_run_id,page_number,receipt_digest
          ),
          ADD CONSTRAINT practice_guide_page_terminal_receipt_supersedes_fk FOREIGN KEY (
            ingestion_run_id,page_number,supersedes_receipt_version
          ) REFERENCES platform.practice_guide_page_terminal_receipts(
            ingestion_run_id,page_number,receipt_version
          ) ON DELETE RESTRICT,
          ADD CONSTRAINT practice_guide_page_terminal_receipt_lineage_ck CHECK (
            (receipt_version=1 AND supersedes_receipt_version IS NULL)
            OR (receipt_version>1 AND supersedes_receipt_version=receipt_version-1)
          );
        DO $$ DECLARE constraint_name name; BEGIN
          SELECT conname INTO constraint_name FROM pg_constraint
          WHERE conrelid='platform.practice_guide_ingestion_reconciliations'::regclass
            AND contype='u' AND pg_get_constraintdef(oid)='UNIQUE (ingestion_run_id)';
          IF constraint_name IS NOT NULL THEN
            EXECUTE format(
              'ALTER TABLE platform.practice_guide_ingestion_reconciliations DROP CONSTRAINT %I',
              constraint_name
            );
          END IF;
        END $$;
        ALTER TABLE platform.practice_guide_ingestion_reconciliations
          ADD COLUMN version bigint NOT NULL DEFAULT 1 CHECK (version>=1),
          ADD COLUMN supersedes_version bigint,
          ADD COLUMN supersession_reason text NOT NULL DEFAULT 'INITIAL_RECONCILIATION',
          ADD CONSTRAINT practice_guide_reconciliation_run_version_uk
            UNIQUE (ingestion_run_id,version),
          ADD CONSTRAINT practice_guide_reconciliation_fingerprint_uk
            UNIQUE (ingestion_run_id,reconciliation_fingerprint),
          ADD CONSTRAINT practice_guide_reconciliation_lineage_ck CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          );

        ALTER TABLE platform.practice_intelligence_releases
          ADD COLUMN activation_decision_id uuid,
          ADD COLUMN activation_decision_version bigint,
          ADD CONSTRAINT practice_intelligence_release_activation_fk
            FOREIGN KEY (activation_decision_id,activation_decision_version)
            REFERENCES platform.practice_guide_edition_activation_decisions(
              activation_decision_id,version
            ) ON DELETE RESTRICT,
          ADD CONSTRAINT practice_intelligence_release_activation_complete_ck
            CHECK (
              (activation_decision_id IS NULL) = (activation_decision_version IS NULL)
            );
        DO $$ DECLARE constraint_name name; BEGIN
          SELECT conname INTO constraint_name FROM pg_constraint
          WHERE conrelid='platform.practice_intelligence_releases'::regclass
            AND contype='u'
            AND pg_get_constraintdef(oid) =
              'UNIQUE (construction_manifest_id, context_assembly_policy_id, context_assembly_policy_version)';
          IF constraint_name IS NOT NULL THEN
            EXECUTE format(
              'ALTER TABLE platform.practice_intelligence_releases DROP CONSTRAINT %I',
              constraint_name
            );
          END IF;
        END $$;
        ALTER TABLE platform.practice_intelligence_releases
          ADD CONSTRAINT practice_intelligence_release_exact_binding_uk UNIQUE (
            construction_manifest_id,activation_decision_id,activation_decision_version,
            context_assembly_policy_id,context_assembly_policy_version
          );
        ALTER TABLE platform.practice_memory_backup_manifests
          ADD COLUMN activation_decision_id uuid,
          ADD COLUMN activation_decision_version bigint,
          ADD COLUMN coverage_manifest_fingerprint text
            CHECK (coverage_manifest_fingerprint IS NULL OR
              coverage_manifest_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          ADD CONSTRAINT practice_memory_backup_activation_fk
            FOREIGN KEY (activation_decision_id,activation_decision_version)
            REFERENCES platform.practice_guide_edition_activation_decisions(
              activation_decision_id,version
            ) ON DELETE RESTRICT,
          ADD CONSTRAINT practice_memory_backup_activation_complete_ck
            CHECK (
              (activation_decision_id IS NULL) = (activation_decision_version IS NULL)
            );
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("PracticeGuide edition downgrade requires a disposable database")
    op.execute(
        """
        ALTER TABLE platform.practice_memory_backup_manifests
          DROP CONSTRAINT practice_memory_backup_activation_complete_ck,
          DROP CONSTRAINT practice_memory_backup_activation_fk,
          DROP COLUMN coverage_manifest_fingerprint,
          DROP COLUMN activation_decision_version,
          DROP COLUMN activation_decision_id;
        ALTER TABLE platform.practice_intelligence_releases
          DROP CONSTRAINT practice_intelligence_release_exact_binding_uk,
          DROP CONSTRAINT practice_intelligence_release_activation_complete_ck,
          DROP CONSTRAINT practice_intelligence_release_activation_fk,
          DROP COLUMN activation_decision_version,
          DROP COLUMN activation_decision_id;
        ALTER TABLE platform.practice_intelligence_releases
          ADD CONSTRAINT practice_intelligence_release_original_binding_uk UNIQUE (
            construction_manifest_id,context_assembly_policy_id,context_assembly_policy_version
          );
        DROP TABLE platform.practice_guide_verification_selection_decisions;
        ALTER TABLE platform.practice_guide_verifications
          DROP CONSTRAINT practice_guide_verification_identity_uk,
          DROP CONSTRAINT practice_guide_verification_result_uk;
        DELETE FROM platform.practice_guide_verifications newer
          USING platform.practice_guide_verifications older
          WHERE newer.guidance_candidate_id=older.guidance_candidate_id
            AND newer.candidate_version=older.candidate_version
            AND newer.verified_at<older.verified_at;
        ALTER TABLE platform.practice_guide_verifications
          ADD CONSTRAINT practice_guide_verification_original_candidate_uk
          UNIQUE (guidance_candidate_id,candidate_version);
        DELETE FROM platform.practice_guide_page_terminal_receipts older
          USING platform.practice_guide_page_terminal_receipts newer
          WHERE older.ingestion_run_id=newer.ingestion_run_id
            AND older.page_number=newer.page_number
            AND older.receipt_version<newer.receipt_version;
        ALTER TABLE platform.practice_guide_page_terminal_receipts
          DROP CONSTRAINT practice_guide_page_terminal_receipt_lineage_ck,
          DROP CONSTRAINT practice_guide_page_terminal_receipt_supersedes_fk,
          DROP CONSTRAINT practice_guide_page_terminal_receipt_digest_uk,
          DROP CONSTRAINT practice_guide_page_terminal_receipts_pkey,
          DROP COLUMN supersession_reason,
          DROP COLUMN supersedes_receipt_version,
          DROP COLUMN receipt_version,
          ADD CONSTRAINT practice_guide_page_terminal_receipts_pkey
            PRIMARY KEY (ingestion_run_id,page_number);
        DELETE FROM platform.practice_guide_ingestion_reconciliations older
          USING platform.practice_guide_ingestion_reconciliations newer
          WHERE older.ingestion_run_id=newer.ingestion_run_id
            AND older.version<newer.version;
        ALTER TABLE platform.practice_guide_ingestion_reconciliations
          DROP CONSTRAINT practice_guide_reconciliation_lineage_ck,
          DROP CONSTRAINT practice_guide_reconciliation_fingerprint_uk,
          DROP CONSTRAINT practice_guide_reconciliation_run_version_uk,
          DROP COLUMN supersession_reason,
          DROP COLUMN supersedes_version,
          DROP COLUMN version,
          ADD CONSTRAINT practice_guide_ingestion_reconciliations_ingestion_run_id_key
            UNIQUE (ingestion_run_id);
        DROP TABLE platform.practice_guide_edition_activation_decisions;
        ALTER TABLE platform.practice_guide_editions
          DROP CONSTRAINT practice_guide_editions_guide_identity_uk;
        ALTER TABLE platform.practice_guides
          DROP CONSTRAINT practice_guides_authority_ck;
        ALTER TABLE platform.practice_guides
          ADD CONSTRAINT practice_guides_authority_layer_check
          CHECK (authority_layer='methodological_guidance');
        """
    )
