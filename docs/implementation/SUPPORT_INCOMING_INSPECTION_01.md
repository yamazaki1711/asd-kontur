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

## Editable inspection register follow-up

The owner-scoped Support API now exports a complete CSV register of all saved
preflights, with one row per required check, original basis, outcome, and an
explicit statement that the material has **not** been admitted for use. The
Support screen offers the export directly. User-entered cells are neutralised
against spreadsheet formula execution. This is an editable working register,
not a signed incoming-control journal or an admission decision. The isolated
database/API qualification covers all rows rather than only the latest 100,
cross-workspace denial, and the hold-for-use marking. Linking preflights to
confirmed batches, professional grants, work applications and actual field
evidence remains the next authority-boundary dependency.

The register follow-up was released as exact source SHA
`141196cb2ed219d5747cd2653940e7af6392edce`, using the private
four-role plist staging tool and the existing migration 0135. The staged
OpenAPI file and the served API were structurally equal (87 routes), and the
new register route returned 401 without authentication. All four application
launchd roles were healthy after cutover; API readiness, one active workspace,
21 source versions, and the existing Qwen/NTD PIDs were preserved. The public
workspace currently has no incoming-inspection preflights, so live export of
owner-entered inspection data was not exercised. Authenticated browser
acceptance remains unavailable because no in-app browser is attached.
The broader isolated Python unit/integration gate for this source checkpoint
finished with 1,544 passed and two skipped in 127.88 seconds; frontend
typecheck and production build also passed. This qualification is not a
four-mode product-readiness result.

## Actionable register wording follow-up

The editable incoming-inspection CSV previously exported internal English
state/kind codes and omitted the corrective action even though the Support UI
showed actions. The generic renderer now uses Russian professional labels,
includes the action for each failed or incomplete check, and rejects unknown
or duplicated checklist identities instead of publishing a corrupted register.
Every row still explicitly states that the batch is not admitted for use. Eight
focused unit tests and both isolated PostgreSQL integration tests passed.
This is a usable register correction, not a material-admission decision: the
current real workspace has no registered material batches or active
professional grants, and the application does not infer either from a
preflight. ProductReady remains false.

The corrected renderer was deployed as exact application SHA
`d382c627437f9f872d7b8e6358c21dbc123877c9` on unchanged migration
`0135_support_incoming_inspection_preflights`. The staged archive passed 10/10
focused unit and isolated PostgreSQL/API tests, frontend typecheck/build and
4/4 private launchd preflight. All four supervised application roles restarted
from that pinned release; a one-second drain between bootout and bootstrap
avoided the immediate launchd I/O race seen in the previous cutover. API
readiness and frontend HTTP 200 passed. The public workspace retained 21
source versions and 274 contract-analysis results with no active durable job;
Qwen and NTD-worker PIDs were unchanged. The current real workspace has no
saved incoming-inspection preflight, so an authenticated owner download of a
real inspection register remains unverified. No material was admitted by this
release.

## Material-admission evaluator boundary (source checkpoint)

The previously unused deterministic admission evaluator could return
`admitted` from the mere presence of an incoming-control UUID, even if the
linked preflight was incomplete or nonconforming, and did not check that its
professional authority had the material-admission capability. The typed input
now requires the incoming-control outcome. An incomplete result blocks,
nonconformity quarantines, non-positive/non-finite delivered quantity blocks,
and a grant for another capability fails closed. This does **not** create an
admission command or a confirmed batch: persistence must still resolve an
actual batch/work/evidence/preflight/grant in one workspace before it may call
the evaluator. No public material-admission result is claimed from this source
checkpoint.

## Batch-bound material-admission command (2026-10-07 source qualification)

The next Support increment adds a human-authorised admission decision without
turning the eight-check preflight into an automatic approval. New preflights
can be bound to an exact canonical material-batch identity/version; legacy
unbound preflights remain readable and exportable but cannot authorize
admission. The command resolves the exact current batch and work versions,
latest bound preflight, verified source links for certificate, passport and
delivery quantity, an active `support.material.admit` grant for the signed-in
person, delivery origin/quantity and the person's decision basis. It appends a
workspace-scoped decision through the fenced Support writer with an
idempotency key. The UI displays available prerequisites, precise missing
inputs, source locators and decision history. A failed incoming check
quarantines the batch; an incomplete check cannot produce `admitted`.

