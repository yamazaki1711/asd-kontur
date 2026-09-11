# OZERO Comprehensive Tender Goal

## Objective

Deliver comprehensive, persistent, evidence-backed PD understanding and usable Tender analysis for
the existing OZERO workspace `01a088aa-0491-7bdd-9127-8359fe927a27`. The result must cover the
complete uploaded package, including every identifiable local area, LOS, KNS, associated excavation,
structure, work scope, quantities, materials, requirements, cross-document disagreement, and missing
information. It is a Tender delivery through shared ASD-KONTUR architecture, not a ProductReady claim.

## Authority and boundaries

Codex implements software, migrations, tests, controlled releases, and orchestration. Local
Qwen3.8-27B performs model-based OCR/VLM, semantic interpretation, engineering extraction, and
consultant generation. Deterministic local code handles native extraction, rendering, splitting,
validation, indexing, and reproducible calculations. Do not use cloud inference, Apple Vision,
Tesseract, or Codex inference as substitutes for Qwen document interpretation.

Keep engineering reports and commits in English. Keep UI and consultant responses in Russian. Preserve
the workspace, source versions, original failed turn `01a088c6-a7a0-7fb4-8a64-732bac76b362`, candidate
authority, evidence provenance, RLS, historical attempts, and unrelated worktree changes. Do not merge
to main, reset OZERO, weaken access controls, or repeat accepted OCR without a demonstrated defect.

## Programme and acceptance

1. Account for every active document, revision, page, meaningful region, and processing disposition.
   Native extraction, visual interpretation, semantic analysis, and reconciliation have separate
   denominators. A successful historical job is not semantic coverage.
2. Build connected reusable entities for the project, locations, LOS/KNS, structures, pits, works,
   quantities, materials, interfaces, and construction dependencies. Preserve containment, location,
   functional connection, and dependency separately. Keep ambiguous links and unresolved observations.
3. Provide evidence-backed dossiers for each identified facility and local area, including aliases,
   purpose, location references, constituent elements, supported dimensions/levels/conditions,
   construction solution, work/material scope, interfaces, source revisions, contradictions, and gaps.
4. Reconcile evidence across disciplines for Tender findings, clarification questions, scope uncertainty,
   potential omissions, and constructability risks. The preliminary sheet-pile/waling-beam business
   scope remains unawarded until sources and authority establish otherwise.
5. Publish Russian project navigation: project → local area → facility → structures/pits → works/materials
   → evidence. Publish honest partial coverage and candidate status; never present no-analysis as zero.
6. Connect the consultant to structured inventory plus evidence. It must support project-wide/local
   questions, comparisons, follow-ups, and exhaustive inventories only where coverage supports them.
7. Accept only after all active pages are accounted for, eligible analysis completes, local-area/LOS/KNS
   dossiers reconcile, relationships survive batch/document boundaries, Tender findings are traceable,
   30 substantive package-wide consultant questions pass, reload/restart/isolation pass, and deployed
   API/UI/worker versions are compatible.

## Current baseline and next action

The package has 22 active source versions and 2,529 pages. V1 engineering extraction of one 60-page
source completed with 2,154 accepted locator fragments and partial candidates; this is preserved evidence,
not full-package acceptance. Database migration `0039_engineering_batches` is live. Commit `fbb7131`
contains the versioned v2 extraction correction but is not deployed at this checkpoint.

### Continuation checkpoint — 2026-09-11

The former v2 checkpoint is superseded by versioned engineering extraction releases. Migration
`0042_dependency_recovery` is applied to the controlled workspace database after a consistent local
backup. The active document worker and local Qwen remain pinned to `bd34f90` while the existing v4
extraction request runs; no active Qwen request was interrupted. Commit `b88507e` is tested and pushed
for the next controlled worker release. It records auditable dependent replacements only when a
causally-linked prerequisite with the same job kind, source manifest digest, and subject succeeds; it
does not erase the historical terminal job or treat an arbitrary newer job as a prerequisite.

For source version `01a088ac-7f16-73ef-9d2c-3957b2393f66`, the complete deterministic v4 manifest
has 1,453 native elements/fragments and 61 base batches. Earlier v2/v3 rows are immutable historical
evidence. The sole v4 retry `01a08e02-1fba-7e43-b1f3-5f2371f65d52` persisted 19 accepted v4 batch
receipts, then correctly failed with `qwen_engineering_response_invalid_evidence`; it has not reached
candidate persistence or project materialization. Inspection established a separate persistence-contract
defect: v4 batch `input_manifest` is stored as a top-level array while the coverage query expects an
object containing `fragments`. Treat the accepted rows as immutable semantic evidence, not as v4
coverage proof. No project-wide result is accepted from this source.

The committed UI/API coverage surface reports accepted semantic fragments separately from classified
pages and from reconciled facts. It is not yet deployed with the corresponding API/frontend release.

Next executable action: implement and qualify a v5 engineering-batch manifest that stores the full
object-shaped input contract, can replay only exact compatible v3/v4 accepted batch evidence, and records
the failing single-fragment response lineage without accepting malformed evidence. Then run one targeted
successor for this source, release the already-migrated dependency-recovery worker, recover only the
blocked downstream stages through the verified replacement lineage, and verify workspace assembly before
scheduling the next eligible active source. Do not leave the OZERO queue empty while eligible sources
remain.

### Continuation checkpoint — 2026-09-11 14:00 UTC+12

The active database is at `0045_bounded_dep_recovery`, backed up before that migration. API release
`b88507e` is compatible and ready at that revision. The supervised document worker is release
`4b0582f`, with `PYTHONPATH` pinned to that release and an explicit RLS scope limited to the OZERO
organization/workspace. This corrected a live deployment defect: the copied launchd plist had retained
the prior release's `PYTHONPATH`, so its executable and imported source did not match. The worker's
initial global dependency-recovery scan also bypassed useful scoped work and stalled over historical
failures; scoped workers now claim runnable work before any unscoped maintenance scan.

The existing v5 successor `01a08e16-f10b-7d6f-90fd-e0f9d9153d2e` is running under
`document-worker:36829`, not duplicated. It replaced only the expired diagnostic lease and has an
established worker-to-local-Qwen loopback connection. One v5 batch for source
`01a088ac-7f16-73ef-9d2c-3957b2393f66` has been accepted and durably recorded; the source still has
61 base batches, so this is progress evidence only, not source or package semantic coverage.

Commit `f5eae86` is pushed and qualified by 39 focused unit tests. It corrects an independent delivery
break: Qwen engineering works, quantities, materials, and unresolved-relationship defects were computed
but discarded by the project-definition path. The pending release preserves those candidates alongside
deterministic supplements and reuses accepted batch receipts rather than asking Qwen again. Do not deploy
it until the active v5 job reaches a terminal state. Next executable action: observe the active job to a
durable batch/result transition, then release `f5eae86`, recover its source-scoped downstream stages,
validate candidate provenance and materialize the project view before scheduling the next active source.

