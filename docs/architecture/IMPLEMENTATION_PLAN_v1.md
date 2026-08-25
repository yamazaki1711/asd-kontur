# Implementation Plan v1

## Delivery policy

One active delivery slice advances the complete Product Capability Registry.
Infrastructure micro-gates cannot displace the product path. Every capability
stream ends in a visible professional result with source/evidence, blockers,
recovery and export—not a test-count claim.

## Completed prerequisite

`MEMORY-INTEGRITY-FIX-01` resolved the two canonical memory defects and passed
three final consecutive clean-room cycles. The historical defect and failed
series receipts remain immutable. This bounded PASS does not change product
readiness.

## Completed bounded slice: PRODUCT-APPLICATION-SPINE-01

Purpose: establish the minimum user-operable application boundary without
claiming any mode ready.

### Deliverables

1. Python application package with FastAPI candidate qualification, versioned
   OpenAPI, command/query ports and generated TypeScript client.
2. React/TypeScript/Vite shell with authentication, workspace selector,
   four-mode navigation and no demo/fallback domain data.
3. Server-side opaque sessions, CSRF, authorization and workspace/RLS negative
   tests.
4. Workspace lifecycle screens: create/admit, view, archive/export,
   reset/destroy confirmation and receipts.
5. Recursive folder and bounded batch upload with streaming hash, MIME/content
   checks, deduplication, quarantine and document registry.
6. PostgreSQL DurableJob table/worker: leases, outbox/inbox, progress SSE,
   pause/resume/cancel/retry, idempotency and reconciliation.
7. PDF.js document viewer with virtualized pages, source/region navigation and
   evidence side panel.
8. Empty but functional Tender/Support/Audit/Restoration workspaces that show
   honest prerequisites/gaps and never fake results.
9. Read-only Platform Knowledge and operational status surfaces.
10. UI E2E for restart recovery, isolation, no-result, blocker, evidence
    navigation and destructive confirmation.

### Explicit non-goals

No real OKS, product-scale claim, complete mode, new NTD acquisition, CAD
intelligence, G-07B or legacy code copy. Dependencies are pinned only after the
[technology ADR](decisions/0014-product-application-technology-baseline.md) and
[Legacy Gate](LEGACY_COMPONENT_DECISION_MATRIX_v1.md).

### Terminal condition

The Spine ended with selected application/interaction/intake foundations and
their capability E2E. It may advance individual capabilities to
`CAPABILITY_READY`; it cannot set ModeReady, TrialReady or ProductReady.

## Next slice: INDUSTRIAL-DOCUMENT-UNDERSTANDING-01

Purpose: turn admitted ПЗ/ПД/РД/ВОР/estimate documents into an evidence-bound,
visible project model without changing memory integrity or claiming a ready
mode.

`admitted documents → document/page classification → ProjectDefinition → OKS
structure → work/quantity/MTR candidates → ConstructionWorkPackages →
WorkRequirementMatrix → visible evidence-bound UI result`.

This slice starts only after MEMORY-INTEGRITY-FIX-01 is merged. It must use the
existing Product Application Spine, durable jobs, workspace isolation,
Knowledge Gateway and exact locators. It does not authorize a real OKS,
recursive NTD acquisition, CAD/Drawing Intelligence or external VLM routing.

## Subsequent streams

1. Industrial Intake scale and Project Understanding;
2. applicable official NTD, RuleVersion and work-type coverage;
3. Tender professional outputs R1/R2;
4. Support production ID/control/output chain;
5. Audit full operator report workflow;
6. Restoration dedicated non-fabricating workflow;
7. Drawing/CAD/output R3 and field/offline;
8. operations/scale and Trial Readiness;
9. four ModeReady decisions and product acceptance.

Each stream updates the same registry and cannot remove a denominator.
