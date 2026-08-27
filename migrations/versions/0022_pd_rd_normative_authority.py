"""Extend the single NTD Authority for PP 87 and the official SPDS corpus.

Revision ID: 0022_pd_rd_normative_authority
Revises: 0021_document_understanding
Create Date: 2026-08-26
"""

from __future__ import annotations

from alembic import op

revision = "0022_pd_rd_normative_authority"
down_revision = "0021_document_understanding"
branch_labels = None
depends_on = None

PLATFORM_TABLES = (
    "official_provider_health_receipts",
    "normative_corpus_manifests",
    "normative_corpus_members",
    "normative_applicability_predicates",
    "rule_normative_provision_evidence",
)

OFFICIAL_URL_CHECK = (
    "^https://(government\\.ru|www\\.government\\.ru|static\\.government\\.ru|"
    "publication\\.pravo\\.gov\\.ru|pravo\\.gov\\.ru|www\\.pravo\\.gov\\.ru|"
    "protect\\.gost\\.ru|www\\.protect\\.gost\\.ru|rst\\.gov\\.ru|www\\.rst\\.gov\\.ru|"
    "minstroyrf\\.gov\\.ru|www\\.minstroyrf\\.gov\\.ru)/"
)


def upgrade() -> None:
    _widen_official_source_constraints()
    _create_provider_and_corpus_ledger()
    _create_applicability_and_rule_lineage()
    _create_workspace_profile()
    _apply_security()


def _widen_official_source_constraints() -> None:
    for table, column in (
        ("normative_editions", "official_catalog_url"),
        ("normative_artifacts", "official_url"),
        ("ntd_catalogue_query_receipts", "official_endpoint"),
    ):
        op.execute(
            f"""
            DO $$ DECLARE item record; BEGIN
              FOR item IN SELECT conname FROM pg_constraint
                WHERE conrelid='platform.{table}'::regclass AND contype='c'
                  AND pg_get_constraintdef(oid) LIKE '%{column}%minstroyrf%'
              LOOP EXECUTE format(
                'ALTER TABLE platform.{table} DROP CONSTRAINT %I', item.conname
              ); END LOOP;
            END $$;
            ALTER TABLE platform.{table}
              ADD CONSTRAINT {table}_{column}_official_provider_ck
              CHECK ({column} IS NULL OR {column} ~ '{OFFICIAL_URL_CHECK}');
            """
        )


def _create_provider_and_corpus_ledger() -> None:
    op.execute(
        """
        CREATE TABLE platform.official_provider_health_receipts (
          provider_health_receipt_id uuid PRIMARY KEY,
          provider text NOT NULL CHECK (provider IN (
            'government_portal','official_legal_publication','rosstandart_fund','minstroy_catalogue'
          )),
          endpoint text NOT NULL,
          transport_profile text NOT NULL CHECK (transport_profile IN ('direct','environment_proxy')),
          checked_at timestamptz NOT NULL,
          access_status text NOT NULL CHECK (access_status IN (
            'available','access_blocked','network_unavailable','tls_verification_failed',
            'proxy_misconfigured','http_access_denied','authentication_required',
            'license_restricted','artifact_unavailable','unexpected_mime','invalid_bytes',
            'unsupported_viewer_protocol','parser_failure','invalid_response'
          )),
          http_status integer CHECK (http_status BETWEEN 100 AND 599),
          response_digest text CHECK (response_digest ~ '^sha256:[a-f0-9]{64}$'),
          failure_code text,
          diagnostic jsonb NOT NULL DEFAULT '{}'::jsonb,
          receipt_fingerprint text NOT NULL UNIQUE CHECK (receipt_fingerprint ~ '^sha256:[a-f0-9]{64}$')
        );
        CREATE TABLE platform.normative_corpus_manifests (
          normative_corpus_manifest_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          corpus_key text NOT NULL,
          provider text NOT NULL CHECK (provider IN (
            'government_portal','official_legal_publication','rosstandart_fund','minstroy_catalogue'
          )),
          official_query text NOT NULL,
          official_query_endpoints text[] NOT NULL CHECK (cardinality(official_query_endpoints)>0),
          denominator integer NOT NULL CHECK (denominator>0),
          parser_version text NOT NULL CHECK (lower(parser_version)<>'latest'),
          manifest_fingerprint text NOT NULL UNIQUE CHECK (manifest_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          supersedes_version bigint,
          created_at timestamptz NOT NULL,
          PRIMARY KEY (normative_corpus_manifest_id,version),
          FOREIGN KEY (normative_corpus_manifest_id,supersedes_version)
            REFERENCES platform.normative_corpus_manifests(normative_corpus_manifest_id,version)
            ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR
                 (version>1 AND supersedes_version=version-1))
        );
        CREATE TABLE platform.normative_corpus_members (
          normative_corpus_manifest_id uuid NOT NULL,
          manifest_version bigint NOT NULL,
          corpus_member_id uuid NOT NULL,
          ordinal integer NOT NULL CHECK (ordinal>=1),
          stable_identity_key text NOT NULL,
          designation text NOT NULL,
          title text NOT NULL,
          official_catalog_id text NOT NULL,
          official_catalog_url text NOT NULL,
          edition_status text NOT NULL CHECK (edition_status IN (
            'active','replaced','cancelled','not_effective_in_rf','unknown'
          )),
          replaces_designation text,
          replaced_by_designation text,
          scope_text text,
          official_metadata jsonb NOT NULL,
          acquisition_status text NOT NULL CHECK (acquisition_status IN (
            'resolved_exact','resolved_superseded','ambiguous_official_records',
            'official_metadata_only','official_artifact_unavailable','official_access_blocked',
            'not_found_official','exact_edition_not_found','edition_conflict',
            'supersession_unresolved','download_failed','artifact_invalid','parse_partial',
            'parsed_verified','blocked_deterministic_failure'
          )),
          metadata_digest text NOT NULL CHECK (metadata_digest ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (normative_corpus_manifest_id,manifest_version,corpus_member_id),
          FOREIGN KEY (normative_corpus_manifest_id,manifest_version)
            REFERENCES platform.normative_corpus_manifests(normative_corpus_manifest_id,version)
            ON DELETE RESTRICT,
          UNIQUE (normative_corpus_manifest_id,manifest_version,ordinal),
          UNIQUE (normative_corpus_manifest_id,manifest_version,official_catalog_id)
        );
        """
    )


