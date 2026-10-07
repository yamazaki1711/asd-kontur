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

Follow-up source checkpoint: the Support screen now also lists current
applicable material requirements by work, with the project quantity where
stated and the latest visible admission decisions for matching batches. It
states explicitly that admission does not prove actual application or
quantity sufficiency; truncated histories cannot be presented as an absence
of decisions. This is a professional requirement-to-decision view, not a
work-readiness or KS/payment approval. Isolated PostgreSQL/API checks and
frontend typecheck/lint pass. This follow-up was subsequently included in the
controlled public cutover recorded below.

The read model also distinguishes a current decision from immutable history.
A later inspection, batch/work version, admission decision or superseded
work-material requirement makes the old decision historical in the Support
view. The requirement table uses only current decisions and never treats an
old `admitted` row as permission to use material after its basis changes.
This is a deterministic projection; the historical row is preserved for
traceability and deletion remains workspace-scoped.
The Support writer independently rechecks the current batch/work versions,
latest preflight, current work-material requirement and active grant immediately
before appending a decision; the application-role precheck is not the sole
authority boundary. No claim is made that this replaces later material
application, consumption balance or document/payment prerequisites.

## Current public checkpoint — 2026-10-07

The requirement-by-work view and current-versus-historical admission projection
were deployed together as exact source SHA
`04c178c54c2006ea3c37eee6a2603fb4cdcb0125`, with unchanged public
migration `0136_support_material_admission_basis`. All four supervised
application roles (`api`, `worker`, `assistant-worker`,
`project-orchestrator`) are pinned to that release and running. Qwen and NTD
workers were not restarted. The API readiness check reports the same migration;
the served OpenAPI is structurally identical to the built v2.3 artifact (87
routes), whose SHA-256 is
`3c2fe23cf36e3474dc7897fc16d9088dd90e6365f901d613656914f8bfdc8af3`.
The frontend returns HTTP 200. The real workspace retains its 21 source
versions. No public material admission was manufactured. The full platform
data fingerprint remains
`ff6e99703e35fa28887ed16571aa62f552649ccd8027b60305691155f863e3da`.
The prior four launchd plists are backed up privately under
`~/.asd-kontur/public-demo/launchd-backups/20261007-pre-04c178c-material-currentness/`.
Focused exact-release tests passed 35/35; frontend typecheck, lint and build
passed. Authenticated owner-screen acceptance and real field-material evidence
remain unavailable, so Support and `ProductReady` remain incomplete.

## Actual material application — public checkpoint

The next Support capability records the *actual use* of an admitted batch on a
specific work. It is deliberately separate from delivery, incoming inspection
and admission. A qualified `support.material.apply` human must supply a
verified, work-version-bound `material_application` evidence link from an
active field document (design/delivery papers cannot stand in for actual use), exact
quantity/unit and reason. The writer rechecks the latest batch/work/preflight,
current admission, current work-material requirement and grant. It serializes
each batch's quantity budget and rejects a cumulative application above the
documented delivery; incompatible units and conflicting delivery bases fail
closed. Idempotent replay returns the same record, and a workspace fence
rejects late writes. The Support screen shows the source-linked actual-use
records and warns when their admission basis later becomes historical.

Migration `0137_support_material_application_basis` adds the admission and
authority links and scoped writer/read policies to the existing kernel
material-application table. Isolated PostgreSQL/API qualification covers
idempotency, over-application, wrong units, delivery evidence used as a false
work-use source, superseded preflight, reload and write fencing. This is a
released checkpoint at exact application SHA
`18ce8439198c3d39e63d8a3a1559e80d5c499612`. A public backup was made at
`~/.asd-kontur/public-demo/backups/0137-material-application-18ce843/pre-migration.dump`
(SHA-256 `1e6458335606b55f2212ef6dfb7977cd10b0cbcf2c68845c0d4f87cd4ff281eb`).
It restored to a separate qualification database and passed 0137 upgrade,
downgrade to 0136 and re-upgrade. The public migration then reached 0137;
all four supervised application roles are pinned to the exact release. The
API readiness check passed, the served OpenAPI was structurally equal to the
built artifact (SHA-256
`0e87c18dceac5522ab4e1d0e772dc500a9a63de46dea50cb0643def452affc79`),
the frontend returned HTTP 200 and the new unauthenticated command returned
401. Qwen and NTD workers were not restarted. The real workspace still has
21 source versions and zero material applications; the full platform-data
fingerprint remains
`ff6e99703e35fa28887ed16571aa62f552649ccd8027b60305691155f863e3da`.
The prior launchd plists are backed up privately under
`~/.asd-kontur/public-demo/launchd-backups/20261007-pre-18ce843-material-application/`.
Exact-release focused tests passed 36/36 and frontend typecheck/lint/build
passed. No public material application or owner field fact was created.
Authenticated owner-screen acceptance was unavailable because the browser
connection was absent. A verified material-use evidence
link must already exist, and material balance, work acceptance and KS/payment
readiness are **not** established by this slice. `ProductReady=false`.

## Field-document to actual-use evidence bridge (source qualification)

The 0137 application command was safe but its ordinary user path was incomplete:
the upload endpoint assigned every source the `project_evidence` role, while the
command required a verified `field_document` locator. Migration 0138 and the
corresponding API/UI now let the user declare a field document at upload and
have a qualified `support.material.apply` person confirm one admitted source
locator for an exact current admission/work. Only that confirmation creates a
work-version-bound, workspace-scoped material-use evidence link. A project
document or delivery record cannot be promoted by merely selecting it. The
actual quantity remains a separate command and stays capped by documented
delivery. The confirmation is idempotent, immutable, lifecycle-fenced, and in
the workspace destruction scope.

The isolated qualification exercises the upload role, rejection of a role
conflict on re-upload, refusal of a project-document locator, successful
qualified confirmation, replay/conflict, actual-use arithmetic, API reload,
0135-to-head migration roundtrip and workspace lifecycle tests. A user still
must provide a real field document and qualified confirmation; neither is
created for the existing owner project. This bridge does not establish material
balance, work acceptance, KS/payment readiness, complete Support-mode
acceptance or whole-product readiness. Authenticated owner-browser acceptance
and public deployment are separate checks, not inferred from source tests.
