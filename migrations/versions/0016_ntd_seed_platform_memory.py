"""Add bounded official NTD seed persistence and retrieval contracts.

Revision ID: 0016_ntd_seed
Revises: 0015_practice_authority
"""

from __future__ import annotations

import os

from alembic import op

revision = "0016_ntd_seed"
down_revision = "0015_practice_authority"
branch_labels = None
depends_on = None

PLATFORM_TABLES = (
    "ntd_seed_manifests",
    "practice_guide_normative_references",
    "ntd_catalogue_query_receipts",
    "practice_guide_ntd_resolution_decisions",
    "normative_artifacts",
    "normative_edition_relationships",
    "normative_provision_candidates",
    "normative_provision_versions",
    "normative_references",
    "normative_activation_decisions",
    "normative_applicability_decisions",
    "normative_seed_outcomes",
    "ntd_parse_receipts",
    "ntd_gaps",
    "ntd_conflicts",
    "practice_ntd_alignments",
    "ntd_backup_manifests",
)


def upgrade() -> None:
    _create_roles()
    _create_seed_and_acquisition_ledger()
    _create_edition_and_provision_canon()
    _create_alignment_and_durability()
    _create_projection()
    _apply_guards_and_grants()


def _create_roles() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_ntd_ingestion_service') THEN "
        "CREATE ROLE asd_ntd_ingestion_service NOLOGIN NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOINHERIT; END IF; "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='asd_ntd_gateway_service') THEN "
        "CREATE ROLE asd_ntd_gateway_service NOLOGIN NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOINHERIT; END IF; END $$"
    )


