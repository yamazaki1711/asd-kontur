# WP-14 Audit Slice v0.1

**Status:** implementation complete on synthetic evidence; canonical CI evidence
is recorded before merge. **ProductReady:** `false`.

## 1. Scope and boundary

WP-14 implements a universal workspace-scoped acquisition/corpus capability and
the first strict consumer of it: Audit. It is object-independent and is not an
automation of Levashovo. Historical reports remain practical, partial evidence;
no further disk research, remote mounts or project-document processing was
performed.

The implemented path is:

```text
collection → admission/inventory → original object ledger
→ deterministic technical preflight → native/page-aware planning
→ bounded shards/attempt receipts → boundary validation
→ exact reconciliation → CorpusSnapshot
→ Document Delta + Causal Readiness Delta + Package/Signing/Handover Readiness
→ evidence-rated AuditReport and rebuildable projections
```

The common `asd_kontur.corpus` package is available to Tender, Support, Audit
and Restoration `ModeExecution`. Audit does not own another object ledger,
source identity, VLM harness or database.

## 2. Acquisition and corpus model

The typed model contains `CollectionMission`, versioned `CollectionScope`,
`CollectionSource`, `PhysicalLocation`, `MediaSource`, `AcquisitionBatch`,
`CollectedItem`, `CustodyReceipt`, `PhysicalObjectInspection`, one-based
`PageInspection`, `ProcessingPlan`, `ProcessingShard`, immutable
`ProcessingReceipt`, `BoundaryCandidate`, `BoundaryValidation`,
`LogicalDocumentOccurrence`, `CorpusReconciliation`, `UnresolvedCorpusItem`,
`CorpusCoverage` and immutable `CorpusSnapshot`.

A path, disk, folder or box is provenance/locator only. A SHA-256 digest proves
byte equality but grants neither source identity nor access/authority. Organized
and chaotic inputs use the same mission and object ledger. Unknown locations or
incomplete acquisition become scoped gaps; `CorpusSnapshot` explicitly sets
`claims_complete_oks=false` and describes only the observed collection scope.

## 3. Technical preflight and huge containers

`inspect_pdf` hashes in 1 MiB chunks, checks PDF magic, encryption/readability,
page count/boxes/rotation, native text, raster objects, embedded attachment and
signature claims, and anomalous dimensions before any provider call. It accepts
a path and does not call `Path.read_bytes`; page text extraction can be limited
to an explicit sample.

The deterministic planner accepts inspection metadata without materializing the
source. The synthetic 360 MiB/726-page raster stress profile is split into 73
bounded ten-page shards. If external qualification and egress are both allowed,
the pages are merely `external_eligible`; no call is made. Without that exact
authorization the route is `deferred`. Sensitive/contract/legal data is never
made external-eligible by local capacity failure. Native and mixed pages in the
same container can take different routes.

The constants in tests are explicit development policy values, not production
budgets. G-07B, production egress, provider terms and real Polza/Qwen execution
remain `BLOCKED`.

## 4. Page, shard, retry and reconciliation

Pages are one-based and each shard contains an exact page list, route, output
contract and idempotency identity. Overlap is processing context only; logical
boundary reconciliation rejects gaps/overlaps and never duplicates a page in a
logical result. Resume selects only pages not already validated by the same
immutable plan.

Reconciliation compares expected pages with exact receipts and distinguishes
`complete`, `partial`, `blocked`, `unresolved`, `provider_failed`,
`recovery_required` and `quarantined`. Missing receipts and unknown outcomes are
unresolved; all-page failure is `provider_failed`; duplicate receipts require
recovery. Empty expected pages cannot be complete. Retry cannot erase successful
receipts or create a silent empty result.

## 5. Physical containers and logical documents

The physical chain reuses `workspace.objects`, `SourceArtifact`, `SourceVersion`
and `SourceLocator`:

```text
PhysicalObjectVersion → container SourceVersion → PageManifest
→ BoundaryCandidate → BoundaryValidation
→ LogicalDocumentOccurrence → exact SourceLocator page range
```

Confidence is stored only as candidate metadata. A boundary is accepted only
with evidence receipts, deterministic validation and an authority decision.
PostgreSQL prevents creation of a logical occurrence unless its exact boundary
validation is accepted. Uncertain ranges remain unresolved segments.

## 6. Audit deltas

Audit consumes an exact `CorpusSnapshot` and produces three independent,
immutable results:

1. `DocumentDelta`: required/found/recognized/classified/versioned/
   evidence-bound/applicable states;
2. `CausalReadinessDelta`: MTR/batch → incoming control → admission → work →
   evidence → ID → PresentedVolume → KS → payment;
3. `PackageReadiness`: package/volume/book membership, order/copies/register,
   professional review, signer authority, signature, handover and acceptance.