### Continuation checkpoint — 2026-09-11 14:16 UTC+12

The controlled database remains at `0045_bounded_dep_recovery`. API and frontend release
`058bf960d3d025ba63efd41342d9898c6ce43ad2` is live with its source explicitly pinned through
`PYTHONPATH`; it exposes semantic extraction coverage with document identity, revision, and page
denominator rather than an opaque source UUID. A scoped application-boundary read returned a partial
model view with source-identified coverage and candidate-only collections; this does not establish
project facts or UI-browser acceptance.

The prior v6 successor `01a08e37-1b2b-74f4-9b7e-9ed5e4ea91de` preserved 179 accepted fragments
from 32 durable receipts and then failed as `qwen_engineering_response_invalid_evidence`. It did not
persist candidates for that source, and the historical failure remains immutable. Commit
`99100771e098c78feefc8ae727ca3a3da89e34c1` introduces `qwen-engineering-extraction-v7`: it reuses
only compatible validated v6 receipts, accepts a Qwen short evidence alias only with harmless terminal
punctuation normalization, and accepts a source-locator UUID only where it maps to one input fragment.
Unknown or ambiguous evidence stays a typed failure. Focused semantic tests: 41 passed; Ruff and strict
mypy passed. The scoped document worker is live at that release.

One authorized manual successor, `01a08e40-42f4-79e4-9159-538249e87fc9`, is running from the v6
failure lineage. It is the only replacement, has a current lease heartbeat, and has a live loopback
connection to the local Qwen runtime. Do not create another retry while it remains running. Next
executable action: observe its first durable v7 batch or terminal transition. On success, validate exact
v6/v7 batch coverage, candidate provenance, and targeted dependent recovery before materializing the
source through the project view; then schedule the next eligible active OZERO source without global
recovery scans. On failure, inspect the exact typed result and change only the demonstrated batch contract.

### Continuation checkpoint — 2026-09-11 14:22 UTC+12

The v7 successor failed after one accepted receipt, again with
`qwen_engineering_response_invalid_evidence`; it remains immutable. Commit
`a8267062faf8abacd227ee4d93605f68a6f15b96` is the active scoped worker release. It versions the
contract as `qwen-engineering-extraction-v8`, performs a bounded local-Qwen evidence-reference repair
before batch subdivision, rejects a vacuous repair response, and records sanitized failed batch metadata
(input-fragment identities and typed failure only, never document text) under the existing immutable
batch ledger. Unit validation: 41 passed, Ruff and strict mypy passed.

The only active successor is `01a08e45-ecbd-708a-b322-3658cf96d6ff`, caused by the v7 terminal job.
It is running under the v8 worker with a current lease and an established Qwen loopback connection. It
will reuse valid v6/v7 evidence only through declared compatibility. Next action: observe the first v8
accepted or failed receipt; a failed receipt will identify the exact bounded input lineage for the next
contract change without exposing document text. Do not restart or duplicate this job.

### Live observation — 2026-09-11 14:25 UTC+12

The v8 successor remains running. Its durable receipts show one accepted one-fragment repair result and
seven failed evidence-validation attempts covering 27 bounded input fragments. Failed receipts retain
only exact batch ordinal, source-fragment identity, and typed failure; for example, the first failure was
base batch 13 on six page-4 fragments. The worker has not restarted the source and maintains a live
connection to local Qwen. This is active recovery evidence, not semantic coverage or candidate
materialization. The next engineering change after this active job reaches a terminal state is to add
sanitized per-row validation diagnostics to failed receipts, then adjust only the demonstrated Qwen output
contract and retry the failed lineage once.

### Continuation checkpoint — 2026-09-11 14:45 UTC+12

The live database remains at `0045_bounded_dep_recovery`. The source package denominator is 22 accepted
source versions / 2,529 pages. Source version `01a088ac-7f16-73ef-9d2c-3957b2393f66` has 1,453 native,
readable layout elements (75,923 characters), deterministically partitioned by the current v10 contract
into 243 standard semantic batches. This is a source-specific denominator, not package semantic coverage.

The v9 descendant `01a08e4f-09a6-7436-935e-099934df66ab` is terminal with one accepted and twelve failed
batch receipts. Sanitized v9 diagnostics established that the failed quantity rows cited valid fragments
but omitted one or more of work name, value, or unit. Commit `61b78d8d7f9fe4dc6c176b6da818f3a426f804a7`
introduces `qwen-engineering-extraction-v10`: such cited observations persist as non-blocking,
evidence-linked `incomplete_quantity_candidate` reconciliation defects; they are never quantity candidates
or project totals. Ruff, strict mypy, and 42 focused document-understanding tests passed.

Worker release `61b78d8` is live, with `PYTHONPATH` and executable pinned to its release worktree.
The only v10 successor is `01a08e56-2374-72b4-b529-c79ba809d3e9`, caused by the terminal v9 job. It is
running, has a live worker-to-local-Qwen connection, and had durably persisted 35 accepted v10 batch
receipts at the snapshot. No second retry may be created while it runs.

Commit `c0047116336625b7d7a48baaf7bee6afdb3aa618` is pushed but not deployed. It versions the profile
as v11 and prevents identically named work observations from being merged merely because they occur on
the same page. A quantity/material relation with an explicit work fragment resolves only to that exact
evidence-bound work; an unqualified same-name relation remains a reconciliation defect. Ruff, strict
mypy, and 43 focused tests passed. Deploy v11 only after the v10 successor is terminal, then create one
version-aware successor to materialize the source using compatible v10 batch evidence and recover its
causally linked downstream stages. Validate candidate provenance and the project view before scheduling
the next eligible source; do not claim project facts, a pit count, or package completion before then.

### Continuation checkpoint — 2026-09-11 15:15 UTC+12

The v10 successor completed successfully at 15:11 UTC+12. Its terminal receipt recorded 45 project-field,
160 work, and 31 quantity candidates for source `01a088ac-7f16-73ef-9d2c-3957b2393f66`; this source had
no extracted structures or materials. The v11 materialization successor
`01a08e74-4695-7a56-9ee2-01f1f5829f0d` completed under release `c004711` without an additional Qwen
request by replaying compatible v10 manifests. It persisted 176 evidence-distinct work candidates, proving
that same-name work observations are no longer overwritten. Its success recovered source-scoped evidence,
work-quantity-material, work-package, matrix, and reconciliation stages through the durable dependency
lineage. The application repository now exposes a partial workspace view containing candidates and coverage;
it is not a completed Tender model or browser acceptance.

