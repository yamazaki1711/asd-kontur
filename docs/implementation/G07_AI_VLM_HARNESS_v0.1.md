# G-07 AI/VLM Verification Harness v0.1

- **Status:** `Accepted implementation foundation — G-07A PASS; G-07B BLOCKED`
- **Owner:** Oleg Shcherbakov
- **Date:** 2026-08-23
- **Authority:** delegated implementation and ordinary architecture authority in the G-07 task
- **Canonical dependency:** G-03 Contract Pack; G-04 persistence; G-05 knowledge/rules; G-06 lifecycle

## 1. Gate interpretation

G-07 implements the common Candidate-only extraction and verification foundation. It does not
implement a Tender, Support, Audit, or Restoration process and does not confirm a fact, legal
position, measurement, geometry, signer, rule, final document, or ProductReady status.

The dependency wording in the Implementation Plan is resolved without concealing the historical
WP-09 dependency:

| Sub-gate | Result | Meaning |
|---|---|---|
| G-07A local/synthetic Harness foundation | **PASS** | Native-first, provider contract, deterministic local process adapter, no-network async provider, Candidate lifecycle, validation, repair, routing, qualification, batch, cost, persistence and reset integration are implemented and tested. |
| G-07B distributed external execution | **BLOCKED** | Requires WP-09 coordination, G-02B active production policy instances, VPS controlled egress, real provider terms, S3/provider residue adapters and approved qualification evidence. |

The accepted G-07 implementation status means the local/synthetic foundation is suitable for the
next implementation work package. It is not production VLM readiness.

## 2. Implemented scope

The package `asd_kontur.harness` contains immutable typed records and narrow services:

- `models.py`: workspace scope, authorized SourceVersion locators, exact execution identity,
  development budgets, requests, provider results, render lineage, CandidateVersion, field values
  and typed ValidationFailure;
- `native.py`: pypdf native-text extraction for exact one-based authorized pages and a typed
  native-first preflight;
- `providers.py`: the provider-neutral interface, deterministic asynchronous external test
  provider, and MLX-independent local Qwen process boundary;
- `routing.py`: fail-closed versioned routing decisions and reserve/commit/release cost ledger;
- `validation.py`: exact-version validator registry and common, legal and geometry validators;
- `repair.py`: targeted bounded repair, repeated-fingerprint/no-progress stop and FieldConflict;
- `batch.py`: one-workspace immutable batch, bounded submission and result reconciliation;
- `qualification.py`: exact full-profile fingerprint, critical floors and zero-tolerance blockers.

There is deliberately no `WorkspaceFact` writer, confirmation repository, model tool executor,
direct SQL tool, or external network client in the Harness.

## 3. Native-first sequence

The enforced decision order is:

1. writable workspace lifecycle state;
2. exact SourceVersion digest;
3. supported media type and authorized page/region locators;
4. active, unambiguous classification and purpose;
5. native/structured layer extraction;
6. common deterministic validation and required-field sufficiency;
7. only then an explicit route decision.

Outcomes are typed: `native_sufficient`, `native_insufficient`, `unsupported_source`,
`policy_blocked`, `source_stale`, `lifecycle_blocked`, `needs_local_execution`, and
`external_route_denied`. Short or absent text alone never authorizes a VLM route. A native result
is still a Candidate and passes the same validator registry as OCR/VLM output.

## 4. Provider architecture

`VlmExecutionProvider` fixes the transport-neutral operations:

```text
describe_capabilities → health → submit → poll → cancel → fetch_result
```

`health.available` is explicitly separate from qualification. `ProviderExecutionResult` is
separate from `CandidateVersion`; unknown outcome requires reconciliation.

### Local Qwen process boundary

The logical primary profile is Qwen3.8-27B. Its identity includes provider/version, model revision,
execution format, quantization, runtime, execution profile, prompt, schema, preprocessing,
rendering and verification versions. 8-bit and BF16 are therefore different profiles and cannot
inherit qualification.

The adapter accepts an explicit interpreter, runner and model directory, invokes an argv list with
no shell interpolation, uses bounded request/result files, enforces timeout and diagnostic-size
limits, checks request and identity digests, and provides `submit_bounded_batch` so one process can
load one model for one bounded workspace batch. A non-blocking heavy-session lock prevents two
concurrent heavy sessions through one adapter instance. Configuration paths are not persisted.

