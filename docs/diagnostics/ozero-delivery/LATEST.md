# OZERO Tender delivery — current checkpoint

## 2026-09-21 19:59 UTC+12 — 22/22 classification and grounded inventory consultation

API and document worker release `c4d7afff7fa8861a74deecedc84133a259ff2a6d`
is live and ready at migration `0063_structure_group_receipts`; assistant release
`e7282fb257e73ec1960bfe757a98030ec468d30c` is live. Nine active sources whose
historical classification jobs remained blocked behind failed OCR were recovered from
their persisted native layout. The recovery produced exactly nine dependency-free,
source/profile-scoped jobs: 9/9 succeeded, no OCR or semantic extraction was repeated,
and active-source classification coverage is now 22/22.

The refreshed candidate model retains complete v15 semantic-input coverage of
133,407/133,407 fragments across 22 sources and 2,529 pages. Current candidate-only
counts are 8,086 fields, 6,396 works, 2,718 quantities, 962 materials, 5,564 work
packages, 7,629 structure nodes, 2,325 relationships, and 1,662 defects. These counts
are persisted extraction/materialization evidence, not confirmed facts or Tender
acceptance.

Live assistant turns `01a0c2f6-1594-7958-9ab8-9c817c9df74e` and
`01a0c2f8-d53e-727b-b299-a3b79823cc93` passed deterministic and model checks. They
expose four explicit facility-associated pit candidates (КНС4, КНС8.1, ЛОС-4, and
ЛОС 8.1) with source links to POS pages 47, 118, 119, and 122. The answer explicitly
states that this is a candidate subset and that the exact project total is unproven.
The inventory still contains 254 unresolved pit-like observations, including generic
excavation descriptions and trenches, so an exact count remains open. Authenticated
browser acceptance is unverified because this execution environment has no attachable
browser instance.

## 2026-09-18 17:54 UTC+12 — source-linked Tender observations deployed

API/frontend release `38f637b6720b365aeb09b15fc1691e69674e913e` is active from the
controlled recovery worktree. A loopback readiness request with proxy bypass returned
PostgreSQL reachable at migration `0048_incremental_reconciliation_claim_priority`;
the root document serves the current built asset `index-DQPBu5bf.js`. The application
now presents persisted reconciliation defects as Russian, source-linked preliminary
Tender observations instead of raw generic object output. Each remains explicitly
non-final: it is neither a confirmed omission nor a verified noncompliance.

The deployment corrected an actual stale-binding defect: the API launchd manifest had
used the current virtual environment while importing Python and serving assets from an
older release tree. Its next/current service configuration now pins the same recovery
worktree and release SHA. The Qwen document worker was not restarted and its TX source
continues independently. Browser-authenticated verification and complete Tender
acceptance remain open.

## 2026-09-12 01:06 UTC+12 — effective failure coverage is separated from retry history

Pushed release candidate 4f41617eb2c27784bd969f76de3b49a69f60547b makes the
application coverage projection separate failed fragment attempts that have an accepted
successor from fragments still requiring recovery. The Russian project view now says
“требуется восстановление” only for the latter and labels the former as recovered
historical attempts. It neither changes source evidence, job lineage, candidate
authority, nor Qwen requests.

The revised scoped PostgreSQL query executed against the live OZERO data and returned
22 documents: 7 complete, 3 partial, and 12 not started. It found 948 historical
failed-attempt fragments with accepted successors and zero currently unresolved failed
fragments. Focused Python and frontend checks passed, including the actual scoped query;
browser verification remains unavailable because no browser is attached. This change is
not deployed while the document worker owns the active Qwen job.

## 2026-09-12 01:01 UTC+12 — isolated malformed leaves no longer starve a source

Pushed release candidate `a898ca36d502484a3b2b0c95c579e3dd6a9cfdb4` preserves the
strict six-collection engineering response schema and keeps malformed model output
out of candidate persistence.  After the bounded recovery reaches one exact source
fragment, it now records that fragment as failed coverage and continues the source;
it does not roll back accepted receipts or prevent other eligible sources from being
claimed.  Focused validation: Ruff format/check, strict mypy, and 54
`test_document_understanding` cases passed.  It is not deployed while the running
document worker owns the only Qwen workload.