Commit `f04d28d4cf069faed691c50ec275e099508cd6f4` introduces `qwen-engineering-extraction-v12`, a bounded
delivery-throughput contract: every fragment remains traceable, but short fragments are packed to at most
24 fragments and 12,000 characters per Qwen request. The source-specific test proves exact full fragment
coverage under both bounds; Ruff, strict mypy, and 44 focused tests passed. Worker release `f04d28d` is
live. The only active successor is `01a08e75-ba75-775a-8137-f9984ff63a39` for PZU source
`01a088ac-8125-7031-8659-a57bd97ff1c6` (56 pages; 5,021 deterministic semantic fragments). It is
processing with local Qwen under the v12 bounded contract. Do not create another PZU retry while it runs.
After PZU reaches a terminal state, validate candidate provenance and the partial project view, then choose
the next structural source (KR1/KR2/POS) using the same v12 path.

### Continuation checkpoint — 2026-09-11 16:14 UTC+12

PZU source version `01a088ac-8125-7031-8659-a57bd97ff1c6` completed its v12 semantic manifest at
16:05 UTC+12: 5,021/5,021 accepted fragment inputs. Five failed model attempts (96 input-fragment
entries across immutable failed receipts) remain visible as failed attempts; their successful bounded
children provide the accepted coverage and were not relabelled as parent success. The source-scoped
`WORK_QUANTITY_MATERIAL_EXTRACTION`, work-package, matrix, reconciliation, and evidence-index
successors then completed through the accepted dependency lineage.

The PZU source contributed 61 project-field candidates, 252 work candidates, 86 quantity candidates,
39 material candidates, and 177 structural candidates. These remain source-backed candidates, not
confirmed project facts or an excavation-pit total. Across the workspace, the current partial model has
109 field candidates, 429 work candidates, 121 quantities, 41 materials, 188 structural candidates, and
five excavation-pit candidates. The latest reconciliation remains `partial` with explicit field conflicts,
missing project-definition fields, unresolved work-type mappings, and unqualified normative/rule inputs.

Release `18c6893fdbee5186b351bdddaab2920c8f7eda3d` is live for both API and worker at database migration
`0045_bounded_dep_recovery`; its API serves the matching built frontend and `/api/v1/health/ready` reports
PostgreSQL reachable at that migration. It replaces the unconditional work-type catalog placeholder with
evaluated work-mapping gaps, makes project/matrix/reconciliation state derived rather than hard-coded, and
shows partial candidate categories in the Russian UI. It also reuses accepted recovery child batches rather
than re-running the failed parent request in a dependent stage. Static checks and 16 focused engineering
semantic tests passed; the disposable-PostgreSQL integration test was skipped because
`ASD_TEST_DATABASE_URL` was not configured, so live evidence remains the controlled OZERO run above.

The next active source is KR1, source version `01a088ac-8084-7c59-8b1a-c9bda7ad8208` (29 pages). Its sole
authorized replacement `01a08eac-9094-73c6-b936-3ca9bc2a0044` was claimed by the new scoped worker at
16:14 UTC+12 and had four accepted v13 batches / 48 fragment inputs at the checkpoint, with a live worker
connection to local Qwen. Continue that source to terminal materialization, then schedule KR2 and POS
without duplicating active work. Full-package coverage, reconciled facility dossiers, Tender findings,
normative project checks, source-link browser acceptance, and consultant acceptance remain open.

### Continuation checkpoint — 2026-09-11 16:41 UTC+12

KR1 remains the only running semantic extraction successor
`01a08eac-9094-73c6-b936-3ca9bc2a0044` under worker release `18c6893`. Its durable
v13 ledger records 204 accepted batches / 2,442 accepted fragment inputs, plus one
immutable failed child receipt for 12 input fragments. It has a current lease and a
live worker-to-local-Qwen loopback connection. The source denominator remains 2,960
fragments; this is not candidate persistence or source completion. Do not duplicate
the active successor.

The next structural source KR2 now has exactly one supported queued replacement
`01a08ec5-b223-7f78-8c1c-893ca2bb8eff`, caused by its historical terminal job and
bound to source version `01a088ac-8065-7088-9fe9-298e3848e7ae`. It is queued behind
KR1, not claimed concurrently, so eligible processing will not become idle after KR1.

Commits `c460131` and `e4b2083` are pushed but not deployed. They add the additive
`0046_structure_relationship_candidates` migration and profile v15: Qwen can persist
exact-locator relationship observations (for example, facility-to-pit associations)
without performing a name-only canonical join. The UI/API exposes such observations
as candidates with source links. The same change fixes semantic coverage reporting to
enumerate every active document, including `not_started` sources. A scoped live read
verified the current denominator as 22 documents: 1 complete, 2 partial and 19 not
started. The new release must wait until the active v13 source is terminal; then apply
the additive migration through the controlled release path and qualify one v14 document
worker batch before broader v15 scheduling.

### Continuation checkpoint — 2026-09-11 16:48 UTC+12

KR1 v13 completed at 16:44 UTC+12 with 2,960 accepted inputs and one retained
12-input failed child receipt. Its candidate evidence reached the partial live model:
231 project fields, 486 works, 142 quantities, 68 materials and 274 structural
candidates across the workspace. These are candidates; no facility or pit inventory is
established from them. Its `WORK_QUANTITY_MATERIAL_EXTRACTION` successor is queued at
priority 87 while KR2 uses the single Qwen slot.

KR2 successor `01a08ec5-b223-7f78-8c1c-893ca2bb8eff` is the only active Qwen job. It
has a 21-page source and 600 accepted v13 fragment inputs at this checkpoint. Do not
restart or duplicate it.

Commit `742357b` corrects a relationship-contract error before deployment: pre-v15 accepted
batches are not compatible with a relationship-required profile, because they never
asked Qwen to inspect relationships. They remain immutable candidate evidence but cannot
prove an empty v15 relationship set. Commit `a36ee21` resolves a relationship endpoint
only when exactly one structure candidate with that normalized name exists at the same
evidence locator; all cross-document identities remain unresolved. The prepared v14
Commit `e1c3908` adds `facility` and `local_area` to the v15 candidate vocabulary; this
is required to distinguish LOS/KNS and local sites from generic structures. The prepared
release must use the latest source commit, not the older e4b2083 worktree.

### Continuation checkpoint — 2026-09-11 17:11 UTC+12

KR2 source version `01a088ac-8065-7088-9fe9-298e3848e7ae` completed its v13
semantic input denominator: 1,525/1,525 accepted inputs. Four immutable failed
receipts cover 24 attempt inputs; successful recovery batches supply the accepted
coverage and the failed receipts remain audit history, not a current 24-input
gap. Its source-scoped work/quantity/material, work-package, matrix,
reconciliation, and evidence-index descendants also succeeded.

Commit `1f1575a92d26121227fd762c8f64320446c3e79c` corrects the semantic coverage
query to select the latest activity profile, not the latest profile with an
accepted batch. It exposes failed attempts separately and labels the Russian UI
accordingly. A scoped live read returned all 22 active documents and confirmed
KR1 2,960/2,960 accepted inputs plus 12 failed historical attempt inputs, and
KR2 1,525/1,525 plus 24. This is semantic candidate coverage, not complete
engineering analysis.

