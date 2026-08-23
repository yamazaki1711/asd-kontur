# WP-14 pdfpipeline architecture impact assessment v0.1

- **Статус:** `Corrected WP-14 requirements; accessible evidence verified; volume coverage PARTIAL`
- **Дата:** 2026-08-23
- **Исходное evidence:**
  [Legacy pdfpipeline / Левашово audit experience](LEGACY_PDFPIPELINE_AUDIT_EXPERIENCE_v0.1.md)
- **Область решения:** требования и acceptance WP-14 Audit; без прикладного
  кода, contracts, DDL и migrations.

## 1. Решение в одном абзаце

Legacy-модель `one database document row ≈ one file, bytes in S3, attributes in
mutable JSON/status columns` не принимается как архитектура ASD-КОНТУР.
Canonical модель уже лучше разделяет stable semantic identity, immutable
version, physical bytes/object receipt, exact locator, render/attempt,
Candidate/Fact, authority, workspace scope and retention. WP-14 уточняется
тремя связанными, но не смешанными оценками — `Document Delta`, `Causal
Readiness Delta` и `Package/Signing/Handover Readiness` — и обязательной
document/container/page reconciliation. Новый ADR не
нужен: решение является уточнением уже принятых IA/LDM/HV/RD, а не сменой
cross-cutting architecture.

## 2. Проверяемая causal hypothesis

Audit оценивает цепочку только в пределах exact applicable rules, договора,
customer regulation, WorkType/Material/control requirements и scope:

```text
МТР / партия
→ входной контроль
→ решение о допуске
→ применение к работе / конструкции
→ контроль выполнения
→ обязательные доказательства
→ комплектность ИД
→ professional review / подписание
→ предъявленный объём
→ КС
→ payment readiness
```

Разрыв не превращается автоматически в юридический вывод. Он создаёт typed
`gap`, `conflict`, `blocker`, `indeterminate` или `uncertainty`, exact affected
entities и downstream impact. Restoration остаётся отдельным процессом.

## 3. Сравнение решений

