# WP-11 Common Domain Process Kernel v0.1

- **Status:** `Accepted implementation foundation — WP-11 PASS`
- **Owner:** Oleg Shcherbakov
- **Date:** 2026-08-23
- **Authority:** delegated implementation and ordinary architecture authority in the WP-11 task
- **Dependencies:** G-04, G-05, G-06 and G-07A accepted foundations; G-02B/G-07B remain blocked

## 1. Purpose and acceptance boundary

WP-11 implements one object-independent domain process kernel shared by Tender, Support, Audit and
Restoration. Its common evidence chain is:

```text
workspace sources → CandidateVersion → ConfirmationDecision → WorkspaceFactVersion
→ construction structure → work/type/volume → MTR → control
→ evidence/document requirements → ID completeness → presented volume
→ KS/payment eligibility → typed findings and deliverable inputs
```

This foundation does not implement any complete mode workflow, professional deliverable,
ID-document generation or ProductReady status. The exact Implementation Plan acceptance is:

- common commands/state/events/services and calculation/blocking interfaces;
- cross-mode invariant, concurrency/idempotency and source-to-result lineage tests;
- no mode-specific store or core;
- one reproducible, workspace-isolated common scenario used by every mode overlay.

## 2. Package and service model

`asd_kontur.kernel` contains:

- immutable typed scope, evidence, quantity, authority, policy, Candidate assessment,
  completeness and process-snapshot records;
- `ConfirmationGate`, which is independent of PostgreSQL and rejects model/service authority;
- deterministic completeness-delta and work-order calculations with explicit missing items and
  dependency-cycle blockers;
- `PostgresCommonKernel`, a narrow transaction service for the Candidate-to-Fact transition.

There is no generic repository, arbitrary table selector, mode-specific package or JSON document
standing in for the domain model. Quantities use `Decimal`, exact units, precision and explicit
rounding versions. Deterministic fingerprints use RFC 8785/JCS plus SHA-256 from the accepted G-04
runtime.

## 3. Candidate-to-Fact authority gate

The transition preserves the strict type and authority boundary:

```text
ProviderExecutionResult != CandidateVersion != validated_candidate != WorkspaceFactVersion
```

`PostgresCommonKernel.confirm_candidate` performs one transaction and requires:

1. exact workspace scope and writable G-06 lifecycle state;
2. exact immutable CandidateVersion and field path;
3. a passed exact ValidationRun with no blocking failures or skipped required validators;
4. verified field-level EvidenceLink with SourceVersion and SourceLocator;
5. active exact ConfirmationPolicyVersion;
6. expected Fact version and scoped idempotency key;
7. either:
   - an active qualified-human grant for the exact fact class; or
   - an explicitly allowed deterministic auto-confirm class, active RuleVersion, exact pinned
     RuleSet membership and applicable passed RuleTrace;
8. no unresolved conflict or uncertainty and no professional-authority requirement.

Legal effect, contractual obligation, geometry/measurement, payable volume, signer authority,
material blocker and professional finalization are always excluded from deterministic
auto-confirm. A model/service identity, confidence, repetition, valid transport or model agreement
cannot satisfy the gate.

The accepted transition writes immutable `ConfirmationDecision`, `WorkspaceFactVersion`, exact
evidence bindings, content-minimal audit and outbox in the same transaction, then completes the
idempotency receipt. A lost response can therefore replay the prior outcome without a second Fact
version. Rejection rolls back all canonical writes.

## 4. Physical model

Forward migration `0005_wp11_common_domain_kernel` follows `0004_g07`.

Platform definitions, which survive workspace reset, are versioned separately:

- `WorkType` / `WorkTypeVersion`;
- `MaterialClass` / `MaterialClassVersion`;
- `RequiredDocumentType` / version;
- `ConfirmationPolicyVersion`.

Workspace canonical/version relations include:

- confirmation authority grants, decisions, fact headers/versions and evidence bindings;
- common process instances and exact fact bindings for ModeExecution;
- construction structures/elements;
- work instances, dependencies and measured volumes;
- material requirements, admitted batches and applications;
- control operations and evidence/document requirements;
- document coverage and ID package completeness;
- presented volumes, KS document/line versions and payment claims;
- typed Conflict/Blocker/Uncertainty records, findings and deliverable inputs.

Stable aggregate identity is separate from immutable version identity. Every workspace relation has
mandatory `(organization_id, workspace_id)`, composite scope references, exact version references,
`ENABLE/FORCE RLS`, the lifecycle write fence and immutable version history. Header advancement is
limited to the WP-11 service role and transaction-local operation token. No nullable universal
scope exists.

## 5. Common chain and deterministic semantics

The schema makes the evidence path explicit:

- a structure is derived only from a confirmed FactVersion and pinned RuleTrace;
- an element belongs to an exact structure version;
- a work instance pins WorkTypeVersion, structure element, source Fact and RuleSet/RuleTrace;
- a volume pins Decimal quantity, unit, precision, calculation version, fact and trace;
- MTR requirement/application pins material class, work version, evidence and quantity semantics;
- control, evidence and document requirements record three-valued applicability and exact trace;
- document coverage points to a typed subject and EvidenceLink;
- ID completeness stores required/covered/missing/blocking counts and a deterministic digest;
- presentation, KS and payment records retain the exact volume/package/calculation lineage;
- findings carry a typed finding class, applicability, facts, evidence, issues, RuleSet and trace;
- deliverable inputs remain typed and versioned; they are not a universal document contract.

Missing input is never an empty success. Applicability is `applicable`, `not_applicable` or
`indeterminate`; the latter is represented by typed issue state. Completeness returns the exact
missing and blocking sets. Work dependency cycles fail with a stable blocker code.

