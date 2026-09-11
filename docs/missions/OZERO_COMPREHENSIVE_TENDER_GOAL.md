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