Migration 0136 is additive. It adds explicit preflight-to-batch identity and
the factual basis columns to the existing decision table, owner-scoped read
policy, and only the read grants needed by the application and Support writer.
It does not mutate global NTD or create source documents, material batches,
professional grants or work instances. On the disposable PostgreSQL cluster,
0135 → 0136 → 0135 → 0136 passed; the bound decision, unbound refusal,
idempotent replay/conflict, later failing inspection, cross-workspace denial,
authenticated API reload and lifecycle freeze passed in focused integration.
The Support UI passed frontend typecheck, lint and production build. These are
source/isolated-environment qualifications, not public deployment or a
professional field admission.

The current owner workspace has no registered material batch or active
`support.material.admit` grant. Therefore the successful real-workspace path
is not yet available there; the application must show those missing
prerequisites rather than manufacture them. The decision is not yet connected
to the effective work-readiness, material-balance or KS/payment chain. Support
mode and ProductReady remain unaccepted.

The controlled public cutover uses exact application SHA
`27106bae395661fbf61816c19fc83f20ba4d7ef8` and migration
`0136_support_material_admission_basis`. A custom-format pre-migration backup
is retained privately at
`~/.asd-kontur/public-demo/backups/0136-material-admission.b8hjkO/pre-migration.dump`
with SHA-256
`dee76335654935f6421e70e564a15b4af1f38845bf7c43e1c7ebf3b26f1d80bb`.
It restored into a separate disposable database; upgrade, downgrade and
re-upgrade passed, and that restored copy was removed after verification.
The four application launchd roles were cut over from private staged plists;
the prior plists are backed up under
`~/.asd-kontur/public-demo/launchd-backups/20261007-pre-27106ba-material-admission/`.
API readiness reports migration 0136, all four loaded release pins match the
SHA, the served OpenAPI equals the built artifact, and the frontend returns
HTTP 200. The admission context route returns HTTP 401 without a session.
The owner workspace retained 21 source versions, zero preflights and zero
admissions; no admission result was manufactured. Qwen and NTD worker PIDs
were unchanged. Before and after the cutover, the normalized full platform
data fingerprint was exactly
`ff6e99703e35fa28887ed16571aa62f552649ccd8027b60305691155f863e3da`;
NTD documents/editions/semantics were 15/15/1,669 and inspected
embedding/graph/search rows remained 0/0/0. This proves preservation for the
specified cutover, not an operational Support-mode completion or an
authenticated owner-browser acceptance.

## Work-material requirement guard (follow-up)

The first admission command confirmed the batch and work independently, but a
human-selected applicability checkbox could still pair a batch with a work
that had no current requirement for its material class. The follow-up queries
the latest exact work-material requirement version and permits a decision only
when the material class/version is applicable to that work and its requirement
state is current. The Support UI lists only eligible works for the selected
batch and explains when no work has such a requirement. A superseded
requirement blocks a new decision even if an older admission exists. This is
a general material-to-work scope guard, not an inferred approval of a
material substitution or an additional-work change.

This follow-up is deployed as exact application SHA
`8e3cf85fc5b9d8d2f8e7634885af017c17bb9491` on unchanged migration
`0136_support_material_admission_basis`. The exact release passed the
isolated material-admission integration test, frontend typecheck/build and
4/4 private launchd preflight. All four application roles run the new SHA;
API readiness and the served OpenAPI digest
`3c2fe23cf36e3474dc7897fc16d9088dd90e6365f901d613656914f8bfdc8af3`
match. Qwen and NTD PIDs stayed unchanged. The public workspace still has
21 source versions and no preflights or admissions. The full platform-data
fingerprint remains
`ff6e99703e35fa28887ed16571aa62f552649ccd8027b60305691155f863e3da`.
The prior four plists are retained privately in
`~/.asd-kontur/public-demo/launchd-backups/20261007-pre-8e3cf85-material-scope/`.
No owner-specific material outcome or authenticated owner-screen acceptance
is claimed. `ProductReady=false`.
