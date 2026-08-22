# WP‑12 Tender Slice v0.1

- **Статус:** `Candidate for acceptance — local PostgreSQL 17 evidence PASS; canonical CI pending`
- **Владелец продукта:** Олег Щербаков
- **Дата:** 2026‑08‑23
- **Ветка:** `implementation/wp12-tender-slice-v0.1`
- **Migration:** `0006_wp12` после `0005_wp11`
- **Contract extension:** immutable additive `contracts/v1.2`

## 1. Назначение и граница

WP‑12 реализует первый объектно-независимый режимный E2E-срез над общим ядром
WP‑11. Он принимает синтетический тендерный корпус, фиксирует scope и
комплектность, выполняет детерминированные проверки, связывает clause-level
риски с доказательствами и RuleTrace, формирует пять типизированных выходов и
допускает успешную финализацию только после независимых профессиональных
решений.

Slice не является отдельным продуктом. Он не реализует Support, Audit,
Restoration, production rendering или ProductReady. G‑02B и G‑07B остаются
`BLOCKED`.

## 2. Process model

Реализована одна последовательность:

1. `AssessTenderCorpus`;
2. `DetermineTenderRequirements`;
3. `AnalyzeContractRisk`;
4. `DraftDisagreementProtocol`;
5. `DraftRevisedContract`;
6. `FinalizeTenderDeliverable`.

Canonical header `workspace.tender_processes` использует состояния
`requested → corpus_assessed → requirements_determined → analyzed → drafted →
waiting_for_authority → finalized` и отдельный terminal `blocked`. Переходы
имеют optimistic concurrency, idempotency и exact contract/policy/RuleSet pins.
Прямой `UPDATE state` запрещён trigger-guard. Принятый переход и outbox event
пишутся одной транзакцией; rejected transition создаёт content-minimal audit,
но не domain event.

## 3. Physical model

### Scope, corpus and requirements

- `tender_processes` — mutable aggregate header только через service path;
- `tender_scope_versions` — immutable scope/classification/purpose/policy pins;
- `tender_corpus_items` — admitted SourceVersion/Locator/Evidence по source class;
- `tender_completeness_assessments` — required/available/missing classes без
  ложного `NO_RISK`;
- `tender_requirement_versions` — three-valued applicability и exact RuleTrace.

### Clause, finding and authority

- `tender_clause_versions` — clause locator, exact source, EvidenceLink и
  подтверждённый `WorkspaceFactVersion`;
- `tender_issue_versions` — typed risk/conflict/gap/uncertainty/blocker и
  Tender-view общих missing-work/material/geometry findings;
- `tender_issue_evidence` — clause-level evidence binding;
- `tender_professional_grants` — квалифицированные human-only review/finalize
  capabilities;
- `tender_finding_confirmation_decisions` — отдельное профессиональное
  подтверждение материального legal finding.

### Outputs

- `tender_disagreement_protocol_versions` и `tender_disagreement_items`;
- `tender_revised_contract_versions` и `tender_revised_clause_versions`;
- `tender_deliverable_versions` для пяти разных типов;
- `tender_review_decisions`;
- `tender_terminal_outcomes`.

Каждая workspace relation содержит обязательные `organization_id` и
`workspace_id`, composite FK, RLS/FORCE RLS, lifecycle write fence и immutable
version history. Для исполнения создана non-owner/non-superuser роль
`asd_tender_service`. У Tender нет отдельной БД, отдельного source/fact/rule
store или nullable universal scope.

## 4. Candidate → Fact → legal finding → finalization

Физическая цепочка:

```text
ProviderExecutionResult
→ CandidateVersion + field evidence + validator pass
→ ConfirmationDecision
→ WorkspaceFactVersion
→ tender_clause_versions
→ tender_issue_versions + RuleTrace + EvidenceLink
→ tender_finding_confirmation_decisions
→ disagreement/revised-clause lineage
→ tender_review_decisions
→ finalized TenderDeliverableVersion
→ terminal outcome
```

`tender_clause_versions.fact_id/fact_version` имеет composite FK на WP‑11 Fact.
Неподтверждённый Candidate физически не может стать clause input. Модельные и
service identities запрещены в professional grants/decisions DB constraints и
typed API. Review и finalizer обязаны быть разными людьми. Confidence, JSON
валидность, model agreement или draft provider result не являются authority.

## 5. Clause, risk, conflict, gap and uncertainty

Clause фиксирует SourceVersion, locator, permitted content digest, authority
layer и Fact lineage. Finding фиксирует subject, severity, three-valued
applicability, exact RuleSetVersion/RuleTrace, evidence, uncertainty code,
recommended change и consequence code.

`TenderValidationInput@1.0.0` и deterministic registry различают:

- missing required section/application;
- conflicting clauses;
- ambiguous term/reference;
- ambiguous NTD edition/effective date;
- Customer Regulation против НТД;
- unallocated responsibility;
- undefined deadline, acceptance or payment basis;
- unconfirmed volume or cost;
- omitted work/material по доступным подтверждённым kernel inputs;
- insufficient geometry source/CRS/units.

Missing data создаёт gap/uncertainty/blocker. Customer Regulation остаётся
workspace source и не имеет write path к platform НТД. Неразрешённая редакция
или conflict возвращает `indeterminate`; никакая универсальная иерархия
источников не введена.

## 6. Typed outputs and lineage

Contract v1.2 и persistence различают:

1. `DisagreementProtocol`;
2. `RevisedContract`;
3. `TenderRiskRegister`;
4. `TenderGapRegister`;
5. `TenderPDRDAnalysis`.

