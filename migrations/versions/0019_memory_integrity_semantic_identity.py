"""Add semantic practice identities and complete release activation lineage.

Revision ID: 0019_memory_integrity
Revises: 0018_product_spine

The pre-0018 construction rows and releases are immutable historical evidence.
This migration adds the normalized canonical layer used by superseding releases.
"""

from __future__ import annotations

import os

from alembic import op

revision = "0019_memory_integrity"
down_revision = "0018_product_spine"
branch_labels = None
depends_on = None

TABLES = (
    "system_integrity_decisions",
    "practice_intelligence_identities",
    "practice_intelligence_versions",
    "practice_intelligence_evidence_links",
    "practice_intelligence_release_memberships",
    "practice_playbook_identities",
    "practice_playbook_versions_v2",
    "practice_playbook_version_members",
    "practice_playbook_release_memberships",
    "practice_intelligence_release_activation_decisions",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform.system_integrity_decisions (
          integrity_decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          supersedes_version bigint,
          decision_type text NOT NULL CHECK (decision_type IN (
            'initial_qualification','superseding_data_defect','requalification'
          )),
          status text NOT NULL CHECK (status IN ('pass','partial_data_defect','superseded')),
          prior_series_id text,
          canonical_commit text NOT NULL CHECK (canonical_commit ~ '^[a-f0-9]{40}$'),
          dump_fingerprint text NOT NULL CHECK (dump_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          reconciliation_fingerprint text NOT NULL
            CHECK (reconciliation_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          defect_identities jsonb NOT NULL,
          reason text NOT NULL,
          owner_decision_ref text NOT NULL,
          product_ready boolean NOT NULL DEFAULT false CHECK (product_ready=false),
          decision_fingerprint text NOT NULL UNIQUE
            CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (integrity_decision_id,version),
          FOREIGN KEY (integrity_decision_id,supersedes_version)
            REFERENCES platform.system_integrity_decisions(integrity_decision_id,version)
            ON DELETE RESTRICT,
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          )
        );

        CREATE TABLE platform.practice_intelligence_identities (
          intelligence_identity_id uuid PRIMARY KEY,
          practice_guide_id uuid NOT NULL
            REFERENCES platform.practice_guides(practice_guide_id) ON DELETE RESTRICT,
          typed_kind text NOT NULL,
          subject text NOT NULL,
          predicate text NOT NULL,
          object_value text NOT NULL,
          unit text,
          dimension text,
          modality text NOT NULL,
          applicability jsonb NOT NULL,
          qualifiers jsonb NOT NULL,
          exclusions jsonb NOT NULL,
          authority_layer text NOT NULL CHECK (authority_layer='methodological_practice'),
          semantic_schema_version text NOT NULL,
          normalized_semantic_digest text NOT NULL UNIQUE
            CHECK (normalized_semantic_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          UNIQUE (practice_guide_id,typed_kind,normalized_semantic_digest)
        );

        CREATE TABLE platform.practice_intelligence_versions (
          intelligence_identity_id uuid NOT NULL
            REFERENCES platform.practice_intelligence_identities(intelligence_identity_id)
            ON DELETE RESTRICT,
          version bigint NOT NULL CHECK (version>=1),
          practice_guide_edition_id uuid NOT NULL
            REFERENCES platform.practice_guide_editions(practice_guide_edition_id)
            ON DELETE RESTRICT,
          construction_manifest_id uuid NOT NULL
            REFERENCES platform.practice_intelligence_construction_manifests(
              construction_manifest_id
            ) ON DELETE RESTRICT,
          canonical_payload jsonb NOT NULL,
          construction_profile_version text NOT NULL,
          semantic_fingerprint text NOT NULL UNIQUE
            CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (intelligence_identity_id,version),
          UNIQUE (intelligence_identity_id,practice_guide_edition_id,semantic_fingerprint)
        );

        CREATE TABLE platform.practice_intelligence_evidence_links (
          evidence_link_id uuid PRIMARY KEY,
          intelligence_identity_id uuid NOT NULL,
          intelligence_version bigint NOT NULL,
          source_guidance_unit_id uuid NOT NULL,
          source_guidance_unit_version bigint NOT NULL,
          source_version_id uuid NOT NULL
            REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          source_locator_id uuid NOT NULL
            REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          guidance_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL CHECK (candidate_version>=1),
          evidence_digest text NOT NULL CHECK (evidence_digest ~ '^sha256:[a-f0-9]{64}$'),
          extraction_verification_receipt text NOT NULL,
          recorded_at timestamptz NOT NULL,
          FOREIGN KEY (intelligence_identity_id,intelligence_version)
            REFERENCES platform.practice_intelligence_versions(
              intelligence_identity_id,version
            ) ON DELETE RESTRICT,
          FOREIGN KEY (source_guidance_unit_id,source_guidance_unit_version)
            REFERENCES platform.practice_guidance_units(guidance_unit_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (guidance_candidate_id,candidate_version)
            REFERENCES platform.practice_guide_candidate_versions(guidance_candidate_id,version)
            ON DELETE RESTRICT,
          UNIQUE (
            intelligence_identity_id,intelligence_version,source_guidance_unit_id,
            source_guidance_unit_version,source_locator_id
          )
        );

        CREATE TABLE platform.practice_intelligence_release_memberships (
          release_id uuid NOT NULL,
          release_version bigint NOT NULL,
          member_sequence bigint NOT NULL CHECK (member_sequence>=1),
          intelligence_identity_id uuid NOT NULL,
          intelligence_version bigint NOT NULL,
          membership_fingerprint text NOT NULL UNIQUE
            CHECK (membership_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (release_id,release_version,member_sequence),
          UNIQUE (
            release_id,release_version,intelligence_identity_id,intelligence_version
          ),
          FOREIGN KEY (release_id,release_version)
            REFERENCES platform.practice_intelligence_releases(release_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (intelligence_identity_id,intelligence_version)
            REFERENCES platform.practice_intelligence_versions(
              intelligence_identity_id,version
            ) ON DELETE RESTRICT
        );

        CREATE TABLE platform.practice_playbook_identities (
          playbook_identity_id uuid PRIMARY KEY,
          practice_guide_id uuid NOT NULL
            REFERENCES platform.practice_guides(practice_guide_id) ON DELETE RESTRICT,
          normalized_semantic_digest text NOT NULL UNIQUE
            CHECK (normalized_semantic_digest ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL
        );

        CREATE TABLE platform.practice_playbook_versions_v2 (
          playbook_identity_id uuid NOT NULL
            REFERENCES platform.practice_playbook_identities(playbook_identity_id)
            ON DELETE RESTRICT,
          version bigint NOT NULL CHECK (version>=1),
          practice_guide_edition_id uuid NOT NULL
            REFERENCES platform.practice_guide_editions(practice_guide_edition_id)
            ON DELETE RESTRICT,
          construction_manifest_id uuid NOT NULL
            REFERENCES platform.practice_intelligence_construction_manifests(
              construction_manifest_id
            ) ON DELETE RESTRICT,
          canonical_payload jsonb NOT NULL,
          construction_profile_version text NOT NULL,
          semantic_fingerprint text NOT NULL UNIQUE
            CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (playbook_identity_id,version)
        );

        CREATE TABLE platform.practice_playbook_version_members (
          playbook_identity_id uuid NOT NULL,
          playbook_version bigint NOT NULL,
          member_sequence bigint NOT NULL CHECK (member_sequence>=1),
          intelligence_identity_id uuid NOT NULL,
          intelligence_version bigint NOT NULL,
          member_role text NOT NULL,
          PRIMARY KEY (playbook_identity_id,playbook_version,member_sequence),
          UNIQUE (
            playbook_identity_id,playbook_version,
            intelligence_identity_id,intelligence_version
          ),
          FOREIGN KEY (playbook_identity_id,playbook_version)
            REFERENCES platform.practice_playbook_versions_v2(playbook_identity_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (intelligence_identity_id,intelligence_version)
            REFERENCES platform.practice_intelligence_versions(
              intelligence_identity_id,version
            ) ON DELETE RESTRICT
        );

        CREATE TABLE platform.practice_playbook_release_memberships (
          release_id uuid NOT NULL,
          release_version bigint NOT NULL,
          member_sequence bigint NOT NULL CHECK (member_sequence>=1),
          playbook_identity_id uuid NOT NULL,
          playbook_version bigint NOT NULL,
          membership_fingerprint text NOT NULL UNIQUE
            CHECK (membership_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (release_id,release_version,member_sequence),
          UNIQUE (release_id,release_version,playbook_identity_id,playbook_version),
          FOREIGN KEY (release_id,release_version)
            REFERENCES platform.practice_intelligence_releases(release_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (playbook_identity_id,playbook_version)
            REFERENCES platform.practice_playbook_versions_v2(playbook_identity_id,version)
            ON DELETE RESTRICT
        );

        CREATE TABLE platform.practice_intelligence_release_activation_decisions (
          release_activation_decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          practice_guide_id uuid NOT NULL
            REFERENCES platform.practice_guides(practice_guide_id) ON DELETE RESTRICT,
          selected_release_id uuid NOT NULL,
          selected_release_version bigint NOT NULL,
          supersedes_version bigint,
          reason_code text NOT NULL,
          owner_decision_ref text NOT NULL,
          authority_identity_id text NOT NULL,
          decision_fingerprint text NOT NULL UNIQUE
            CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (release_activation_decision_id,version),
          UNIQUE (practice_guide_id,version),
          FOREIGN KEY (selected_release_id,selected_release_version)
            REFERENCES platform.practice_intelligence_releases(release_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (release_activation_decision_id,supersedes_version)
            REFERENCES platform.practice_intelligence_release_activation_decisions(
              release_activation_decision_id,version
            ) ON DELETE RESTRICT,
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          )
        );
        """
    )
    op.execute(
        "GRANT USAGE ON SCHEMA platform TO "
        "asd_guidance_ingestion_service,asd_guidance_gateway_service"
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON platform.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )
        op.execute(f"GRANT SELECT ON platform.{table} TO asd_guidance_gateway_service")
        op.execute(f"GRANT SELECT,INSERT ON platform.{table} TO asd_guidance_ingestion_service")


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Memory integrity downgrade requires a disposable database")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE platform.{table}")