def _create_seed_and_acquisition_ledger() -> None:
    op.execute(
        """
        CREATE TABLE platform.ntd_seed_manifests (
          seed_manifest_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          profile_version text NOT NULL CHECK (lower(profile_version)<>'latest'),
          practice_guide_edition_id uuid NOT NULL
            REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL
            REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          page_numbers integer[] NOT NULL CHECK (page_numbers=ARRAY[15,16,17,18,19]),
          raw_mention_count integer NOT NULL CHECK (raw_mention_count>0),
          identity_count integer NOT NULL CHECK (identity_count>0),
          manifest_fingerprint text NOT NULL UNIQUE
            CHECK (manifest_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          supersedes_version bigint,
          created_by_identity_id text NOT NULL,
          created_at timestamptz NOT NULL,
          PRIMARY KEY (seed_manifest_id,version),
          FOREIGN KEY (seed_manifest_id,supersedes_version)
            REFERENCES platform.ntd_seed_manifests(seed_manifest_id,version) ON DELETE RESTRICT,
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          )
        );
        CREATE TABLE platform.practice_guide_normative_references (
          practice_guide_reference_id uuid PRIMARY KEY,
          seed_manifest_id uuid NOT NULL,
          seed_manifest_version bigint NOT NULL,
          practice_guide_edition_id uuid NOT NULL
            REFERENCES platform.practice_guide_editions(practice_guide_edition_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL
            REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          pdf_page integer NOT NULL CHECK (pdf_page BETWEEN 15 AND 19),
          region double precision[] NOT NULL,
          occurrence_ordinal integer NOT NULL CHECK (occurrence_ordinal>=1),
          raw_designation text NOT NULL,
          raw_title text,
          raw_context text NOT NULL,
          normalized_designation text NOT NULL,
          stable_identity_key text NOT NULL,
          document_kind text NOT NULL,
          printed_edition text,
          extraction_method text NOT NULL,
          extraction_receipt_digest text NOT NULL
            CHECK (extraction_receipt_digest ~ '^sha256:[a-f0-9]{64}$'),
          source_fragment_digest text NOT NULL
            CHECK (source_fragment_digest ~ '^sha256:[a-f0-9]{64}$'),
          verification_status text NOT NULL CHECK (verification_status IN (
            'geometry_verified_semantics_unresolved','resolved','gap','superseded'
          )),
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (seed_manifest_id,seed_manifest_version)
            REFERENCES platform.ntd_seed_manifests(seed_manifest_id,version) ON DELETE RESTRICT,
          CHECK (cardinality(region)=4),
          CHECK (region[1]>=0 AND region[1]<region[3] AND region[3]<=1),
          CHECK (region[2]>=0 AND region[2]<region[4] AND region[4]<=1),
          UNIQUE (seed_manifest_id,seed_manifest_version,occurrence_ordinal)
        );
        CREATE TABLE platform.ntd_catalogue_query_receipts (
          acquisition_receipt_id uuid PRIMARY KEY,
          practice_guide_reference_id uuid
            REFERENCES platform.practice_guide_normative_references(practice_guide_reference_id)
            ON DELETE RESTRICT,
          previous_receipt_id uuid
            REFERENCES platform.ntd_catalogue_query_receipts(acquisition_receipt_id)
            ON DELETE RESTRICT,
          normalized_query text NOT NULL,
          official_endpoint text NOT NULL CHECK (official_endpoint LIKE 'https://minstroyrf.gov.ru/%'),
          requested_at timestamptz NOT NULL,
          returned_catalog_ids text[] NOT NULL,
          selected_catalog_id text,
          selection_reason text,
          rejected_candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
          artifact_url text,
          http_status integer CHECK (http_status BETWEEN 100 AND 599),
          content_type text,
          etag text,
          last_modified text,
          byte_length bigint CHECK (byte_length>=0),
          content_digest text CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          parser_version text NOT NULL CHECK (lower(parser_version)<>'latest'),
          terminal_status text NOT NULL CHECK (terminal_status IN (
            'resolved_exact','resolved_superseded','ambiguous_official_records',
            'official_metadata_only','official_artifact_unavailable','official_access_blocked',
            'not_found_official','exact_edition_not_found','edition_conflict',
            'supersession_unresolved','download_failed','artifact_invalid','parse_partial',
            'parsed_verified','blocked_deterministic_failure'
          )),
          failure_code text,
          receipt_fingerprint text NOT NULL UNIQUE
            CHECK (receipt_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CHECK ((selected_catalog_id IS NULL)=(selection_reason IS NULL))
        );
        CREATE TABLE platform.practice_guide_ntd_resolution_decisions (
          resolution_decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          practice_guide_reference_id uuid NOT NULL
            REFERENCES platform.practice_guide_normative_references(practice_guide_reference_id)
            ON DELETE RESTRICT,
          acquisition_receipt_id uuid NOT NULL
            REFERENCES platform.ntd_catalogue_query_receipts(acquisition_receipt_id)
            ON DELETE RESTRICT,
          resolution_status text NOT NULL CHECK (resolution_status IN (
            'resolved_exact','resolved_superseded','ambiguous_official_records',
            'official_metadata_only','official_artifact_unavailable','official_access_blocked',
            'not_found_official','exact_edition_not_found','edition_conflict',
            'supersession_unresolved','download_failed','artifact_invalid','parse_partial',
            'parsed_verified','blocked_deterministic_failure'
          )),
          normative_document_id uuid
            REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          mentioned_edition_id uuid
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          current_official_edition_id uuid
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          as_of_edition_id uuid
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          conflict_status text,
          uncertainty_codes text[] NOT NULL DEFAULT '{}',
          decision_reason text NOT NULL,
          supersedes_version bigint,
          decision_fingerprint text NOT NULL UNIQUE
            CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          decided_at timestamptz NOT NULL,
          PRIMARY KEY (resolution_decision_id,version),
          UNIQUE (practice_guide_reference_id,version),
          FOREIGN KEY (resolution_decision_id,supersedes_version)
            REFERENCES platform.practice_guide_ntd_resolution_decisions(
              resolution_decision_id,version
            ) ON DELETE RESTRICT,
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          )
        );
        """
    )