The sole supported POS retry `01a08edb-97d7-7ce6-89b8-bd4a518d79c6` was claimed
after the queue drained, then failed without source mutation as
`structured_extraction_evidence_unavailable`. Its receipt proves the old worker
required deterministic page-role decisions before it invoked Qwen, despite
native POS elements being available. Commit
`ce9cd3be3561f3f90e50cb12304f49cf5a38935f` fixes that gating defect: evidence
bound native elements now reach Qwen semantic extraction when page classification
is absent; no-element input still fails explicitly. It also retains Qwen
structure-relationship candidates in the project bundle. Qualification: 64
focused backend tests, scoped Ruff/strict mypy, and frontend format/lint/typecheck/build.

The controlled release is prepared but not activated. A full `pg_dump` using the
configured `asd_public_app` connection fails at `platform_records` permission
denial, so no current recoverable full-database backup exists from this attempt.
No migration and no launchd plist was changed. Database `0046` and the exact
ce9cd3b API/worker/assistant release must not be activated until an already
authorized full-backup/migration connection is supplied or located. Existing
pre-0045 backups preserve older state but do not cover current OZERO extraction
evidence. The next executable action is to use the approved migration-backup
credential/mechanism, take a nonempty consistent backup, apply only additive
0046, switch the three affected services to the pinned ce9cd3b release, and
create one replacement from the new POS failure lineage. Do not rerun OCR or
create another retry before that release.

### Continuation checkpoint — 2026-09-11 17:28 UTC+12

The preceding deployment blocker is resolved. A consistent owner-authorized backup was
created locally before the schema transition (its path and digest are retained in the
restricted operational record), the additive migration head is now
`0046_structure_relationship_candidates`, and API, document worker, and assistant
worker are all pinned to release `13f50af54c61c3847cac285087c9308f9a2fe7be`.
The API readiness check reports PostgreSQL reachable at that migration head. This is a
compatible release set, not Tender acceptance.

The only authorized successor of the failed POS extraction is
`01a08ee8-946f-7cbd-b190-32c8d7af0025`, caused by
`01a08edb-97d7-7ce6-89b8-bd4a518d79c6`, for POS source version
`01a088ac-81c2-7033-8f75-8160ffeb2cb2`. It was claimed at 17:20 UTC+12 by the
pinned document worker. A live loopback connection from that worker to the local Qwen
runtime was observed; the durable v15 batch ledger had 32 accepted batches at 17:27
UTC+12 and continued to advance. The deterministic manifest for this source contains
5,252 exact-layout fragments in 438 bounded batches. Accepted batches are durable
candidate evidence only; project candidates are deliberately persisted after the
complete manifest validates, so no POS facts, facility dossier, or pit count may be
published yet.

Current code confirms the required v15 safeguards: engineering fragments retain
traceable full spans rather than being limited to the classification sampler; standard
engineering requests use a 1,200-token output ceiling and explicitly reject output
exhaustion; all six response collections are mandatory; material quantity and unit are
optional; and same-name work references resolve only by source/fragment/page evidence
or remain durable unresolved observations. Focused engineering semantic tests passed.
Continue the active POS job without interruption, then verify candidate persistence,
version-aware dependent recovery, partial project-view materialization, and evidence
links before scheduling the next eligible source. Full 22-document coverage,
cross-document facility reconciliation, NTD checks, Tender outputs, and consultant
acceptance remain open.

### Continuation checkpoint — 2026-09-11 17:46 UTC+12

### Continuation checkpoint — 2026-09-11 19:14 UTC+12

The POS extraction job `01a08ee8-946f-7cbd-b190-32c8d7af0025` is terminal succeeded
with receipt `01a08f49-d11d-7f8e-b895-e1764c4d6536`. Its immutable v15 ledger has
443 accepted batches for all 5,252 exact-layout manifest fragments. Five invalid
attempt receipts cover 60 attempt fragments; accepted bounded children preserve
effective coverage without erasing those failures. The old persistence profile wrote
299 fields, 494 structural nodes, 148 relationship observations, 478 works, 94
quantities, and 45 materials for POS. These are source-backed candidates only.

A verified consistent backup was made after POS reached terminal state. The controlled
application database is now at `0047_profile_scoped_engineering_candidates`; API,
document worker, and assistant worker import release
`e28da91a57879602f727faedf74acbd9e8fe7adb`, and `/api/v1/health/ready` returns
`ready`. The frontend was rebuilt from that release. The service reload initially
waited for launchd to release SIGTERM'd instances, then succeeded; no source or job
record was rewritten.

Using the supported application repository command as the existing OZERO owner
scheduled 22 profile-aware semantic successors plus one reconciliation job. It reuses
accepted compatible semantic manifests and does not schedule OCR. POS successor
`01a08f4e-3b70-76ff-8245-15626d8da266` is queued with both v15 semantic and candidate
persistence provenance, so it will materialize the exact current profile rather than
mixing generic historical candidates. The single worker is currently processing the
first queued source, `Раздел ПД №12.5 005.2-2025-СМ5_ПИР_pdf.pdf`
(`01a088ac-7f16-73ef-9d2c-3957b2393f66`); it has seven accepted v15 batches / 84
semantic fragments at this snapshot. Twenty-one source jobs and the reconciliation
remain queued. Next action: observe the source to a persisted v15 stage result, prove
candidate profile selection and downstream materialization, then continue the single
worker through all eligible sources. Do not call Tender, facility reconciliation,
normative analysis, or consultant acceptance complete from this checkpoint.

### Continuation checkpoint — 2026-09-11 19:23 UTC+12

The compatible frontend artifact from `de98eaf4f1f535692c6af7d7c712767aa65fdae0`
is live through the e28 API. It makes every returned structural candidate and raw
relationship observation inspectable with explicit incremental display and a
Russian name/kind search; the prior silent first-200 truncation is removed. Frontend
format, lint, TypeScript, production build, and the existing Vitest suite passed.
This is an evidence-navigation improvement only, not facility reconciliation or
browser acceptance.

The active successor for `01a088ac-7f16-73ef-9d2c-3957b2393f66` remains
`01a08f4e-3b54-7dd6-8114-39b798d51740` under the e28 document worker. It has a
fresh lease and 41 accepted v15 batches / 492 accepted fragments with no failed
receipt at this observation. The other 21 source successors and one reconciliation
job remain queued. Next executable action remains terminal observation of this
source, profile-aware candidate persistence and dependent recovery; do not run an
assistant-Qwen request concurrently with this one heavy document workload.

The deployed application boundary now returns a truthful partial OZERO model from
previously accepted source evidence: 291 project-field candidates, 304 structural
candidates, 505 work candidates, 146 quantity candidates, 79 material candidates,
505 provisional work packages, and 154 reconciliation defects across the active
22-source / 2,529-page manifest. The reconciliation is explicitly `partial`; its
gaps include unresolved work mapping, project-field conflicts, missing normative
applicability inputs, and unavailable verified PD/RD rule versions. These values are
candidate evidence and unresolved findings, not a reconciled LOS/KNS/pit inventory or
a complete Tender conclusion.

