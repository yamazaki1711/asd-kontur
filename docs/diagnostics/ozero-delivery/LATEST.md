# OZERO Tender delivery — current checkpoint

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