Disagreement item связывает исходный clause locator, confirmed finding decision,
EvidenceLink, RuleTrace, consequence и предлагаемую редакцию. Revised clause
сохраняет цепочку `source clause → finding → professional decision → protocol
item → revised text`. Финализация создаёт новую immutable deliverable version;
draft не изменяется in-place.

Структурированная финализация не равна print-ready DOCX/PDF. Rendering,
qualification шаблона и PrintValidation остаются отдельным `BLOCKED` capability.

## 7. Common-kernel reuse

Tender использует существующие Workspace, ModeExecution, SourceVersion,
SourceLocator, EvidenceLink, CandidateVersion, WorkspaceFactVersion,
RuleEvaluation/RuleTrace и `kernel_finding_versions`. Общие WorkType, work/MTR,
control/evidence/ID completeness и geometry findings не дублируются. Tender
добавляет только режимный scope, анализ clauses и typed presentation outputs.

Это сохраняет возможность применять одно ядро к Tender, Support, Audit и
Restoration; готовность Tender не устанавливает готовность остальных режимов.

## 8. Archive, reset and isolation

Portable logical archive test включает exact Tender process revision, пять
deliverable version refs и Contract v1.2 в immutable manifest; archive не
является backup и не означает print-ready output.

Все Tender relations добавлены в child-first inventory
`PostgresWorkspaceStorageAdapter`. Disposable reset удаляет process, clauses,
findings, drafts, decisions и outputs выбранного workspace. RLS A/B test
показывает отсутствие чтения другого workspace; purge A сохраняет Tender B.
Platform RuleSetVersion остаётся неизменным. Content-bearing Tender state не
попадает в content-free audit/attestation residue.

## 9. Contracts and events

`contracts/v1.2` — additive SemVer extension, сохраняющий v0.1/v1.0/v1.1. Один
Draft 2020‑12 schema с local-only URN references определяет typed deliverable и
process event. Valid/invalid fixtures проверяют clause/evidence lineage,
indeterminate-without-uncertainty и невозможность finalized output без typed
items, без blockers и без independent decisions.

Persisted commands/events/results не используют `latest`. Event не является
system of record и доставляется at-least-once через существующий outbox.

## 10. Migration and rollback

`0006_wp12` является forward-only production migration. Она не изменяет
0001…0005, создаёт relation constraints, роли, grants, policies и guards без
сети и mutable production policy. Destructive downgrade разрешён только при
`ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1` в disposable development/test DB; production
downgrade fail-closed.

Проверяются clean `0001→0006` и disposable `0006→0005→0006`.

## 11. Selective legacy mapping

| Legacy element | Decision | WP‑12 treatment |
|---|---|---|
| Clause-level legal finding | `preserve` | Точный clause locator и risk subject сохранены |
| Трёхколоночная структура протокола | `modernize` | Добавлены Fact/Evidence/RuleTrace/decision/consequence lineage |
| Revised contract clause mapping | `modernize` | Immutable source→finding→decision→new clause versions |
| Conflict visibility and completeness checks | `modernize` | Three-valued applicability и stable typed validation codes |
| Hard-coded normative “trap” catalogue | `reject` | Нет неподтверждённого нормативного содержания |
| LLM verdict/confidence as legal truth | `reject` | Qualified human decision is mandatory |
| Global evidence graph/project memory | `reject` | Composite workspace scope; graph is never SoR |
| Pilot paths, real documents and generated examples | `reject` | Только synthetic object-independent fixtures |

Legacy code не копировался механически и удалённые компьютеры не обследовались.

## 12. Test evidence

Local evidence на disposable PostgreSQL 17.10:

- Contract/unit WP‑12: `12 passed`;
- PostgreSQL WP‑12 integration: `4 passed`;
- migration head/schema/role/RLS;
- AT‑PE‑41 E2E from admitted source and confirmed Fact to five outputs;
- model/unconfirmed Candidate negative authority tests;
- clause/revision lineage;
- optimistic concurrency/idempotency and direct-update guard;
- lifecycle freeze;
- exact portable archive manifest;
- A/B RLS and scoped reset;
- platform RuleSet integrity;
- disposable downgrade/upgrade.

Полный repository pytest, PostgreSQL 18 + pgvector canonical CI и post-merge CI
фиксируются перед переводом статуса в `PASS`.

## 13. Intentionally not implemented / blockers

- real Qwen or external VLM inference — G‑07 production qualification blocked;
- Polza.ai/external egress/VPS/S3 — G‑07B/G‑02B blocked;
- production legal authority grants and policy instances — `UNSET/BLOCKED`;
- official normative content or production ConflictPolicy instances — не
  выдумывались;
- print-ready DOCX/PDF and qualified templates — blocked;
- Support, Audit, Restoration and cross-mode ProductReady acceptance — not
  implemented.

## 14. Gate self-check

| WP‑12 criterion | Status | Evidence |
|---|---|---|
| WP‑11 reuse; no Tender-specific kernel/store | `PASS local` | Fact/RuleTrace/kernel finding FKs and tests |
| Tender corpus/scope/requirements | `PASS local` | typed model, persistence, E2E |
| Clause risks/conflicts/gaps/uncertainties | `PASS local` | validators + exact lineage |
| Five typed outputs | `PASS local` | contract v1.2 + versioned DB outputs |
| Qualified legal confirmation/finalization | `PASS local` | human-only grants, independent decisions |
| Archive/reset/A-B isolation | `PASS local` | PG17 disposable evidence |
| AT‑PE‑41 terminal semantics | `PASS local` | E2E success and explicit blockers |
| Canonical PostgreSQL 18 CI | `PENDING` | GitHub PR check required |
| ProductReady | `FALSE` | DB check and four-mode conjunctive gate |

WP‑12 может стать `PASS` только после зелёного canonical CI. Даже после этого
статус означает accepted Tender implementation slice, а не готовность продукта.
