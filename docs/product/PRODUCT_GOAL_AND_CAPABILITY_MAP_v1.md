# Product Goal and Capability Map v1

- Product Goal: `PRODUCT-GOAL-ASD-KONTUR@1.0.0`
- Owner source: [GitHub issue #19](https://github.com/yamazaki1711/asd-kontur/issues/19)
- Machine denominator: [Contract Pack v2.0](../../contracts/v2.0/README.md)
- Current readiness ledger: [Contract Pack v2.2](../../contracts/v2.2/README.md)
- Current decision: [Product Goal Rebaseline](PRODUCT_GOAL_REBASELINE_DECISION_v1.json)

## Goal

ASD-KONTUR is an object-independent, local-first, evidence-bound construction
software system for thousands of documents. Its common professional chain is:

`PD/RD + contract + VOR/estimate + customer regulation + NTD`
`→ ProjectDefinition → OKS structure → works/quantities → MTR → control points`
`→ required evidence → ID → presented quantities → KS → payment`.

The three permanent results are:

1. a contractor-protective protocol of disagreements and revised construction
   contract;
2. PD/RD analysis for omitted work/material, constructability/geometric
   collisions, errors, cost and time risk;
3. executive schemes from verified design and as-built geometry only.

Tender, Support, Audit and Restoration are required. They share one domain and
knowledge kernel; a backend slice or UI screen is not a ready mode.

## Complete denominator

The registry contains **142 mandatory capabilities across 13 planes**. The
independent required list prevents a capability from disappearing silently.

| Plane | Count | Stable capability namespace | Current distribution |
|---|---:|---|---|
| Product Interaction | 13 | `interaction.*` | 12 NOT_IMPLEMENTED, 1 CONTRACT_ONLY |
| Application | 10 | `application.*` | 4 NOT_IMPLEMENTED, 3 CONTRACT_ONLY, 3 FOUNDATION_ONLY |
| Industrial Intake | 17 | `intake.*` | 3 NOT_IMPLEMENTED, 6 CONTRACT_ONLY, 8 FOUNDATION_ONLY |
| Project Understanding | 12 | `project-understanding.*` | 9 CONTRACT_ONLY, 3 FOUNDATION_ONLY |
| Knowledge and Rules | 11 | `knowledge.*` | 2 NOT_IMPLEMENTED, 2 CONTRACT_ONLY, 6 FOUNDATION_ONLY, 1 PARTIAL |
| Engineering Intelligence | 9 | `engineering.*` | 6 CONTRACT_ONLY, 3 FOUNDATION_ONLY |
| Tender | 8 | `tender.*` | 3 CONTRACT_ONLY, 5 FOUNDATION_ONLY |
| Support | 12 | `support.*` | 6 CONTRACT_ONLY, 6 FOUNDATION_ONLY |
| Audit | 8 | `audit.*` | 4 CONTRACT_ONLY, 4 FOUNDATION_ONLY |
| Restoration | 7 | `restoration.*` | 2 CONTRACT_ONLY, 5 FOUNDATION_ONLY |
| Document/CAD Output | 11 | `output.*` | 9 CONTRACT_ONLY, 2 FOUNDATION_ONLY |
| Field/Offline | 10 | `field.*` | 10 CONTRACT_ONLY |
| Operations | 14 | `operations.*` | 9 CONTRACT_ONLY, 5 FOUNDATION_ONLY |
| **Rebaseline total (v2.0)** | **142** | — | **21 NOT_IMPLEMENTED, 70 CONTRACT_ONLY, 50 FOUNDATION_ONLY, 1 PARTIAL** |

The per-plane table above preserves the v2.0 rebaseline. The effective
post-Spine distribution is the additive v2.1 delta reconciled by v2.2; no stable
capability identity was added, removed or renamed.

| Effective readiness after Product Application Spine | Count |
|---|---:|
| `CAPABILITY_READY` | 16 |
| `PARTIAL` | 10 |
| `FOUNDATION_ONLY` | 45 |
| `CONTRACT_ONLY` | 64 |
| `NOT_IMPLEMENTED` | 7 |
| **Denominator** | **142** |

The complete stable-ID list and per-capability product result, modes, lifecycle,
inputs, outputs, dependencies, canonical/workspace data, surface, evidence,
readiness, gaps, acceptance, scale and next slice are in:

- [required-capabilities.json](../../contracts/v2.0/required-capabilities.json);
- [product-capability-registry.json](../../contracts/v2.0/fixtures/valid/product-capability-registry.json).

These files are normative and machine-validated; this page is their navigation
view, not a second registry.

## Readiness ladder

| Level | Meaning |
|---|---|
| `NOT_IMPLEMENTED` | No accepted contract or implementation. |
| `CONTRACT_ONLY` | Boundary/schema exists; behavior is not implemented. |
| `FOUNDATION_ONLY` | Services/schema/tests exist without a user/operations process. |
| `PARTIAL` | Some behavior/evidence exists, but terminal criteria are unmet. |
| `CAPABILITY_READY` | Production-shaped interface, real declared formats, professional result and capability E2E pass. |
| `MODE_READY` | One mode passes its complete admission-to-output/export/recovery user workflow. |
| `TRIAL_READY` | Application Spine, UI/API/intake/jobs/viewer, applicable NTD/rules/outputs, operations and scale qualification all pass under an explicit decision. |
| `PRODUCT_READY` | Four MODE_READY decisions, three product results and system-wide operational acceptance all pass. |

Tests are evidence inside a denominator; their count is never a readiness KPI.
No real OKS is proposed before an exact `TrialReadinessDecision`.

## Current truth

- `PlatformKernelReady=PARTIAL`;
- `ProductApplicationReady=PARTIAL`;
- `TrialReady=false`;
- `OKSReady=false`;
- `ProductReady=false`.

SYSTEM-INTEGRITY-CYCLE-01 proves bounded kernel reproducibility only. Its old
semantic claim was superseded by the memory DATA_DEFECT; MEMORY-INTEGRITY-FIX-01
may close only that bounded defect after its own qualification series.
Rule Registry has infrastructure but zero operational rules.

## Delivery order

1. complete `MEMORY-INTEGRITY-FIX-01` in its separate worktree;
2. implement `INDUSTRIAL-DOCUMENT-UNDERSTANDING-01` exactly as specified in the
   [Implementation Plan](../architecture/IMPLEMENTATION_PLAN_v1.md);
3. deliver capability streams that end in visible professional outputs;
4. perform Trial Readiness qualification before any real OKS.