The live worker remains release `9394b46`.  Its current source is
`Раздел ПД №12.2 005.2-2025-СМ2. Изм.3.pdf`; durable base progress is `158/1074`.
At the observation, its immutable v15 ledger contained 183 accepted receipts (1,800
input fragments) and 25 failed receipts (240 input fragments).  Accepted receipts
contain 125 field, 44 structural, 11 relationship, 251 work, 149 quantity, and 17
material observations.  The old worker has not materialized any of those observations
into this source's candidate projection, so they are not yet a project-model result.

Next active work: let this job reach its safe terminal boundary; then validate its
receipt lineage, make the required recoverable backup, transition the worker to the
matching partial-materialization release, and use supported downstream recovery.
This remains partial semantic evidence, not a facility inventory, pit count, Tender
finding, or consultant acceptance.

## 2026-09-12 00:51 UTC+12 — candidate-only partial model release active

The public API and rebuilt frontend are pinned to
`6194eb31fd82630b136dd0f404252b532a8cae44`, with PostgreSQL migration
`0048_incremental_reconciliation_claim_priority`. A loopback readiness request
returned `ready` at that exact migration. The release was qualified in an isolated
loopback API process before activation; the preceding launchd registration failure
was recovered using the preserved API plist and did not affect data or workers.

The document worker was deliberately not restarted. It still owns OZERO semantic job
`01a08f4e-3b5e-798c-9d5b-b3acd1724683` for
`Раздел ПД №12.2 005.2-2025-СМ2. Изм.3.pdf`; its durable progress is `127/1074`.
The API now selects accepted semantic-batch receipts for partial candidate publication.
That makes already accepted source evidence available to the real project-model
surface without treating it as reconciled facts. The assistant worker was not changed
while the document worker uses the single local-Qwen slot.

At this snapshot the exact semantic-input denominator is 22 documents / 2,529 pages /
133,407 fragments: 7 documents have complete accepted semantic input coverage, 3 are
partial, and 12 are not started. Accepted input fragments total 24,499; 888 are
historical failed-attempt inputs with successor handling, not a second document count.
The current projection contains 1,869 field, 1,256 work, 377 quantity, 160 material,
and 417 structural-relationship candidates. They remain source-backed candidates only:
no reconciled facility/LOS/KNS inventory, pit total, Tender conclusion, or consultant
acceptance has been established.

Next active work: allow the running source to reach a terminal receipt, validate its
candidate provenance and dependent recovery, then transition the document worker at
that safe boundary to the same pinned release for dense manifests and continue the
remaining eligible sources. Cross-document facility reconciliation, project-specific
NTD checks, Tender findings, and grounded consultant/browser acceptance remain open.

## 2026-09-12 00:32 UTC+12 — complete-source pass remains active

The active OZERO source is `Раздел ПД №12.2 005.2-2025-СМ2. Изм.3.pdf`
(`01a088ac-7fdb-7b12-be33-e3a325af8edf`). Its live v15 job has an immutable
accepted-batch progress event of `110/1074`. The document worker and Qwen process
remain live; no source, retry lineage, or accepted batch has been reset.

The scoped application projection currently reports 22 active source versions and
2,529 pages: 7 semantic sources complete, 3 partial, and 12 not started. It exposes
1,824 field, 1,080 work, 342 quantity, 160 material, 1,308 structural, and 417
relationship **candidate observations**. These figures are not facility identities,
confirmed facts, an excavation-pit total, or a complete Tender analysis.

`de7f403` is the tested pending delivery change. It publishes accepted semantic-batch
observations as exact-locator partial candidates and makes the API select a current
accepted batch profile before terminal source completion. Cross-batch quantities and
materials remain deferred until their work relationship can be reconciled. The staged
release is not activated while the old worker owns the active Qwen job.

Next operational action: wait for this source's terminal receipt, inspect its persisted
candidate provenance, make a fresh recoverable backup, deploy the pinned release, and
exercise the live partial project-model view. Full corpus extraction, cross-document
facility reconciliation, project-specific NTD checks, Tender findings, and consultant/
browser acceptance remain open.

## 2026-09-11 21:09 UTC+12 — v15 complete-source pass continues

API release `8159206681f681ed84a3807c9b09120e90461d07` is ready at migration
`0047_profile_scoped_engineering_candidates`. The document worker imports the same
release worktree. Its recorded launchd label is older (`22142e2`), so the next safe
worker transition must correct that release-manifest label; the code path itself was
verified from `PYTHONPATH` and is not inferred from the label.