POS semantic job `01a08ee8-946f-7cbd-b190-32c8d7af0025` remains the sole active Qwen
document workload. At this snapshot its v15 ledger has 119 accepted batches and one
immutable `qwen_engineering_response_invalid_json` parent record. The parent was split
into accepted child batches; it does not invalidate accepted fragments or justify a
document-wide retry. Next: complete this source, verify candidate persistence and
downstream materialization, then continue eligible sources and reconcile facility
identity, project-wide coverage, Tender findings, and grounded consultation.

### Continuation checkpoint — 2026-09-11 19:39 UTC+12

The live document worker remains the pinned `e28da91` release and has one active Qwen
semantic job, `01a08f4e-3b54-7dd6-8114-39b798d51740`, for source version
`01a088ac-7f16-73ef-9d2c-3957b2393f66`. Its scoped durable ledger has 98 accepted
v15 batches / 1,176 accepted fragment inputs and no failed v15 receipt at this
checkpoint. The job has a current lease heartbeat; do not restart or duplicate it.

Commits `c98db6ab964f23d8f4b5123e082ad7738893f920` and
`f533d5c6586448369fe58ae5a9d1de2a91cbac6b` are pushed and qualified but their Python
worker/API changes are not loaded yet. They append a deduplicated, content-free durable
semantic-batch progress event and expose the latest event in the effective job API and
Russian jobs table. The API behavior is regression-tested against 205 historical jobs
and a linked running retry in a disposable PostgreSQL database; the frontend tolerates
an older API response until the compatible service transition. Deploy only after the
active semantic job reaches a terminal state, then prove a fresh worker batch writes and
the application returns current/total progress. This is a processing-visibility repair,
not Tender acceptance or project-model materialization.

### Continuation checkpoint — 2026-09-11 19:54 UTC+12

The completed source `01a088ac-7f16-73ef-9d2c-3957b2393f66` was preserved through
candidate persistence; the workspace remains a **partial** model across 22 active
source versions / 2,529 pages. A controlled safe-boundary release placed the document
worker on `22142e2c2737d97e8bfbdfce22d7e7ef211b2f40` without restarting the loaded
local Qwen runtime. Its new active job
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096` has a 497-batch v15 manifest and durable
content-free `engineering.semantic_batch_progress` receipts (`2/497` at this snapshot).
That is verified worker-to-Qwen processing visibility, not source completion.

The scoped application boundary exposes a partial materialization: six source versions
complete, two partial, fourteen not started; 639 field candidates, 980 work candidates,
246 quantities, 124 materials, 864 structural candidates, and 169 relationship
observations. These evidence-bound candidates have not been reconciled into facilities,
LOS/KNS dossiers, excavation inventory, Tender findings, or consultant answers.
One expired lease from the pre-transition worker remains historical/inflight until the
current bounded Qwen job reaches a claim boundary; do not duplicate it or mutate the
old attempt. Next: let the active job persist its candidate set, verify its downstream
replacement lineage and partial project view, then continue the remaining eligible
source manifest and implement cross-document facility/area reconciliation.

### Continuation checkpoint — 2026-09-11 17:51 UTC+12

The scoped durable read confirms that the POS successor is still `running` under
`document-worker:57884` with a fresh heartbeat. Its v15 ledger has 132 accepted batch
receipts and two immutable failed parent receipts (`invalid_json` and
`invalid_evidence`); the split child receipts required for those parents are accepted.
The deterministic POS denominator remains 438 base batches, so this is in-progress
semantic coverage rather than candidate persistence, source completion, or a Tender
result. The live worker keeps a loopback connection to the local Qwen process; it must
not be restarted merely to inspect progress.

The owner-scoped application boundary was also re-read at this point. It still returns
the same truthful partial model across the 22 active source versions and 2,529 pages:
291 project fields, 304 structure candidates, 505 work candidates, 146 quantities,
79 materials, 505 provisional work packages, and 154 reconciliation defects. No
accepted structure relationships are present yet. Candidate counts and successful
native extraction must not be presented as a reconciled facility/LOS/KNS/pit inventory.
After POS terminal success, the next executable work is to verify its candidate
persistence, replacement-lineage recovery, and project-view materialization before
scheduling the next source; if it terminates unsuccessfully, inspect only the exact
failed batch lineage and recover the bounded input.

### Continuation checkpoint — 2026-09-11 23:57 UTC+12

The POS source and the later СМ3 source have both reached durable terminal success;
their dependent work/package, matrix, reconciliation, and evidence-index stages ran.
The live database is now at additive migration
`0048_incremental_reconciliation_claim_priority`. Its claim policy was exercised on
the real queue: incremental reconciliation `01a08fce-76c0-7cb9-97bd-3b1236718625`
was claimed and succeeded before further source inference. A non-empty current
owner-authorized PostgreSQL backup was made immediately before that migration in the
restricted operational backup store. Runtime command commit `11a37bb14aacef91c779cb9f4accf4ccc4753ecb`
also repairs the migration wrapper so it supplies Alembic's mandatory explicit
database URL; its focused unit test, Ruff, and strict source mypy pass.

The sole live Qwen workload is currently source `01a088ac-7fdb-7b12-be33-e3a325af8edf`
(`Раздел ПД №12.2 005.2-2025-СМ2. Изм.3.pdf`), job
`01a08f4e-3b5e-798c-9d5b-b3acd1724683`. The document worker has a live loopback
connection to Qwen, and sampled Qwen execution shows MLX Metal kernels, not a CPU-only
fallback. It must continue without interruption. A different pre-restart СМ5 lease,
`01a08f4e-3b5d-713f-b1f8-9feb58a7a565`, is expired with no live executor; retain it as
historical lineage and recover it through the durable lifecycle only after the active
request reaches a terminal boundary. Do not mark it successful or create a duplicate
active source attempt.

The latest materialization remains explicitly `partial`: it covers the active 22
source versions / 2,529 pages as an intake denominator, not complete semantic
analysis. It holds 5,131 accepted candidate observations, 1,080 unresolved candidate
observations, 357 open reconciliation defects, and source-backed candidate nodes
(including 65 pit-labelled nodes). Those are neither deduplicated facility dossiers
nor an established pit inventory/count. Next: observe the active СМ2 terminal result,
verify its candidate persistence and incremental materialization, then continue the
eligible corpus while implementing version-aware recovery of the expired СМ5 lease and
cross-document facility reconciliation.

### Continuation checkpoint — 2026-09-11 21:45 UTC+12

The live worker release is the pinned `75666044b2598bffaa5418f40cc830f36cd773b6`
worktree, not an assumed GitHub branch head. The active OZERO semantic job
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096` remained `running` under
`document-worker:74713` at 21:44 UTC+12 with a fresh heartbeat and durable progress
350/497. Its worker had an established loopback connection to the Qwen runtime. This
is progress through a per-source batch manifest only, not semantic completion or a
Tender finding.