The deterministic process adapter is tested end to end. The installed local evidence was checked
read-only: MLX Python exists, and Qwen3.8-27B 8-bit and BF16 directories exist. A real MLX inference
smoke was **not** performed because the new canonical render-object-to-runner binding is not yet
qualified; reusing the pilot runner would bypass the new render and authorization contract.
Therefore:

- local process contract: `VERIFIED`;
- physical runtime availability: `OBSERVED`;
- real Qwen synthetic inference: `BLOCKED`;
- production local qualification: `BLOCKED`.

### External boundary

`DeterministicExternalProvider` models async submit/poll/cancel, duplicate submit, unknown outcome
and reconciliation without network access. It has no endpoint, credentials, SQL, object URL,
Knowledge Gateway access or human authority. All real external destinations remain default-deny.

## 5. Routing, fallback and budgets

Routes are `native_only`, `local_ocr`, `local_vlm`, `authorized_external_vlm`, and `no_execution`.
The decision records considered/rejected routes, exact policy version and authorization reference.

- legal, contractual, confidential and geometry-related content is local-only unless separately
  authorized by a future active production policy;
- missing, ambiguous, expired or unset classification denies external execution;
- provider outage never expands authority;
- local failure never makes local-only data eligible for egress;
- external execution requires qualification, egress authority, active terms, purpose/classification
  allowlists, mass-raster purpose, reservation and a new authorization reference;
- provider switch is a new routing decision, not hidden repair.

Only explicit synthetic development budgets contain numbers. PostgreSQL allows an active budget
only when all mandatory fields are populated and requires human approval for an active production
budget. No production numbers or Polza.ai prices were invented.

## 6. Candidate and validation boundary

Harness terminal dispositions are limited to:

- `validated_candidate`;
- `unresolved_uncertainty`;
- `rejected_extraction`;
- `provider_model_failure`.

There is no `confirmed` or `fact` state. A validated Candidate requires exact ValidationResult
references and a locator for every material field. Model confidence is not read by validators.

The versioned registry supports schema/type/required field, locator/scope, unit, range and domain
validators. The implementation includes the required stable failures used by native, legal and
geometry boundary tests, including `SCHEMA_REQUIRED_FIELD_MISSING`, `LOCATOR_INVALID`,
`LOCATOR_OUTSIDE_SCOPE`, `UNIT_MISSING`, `LEGAL_LOCATOR_UNVERIFIED`,
`GEOMETRY_INPUT_UNCONFIRMED`, and `SOURCE_STALE`. A missing mandatory validator produces
`indeterminate`, never empty success.

## 7. Targeted repair

Only failures marked `targeted_repair` enter a repair plan. The plan pins parent CandidateVersion,
field paths, source locators and failure fingerprints. The parent is immutable; repair produces a
new version. Repeated failure fingerprints, no progress, a non-repairable failure or exhausted
cycle budget stop execution. Multiple different passing values for the same field and locator
produce `FieldConflict`; the model does not choose a winner.

## 8. Qualification

Qualification identity is the entire execution tuple, not a model name. A decision pins corpus,
strata, metrics, critical floors, all zero-tolerance blocker results, validity interval and human
approval. The implementation rejects inheritance after revision, quantization or profile changes
and rejects a high average when a critical floor or blocker fails.

The zero-tolerance set contains cross-workspace leakage, invented source/locator/edition/geometry,
critical unit or sign error, Candidate-to-Fact bypass, egress bypass, document/workspace mixing,
hidden mandatory uncertainty and schema/result substitution.

No four-mode golden corpus, production floors or production qualification decision exists.

## 9. Persistence and migration

Forward migration `0004_g07_ai_vlm_harness` follows `0003_g06`.

Platform relations contain provider, execution profile, routing policy, execution budget and
qualification versions. They are immutable platform memory and survive workspace reset.

Workspace relations contain execution requests, routing decisions, attempts, provider
results/failures, render artifacts, Candidate versions/fields/evidence, validation runs/failures,
repair plans/cycles, batches/items, cost envelopes/ledger and raw-artifact references. Every table
has mandatory `(organization_id, workspace_id)`, composite foreign keys where applicable,
`ENABLE/FORCE RLS`, non-owner role policies, immutable-update guards, the G-06 write fence and an
exact destruction-role delete path. There is no nullable universal scope.

All request/result/policy/schema/rule references reject mutable `latest`. Candidate fields may use
JSONB only as a value paired with `value_type`, field path and evidence; JSONB is not used as a
replacement for the aggregate model.

Disposable downgrade requires `ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1`; the cluster role remains, as in
0001–0003. Production destructive downgrade remains prohibited.