| Наблюдение | Evidence | Какую проблему решало legacy | Результат на Левашово | Текущая модель ASD-КОНТУР | Решение | Изменение WP-14 |
|---|---|---|---|---|---|---|
| File/path использовался как document intake identity | `ingest.py`, `001_core_schema.sql` | Быстро зарегистрировать массовый corpus | Rename/container split/version создавали ambiguous identity | `SourceArtifact` stable identity, immutable `SourceVersion`, external locator as attribute | Modernize | Audit inventory различает file occurrence, semantic source and version. |
| SHA-256 применялся для global dedup | `ingest.py`, `datamining.md` | Сократить bytes/cost | Duplicate bytes теряли самостоятельную authority/scope; shared content путал rows | `PhysicalObject` отделён от source identity; digest не capability; no cross-workspace project dedup | Reject identity semantics; preserve integrity check | Duplicate bytes никогда сами не закрывают two requirements и не дают cross-scope access. |
| Один physical PDF содержал много documents | `papka_200_split_final_report.md`, `container_worker.py` | Извлечь logical documents из сканов | Over-segmentation и invalid boundaries | Exact `SourceVersion`/`SourceLocator`, immutable RenderArtifact/attempt lineage | Modernize | Boundary inventory: physical container → exact page ranges → logical source occurrences; gaps/overlaps/duplicates explicit. |
| Logical row мог ссылаться на общий container blob | `datamining.md`, `status_report_02082026.md` | Не копировать bytes после split | 58% rows в одном измерении имели materialization gap | Source version/object receipt/locator are separate and integrity-verifiable | Reject implicit shared-content read | Audit validates resolvability and exact bytes/locator, not row existence. |
| JSON metadata и mutable status | source/SQL/dashboard | Быстро расширять types и вручную исправлять | Reclassification не добавляла required type fields; history/authority weak | Typed immutable versions, schema pins, ConfirmationDecision, audit | Modernize | Classification/content/authority checks form separate delta dimensions; correction appends version. |
| Sliding page windows + overlap | `container_worker.py` | Обработать большие raster PDF | Useful scale, but boundary duplication/gaps and false success | G-07 immutable item/attempt/render and batch reconciliation | Preserve mechanism, modernize proof | Per-page/region terminal receipt; no aggregate success until exact inventory reconciled. |
| Provider JSON parsing and escape repair | `providers.py`, `worker_lib.py` | Tolerate malformed outputs | Malformed/partial responses could enter later logic | Contract Pack exact schema, typed ProviderFailure, no silent coercion | Reject silent repair | Schema-invalid/partial/truncated remains failure; unprocessed locators remain open. |
| Mutable queue reset/retry | `LEVASHOVO_15.md`, reports | Resume interrupted work | Reprocessed completed acts, duplicate rows/cost | Immutable attempts, idempotency, reconciliation | Modernize | Retry same semantic item cannot create duplicate source/finding; unknown outcome reconciled. |
| Process counters defined `FINAL` | `LEVASHOVO_16.md` | Simple operations monitoring | Later steps failed while global status stayed final | Canonical state + receipts; events/projections not SoR | Reject | Audit corpus readiness is reconciled from canonical inventory, not worker/dashboard status. |
| Confidence review | `worker.py`, dashboard | Prioritize manual queue | Systematic mismatches survived high confidence | Candidate-only boundary, deterministic validators, authority | Reject as truth; preserve prioritization only | Confidence may order queue but cannot close Document Delta or confirm fact. |
| Direct SQL/sheet correction | dashboard source and passport | Rapid PTO cleanup | Weak version/authority/audit semantics | Typed commands, optimistic concurrency, immutable decisions | Modernize | PTO correction creates new version, decision, audit and projection update. |
| File-count/stage progress | dashboard passport/status | Give Customer visibility | Appeared advanced while incoming control/signing gaps remained | Rebuildable projections over canonical facts/requirements | Modernize | Customer dashboard reports evidence coverage and downstream readiness with denominators and unknowns. |
| AOSR/AORPI label confusion | reclassification reports | Common taxonomy for search | False completeness and missing type-specific fields | Versioned RequiredDocumentType/DocumentRequirement and exact rules | Modernize | Unknown/conflicting type is explicit; type name alone cannot cover requirement. |
| Missing attachment references | delta/search reports | Link acts to evidence | 0/25 sample references resolved; absence ambiguous | EvidenceLink and DocumentCoverage with exact locator | Preserve problem, modernize relation | Missing link and missing document are distinct findings; Audit may search but cannot infer coverage. |
| Raw/object integrity drift | `raw_integrity_gap_06082026.md`, `LEVASHOVO_16.md` | Preserve corpus bytes | DB referenced missing S3 objects; local residues existed | ObjectReceipt, adapter inventory, lifecycle residual verification | Modernize | Audit distinguishes unavailable, missing, residue and integrity mismatch; no false negative. |
| Dashboard/PTO projections | passport and UI source | Coordinate large recovery effort | Operationally useful, canonical coupling unsafe | IA projection plane + typed commands | Preserve UX need | Define Customer and PTO projection contracts, no UI implementation in WP-14. |
| Incoming-control chain | TZ/status/delta reports + owner context | Determine ID readiness | Early gaps propagated to unsigned/unusable packages | WP-11/WP-13 MTR, ControlOperation, DocumentRequirement, IDPackage, PresentedVolume/KS/PaymentClaim | Preserve causal need | Add Causal Readiness Delta and affected-entity traversal with three-valued applicability. |
| Package/tom/book identities and many-to-many document membership | `TZ_Levashovo_v9_0.md` §§4.2/4.3/11.12 | Assemble physical ID packages without duplicating document sources | Package readiness and document discovery were conflated | `IDPackage`, `DocumentCoverage`, `FinalizedDocument`, `SourceVersion` cover parts but lack explicit physical membership semantics | Modernize | Add versioned Package, Volume/Book and ordered DocumentMembership; section remains separate. |
| Physical signing/handover lifecycle | `TZ_Levashovo_v9_0.md` §§11.12.3–11.12.6 | Track copies, registers, signatures, return, re-presentation and acceptance | Filled folder could appear ready before signature/handover acceptance | Professional review/signature evidence exist, but WP-14 had no separate aggregate | Modernize | Add Package/Signing/Handover Readiness with distinct states and denominator. |
| Stop-code requested external work | `TZ_Levashovo_v9_0.md` stop-code/ActionRequest sections | Route blockers to responsible party and track closure | Mutable status could hide who proved closure | Authorization/SoD, immutable decisions and audit already exist | Modernize | Typed ActionRequest; initiator/executor/verifier, evidence closure, deadline/escalation/supersession. |
| `(signed + unsigned) / total` metric | legacy VK metric definition | Show documents distributed by signing state | Produced 100% even with zero signed when all items classified | Versioned rebuildable projections | Reject as readiness | Separate found/signed/accepted denominators; blockers and counts beside percentages. |
| Latest revision wins | legacy version rule | Simplify operator selection | Could silently replace authority and hide conflicts | Immutable versions, effective intervals, explicit supersession | Reject | No LWW; authoritative selection requires decision/authority/reconciliation. |
| Reclassification changed only document label | AOSR/AORPI correction evidence | Repair taxonomy quickly | Required attrs of new type remained absent | Candidate/Fact and typed schema/version validators | Modernize | Reclassification appends version, reruns validators and creates targeted repair/ActionRequest. |
| Archive/reset absent from legacy core | SQL/source review | Not a primary legacy concern | Project/global rows and object residues were hard to delimit | G-06 exact adapter inventory, archive, reset verification, RLS | Reject legacy omission | Audit data/artifacts must be workspace-scoped, archived and reset through G-06. |

