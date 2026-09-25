"""Recover dependency-terminal document stages from accepted replacements.

Revision ID: 0042_dependency_recovery
Revises: 0041_engineering_v4_manifest
"""

from __future__ import annotations

import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic import op

revision = "0042_dependency_recovery"
down_revision = "0041_engineering_v4_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION workspace.dependency_success_satisfied(
          p_organization uuid, p_workspace uuid, p_prerequisite uuid
        ) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
          WITH RECURSIVE root AS (
            SELECT job_id,job_kind,subject_document_id,input_digest
              FROM workspace.durable_jobs
             WHERE organization_id=p_organization AND workspace_id=p_workspace
               AND job_id=p_prerequisite
          ), lineage AS (
            SELECT r.job_id,r.job_kind,r.subject_document_id,r.input_digest,0 AS depth
              FROM root r
            UNION ALL
            SELECT successor.job_id,successor.job_kind,successor.subject_document_id,
                   successor.input_digest,lineage.depth+1
              FROM workspace.durable_jobs successor
              JOIN lineage ON successor.organization_id=p_organization
                           AND successor.workspace_id=p_workspace
                           AND successor.causation_id=lineage.job_id
             WHERE lineage.depth < 32
               AND successor.job_kind=lineage.job_kind
               AND successor.input_digest=lineage.input_digest
               AND successor.subject_document_id IS NOT DISTINCT FROM lineage.subject_document_id
          )
          SELECT EXISTS (
            SELECT 1 FROM lineage
            JOIN workspace.durable_jobs candidate
              ON candidate.organization_id=p_organization AND candidate.workspace_id=p_workspace
             AND candidate.job_id=lineage.job_id
             AND candidate.state='succeeded'
          )
        $$;
        REVOKE ALL ON FUNCTION workspace.dependency_success_satisfied(uuid,uuid,uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.dependency_success_satisfied(uuid,uuid,uuid)
          TO asd_document_worker;

        CREATE FUNCTION workspace.recover_dependency_terminal_failures()
        RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        DECLARE
          candidate record;
          derived uuid;
          event_digest text;
          recovered integer := 0;
        BEGIN
          FOR candidate IN
            SELECT dependent.organization_id,dependent.workspace_id,dependent.job_id AS blocked_job_id,
                   prerequisite.job_id AS prerequisite_job_id,
                   replacement.job_id AS replacement_job_id,
                   dependent.subject_document_id,dependent.job_kind,dependent.input_manifest,
                   dependent.input_digest,dependent.priority,dependent.max_attempts,
                   dependent.retry_policy_version,dependent.provenance,dependent.correlation_id,
                   dependent.created_by_identity_id
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
                  SELECT prerequisite.job_id,prerequisite.job_kind,prerequisite.subject_document_id,
                         prerequisite.input_digest,0 AS depth
                  UNION ALL
                  SELECT successor.job_id,successor.job_kind,successor.subject_document_id,
                         successor.input_digest,lineage.depth+1
                    FROM workspace.durable_jobs successor
                    JOIN lineage ON successor.organization_id=prerequisite.organization_id
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
                 ORDER BY lineage.depth,succeeding.completed_at,succeeding.job_id
                 LIMIT 1
              ) replacement
             WHERE dependent.state='reconciliation_required'
               AND dependent.typed_failure_code='dependency_terminal_failure'
               AND NOT EXISTS (
                 SELECT 1 FROM workspace.durable_jobs prior_recovery
                  WHERE prior_recovery.organization_id=dependent.organization_id
                    AND prior_recovery.workspace_id=dependent.workspace_id
                    AND prior_recovery.causation_id=dependent.job_id
                    AND prior_recovery.provenance->>'dependency_recovery_prerequisite'
                        = prerequisite.job_id::text
                    AND prior_recovery.provenance->>'dependency_recovery_replacement'
                        = replacement.job_id::text
               )
             FOR UPDATE OF dependent SKIP LOCKED
          LOOP
            derived := gen_random_uuid();
            INSERT INTO workspace.durable_jobs (
              organization_id,workspace_id,job_id,subject_document_id,job_kind,input_manifest,input_digest,
              idempotency_key,state,priority,max_attempts,retry_policy_version,provenance,
              correlation_id,causation_id,created_by_identity_id
            ) VALUES (
              candidate.organization_id,candidate.workspace_id,derived,candidate.subject_document_id,
              candidate.job_kind,candidate.input_manifest,candidate.input_digest,
              'dependency-recovery:' || candidate.blocked_job_id::text || ':' || candidate.replacement_job_id::text,
              'queued',candidate.priority,candidate.max_attempts,candidate.retry_policy_version,
              candidate.provenance || jsonb_build_object(
                'dependency_recovery_of',candidate.blocked_job_id::text,
                'dependency_recovery_prerequisite',candidate.prerequisite_job_id::text,
                'dependency_recovery_replacement',candidate.replacement_job_id::text
              ), candidate.correlation_id,candidate.blocked_job_id,candidate.created_by_identity_id
            );
            INSERT INTO workspace.durable_job_dependencies (
              organization_id,workspace_id,job_id,depends_on_job_id,dependency_kind
            )
              SELECT organization_id,workspace_id,derived,depends_on_job_id,dependency_kind
                FROM workspace.durable_job_dependencies
               WHERE organization_id=candidate.organization_id AND workspace_id=candidate.workspace_id
                 AND job_id=candidate.blocked_job_id;
            event_digest := 'sha256:' || encode(public.digest(
              derived::text || '-1-job.queued-dependency_recovery','sha256'),'hex');
            INSERT INTO workspace.job_progress_events (
              organization_id,workspace_id,job_id,event_sequence,event_type,progress_current,
              progress_total,safe_message_code,terminal,recorded_at,retention_until,event_digest
            ) VALUES (
              candidate.organization_id,candidate.workspace_id,derived,1,'job.queued',0,1,
              'dependency_recovery_queued',false,clock_timestamp(),
              clock_timestamp()+interval '24 hours',event_digest
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
    _replace_claim_function()


def _replace_claim_function() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION workspace.claim_next_durable_job(p_worker_identity text, p_lease_seconds integer)
        RETURNS TABLE (
          organization_id uuid, workspace_id uuid, job_id uuid, job_kind text,
          input_manifest jsonb, input_digest text, attempt_number integer,
          lease_generation bigint, cancellation_state text
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, workspace
        AS $$
        DECLARE
          claimed workspace.durable_jobs%ROWTYPE;
          next_generation bigint;
          next_attempt integer;
          next_sequence bigint;
          lease_uuid uuid;
          now_at timestamptz := clock_timestamp();
          lease_until timestamptz;
          lease_fingerprint text;
          event_fingerprint text;
        BEGIN
          IF p_worker_identity IS NULL OR length(p_worker_identity) < 3 OR p_lease_seconds < 5 OR p_lease_seconds > 3600 THEN
            RAISE EXCEPTION 'invalid durable job lease request' USING ERRCODE='22023';
          END IF;
          UPDATE workspace.durable_jobs j
             SET state='queued', lease_owner=NULL, lease_expires_at=NULL,
                 typed_failure_code='stale_lease_recovered'
           WHERE j.state IN ('leased','running')
             AND j.lease_expires_at < now_at
             AND j.attempt_count < j.max_attempts
             AND j.cancellation_state='none';
          SELECT j.* INTO claimed
            FROM workspace.durable_jobs j
           WHERE j.state='queued' AND j.eligible_at <= now_at
             AND j.cancellation_state='none'
             AND j.attempt_count < j.max_attempts
             AND NOT EXISTS (
               SELECT 1 FROM workspace.durable_job_dependencies d
               JOIN workspace.durable_jobs prerequisite
                 ON prerequisite.organization_id=d.organization_id
                AND prerequisite.workspace_id=d.workspace_id
                AND prerequisite.job_id=d.depends_on_job_id
               WHERE d.organization_id=j.organization_id AND d.workspace_id=j.workspace_id
                 AND d.job_id=j.job_id
                 AND ((d.dependency_kind='success_required' AND NOT workspace.dependency_success_satisfied(
                    j.organization_id,j.workspace_id,d.depends_on_job_id))
                   OR (d.dependency_kind='terminal_required' AND prerequisite.state NOT IN ('succeeded','failed','cancelled','reconciliation_required')))
             )
           ORDER BY j.priority DESC, j.created_at, j.job_id
           FOR UPDATE OF j SKIP LOCKED LIMIT 1;
          IF NOT FOUND THEN RETURN; END IF;
          next_generation := claimed.lease_generation + 1;
          next_attempt := claimed.attempt_count + 1;
          next_sequence := COALESCE((SELECT max(e.event_sequence)+1 FROM workspace.job_progress_events e
            WHERE e.organization_id=claimed.organization_id AND e.workspace_id=claimed.workspace_id AND e.job_id=claimed.job_id),1);
          lease_uuid := gen_random_uuid();
          lease_until := now_at + make_interval(secs => p_lease_seconds);
          lease_fingerprint := 'sha256:' || encode(public.digest(
            claimed.job_id::text || '-' || next_generation::text || '-' || p_worker_identity || '-' || now_at::text,'sha256'),'hex');
          event_fingerprint := 'sha256:' || encode(public.digest(
            claimed.job_id::text || '-' || next_sequence::text || '-job.leased-' || next_generation::text,'sha256'),'hex');
          UPDATE workspace.durable_jobs j SET state='leased',attempt_count=next_attempt,lease_owner=p_worker_identity,
            lease_generation=next_generation,lease_expires_at=lease_until,heartbeat_at=now_at,
            started_at=COALESCE(j.started_at,now_at)
          WHERE j.organization_id=claimed.organization_id AND j.workspace_id=claimed.workspace_id AND j.job_id=claimed.job_id;
          INSERT INTO workspace.durable_job_attempts VALUES (
            claimed.organization_id,claimed.workspace_id,claimed.job_id,next_attempt,gen_random_uuid(),
            p_worker_identity,next_generation,'spine-worker-v0.1',claimed.input_digest,now_at);
          INSERT INTO workspace.job_leases VALUES (
            claimed.organization_id,claimed.workspace_id,claimed.job_id,next_generation,lease_uuid,
            p_worker_identity,now_at,lease_until,lease_fingerprint);
          INSERT INTO workspace.job_progress_events (
            organization_id,workspace_id,job_id,event_sequence,event_type,progress_current,progress_total,
            safe_message_code,terminal,recorded_at,retention_until,event_digest
          ) VALUES (
            claimed.organization_id,claimed.workspace_id,claimed.job_id,next_sequence,'job.leased',NULL,NULL,
            'job.leased',false,now_at,now_at+interval '24 hours',event_fingerprint);
          RETURN QUERY SELECT claimed.organization_id,claimed.workspace_id,claimed.job_id,claimed.job_kind,
            claimed.input_manifest,claimed.input_digest,next_attempt,next_generation,claimed.cancellation_state;
        END $$;
        REVOKE ALL ON FUNCTION workspace.claim_next_durable_job(text,integer) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION workspace.claim_next_durable_job(text,integer) TO asd_document_worker;
        """
    )


def downgrade() -> None:
    if os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Dependency recovery downgrade requires a disposable database")
    op.execute("DROP FUNCTION workspace.recover_dependency_terminal_failures()")
    op.execute("DROP FUNCTION workspace.dependency_success_satisfied(uuid,uuid,uuid)")
    op.execute("DROP FUNCTION workspace.claim_next_durable_job(text,integer)")
    op.execute("DROP FUNCTION workspace.reconcile_unclaimable_durable_jobs()")
    specification = spec_from_file_location(
        "asd_kontur_migration_0018",
        Path(__file__).with_name("0018_product_application_spine.py"),
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("product_spine_claim_function_source_unavailable")
    migration = module_from_spec(specification)
    specification.loader.exec_module(migration)
    migration._create_worker_claim_function()
