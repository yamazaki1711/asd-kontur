# Support incoming-inspection slice — 2026-10-07

## User result

Support now has an eight-check incoming-inspection preflight for an identified
material batch. A user can record documentary checks, physical observations,
and the incoming-control log status, then reopen the recorded result and its
specific corrective actions. A failed check calls for batch isolation; an
incomplete check calls for evidence or an actual inspection.

This record **does not admit a material batch for use**. Every outcome carries
`hold_for_use=true`; even a complete checklist only becomes ready for review by
an authorised responsible person. Physical observations are user-entered, not
inferred from uploaded paperwork or asserted by Qwen.

## Boundary and implementation

- Exact check set: passports/certificates, specification conformity, marking,
  visual condition, shelf life, delivery quantity, storage and incoming log.
- Workspace-scoped append-only storage, RLS, owner-authorised read/write,
  idempotency key and fenced-workspace insertion guard.
- The workspace destruction registry includes the new table, so these
  project-specific records are in the deletion scope.
- API and Support UI expose submission and history. The UI does not display
  this preflight as an approved material admission.

## Qualification and release limit

Four deterministic unit tests pass, frontend typechecking/build pass, and the
OpenAPI contract has been regenerated. The isolated PostgreSQL integration
test exists but has not run because `ASD_TEST_DATABASE_URL` is not configured
in this session. Migration 0135 has **not** been applied to the owner database;
the deployed release remains the prior version. Before deployment, run the
isolated migration/integration test, then perform the required backup/restore
upgrade verification and a controlled application acceptance.

This is one Support result, not Support-mode readiness. It does not yet bind
the preflight to a material-admission decision, field evidence, work-package
blocking, laboratory records or KS/payment outputs. Tender, Audit and
Restoration readiness are unchanged. `ProductReady=false`.