The only active Qwen document workload is job
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096` for
`Раздел ПД №12.3 005.2-2025-СМ3. Изм.3.pdf` (121 pages, source version
`01a088ac-7f97-761a-b857-f5d3b4c5be8b`). Its native evidence denominator is 5,957
locators. At this observation the job had durable base progress `309/497`, 3,672
accepted fragment inputs, and 135 immutable failed-attempt inputs. It remains running
with a fresh lease and a live worker-to-local-Qwen loopback connection. This is active
semantic processing, not source completion or a Tender result.

The partial candidate ledger now contains 684 fields, 1,156 works, 281 quantities,
124 materials, 864 source-scoped structure observations, and 169 relationship
observations. None is a reconciled cross-document facility, LOS/KNS, excavation-pit
inventory, or confirmed fact. The current UI can expose expired job leases honestly;
browser acceptance is still unverified because no browser binding is available.

The next supervised-worker plist was staged with the verified `8159206` release
identity and backed up before the edit. It was deliberately **not** reloaded: the
running job retained its original process, fresh lease, and worker-to-Qwen connection.

## 2026-09-11 20:56 UTC+12 — exact-evidence graph components live

API/frontend release `6739b203269dd20e0eab1d22532271217e1a451c` is live at migration
`0047_profile_scoped_engineering_candidates`; its launchd source path is explicitly
pinned to the release worktree. Live OpenAPI exposes `structure_components`, and the
owner-scoped OZERO project-model boundary returns 32 exact-evidence graph components
from 864 structural candidates and 169 relationship observations. A component joins
only endpoints already resolved inside the same source evidence; it deliberately does
not merge equal names across documents, establish a facility identity, or determine a
pit total. The Russian model UI displays these as source-linked candidate groups.

The active document worker remains `22142e2` and local Qwen was not restarted. Job
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096` is still processing source version
`01a088ac-7f97-761a-b857-f5d3b4c5be8b`, with durable base progress `282/497` at the
checkpoint. Full semantic coverage, cross-document reconciliation, project-specific
NTD checks, Tender findings, browser source-link acceptance, and consultant acceptance
remain open.

## 2026-09-11 19:59 UTC+12 — partial structural dossiers deployed

API/frontend release `43244dba95d8d8974e45401e1790cfa45be67cc6` is live at the
same migration `0047`. The actual scoped project-model boundary now returns 864
source-scoped structural dossiers alongside the candidate nodes and relationship
observations. Each dossier retains its original source locator and only includes
relationships resolved to that exact evidence-scoped node; no cross-document name
merge, facility identity decision, or excavation-pit total is asserted. Browser
acceptance remains unverified in this checkpoint.

