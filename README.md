# АСД-КОНТУР

> **Current product status (superseding, 2026-08-26):** the repository contains
> a `PARTIAL` Platform/Domain Kernel, not a user-ready software complex.
> Frontend, Application Spine, industrial intake and production operator flows
> are not implemented. `TrialReady=false`, `OKSReady=false`,
> `ProductReady=false`. The canonical denominator is the
> [Product Goal and Capability Map](docs/product/PRODUCT_GOAL_AND_CAPABILITY_MAP_v1.md)
> and [Contract Pack v2.0](contracts/v2.0/README.md).

**АСД-КОНТУР** — объектно-независимый программный комплекс для анализа
строительной документации, управления доказательствами и подготовки
проверяемых результатов по объектам капитального строительства (**ОКС**).

Репозиторий содержит принятую архитектуру и первый общий persistence
foundation нового ядра. Наличие схемы БД и runtime-контрактов не означает
готовность MVP, production-среды, отдельного режима или генератора
исполнительной документации.

## Объектная и процессная граница

- `ConstructionObject` — стабильная identity ОКС и его жизненного цикла;
- `Workspace` — изолированная память одной обработки одного ОКС;
- `ModeExecution` — конкретный запуск режима внутри workspace.

Общий конвейер:

`workspace → источники и факты ОКС → общее ядро → результаты → финализация → экспорт/архив → доказанный reset → следующий ОКС`.

Четыре обязательных режима используют одно доменное ядро:

1. `Tender` — договорные разногласия, риски и анализ до исполнения;
2. `Support` — сопровождение СМР и комплектности доказательств;
3. `Audit` — проверка обязательного и фактического состояния;
4. `Restoration` — допустимое восстановление недостающей ИД только из
   подтверждённых данных.

`ProductReady = Tender ∧ Support ∧ Audit ∧ Restoration`. Пилот, один ОКС или
готовность одного режима не являются готовностью продукта.

## Постоянные продуктовые результаты

1. подрядчико-защитный протокол разногласий и переработанный договор;
2. анализ ПД/РД с пропущенными работами и материалами, конструктивными и
   геометрическими коллизиями, ошибками и рисками;
3. исполнительные схемы только из подтверждённых проектных и фактических
   геометрических данных.

`ID Generation & Template Platform` — capability общего ядра для
квалифицированных DOCX/XLSX/PDF/DXF-шаблонов. Созданный файл остаётся
`GeneratedDocumentCandidate` до проверок компоновки, профессионального
решения и явной финализации.

## Память, ИИ и размещение

`Platform memory` сохраняет официальные НТД со всеми редакциями,
квалифицированные правила, справочники, универсальные шаблоны и постоянный
versioned `ID Practice Intelligence` из «Пособия по ИД». Пособие хранится как
`methodological_practice`: оно объясняет профессиональную практику, но не
становится нормативной обязанностью. Исходная edition и canonical intelligence
имеют retention class `permanent_platform_core` и переживают reset/destroy
любого workspace. ПД/РД,
договор, регламент Заказчика, факты, результаты и VLM-артефакты принадлежат
конкретному workspace и уничтожаются по его retention/lifecycle. Регламент
Заказчика не является НТД и не может её перезаписывать.

Перед любой ID-related VLM операцией платформа детерминированно собирает
source-pinned `IDPracticeContextPack` через Knowledge Gateway. Смена Qwen,
provider, embeddings или graph не меняет canonical memory; runtime получает
раздельно требования НТД, советы пособия, факты ОКС и gaps/conflicts.

`UNIFIED-HARNESS-01` расширяет эту границу на все существенные строительные
AI/VLM-операции: один `ConstructionHarnessContextPack` и одна versioned
`WorkRequirementMatrix` связывают ПД/РД, смету/ВОР, договор, дополнения регламента
Заказчика, Practice Intelligence, verified NTD и qualified RuleVersion для
Tender, Support, Audit и Restoration. Отсутствующий NTD subset остаётся явным
gap; customer overlay не может ослабить нормативный минимум.

Любой OCR/VLM/LLM создаёт только `Candidate` или draft. Модель не подтверждает
факт, нормативную применимость, юридическое решение, геометрию, подписанта,
финализацию или destructive operation.

Целевая local-first hybrid topology:

- MBP — единственный authoritative primary и PostgreSQL canonical plane;
- VPS — coordination, status projection и controlled egress без domain replica;
- S3 — durable object/archive/recovery plane;
- failover — только ручной, с fencing; automatic promotion и split-brain
  запрещены.

## Исторические foundation/bounded gates

The PASS labels below preserve what their exact bounded gates proved. They do
not mean `CAPABILITY_READY`, `MODE_READY`, TrialReady or ProductReady. Current
readiness semantics are defined by
[ADR-0013](docs/architecture/decisions/0013-platform-kernel-to-product-application.md).

- `G-00 Architecture Baseline` — **PASS**;
- `G-01 Logical Data Model` — **PASS**;
- `G-02A Deployment and Policy Profiles` — **PASS** как fail-closed
  нормативный профиль;
