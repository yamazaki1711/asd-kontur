# АСД-КОНТУР — Contract Pack v0.1

Статус: **Accepted architecture baseline**

Gate: **G-03 Contract Pack — PASS**

Владелец: **Олег Щербаков**

Дата решения: **2026-08-22**

Основание: делегированные владельцем архитектурные полномочия в задаче G-03.

## 0. Назначение и предел решения

Этот документ и каталог [`contracts/v0.1/`](../../contracts/v0.1/README.md)
задают нормативные, версионируемые контракты между компонентами АСД-КОНТУР.
Они достаточны для начала будущей реализации без повторного изобретения
message envelopes, payload boundaries, scope, authority, provenance, state,
errors, idempotency, concurrency, compatibility и retention semantics.

Contract Pack не является Python implementation, Pydantic model, ORM, DDL,
HTTP API, queue configuration или deployment. Transport binding обязан быть
отдельным adapter и не может менять domain semantics.

Точный acceptance criterion из `IMPLEMENTATION_PLAN_v0.1.md`:
machine-readable contracts проходят compatibility, negative-scope и round-trip
tests; G-03 включает schema registry/versioning rules, canonical и
invalid/hostile fixtures, schema fingerprints, deterministic serialization,
organization/workspace isolation и запрет silent coercion/fallback.

G-02A остаётся `PASS`; G-02B production instances остаётся `BLOCKED`. Это не
мешает нормативному G-03: unset production values выражаются типизированным
`POLICY_BLOCKED`, а не подменяются permissive defaults.

## 1. Неподвижные архитектурные границы

1. Scope-иерархия: `platform → organization → ConstructionObject → Workspace
   → ModeExecution`.
2. Platform и workspace records имеют разные допустимые scope variants. Один
   nullable `scope_id` не является допустимым контрактом.
3. `Tender`, `Support`, `Audit`, `Restoration` используют одно ядро, один
   Contract Registry и одну модель canonical state.
4. Постоянны три результата: договорный защитный результат; анализ ПД/РД;
   исполнительная схема только из подтверждённой геометрии. ID Generation &
   Template Platform — capability того же ядра.
5. НТД и утверждённое доменное знание — platform memory. ПД/РД, договор,
   регламент Заказчика, факты, результаты, generated documents и VLM artifacts
   — workspace memory.
6. Регламент Заказчика ссылается на применимую НТД, но не заменяет её.
   Противоречие создаёт `Conflict`/`Uncertainty` и применяется через pinned
   `ConflictPolicy`.
7. `ProviderExecutionResult ≠ Candidate ≠ ValidatedCandidate ≠ WorkspaceFact`.
   Confidence, transport success и consensus моделей не предоставляют
   authority.
8. `RuleVersion` применяется только через pinned `RuleSetVersion`; rolling
   `latest` запрещён. Applicability имеет три значения: `applicable`,
   `not_applicable`, `indeterminate`.
9. Geometry требует CRS/reference frame, units, precision, confirmed source и
   evidence. VLM output не является geometry source.
10. MBP — authoritative primary; VPS — coordination/status/controlled egress;
    S3 — object/archive/recovery plane. Ни message, event, VPS projection, FTS,
    pgvector, graph, cache, render или provider result не является canonical
    state.
11. Cross-workspace references, batch context, cache context и physical
    deduplication project blobs запрещены. Digest не является access capability.
12. После reset audit content-minimal и не позволяет реконструировать ОКС.
    Promotion создаёт новую sanitized platform identity без live-link к
    уничтожаемому workspace.

## 2. Contract Registry

Authoritative registry: [`contracts/v0.1/registry.json`](../../contracts/v0.1/registry.json).

### 2.1. Паспорт контракта

Каждый stable contract key имеет нормализованный паспорт:

| Поле | Нормативная семантика |
|---|---|
| `contract_key` | стабильное имя семантической операции или record |
| `contract_family` | `domain`, `integration`, `tool`, `provider`, `storage`, `process_lifecycle`, `authorization`, `deliverable` |
| `contract_version` | SemVer конкретного контракта; для v0.1 — `0.1.0` |
| `schema_id` / `schema_pointer` | точная immutable schema identity и fragment |
| `status` | `draft`, `proposed`, `accepted`, `deprecated`, `retired`; registry v0.1 — `accepted` |
| `owner` | Олег Щербаков; будущий operational owner не получает authority автоматически |
| `scope` | допустимые concrete scope variants |
| `producer` / `consumers` | логические роли, не deployment адреса |
| `compatibility_policy` | правила producer/consumer evolution |
| effective interval | `effective_from`, nullable `effective_until`; interval не меняет historical bytes |
| supersession | `supersedes`, `deprecation`; отсутствие означает не «latest» |
| `retention_class` | ссылка на policy-controlled fate, не произвольный срок |
| authority | capability, qualification, policy и segregation requirements |
| `tests` | обязательные contract-test classes |
| `digest` | SHA-256 exact schema resource; fragment задаётся `schema_pointer` |

