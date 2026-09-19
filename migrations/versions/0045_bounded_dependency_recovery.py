"""Bound dependency-terminal recovery and make replay idempotent.

Revision ID: 0045_bounded_dep_recovery
Revises: 0044_dep_recovery_idempotency
"""

from __future__ import annotations

import os

from alembic import op

revision = "0045_bounded_dep_recovery"
down_revision = "0044_dep_recovery_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS durable_jobs_dependency_recovery_pending_idx
          ON workspace.durable_jobs (created_at, job_id)
          WHERE state='reconciliation_required'
            AND typed_failure_code='dependency_terminal_failure';

        CREATE OR REPLACE FUNCTION workspace.recover_dependency_terminal_failures()
        RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        DECLARE
          candidate record;
          derived uuid;
          event_digest text;
          inserted integer;
          recovered integer := 0;
        BEGIN
          FOR candidate IN
            SELECT dependent.organization_id, dependent.workspace_id,
                   dependent.job_id AS blocked_job_id,
                   prerequisite.job_id AS prerequisite_job_id,
                   replacement.job_id AS replacement_job_id,
                   dependent.subject_document_id, dependent.job_kind,
                   dependent.input_manifest, dependent.input_digest,
                   dependent.priority, dependent.max_attempts,
                   dependent.retry_policy_version, dependent.provenance,
                   dependent.correlation_id, dependent.created_by_identity_id
              FROM workspace.durable_jobs dependent
              JOIN workspace.durable_job_dependencies dependency
                ON dependency.organization_id=dependent.organization_id
               AND dependency.workspace_id=dependent.workspace_id
               AND dependency.job_id=dependent.job_id
               AND dependency.dependency_kind='success_required'
              JOIN workspace.durable_jobs prerequisite
                ON prerequisite.organization_id=dependency.organization_id
               AND prerequisite.workspace_id=dependency.workspace_id
               AND prerequisite.job_id=dependency.depends_on_job_id
              CROSS JOIN LATERAL (
                WITH RECURSIVE lineage AS (
                  SELECT prerequisite.job_id, prerequisite.job_kind,
                         prerequisite.subject_document_id, prerequisite.input_digest,
                         0 AS depth
                  UNION ALL
                  SELECT successor.job_id, successor.job_kind,
                         successor.subject_document_id, successor.input_digest,
                         lineage.depth+1
                    FROM workspace.durable_jobs successor
                    JOIN lineage
                      ON successor.organization_id=prerequisite.organization_id
                     AND successor.workspace_id=prerequisite.workspace_id
                     AND successor.causation_id=lineage.job_id
                   WHERE lineage.depth < 32
                     AND successor.job_kind=lineage.job_kind
                     AND successor.input_digest=lineage.input_digest
                     AND successor.subject_document_id IS NOT DISTINCT FROM lineage.subject_document_id
                )
                SELECT succeeding.job_id
                  FROM lineage
                  JOIN workspace.durable_jobs succeeding
                    ON succeeding.organization_id=prerequisite.organization_id
                   AND succeeding.workspace_id=prerequisite.workspace_id
                   AND succeeding.job_id=lineage.job_id
                 WHERE succeeding.state='succeeded'
                   AND succeeding.job_id<>prerequisite.job_id
                 ORDER BY lineage.depth, succeeding.completed_at, succeeding.job_id
                 LIMIT 1
              ) replacement
             WHERE dependent.state='reconciliation_required'
               AND dependent.typed_failure_code='dependency_terminal_failure'
               AND NOT EXISTS (
                 SELECT 1
                   FROM workspace.durable_jobs existing
                  WHERE existing.organization_id=dependent.organization_id
                    AND existing.workspace_id=dependent.workspace_id
                    AND existing.job_kind=dependent.job_kind
                    AND existing.idempotency_key=(
                      'dependency-recovery:' || dependent.job_id::text || ':' || replacement.job_id::text
                    )
               )
             ORDER BY dependent.created_at, dependent.job_id
             LIMIT 16
             FOR UPDATE OF dependent SKIP LOCKED
          LOOP
            derived := gen_random_uuid();
            INSERT INTO workspace.durable_jobs (
              organization_id, workspace_id, job_id, subject_document_id,
              job_kind, input_manifest, input_digest, idempotency_key, state,
              priority, max_attempts, retry_policy_version, provenance,
              correlation_id, causation_id, created_by_identity_id
            ) VALUES (
              candidate.organization_id, candidate.workspace_id, derived,
              candidate.subject_document_id, candidate.job_kind,
              candidate.input_manifest, candidate.input_digest,
              'dependency-recovery:' || candidate.blocked_job_id::text || ':' || candidate.replacement_job_id::text,
              'queued', candidate.priority, candidate.max_attempts,
              candidate.retry_policy_version,
              candidate.provenance || jsonb_build_object(
                'dependency_recovery_of', candidate.blocked_job_id::text,
                'dependency_recovery_prerequisite', candidate.prerequisite_job_id::text,
                'dependency_recovery_replacement', candidate.replacement_job_id::text
              ), candidate.correlation_id, candidate.blocked_job_id,
              candidate.created_by_identity_id
            ) ON CONFLICT (organization_id, workspace_id, job_kind, idempotency_key)
              DO NOTHING;
            GET DIAGNOSTICS inserted = ROW_COUNT;
            IF inserted = 0 THEN
              CONTINUE;
            END IF;
            INSERT INTO workspace.durable_job_dependencies (
              organization_id, workspace_id, job_id, depends_on_job_id, dependency_kind
            )
              SELECT organization_id, workspace_id, derived, depends_on_job_id, dependency_kind
                FROM workspace.durable_job_dependencies
               WHERE organization_id=candidate.organization_id
                 AND workspace_id=candidate.workspace_id
                 AND job_id=candidate.blocked_job_id;
            event_digest := 'sha256:' || encode(public.digest(
              derived::text || '-1-job.queued-dependency_recovery', 'sha256'
            ), 'hex');
            INSERT INTO workspace.job_progress_events (
              organization_id, workspace_id, job_id, event_sequence, event_type,
              progress_current, progress_total, safe_message_code, terminal,
              recorded_at, retention_until, event_digest
            ) VALUES (
              candidate.organization_id, candidate.workspace_id, derived, 1,
              'job.queued', 0, 1, 'dependency_recovery_queued', false,
              clock_timestamp(), clock_timestamp()+interval '24 hours', event_digest
            );
            recovered := recovered+1;
          END LOOP;
          RETURN recovered;
        END $$;
        REVOKE ALL ON FUNCTION workspace.recover_dependency_terminal_failures() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.recover_dependency_terminal_failures()
          TO asd_document_worker;
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Dependency recovery downgrade requires a disposable database")
    op.execute("DROP INDEX workspace.durable_jobs_dependency_recovery_pending_idx")
    # Restore the 0044 wrapper without consuming its preserved v1 implementation.
    # The following 0044 downgrade still needs that function under its v1 name.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION workspace.recover_dependency_terminal_failures()
        RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        DECLARE
          violated_constraint text;
        BEGIN
          RETURN workspace.recover_dependency_terminal_failures_v1();
        EXCEPTION WHEN unique_violation THEN
          GET STACKED DIAGNOSTICS violated_constraint = CONSTRAINT_NAME;
          IF violated_constraint = 'durable_jobs_organization_id_workspace_id_job_kind_idempote_key' THEN
            RETURN 0;
          END IF;
          RAISE;
        END $$;
        """
    )