## 6. Four-mode use

Tender, Support, Audit and Restoration use the existing single `ModeExecution` table and the same
WP-11 relations/services. `mode_kernel_bindings` permits a governed mode execution to consume an
exact confirmed FactVersion in the same workspace; both mode and fact composite foreign keys are
database enforced. The cross-mode integration test creates all four modes and binds them to the
same common confirmed fact and chain. No mode table, database, repository or lifecycle variant was
added.

The mode status does not imply result finalization or ProductReady. Mode-specific orchestration is
deferred to WP-12…WP-15.

## 7. Isolation, lifecycle and reset

The non-owner `asd_kernel_service` is subject to default-deny RLS and obtains scope only through
transaction-local settings. It has read policies only for the exact Candidate/Evidence/RuleTrace
inputs and write access only to WP-11, audit, outbox and idempotency relations needed by the
confirmation transition.

Cross-workspace facts, evidence, traces and mode bindings are rejected by composite foreign keys or
RLS. A frozen workspace rejects late fact/domain writes through the G-06 material-write fence.

All WP-11 workspace tables are added child-first to the exact G-06 PostgreSQL Storage Adapter
Registry implementation. Migration `0005` also corrects an earlier lifecycle integration defect:
immutable G-05 workspace source/rule/trace records now allow only scoped deletion by the restricted
destruction role; platform immutability remains unchanged. Disposable reset evidence deletes the
entire WP-11 state of workspace A, leaves workspace B unchanged and preserves platform WorkType,
NTD/rule memory and other platform definitions.

## 8. Contracts and events

No Contract Pack extension was necessary. WP-11 uses the accepted v0.1 contracts for Candidate,
ValidationResult, ConfirmationDecision/WorkspaceFact, EvidencePack, RuleTrace,
CommandEnvelope/outcome, event/outbox and typed mode deliverables. Persisted references reject
mutable `latest`.

The service writes a `workspace.fact-confirmed` outbox record only after an accepted canonical
transition. Rejected commands produce no domain event. Delivery remains at-least-once and events
remain derived integration records, not canonical state.

## 9. Migration and rollback

- clean upgrade: `0001_g04 → 0002_g05 → 0003_g06 → 0004_g07 → 0005_wp11`;
- canonical upgrade: `0004_g07 → 0005_wp11`;
- disposable rollback/reapply: `0005_wp11 → 0004_g07 → 0005_wp11`;
- destructive downgrade requires explicit `ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1` and is prohibited for
  production use;
- downgrade removes WP-11 policies/grants/triggers from surviving G-04…G-07 relations and restores
  the prior G-05 workspace immutability triggers.

Migration execution is deterministic and does not read network, provider terms, mutable policy or
runtime application services.

## 10. Legacy mapping

| Legacy idea | Decision | WP-11 result |
|---|---|---|
| Deterministic identifiers and RuleTrace | **Preserve/modernize** | Uses accepted UUID/JCS foundation, exact RuleVersion/RuleSet and immutable trace references. |
| Typed calculations and completeness delta | **Preserve/modernize** | Decimal/unit/precision records and deterministic missing/blocking sets replace implicit calculations. |
| ISGenerator/ISUID/id-track evidence bindings | **Future selective port** | Typed document requirements, coverage, ID package and deliverable-input relations are stable future inputs; no legacy generator or template was copied. |
| Global project memory / graph as truth | **Reject** | Workspace-scoped canonical relations are the source of record; projections remain rebuildable. |
| Confidence confirmation / fuzzy normative defaults | **Reject** | Explicit ConfirmationDecision, exact authority and three-valued applicability are mandatory. |
| Whole-schema reset / TM-35 assumptions | **Reject** | Exact adapter inventory and object-independent synthetic fixtures only. |

No legacy source file, ORM model, project fixture or generated document was copied.

## 11. Verification evidence

Local PostgreSQL 17.10 evidence before publication:

- `22 passed` focused unit tests;
- `7 passed` focused PostgreSQL integration/migration tests;
- `171 passed` full suite with no skipped/deselected tests;
- strict mypy: 50 source files, no issues;
- Ruff format/lint: clean;
- non-owner service-role RLS/default-deny and A/B isolation;
- atomic/idempotent confirmation, optimistic concurrency and lifecycle fence;
- exact common-chain lineage and four-mode reuse;
- scoped reset, workspace-B survival and platform-memory survival;
- clean migration and disposable downgrade/upgrade.

Pull request #8 produced two successful canonical workflow runs (branch push and PR) on PostgreSQL
18 + pgvector. The same locked, Ruff, mypy, migration, Contract Pack and `171 passed` pytest suite
completed without failed, skipped or cancelled checks.

## 12. Gate self-check and blockers

| WP-11 criterion | Status |
|---|---|
| Candidate-to-Fact authority boundary | PASS |
| Common structure/work/MTR/control/evidence/ID/volume/KS/payment chain | PASS |
| Typed findings, issues and deliverable inputs | PASS |
| Deterministic calculations and source-to-result lineage | PASS |
| Four modes use one kernel/store/lifecycle | PASS |
| Concurrency, idempotency and immutable history | PASS |
| Non-owner RLS, A/B isolation and lifecycle fence | PASS |
| G-06 reset integration and platform-memory preservation | PASS |
| PostgreSQL 18 + pgvector canonical CI | PASS |

`WP-11 = PASS` is an accepted implementation foundation on synthetic/disposable evidence. G-02B,
G-07B, production policies/authority, all four mode E2E suites, three production
deliverables and ProductReady remain `BLOCKED`. The next work package is WP-12 Tender slice and does
not start automatically.