Для компактности registry хранит общие поля в `release_defaults` и
`family_passports`, а individual keys — в `contract_groups`. Нормализованный
паспорт — строгий merge этих трёх уровней. Missing или conflicting inherited
field делает registry invalid; наследование не создаёт permissive default.

### 2.2. Семейства и ownership

| Family | Canonical producer | Основные consumers | Запрещённое смешение |
|---|---|---|---|
| Domain | authoritative domain core | domain/process/review | Candidate, Fact, Rule, Event, Deliverable как один record |
| Integration | outbox publisher/adapters | inbox/status/reconciliation | event как SoR; global order/exactly-once |
| Tool | Knowledge Tool Gateway | authorized execution | direct SQL/object access модели |
| Provider | execution orchestrator/adapter | candidate builder/harness | provider result как Candidate/Fact |
| Storage | StorageAdapter | domain/archive/recovery | digest-only access; cross-workspace blob sharing |
| Process/lifecycle | process/lifecycle controller | core/adapters/audit | `close=delete`; reset без attestation |
| Authorization | PDP/authority registry/audit writer | protected operations | service/model identity как human authority |
| Deliverable | mode/generation/geometry core | reviewers/export/archive | universal untyped document; file-open=finalized |

## 3. Общие definitions и envelopes

JSON Schema dialect: **Draft 2020-12**. Stable identifiers используют URN
`urn:asd-kontur:contracts:v0.1:*`. URN не утверждает наличие deployed registry
service; resolution выполняется из pinned local bundle. Network schema fetch
запрещён.

### 3.1. Identity и scope

- Stable entity/message identifiers логически типизированы. UUIDv7 — будущий
  default для новых identities; deterministic UUIDv5 разрешён только через
  зарегистрированные namespace/canonicalization contracts.
- `ScopeReference` — tagged union:
  `platform(platform_scope)`, `organization(organization_id)` или
  `workspace(organization_id, construction_object_id, workspace_id,
  mode_execution_id?)`.
- Workspace-owned foreign reference должен включать или проверять
  `workspace_id`; на physical layer это реализуется composite FK/RLS, но здесь
  задаётся логический invariant.
- `identity_kind`: human, service, integration, model, node, device. Только
  human authority registry и утверждённая policy могут дать professional или
  destructive capability.

### 3.2. Версии, время и digest

- `contract_version` и `schema_version` — exact SemVer.
- `aggregate_version` — observed version; `expected_version` — optimistic
  precondition.
- Timestamps — UTC RFC 3339 date-time. Clock time не определяет ordering между
  агрегатами.
- Canonical digest: SHA-256 над RFC 8785 JCS representation, исключая само
  поле digest по schema-specific digest projection. Raw object bytes имеют
  отдельный content digest.
- Digest доказывает равенство bytes, но не scope, access, official status,
  applicability или authority.

### 3.3. Message envelope

Общие поля применяются по семействам, а не механически ко всем payload:

| Поле | Command | Event | Tool/provider request | Canonical record |
|---|---:|---:|---:|---:|
| contract/schema name+version | required | required | required | registry + record version |
| message/request/record identity | required | required | required | required |
| organization/ОКС/workspace/mode scope | concrete-scope required | inherited exact scope | required | owner scope required |
| aggregate/expected version | mutation commands | aggregate event | if mutating | entity version |
| actor/service identity | at least one | producer service | caller+service | provenance |
| authority reference | protected command | originating decision ref | required for protected call | transition decision |
| purpose/classification | required | required | required | classification/retention policy |
| idempotency | command required | message id dedup | submit/side-effect required | external natural-key uniqueness |
| correlation/causation | correlation required | both required | correlation required | provenance links |
| pinned policy/rules | operation-dependent required | copied from cause | required where applicable | decision/evaluation record |
| evidence/uncertainty | when semantically applicable | references only | response completeness | material result required |
| requested side effects | command explicit | none implicit | submit/cancel explicit | receipts/result refs |
| retention/provenance/digest | required | required | required | required |

Unknown fields are rejected at authority, canonical-state and external-egress
boundaries. No parser may silently coerce incompatible types, strip a scope
field or substitute a default policy/rule version.

## 4. Commands и outcomes

`CommandEnvelope` carries exact scope, requested transition, expected aggregate
version, authority context, evidence, idempotency key and explicit side effects.

Idempotency identity is `(scope, command handler, idempotency_key)`. The handler
also compares semantic input digest:

- same key + same digest + completed outcome → `duplicate_completed` with
  `original_outcome_ref`;
- same key + different digest → `IDEMPOTENCY_CONFLICT`;
- wrong `expected_version` → `CONCURRENCY_CONFLICT`;
- transport accepted or queued → at most `accepted_pending`;
- domain completion → `accepted_completed` and canonical result reference;
- post-acceptance failure → `accepted_failed` with typed errors and side-effect
  states;
- rejected before acceptance → `rejected`.