## 4. Document/file identity clarification

No `one document = one file` ADR is introduced.

The accepted model supports the required cases when interpreted explicitly:

- `PhysicalObjectVersion` identifies exact scoped bytes and storage receipt;
- `SourceArtifact` identifies the semantic source independently from filename;
- `SourceVersion` identifies one immutable admitted semantic version;
- `SourceLocator` identifies exact pages/regions/structural units in that
  version or its physical container;
- one physical container may contain zero, one or many logical source
  occurrences;
- a logical source version may be represented by a full object or by an exact
  locator into a parent container, with immutable derivation/materialization
  lineage;
- replacement bytes create a new `SourceVersion`; corrected classification or
  boundary creates a new typed decision/version, not an in-place rewrite;
- applications remain separate SourceArtifacts; `PackageVersion` and nested
  `VolumeBookVersion` identify assembly scope independently from section or
  physical container;
- `DocumentMembershipVersion` relates one exact document/source/finalized
  version to one or many packages/books with role, ordering, required copies,
  stage and provenance; membership never duplicates source identity;
- duplicate bytes prove equality only; document authority, role, signature,
  scope and requirement coverage remain separate.

WP-14 implementation must select a typed physical mapping for logical
occurrence/boundary lineage and prove it with contracts, persistence and
integration tests. Package/Volume/Book/Membership are minimal compatible
extensions of existing `IDPackage`/`DocumentCoverage`, not a return to legacy
folder-as-canon. That choice remains within current IA/LDM invariants.

## 5. Document Delta

For every applicable `DocumentRequirement`, Audit computes an immutable,
reproducible delta:

```text
required document/evidence
↔ found physical object/file occurrence
↔ exact logical document/source version and locator
↔ recognized content and extraction coverage
↔ classification and typed schema
↔ integrity/version/conflicts
↔ confirmed attributes
↔ applicability and evidence coverage
↔ signer/authority/signature status
```

