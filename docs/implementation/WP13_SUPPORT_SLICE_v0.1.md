# WP‑13 Support Slice v0.1

- **Статус:** `WP-13 acceptance candidate — canonical CI pending`
- **Владелец продукта:** Олег Щербаков
- **Дата:** 2026‑08‑23
- **Ветка:** `implementation/wp13-support-slice-v0.1`
- **Migration:** `0007_wp13` после `0006_wp12`
- **Contract extension:** immutable additive `contracts/v1.3`

## 1. Назначение и граница

WP‑13 реализует объектно-независимый Support slice над общим WP‑11 kernel. Его
доказательная цепочка связывает подтверждённые project sources и факты с
планируемыми/выполненными работами, МТР, контролем, evidence, комплектностью ИД,
генерацией документов, предъявленными объёмами, КС и payment readiness.

Slice одинаково использует Workspace, Support ModeExecution, SourceVersion,
Candidate/Fact authority gate, WorkType/WorkInstance/WorkVolume, MTR, control,
RuleTrace, audit, outbox и G‑06 lifecycle. Отдельная Support DB или второе
доменное ядро не создавались. Support не является MVP/ProductReady и не
реализует Audit, Restoration или production deployment.

## 2. DoR, actions, tests и DoD

Нормативный WP‑13 из Implementation Plan задаёт:

- DoR: WP‑11 и field/confirmation/geometry contracts;
- actions: planned/performed work, МТР, controls, evidence, proactive ID drafts,
  claimed volumes/КС/payment readiness;
- tests: offline conflicts, missing evidence, calibration/authority, hidden
  work, material custody, archive/reset;
- DoD: полная воспроизводимая цепочка без confidence-based Fact и без
  неподтверждённой executive geometry.

Реализация и AT‑PE‑42 покрывают все эти пункты synthetic/disposable evidence.

## 3. Support process

`SupportProcessStateMachine` и `PostgresSupportProcess` определяют команды:

- `ConfigureSupportScope`, `CreatePlannedWork`, `EvaluateWorkReadiness`;
- `ConfirmWorkFact`, `RegisterMaterialBatch`, `ApplyMaterialBatch`;
- `RecordControlEvent`, `AttachEvidence`, `EvaluateIdCompleteness`;
- `StartGenerationRun`, `FormIdPackage`, `EvaluateVolumeReadiness`;
- `FormExecutiveScheme`, `TracePresentedVolume`, `EvaluatePaymentReadiness`;
- `FinalizeSupportDeliverable`.

Принятый переход изменяет canonical aggregate revision и записывает exact v1.3
outbox event с content-minimal audit в одной транзакции. Rejected finalization
создаёт audit без domain event. Idempotent replay возвращает сохранённые state и
revision исходного outcome; semantic key reuse и stale expected revision
fail-closed. Direct state mutation и late write после lifecycle freeze
запрещены DB triggers.

## 4. Work, МТР, control и evidence

Work readiness различает plan, performed FactVersion, predecessors, pre-start
controls, admitted materials, evidence checkpoints и blockers. Скрываемая
работа требует evidence не позднее заданного checkpoint; поздний документ не
делает контроль своевременным.

Material admission фиксирует exact batch, manufacturer/supplier, quantity/unit,
certificate/passport EvidenceLinks, incoming control, custody, applicability и
human authority. Неполные документы дают waiting/blocker, custody gap остаётся
видимым, conflict переводит admission в quarantine; fuzzy match отсутствует.

Control result содержит method/criterion/unit/tolerance, performed Fact,
instrument calibration interval, EvidenceLink, RuleTrace и professional grant.
Отрицательный результат immutable; retest создаёт новую version с supersedes.
Missing/expired calibration даёт typed indeterminate blocker.

## 5. Field/offline confirmation

Offline envelope хранит device/source identity, acquisition/timestamp authority,
locator/evidence, units/precision и import lineage. Доставка одного fingerprint
идемпотентна. Другая semantic version того же observation создаёт conflict и
quarantine без last-write-wins. Это локальный deterministic reconciliation
contract; WP‑09/VPS/S3 synchronization не реализованы.

