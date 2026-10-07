# Audit ID-document interpretation, slice 01

Date: 2026-10-08. This is an implementation checkpoint, not Audit acceptance.

## User task and boundary

When a user uploads actual as-built documentation, the application should
identify the likely document form and the work named in it without treating
mere file presence as proof of inspection, signature, completion or compliance.
The current owner workspace has no `field_document` sources, so this slice must
not schedule new inference against its 21 project/design sources.

## Implemented

- The supervised orchestrator derives one idempotent job from each active,
  admitted field-document version after aggregation and native/OCR layout are
  available. It does not enqueue duplicates on later sweeps.
- The existing single-model worker sends bounded source-locator fragments to
  local Qwen. It validates exact quotes and source identity, allows explicit
  `unknown`, and performs one bounded format/evidence repair.
- The immutable stage receipt stores the result as a workspace-scoped Qwen
  candidate. A worker crash after receipt persistence reuses that receipt.
- The Audit inventory can display the candidate document kind and work scope
  with exact locator links and a clear warning that substantive Audit checks
  have not been performed.
- Migration 0142 adds the job kind to the durable-job constraint and model-slot
  fairness function. It does not alter platform NTD or project facts.

## Verification and release boundary

Seven source-boundary unit cases pass. The application-spine and
document-understanding unit selection passes 235/235; Ruff, mypy, frontend
lint/typecheck, frontend unit tests and build pass. Public DB read-only
inspection confirmed migration head 0141 and both expected fairness-function
source patterns. Migration 0142 upgraded, downgraded and re-upgraded on a
separate disposable database using a dedicated non-production role. The
broader integration suite could not migrate its newly created databases under
that restricted role because `CREATE EXTENSION vector` requires superuser
privileges. The exact disposable database and role were removed afterward;
other historical test databases were left untouched. Browser control was
unavailable in this session.

The public database was backed up to a private custom-format dump before
migration (SHA-256 `3bc9e04fc31bf649780c232c340aa69fc06799ccdffd5cd2251764f14fb55e10`).
The dump restored into a separate database with 44 workspace rows and 7,097
durable-job rows; migration 0142 upgraded, downgraded and re-upgraded there.
The restored NTD chunk fingerprint exactly matched the public pre-migration
fingerprint (`f85797e67e4beeeab1052a462ba29445`). After controlled public
migration, that fingerprint and the platform NTD counters remained unchanged.
The temporary restored database was removed; the backup was retained for
rollback. API, worker, assistant worker and orchestrator were cut over to
source SHA `1201cff1118356911b9765f5058da63347d1d71f`, migration 0142;
Qwen and NTD services were not restarted. API readiness and frontend returned
HTTP 200. The owner workspace has zero ID-document interpretation jobs because
it has zero `field_document` sources. Live Audit semantic acceptance is therefore
still unverified, and this is not Audit mode acceptance.

One bounded synthetic, non-workspace Qwen qualification was run against the
persistently loaded local `/generate` service. It returned
`concealed_work_act` and the cited cable-installation work scope in 12.1 seconds
with candidate authority; it did not claim that the unsigned example was valid.
This verifies the model task contract on one changed construction example, not
autonomous job scheduling or independent document-audit acceptance.

## Still required for Audit

The candidate must be linked to the applicable work/documentation matrix and
independently checked for identity, revisions, signatures, dates, material and
test evidence, cross-document consistency and applicable requirements. Only
then may the system publish an Audit finding or completion outcome. Support,
Restoration, drawings, field/offline and full lifecycle/scale acceptance remain
open. `ProductReady=false`.