Required dimensions:

| Dimension | Outcomes (minimum) |
|---|---|
| Discovery | `not_searched`, `not_found`, `found`, `multiple`, `unavailable` |
| Boundary | `exact`, `gap`, `overlap`, `mixed`, `out_of_range`, `unverified` |
| Processing | `not_attempted`, `partial`, `failed`, `unknown`, `complete` |
| Classification | `candidate`, `confirmed`, `ambiguous`, `conflicting`, `inapplicable` |
| Integrity/version | `verified`, `missing_bytes`, `digest_mismatch`, `superseded`, `conflicting` |
| Evidence binding | `unlinked`, `linked_unverified`, `verified`, `wrong_scope`, `wrong_subject` |
| Requirement coverage | `covered`, `partially_covered`, `not_covered`, `indeterminate`, `not_applicable` |
| Authority/signing | `not_required`, `required_missing`, `authority_unverified`, `signed_verified`, `conflicting` |

`found`, `recognized`, `classified`, `generated` and `file opens` are never
aliases for `covered` or `signed_verified`.

## 6. Causal Readiness Delta

For each scoped material batch/work/ID/presentation/payment path, Audit builds a
typed dependency evaluation over exact entity versions:

```text
MaterialBatchVersion
→ incoming-control requirements/results
→ AdmissionDecision
→ MaterialApplication / WorkInstance / confirmed WorkVolume
→ ControlOperation / Measurement / timely EvidenceLink
→ DocumentRequirement and IDPackage coverage
→ ProfessionalReviewDecision / signature evidence
→ PresentedVolume
→ KsLine / KsDocument
→ PaymentClaim readiness
```

Each edge records:

- exact subject and dependency versions;
- applicability: `applicable`, `not_applicable`, `indeterminate`;
- RuleVersion, RuleTrace, ConflictPolicy and evidence locator;
- timing/effective interval;
- authority and ConfirmationDecision where required;
- status: `satisfied`, `unsatisfied`, `conflicting`, `unknown`, `blocked`;
- downstream affected entities;
- remediation class: `evidence_search`, `professional_decision`,
  `restoration_candidate`, `unrecoverable_candidate`, `not_applicable`.

Audit reports impact; it does not create missing facts, backdate control,
approve materials, sign documents, modify KS or perform Restoration.

## 7. Package / Signing / Handover Readiness

For each exact package scope and version, Audit evaluates a third independent
delta:

```text
required documents and memberships
→ package / volume / book structure and ordering
→ registers / attachments / required copies
→ professional review
→ signer requirements, authority and signature evidence
→ handover receipt
→ returned-with-comments / re-presentation
→ acceptance decision
```

Each version pins its own denominator, exact scope, RuleSetVersion, evidence,
uncertainties, blockers, downstream impact and semantic fingerprint. Minimum
states remain distinct: `found`, `recognized`, `classified`, `evidence_bound`,
`included`, `physically_assembled`, `reviewed`, `ready_for_signature`,
`signed`, `handed_over`, `returned_with_comments`, `re_presented`, `accepted`.
Handover is not acceptance; a signed document outside a required membership
does not cover the package; a missing copy or unverified signer blocks the
relevant readiness dimension.

Package readiness does not prove Causal Readiness: a physically complete
folder can still contain an unadmitted batch or untimely evidence. Conversely,
a causal fact does not prove that required copies, signatures and handover are
complete. The three deltas may be presented together but never averaged into a
single percentage.

### 7.1. ActionRequest / stop-code model

An audit blocker may create an immutable `ActionRequestVersion` with typed
action, initiator, addressee/executor, affected version, evidence, deadline,
blocking impact, expected closure evidence and authority policy. Completion by
the executor is only `performed`; closure is a separate authorized verification
by the initiator or policy-qualified verifier. Cancellation and supersession
are decisions with audit lineage. Reclassification, queue removal or process
counter change cannot close it. Overdue/escalation is derived from exact
deadline and state; notification UI is outside WP-14.