The owner-scoped `start_project_understanding` command was executed once through its
supported repository contract while that source continued. It did not create a second
attempt for the running input. It persisted queued reconciliation
`01a08fd8-5866-7a9d-9697-6e74e32dc94e` and reprioritized only compatible queued
semantic jobs: ten are now priority 170 (including PZU and KR sources), eight remain
priority 130 pending stronger role evidence. The document worker must be allowed to
finish the active source; then verify candidate persistence and the priority-165
incremental reconciliation before asserting any user-visible facility or pit result.

### Pending controlled release — 2026-09-11 21:53 UTC+12

Isolated commit `83fe4c9dbf2ac6e758c4914ea867e54b5b893a6d` corrects a demonstrated
publication-order defect: an incremental reconciliation is a bounded database-only
materialization and must run at priority 175, ahead of queued Qwen source extraction,
so a completed source is visible before unrelated sources start. It does not invoke
inference or alter source candidates. Ruff/format/strict mypy pass; the focused
PostgreSQL integration case is environment-skipped and is not acceptance evidence.

The live worker was sent its supported graceful TERM request while it was processing
the active 497-batch source. Its signal handler retains the source lease and Qwen
request until that source has a terminal outcome, then stops before claiming another
job. Do not overwrite the release worktree or restart the worker before that boundary.
After terminal verification, cherry-pick `83fe4c9` into the pinned release, run the
targeted checks, restart only the document worker, and verify the priority-175
materialization produces a current partial model before the next Qwen source is
claimed.

### Continuation checkpoint — 2026-09-11 21:09 UTC+12

The controlled database is at `0047_profile_scoped_engineering_candidates`. API
release `8159206681f681ed84a3807c9b09120e90461d07` is healthy and imports its
explicit release worktree. The document worker imports that same worktree, although
its launchd environment label still says `22142e2`; treat the label mismatch as a
release-manifest repair to make only at a safe worker boundary, not as evidence of a
different executing code path.

The only live Qwen document execution is
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096`, for the active 121-page source version
`01a088ac-7f97-761a-b857-f5d3b4c5be8b` (`Раздел ПД №12.3 005.2-2025-СМ3. Изм.3.pdf`).
It has 5,957 native evidence locators and its v15 semantic job has a fresh lease,
durable base progress `309/497`, 3,672 accepted fragment inputs, and 135 input
fragments represented only by immutable failed-attempt receipts. The local Qwen
process has a live loopback connection from the worker; do not restart it or create a
second successor while this job runs.

An earlier v15 job for a different source is visibly `running` with an expired lease
owned by a no-longer-running worker process. The deployed effective-jobs UI exposes
this as an unavailable executor rather than live progress. Its replacement must be
claimed through the existing durable claim function at a safe serial worker boundary;
do not update its row manually or run a competing Qwen job.

The owner-scoped current candidate ledger contains 684 project fields, 1,156 works,
281 quantities, 124 materials, 864 source-scoped structure observations, and 169
relationship observations. These remain candidate evidence. They do not establish a
cross-document LOS/KNS/facility inventory, pit count, Tender finding, or consultant
acceptance. Browser-based UI acceptance is unverified because no in-app browser
binding is currently available.

The next worker plist is now staged with that same exact `8159206` release identity
and a recoverable pre-change copy is retained in the restricted release record. The
loaded worker was not restarted and still correctly reports its prior `22142e2` label;
the changed plist only takes effect at a later safe boundary. A new live observation
after the configuration write confirms the semantic job lease and worker PID remain
unchanged and fresh.

### Continuation checkpoint — 2026-09-11 18:08 UTC+12

The active POS job remains `running` under the pinned `13f50af` worker. Its Qwen v15
ledger has 186 accepted batch receipts and two immutable failed parent receipts; the
worker-to-Qwen loopback connection is established and the model process is active. No
restart or replacement was performed while that request is in flight.

Feature release `aa16603` is pushed and qualified, but not deployed. It changes the
existing project-model command into a safe semantic-recovery scheduler: for every
active source with persisted, nonempty native layout it queues one profile-explicit
v15 `PROJECT_DEFINITION_EXTRACTION` successor only when no active or completed v15
stage already exists. It uses the active document-version decision rather than all
historical versions, preserves terminal predecessors through `causation_id`, and
records the scheduled semantic inputs in the reconciliation digest. A PostgreSQL
regression test proves that repeated user commands do not duplicate the recovery job.
Focused integration tests (5), Ruff, formatter, and strict mypy pass for that release.
Once POS is terminal, release `aa16603` may be activated without a migration; then the
existing model action will schedule the remaining native-readable active sources while
leaving sources without native layout explicitly uncovered for the Qwen visual path.

### Continuation checkpoint — 2026-09-11 18:32 UTC+12

The sole active Qwen workload remains POS job
`01a08ee8-946f-7cbd-b190-32c8d7af0025`, with a current worker heartbeat and no typed
failure. Its v15 durable ledger contains 339 accepted recovery/batch receipts covering
4,032 exact fragment inputs, plus three immutable failed parent receipts; accepted
children exist for the observed bounded recoveries. The base manifest denominator is
still 438 batches / 5,252 fragments. This is active semantic processing only, not
complete source coverage, candidate publication, object reconciliation, or Tender
acceptance. Do not restart the worker or create another POS job.

Release candidate `892335ccc93218f5beddd33109b1297d363c2282` is pushed and prepared
in isolated worktree `/Users/oleg/asd-kontur-pilot-release-892335c`, but not deployed.
It contains additive migration `0047_profile_scoped_engineering_candidates`. It scopes
Qwen fields, works, structures, relationships, and extraction defects to the exact
semantic profile, filters active project assembly/UI candidates to the latest completed
profile per active source, exposes the profile in the API, and requires both profile
provenance and a complete immutable stage receipt before a source can suppress a
successor. The new release can deterministically reassemble already accepted v15 POS
batch manifests into profile-scoped candidate identities without rerunning Qwen or OCR.

Focused Qwen semantic unit tests, the PostgreSQL scheduler/profile-isolation integration
tests, Ruff, formatter, and strict mypy pass. After POS reaches a terminal receipt: take
the already-required recoverable backup, migrate only 0047, switch API/document worker
to this pinned worktree, then issue one supported project-understanding command. Verify
that the POS successor reuses its accepted batches, persists candidates under v15,
recovers the dependent model path, and appears correctly in the deployed API before
scheduling the remaining corpus. Full 22-document coverage, facility dossiers, NTD
checks, Tender findings, pit inventory, and consultant acceptance are all still open.

### Continuation checkpoint — 2026-09-11 20:19 UTC+12

POS is now terminal and its version-aware dependent stages completed. Its v15 semantic
coverage is 5,252/5,252 accepted source fragments, with five immutable failed-parent
attempts covering 60 inputs whose accepted bounded children supply the coverage. The
source persisted 299 field, 478 work, 94 quantity, 45 material, 494 structural, and
148 relationship **candidates**. Those records remain evidence-bound candidates, not
reconciled facilities, project facts, or a pit inventory.

The workspace view remains partial across 22 active sources/2,529 pages: 6 sources
complete, 2 partial, and 14 not started. Its selected compatible candidate collections
currently contain 639 fields, 980 works, 246 quantities, 124 materials, 864 structural
nodes, and 169 raw relationship observations. Materialization gaps and unqualified
normative inputs remain visible; no Tender or consultant acceptance is claimed.

The sole live Qwen document workload is source `01a088ac-7f97-761a-b857-f5d3b4c5be8b`
(`Раздел ПД №12.3 005.2-2025-СМ3. Изм.3.pdf`), durable job
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096`. It had 72/497 accepted batches at the
observation. An older job held by dead worker `document-worker:69134` has an expired
lease and no semantic progress; it remains immutable historical state and will be
recovered only through the supported claim protocol.