def _create_edition_and_provision_canon() -> None:
    op.execute(
        """
        DO $$ DECLARE constraint_name name; BEGIN
          SELECT conname INTO constraint_name FROM pg_constraint
          WHERE conrelid='platform.structural_units'::regclass
            AND contype='c' AND pg_get_constraintdef(oid) LIKE '%unit_type%';
          IF constraint_name IS NOT NULL THEN
            EXECUTE format('ALTER TABLE platform.structural_units DROP CONSTRAINT %I',constraint_name);
          END IF;
        END $$;
        ALTER TABLE platform.structural_units
          ADD CONSTRAINT structural_units_ntd_seed_unit_type_ck
          CHECK (unit_type IN (
            'section','clause','subclause','table','figure','appendix',
            'definition_scope','form','other'
          ));
        ALTER TABLE platform.normative_editions
          ADD COLUMN official_catalog_id text,
          ADD COLUMN official_catalog_url text
            CHECK (official_catalog_url IS NULL OR official_catalog_url LIKE 'https://minstroyrf.gov.ru/%'),
          ADD COLUMN approval_metadata jsonb,
          ADD COLUMN retrieved_at timestamptz,
          ADD COLUMN edition_fingerprint text UNIQUE
            CHECK (edition_fingerprint IS NULL OR edition_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          ADD CONSTRAINT normative_editions_no_mutable_latest_ck
          CHECK (lower(edition_label)<>'latest');
        CREATE TABLE platform.normative_artifacts (
          normative_artifact_id uuid PRIMARY KEY,
          normative_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL UNIQUE
            REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          official_catalog_id text NOT NULL,
          official_url text NOT NULL CHECK (official_url LIKE 'https://minstroyrf.gov.ru/%'),
          filename text NOT NULL,
          media_type text NOT NULL,
          size_bytes bigint NOT NULL CHECK (size_bytes>0),
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          relation_to_edition text NOT NULL CHECK (relation_to_edition IN (
            'catalog_record','primary_text','attachment','amendment','form','appendix'
          )),
          retrieval_metadata_digest text NOT NULL
            CHECK (retrieval_metadata_digest ~ '^sha256:[a-f0-9]{64}$'),
          registered_at timestamptz NOT NULL,
          UNIQUE (normative_edition_id,official_url,content_digest)
        );
        CREATE TABLE platform.normative_edition_relationships (
          relationship_id uuid PRIMARY KEY,
          from_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          to_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          relation_kind text NOT NULL CHECK (relation_kind IN (
            'supersedes','superseded_by','amends','amended_by','replaces','derived_from',
            'effective_from','effective_to','unknown_relation'
          )),
          official_evidence_ref text NOT NULL,
          source_locator_id uuid
            REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          verification_status text NOT NULL CHECK (verification_status IN (
            'verified','unresolved','rejected'
          )),
          relationship_fingerprint text NOT NULL UNIQUE
            CHECK (relationship_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          CHECK (from_edition_id<>to_edition_id),
          UNIQUE (from_edition_id,to_edition_id,relation_kind,official_evidence_ref)
        );
        CREATE TABLE platform.normative_provision_candidates (
          provision_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL CHECK (candidate_version>=1),
          normative_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL
            REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          structural_path text NOT NULL,
          provision_kind text NOT NULL CHECK (provision_kind IN (
            'section','clause','subclause','table','appendix','form','definition','other'
          )),
          page_number integer CHECK (page_number>=1),
          region double precision[],
          verbatim_text text NOT NULL,
          extraction_method text NOT NULL CHECK (extraction_method IN (
            'native_pdf_layout','native_html_structure','ocr_region','vlm_bounded_region'
          )),
          extraction_profile_version text NOT NULL CHECK (lower(extraction_profile_version)<>'latest'),
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          model_provenance jsonb,
          created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (provision_candidate_id,candidate_version),
          CHECK ((page_number IS NULL)=(region IS NULL)),
          CHECK (region IS NULL OR cardinality(region)=4),
          CHECK (region IS NULL OR (
            region[1]>=0 AND region[1]<region[3] AND region[3]<=1
            AND region[2]>=0 AND region[2]<region[4] AND region[4]<=1
          )),
          UNIQUE (normative_edition_id,source_version_id,structural_path,candidate_version,content_digest)
        );
        CREATE TABLE platform.normative_provision_versions (
          normative_provision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          provision_candidate_id uuid NOT NULL,
          candidate_version bigint NOT NULL,
          normative_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL
            REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          structural_unit_id uuid
            REFERENCES platform.structural_units(structural_unit_id) ON DELETE RESTRICT,
          structural_path text NOT NULL,
          provision_kind text NOT NULL CHECK (provision_kind IN (
            'section','clause','subclause','table','appendix','form','definition','other'
          )),
          page_number integer CHECK (page_number>=1),
          region double precision[],
          verbatim_text text NOT NULL,
          content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[a-f0-9]{64}$'),
          semantic_fingerprint text NOT NULL
            CHECK (semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          verification_status text NOT NULL CHECK (verification_status IN (
            'candidate','verified','quarantined','rejected'
          )),
          verification_decision_ref text NOT NULL,
          verified_by_identity_id text NOT NULL,
          verified_at timestamptz NOT NULL,
          supersedes_version bigint,
          PRIMARY KEY (normative_provision_id,version),
          FOREIGN KEY (provision_candidate_id,candidate_version)
            REFERENCES platform.normative_provision_candidates(
              provision_candidate_id,candidate_version
            ) ON DELETE RESTRICT,
          FOREIGN KEY (normative_provision_id,supersedes_version)
            REFERENCES platform.normative_provision_versions(normative_provision_id,version)
            ON DELETE RESTRICT,
          CHECK ((page_number IS NULL)=(region IS NULL)),
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          ),
          CHECK (verification_status<>'verified' OR (
            structural_unit_id IS NOT NULL AND length(verbatim_text)>0
          )),
          UNIQUE (provision_candidate_id,candidate_version,verification_decision_ref)
        );
        CREATE TABLE platform.normative_activation_decisions (
          activation_decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          normative_document_id uuid NOT NULL
            REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          selected_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          as_of date NOT NULL,
          status text NOT NULL CHECK (status IN ('active','superseded','indeterminate','suspended')),
          authority_reference text NOT NULL,
          evidence_refs jsonb NOT NULL,
          supersedes_version bigint,
          decision_fingerprint text NOT NULL UNIQUE
            CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          decided_at timestamptz NOT NULL,
          PRIMARY KEY (activation_decision_id,version),
          FOREIGN KEY (activation_decision_id,supersedes_version)
            REFERENCES platform.normative_activation_decisions(activation_decision_id,version)
            ON DELETE RESTRICT,
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          )
        );
        CREATE TABLE platform.normative_references (
          normative_reference_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          source_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          source_provision_id uuid,
          source_provision_version bigint,
          source_locator_id uuid NOT NULL
            REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          raw_designation text NOT NULL,
          normalized_designation text NOT NULL,
          target_document_id uuid
            REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          target_edition_id uuid
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          resolution_status text NOT NULL CHECK (resolution_status IN (
            'resolved_exact','ambiguous','external_reference_gap','not_found'
          )),
          decision_ref text NOT NULL,
          reference_fingerprint text NOT NULL UNIQUE
            CHECK (reference_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (normative_reference_id,version),
          FOREIGN KEY (source_provision_id,source_provision_version)
            REFERENCES platform.normative_provision_versions(normative_provision_id,version)
            ON DELETE RESTRICT,
          CHECK ((source_provision_id IS NULL)=(source_provision_version IS NULL)),
          CHECK ((target_edition_id IS NULL) OR (target_document_id IS NOT NULL))
        );
        CREATE TABLE platform.normative_applicability_decisions (
          applicability_decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          normative_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          scope_kind text NOT NULL CHECK (scope_kind IN ('platform_general','retrieval_as_of')),
          scope_ref text,
          as_of date NOT NULL,
          applicability_status text NOT NULL CHECK (applicability_status IN (
            'applicable','not_applicable','indeterminate'
          )),
          predicate jsonb NOT NULL,
          evidence_refs jsonb NOT NULL,
          decided_by_identity_id text NOT NULL,
          decision_fingerprint text NOT NULL UNIQUE
            CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          decided_at timestamptz NOT NULL,
          PRIMARY KEY (applicability_decision_id,version)
        );
        """
    )