`accepted_pending` is never a successful domain outcome. An unresolved external
side effect remains `unknown` or failed and requires reconciliation; it cannot
be converted into success by retry count.

## 5. Domain и integration events

`DomainEvent` is emitted after authoritative commit. `IntegrationEvent` is an
allowlisted/redacted projection of a committed event and identifies destination,
source event and redaction profile.

- Ordering is guaranteed only by `(aggregate_id, aggregate_version)`.
- Delivery is at-least-once. Consumer deduplicates by message identity and
  semantic digest.
- No global order and no exactly-once promise.
- OutboxRecord, InboxReceipt and DeliveryAttempt are operational ledgers.
- Retry preserves message identity; a materially changed payload receives a new
  identity and causation link.
- Exhausted or unsafe delivery enters quarantine/DLQ with typed error.
- ReconciliationRecord resolves canonical-versus-projection divergence; an
  event is never used to reconstruct unverified canonical state implicitly.

## 6. Sources и evidence

The source family covers admission, `SourceArtifact`, immutable
`SourceVersion`, `SourceLocator`, separate `PhysicalObject` byte identity,
`AcquisitionRecord`, `ExtractionAttempt/Record`, `EvidenceLink`, `EvidencePack`,
`EvidenceCapsule`, assertion trace and archive/import lineage.

Admission records source class, scope, classification, retention, acquisition
identity and integrity. A new byte sequence creates a new PhysicalObject and a
new SourceVersion; a digest collision or mismatch blocks admission.

Every evidence reference is either platform-scoped or carries the same
`workspace_id` as its consumer. `SourceLocator` identifies a page, region,
structural unit, cell/range, entity or byte range and may carry fragment digest.
EvidencePack is a frozen manifest of evidence links plus gaps/conflicts; an
EvidenceCapsule is a content-minimized, purpose-specific export with its own
authorization and retention fate.

Official source → SourceVersion → NormativeDocument → NormativeEdition →
StructuralUnit → KnowledgeAssertion → RuleEvidence → RuleVersion remains the
required platform provenance chain. Withdrawn editions stay addressable but
are not auto-applicable.

Archive import verifies package lineage and always creates a new workspace and
new scoped identifiers with an explicit mapping. It cannot revive the original
workspace identity.

## 7. Candidate, validation, confirmation и Fact

`CandidateVersion` contains field-level values, locators, evidence, origin and
optional model self-confidence. Confidence is diagnostic only.

`ValidationResult` records validator profile, status and typed failures.
Targeted repair creates a new CandidateVersion linked to the previous version;
it never mutates the original. A `validated_candidate` must cite at least one
validation result, but is still not a fact.

`ConfirmationDecision` requires explicit authority, ConfirmationPolicy,
validation results and evidence. Only a confirmed decision can authorize a new
`WorkspaceFactVersion`. A Fact records the decision, authority and evidence;
its schema intentionally has no model-confidence field.

Forbidden transitions:

- confidence ≥ threshold → Fact;
- transport/provider success → Fact;
- agreement of several models → Fact;
- validator success without confirmation authority → Fact;
- human identity without applicable grant/qualification → Fact.

`Uncertainty` and `Conflict` are first-class versioned records. Indeterminate
input blocks decisions governed by fail-closed policy; it is not `false` and is
not silently omitted.

## 8. Deterministic rules and Knowledge Tool Gateway

### 8.1. Rule contracts

Applicable-rules request pins workspace, confirmed inputs, applicable editions,
RuleSetVersion and policies. Response distinguishes applicable,
not-applicable and indeterminate rules.

`RuleEvaluation` records exact RuleVersion, pinned RuleSetVersion, confirmed
input refs, source/edition refs, typed output and a separate `RuleTrace`.
`RuleTrace` includes policies, evidence, applicability basis, normalized
units/CRS, calculation steps, missing inputs, uncertainties, conflict policies,
evaluator binding and deterministic fingerprint.

An inactive/unavailable RuleVersion yields `RULE_UNAVAILABLE`. Workspace rule
versions cannot overwrite platform rules; they are explicit workspace records
with conflict group/policy and qualified human fallback. Controlled RuleSet
upgrade requires impact preview, compatibility result, authority and a new pin;
no rolling upgrade occurs.

### 8.2. Knowledge Tool Gateway

Final tool names:

1. `knowledge.search`;
2. `knowledge.get_source_fragment`;
3. `knowledge.get_applicable_rules`;
4. `knowledge.trace_assertion`;
5. `knowledge.explain_conflict`;
6. `knowledge.get_required_documents`.

Every request carries workspace, purpose, authorization decision and exact
versions where applicable. Every response returns status, typed results,
EvidencePack, editions, applicability, gaps, conflicts and uncertainties.
Pagination is allowed only for bounded search/result lists and is cursor-based.

The model receives neither SQL nor unrestricted object-storage access. Source
fragment retrieval uses scoped locators and authorization; digest alone is not
a retrieval capability.