def _create_applicability_and_rule_lineage() -> None:
    op.execute(
        """
        CREATE TABLE platform.normative_applicability_predicates (
          applicability_predicate_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          normative_provision_id uuid NOT NULL,
          normative_provision_version bigint NOT NULL,
          predicate jsonb NOT NULL,
          required_inputs text[] NOT NULL,
          exclusions jsonb NOT NULL,
          semantic_fingerprint text NOT NULL UNIQUE CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          supersedes_version bigint,
          qualified_by_identity_id text NOT NULL,
          qualification_decision_ref text NOT NULL,
          qualified_at timestamptz NOT NULL,
          PRIMARY KEY (applicability_predicate_id,version),
          FOREIGN KEY (normative_provision_id,normative_provision_version)
            REFERENCES platform.normative_provision_versions(normative_provision_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (applicability_predicate_id,supersedes_version)
            REFERENCES platform.normative_applicability_predicates(applicability_predicate_id,version)
            ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR
                 (version>1 AND supersedes_version=version-1))
        );
        CREATE TABLE platform.rule_normative_provision_evidence (
          rule_normative_evidence_id uuid PRIMARY KEY,
          rule_version_id uuid NOT NULL REFERENCES platform.rule_versions(rule_version_id) ON DELETE RESTRICT,
          normative_provision_id uuid NOT NULL,
          normative_provision_version bigint NOT NULL,
          normative_edition_id uuid NOT NULL REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          source_locator_id uuid NOT NULL REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          applicability_predicate_id uuid NOT NULL,
          applicability_predicate_version bigint NOT NULL,
          qualification_decision_ref text NOT NULL,
          evidence_digest text NOT NULL CHECK (evidence_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          FOREIGN KEY (normative_provision_id,normative_provision_version)
            REFERENCES platform.normative_provision_versions(normative_provision_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (applicability_predicate_id,applicability_predicate_version)
            REFERENCES platform.normative_applicability_predicates(applicability_predicate_id,version)
            ON DELETE RESTRICT,
          UNIQUE (rule_version_id,normative_provision_id,normative_provision_version)
        );
        """
    )


def _create_workspace_profile() -> None:
    op.execute(
        """
        CREATE TABLE workspace.applicable_pd_rd_normative_profiles (
          organization_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          profile_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          project_definition_id uuid NOT NULL,
          project_definition_version bigint NOT NULL,
          applicable_on date,
          input_fingerprint text NOT NULL CHECK (input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          corpus_denominator jsonb NOT NULL,
          normative_edition_ids uuid[] NOT NULL,
          rule_version_ids uuid[] NOT NULL,
          required_pd_sections jsonb NOT NULL,
          expected_rd_sets jsonb NOT NULL,
          formatting_requirements jsonb NOT NULL,
          unresolved_inputs text[] NOT NULL,
          gaps jsonb NOT NULL,
          completeness_status text NOT NULL CHECK (completeness_status IN (
            'complete','partial','indeterminate','blocked'
          )),
          semantic_fingerprint text NOT NULL CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (organization_id,workspace_id,profile_id,version),
          FOREIGN KEY (organization_id,workspace_id,project_definition_id,project_definition_version)
            REFERENCES workspace.project_definition_versions
              (organization_id,workspace_id,project_definition_id,version) ON DELETE RESTRICT,
          UNIQUE (organization_id,workspace_id,input_fingerprint,semantic_fingerprint)
        );
        """
    )