Provider/model/integration identity не получает professional capability.
Фактическое выполнение, объём, material admission, control, geometry и
finalization используют существующий WP‑11 Candidate→ConfirmationDecision→
WorkspaceFactVersion gate и отдельные Support human grants.

## 6. Комплектность ИД и generation pipeline

`evaluate_id_completeness` вычисляет deterministic required-vs-actual delta по
exact RequiredDocumentType/RuleTrace/applicability/evidence/authority. Missing,
conflicting и indeterminate requirements остаются typed gap/blocker.

Semantic generation pipeline реализует:

```text
RequiredDocumentType → TemplateVersion → FieldSchema → BindingPlan
→ GenerationRun → FieldResolution → EvidenceBinding
→ GeneratedDocumentCandidate → RenderArtifact → PrintValidationResult
→ ProfessionalReviewDecision → FinalizedDocument
```

Каждый run создаёт fresh package. Confirmed material field требует FactVersion,
EvidenceLink и locator; Candidate/gap не получает placeholder. Exact template,
schema, binding, renderer, validator, policy и RuleSet versions pinned, `latest`
запрещён. Одинаковые semantic inputs дают одинаковый fingerprint и bytes;
новый input не наследует строки предыдущего run.

Для qualification mechanics созданы synthetic DOCX и XLSX packages стандартной
OOXML структуры. DOCX проверяет package parts, styles/settings, sections/page
settings, table/field coverage и unresolved tokens. XLSX проверяет formula,
totals structure, merges, hidden evidence sheet, print area/titles, scaling,
protection и field coverage. Это `synthetic_structural_only`, не официальный
шаблон и не production print-ready qualification.

## 7. Geometry и ExecutiveScheme

`form_executive_scheme` принимает только confirmed design/as-built inputs с
SourceVersion/Locator, human confirmation, CRS/frame, unit/precision,
measurement method и действующей calibration. Transform/tolerance computation
детерминирован; inclusive/exclusive boundary входит в fingerprint.

VLM/model identity, missing CRS, incompatible units, invalid calibration и
cross-scope references блокируют semantic scheme. WP‑13 создаёт только
`ExecutiveSchemeVersion` на достигнутом semantic level. Production DXF/SVG/PDF
render/print profile остаётся `BLOCKED`.

## 8. PresentedVolume, КС и payment

Commercial evaluation связывает confirmed WorkVolume с PresentedVolume,
complete ID/evidence, contract conditions, KsLine/KsDocument и PaymentClaim.
Presented quantity не может превышать подтверждённую, units/precision и totals
детерминированы, duplicates/previous presentation остаются blockers.
PaymentRecord не создаёт entitlement и не меняет readiness fingerprint.

## 9. Physical model, RLS и authority

Migration `0007_wp13` добавляет platform `template_sources`,
`field_schema_versions`, `template_versions` и workspace relations для Support
scope/process, grants, readiness, material/control/offline records, ID
completeness/generation/review, geometry, volume/payment, deliverables и terminal
outcomes.

Все workspace relations имеют обязательные organization/workspace composite
keys, RLS/FORCE RLS, lifecycle write fence, immutable history и child-first
destruction support. `asd_support_service` — non-owner/non-superuser role и не
может самостоятельно выдавать professional grants. Review и finalization
требуют разных human identities; DB triggers проверяют exact active capability.

Platform templates физически отделены от workspace generation artifacts.
Synthetic source имеет `synthetic_only`/development assurance; production
active/official status невозможен без exact verified authority conditions.

## 10. Lifecycle, archive и reset

Все 25 WP‑13 workspace tables включены в G‑06
`PostgresWorkspaceStorageAdapter` child-first inventory. Portable archive test
фиксирует exact workspace/process/contract/deliverable manifest и проверяет hash
и readability до purge.