The document worker remains `22142e2` and local Qwen continues job
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096`; its current durable base-batch progress is
`25/497`. The entire Tender acceptance remains open.

## 2026-09-11 19:51 UTC+12 — real worker batch-progress proof; corpus remains partial

The document worker was transitioned at a safe semantic-job boundary to pinned release
`22142e2c2737d97e8bfbdfce22d7e7ef211b2f40`; Qwen remained loaded and was not restarted.
The new worker claimed OZERO job `01a08f4e-3b5b-7851-9f3d-fcaf3e84c096` for source version
`01a088ac-7f59-7a03-b342-fd7187e8d472` and appended durable, content-free events
`engineering.semantic_batch_progress` for `1/497` and `2/497` accepted base batches.
This proves the deployed document-worker → local-Qwen → PostgreSQL progress-event path.
It does **not** prove source completion, candidate persistence, facility reconciliation,
or a usable Tender result.

The API remains pinned to `f533d5c6586448369fe58ae5a9d1de2a91cbac6b`; the static frontend
artifact was rebuilt from `22142e2` and labels only genuine semantic-batch events as
`Семантические пакеты`. The API readiness check is still healthy at migration
`0047_profile_scoped_engineering_candidates`. The assistant worker remains unchanged.
The prior source `01a088ac-7f16-73ef-9d2c-3957b2393f66` completed before the transition;
its workspace-wide candidate totals are raw profile-scoped candidate evidence, not facts
or a project inventory. The active 497-batch source, its 20 remaining semantic successors,
and workspace reconciliation remain open.

## 2026-09-11 19:42 UTC+12 — API/frontend progress release active; source pass continues

The API/frontend is pinned to `f533d5c6586448369fe58ae5a9d1de2a91cbac6b` and the
current bundle returns HTTP 200 through the actual loopback application route. Readiness
reports PostgreSQL reachable at migration `0047_profile_scoped_engineering_candidates`.
The document worker intentionally remains on `13f50af54c61c3847cac285087c9308f9a2fe7be`
while its active Qwen request is in progress; the assistant worker is unchanged. This
split is backwards-compatible: the UI displays an em dash until an older API or worker
supplies the new safe progress fields.

The worker's active source, `01a088ac-7f16-73ef-9d2c-3957b2393f66`, remains running
with a current lease. At the snapshot its v15 immutable ledger has 107 accepted batches
and 1,284 accepted fragment inputs, with no failed v15 receipt. This is not a completed
source, candidate persistence, project-model materialization, facility reconciliation,
or Tender result. The 21 other profile-aware source successors and the reconciliation
job remain queued.

`c98db6a` adds content-free durable semantic-batch events; `4406e23` exposes the latest
event on effective jobs; `f533d5c` makes the UI robust while an older API is still in
place. A disposable PostgreSQL regression proves the effective jobs API retains a linked
running retry beyond 205 historical jobs and returns `7 / 10` progress. A real semantic
event remains unverified until the active source reaches terminal state and the document
worker is transitioned.

## 2026-09-11 19:12 UTC+12 — profile-scoped release live; complete corpus pass active

The controlled OZERO release is now pinned to `e28da91a57879602f727faedf74acbd9e8fe7adb`
for API, document worker, and assistant worker. The API readiness route is `ready` at
database head `0047_profile_scoped_engineering_candidates`. The exact pre-0047
database backup was successfully created and verified in the restricted operational
store before the additive migration; its path and digest are deliberately not copied
into Git.

The POS source version `01a088ac-81c2-7033-8f75-8160ffeb2cb2` completed its original
v15 run as durable historical evidence: 443 accepted batches cover its complete
5,252-fragment manifest. Five rejected attempts cover 60 attempt fragments, with
accepted bounded recovery children present in the same immutable ledger. The old
worker wrote a complete generic persistence stage and source-backed candidates
(299 fields, 494 structural nodes, 148 raw relationship observations, 478 work
candidates, 94 quantities, and 45 materials). These are candidates under the old
profile, not reconciled facilities, Tender facts, or an exhaustive pit inventory.

The live profile-aware `start_project_understanding` command has scheduled one
version-aware semantic successor for each of the 22 active source versions plus one
workspace reconciliation job. It neither re-runs OCR nor mutates historical attempts.
POS successor `01a08f4e-3b70-76ff-8245-15626d8da266` is queued with explicit v15
semantic and candidate-persistence provenance and will reuse compatible POS batches.
The single supervised document worker is currently processing
`Раздел ПД №12.5 005.2-2025-СМ5_ПИР_pdf.pdf`; 21 successors remain queued. This is
full-package processing in progress, not semantic coverage completion or Tender
acceptance.

The frontend artifact from `de98eaf4f1f535692c6af7d7c712767aa65fdae0` is also live
with the compatible e28 API: the Russian structural-candidate panel now supports a
name/kind search and incremental display of every returned structure and relationship
candidate. It no longer silently stops after 200 rows. This makes partial evidence
inspectable; it does not reconcile aliases or convert candidates into confirmed facts.

Updated: 2026-09-11 16:41 UTC+12

The live API is pinned to `8e0c2f5c68ff2c36a4b428dba9e8ec70b18338da`, the scoped
document worker to `18c6893fdbee5186b351bdddaab2920c8f7eda3d`, and the assistant
worker to `a9a693a854f4dd4120de6e8f16451923d82fe4ab`, all at database migration
`0045_bounded_dep_recovery`. The API readiness check reports PostgreSQL reachable.

PZU (source version `01a088ac-8125-7031-8659-a57bd97ff1c6`, 56 pages) reached its
entire v12 semantic input denominator: 5,021 accepted fragment inputs. Five rejected
model attempts remain immutable historical attempts. Their bounded recovery children
are the accepted evidence; this is not a claim that every engineering interpretation is
complete or confirmed.

The current project view is partial. It exposes source-backed candidate collections and
coverage separately from reconciled facts. Workspace totals at this checkpoint are 109
field candidates, 429 work candidates, 121 quantity candidates, 41 material candidates,
188 structural candidates, and five excavation-pit candidates. Those pit candidates are
not an established count: cross-document identity, revision, and coverage reconciliation
are still required.

KR1 (source version `01a088ac-8084-7c59-8b1a-c9bda7ad8208`) is the active next
structural source. Its sole replacement job is `01a08eac-9094-73c6-b936-3ca9bc2a0044`.
It has accepted 2,442 of its 2,960 deterministic semantic fragment inputs at this
snapshot. One immutable failed child receipt covers 12 inputs and remains a visible
unresolved model attempt; it is not relabelled as success. Do not create another
replacement while that job runs.

The semantic coverage query now enumerates all active sources rather than only sources
which already have accepted batches: 22 active documents, 1 complete, 2 partial, and
19 not started. KR2 has exactly one queued successor
`01a08ec5-b223-7f78-8c1c-893ca2bb8eff`, which will follow KR1 without concurrent heavy
Qwen execution.

Pushed but un-deployed commits `c460131`, `e4b2083`, `742357b`, `a36ee21`, and `e1c3908` add profile v15 and an additive
relationship-candidate ledger. The ledger retains evidence-bound raw endpoints and does
not perform a name-only facility merge. Its migration is
`0046_structure_relationship_candidates`; release waits for the active v13 job to
become terminal.

KR1 v13 has now completed its 2,960 accepted fragment-input denominator. The immutable
failed child receipt remains separate. Its accepted candidate evidence has reached the
partial live project view: 231 field candidates, 486 work candidates, 142 quantity
candidates, 68 material candidates and 274 structure candidates across the workspace.
Examples visible through source links include KNS observations in IOS1 pages 10, 12–13,
and 52. They are not yet reconciled facility dossiers, nor evidence of an exhaustive KNS
or excavation inventory.

Next active work: materialize KR1 through the durable dependency chain; then run KR2
and POS. Assemble facility/area relationships, complete the source manifest, perform
cross-document Tender reconciliation and normative evaluation, and verify the project
consultant through the user-facing application.

## 2026-09-11 17:11 UTC+12 — current correction and release gate

KR1 and KR2 are no longer active: their v13 semantic manifests have respectively
accepted 2,960/2,960 and 1,525/1,525 fragment inputs. Failed input counts (12 and
24) are immutable historical attempt records; they do not reduce accepted coverage.
The source-scoped KR2 downstream chain completed. Package completion, facility
reconciliation, and Tender acceptance remain open.

The one permitted POS replacement failed immediately as
`structured_extraction_evidence_unavailable`. Its receipt demonstrated that the
deployed worker gates Qwen semantic extraction on deterministic role decisions.
Commit `ce9cd3b` removes that incorrect gate for evidence-bearing native elements
and retains Qwen relationship candidates; it is fully qualified but **not
deployed**.

Deployment is blocked solely by the required current full-backup gate. The existing
application role can access scoped OZERO records but `pg_dump` fails on a platform
table permission check. No migration, service reload, or source mutation was made.
The next active work is locating the already-authorized full-backup/migration path;
then deploy exact `ce9cd3b` with additive migration 0046 and retry only the POS
failure lineage.

## 2026-09-11 18:23 UTC+12 — profile-isolation release prepared

The active POS v15 semantic job remains `running` under the existing pinned worker;
at this observation it had 308 accepted durable batch receipts (3,672 fragment inputs)
and two immutable failed parent receipts whose recovery children are accepted. It has
not yet reached candidate persistence, project materialization, or Tender acceptance.

Release candidate `c29e8e3` (including
`b0b80a8275519e569b0faf38ffa1f6e50a359a24`) is pushed but **not deployed**.
It adds additive migration `0047_profile_scoped_engineering_candidates` and keeps
Qwen engineering observations, structural nodes, relationships, and extraction defects
scoped to the exact semantic profile that produced them. The active project view and
reconciliation will select only the completed profile for each active source; legacy
generic candidates remain immutable historical evidence rather than being mixed into a
newer Qwen pass. A profile-aware successor can reuse compatible accepted v15 manifests
to persist the corrected candidate identities without rerunning OCR or duplicating Qwen
inference.

Focused unit, PostgreSQL integration, format, lint, and strict type checks passed for
this release. A job is reusable only when its exact profile provenance and immutable
`PROJECT_DEFINITION_EXTRACTION` stage receipt both exist; a terminal state alone cannot
silently suppress recovery. Activation waits for the current POS worker job to become terminal so its
accepted batches and lease are preserved. The next executable action is to verify that
terminal receipt, apply the additive migration through the existing recoverable release
procedure, and schedule the profile-aware persistence successor exactly once.

## 2026-09-11 20:19 UTC+12 — current OZERO delivery state

POS (`Раздел ПД №7 005.2-2025-ПОС_изм.8.pdf`, source version
`01a088ac-81c2-7033-8f75-8160ffeb2cb2`) has completed its v15 source denominator:
5,252/5,252 accepted semantic fragment inputs. Five immutable failed-parent attempts
cover 60 inputs; accepted bounded children provide the covered evidence. Its downstream
candidate and materialization stages completed and persisted 299 field, 478 work, 94
quantity, 45 material, 494 structural, and 148 relationship candidates. They are not
confirmed project facts, reconciled LOS/KNS dossiers, or a project-wide pit count.

The live candidate-only workspace view is still partial: 22 active sources / 2,529
pages, with 6 semantic-complete sources, 2 partial sources, and 14 not started. The
selected compatible collections contain 639 fields, 980 works, 246 quantities, 124
materials, 864 structure candidates, and 169 relationship observations. Full-package
coverage, cross-document reconciliation, normative evaluation, Tender findings,
browser source-link acceptance, and consultant acceptance remain open.

The only active Qwen document workload is job
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096` for
`Раздел ПД №12.3 005.2-2025-СМ3. Изм.3.pdf`: 72/497 accepted batches at this snapshot.
It is progressing through one supervised worker and the local Qwen runtime. An older
dead-worker lease is now explicitly surfaced as expired rather than falsely displayed
as active.