- `G-02B production instance readiness` — **BLOCKED** до утверждённых
  evidence-backed policy instances и проверок;
- `G-03 Contract Pack` — **PASS** как accepted normative contracts и
  machine-readable schema/fixture baseline;
- `G-04 Persistence Foundation` — **PASS 2026-08-23**: Contract Pack runtime,
  PostgreSQL migrations, composite scope/RLS, audit и inbox/outbox проверены
  локально и в CI на real PostgreSQL;
- `G-05 Platform Knowledge Foundation` — **PASS 2026-08-23**: WP‑05/06/07,
  PostgreSQL migrations, FTS/pgvector/typed graph, Knowledge Gateway, rules и
  Promotion Gate проверены локально и в canonical PostgreSQL 18 CI;
- `G-06 Workspace Lifecycle Foundation` — **PASS 2026-08-23**:
  synthetic/disposable lifecycle, archive/import, reset/destroy, adapter
  receipts, residual scans и content-free attestation проверены локально и в
  canonical PostgreSQL 18 CI; production retention/destruction readiness
  остаётся `BLOCKED`.
- `G-07A AI/VLM Harness Foundation` — **PASS 2026-08-23**: native-first,
  provider-neutral execution, Candidate-only lifecycle, validators/repair,
  qualification, batch/reconciliation, migration и lifecycle/reset integration
  приняты на synthetic/local evidence; реальный Qwen inference smoke не является
  выполненной qualification.
- `G-07B distributed/external execution` — **BLOCKED** до WP-09, G-02B,
  production egress/terms/budgets/qualification и реальных provider adapters.
- `KG-ID-01 permanent ID Practice Intelligence` — **PARTIAL 2026-08-25**:
  425/425 страниц reconciled, 2 410 source-guidance опубликованы как
  `permanent_platform_core`, сформированы 7 113 typed units и 1 644 playbooks;
  restore и projection rebuild воспроизводимы. Fresh-session acceptance —
  24/25 systemic и 7/7 adversarial, поэтому gate не закрыт и ProductReady
  остаётся `false`.
- `NTD-SEED-01 bounded official NTD memory` — **PARTIAL 2026-08-25**:
  exact guide geometry reconciled 37 mentions to 25 stable identities; all 25
  official-only attempts terminated as `official_access_blocked`. Migration
  `0016`, Contract Pack v1.7, Gateway gaps, workspace-reset survival,
  dump/restore, projection rebuild and fresh-session non-fabrication are
  verified; 0 official editions/provisions are published.
- `UNIFIED-HARNESS-01` — **PASS (bounded implementation) 2026-08-25**: additive Contract Pack
  v1.8 и migration `0017` связывают одну ProjectDefinition/WorkRequirementMatrix
  с platform Practice/NTD/Rule memory и четырьмя mode views; 350 local tests,
  включая PostgreSQL integration, прошли. ProductReady остаётся `false`.
- `WP-11 Common Domain Process Kernel` — **PASS 2026-08-23**:
  общий Candidate→Fact authority gate и цепочка structure→work→MTR→control→evidence→ID→volume→KS→payment
  проверены локально и в canonical PostgreSQL 18 CI без mode-specific core;
  это не означает готовность режима или результата.
- `WP-12 Tender Slice` — **PASS 2026-08-23**: object-independent
  clause/risk/conflict/gap analysis, пять typed Tender outputs,
  Candidate→Fact→qualified legal authority boundary и archive/reset isolation
  прошли локально на disposable PostgreSQL 17 и в canonical PostgreSQL 18 CI.
  Audit и Restoration не начаты; ProductReady = false.
- `WP-13 Support Slice` — **PASS 2026-08-23**: common-kernel
  work/MTR/control/evidence, ID completeness/generation, confirmed geometry и
  volume/KS/payment trace прошли local PostgreSQL 17 и canonical PostgreSQL 18
  CI. Production print-ready и policy instances остаются blocked.
- `WP-14 pre-implementation evidence assessment` — **COMPLETE 2026-08-23**:
  legacy pdfpipeline/Левашово использован как partial practical evidence, а не
  переносимая архитектура.
- `WP-14 Audit Slice` — **PASS 2026-08-23**:
  общий four-mode acquisition/corpus pipeline, streamed preflight,
  page/shard/reconciliation, `CorpusSnapshot` и три независимые Audit delta
  прошли полный local PostgreSQL 17 и canonical PostgreSQL 18 + pgvector CI.
  G-07B, Restoration и ProductReady остаются blocked/not ready.

Ключевые документы:

- [Documentation index](docs/README.md)
- [Product Goal and Capability Map v1](docs/product/PRODUCT_GOAL_AND_CAPABILITY_MAP_v1.md)
- [Four-mode Functional Model v1](docs/product/FOUR_MODE_FUNCTIONAL_MODEL_v1.md)
- [Architecture Blueprint v1](docs/architecture/ARCHITECTURE_BLUEPRINT_v1.md)
- [Implementation Plan v1](docs/architecture/IMPLEMENTATION_PLAN_v1.md)
- [Trial Readiness Specification v1](docs/product/TRIAL_READINESS_SPECIFICATION_v1.md)
- [Legacy Component Decision Matrix](docs/architecture/LEGACY_COMPONENT_DECISION_MATRIX_v1.md)
- [Product Scope](docs/product/PRODUCT_SCOPE.md)
- [Architecture Blueprint](docs/architecture/ARCHITECTURE_BLUEPRINT_v0.1.md)
- [Implementation Plan](docs/architecture/IMPLEMENTATION_PLAN_v0.1.md)
- [Logical Data Model](docs/architecture/LOGICAL_DATA_MODEL_v0.1.md)
- [Deployment and Policy Profiles](docs/architecture/DEPLOYMENT_AND_POLICY_PROFILES_v0.1.md)
- [Contract Pack](docs/architecture/CONTRACT_PACK_v0.1.md)
- [Machine-readable contracts](contracts/v0.1/README.md)
- [G-04 Persistence Foundation](docs/implementation/G04_PERSISTENCE_FOUNDATION_v0.1.md)
- [G-05 Platform Knowledge Foundation](docs/implementation/G05_PLATFORM_KNOWLEDGE_FOUNDATION_v0.1.md)
- [G-06 Workspace Lifecycle Foundation](docs/implementation/G06_WORKSPACE_LIFECYCLE_FOUNDATION_v0.1.md)
- [G-07 AI/VLM Harness](docs/implementation/G07_AI_VLM_HARNESS_v0.1.md)
- [NTD-SEED-01 bounded official NTD memory](docs/implementation/NTD_SEED_FROM_PRACTICE_GUIDE_v0.1.md)
- [UNIFIED-HARNESS-01](docs/implementation/UNIFIED_CONSTRUCTION_HARNESS_v0.1.md)
- [WP-11 Common Domain Process Kernel](docs/implementation/WP11_COMMON_DOMAIN_PROCESS_KERNEL_v0.1.md)
- [WP-12 Tender Slice](docs/implementation/WP12_TENDER_SLICE_v0.1.md)
- [WP-13 Support Slice](docs/implementation/WP13_SUPPORT_SLICE_v0.1.md)
- [Legacy pdfpipeline / Левашово audit experience](docs/reports/LEGACY_PDFPIPELINE_AUDIT_EXPERIENCE_v0.1.md)
- [WP-14 pdfpipeline architecture impact assessment](docs/reports/WP14_PDFPIPELINE_ARCHITECTURE_IMPACT_ASSESSMENT_v0.1.md)
- [WP-14 Audit Slice implementation](docs/implementation/WP14_AUDIT_SLICE_v0.1.md)
- [Technical Architecture](docs/architecture/TECHNICAL_ARCHITECTURE_v0.3.md)
- [ID Generation & Template Platform](docs/architecture/ID_GENERATION_AND_TEMPLATE_PLATFORM_SPECIFICATION_v0.1.md)
- [ADR index](docs/architecture/decisions/)
- [Legacy ID Generator Asset Inventory](docs/reports/LEGACY_ID_GENERATOR_ASSET_INVENTORY_v0.1.md)

## Репозиторий

- `docs/product/` — продуктовые границы и операционная модель;
- `docs/mvp/` — исторически названные функциональные срезы и сценарии,
  подчинённые четырёхрежимной границе готовности;
- `docs/architecture/` — нормативная архитектура и plan gates;
- `docs/architecture/decisions/` — ADR-0001…ADR-0014;
- `docs/reports/` — проверенные audit/inventory/transition records.
- `contracts/v0.1/` — accepted G-03 registry; `contracts/v1.0/` — узкая
  immutable G-06 версия content-free DestructionAttestation;
  `contracts/v1.1/` — additive G-07 render/batch/qualification/raw-artifact
  extension; `contracts/v1.2/` — additive WP‑12 typed Tender extension;
  `contracts/v1.3/` — additive WP‑13 Support/generation/geometry extension;
  `contracts/v1.4/` — additive WP‑14 corpus/Audit extension;
  `contracts/v1.5/` — KG‑ID source-guidance extraction/publication;
  `contracts/v1.6/` — permanent Practice Intelligence, Context Assembly and
  backup-integrity contracts; `contracts/v1.7/` — bounded official NTD,
  edition/provision and normative Knowledge Gateway contracts;
  `contracts/v1.8/` — unified multi-work Construction Harness contracts;
  `contracts/v1.9/` — bounded kernel integrity contracts;
  `contracts/v2.0/` — complete product capability denominator and fail-closed
  readiness contracts.
- `src/asd_kontur/`, `migrations/`, `tests/` — активное общее ядро G‑04…G‑07,
  WP‑11…WP‑14 и KG‑ID‑01:
  Contract Pack runtime, PostgreSQL persistence, platform knowledge и
  workspace lifecycle/AI-VLM Harness/common process foundations, four-mode
  slices и постоянную Practice Intelligence.

Старый прикладной prototype доступен через Git history, ветку
`archive/pre-rebaseline-prototype-2026-08-22` и тег
`pre-rebaseline-prototype-2026-08-22`; он не является активным ядром.

Основной язык архитектурной документации — русский. Будущие программные
идентификаторы и machine-readable contracts — английские.