### 7.2. Reclassification and authoritative version selection

Reclassification appends an immutable classification version, reruns the exact
type-specific validators and emits missing attributes plus targeted repair or
ActionRequests. It does not mutate prior classification or make the document
ready. A later upload/version is not authoritative until explicit supersession,
authority, effective interval, conflict detection and reconciliation succeed.
Confidence can only prioritize work; it cannot confirm classification, Fact,
signature, coverage or package readiness.

## 8. Dashboard projection requirements

### 8.1. Customer projection

Required metrics are projections with snapshot/version/freshness and explicit
denominators:

- corpus inventory and verified processing coverage;
- incoming-control coverage by batch and requirement;
- admitted/blocked/indeterminate MaterialBatch counts;
- work/evidence/ID coverage and affected structures;
- signed/unsigned/authority-unverified package counts;
- presentation, KS and payment readiness by exact scope;
- causal blockers and downstream impact;
- trend and stale/unknown portions.

No single percentage may collapse unknown/inapplicable/blocked states. Every
numerator/denominator is versioned and provenance-bound. Unsigned is never in a
signed-readiness numerator; unknown/indeterminate never adds to ready; distinct
readiness dimensions are not averaged. Critical blockers and underlying counts
remain visible beside percentages. File count can be shown only as inventory.

### 8.2. PTO projection and commands

Projection supports search, classification review, attribute correction,
document↔batch/work/control linking, missing evidence, duplicates/conflicts,
page retry, package/signing state, comments/decisions and version history.
Every mutation is a typed authorized command against expected version. Direct
canonical JSON/SQL editing is prohibited. Projection rebuild must reproduce the
same canonical fingerprint and must not emit domain changes.

## 9. Refined WP-14 DoR

WP-14 implementation may start only when all are true:

1. WP-11 common kernel and WP-13 Support entities required by the causal chain
   are canonical and migration-compatible.
2. Exact Audit scope, corpus manifest and qualification corpus are defined with
   synthetic, object-independent data.
3. Pinned Audit `RuleSetVersion`, subject-specific ConflictPolicy and authority
   profile are available; missing production values remain BLOCKED.
4. Typed semantics exist for logical document occurrence/boundary,
   classification/version conflict, extraction coverage and Document Delta.
5. Typed causal traversal covers MaterialBatch→incoming control→admission→work
   →evidence→ID→signing→PresentedVolume→KS→PaymentClaim.
6. Typed `PackageVersion`, `VolumeBookVersion`, ordered
   `DocumentMembershipVersion`, signing/handover/acceptance states and
   `ActionRequestVersion` semantics are fixed without conflating section,
   package or physical container.
7. Each of the three deltas has its own versioned denominator, exact scope,
   evidence, RuleSetVersion, uncertainty, blockers, downstream impact and
   fingerprint; no aggregate average is authoritative.
8. Audit/Restoration boundary and three-valued applicability are explicit.
9. G-07 provider partial/unknown result semantics are used; real external route
   remains G-07B/G-02B BLOCKED.
10. Workspace RLS/lifecycle/reset and G-06 adapter inventory extension are
   planned for all new Audit canonical and projection artifacts.
11. Dashboard is specified as rebuildable projection + typed commands, not UI
   or system of record.
12. Acronym/document taxonomy uses exact sourced identities; `АОПРИ` is not
    assumed equivalent to observed `АОРПИ`.

## 10. Refined WP-14 deliverables

- one Audit ModeExecution process over WP-11 kernel;
- immutable AuditScope/CorpusInventory and reconciliation report;
- Document Delta versions with exact requirement/source/locator/attempt and
  authority lineage;
- Causal Readiness Delta versions with affected-entity impact paths;
- Package/Signing/Handover Readiness versions, Package/Volume/Book ordered
  memberships and separately versioned denominators;