Release `bb7c86743e8324fa5b7c808bca7fd7ce29d08945` is live for API/frontend at
migration `0047_profile_scoped_engineering_candidates`. It marks expired leases in the
effective processing view instead of presenting them as active. Assistant worker
release `f42cbcd00969bd19de7aba529d53b761683a6e85` is live and makes structured
work-package, matrix, discrepancy, and information-gap tools cite their own exact
workspace locators rather than unrelated overview candidates. The document worker and
local Qwen process were not restarted. Next: keep the active source running, validate
its candidate persistence and downstream materialization when terminal, then proceed
source-by-source with facility reconciliation and Tender acceptance.

### Continuation checkpoint — 2026-09-11 20:25 UTC+12

API/frontend release `3c64021bc720f0a0e56172945d1a3be63a0ffdd6` is now live and ready
at migration `0047_profile_scoped_engineering_candidates`. The project page no longer
silently drops candidate works, quantities, or materials after the first 100: it offers
Russian local filtering and explicit incremental display while preserving candidate
status and exact evidence links. Assistant worker `f1d9e453981f7b352856365719b15479f044c072`
adds explicit 22-source semantic coverage and candidate-only counts to its workspace
overview, so an incomplete corpus cannot be treated as an exhaustive inventory.

The active Qwen source is still the same estimate document/job and had 102/497 accepted
batches at this observation. There is no browser attached to this Codex session, so
browser acceptance remains unverified; the deployed API readiness and bounded
application/repository reads pass. Keep the single document Qwen workload uninterrupted.

### Continuation checkpoint — 2026-09-11 20:35 UTC+12

The only Qwen document workload remains the same v15 semantic extraction job
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096` for source version
`01a088ac-7f97-761a-b857-f5d3b4c5be8b`. A scoped durable read recorded a current
worker heartbeat and lease, 198 accepted batch receipts covering 2,304 exact input
fragments, and six immutable failed parent receipts covering 66 fragment inputs. No
replacement was scheduled and no worker or Qwen process was restarted. Accepted child
receipts may cover failed-parent inputs, so the 497 base-batch workload counter is not
by itself semantic coverage; the source coverage projection remains the publication
authority.

The current API/frontend release is `4de01ae25088b79d0b16f9f9d3ed8fb147531ddd` at
migration `0047_profile_scoped_engineering_candidates`; the document worker still runs
the previously pinned `22142e2c2737d97e8bfbdfce22d7e7ef211b2f40` release. Commit
`4ee4f6c` is contained in the API release but its document-worker reconciliation behavior
has deliberately not been activated during the live Qwen request. It makes raw,
profile-scoped structural candidates and relationships participate in a fresh
reconciliation fingerprint and exposes `STRUCTURE_CANDIDATE_RECONCILIATION_PENDING`;
it does not manufacture canonical facilities, a pit inventory, or Tender findings.

Next executable action: observe this source to a terminal receipt. At the safe Qwen
boundary, verify its candidate provenance and replacement lineage, transition the
document worker to the pinned compatible release, invoke only the supported source
downstream recovery, and inspect the refreshed application model before scheduling the
next eligible source. Cross-document facility reconciliation, package-wide coverage,
NTD project checks, Tender findings, and consultant/browser acceptance remain open.

### Continuation checkpoint — 2026-09-11 21:23 UTC+12

The active Qwen source/job is unchanged and remains healthy: durable job
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096` has a fresh
`document-worker:74713` lease and 326/497 accepted batch-progress units. It must reach
a safe terminal receipt before any worker restart. The local Qwen3.8 process is the
only heavy model process and has not been interrupted.