def _apply_security() -> None:
    for table in PLATFORM_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON platform.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )
        op.execute(f"GRANT SELECT,INSERT ON platform.{table} TO asd_ntd_ingestion_service")
        op.execute(
            f"GRANT SELECT ON platform.{table} "
            "TO asd_ntd_gateway_service,asd_platform_curator,asd_app"
        )
    op.execute(
        "ALTER TABLE workspace.applicable_pd_rd_normative_profiles ENABLE ROW LEVEL SECURITY"
    )
    op.execute("ALTER TABLE workspace.applicable_pd_rd_normative_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY applicable_pd_rd_normative_profiles_scope ON "
        "workspace.applicable_pd_rd_normative_profiles USING ("
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid) WITH CHECK ("
        "organization_id=NULLIF(current_setting('asd.organization_id',true),'')::uuid AND "
        "workspace_id=NULLIF(current_setting('asd.workspace_id',true),'')::uuid)"
    )
    op.execute(
        "GRANT SELECT ON workspace.applicable_pd_rd_normative_profiles "
        "TO asd_app,asd_ntd_gateway_service; "
        "GRANT SELECT,INSERT ON workspace.applicable_pd_rd_normative_profiles TO asd_document_worker; "
        "GRANT SELECT,DELETE ON workspace.applicable_pd_rd_normative_profiles TO asd_destruction_executor"
    )
    op.execute("GRANT USAGE ON SCHEMA workspace TO asd_ntd_gateway_service")
    op.execute(
        "GRANT USAGE ON SCHEMA platform TO asd_document_worker; "
        "GRANT SELECT ON platform.rule_versions,platform.rule_version_states,"
        "platform.rule_normative_provision_evidence,platform.normative_provision_versions,"
        "platform.normative_editions,platform.source_locators,"
        "platform.normative_applicability_predicates,platform.normative_corpus_manifests "
        "TO asd_document_worker"
    )
    op.execute(
        "CREATE TRIGGER applicable_pd_rd_normative_profiles_immutable BEFORE UPDATE OR DELETE ON "
        "workspace.applicable_pd_rd_normative_profiles FOR EACH ROW "
        "EXECUTE FUNCTION application.reject_spine_mutation_except_destruction()"
    )


def downgrade() -> None:
    op.execute("REVOKE USAGE ON SCHEMA workspace FROM asd_ntd_gateway_service")
    op.execute(
        "REVOKE SELECT ON platform.rule_versions,platform.rule_version_states,"
        "platform.rule_normative_provision_evidence,platform.normative_provision_versions,"
        "platform.normative_editions,platform.source_locators,"
        "platform.normative_applicability_predicates,platform.normative_corpus_manifests "
        "FROM asd_document_worker"
    )
    op.execute("DROP TABLE workspace.applicable_pd_rd_normative_profiles")
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE platform.{table}")
    for table, column in (
        ("normative_editions", "official_catalog_url"),
        ("normative_artifacts", "official_url"),
        ("ntd_catalogue_query_receipts", "official_endpoint"),
    ):
        op.execute(
            f"ALTER TABLE platform.{table} DROP CONSTRAINT {table}_{column}_official_provider_ck"
        )
    op.execute(
        "ALTER TABLE platform.normative_editions ADD CONSTRAINT "
        "normative_editions_official_catalog_url_check CHECK (official_catalog_url IS NULL OR "
        "official_catalog_url LIKE 'https://minstroyrf.gov.ru/%')"
    )
    op.execute(
        "ALTER TABLE platform.normative_artifacts ADD CONSTRAINT "
        "normative_artifacts_official_url_check CHECK (official_url LIKE 'https://minstroyrf.gov.ru/%')"
    )
    op.execute(
        "ALTER TABLE platform.ntd_catalogue_query_receipts ADD CONSTRAINT "
        "ntd_catalogue_query_receipts_official_endpoint_check CHECK ("
        "official_endpoint LIKE 'https://minstroyrf.gov.ru/%')"
    )