def _create_alignment_and_durability() -> None:
    op.execute(
        """
        CREATE TABLE platform.normative_seed_outcomes (
          seed_manifest_id uuid NOT NULL,
          seed_manifest_version bigint NOT NULL,
          stable_identity_key text NOT NULL,
          normalized_designation text NOT NULL,
          normative_document_id uuid
            REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          normative_edition_id uuid
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          terminal_status text NOT NULL CHECK (terminal_status IN (
            'resolved_exact','resolved_superseded','ambiguous_official_records',
            'official_metadata_only','official_artifact_unavailable','official_access_blocked',
            'not_found_official','exact_edition_not_found','edition_conflict',
            'supersession_unresolved','download_failed','artifact_invalid','parse_partial',
            'parsed_verified','blocked_deterministic_failure'
          )),
          terminal_receipt_id uuid NOT NULL
            REFERENCES platform.ntd_catalogue_query_receipts(acquisition_receipt_id)
            ON DELETE RESTRICT,
          outcome_fingerprint text NOT NULL UNIQUE
            CHECK (outcome_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (seed_manifest_id,seed_manifest_version,stable_identity_key),
          FOREIGN KEY (seed_manifest_id,seed_manifest_version)
            REFERENCES platform.ntd_seed_manifests(seed_manifest_id,version) ON DELETE RESTRICT,
          CHECK ((normative_edition_id IS NULL) OR (normative_document_id IS NOT NULL))
        );
        CREATE TABLE platform.ntd_parse_receipts (
          parse_receipt_id uuid PRIMARY KEY,
          normative_artifact_id uuid NOT NULL
            REFERENCES platform.normative_artifacts(normative_artifact_id) ON DELETE RESTRICT,
          parser_version text NOT NULL CHECK (lower(parser_version)<>'latest'),
          extraction_method text NOT NULL,
          page_count integer CHECK (page_count>=1),
          native_text_characters bigint NOT NULL CHECK (native_text_characters>=0),
          candidate_count bigint NOT NULL CHECK (candidate_count>=0),
          verified_provision_count bigint NOT NULL CHECK (verified_provision_count>=0),
          ocr_pages integer[] NOT NULL DEFAULT '{}',
          terminal_status text NOT NULL CHECK (terminal_status IN (
            'parse_partial','parsed_verified','blocked_deterministic_failure','artifact_invalid'
          )),
          extraction_fingerprint text NOT NULL UNIQUE
            CHECK (extraction_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL
        );
        CREATE TABLE platform.ntd_gaps (
          normative_gap_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          stable_identity_key text NOT NULL,
          gap_code text NOT NULL CHECK (gap_code IN (
            'official_artifact_unavailable','official_access_blocked','identity_ambiguous',
            'exact_edition_not_found','metadata_only','edition_conflict',
            'supersession_unresolved','missing_exact_locator','external_reference_gap',
            'parse_partial','applicability_indeterminate'
          )),
          blocker_scope text NOT NULL,
          evidence_refs jsonb NOT NULL,
          status text NOT NULL CHECK (status IN ('open','resolved','superseded')),
          supersedes_version bigint,
          gap_fingerprint text NOT NULL UNIQUE CHECK (gap_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (normative_gap_id,version),
          FOREIGN KEY (normative_gap_id,supersedes_version)
            REFERENCES platform.ntd_gaps(normative_gap_id,version) ON DELETE RESTRICT,
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          )
        );
        CREATE TABLE platform.ntd_conflicts (
          normative_conflict_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          conflict_kind text NOT NULL,
          participant_refs jsonb NOT NULL,
          evidence_refs jsonb NOT NULL,
          state text NOT NULL CHECK (state IN ('open','indeterminate','resolved','superseded')),
          resolution_decision_ref text,
          supersedes_version bigint,
          conflict_fingerprint text NOT NULL UNIQUE
            CHECK (conflict_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL,
          PRIMARY KEY (normative_conflict_id,version),
          FOREIGN KEY (normative_conflict_id,supersedes_version)
            REFERENCES platform.ntd_conflicts(normative_conflict_id,version) ON DELETE RESTRICT,
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          )
        );
        CREATE TABLE platform.practice_ntd_alignments (
          alignment_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          practice_guide_reference_id uuid NOT NULL
            REFERENCES platform.practice_guide_normative_references(practice_guide_reference_id)
            ON DELETE RESTRICT,
          guidance_unit_id uuid,
          guidance_unit_version bigint,
          normative_document_id uuid
            REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          normative_edition_id uuid
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          normative_provision_id uuid,
          normative_provision_version bigint,
          alignment_status text NOT NULL CHECK (alignment_status IN (
            'confirmed_by_ntd','practice_only','normative_conflict','edition_warning','unresolved'
          )),
          as_of date NOT NULL,
          evidence_refs jsonb NOT NULL,
          decision_ref text NOT NULL,
          supersedes_version bigint,
          alignment_fingerprint text NOT NULL UNIQUE
            CHECK (alignment_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          decided_at timestamptz NOT NULL,
          PRIMARY KEY (alignment_id,version),
          FOREIGN KEY (guidance_unit_id,guidance_unit_version)
            REFERENCES platform.practice_guidance_units(guidance_unit_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (normative_provision_id,normative_provision_version)
            REFERENCES platform.normative_provision_versions(normative_provision_id,version)
            ON DELETE RESTRICT,
          FOREIGN KEY (alignment_id,supersedes_version)
            REFERENCES platform.practice_ntd_alignments(alignment_id,version) ON DELETE RESTRICT,
          CHECK ((guidance_unit_id IS NULL)=(guidance_unit_version IS NULL)),
          CHECK ((normative_provision_id IS NULL)=(normative_provision_version IS NULL)),
          CHECK (
            (version=1 AND supersedes_version IS NULL)
            OR (version>1 AND supersedes_version=version-1)
          )
        );
        CREATE TABLE platform.ntd_backup_manifests (
          backup_manifest_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version>=1),
          seed_manifest_fingerprint text NOT NULL
            CHECK (seed_manifest_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          source_versions jsonb NOT NULL,
          edition_fingerprints jsonb NOT NULL,
          provision_fingerprints jsonb NOT NULL,
          activation_decision_refs jsonb NOT NULL,
          gap_fingerprints text[] NOT NULL,
          conflict_fingerprints text[] NOT NULL,
          projection_profile_version text NOT NULL CHECK (lower(projection_profile_version)<>'latest'),
          canonical_semantic_fingerprint text NOT NULL
            CHECK (canonical_semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          created_at timestamptz NOT NULL,
          PRIMARY KEY (backup_manifest_id,version),
          UNIQUE (seed_manifest_fingerprint,canonical_semantic_fingerprint)
        );
        """
    )