- typed ActionRequest lifecycle with authority-checked evidence closure;
- typed AuditFinding/Gap/Conflict/Uncertainty/Blocker;
- Customer and PTO projection models with rebuild fingerprints;
- evidence-rated AuditReport/coverage/limitations and blocking terminal outcome;
- additive contracts only for real inter-component records;
- forward migration, RLS/FORCE RLS, lifecycle fence, archive/reset coverage;
- synthetic AT-PE-43 corpus and the mandatory scenarios below.

## 11. Mandatory WP-14 acceptance scenarios

1. Thousands of files do not imply completeness.
2. Successfully recognized PDF does not imply usable evidence.
3. A found document without exact MaterialBatch link does not close incoming
   control.
4. A batch without complete applicable incoming control is not admitted.
5. A backfilled incoming-control document does not prove timely control.
6. Page processing cannot accidentally split one logical document into several
   accepted documents.
7. Provider batch/result cannot mix several logical documents or workspaces.
8. Duplicate bytes do not imply equal document identity, scope or authority.
9. Conflicting versions remain visible and no last-write-wins is used.
10. Missing АВК/АОРПИ/verification journal produces an exact causal gap only
    when required by applicable rules; unresolved `АОПРИ` terminology remains
    explicit.
11. Missing incoming-control evidence links to affected batches, work and
    structures.
12. Insufficient evidence blocks ID readiness; it does not merely reduce a
    dashboard percentage.
13. `GeneratedDocumentCandidate` is not a signed/final document.
14. Four filled folders without verified authority/signatures are not ready ID.
15. ID gap links to affected PresentedVolume, KS and payment readiness.
16. Customer progress derives from evidence coverage/readiness, with explicit
    unknown and inapplicable denominators.
17. PTO correction creates a new version and audit, preserving history.
18. Provider partial success preserves all unprocessed pages as open/failed.
19. Retry does not create duplicate sources, documents or findings.
20. Dashboard rebuild does not change canonical result/fingerprint.
21. Audit diagnoses and classifies; it does not perform Restoration.
22. Project-specific Levashovo rules/statuses do not become platform rules
    automatically.
23. All-window provider failure cannot become empty-success or `complete`.
24. Invalid/overlapping/out-of-range page boundaries block accepted inventory.
25. A logical row referencing container bytes without exact locator/materialized
    lineage is unresolved, not processed.
26. Process/dashboard `FINAL` conflicts with receipts and becomes inconsistent,
    not complete.
27. Missing object bytes and provider unknown outcome remain distinct typed
    blockers.
28. A document found in a different workspace/digest cache remains invisible
    and cannot cover the requirement.
29. Reset removes Audit corpus/findings/projections for workspace A without
    altering workspace B or platform NTD/rules/templates.
30. Identical inputs, exact versions and RuleSet produce identical delta and
    report semantic fingerprints.
31. All files found but no document signed cannot yield signed-ID or KS
    readiness.
32. All documents classified but required type-specific attributes missing
    remain not ready.
33. Reclassification creates a new immutable version, reruns validators and
    creates exact repair requirements.
34. The latest uploaded version does not win without authority, explicit
    supersession and conflict reconciliation.
35. High confidence creates neither Fact nor covered Document Delta.
36. One exact document may join several packages without duplicating source
    identity.
37. Package, Volume/Book and section remain separate identities and scopes.
38. A package missing one required copy is not handover-ready.
39. A package with unverified signer authority is not signature-ready.
40. A signed document outside the required package membership does not cover
    Package Readiness.
41. A stop-code creates a typed ActionRequest with exact affected object,
    addressee, evidence and blocking impact.
42. An executor cannot self-close a blocker when policy requires initiator or
    independent verifier confirmation.
43. ActionRequest closure requires exact evidence and authority decision.
44. Post-signing rejection appends a new state/version and preserves signed
    history.
