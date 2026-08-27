"""Qualify official templates and finalize Support package documents.

Revision ID: 0026_support_id_finalize
Revises: 0025_support_production_id
Create Date: 2026-08-27
"""

from __future__ import annotations

import os

from alembic import op

revision = "0026_support_id_finalize"
down_revision = "0025_support_production_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform.template_qualification_receipts (
          template_id uuid NOT NULL,
          template_version text NOT NULL,
          qualification_version bigint NOT NULL CHECK (qualification_version>=1),
          source_version_ref text NOT NULL CHECK (lower(source_version_ref)<>'latest'),
          normative_edition_ref text NOT NULL CHECK (lower(normative_edition_ref)<>'latest'),
          official_url text NOT NULL CHECK (official_url LIKE 'https://%'),
          official_source_digest text NOT NULL CHECK (official_source_digest ~ '^sha256:[a-f0-9]{64}$'),
          selected_pages integer[] NOT NULL CHECK (cardinality(selected_pages)>0),
          profile_version text NOT NULL CHECK (lower(profile_version)<>'latest'),
          renderer_profile_version text NOT NULL CHECK (lower(renderer_profile_version)<>'latest'),
          validator_profile_version text NOT NULL CHECK (lower(validator_profile_version)<>'latest'),
          check_codes text[] NOT NULL CHECK (cardinality(check_codes)>0),
          blocker_codes text[] NOT NULL,
          result text NOT NULL CHECK (result IN ('qualified','blocked','rejected')),
          receipt_digest text NOT NULL CHECK (receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          qualified_at timestamptz NOT NULL,
          PRIMARY KEY (template_id,template_version,qualification_version),
          FOREIGN KEY (template_id,template_version)
            REFERENCES platform.template_versions(template_id,version) ON DELETE RESTRICT,
          CHECK (result<>'qualified' OR cardinality(blocker_codes)=0)
        );
        CREATE TABLE platform.template_field_binding_versions (
          template_id uuid NOT NULL,
          template_version text NOT NULL,
          field_key text NOT NULL,
          binding_version text NOT NULL CHECK (lower(binding_version)<>'latest'),
          page_index integer NOT NULL CHECK (page_index>=1),
          region double precision[] NOT NULL CHECK (array_length(region,1)=4),
          typography jsonb NOT NULL,
          binding_digest text NOT NULL CHECK (binding_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (template_id,template_version,field_key),
          FOREIGN KEY (template_id,template_version)
            REFERENCES platform.template_versions(template_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE platform.template_renderer_assets (
          template_id uuid NOT NULL,
          template_version text NOT NULL,
          asset_role text NOT NULL CHECK (asset_role IN ('font','layout_golden','validator_fixture')),
          asset_version bigint NOT NULL CHECK (asset_version>=1),
          object_key text NOT NULL,
          media_type text NOT NULL,
          byte_length bigint NOT NULL CHECK (byte_length>0),
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          provenance jsonb NOT NULL,
          validation_status text NOT NULL CHECK (validation_status IN ('qualified','blocked','rejected')),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (template_id,template_version,asset_role,asset_version),
          UNIQUE (content_digest),
          FOREIGN KEY (template_id,template_version)
            REFERENCES platform.template_versions(template_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE workspace.support_package_backup_manifests (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          backup_manifest_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          id_package_id uuid NOT NULL,
          through_package_version bigint NOT NULL CHECK (through_package_version>=1),
          canonical_manifest jsonb NOT NULL,
          manifest_fingerprint text NOT NULL CHECK (manifest_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          object_digests text[] NOT NULL,
          result text NOT NULL CHECK (result IN ('verified','blocked')),
          blocker_codes text[] NOT NULL,
          created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,backup_manifest_id,version),
          FOREIGN KEY (organization_id,workspace_id,id_package_id,through_package_version)
            REFERENCES workspace.id_package_versions(organization_id,workspace_id,id_package_id,version)
            ON DELETE RESTRICT,
          CHECK (result<>'verified' OR cardinality(blocker_codes)=0)
        );
        """
    )
    op.execute(
        "GRANT SELECT ON platform.template_qualification_receipts,"
        "platform.template_field_binding_versions,platform.template_renderer_assets "
        "TO asd_app,asd_document_worker,asd_support_service"
    )
    predicate = (
        "organization_id=nullif(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=nullif(current_setting('asd.workspace_id',true),'')::uuid"
    )
    table = "support_package_backup_manifests"
    op.execute(f"ALTER TABLE workspace.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE workspace.{table} FORCE ROW LEVEL SECURITY")
    for role, suffix in (
        ("asd_app", "app"),
        ("asd_support_service", "support"),
        ("asd_destruction_executor", "destruction"),
    ):
        op.execute(
            f"CREATE POLICY {table}_{suffix}_scope ON workspace.{table} FOR ALL TO {role} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_app,asd_support_service")
    op.execute(f"GRANT SELECT,DELETE ON workspace.{table} TO asd_destruction_executor")
    op.execute(
        f"CREATE TRIGGER {table}_write_fence BEFORE INSERT OR UPDATE ON workspace.{table} "
        "FOR EACH ROW EXECUTE FUNCTION workspace.enforce_material_write_fence()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON workspace.{table} "
        "FOR EACH ROW EXECUTE FUNCTION application.reject_spine_mutation_except_destruction()"
    )
    for table in (
        "support_document_review_decisions",
        "support_finalized_document_versions",
    ):
        op.execute(
            f"CREATE POLICY {table}_product_app_scope ON workspace.{table} FOR ALL TO asd_app "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(f"GRANT SELECT,INSERT ON workspace.{table} TO asd_app")


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Support ID finalization downgrade requires a disposable database")
    for table in (
        "support_document_review_decisions",
        "support_finalized_document_versions",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_product_app_scope ON workspace.{table}")
    op.execute("DROP TABLE workspace.support_package_backup_manifests")
    op.execute("DROP TABLE platform.template_renderer_assets")
    op.execute("DROP TABLE platform.template_field_binding_versions")
    op.execute("DROP TABLE platform.template_qualification_receipts")