API/frontend release `bb7c86743e8324fa5b7c808bca7fd7ce29d08945` is live at database
migration `0047_profile_scoped_engineering_candidates`; readiness reports PostgreSQL
reachable. Assistant worker release `f42cbcd00969bd19de7aba529d53b761683a6e85` is
live. It ensures derived work-package/matrix/discrepancy tools cite their own exact
workspace evidence. Document worker and Qwen remained running without interruption.

## 2026-09-11 20:25 UTC+12 — visibility and consultation safeguards deployed

API/frontend `3c64021bc720f0a0e56172945d1a3be63a0ffdd6` is live and ready at migration
`0047_profile_scoped_engineering_candidates`. Candidate schedules no longer silently
stop after the first 100 rows: Russian local filtering and explicit incremental display
make the persisted partial works, quantities, and materials inspectable with their
source links. The change does not reconcile identities or promote candidate data.

Assistant worker `f1d9e453981f7b352856365719b15479f044c072` is live. Its workspace
overview exposes the per-source semantic-coverage state and an explicitly
candidate-only summary; its derived work/package/matrix/discrepancy tools retain their
own exact evidence items. This prevents an incomplete model from appearing to support
an exhaustive factual answer. Browser acceptance is still unverified because this
Codex session has no attached browser; no browser PASS is claimed.