The worker's durable claim function orders equal work by `priority DESC, created_at,
job_id`. Scoped evidence established that the pending source semantic jobs were all
priority 130 even where durable `document_role_decisions` identify
`drawing_or_scheme`, `project_documentation`, or `working_documentation`. This delayed
multidisciplinary structural/site/technical evidence behind estimates.

Feature release candidate `7c819d09d9fcc756a8a9c0f7eadea1e1fd89a669` is pushed to
`implementation/ntd-canonical-memory-build-01`; it is not deployed. It derives bounded
fair dispatch priorities from persisted roles (170 structural/drawing/project,
160 explanatory/specification, 150 BoQ/estimate, 130 unclassified), records an auditable
`job.priority_recomputed` event for compatible queued passes, and leaves running leases,
input manifests, candidate authority, and history unchanged. Focused Ruff, strict mypy
for the changed adapter, and three unit tests pass. The PostgreSQL integration test is
skipped because this checkout's integration database fixture is unavailable; deployment
requires an application-boundary check before release.

Next executable action: at the active job's terminal boundary, deploy the pinned worker
release including this scheduling repair, issue the supported workspace-understanding
command to re-evaluate queued source priorities, verify a classified structural/site/
technical source is claimed ahead of lower-tier estimates, and then continue source
candidate persistence and model materialization. Do not claim facility dossiers, pit
inventory, Tender analysis, or consultant acceptance yet.

### Continuation checkpoint — 2026-09-11 21:37 UTC+12

Release `43b2ac1f22938014db5ee53645983693a0f41482` is pushed and present in the
pinned release worktree but is **not yet executed** by the document worker. It combines
the role-based fair source scheduler and an incremental project-reconciliation trigger.
After a successful `PROJECT_DEFINITION_EXTRACTION`, the worker will queue one
idempotent, causally linked reconciliation at priority 165. It materializes only
profile-selected completed source candidates, so partial evidence becomes visible before
the full corpus drains; it neither confirms candidates nor merges cross-document names.
The implementation passed Ruff and strict mypy; PostgreSQL fixture integration is
available in CI but skipped in this checkout, while a rollback-only scoped OZERO
transaction independently proved the real insert, idempotency, causation, and priority.

The current v15 source job is still active and must be allowed to finish before the
worker is restarted. At the latest observation it had 338/497 accepted progress units;
the local Qwen process remains the sole heavy model workload. Next executable action:
on terminal receipt, safely restart the worker onto `43b2ac1`, verify the existing
source's candidate persistence, then observe the incremental reconciliation and the
role-prioritized next source through the actual API. Full package coverage, facility
identity reconciliation, project-specific NTD findings, Tender outputs, and consultant
acceptance remain open.
### Continuation checkpoint — 2026-09-11 22:29 UTC+12

The active Qwen v15 source remains `01a088ac-7f97-761a-b857-f5d3b4c5be8b`
(`Раздел ПД №12.3 005.2-2025-СМ3. Изм.3.pdf`), job
`01a08f4e-3b5b-7851-9f3d-fcaf3e84c096`. It is held by
`document-worker:74713` with a fresh lease and has progressed to 393/497 base
batches. The local loopback Qwen3.8-27B process is the only model workload and
the worker has a live connection to it. At this observation, the immutable batch
ledger contains 420 accepted outputs and 36 failed parent receipts; parent failures
are not a coverage count because accepted bounded descendants may recover them.

Do not interrupt this source. A Codex-authored, un-deployed scheduler correction is
prepared in isolated commit `a98bbc3`: migration 0048 makes the durable claim function
choose an explicit incremental project-reconciliation job before unrelated semantic
inference. This covers already-persisted priority-165 incremental jobs as well as
future priority-175 jobs, without modifying job lineage or using a direct database
priority update. Ruff format/check and strict mypy pass; the focused PostgreSQL test is
environment-skipped and must be exercised against the controlled release database
before it is accepted. At source terminal: inspect its stage result and candidates,
then integrate, migrate, and restart only the document worker through the controlled
release procedure; verify the reconciliation is claimed before any next Qwen source.

No facility inventory, excavation-pit total, NTD project finding, Tender acceptance, or
consultant acceptance is established by this checkpoint.

### Continuation checkpoint — 2026-09-12 00:14 UTC+12

The active semantic job is now `01a08f4e-3b5e-798c-9d5b-b3acd1724683` for source
`01a088ac-7fdb-7b12-be33-e3a325af8edf` (`Раздел ПД №12.2 005.2-2025-СМ2. Изм.3.pdf`).
It is held by `document-worker:5939`; at the recorded observation it had accepted
57 of 1,074 legacy v15 batches. The Qwen3.8-27B MLX process is the only heavy model
workload. The accepted receipts are partial candidate evidence, not complete semantic
coverage, a reconciled facility inventory, or a Tender result.

Feature release `2b48e05f4d19de12d2cbd5d9e17881d80ddc5e79` is pushed to
`implementation/ntd-canonical-memory-build-01` and staged in
`/Users/oleg/asd-kontur-pilot-release-2b48e05`; it is not deployed. It retains
byte-identical legacy manifests whenever any accepted v15 batch exists, and gives
only a previously unstarted source an explicit, digest-recorded
`dense-fragments-v1` 48-fragment packing policy. It does not change the Qwen prompt,
candidate schema, or extraction-profile version. Focused format/check, strict mypy,
and 51 document-understanding unit tests passed. No migration is required.

Next executable action: allow this active source to terminally persist or fail under
the existing release; then verify its receipt and candidate provenance, make a fresh
recoverable database backup, and perform the controlled worker transition to the
pinned release. Confirm that a new, unstarted eligible source receives dense manifests
and that a source with accepted legacy batches is resumed without duplicate Qwen work.
Continue then with all active OZERO sources, reconciliation, project model, Tender
analysis, NTD evaluation, and grounded consultant acceptance.

### Continuation checkpoint — 2026-09-12 00:20 UTC+12

Release `53cafdf` is pushed but not deployed. In addition to the explicit dense
policy, it publishes deterministic, source-backed fields, structure observations,
exact-locator relationships, and work observations immediately after an engineering
batch receipt is accepted. On a restart it safely backfills those partial candidates
from exact v15 batch manifests without another Qwen call. The project-view profile
selection now includes accepted batch receipts, so these entries can be displayed as
partial candidates before a source's terminal stage result exists. Quantities and
materials that need a cross-batch work identity remain in their immutable receipt
until the complete-source reconciliation resolves or preserves the relationship.

This is a partial-publication mechanism, not a facility identity merger, an authority
promotion, or a complete Tender model. Focused format/check, strict mypy, and 53 unit
tests passed. The release has not yet been exercised through PostgreSQL with the
application repository or deployed, and the active old worker must not be interrupted
while it owns the current Qwen request.

### Continuation checkpoint — 2026-09-12 00:25 UTC+12

The pending exact release is now `de7f4033e35ce8d6af1e3d5f26b11c6ac5c5dd9f`, staged
at `/Users/oleg/asd-kontur-pilot-release-2b48e05`. It corrects partial publication so
coverage is expressed by the source/batch state rather than being frozen into an
otherwise identical field candidate by `ON CONFLICT DO NOTHING`. The staged
application repository was read against the correctly scoped OZERO database: its
profile-selection queries returned the existing candidate projection (1,824 fields,
1,080 works, 342 quantities, 160 materials, and 1,308 structural observations) without
raising SQL or RLS errors. These are candidate-observation counts, not facility totals,
confirmed facts, or a completeness claim.

The active old-worker source remains running and has 89/1,074 accepted v15 batch
progress units at the recorded observation. Do not restart it merely to activate the
partial-publication release. At its terminal boundary, first capture its terminal
receipt/provenance and current candidate projection, create a fresh recoverable backup,
then deploy the pinned compatible API/worker/assistant release and exercise the real
partial-state API/UI path before allowing a newly unstarted source to claim dense work.

### Continuation checkpoint — 2026-09-12 00:51 UTC+12

The API/frontend alone were moved through a controlled, recoverable release to
`6194eb31fd82630b136dd0f404252b532a8cae44` at database migration
`0048_incremental_reconciliation_claim_priority`. An isolated loopback process and
the activated API readiness route both returned `ready`. The API now exposes accepted
v15 batch receipts as exact-locator partial candidates. A launchd registration failure
was recovered from a preserved plist before activation; it did not change OZERO rows,
source objects, receipts, or workers.

The Qwen document worker was not restarted. Job
`01a08f4e-3b5e-798c-9d5b-b3acd1724683` for source
`01a088ac-7fdb-7b12-be33-e3a325af8edf` remains running with durable `127/1074`
accepted-batch progress. The current exact coverage is 22 documents / 2,529 pages /
133,407 fragments: 7 complete, 3 partial, 12 not started; 24,499 accepted input
fragments and 888 historical failed-attempt inputs. Candidate evidence remains
candidate-only and cannot establish a facility inventory, pit count, Tender finding, or
consultant answer. Next executable action: wait for this job's terminal receipt, then
validate its candidate/dependency lineage and move the worker at that safe boundary to
the matching release before continuing the remaining eligible sources.