## 9. Provider-neutral VLM execution

Provider contracts cover capabilities, health, submit, poll, cancel, routing,
authorization, budget reservation, ExecutionAttempt, ProviderExecutionResult,
validation, targeted repair, fallback, cost reconciliation and terminal
outcome.

Routing evaluates classification, destination/provider/model/profile allowlist,
provider terms, retention, cost, qualification and workspace egress policy.
For an external route any `UNSET`, `BLOCKED`, expired or incompatible policy
causes `deny/POLICY_BLOCKED`. Fallback that changes provider, destination,
classification or cost envelope requires a new authorization and budget
reservation.

ProviderExecutionResult stores provider/model identity, raw artifact reference,
usage/cost observation, finish state and diagnostic output. CandidateBuilder is
a separate deterministic boundary that creates CandidateVersion. Validation
and repair remain separate. Terminal outcome never confirms a WorkspaceFact.

Qwen3.8-27B is the intended primary local profile and external execution is
provider-neutral. Contract semantics do not depend on MLX, Polza.ai, model
revision or provider-specific HTTP.

## 10. Storage and synchronization

`ScopedObjectReference` identifies object identity/version, object class,
platform or workspace scope, storage adapter, exact content digest and an
access-capability reference. Supported logical classes include immutable source,
platform object, workspace artifact, archive package and recovery object.

Put/get/head/list/delete are adapter operations with explicit scope,
authorization, expected digest/version and idempotency. Delete is prohibited
outside an approved lifecycle DeletionPlan. AdapterReceipt reports observed
state, bytes/digest when applicable and residue. StorageAdapterVerification
aggregates receipts; silent archive/purge success is forbidden.

Cross-workspace physical deduplication of project blobs is prohibited.
Platform NTD/template objects and workspace objects never share an unrestricted
content-addressed reference. Same digest across workspaces remains two logical
and physical scoped objects.

Offline/field synchronization uses SyncEnvelope, SyncAck and
ReconciliationRecord. It never applies timestamp/last-write-wins. Conflicting
aggregate versions produce `RECONCILIATION_REQUIRED`; no foreign workspace
batch, context or cache may be attached.

## 11. Lifecycle, archive, reset and destruction

Lifecycle commands are idempotent, expected-version guarded and authority
checked:

`freeze → finalize → export → archive → archive verification → deletion-plan
preview → dual authorization → purge adapters → residue verification →
DestructionAttestation → RESET_VERIFIED/destroyed`.

- Close/freeze/finalize do not delete content.
- Archive success requires manifest, immutable object identities/digests,
  compatibility metadata and verification evidence.
- LegalHold blocks purge regardless of process progress.
- ArchiveImport creates a new workspace and explicit source→target ID map.
- DeletionPlan enumerates every canonical, object, projection, raw VLM, backup,
  WAL/PITR/snapshot and external-provider residue adapter.
- Each adapter produces a receipt; missing/failed/indeterminate receipt blocks.
- DestructionAttestation is append-only and content-minimal. `verified=true`
  requires deletion plan, all receipts, residual scans, dual authority and
  verifier identity.
- Reset/destroy cannot complete without verified attestation.

Post-reset audit retains only permitted identities, timestamps, policy/contract
versions, result codes and non-reconstructive digests. Source fragments,
prompts/responses, names, document content and live workspace locators are
forbidden.

## 12. Authorization and audit

AuthorizationRequest contains identity, requested capability, concrete scope,
purpose, classification, subject, side effects and pinned policy versions.
AuthorizationDecision is immutable `allow` or `deny`, with reason codes,
effective interval and decision digest. Missing, expired, ambiguous or
incompatible policy yields deny.

Grant and professional qualification are separate versioned records. A grant
does not prove professional qualification; qualification does not imply a grant.
ConfirmationPolicy identifies which authority can confirm each fact/result
class. Segregation of duties is checked for RuleVersion approval, template
activation, professional review, external egress and destruction.

Service, model, queue, integration and storage identities can hold technical
capabilities only. They cannot inherit human authority, approve rules, confirm
facts, assign signers, finalize documents or authorize destruction.

AuditRecord is append-only and content-minimal. It records who/what/when/scope,
operation, decision/result codes, correlation, pinned versions and diagnostic
reference. It does not duplicate project payload or evidence content.

## 13. ID Generation & Template Platform

Contracts distinguish:

`TemplateSource → TemplateVersion → TemplateQualification →
TemplateActivationDecision → BindingPlan/EvidenceBinding → GenerationRequest →
GenerationRun → FieldResolution → RenderArtifact/ValidationReport →
GeneratedDocumentCandidate → PrintValidationResult →
ProfessionalReviewDecision → FinalizedDocument → ExportPackage`.

TemplateSource is acquired bytes and provenance. TemplateVersion is an
immutable source or parameterized derivative with lineage. Activation requires
qualification for exact format, renderer/font/toolchain and applicable use; it
does not establish official form status without evidence.

