"""Add canonical ID Practice Intelligence and playbook projections.

Revision ID: 0011_id_intelligence
Revises: 0010_kg_id_compat
"""

from __future__ import annotations

import os

from alembic import op

revision = "0011_id_intelligence"
down_revision = "0010_kg_id_compat"
branch_labels = None
depends_on = None

PLATFORM_TABLES = (
    "practice_intelligence_construction_manifests",
    "practice_intelligence_units",
    "practice_intelligence_sources",
    "practice_playbooks",
    "practice_playbook_members",
)

PROJECTION_TABLES = (
    "practice_intelligence_lexical_versions",
    "practice_intelligence_lexical_entries",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform.practice_intelligence_construction_manifests (
          construction_manifest_id uuid PRIMARY KEY,
          coverage_manifest_id uuid NOT NULL REFERENCES platform.practice_guidance_coverage_manifests(coverage_manifest_id) ON DELETE RESTRICT,
          construction_profile_version text NOT NULL,
          source_guidance_count bigint NOT NULL CHECK (source_guidance_count>=0),
          intelligence_unit_count bigint NOT NULL CHECK (intelligence_unit_count>=0),
          playbook_count bigint NOT NULL CHECK (playbook_count>=0),
          construction_fingerprint text NOT NULL UNIQUE CHECK (construction_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          authority_layer text NOT NULL CHECK (authority_layer='methodological_guidance'),
          product_ready boolean NOT NULL DEFAULT false CHECK (product_ready=false),
          constructed_at timestamptz NOT NULL,
          UNIQUE (coverage_manifest_id,construction_profile_version)
        );
        CREATE TABLE platform.practice_intelligence_units (
          intelligence_unit_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          construction_manifest_id uuid NOT NULL REFERENCES platform.practice_intelligence_construction_manifests(construction_manifest_id) ON DELETE RESTRICT,
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          coverage_manifest_id uuid NOT NULL REFERENCES platform.practice_guidance_coverage_manifests(coverage_manifest_id) ON DELETE RESTRICT,
          intelligence_kind text NOT NULL CHECK (intelligence_kind IN (
            'id_practice_principle','id_workflow_step','form_completion_guidance',
            'field_completion_guidance','attention_point','allowed_practice_variant',
            'practice_rationale','common_failure_pattern','verification_checklist',
            'completeness_guidance','journal_selection_guidance',
            'document_dependency_guidance','visual_completion_example')),
          title text NOT NULL,
          instruction text NOT NULL,
          rationale text,
          applicability_conditions jsonb NOT NULL,
          work_types jsonb NOT NULL,
          document_types jsonb NOT NULL,
          form_types jsonb NOT NULL,
          workflow_stages jsonb NOT NULL,
          field_elements jsonb NOT NULL,
          required_inputs jsonb NOT NULL,
          evidence_requirements jsonb NOT NULL,
          allowed_variants jsonb NOT NULL,
          failure_patterns jsonb NOT NULL,
          checklist_items jsonb NOT NULL,
          dependency_refs jsonb NOT NULL,
          normative_references jsonb NOT NULL,
          uncertainties jsonb NOT NULL,
          construction_profile_version text NOT NULL,
          authority_layer text NOT NULL CHECK (authority_layer='methodological_guidance'),
          integrity_digest text NOT NULL UNIQUE CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          constructed_at timestamptz NOT NULL,
          PRIMARY KEY (intelligence_unit_id,version)
        );
        CREATE TABLE platform.practice_intelligence_sources (
          intelligence_source_id uuid PRIMARY KEY,
          intelligence_unit_id uuid NOT NULL,
          intelligence_unit_version bigint NOT NULL,
          guidance_unit_id uuid NOT NULL,
          guidance_unit_version bigint NOT NULL,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          source_locator_id uuid NOT NULL REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          page_number integer NOT NULL CHECK (page_number>=1),
          region double precision[] NOT NULL CHECK (cardinality(region)=4),
          fragment_digest text NOT NULL CHECK (fragment_digest ~ '^sha256:[a-f0-9]{64}$'),
          evidence_role text NOT NULL CHECK (evidence_role IN ('primary','visual_example','cross_reference')),
          recorded_at timestamptz NOT NULL,
          UNIQUE (intelligence_unit_id,intelligence_unit_version,guidance_unit_id,guidance_unit_version,source_locator_id),
          FOREIGN KEY (intelligence_unit_id,intelligence_unit_version) REFERENCES platform.practice_intelligence_units(intelligence_unit_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (guidance_unit_id,guidance_unit_version) REFERENCES platform.practice_guidance_units(guidance_unit_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.practice_playbooks (
          playbook_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          construction_manifest_id uuid NOT NULL REFERENCES platform.practice_intelligence_construction_manifests(construction_manifest_id) ON DELETE RESTRICT,
          practice_guide_edition_id uuid NOT NULL REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          coverage_manifest_id uuid NOT NULL REFERENCES platform.practice_guidance_coverage_manifests(coverage_manifest_id) ON DELETE RESTRICT,
          title text NOT NULL,
          purpose text NOT NULL,
          applicability_conditions jsonb NOT NULL,
          work_types jsonb NOT NULL,
          document_types jsonb NOT NULL,
          form_types jsonb NOT NULL,
          workflow_stages jsonb NOT NULL,
          uncertainties jsonb NOT NULL,
          construction_profile_version text NOT NULL,
          authority_layer text NOT NULL CHECK (authority_layer='methodological_guidance'),
          integrity_digest text NOT NULL UNIQUE CHECK (integrity_digest ~ '^sha256:[a-f0-9]{64}$'),
          constructed_at timestamptz NOT NULL,
          PRIMARY KEY (playbook_id,version)
        );
        CREATE TABLE platform.practice_playbook_members (
          playbook_id uuid NOT NULL,
          playbook_version bigint NOT NULL,
          member_sequence bigint NOT NULL CHECK (member_sequence>=1),
          intelligence_unit_id uuid NOT NULL,
          intelligence_unit_version bigint NOT NULL,
          member_role text NOT NULL CHECK (member_role IN (
            'principle','workflow_step','form_guidance','field_guidance','attention_point',
            'allowed_variant','rationale','failure_pattern','checklist','completeness',
            'journal_selection','dependency','visual_example')),
          PRIMARY KEY (playbook_id,playbook_version,member_sequence),
          UNIQUE (playbook_id,playbook_version,intelligence_unit_id,intelligence_unit_version),
          FOREIGN KEY (playbook_id,playbook_version) REFERENCES platform.practice_playbooks(playbook_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (intelligence_unit_id,intelligence_unit_version) REFERENCES platform.practice_intelligence_units(intelligence_unit_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE projection.practice_intelligence_lexical_versions (
          lexical_version_id uuid PRIMARY KEY,
          construction_manifest_id uuid NOT NULL REFERENCES platform.practice_intelligence_construction_manifests(construction_manifest_id) ON DELETE RESTRICT,
          projection_contract_version text NOT NULL,
          source_fingerprint text NOT NULL CHECK (source_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          state text NOT NULL CHECK (state IN ('building','ready','stale','failed','empty')),
          entry_count bigint NOT NULL CHECK (entry_count>=0),
          built_at timestamptz,
          CHECK (state<>'ready' OR built_at IS NOT NULL)
        );
        CREATE TABLE projection.practice_intelligence_lexical_entries (
          lexical_version_id uuid NOT NULL REFERENCES projection.practice_intelligence_lexical_versions(lexical_version_id) ON DELETE CASCADE,
          entity_kind text NOT NULL CHECK (entity_kind IN ('intelligence_unit','practice_playbook')),
          entity_id uuid NOT NULL,
          entity_version bigint NOT NULL CHECK (entity_version>=1),
          intelligence_kind text,
          searchable_text text NOT NULL,
          search_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian',searchable_text)) STORED,
          entry_digest text NOT NULL CHECK (entry_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (lexical_version_id,entity_kind,entity_id,entity_version)
        );
        CREATE INDEX practice_intelligence_lexical_search_idx
          ON projection.practice_intelligence_lexical_entries USING gin(search_vector);
        CREATE INDEX practice_intelligence_lexical_kind_idx
          ON projection.practice_intelligence_lexical_entries
          (lexical_version_id,entity_kind,intelligence_kind);
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
        raise RuntimeError(
            "ID Practice Intelligence downgrade is allowed only in a disposable database"
        )
    for table in reversed(PROJECTION_TABLES):
        op.execute(f"DROP TABLE projection.{table}")
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE platform.{table}")
