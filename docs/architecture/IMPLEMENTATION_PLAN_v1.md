# Implementation Plan v1

## Delivery policy

One active delivery slice advances the complete Product Capability Registry.
Infrastructure micro-gates cannot displace the product path. Every capability
stream ends in a visible professional result with source/evidence, blockers,
recovery and export—not a test-count claim.

## Active product-led delivery policy — 2026-09-19

**Programme objective:** production-quality ASD-KONTUR for Tender, Support,
Audit and Restoration, including evidence-backed analysis and complete,
editable executive-documentation (ID) packages. The 143-capability registry
remains the readiness denominator.

**Delivery unit:** one reusable product capability with a visible application
output. A source receipt, page counter, candidate store, or test suite is
supporting evidence, never the output by itself.

**OZERO:** the preserved OZERO workspace is one real validation corpus. It is
not the product boundary, a required fact source for all development, or a
reason to postpone an independently testable capability. OZERO checks are
recorded with the precise subset they exercise; controlled inputs with known
outcomes establish reusable behaviour first.

The current product path is deliberately two connected increments:

| Capability | Modes | User-visible output | Implementation gap | Acceptance | OZERO role |
| --- | --- | --- | --- | --- | --- |
| Evidence-bound Tender comparison and findings schedule | Tender | Editable schedule of source-backed quantity/material comparisons, risks, consequences and exact missing inputs | Work packages currently mirror raw observations and generic reconciliation cards cannot distinguish a real comparison from unavailable comparison input | Controlled revisions, repeated names, distinct scopes, quantity discrepancy and missing-input cases; persistence, evidence navigation and isolation | Validate a selected available design/estimate subset only; no project-wide claim until coverage supports it |
| Supported ID package formation and export | Support; reusable data prepared in Tender | Register-first editable ID package, generated supported forms, attachments/missing-field manifest and export | Existing package formation needs a scope-aware, deduplicated work package and a production-facing completeness/report boundary | Controlled known work type with composition, missing fields, revisions, export/render/edit/reload/isolation | Optional regression check only; OZERO does not supply execution dates, measurements, signatures or a Support transition |

### Product-led delivery evidence — 2026-09-19

The two initial increments are implemented on feature releases `98b7363` and
`fca2198` (the controlled API release set must still be verified per runtime):

* Tender now consolidates work observations only within an explicit source and
  scope, retains conflicting quantities rather than summing them, exposes a
  source-backed editable findings schedule, and states when estimate or
  contract input is unavailable instead of emitting an unsupported omission or
  generic contract-review conclusion.
* Support can export the exact formed package as a deterministic editable ZIP:
  its register is the first entry, available generated/finalized documents are
  included, and missing/blocked positions are an explicit separate schedule.

Release `98b7363` replaces the CSV-only first register projection with a
Russian editable DOCX register candidate as the first archive document,
retaining the CSV as a tabular projection and the missing-items schedule as a
separate truthful boundary. It is tested from controlled package data with a
valid OOXML structure and a persisted application export. It does not claim
official register-template authority, completed field records, or visual
renderer qualification; OZERO is not required for this change.

Tender now also has the editable Russian report described above. It exposes the
current materialization state, coverage gaps, candidate finding, practical
consequence, exact missing input, and source/revision/locator reference.
Controlled project-model data tests its candidate boundary and document
validity; an OZERO check is limited to rendering its already-persisted findings
and never implies full-corpus Tender acceptance.

The next active reusable output is an **Audit expected-versus-package
preflight**. It is a workspace-scoped application projection of exact
requirement versions and ID-package memberships. It preserves repeated document
names in distinct work scopes, reports missing/generated/finalized-but-not-yet-
audited positions, and never promotes a package member to an independently
audited conclusion. It is intentionally not the immutable canonical Audit
ledger: that ledger remains owned by the separately scoped `asd_audit_service`
role. Controlled support-package data verifies identity/version matching,
candidate boundaries, API authorization, and UI rendering; OZERO is not needed
for its acceptance.

Controlled checks cover repeated names in different scopes, contradictory
quantities, missing estimate input, contract-input state, register ordering,
generated/missing documents, persistence, authorization scope, and ZIP
content. These checks establish reusable behavior; they do not establish
OZERO-wide extraction, Tender completeness, a Support field execution, or
full-product readiness. OZERO remains available for a selected real-data
regression only after the relevant live worker path is healthy.

Blocked live processing and the local Qwen slot never block implementation,
controlled verification, or outputs that do not require that live runtime.
No capability is promoted to `CAPABILITY_READY` without its declared
professional output and E2E evidence.

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

## Current slice: INDUSTRIAL-DOCUMENT-UNDERSTANDING-01

Purpose: turn admitted ПЗ/ПД/РД/ВОР/estimate documents into an evidence-bound,
visible project model without changing memory integrity or claiming a ready
mode.

`admitted documents → document/page classification → ProjectDefinition → OKS
structure → work/quantity/MTR candidates → ConstructionWorkPackages →
WorkRequirementMatrix → visible evidence-bound UI result`.

This slice starts only after MEMORY-INTEGRITY-FIX-01 is merged. It must use the
existing Product Application Spine, durable jobs, workspace isolation,
Knowledge Gateway and exact locators. Its bounded normative denominator is the
official PP No. 87 edition/amendment chain and the official SPDS family manifest
needed for PD/RD applicability. It does not authorize recursive acquisition of
unrelated NTD, a real OKS, CAD/Drawing Intelligence or external VLM routing.

Current implementation and acquisition status is recorded in
[INDUSTRIAL-DOCUMENT-UNDERSTANDING-01](../implementation/INDUSTRIAL_DOCUMENT_UNDERSTANDING_01.md).

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

The Field/Offline stream includes the separately registered
[`FIELD-ANDROID-CLIENT-01`](../implementation/FIELD_ANDROID_CLIENT_01.md)
capability ([issue #24](https://github.com/yamazaki1711/asd-kontur/issues/24)).
It remains `NOT_IMPLEMENTED`; an approved threat model and comparative device,
MDM, security, offline-sync and delivery decisions precede any Android project.
Its absence blocks Support/Audit/Restoration field acceptance and final
`ProductReady`, but does not expand the current Industrial Document Understanding
slice.