Generation is stateless: each GenerationRun starts from the pinned immutable
TemplateVersion and creates one fresh document object. Reusing a previously
filled document as mutable state is forbidden. Every field resolution records
binding rule, typed value, evidence, authority, renderer action and outcome.

Format semantics remain explicit:

| Format | Contract requirements |
|---|---|
| DOCX | content controls/merge fields/runs/tables/sections, font and pagination qualification |
| XLSX | cells/ranges/names/formulas/print areas, row/column layout and calculation policy |
| fillable PDF | exact AcroForm field identity, appearance regeneration and flattening/signature policy |
| non-fillable PDF | overlay coordinates, page boxes, fonts, clipping and canonical render comparison |
| DXF/SVG/PDF scheme | geometry source/version, CRS/units/precision, layer/style profile and canonical output render |

File-open success means only that bytes were produced. `print_ready` requires
qualified canonical renders, layout/overflow/clipping/font/page checks and no
blockers. Finalization additionally requires exact candidate digest,
professional review/authority and immutable FinalizedDocument. Filled
workspace document never becomes a platform template. Promotion creates a new
sanitized platform identity after anonymization, applicability and regression
evidence, with no live workspace link.

## 14. Geometry contracts

GeometrySource/Version identifies design or confirmed as-built origin and exact
evidence. GeometryContext pins CRS/reference frame, units and PrecisionProfile.
TransformationCalculation records source/target frames, parameters, algorithm,
inputs, outputs and deterministic fingerprint. ToleranceEvaluation pins rule,
tolerance policy, measurement uncertainty and outcome.

ExecutiveSchemeEligibility is `eligible` only when all required design and
confirmed as-built geometry, CRS/frame, units, precision, transformations,
tolerance evaluations and evidence are valid and all geometric conflicts are
resolved by qualified authority. VLM/OCR output may create a Candidate for
review, never geometry source or confirmed observation.

## 15. Four modes and typed product deliverables

Every ModeExecution contract contains execution request, input manifest,
required source classes, pinned policy/rules, progress, blockers,
uncertainties, draft deliverables, validation and terminal outcome.
`ModeExecutionTerminalResult` freezes those pins and references. Blocked and
completed-with-declared-gaps are explicit outcomes, not transport failures.

| Mode | Required contract emphasis | Typical typed results |
|---|---|---|
| Tender | contract/PD/RD/source completeness, applicable rules, commercial/legal authority | disagreement protocol, revised contract, PD/RD analysis, missing work/material finding, clashes |
| Support | confirmed work/material/control/measurement chain and ID completeness | ID document, executive scheme, findings, export/archive manifest |
| Audit | frozen evidence/rules/policies and reproducible traces | audit finding, PD/RD/ID/geometric findings |
| Restoration | archive/import lineage, provenance gaps, controlled reconstruction | restoration finding, recovered typed deliverables with declared gaps |

Typed deliverables are distinct: disagreement protocol, revised contract,
PD/RD analysis, missing-work/material finding, constructive clash, geometric
clash, executive scheme, ID document, audit finding, restoration finding,
export manifest and archive manifest. `typed_content` must be governed by the
specific contract key; one universal unstructured `document` is prohibited.

`ProductReadiness` requires E2E evidence for all four modes, R1/R2/R3 acceptance
evidence and shared-kernel invariant evidence. One successful mode or generated
file cannot set `product_ready`.

## 16. Error taxonomy

Machine-readable definition:
[`error.schema.json`](../../contracts/v0.1/schemas/error.schema.json).
Every error has stable code, category, severity, retryability, terminal flag,
scope, component, operation, optional field/page/object locator, evidence refs,
safe human message, diagnostic reference and remediation contract.

| Category | Stable codes | Default semantics |
|---|---|---|
| Contract/schema | `CONTRACT_INVALID_SCHEMA`, `CONTRACT_INCOMPATIBLE_VERSION`, `CONTRACT_UNKNOWN_VERSION` | reject; never coerce |
| Authority/policy | `AUTH_UNAUTHORIZED`, `POLICY_BLOCKED`, `CLASSIFICATION_AMBIGUOUS` | deny/fail closed |
| Scope | `SCOPE_VIOLATION`, `WORKSPACE_MISMATCH` | terminal for current request; security audit |
| Concurrency/idempotency | `CONCURRENCY_CONFLICT`, `IDEMPOTENCY_CONFLICT` | caller re-read/reconcile; no LWW |
| Source/evidence | `SOURCE_UNAVAILABLE`, `SOURCE_INTEGRITY_MISMATCH`, `EVIDENCE_MISSING` | retry only when source availability permits; integrity mismatch blocks |
| Candidate/decision | `CANDIDATE_INVALID`, `VALIDATION_BLOCKED`, `DECISION_INDETERMINATE` | remains Candidate/uncertainty; no Fact |
| Rule | `RULE_UNAVAILABLE` | no substitute/latest; block evaluation |
| Provider/budget | `PROVIDER_FAILURE`, `BUDGET_EXHAUSTED` | bounded retry; fallback requires policy/authority |
| Storage/integrity | `STORAGE_FAILURE` | no silent success; reconcile receipts |
| Render/geometry | `RENDER_PRINT_FAILURE`, `GEOMETRY_BLOCKED` | no finalization/scheme eligibility |
| Archive/import | `ARCHIVE_FAILURE`, `ARCHIVE_IMPORT_FAILURE` | no archive/import success |
| Reset/residue | `RESET_INCOMPLETE`, `RESIDUE_DETECTED` | no RESET_VERIFIED/destroyed |
| Reconciliation | `RECONCILIATION_REQUIRED` | explicit human/policy workflow; non-terminal system state |

