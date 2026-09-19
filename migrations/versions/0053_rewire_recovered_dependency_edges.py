"""Rewire accepted prerequisite edges in recovered durable jobs.

Revision ID: 0053_rewire_recovery_edges
Revises: 0052_dependency_success_lookup
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import cast

from alembic import op

revision = "0053_rewire_recovery_edges"
down_revision = "0052_dependency_success_lookup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
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
            WITH RECURSIVE successful_lineage AS MATERIALIZED (
              SELECT successor.organization_id, successor.workspace_id,
                     successor.job_id AS replacement_job_id,
                     successor.causation_id AS predecessor_job_id,
                     successor.job_kind, successor.subject_document_id,
                     successor.input_digest, successor.completed_at, 1 AS depth
                FROM workspace.durable_jobs successor
               WHERE successor.state='succeeded'
              UNION ALL
              SELECT lineage.organization_id, lineage.workspace_id,
                     lineage.replacement_job_id, predecessor.causation_id,
                     lineage.job_kind, lineage.subject_document_id,
                     lineage.input_digest, lineage.completed_at, lineage.depth+1
                FROM successful_lineage lineage
                JOIN workspace.durable_jobs predecessor
                  ON predecessor.organization_id=lineage.organization_id
                 AND predecessor.workspace_id=lineage.workspace_id
                 AND predecessor.job_id=lineage.predecessor_job_id
                 AND predecessor.job_kind=lineage.job_kind
                 AND predecessor.input_digest=lineage.input_digest
                 AND predecessor.subject_document_id IS NOT DISTINCT FROM lineage.subject_document_id
               WHERE lineage.depth < 32
            ), replacement AS MATERIALIZED (
              SELECT DISTINCT ON (organization_id,workspace_id,predecessor_job_id)
                     organization_id,workspace_id,predecessor_job_id,replacement_job_id
                FROM successful_lineage
               ORDER BY organization_id,workspace_id,predecessor_job_id,
                        depth,completed_at,replacement_job_id
            )
            SELECT dependent.organization_id,dependent.workspace_id,
                   dependent.job_id AS blocked_job_id,
                   prerequisite.job_id AS prerequisite_job_id,
                   replacement.replacement_job_id,
                   dependent.subject_document_id,dependent.job_kind,
                   dependent.input_manifest,dependent.input_digest,
                   dependent.priority,dependent.max_attempts,
                   dependent.retry_policy_version,dependent.provenance,
                   dependent.correlation_id,dependent.created_by_identity_id
              FROM replacement
              JOIN workspace.durable_jobs prerequisite
                ON prerequisite.organization_id=replacement.organization_id
               AND prerequisite.workspace_id=replacement.workspace_id
               AND prerequisite.job_id=replacement.predecessor_job_id
              JOIN workspace.durable_job_dependencies dependency
                ON dependency.organization_id=prerequisite.organization_id
               AND dependency.workspace_id=prerequisite.workspace_id
               AND dependency.depends_on_job_id=prerequisite.job_id
               AND dependency.dependency_kind='success_required'
              JOIN workspace.durable_jobs dependent
                ON dependent.organization_id=dependency.organization_id
               AND dependent.workspace_id=dependency.workspace_id
               AND dependent.job_id=dependency.job_id
             WHERE dependent.state='reconciliation_required'
               AND dependent.typed_failure_code='dependency_terminal_failure'
               AND NOT EXISTS (
                 SELECT 1 FROM workspace.durable_jobs existing
                  WHERE existing.organization_id=dependent.organization_id
                    AND existing.workspace_id=dependent.workspace_id
                    AND existing.job_kind=dependent.job_kind
                    AND (
                      existing.idempotency_key=(
                        'dependency-recovery-v2:' || dependent.job_id::text || ':' || replacement.replacement_job_id::text
                      ) OR (
                        existing.idempotency_key=(
                          'dependency-recovery:' || dependent.job_id::text || ':' || replacement.replacement_job_id::text
                        ) AND existing.state IN ('queued','leased','running','succeeded')
                      )
                    )
               )
             ORDER BY dependent.created_at,dependent.job_id
             LIMIT 16
             FOR UPDATE OF dependent SKIP LOCKED
          LOOP
            derived := gen_random_uuid();
            INSERT INTO workspace.durable_jobs (
              organization_id,workspace_id,job_id,subject_document_id,
              job_kind,input_manifest,input_digest,idempotency_key,state,
              priority,max_attempts,retry_policy_version,provenance,
              correlation_id,causation_id,created_by_identity_id
            ) VALUES (
              candidate.organization_id,candidate.workspace_id,derived,
              candidate.subject_document_id,candidate.job_kind,
              candidate.input_manifest,candidate.input_digest,
              'dependency-recovery-v2:' || candidate.blocked_job_id::text || ':' || candidate.replacement_job_id::text,
              'queued',candidate.priority,candidate.max_attempts,
              candidate.retry_policy_version,
              candidate.provenance || jsonb_build_object(
                'dependency_recovery_protocol','successor_v2',
                'dependency_recovery_of',candidate.blocked_job_id::text,
                'dependency_recovery_prerequisite',candidate.prerequisite_job_id::text,
                'dependency_recovery_replacement',candidate.replacement_job_id::text
              ),candidate.correlation_id,candidate.blocked_job_id,
              candidate.created_by_identity_id
            ) ON CONFLICT (organization_id,workspace_id,job_kind,idempotency_key)
              DO NOTHING;
            GET DIAGNOSTICS inserted = ROW_COUNT;
            IF inserted=0 THEN CONTINUE; END IF;
            INSERT INTO workspace.durable_job_dependencies (
              organization_id,workspace_id,job_id,depends_on_job_id,dependency_kind
            )
              SELECT organization_id,workspace_id,derived,
                     CASE
                       WHEN depends_on_job_id=candidate.prerequisite_job_id
                        AND dependency_kind='success_required'
                       THEN candidate.replacement_job_id
                       ELSE depends_on_job_id
                     END,
                     dependency_kind
                FROM workspace.durable_job_dependencies
               WHERE organization_id=candidate.organization_id
                 AND workspace_id=candidate.workspace_id
                 AND job_id=candidate.blocked_job_id;
            event_digest := 'sha256:' || encode(public.digest(
              derived::text || '-1-job.queued-dependency_recovery','sha256'
            ),'hex');
            INSERT INTO workspace.job_progress_events (
              organization_id,workspace_id,job_id,event_sequence,event_type,
              progress_current,progress_total,safe_message_code,terminal,
              recorded_at,retention_until,event_digest
            ) VALUES (
              candidate.organization_id,candidate.workspace_id,derived,1,
              'job.queued',0,1,'dependency_recovery_queued',false,
              clock_timestamp(),clock_timestamp()+interval '24 hours',event_digest
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
    source = Path(__file__).with_name("0051_successor_driven_dependency_recovery.py")
    namespace: dict[str, object] = {}
    exec(source.read_text(), namespace)
    cast(Callable[[], None], namespace["upgrade"])()
