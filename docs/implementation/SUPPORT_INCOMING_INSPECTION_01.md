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

## Qualification and release

Four deterministic unit tests and two isolated PostgreSQL integration tests
pass; frontend typechecking/build pass, and the OpenAPI contract has been
regenerated. The integration tests used a verified disposable PostgreSQL 17
cluster under `/tmp`, not the owner database. They covered migration 0135,
workspace isolation, immutable writes, owner-scoped replay/conflict, the
authenticated submit/list API, and late-write rejection during lifecycle
freezing. The broader isolated Python suite passed 1,540 tests, with two skips.
The in-app Browser reported zero available browser instances, so authenticated
owner-screen acceptance could not be performed; it is not inferred from
TestClient or frontend build results.

Release `491add15a29306683cef0db10c6fc19a4ba3a14e` was staged from its
exact Git archive with offline locked Python dependencies and an offline
frontend build. Before the public migration, a custom-format backup of
`asd_kontur_public_demo` was written under
`~/.asd-kontur/public-demo/backups/0135-preflight.viBsID/` with SHA-256
`0b7f88010ad0bdbba995a8938b9c76d1f14cf18900aa41347ac0a18b9046e2f4`.
That backup restored separately to `asd_restore_0135_20261007`; upgrade,
downgrade and re-upgrade of 0135 all passed there. No existing production row
was deleted for this migration. Public migration 0135 was then applied.

All four application launchd roles were rolled to the pinned release after a
4/4 staged-plist preflight. API readiness returned migration 0135; the served
OpenAPI SHA-256 matched the staged digest
`3f24870efdfb165b20c854a581671df1fbbb6906cc997616f7e99c4a5f09489c`.
The two new routes returned 401 without authentication. The owner database
still had one active workspace, 21 source versions and 274 contract-analysis
results, matching the restored pre-migration copy. The new preflight table was
empty. Qwen PID 9105 and NTD-worker PID 1356 were not restarted. Selected
canonical NTD, graph/search, normative and practice row counts, and the NTD
publication fingerprint, were identical before and after migration.

During staging, a `plutil` conversion unexpectedly rewrote the on-disk API
plist. It was restored immediately from the exact previous-release staged
copy and verified by `plutil -lint`, the old SHA pin and API readiness before
cutover. Separately, staging-plist array replacement inserted an extra
argument; the 4/4 topology preflight caught it before cutover, and the staged
argument array was corrected. No live service was restarted until the staged
plists passed. These tool-behaviour hazards must be accounted for in future
release automation.

Source-only follow-up `tools/stage_launchd_release.py` replaces that fragile
manual plist-editing step. It validates all four source argument arrays,
creates a new private staging directory, writes complete replacement arrays
and release pins with `plistlib`, retains existing secret values without
printing them, and runs the four-role topology check. Two synthetic tests
verify unchanged source plists, private permissions, no duplicated executable
argument, rejection of an existing output directory and fail-closed malformed
input. This tool is not part of the already deployed `491add1` release and
does not itself migrate or restart any service.

This is one Support result, not Support-mode readiness. It does not yet bind
the preflight to a material-admission decision, field evidence, work-package
blocking, laboratory records or KS/payment outputs. Tender, Audit and
Restoration readiness are unchanged. `ProductReady=false`.