`retryable` describes technical safety, not authorization to retry. Retry cannot
change scope, provider, budget, payload or authority. Safe message contains no
secret/project content; detailed diagnostics stay behind scoped access.

## 17. Versioning, compatibility and schema fingerprints

1. Contract and schema versions use SemVer independently but are pinned
   together in persisted messages/results.
2. Patch: clarification or constraint-equivalent correction proven compatible.
3. Minor: additive optional field or new separately negotiated contract.
   Adding enum members is compatible only for consumers declaring unknown-value
   handling; otherwise it is breaking.
4. Major: removed/renamed/required fields, changed meaning/type/scope,
   tightened accepted historical payload, authority or retention change.
5. Historical schemas and fixtures are immutable. Correction creates a new
   version and `supersedes` link.
6. Producers emit only versions accepted by the consumer compatibility matrix.
   Consumers reject unknown/incompatible versions with stable errors.
7. Persisted `latest`, implicit current policy/rules or mutable schema URL are
   prohibited.
8. Deprecation requires announced interval, replacement, compatibility tests
   and inventory of persisted consumers. Retirement never deletes historical
   schema needed to interpret retained records.
9. Event upcasting is an explicit, pure, version-pinned adapter with source and
   target digests. It does not imply event sourcing and cannot invent missing
   authority/evidence.
10. Downgrade never silently drops security, scope, provenance, retention or
    authority fields.

Schema fingerprint is exact SHA-256 of the checked-in schema bytes and is stored
in registry. Payload digest uses the schema-declared JCS digest projection.
Changing whitespace changes schema fingerprint but not a payload's canonical
semantic digest.

## 18. Machine-readable coverage

| Schema resource | Critical boundaries |
|---|---|
| `common` | identifiers, concrete scope, identities, authority, policy/rules, evidence, locator, provenance, envelope |
| `error` | typed error taxonomy |
| `message` | CommandEnvelope/outcome, Domain/IntegrationEvent, delivery record |
| `source-evidence` | physical/source version, extraction, EvidenceLink/Pack, archive lineage |
| `candidate-fact` | CandidateVersion, validation, confirmation, WorkspaceFact, uncertainty/conflict |
| `rules-knowledge` | RuleEvaluation, RuleTrace, controlled upgrade, six Knowledge Gateway tools |
| `vlm-execution` | provider-neutral request/result/routing/budget/repair/fallback/terminal |
| `storage-sync` | scoped object, adapter operation/receipt, offline sync/reconciliation |
| `lifecycle` | archive/import, deletion plan, DestructionAttestation |
| `authorization-audit` | request/decision/grant/legal hold/content-minimal audit |
| `generation` | template lineage/activation, binding, run/render/validation, candidate/finalization/export |
| `geometry` | geometry context/version, transform, tolerance, scheme eligibility |
| `mode-deliverable` | four modes, terminal result, typed deliverables, ProductReadiness |

The compact kernel formalizes critical boundaries; registry keys cover the
full family where several commands share one structural envelope. Future
implementation may split a schema fragment without changing semantics, using a
compatible minor or breaking major as required.

The architecture-only worktree contains no installed Draft 2020-12 validator,
and no dependency was installed for this gate. A dependency-free verification
outside the tracked tree checked JSON syntax, unique `$id`, local `$ref` and
JSON Pointer resolution, registry fingerprints/passports, all declared schema
keywords used by fixtures, valid acceptance, invalid rejection and round-trip.
This proves internal consistency of the published bundle. Qualification of the
future implementation's standards-conformant validator, including the official
Draft 2020-12 test suite and RFC 8785 implementation, is a mandatory G-04
contract test and is not claimed by G-03.

## 19. Fixtures and rejection semantics

Fixture manifest:
[`fixtures/manifest.json`](../../contracts/v0.1/fixtures/manifest.json).
Fixtures are anonymized synthetic records and contain no project, secret,
provider or production-policy data.

- `schema` fixtures are checked against an exact `$id` + JSON Pointer.
- `semantic` invalid fixtures exercise cross-record/canonical-state invariants
  not reducible to single-document JSON Schema.
- Every invalid fixture declares expected stable error code and rejection
  reason.
