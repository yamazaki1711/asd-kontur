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
source patterns. No public migration, release cutover or live Audit acceptance
has occurred in this checkpoint because a dedicated disposable PostgreSQL test
target was not configured. Browser control was unavailable in this session.

## Still required for Audit

The candidate must be linked to the applicable work/documentation matrix and
independently checked for identity, revisions, signatures, dates, material and
test evidence, cross-document consistency and applicable requirements. Only
then may the system publish an Audit finding or completion outcome. Support,
Restoration, drawings, field/offline and full lifecycle/scale acceptance remain
open. `ProductReady=false`.
