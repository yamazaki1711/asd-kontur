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
evidence. The active v4 retry `01a08e02-1fba-7e43-b1f3-5f2371f65d52` is the sole effective attempt;
it has persisted accepted v4 batches but has not yet reached candidate persistence or project
materialization. No project-wide result is accepted from it.

The committed UI/API coverage surface reports accepted semantic fragments separately from classified
pages and from reconciled facts. It is not yet deployed with the corresponding API/frontend release.

Next executable action: allow the sole v4 attempt to complete without duplication; inspect its immutable
batch/candidate receipts. Then release the already-migrated `b88507e` worker, recover only the blocked
downstream stages through the verified replacement lineage, and verify workspace assembly before
scheduling the next eligible active source. Do not leave the OZERO queue empty while eligible sources
remain.