- Round-trip means parse → validate → deterministic serialize → parse → validate
  while preserving semantic content and digest projection; it does not permit
  type coercion or unknown-field deletion.

## 20. Normative contract-test plan

| Test class | Required assertions |
|---|---|
| Producer | every emitted record validates exact pinned schema; digest/provenance complete |
| Consumer | declared version range; unknown fields/versions fail closed |
| Compatibility | additive/breaking classification, previous valid corpus, downgrade rejection |
| Round-trip/property | deterministic serialization, no coercion, boundary values, stable fingerprint |
| Idempotency | same key+digest replay; changed digest conflict; side-effect receipts stable |
| Optimistic concurrency | stale expected version rejected; no last-write-wins |
| Scope isolation | org/ОКС/workspace composite mismatch rejected in messages, refs, batch, cache and sync |
| Provenance | every material assertion/result reaches SourceVersion/Evidence and authority where required |
| Candidate→Fact | confidence/model consensus/provider success never confirms; exact ConfirmationDecision required |
| Rules | active exact RuleVersion and pinned RuleSetVersion; indeterminate blocks; controlled upgrade only |
| Egress | absent/UNSET/BLOCKED/expired/incompatible policy denies; fallback reauthorizes |
| Provider | result/candidate/fact separation; budget reservation/reconciliation; bounded repair |
| Storage | digest not access; no cross-workspace dedup; adapter receipts and integrity |
| Archive/import | manifest integrity; import always new workspace and scoped mapping |
| Reset/destruction | LegalHold; complete plan/receipts/residual scans; verified attestation; content-free audit |
| ID generation | fresh document/run; exact evidence bindings; format-specific render; print and professional gates |
| Geometry | CRS/units/precision/confirmed evidence; deterministic transformation/tolerance; VLM rejection |
| Four-mode E2E | Tender/Support/Audit/Restoration use same kernel and typed terminal results |
| ProductReady | all four mode evidence + R1/R2/R3 + cross-mode invariants; any missing item blocks |

Before implementation authority, these are normative test contracts. G-04+
must materialize producer/consumer/property tests; passing current fixture
validation does not claim runtime or production readiness.

## 21. Migration mapping: archived prototype contracts

The canonical re-baseline has no active `src/`, `tests/` or `tools/`. Therefore
there is no current Python public API to bless. The archived prototype is a
future selective-port input only, per re-baseline manifest and accepted
migration maps.

| Archived element | Target | Disposition | Contract conflict/action |
|---|---|---|---|
| deterministic identifiers | typedId + registered deterministic identity policy | preserve principle, rework | retain canonicalization; remove path/pilot namespace authority |
| Candidate classes | CandidateVersion/Validation/Confirmation/Fact | replace boundary | hard-coded `CONFIDENCE_THRESHOLD=0.8` rejected; no confidence confirmation |
| `RuleTrace` | full RuleTrace schema | preserve and extend | add ruleset/policy/evidence/applicability/units/fingerprint |
| NTD edition models | SourceVersion/NormativeEdition/rule provenance | selective port | preserve temporal editions; add platform scope, official provenance, no overwrite |
| corpus scanner/hash | source admission/acquisition | adapter later | digest useful; path is not identity; add workspace/classification/retention |
| VLM runners/adapters | provider contracts | rewrite behind adapter | remove local-path/provider format leakage; add policy/budget/raw-artifact lifecycle |
| extraction mode/text layer | Candidate construction | selective port | preserve native-first idea; add field evidence and validator/repair contracts |
| bridge | source→Candidate mapper | replace pilot mapping | remove `01_ПД/02_РД`, TM-35 path IDs, packed locators and RuleSet misuse |
| pilot CLI/config/tools | future test/ops client only | retire from product | no hard-coded corpus/model/mass run bypass |
| absent workspace persistence | all scoped contracts | new work after authority | complete architectural gap; do not adapt unsafe no-scope records |

No archived class becomes canonical merely because a legacy test passed.

## 22. Legacy conclusions used without repeated audit

| Legacy area | Preserve | Modernize | Reject |
|---|---|---|---|
| PostgreSQL/pgvector/FTS | projection/use-case evidence | canonical/projection separation and scoped indexes | graph/vector/FTS as SoR |
| NormativeClause/KAG/Evidence Graph | provenance and typed-link ideas | NormativeEdition/Assertion/Evidence/Rule contracts | unversioned clauses, opaque graph authority |
| rules/temporal editions | temporal/version principles | pinned RuleSet and controlled upgrade | rolling latest/hard-coded applicability |
| lifecycle/reset/archive | manifest/receipt/restore concepts | complete adapter inventory and attestation | close=delete, success without residue proof |
| ISGenerator/ISUID/id-track | format adapters, mappings, test evidence | qualified Template Platform contracts | production-readiness inference from files opening |
| DOCX/XLSX/PDF/DXF | format-specific technical knowledge | source/version/qualification/render/print contracts | universal mutable template/document blob |
| 25 YAML/catalogs/mappings | evidence of reusable mapping content | intake, schema, provenance, qualification | official/applicable status by filename/count |
| Qwen ID schemas | candidate schema ideas | provider-neutral Candidate boundary | model output as confirmed field/fact |
| blank forms/goldens | qualification candidates | sanitize, classify, provenance and Promotion Gate | project-filled document as platform template |
| defect outputs | negative fixture ideas | anonymized regression corpus | acceptance evidence or canonical domain state |

