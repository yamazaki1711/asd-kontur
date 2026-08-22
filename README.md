# АСД-КОНТУР

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
квалифицированные правила, справочники и универсальные шаблоны. ПД/РД,
договор, регламент Заказчика, факты, результаты и VLM-артефакты принадлежат
конкретному workspace и уничтожаются по его retention/lifecycle. Регламент
Заказчика не является НТД и не может её перезаписывать.

Любой OCR/VLM/LLM создаёт только `Candidate` или draft. Модель не подтверждает
факт, нормативную применимость, юридическое решение, геометрию, подписанта,
финализацию или destructive operation.

Целевая local-first hybrid topology:

- MBP — единственный authoritative primary и PostgreSQL canonical plane;
- VPS — coordination, status projection и controlled egress без domain replica;
- S3 — durable object/archive/recovery plane;
- failover — только ручной, с fencing; automatic promotion и split-brain
  запрещены.

## Архитектурная зрелость

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

Ключевые документы:

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
- [WP-11 Common Domain Process Kernel](docs/implementation/WP11_COMMON_DOMAIN_PROCESS_KERNEL_v0.1.md)
- [WP-12 Tender Slice](docs/implementation/WP12_TENDER_SLICE_v0.1.md)
- [WP-13 Support Slice](docs/implementation/WP13_SUPPORT_SLICE_v0.1.md)
- [Technical Architecture](docs/architecture/TECHNICAL_ARCHITECTURE_v0.3.md)
- [ID Generation & Template Platform](docs/architecture/ID_GENERATION_AND_TEMPLATE_PLATFORM_SPECIFICATION_v0.1.md)
- [ADR index](docs/architecture/decisions/)
- [Legacy ID Generator Asset Inventory](docs/reports/LEGACY_ID_GENERATOR_ASSET_INVENTORY_v0.1.md)

## Репозиторий

- `docs/product/` — продуктовые границы и операционная модель;
- `docs/mvp/` — исторически названные функциональные срезы и сценарии,
  подчинённые четырёхрежимной границе готовности;
- `docs/architecture/` — нормативная архитектура и plan gates;
- `docs/architecture/decisions/` — ADR-0001…ADR-0010;
- `docs/reports/` — проверенные audit/inventory/transition records.
- `contracts/v0.1/` — accepted G-03 registry; `contracts/v1.0/` — узкая
  immutable G-06 версия content-free DestructionAttestation;
  `contracts/v1.1/` — additive G-07 render/batch/qualification/raw-artifact
  extension; `contracts/v1.2/` — additive WP‑12 typed Tender extension;
  `contracts/v1.3/` — additive WP‑13 Support/generation/geometry extension.
- `src/asd_kontur/`, `migrations/`, `tests/` — активное общее ядро G‑04…G‑07,
  WP‑11, WP‑12 и WP‑13:
  Contract Pack runtime, PostgreSQL persistence, platform knowledge и
  workspace lifecycle/AI-VLM Harness/common process foundations и первый
  Tender и Support implementation slices.

Старый прикладной prototype доступен через Git history, ветку
`archive/pre-rebaseline-prototype-2026-08-22` и тег
`pre-rebaseline-prototype-2026-08-22`; он не является активным ядром.

Основной язык архитектурной документации — русский. Будущие программные
идентификаторы и machine-readable contracts — английские.