def _create_projection() -> None:
    op.execute(
        """
        CREATE TABLE projection.ntd_lexical_versions (
          lexical_version_id uuid PRIMARY KEY,
          profile_version text NOT NULL CHECK (lower(profile_version)<>'latest'),
          canonical_semantic_fingerprint text NOT NULL
            CHECK (canonical_semantic_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          status text NOT NULL CHECK (status IN ('building','ready','empty','stale','failed')),
          built_at timestamptz,
          UNIQUE (profile_version,canonical_semantic_fingerprint)
        );
        CREATE TABLE projection.ntd_lexical_entries (
          lexical_version_id uuid NOT NULL
            REFERENCES projection.ntd_lexical_versions(lexical_version_id) ON DELETE CASCADE,
          normative_provision_id uuid NOT NULL,
          normative_provision_version bigint NOT NULL,
          normative_edition_id uuid NOT NULL
            REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          structural_path text NOT NULL,
          verbatim_text text NOT NULL,
          search_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian',verbatim_text)) STORED,
          PRIMARY KEY (lexical_version_id,normative_provision_id,normative_provision_version),
          FOREIGN KEY (normative_provision_id,normative_provision_version)
            REFERENCES platform.normative_provision_versions(normative_provision_id,version)
            ON DELETE RESTRICT
        );
        CREATE INDEX ix_ntd_lexical_entries_fts
          ON projection.ntd_lexical_entries USING gin(search_vector);
        """
    )