## 2026-09-11 21:45 UTC+12 — active-source completion and fair queue are live

The currently deployed document-worker source tree is pinned at
`75666044b2598bffaa5418f40cc830f36cd773b6`. Its only active Qwen semantic source,
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096` for source version
`01a088ac-7f97-761a-b857-f5d3b4c5be8b`, was `running` with a fresh worker heartbeat
and durable base-batch progress **350/497**. At this point its v15 ledger contained
365 accepted and 21 immutable failed-parent receipts; child recovery lineage must be
evaluated at terminal completion, so those receipt counts are not published semantic
coverage or Tender findings.

The supported owner-scoped project-understanding command was invoked once while that
job ran. It preserved the running job, placed reconciliation
`01a08fd8-5866-7a9d-9697-6e74e32dc94e` in the durable queue, and recomputed priority
only for compatible queued source jobs. Ten source extractions (including PZU and KR
inputs) now have priority 170; eight stay priority 130 pending better available role
evidence. The next observable product boundary remains source candidate persistence
and a priority-165 partial reconciliation after this current source is terminal.

## 2026-09-18 15:57 UTC+12 — active recovery and pending compatible release

The scoped OZERO worker is actively processing iOS1 semantic recovery job
`01a0b287-9b11-740a-ac24-a49a4f616b23`: its durable progress is **168/180** accepted
bounded batches, with a fresh lease heartbeat. The local Qwen3.8 process has an
established worker connection and is consuming CPU. This is active model work, not a
claim of completed source coverage or Tender analysis.

Two compatible commits are pushed but deliberately not deployed while that request
owns the worker: `bd79d82` preserves accepted candidates from a partial source in
assembly and API materialization, and `1628f3f` makes the loopback Qwen transport
threaded while preserving its single generation lock. The latter will make health
observable and return a bounded busy response during a document request; it does not
allow concurrent Metal generation. After the active job terminals, the release
procedure is: capture its receipts and coverage, take a fresh database backup, switch
the API/document-worker/Qwen launchd units to the pinned release, verify health and
candidate materialization, then continue only eligible source recovery.
