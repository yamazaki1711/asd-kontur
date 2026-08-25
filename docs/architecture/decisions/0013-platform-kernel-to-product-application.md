# ADR-0013: Platform Kernel → Product Application

- Status: Accepted
- Owner: Oleg Shcherbakov
- Date: 2026-08-26
- Decision: `PRODUCT-GOAL-REBASELINE-DECISION-v1`

## Context

ASD-KONTUR has a substantial evidence-bound Platform/Domain Kernel: PostgreSQL
canon, isolation, provenance, lifecycle, Knowledge Gateway, AI/VLM harness,
Practice Intelligence, NTD and Rule contracts, and bounded four-mode domain
views. It does not yet have the application, interaction, industrial intake,
output and operational processes needed by a user working with thousands of
construction documents.

Backend tests, a synthetic fixture, a bounded mode slice or an integrity cycle
cannot stand in for a user-operable professional outcome. The complete
denominator is the versioned Product Capability Registry.

## Decision

1. The existing implementation is classified as a **Platform/Domain Kernel**.
2. Readiness is ordered and fail closed:
   `NOT_IMPLEMENTED → CONTRACT_ONLY → FOUNDATION_ONLY → PARTIAL →
   CAPABILITY_READY → MODE_READY → TRIAL_READY → PRODUCT_READY`.
3. A capability becomes `CAPABILITY_READY` only through a production-shaped
   approved interface, real declared input formats, professional output,
   blockers/recovery, and capability E2E evidence.
4. A mode becomes `MODE_READY` only after its complete user workflow passes
   from admission to evidence-bound result, export and recovery.
5. No real OKS may be proposed or admitted without an exact accepted
   `TrialReadinessDecision`.
6. `PRODUCT_READY` requires all four `MODE_READY` decisions, all three permanent
   product results, and cross-platform operational acceptance.
7. `READY_FOR_INTEGRITY_CYCLE` continues to mean participation in a kernel
   integrity harness. It is not capability, trial or product readiness.
8. Rule Registry with `RuleVersion=0` is
   `infrastructure_ready=true, operational_rule_coverage=false`.
9. Historical decisions and receipts remain immutable; only their overly broad
   interpretation is superseded.

## Legacy decision gate

mac_asd is product evidence, scenario catalog, engineering hypothesis set,
selective component source, anti-pattern catalog and regression corpus. It is
not the target architecture. Before any reuse, the component must pass the
[Legacy Component Decision Matrix](../LEGACY_COMPONENT_DECISION_MATRIX_v1.md).

The policy is: **selective engineering reuse** — preserve the demonstrably best
ideas, algorithms, assets and tests; harden and integrate them into the modern
architecture. Mechanical copy-paste or adoption of a legacy stack without a
new evidence-backed decision is prohibited.

## Consequences

- Product Application Spine is the next delivery slice after the in-progress
  memory-integrity correction.
- UI, API, intake, output and operations are first-class planes, not deferred
  polish.
- Product status at adoption is:
  `PlatformKernelReady=PARTIAL`, `TrialReady=false`, `OKSReady=false`,
  `ProductReady=false`.