## 10. Contract extension v1.1

Contract Pack v0.1 and destruction-attestation v1.0 were not modified. Additive release
`contracts/v1.1` defines render lineage, one-workspace batch manifest, qualification decision and
raw-artifact retention reference. It uses Draft 2020-12, stable URN `$id`, local-only references,
fingerprints and valid/invalid hostile fixtures. Earlier contracts remain immutable and compatible.

## 11. Lifecycle and retention integration

G-07 relations are added to the exact allowlist of `PostgresWorkspaceStorageAdapter` in child-first
order. Synthetic reset evidence proves raw Harness data is deleted while the platform execution
profile remains. The application/harness roles cannot write after G-06 freeze. `no_raw_storage`
requires no object or encryption-key reference; a future production encrypted profile remains
blocked on active key/policy evidence.

Audit requirements remain content-minimal: identifiers, decisions, stable failure codes,
correlation/causation and digests only. Prompt, page content and provider response are not written to
platform audit.

## 12. Legal and geometry boundaries

Legal Candidate validation requires exact SourceVersion and verified locator; an invented citation
is a blocker. Normative applicability and precedence remain in the Knowledge/Rule/human authority
process.

Geometry validation requires confirmed source, CRS, units and precision. Render coordinates require
two reversible 3×3 transforms. A VLM region is only a Candidate locator; it never becomes confirmed
measurement, geometry or an executive scheme.

## 13. Legacy decisions

| Evidence | Decision | Result |
|---|---|---|
| old `mlx_vlm_adapter.py` and runners | **Modernize** | Preserved process isolation, strict result file, timeout and one-load batch principle; replaced file-level `None`/free text with typed failures, full scope, policy, digest and Candidate boundary. |
| old `text_layer.py` / Candidate mode | **Modernize** | Preserved native-first intent; replaced page-confidence logic with required-field sufficiency and common validators. |
| old per-page runner | **Reject** | No per-page model reload in bounded batch. |
| old fixed confidence threshold | **Reject** | Confidence cannot confirm a Candidate. |
| mac_asd PDF/VLM pipeline | **Evidence only** | Preserved typed page/render intent; rejected fixed 300-DPI semantics, direct aggregate result, silent fallback, unverified geometry and mode-specific core. |
| TM-35 paths, benchmark outputs, model paths | **Reject from canonical data** | No real ОКС data or local path is persisted or committed. |

No legacy application file or algorithm was copied mechanically.

## 14. Verification evidence

Local evidence on PostgreSQL 17.10:

- `112 passed` unit/contract suite;
- `142 passed` full suite with PostgreSQL integration;
- migration clean install `0001 → 0002 → 0003 → 0004`;
- disposable `0004 → 0003 → 0004` and existing broader downgrade/upgrade suites;
- actual non-owner `asd_harness_service` RLS tests;
- default deny without transaction scope and A/B workspace isolation;
- composite FK rejection of another workspace SourceVersion;
- immutable CandidateVersion and freeze write-fence rejection;
- exact reset adapter deletion and platform profile survival;
- deterministic local process and bounded-batch tests;
- Contract v1.1 fingerprint, Draft 2020-12, valid/invalid hostile fixture tests.

Canonical PostgreSQL 18 + pgvector CI evidence is recorded only after the PR workflow succeeds.

## 15. Gate self-check

| Criterion | Status |
|---|---|
| Native-first and exact SourceVersion/locator preflight | PASS |
| Provider-neutral local/external contracts | PASS |
| Local process adapter and one-session bounded batch | PASS (deterministic runner) |
| Real local Qwen synthetic inference | BLOCKED |
| Candidate-only lifecycle | PASS |
| Deterministic validators and explicit uncertainty | PASS |
| Bounded targeted repair | PASS |
| Routing/default-deny/fallback reauthorization | PASS |
| Qualification framework and zero blockers | PASS |
| Batch/idempotency/reconciliation/cost semantics | PASS |
| PostgreSQL migration, RLS, lifecycle/reset integration | PASS locally; CI pending before merge |
| Real external/VPS/S3/provider execution | BLOCKED as G-07B |

`G-07A = PASS` is an accepted synthetic/local implementation foundation. `G-07B`, G-02B,
production local-model qualification, production numerical policies, real Polza.ai, production raw
encryption, four-mode E2E, deliverable E2E and ProductReady remain `BLOCKED`.

The next work package after publication is WP-11, the common domain process kernel. It is not begun
by this gate.