45. Handover does not imply acceptance.
46. A projection using `(signed + unsigned) / total` as signed readiness is
    rejected; zero signed cannot display 100% signed readiness.
47. Readiness of one package does not imply readiness of the Audit scope.
48. Physical folder completeness does not prove causal VK/ID/KS readiness.
49. Dashboard rebuild changes neither canonical Package nor ActionRequest
    state.
50. Object-specific legacy stages, copy counts and registers do not become
    platform rules without Promotion Gate.

## 12. Refined WP-14 DoD

WP-14 passes only if:

- AT-PE-43 exercises Document Delta, Causal Readiness Delta and
  Package/Signing/Handover Readiness end to end;
- every result is tied to exact scope, source/version/locator, rule/policy,
  applicability, evidence, authority and reproducible fingerprint;
- partial/unavailable/ambiguous states stay visible and no empty-success exists;
- downstream impacts are traced without asserting unsupported legal outcome;
- dashboard projections rebuild from canonical state without mutation and
  cannot hide blockers through a combined percentage;
- immutable reclassification, explicit supersession and ActionRequest closure
  authority/SoD are enforced;
- independent Audit authority and required SoD are enforced;
- real PostgreSQL RLS/isolation, lifecycle fence, archive/reset and migration
  tests pass on synthetic disposable data;
- canonical CI is green;
- G-07B/G-02B, production policies and real provider execution remain honestly
  BLOCKED where evidence is absent;
- Audit report can terminally block and does not fabricate completeness or
  silently perform Restoration.

## 13. Почему современная архитектура лучше legacy

The accepted architecture materially improves:

- workspace isolation through composite scope, RLS/FORCE RLS and no global
  digest identity;
- immutable source/fact/result versions and exact locators;
- physical bytes/object receipt separated from semantic identity and authority;
- Candidate/Fact/ConfirmationDecision boundary;
- exact provider attempt/render/batch/reconciliation semantics;
- deterministic RuleTrace and three-valued applicability;
- append-only audit, lifecycle fences, archive and verified reset;
- rebuildable projections instead of dashboard/database status as canon.

Legacy evidence has priority only where it exposes real omitted acceptance
conditions: document boundaries in multi-document PDF, partial-page outcomes,
evidence coverage versus file count, timely incoming control, document signing
readiness and downstream causal impact.

## 14. Architecture-change assessment

No accepted RD/DR/HV/IA/TA/ADR is changed. No new ADR is created. Existing
`SourceArtifact/SourceVersion/PhysicalObject/SourceLocator`, WP-11/WP-13 domain
chain, G-07 attempts and G-06 lifecycle provide most primitives. Explicit
Package/Volume/Book/Membership and ActionRequest versions are additive LDM/IA
clarifications, not a legacy folder model and not a cross-cutting ADR change.

The implementation task must prove a typed occurrence/boundary mapping. If
physical design later demonstrates that existing primitives cannot preserve
many-logical-documents-per-container and many-representations-per-document
without identity ambiguity, that specific cross-cutting gap must be escalated
before migration; it is not assumed now.

## 15. Remaining blockers and next step

- actual WP-14 code, contracts, migration and tests are intentionally absent;
- production Audit RuleSet, customer-specific requirement matrix and authority
  grants remain uninstantiated;
- real external pdfpipeline/Polza route remains blocked by G-07B/G-02B;
- five `king25` and one `ms-7e26` user/work NTFS volumes remain outside
  evidence coverage because read-only mount requires interactive polkit;
- production Package/Signing/Handover rules, copy counts, register hierarchy
  and ActionRequest authority policies remain uninstantiated.

The semantic DoR is now explicit, but correction coverage is not fully closed
until inaccessible volumes are searched or formally recorded unavailable by
the owner. After that coverage decision and acceptance of this correction, the
only next step is a separately authorized **WP-14 Audit Slice implementation**.