Disposable reset A удаляет Support process, facts-derived state, MTR/control,
offline records, generation/renders, geometry, volume/КС/payment и deliverables
только A. RLS и composite scope сохраняют B. Platform НТД, RuleSet и
TemplateSource/TemplateVersion не входят в deletion inventory и остаются
неизменными.

## 11. Contracts and migration

`contracts/v1.3` — additive Draft 2020‑12 contract, сохраняющий v0.1–v1.2. Он
определяет exact Support scope, generation outcome, executive geometry,
commercial readiness, terminal outcome и process event. Local URN references,
schema fingerprint и valid/invalid fixtures проверяются без network resolution.
Negative fixtures запрещают model/VLM geometry и payment-ready с blockers.

Migration не изменяет 0001…0006, не читает сеть/production policy и не создаёт
credentials. Production downgrade fail-closed. Disposable test проверяет clean
0001→0007 и `0007→0006→0007` при explicit test-only flag.

## 12. Selective legacy mapping

| Legacy element | Decision | WP‑13 treatment |
|---|---|---|
| Deterministic completeness delta | `preserve` | Typed required-vs-actual evaluation с RuleTrace |
| Evidence binding | `modernize` | Exact FactVersion/EvidenceLink/Locator per material field |
| Stateless DOCX/XLSX package mechanics | `modernize` | Fresh deterministic OOXML package и structural validators |
| ISGenerator/ISUID/id-track identity concepts | `modernize` | Exact run/template/schema/binding identities; не legacy algorithm copy |
| Deterministic geometry/math | `modernize` | Confirmed CRS/unit/calibration inputs and tolerance fingerprint |
| Stateful АОСР accumulation | `reject` | Каждый GenerationRun fresh; leakage regression test |
| Generated files as templates | `reject` | Platform TemplateSource отдельная authority-qualified relation |
| Zero КС-2/КС-3 as success | `reject` | Missing volume/cost/evidence blocks payment readiness |
| Fuzzy 292/приказ №624 defaults | `reject` | Только pinned active rules/evidence; нет нормативных догадок |
| TM‑35 paths/data and global memory | `reject` | Только synthetic object-independent fixtures и workspace scope |

Legacy code не копировался механически; удалённые компьютеры и старое dirty
worktree не изменялись.

## 13. Test evidence

Local evidence на disposable PostgreSQL 17.10:

- WP‑13 unit/contract: `28 passed`;
- WP‑13 PostgreSQL integration: `4 passed`;
- полный repository pytest: `219 passed`, без skips;
- clean migration head `0007_wp13`, schema/role/grants/RLS inspection;
- non-owner A/B isolation, idempotency, optimistic concurrency и freeze fence;
- synthetic DOCX/XLSX package/structural qualification mechanics;
- confirmed geometry positive/negative/tolerance scenarios;
- exact portable archive и scoped reset с platform-template integrity;
- disposable `0007→0006→0007`.

Canonical PostgreSQL 18 + pgvector CI должен завершиться до перевода статуса в
`PASS`; текущая запись не выдаёт локальную проверку за canonical acceptance.

## 14. Ограничения и blockers

Намеренно не реализованы и остаются `BLOCKED`:

- production TemplateSource/TemplateVersion qualification, renderer golden
  renders и DOCX/XLSX/PDF/DXF/SVG print-ready profiles;
- production professional grants, policy numbers и customer requirements;
- real offline/VPS/S3 synchronization, G‑07B external route и G‑02B;
- реальные Qwen/Polza.ai вызовы, НТД/ОКС documents и production deployment;
- Audit WP‑14, Restoration WP‑15, cross-mode acceptance и ProductReady.

## 15. Gate self-check

WP‑13 может стать `PASS` только после зелёного canonical CI на PostgreSQL 18.
При этом PASS означает лишь accepted Support implementation slice на
synthetic/disposable evidence. Он не подтверждает production print readiness,
production retention/egress, готовность остальных режимов или продукта.

Следующий work package после отдельного разрешения: **WP‑14 Audit Slice**.