Each has an independent versioned denominator, exact scope, pinned
`RuleSetVersion`, evidence, conflicts/uncertainties/blockers, downstream impact
and RFC 8785/SHA-256 fingerprint. No API computes a combined readiness
percentage. Found or classified files, generated candidates, folder counts,
confidence and KS entries do not create readiness or Fact.

`ActionRequest` separates initiator, addressee/executor and independent verifier;
verified closure requires remediation evidence and an identified executor.
Reclassification appends a `ClassificationVersion`, reruns the exact validator
profile and remains not ready while type-specific attributes or authority are
missing. Last-write-wins is absent.

## 7. Customer and PTO projections

`CustomerAuditProjection` exposes collection/processing counts, independent
document/package states, causal blockers, denominator provenance and freshness.
`PtoAuditProjection` exposes unresolved items/pages, typed ActionRequests and
readiness blockers. Both are deterministic rebuilds over canonical fingerprints;
they cannot mutate source, package or action state.

## 8. Persistence, authority and lifecycle

Alembic revision `0008_wp14` follows `0007_wp13`. It creates one immutable
platform processing-profile family and workspace relations for collection,
preflight, pages, plans/shards/receipts, boundaries/occurrences, reconciliation,
snapshots, all three deltas, package membership, ActionRequests,
classification, reports and projections.

Every workspace relation has mandatory `organization_id` and `workspace_id`,
composite foreign keys, `ENABLE RLS`, `FORCE RLS`, transaction-local scope,
lifecycle write-fence triggers, immutable history and explicit destruction-role
policies. The non-owner `asd_audit_service` receives narrow grants. Mutable
mission/process headers require `asd.audit_operation_id` and an exact
`revision + 1`; version records reject UPDATE/DELETE. Audit processes require an
Audit `ModeExecution`; collection missions deliberately support all four modes.

`PostgresCorpusAuditStore` is a narrow typed writer for inspections, plans,
reconciliation, snapshots and document deltas; no arbitrary-SQL repository is
exposed. Accepted process transitions have typed event names; rejected or stale
commands return no domain event. Existing append-only audit, idempotency and
outbox relations remain the shared infrastructure.

The G-06 `PostgresWorkspaceStorageAdapter` exact allowlist includes every new
workspace relation in dependency-safe order. Exact synthetic purge evidence
shows workspace A rows disappear while workspace B and platform processing
profiles remain. No schema truncate/drop or cascading whole-workspace delete is
introduced.

## 9. Contract Pack

`contracts/v1.4` is an additive immutable Draft 2020-12 extension preserving
v0.1–v1.3. It defines collection mission, physical inspection, page manifest,
processing plan/shard/receipt, boundary candidate, reconciliation,
`CorpusSnapshot`, Audit delta and report records. Its fingerprint is checked
against exact bytes. Negative fixtures reject empty-complete reconciliation,
complete snapshots with unresolved items, confidence-based Fact/authority and
`ProductReady`.

## 10. Verification evidence

Only generated/synthetic object-independent data is used. The suite covers:

- organized and chaotic intake through one model;
- streaming/path preflight and mixed-page routing;
- 360 MiB/726-page metadata planning without a large binary fixture;
- external default-deny, sensitivity and bounded sharding;
- page resume, partial/all-failed/unknown/duplicate receipt reconciliation;
- boundary range/evidence/authority, gap and overlap checks;
- exact snapshot prerequisite and three independent delta fingerprints;
- false signed-readiness, missing evidence/downstream impact, reclassification,
  ActionRequest SoD and projection rebuild;
- PostgreSQL 17 clean migration, RLS/FORCE RLS, default deny, A/B isolation,
  shared four-mode collection, immutable/optimistic headers, lifecycle fence,
  exact deletion inventory and `0008 → 0007 → 0008` disposable round-trip.

Local gate evidence on 2026-08-23: `uv lock --check`, Ruff format/lint and
strict mypy passed; the complete suite passed as `258 passed` against disposable
PostgreSQL 17. The v1.4 registry fingerprint and all positive/negative fixtures,
Markdown relative links, whitespace and publication-safety scans also passed.

Canonical PostgreSQL 18 + pgvector workflow evidence is recorded in the PR and
final gate update. Test count is supporting evidence, not the acceptance reason.

## 11. Rollback and risk

Production downgrade is fail-closed; disposable downgrade requires
`ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1`. Rollback is a new plan/snapshot/delta
version or quarantine/reconciliation, never mutation of prior evidence.

Residual risks/blockers:

- G-07B external/distributed route and production provider qualification;
- production processing budgets, egress policy, terms, encryption and cost;
- real large-corpus qualification and real professional Audit authorities;
- production rendering/signature verification and physical handover adapters;
- G-02B, WP-15 Restoration and cross-mode ProductReady acceptance.

## 12. Gate self-check

WP-14 is accepted only as a synthetic/disposable implementation slice when
AT-PE-43, local PostgreSQL and canonical CI are green. It does not assert legal
impossibility, restore missing evidence, qualify a provider or make the product
ready. The sole next work package is WP-15 Restoration Slice.
