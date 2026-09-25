"""Add canonical NTD text, chunk, embedding and readiness layers.

Revision ID: 0033_ntd_memory
Revises: 0032_ntd_consultant
Create Date: 2026-08-30
"""

# ruff: noqa: RUF001 -- SQL normalization intentionally includes Cyrillic ranges.

from __future__ import annotations

import os

from alembic import op

revision = "0033_ntd_memory"
down_revision = "0032_ntd_consultant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform.ntd_corpus_objects (
          corpus_object_id uuid PRIMARY KEY,
          artifact_digest text NOT NULL UNIQUE CHECK (artifact_digest ~ '^sha256:[a-f0-9]{64}$'),
          size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
          media_type text NOT NULL,
          authority_class text NOT NULL CHECK (authority_class IN (
            'official','official_binding_recovered','legacy_reference','gesn_candidate'
          )),
          logical_document_key text NOT NULL,
          stable_designation text NOT NULL,
          alternative_designations text[] NOT NULL DEFAULT '{}',
          title text NOT NULL,
          printed_edition text,
          source_artifact_id uuid REFERENCES platform.source_artifacts(source_artifact_id) ON DELETE RESTRICT,
          source_version_id uuid REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          normative_document_id uuid REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          normative_edition_id uuid REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          normative_artifact_id uuid REFERENCES platform.normative_artifacts(normative_artifact_id) ON DELETE RESTRICT,
          original_paths jsonb NOT NULL,
          recovered_paths jsonb NOT NULL,
          duplicate_representation_digests jsonb NOT NULL DEFAULT '[]'::jsonb,
          provenance jsonb NOT NULL,
          bytes_status text NOT NULL CHECK (bytes_status IN ('present_verified','not_locally_available','digest_mismatch','unsupported')),
          edition_currency_status text NOT NULL CHECK (edition_currency_status IN ('not_checked','checked')),
          terminal_outcome text NOT NULL CHECK (terminal_outcome IN (
            'admitted','blocked_bytes_unavailable','blocked_digest_mismatch','blocked_unsupported_format'
          )),
          blocker_code text,
          corpus_profile_version text NOT NULL CHECK (lower(corpus_profile_version) <> 'latest'),
          corpus_fingerprint text NOT NULL UNIQUE CHECK (corpus_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CHECK ((terminal_outcome='admitted')=(source_version_id IS NOT NULL))
        );
        CREATE INDEX ntd_corpus_objects_designation_idx
          ON platform.ntd_corpus_objects ((regexp_replace(lower(stable_designation),'[^0-9a-zа-я]+','','g')));

        CREATE TABLE platform.ntd_corpus_pages (
          corpus_page_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          corpus_object_id uuid NOT NULL REFERENCES platform.ntd_corpus_objects(corpus_object_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          page_number integer NOT NULL CHECK (page_number >= 1),
          page_kind text NOT NULL CHECK (page_kind IN (
            'native','raster','mixed','table_heavy','damaged_native','blank','unsupported_corrupt'
          )),
          width_points numeric NOT NULL CHECK (width_points > 0),
          height_points numeric NOT NULL CHECK (height_points > 0),
          rotation_degrees integer NOT NULL CHECK (rotation_degrees IN (0,90,180,270)),
          render_digest text CHECK (render_digest IS NULL OR render_digest ~ '^sha256:[a-f0-9]{64}$'),
          raw_transcription text NOT NULL,
          normalized_text text NOT NULL,
          raw_text_digest text NOT NULL CHECK (raw_text_digest ~ '^sha256:[a-f0-9]{64}$'),
          normalized_text_digest text NOT NULL CHECK (normalized_text_digest ~ '^sha256:[a-f0-9]{64}$'),
          source_locator_id uuid NOT NULL REFERENCES platform.source_locators(source_locator_id) ON DELETE RESTRICT,
          extraction_method text NOT NULL,
          extraction_profile_version text NOT NULL CHECK (lower(extraction_profile_version) <> 'latest'),
          model_profile text,
          request_digest text CHECK (request_digest IS NULL OR request_digest ~ '^sha256:[a-f0-9]{64}$'),
          response_digest text CHECK (response_digest IS NULL OR response_digest ~ '^sha256:[a-f0-9]{64}$'),
          critical_token_status text NOT NULL CHECK (critical_token_status IN ('not_applicable','checked','requires_review')),
          terminal_outcome text NOT NULL CHECK (terminal_outcome IN (
            'native_complete','ocr_complete','mixed_complete','table_complete','blank_verified','blocked_corrupt','blocked_extraction'
          )),
          blocker_code text,
          page_fingerprint text NOT NULL UNIQUE CHECK (page_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          supersedes_version bigint,
          PRIMARY KEY (corpus_page_id,version),
          UNIQUE (corpus_object_id,page_number,version),
          FOREIGN KEY (corpus_page_id,supersedes_version) REFERENCES platform.ntd_corpus_pages(corpus_page_id,version) ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR (version>1 AND supersedes_version=version-1))
        );

        CREATE TABLE platform.ntd_chunks (
          chunk_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          corpus_object_id uuid NOT NULL REFERENCES platform.ntd_corpus_objects(corpus_object_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          normative_document_id uuid REFERENCES platform.normative_documents(normative_document_id) ON DELETE RESTRICT,
          normative_edition_id uuid REFERENCES platform.normative_editions(normative_edition_id) ON DELETE RESTRICT,
          authority_class text NOT NULL CHECK (authority_class IN (
            'official','official_binding_recovered','legacy_reference','gesn_candidate'
          )),
          ordinal integer NOT NULL CHECK (ordinal >= 1),
          page_start integer NOT NULL CHECK (page_start >= 1),
          page_end integer NOT NULL CHECK (page_end >= page_start),
          structural_path text NOT NULL,
          source_locator_ids uuid[] NOT NULL CHECK (cardinality(source_locator_ids) > 0),
          raw_text text NOT NULL CHECK (length(raw_text) > 0),
          normalized_text text NOT NULL CHECK (length(normalized_text) > 0),
          raw_text_digest text NOT NULL CHECK (raw_text_digest ~ '^sha256:[a-f0-9]{64}$'),
          normalized_text_digest text NOT NULL CHECK (normalized_text_digest ~ '^sha256:[a-f0-9]{64}$'),
          chunking_profile_version text NOT NULL CHECK (lower(chunking_profile_version) <> 'latest'),
          parent_chunk_id uuid,
          continuation_of_chunk_id uuid,
          chunk_fingerprint text NOT NULL UNIQUE CHECK (chunk_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          search_vector tsvector GENERATED ALWAYS AS (
            to_tsvector('russian', structural_path || ' ' || normalized_text)
          ) STORED,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          supersedes_version bigint,
          PRIMARY KEY (chunk_id,version),
          UNIQUE (corpus_object_id,ordinal,version),
          FOREIGN KEY (chunk_id,supersedes_version) REFERENCES platform.ntd_chunks(chunk_id,version) ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR (version>1 AND supersedes_version=version-1))
        );
        CREATE INDEX ntd_chunks_fts_gin ON platform.ntd_chunks USING gin(search_vector);
        CREATE INDEX ntd_chunks_source_idx ON platform.ntd_chunks(source_version_id,page_start,page_end);

        CREATE TABLE platform.ntd_structural_units (
          structural_unit_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          corpus_object_id uuid NOT NULL REFERENCES platform.ntd_corpus_objects(corpus_object_id) ON DELETE RESTRICT,
          source_version_id uuid NOT NULL REFERENCES platform.source_versions(source_version_id) ON DELETE RESTRICT,
          parent_structural_unit_id uuid,
          unit_kind text NOT NULL CHECK (unit_kind IN (
            'document','section','clause','subclause','definition','table','table_row','note','appendix','page_region'
          )),
          ordinal integer NOT NULL CHECK (ordinal >= 1),
          label text,
          heading text,
          page_start integer NOT NULL CHECK (page_start >= 1),
          page_end integer NOT NULL CHECK (page_end >= page_start),
          structural_path text NOT NULL,
          source_locator_ids uuid[] NOT NULL CHECK (cardinality(source_locator_ids) > 0),
          raw_text text NOT NULL,
          normalized_text text NOT NULL,
          raw_text_digest text NOT NULL CHECK (raw_text_digest ~ '^sha256:[a-f0-9]{64}$'),
          normalized_text_digest text NOT NULL CHECK (normalized_text_digest ~ '^sha256:[a-f0-9]{64}$'),
          derivation_method text NOT NULL,
          confidence_status text NOT NULL CHECK (confidence_status IN ('deterministic','reviewed','candidate')),
          unit_fingerprint text NOT NULL UNIQUE CHECK (unit_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          supersedes_version bigint,
          PRIMARY KEY (structural_unit_id,version),
          UNIQUE (corpus_object_id,ordinal,version),
          FOREIGN KEY (structural_unit_id,supersedes_version)
            REFERENCES platform.ntd_structural_units(structural_unit_id,version) ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR (version>1 AND supersedes_version=version-1))
        );
        CREATE INDEX ntd_structural_units_parent_idx
          ON platform.ntd_structural_units(corpus_object_id,parent_structural_unit_id,ordinal);
        CREATE INDEX ntd_structural_units_locator_idx
          ON platform.ntd_structural_units(source_version_id,page_start,page_end);

        CREATE TABLE platform.ntd_chunk_profiles (
          chunk_profile_id uuid PRIMARY KEY,
          profile_key text NOT NULL,
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          strategy text NOT NULL CHECK (strategy IN ('fixed','structure_aware','contextual','hierarchical')),
          parameters jsonb NOT NULL,
          qualification_status text NOT NULL CHECK (qualification_status IN ('candidate','qualified_primary','qualified_fallback','rejected')),
          benchmark_receipt jsonb NOT NULL,
          profile_fingerprint text NOT NULL UNIQUE CHECK (profile_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (profile_key,profile_version)
        );

        CREATE TABLE platform.ntd_contextual_chunks (
          contextual_chunk_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          chunk_id uuid NOT NULL,
          chunk_version bigint NOT NULL,
          chunk_profile_id uuid NOT NULL REFERENCES platform.ntd_chunk_profiles(chunk_profile_id) ON DELETE RESTRICT,
          structural_unit_ids uuid[] NOT NULL CHECK (cardinality(structural_unit_ids) > 0),
          designation_context text NOT NULL,
          title_context text NOT NULL,
          section_context text NOT NULL,
          parent_heading_context text NOT NULL,
          scope_context text NOT NULL,
          regulated_work_context text NOT NULL,
          page_range_context text NOT NULL,
          derived_context text NOT NULL,
          context_digest text NOT NULL CHECK (context_digest ~ '^sha256:[a-f0-9]{64}$'),
          input_text text NOT NULL,
          input_digest text NOT NULL CHECK (input_digest ~ '^sha256:[a-f0-9]{64}$'),
          contextual_fingerprint text NOT NULL UNIQUE CHECK (contextual_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          lexical_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian',input_text)) STORED,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          supersedes_version bigint,
          PRIMARY KEY (contextual_chunk_id,version),
          UNIQUE (chunk_profile_id,chunk_id,chunk_version,version),
          FOREIGN KEY (chunk_id,chunk_version) REFERENCES platform.ntd_chunks(chunk_id,version) ON DELETE RESTRICT,
          FOREIGN KEY (contextual_chunk_id,supersedes_version)
            REFERENCES platform.ntd_contextual_chunks(contextual_chunk_id,version) ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR (version>1 AND supersedes_version=version-1))
        );
        CREATE INDEX ntd_contextual_chunks_fts_gin
          ON platform.ntd_contextual_chunks USING gin(lexical_vector);

        CREATE TABLE platform.ntd_embedding_profiles (
          embedding_profile_id uuid PRIMARY KEY,
          profile_key text NOT NULL,
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          model_id text NOT NULL,
          model_revision text NOT NULL,
          model_digest text NOT NULL CHECK (model_digest ~ '^sha256:[a-f0-9]{64}$'),
          dimension integer NOT NULL CHECK (dimension > 0),
          normalization text NOT NULL CHECK (normalization IN ('l2','none')),
          input_construction text NOT NULL,
          qualification_receipt jsonb NOT NULL,
          status text NOT NULL CHECK (status IN ('candidate','qualified','retired')),
          profile_fingerprint text NOT NULL UNIQUE CHECK (profile_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (profile_key,profile_version)
        );

        CREATE TABLE platform.ntd_chunk_embeddings (
          embedding_profile_id uuid NOT NULL REFERENCES platform.ntd_embedding_profiles(embedding_profile_id) ON DELETE RESTRICT,
          contextual_chunk_id uuid NOT NULL,
          contextual_chunk_version bigint NOT NULL,
          dimension integer NOT NULL CHECK (dimension > 0),
          embedding vector(1024) NOT NULL,
          embedding_digest text NOT NULL CHECK (embedding_digest ~ '^sha256:[a-f0-9]{64}$'),
          input_digest text NOT NULL CHECK (input_digest ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (embedding_profile_id,contextual_chunk_id,contextual_chunk_version),
          UNIQUE (embedding_profile_id,embedding_digest,contextual_chunk_id),
          FOREIGN KEY (contextual_chunk_id,contextual_chunk_version)
            REFERENCES platform.ntd_contextual_chunks(contextual_chunk_id,version) ON DELETE RESTRICT,
          CHECK (vector_dims(embedding)=dimension)
        );
        CREATE INDEX ntd_chunk_embeddings_hnsw
          ON platform.ntd_chunk_embeddings USING hnsw (embedding vector_cosine_ops)
          WITH (m=16,ef_construction=64);

        CREATE TABLE platform.ntd_reranker_profiles (
          reranker_profile_id uuid PRIMARY KEY,
          profile_key text NOT NULL,
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          model_id text NOT NULL,
          model_revision text NOT NULL,
          model_digest text NOT NULL CHECK (model_digest ~ '^sha256:[a-f0-9]{64}$'),
          dtype text NOT NULL CHECK (dtype IN ('float16','bfloat16','float32')),
          instruction text NOT NULL,
          qualification_receipt jsonb NOT NULL,
          status text NOT NULL CHECK (status IN ('candidate','qualified','retired')),
          profile_fingerprint text NOT NULL UNIQUE CHECK (profile_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (profile_key,profile_version)
        );

        CREATE TABLE platform.ntd_retrieval_profiles (
          retrieval_profile_id uuid PRIMARY KEY,
          profile_key text NOT NULL,
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          chunk_profile_id uuid NOT NULL REFERENCES platform.ntd_chunk_profiles(chunk_profile_id) ON DELETE RESTRICT,
          embedding_profile_id uuid REFERENCES platform.ntd_embedding_profiles(embedding_profile_id) ON DELETE RESTRICT,
          reranker_profile_id uuid REFERENCES platform.ntd_reranker_profiles(reranker_profile_id) ON DELETE RESTRICT,
          pipeline_kind text NOT NULL CHECK (pipeline_kind IN (
            'exact','fts','dense','exact_fts','fts_dense_rrf','hybrid_reranker',
            'hybrid_hierarchical','hybrid_graph','hybrid_graph_reranker'
          )),
          parameters jsonb NOT NULL,
          benchmark_receipt jsonb NOT NULL,
          status text NOT NULL CHECK (status IN ('candidate','qualified_primary','qualified_fallback','retired')),
          profile_fingerprint text NOT NULL UNIQUE CHECK (profile_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (profile_key,profile_version)
        );

        CREATE TABLE projection.ntd_memory_versions (
          projection_version_id uuid PRIMARY KEY,
          retrieval_profile_id uuid NOT NULL REFERENCES platform.ntd_retrieval_profiles(retrieval_profile_id) ON DELETE RESTRICT,
          source_snapshot_fingerprint text NOT NULL CHECK (source_snapshot_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          lexical_projection_identity text NOT NULL,
          vector_projection_identity text,
          hierarchy_projection_identity text NOT NULL,
          graph_projection_identity text NOT NULL,
          index_digests jsonb NOT NULL,
          counters jsonb NOT NULL,
          projection_fingerprint text NOT NULL UNIQUE CHECK (projection_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE projection.ntd_hierarchy_edges (
          projection_version_id uuid NOT NULL REFERENCES projection.ntd_memory_versions(projection_version_id) ON DELETE RESTRICT,
          parent_structural_unit_id uuid NOT NULL,
          child_structural_unit_id uuid NOT NULL,
          ordinal integer NOT NULL CHECK (ordinal >= 1),
          depth integer NOT NULL CHECK (depth >= 1),
          path_fingerprint text NOT NULL CHECK (path_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          PRIMARY KEY (projection_version_id,parent_structural_unit_id,child_structural_unit_id)
        );

        CREATE TABLE platform.ntd_graph_nodes (
          graph_node_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          node_kind text NOT NULL CHECK (node_kind IN (
            'source_artifact','source_version','normative_document','normative_edition','section','provision',
            'definition','table','appendix','work_type','construction','material','control_operation',
            'quality_document','executive_document','participant','applicability_predicate','practice_unit','rule'
          )),
          canonical_entity_id uuid NOT NULL,
          label text NOT NULL,
          authority_status text NOT NULL,
          source_locator_ids uuid[] NOT NULL DEFAULT '{}',
          node_fingerprint text NOT NULL UNIQUE CHECK (node_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          supersedes_version bigint,
          PRIMARY KEY (graph_node_id,version),
          FOREIGN KEY (graph_node_id,supersedes_version)
            REFERENCES platform.ntd_graph_nodes(graph_node_id,version) ON DELETE RESTRICT,
          CHECK ((version=1 AND supersedes_version IS NULL) OR (version>1 AND supersedes_version=version-1))
        );

        CREATE TABLE platform.ntd_graph_edge_candidates (
          graph_edge_candidate_id uuid PRIMARY KEY,
          source_graph_node_id uuid NOT NULL,
          target_graph_node_id uuid NOT NULL,
          relation_kind text NOT NULL CHECK (relation_kind IN (
            'contains','references','supersedes','amends','defines','applies_to','requires_control',
            'requires_document','requires_quality_record','regulates_work','regulates_material',
            'aligned_with_practice','conflicts_with','derived_from'
          )),
          derivation_method text NOT NULL CHECK (derivation_method IN ('explicit_structure','exact_reference','deterministic_mapping','model_candidate')),
          source_locator_ids uuid[] NOT NULL CHECK (cardinality(source_locator_ids) > 0),
          status text NOT NULL CHECK (status IN ('candidate','accepted','rejected')),
          candidate_fingerprint text NOT NULL UNIQUE CHECK (candidate_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE platform.ntd_graph_edges (
          graph_edge_id uuid PRIMARY KEY,
          source_graph_node_id uuid NOT NULL,
          target_graph_node_id uuid NOT NULL,
          relation_kind text NOT NULL CHECK (relation_kind IN (
            'contains','references','supersedes','amends','defines','applies_to','requires_control',
            'requires_document','requires_quality_record','regulates_work','regulates_material',
            'aligned_with_practice','conflicts_with','derived_from'
          )),
          authority_method text NOT NULL CHECK (authority_method IN ('explicit_structure','exact_reference','deterministic_mapping','professional_confirmation')),
          source_locator_ids uuid[] NOT NULL CHECK (cardinality(source_locator_ids) > 0),
          edge_fingerprint text NOT NULL UNIQUE CHECK (edge_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE platform.ntd_retrieval_benchmark_receipts (
          benchmark_receipt_id uuid PRIMARY KEY,
          benchmark_profile text NOT NULL CHECK (lower(benchmark_profile) <> 'latest'),
          corpus_fingerprint text NOT NULL CHECK (corpus_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          question_count integer NOT NULL CHECK (question_count >= 100),
          retrieval_profile_fingerprint text NOT NULL CHECK (retrieval_profile_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          metrics jsonb NOT NULL,
          latency jsonb NOT NULL,
          index_sizes jsonb NOT NULL,
          reproducibility jsonb NOT NULL,
          terminal_outcome text NOT NULL CHECK (terminal_outcome IN ('pass','fail','blocked')),
          receipt_fingerprint text NOT NULL UNIQUE CHECK (receipt_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE platform.ntd_memory_build_jobs (
          build_job_id uuid PRIMARY KEY,
          idempotency_key text NOT NULL UNIQUE,
          corpus_object_id uuid REFERENCES platform.ntd_corpus_objects(corpus_object_id) ON DELETE RESTRICT,
          stage text NOT NULL CHECK (stage IN ('binding','inventory','extraction','chunking','embedding','projection','reconciliation')),
          status text NOT NULL CHECK (status IN ('queued','running','succeeded','blocked','retryable_failed','cancelled')),
          attempt integer NOT NULL CHECK (attempt >= 0),
          input_fingerprint text NOT NULL CHECK (input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          terminal_outcome text,
          blocker_code text,
          started_at timestamptz,
          finished_at timestamptz,
          heartbeat_at timestamptz,
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE platform.ntd_memory_build_receipts (
          build_receipt_id uuid PRIMARY KEY,
          profile_version text NOT NULL CHECK (lower(profile_version) <> 'latest'),
          denominator_ntd integer NOT NULL CHECK (denominator_ntd=118),
          deferred_estimate_references integer NOT NULL CHECK (deferred_estimate_references=12),
          counters jsonb NOT NULL,
          source_audit_digest text NOT NULL CHECK (source_audit_digest ~ '^sha256:[a-f0-9]{64}$'),
          embedding_profile_id uuid REFERENCES platform.ntd_embedding_profiles(embedding_profile_id) ON DELETE RESTRICT,
          projection_fingerprint text NOT NULL CHECK (projection_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          build_fingerprint text NOT NULL UNIQUE CHECK (build_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          terminal_outcome text NOT NULL CHECK (terminal_outcome IN ('complete','partial','blocked')),
          recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE application.ntd_memory_readiness_decisions (
          decision_id uuid NOT NULL,
          version bigint NOT NULL CHECK (version >= 1),
          source_commit text NOT NULL CHECK (source_commit ~ '^[a-f0-9]{40}$'),
          status text NOT NULL CHECK (status IN ('not_ready','ready')),
          denominator_ntd integer NOT NULL CHECK (denominator_ntd=118),
          deferred_estimate_references integer NOT NULL CHECK (deferred_estimate_references=12),
          build_receipt_id uuid REFERENCES platform.ntd_memory_build_receipts(build_receipt_id) ON DELETE RESTRICT,
          criteria jsonb NOT NULL,
          blockers jsonb NOT NULL,
          decision_fingerprint text NOT NULL UNIQUE CHECK (decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
          decided_by_identity_id text NOT NULL,
          decided_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (decision_id,version)
        );

        CREATE TRIGGER ntd_corpus_objects_immutable BEFORE UPDATE OR DELETE ON platform.ntd_corpus_objects
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_corpus_pages_immutable BEFORE UPDATE OR DELETE ON platform.ntd_corpus_pages
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_chunks_immutable BEFORE UPDATE OR DELETE ON platform.ntd_chunks
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_structural_units_immutable BEFORE UPDATE OR DELETE ON platform.ntd_structural_units
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_chunk_profiles_immutable BEFORE UPDATE OR DELETE ON platform.ntd_chunk_profiles
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_contextual_chunks_immutable BEFORE UPDATE OR DELETE ON platform.ntd_contextual_chunks
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_embedding_profiles_immutable BEFORE UPDATE OR DELETE ON platform.ntd_embedding_profiles
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_chunk_embeddings_immutable BEFORE UPDATE OR DELETE ON platform.ntd_chunk_embeddings
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_reranker_profiles_immutable BEFORE UPDATE OR DELETE ON platform.ntd_reranker_profiles
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_retrieval_profiles_immutable BEFORE UPDATE OR DELETE ON platform.ntd_retrieval_profiles
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_memory_versions_immutable BEFORE UPDATE OR DELETE ON projection.ntd_memory_versions
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_hierarchy_edges_immutable BEFORE UPDATE OR DELETE ON projection.ntd_hierarchy_edges
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_graph_nodes_immutable BEFORE UPDATE OR DELETE ON platform.ntd_graph_nodes
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_graph_edge_candidates_immutable BEFORE UPDATE OR DELETE ON platform.ntd_graph_edge_candidates
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_graph_edges_immutable BEFORE UPDATE OR DELETE ON platform.ntd_graph_edges
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_retrieval_benchmark_receipts_immutable BEFORE UPDATE OR DELETE ON platform.ntd_retrieval_benchmark_receipts
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_memory_build_receipts_immutable BEFORE UPDATE OR DELETE ON platform.ntd_memory_build_receipts
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();
        CREATE TRIGGER ntd_memory_readiness_decisions_immutable BEFORE UPDATE OR DELETE ON application.ntd_memory_readiness_decisions
          FOR EACH ROW EXECUTE FUNCTION platform.reject_immutable_mutation();

        GRANT SELECT ON platform.ntd_seed_manifests,platform.ntd_corpus_objects,platform.ntd_corpus_pages,platform.ntd_chunks,
          platform.ntd_structural_units,platform.ntd_chunk_profiles,platform.ntd_contextual_chunks,
          platform.ntd_embedding_profiles,platform.ntd_chunk_embeddings,platform.ntd_reranker_profiles,
          platform.ntd_retrieval_profiles,projection.ntd_memory_versions,projection.ntd_hierarchy_edges,
          platform.ntd_graph_nodes,platform.ntd_graph_edge_candidates,platform.ntd_graph_edges,
          platform.ntd_retrieval_benchmark_receipts,platform.ntd_memory_build_receipts,
          application.ntd_memory_readiness_decisions TO asd_app,asd_document_worker;
        GRANT SELECT,INSERT,UPDATE ON platform.ntd_memory_build_jobs TO asd_document_worker;
        GRANT INSERT ON platform.ntd_corpus_objects,platform.ntd_corpus_pages,platform.ntd_chunks,
          platform.ntd_structural_units,platform.ntd_chunk_profiles,platform.ntd_contextual_chunks,
          platform.ntd_embedding_profiles,platform.ntd_chunk_embeddings,platform.ntd_reranker_profiles,
          platform.ntd_retrieval_profiles,projection.ntd_memory_versions,projection.ntd_hierarchy_edges,
          platform.ntd_graph_nodes,platform.ntd_graph_edge_candidates,platform.ntd_graph_edges,
          platform.ntd_retrieval_benchmark_receipts,platform.ntd_memory_build_receipts
          TO asd_document_worker;
        GRANT INSERT ON application.ntd_memory_readiness_decisions TO asd_app;
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("NTD canonical memory downgrade requires a disposable database")
    for table in (
        "application.ntd_memory_readiness_decisions",
        "platform.ntd_memory_build_receipts",
        "platform.ntd_memory_build_jobs",
        "platform.ntd_retrieval_benchmark_receipts",
        "platform.ntd_graph_edges",
        "platform.ntd_graph_edge_candidates",
        "platform.ntd_graph_nodes",
        "projection.ntd_hierarchy_edges",
        "projection.ntd_memory_versions",
        "platform.ntd_retrieval_profiles",
        "platform.ntd_reranker_profiles",
        "platform.ntd_chunk_embeddings",
        "platform.ntd_embedding_profiles",
        "platform.ntd_contextual_chunks",
        "platform.ntd_chunk_profiles",
        "platform.ntd_structural_units",
        "platform.ntd_chunks",
        "platform.ntd_corpus_pages",
        "platform.ntd_corpus_objects",
    ):
        op.execute(f"DROP TABLE {table}")
