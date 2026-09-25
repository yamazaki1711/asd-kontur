"""Claim incremental materializations before further semantic inference.

Revision ID: 0048_incremental_reconciliation_claim_priority
Revises: 0047_profile_scoped_engineering_candidates

An incremental project-understanding reconciliation is a short database-only
materialization causally tied to an already accepted semantic source.  It must
not wait behind unrelated Qwen jobs merely because an earlier deployment
persisted it at priority 165.  The claim policy recognizes the explicit
incremental manifest marker, retaining durable-job lineage and all ordinary
priority ordering for other work.
"""

from __future__ import annotations

import os

from alembic import op

revision = "0048_incremental_reconciliation_claim_priority"
down_revision = "0047_profile_scoped_engineering_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
           ORDER BY CASE WHEN j.job_kind='PROJECT_UNDERSTANDING_RECONCILIATION'
                              AND j.input_manifest ? 'incremental_source_job_id' THEN 1 ELSE 0 END DESC,
                    j.priority DESC, j.created_at, j.job_id
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
        raise RuntimeError("Claim-priority downgrade requires a disposable database")
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    specification = spec_from_file_location(
        "asd_kontur_migration_0042",
        Path(__file__).with_name("0042_dependency_replacement_recovery.py"),
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("claim-function source unavailable")
    migration = module_from_spec(specification)
    specification.loader.exec_module(migration)
    migration._replace_claim_function()