## 23. Comparison with interrupted draft

The old dirty worktree was read only after canonical architecture review. No
directory was copied wholesale and the old files remain unmodified.

| Draft element | Decision | Reason |
|---|---|---|
| 13-schema compact decomposition | accepted/reworked | good critical-boundary coverage; moved to stable URN and extended |
| common envelope and scope checks | reworked | retained explicit fields; added concrete scope union, policy/rules and pagination definitions |
| Command/outcome/event schema | accepted/reworked | retained semantics; fixed namespace and registry integration |
| Candidate/Fact schema | reworked | required validation refs for validated Candidate; added explicit schema-negative Fact confidence case |
| RuleEvaluation embedded trace | replaced | RuleTrace became independently addressable and pins ruleset/rule/inputs/evidence/applicability/fingerprint |
| generation schema | reworked | added TemplateSource/Version/Activation, EvidenceBinding, GenerationRequest, RenderArtifact, ValidationReport |
| mode schema | reworked | added immutable ModeExecutionTerminalResult |
| HTTP-like `schemas.asd-kontur.local` IDs | rejected | implied a service that does not exist; offline stable URNs chosen |
| schema-only file registry | replaced | registry now covers all contract families and full inherited passports |
| valid/invalid examples | accepted/reworked | retained only explicit anonymized files, added manifest and Candidate/Fact/finalization/mode vectors |
| semantic negative vectors | accepted | correct for cross-record invariants; now carry expected code/reason in manifest |
| premature `Accepted`/G-03 PASS in incomplete document | rejected | draft stopped after Knowledge Gateway and omitted required families/tests/versioning/migration |

## 24. Accepted decisions within delegated authority

| Decision | Basis |
|---|---|
| JSON Schema Draft 2020-12 | supports `$defs`, conditional constraints and `unevaluatedProperties`; transport-neutral |
| Stable offline URN namespace | exact immutable identity without pretending a registry service exists |
| SemVer + exact persistence pin | controlled compatibility and no mutable latest |
| RFC 8785 JCS + SHA-256 digest projection | deterministic cross-language payload hashing; implementation qualification still required |
| Compact schema kernel + complete logical registry | proves critical boundaries without hundreds of empty schemas |
| Schema vs semantic negative fixtures | JSON Schema cannot prove cross-record canonical-state invariants alone |
| Family-passport inheritance | avoids repeated metadata while keeping every stable key resolvable to a full passport |
| Events at-least-once/per-aggregate ordering | consistent with accepted process architecture; no false exactly-once/global-order claim |
| No new ADR | choices refine accepted G-03 scope and do not reverse a cross-cutting ADR |

These decisions preserve four modes, three product results, platform/workspace
isolation, Candidate-only AI boundary and accepted RD/DR/HV/IA/TA/LDM/DPP.
They do not establish production policy values, official template status,
normative applicability, professional grants, provider terms, budgets or
qualification thresholds.

## 25. Gate decision and remaining blockers

G-03 acceptance is **PASS** because:

- all mandatory contract families have stable registry keys and normative
  state/error/scope/provenance semantics;
- critical boundaries have Draft 2020-12 machine-readable schemas;
- valid and hostile/invalid fixtures have exact validation/rejection mapping;
- versioning, immutable schema identity, compatibility, deterministic digest,
  idempotency and concurrency are specified;
- negative-scope, Candidate/Fact, ruleset, egress, lifecycle, generation,
  geometry, four-mode and ProductReady tests are normative;
- future implementation can bind to these contracts without changing the
  architecture.

G-03 PASS is an architecture gate, not implementation or production readiness.
G-02B remains `BLOCKED` for missing approved production RetentionProfile,
provider terms/processing/finite retention/region/model revision, egress and
cost instances, measured resource thresholds, renderer/font/template/model
qualification, backup/failover parameters, professional grants and other
evidence-backed values catalogued in DPP.

No ORM, DDL, migration, API, queue, repository, deployment or model execution
is authorized by this document. The next critical-path step in the accepted
Implementation Plan is G-04 Foundation Kernel, and it requires a separate
explicit implementation authority.

## 26. Immutable implementation extensions

G-06 added the separate `contracts/v1.0` content-free
DestructionAttestation schema. G-07 adds the additive `contracts/v1.1`
Harness extension for render lineage, one-workspace batch manifests,
qualification decisions and raw-artifact retention references. Neither
release mutates a v0.1 schema or changes the G-03 persisted semantics; their
registries declare exact compatibility and fingerprints.