def _apply_guards_and_grants() -> None:
    for table in PLATFORM_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE "
            f"ON platform.{table} FOR EACH ROW "
            "EXECUTE FUNCTION platform.reject_immutable_mutation()"
        )
    op.execute("GRANT USAGE ON SCHEMA platform TO asd_ntd_ingestion_service")
    op.execute("GRANT USAGE ON SCHEMA platform TO asd_ntd_gateway_service")
    for table in PLATFORM_TABLES:
        op.execute(f"GRANT SELECT,INSERT ON platform.{table} TO asd_ntd_ingestion_service")
        op.execute(f"GRANT SELECT ON platform.{table} TO asd_ntd_gateway_service")
    for table in (
        "official_source_registry_entries",
        "objects",
        "object_receipts",
        "source_artifacts",
        "acquisition_attempts",
        "source_versions",
        "source_locators",
        "evidence_links",
        "normative_documents",
        "normative_editions",
        "normative_edition_states",
        "structural_units",
        "practice_guides",
        "practice_guide_editions",
        "practice_guidance_units",
    ):
        op.execute(f"GRANT SELECT,INSERT ON platform.{table} TO asd_ntd_ingestion_service")
        op.execute(f"GRANT SELECT ON platform.{table} TO asd_ntd_gateway_service")
    op.execute("GRANT UPDATE ON platform.acquisition_attempts TO asd_ntd_ingestion_service")
    op.execute("GRANT USAGE ON SCHEMA projection TO asd_projection_builder")
    op.execute(
        "GRANT SELECT,INSERT,UPDATE,DELETE ON projection.ntd_lexical_versions,"
        "projection.ntd_lexical_entries TO asd_projection_builder"
    )
    op.execute(
        "GRANT SELECT ON projection.ntd_lexical_versions,projection.ntd_lexical_entries "
        "TO asd_ntd_gateway_service"
    )
    op.execute("GRANT SELECT ON platform.normative_provision_versions TO asd_projection_builder")


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("NTD seed downgrade requires an explicitly disposable database")
    op.execute("DROP TABLE projection.ntd_lexical_entries")
    op.execute("DROP TABLE projection.ntd_lexical_versions")
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE platform.{table}")
    op.execute(
        "ALTER TABLE platform.normative_editions "
        "DROP CONSTRAINT normative_editions_no_mutable_latest_ck, "
        "DROP COLUMN edition_fingerprint, DROP COLUMN retrieved_at, "
        "DROP COLUMN approval_metadata, DROP COLUMN official_catalog_url, "
        "DROP COLUMN official_catalog_id"
    )
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM platform.structural_units WHERE unit_type IN ('form','other')
          ) THEN
            RAISE EXCEPTION 'Cannot downgrade while NTD form/other structural units exist';
          END IF;
        END $$;
        ALTER TABLE platform.structural_units
          DROP CONSTRAINT structural_units_ntd_seed_unit_type_ck;
        ALTER TABLE platform.structural_units
          ADD CONSTRAINT structural_units_unit_type_check
          CHECK (unit_type IN (
            'section','clause','subclause','table','figure','appendix','definition_scope'
          ));
        """
    )
