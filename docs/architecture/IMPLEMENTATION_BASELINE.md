# Базовый уровень реализации АСД-КОНТУР

> **Historical baseline.** Current product delivery and readiness are governed
> by [Implementation Plan v1](IMPLEMENTATION_PLAN_v1.md) and Contract Pack v2.0.

- **Статус:** `Accepted baseline through WP-13 Support implementation slice`
- **Дата:** 2026-08-23
- **Владелец:** Олег Щербаков
- **Ветка re-baseline:** `architecture/rebaseline-v0.1`
- **Область:** принятая архитектура и минимальный persistence foundation
  нового общего ядра

## 1. Текущее состояние

Архитектурный re-baseline сохранён; поверх него добавлен первый общий
implementation foundation:

- `G-00 Architecture Baseline` — `PASS`;
- `G-01 Logical Data Model` — `PASS`;
- `G-02A Deployment and Policy Profiles` — `PASS` как полный fail-closed
  нормативный профиль;
- `G-02B production instance readiness` — `BLOCKED`;
- `G-03 Contract Pack` — `PASS 2026-08-22`; нормативные schemas, registry и
  fixtures приняты, а runtime adapter проверен последующим G-04;
- `G-04 Persistence Foundation` — `PASS 2026-08-23`; Contract Pack runtime,
  PostgreSQL migrations, RLS, scoped repositories, audit и messaging ledgers
  проверены на real PostgreSQL локально и в CI;
- `G-05 Platform Knowledge Foundation` — `PASS 2026-08-23`: WP‑05/06/07,
  migrations, pgvector/FTS/graph, Gateway, rules и Promotion Gate проверены
  локально и в canonical PostgreSQL 18 CI;
- `G-06 Workspace Lifecycle Foundation` — `PASS 2026-08-23`:
  lifecycle/archive/import/reset/destruction foundation и A/B isolation
  проверены локально и в canonical PostgreSQL 18 CI;
- `G-07A AI/VLM Harness Foundation` — `PASS 2026-08-23`: native-first,
  provider-neutral local/synthetic execution, Candidate-only lifecycle,
  validators/repair, qualification, batch/reconciliation, migration and
  lifecycle/reset integration; G-07B и production qualification/egress
  остаются `BLOCKED`;
- `WP-11 Common Domain Process Kernel` — `PASS 2026-08-23`: Candidate→Fact
  authority, common process chain, four-mode reuse and reset isolation passed
  local PostgreSQL 17 and canonical PostgreSQL 18 CI;
- `WP-12 Tender Slice` — `PASS 2026-08-23`: AT-PE-41, typed outputs, legal
  authority, archive/reset and isolation passed on local PostgreSQL 17 and in
  canonical PostgreSQL 18 CI;
- `WP-13 Support Slice` — `PASS 2026-08-23`: AT-PE-42,
  work/MTR/control/evidence, ID generation mechanics, confirmed geometry,
  volume/KS/payment and scoped reset passed locally and in canonical CI;
- `WP-14 pre-implementation evidence assessment` — `COMPLETE 2026-08-23`:
  legacy pdfpipeline/Левашово practice assessed without source migration;
  Document Delta, Causal Readiness Delta and expanded AT-PE-43/DoR accepted;
  historical archive coverage remains intentionally `PARTIAL`.
- `WP-14 Audit Slice` — `PASS 2026-08-23`:
  common collection/preflight/page-shard/reconciliation/CorpusSnapshot capability,
  three independent Audit deltas, migration `0008_wp14`, Contract Pack v1.4 and
  PostgreSQL 17 local plus canonical PostgreSQL 18 + pgvector CI evidence are
  complete;
- Restoration, production deployment и ProductReady — `NOT STARTED`.

Старый prototype, его `src/`, tests, tools, runtime configuration, pilot
assets и бинарный DOCX удалены из active tree. Они остаются в Git history,
ветке `archive/pre-rebaseline-prototype-2026-08-22` и аннотированном теге
`pre-rebaseline-prototype-2026-08-22`.

Последний подтверждённый локальный pre-rebaseline test baseline старого
prototype: `224 passed, 2 deselected`. Этот результат относится только к
архивируемому prototype и не доказывает готовность нового ядра, режима,
ID Generator или продукта.

## 2. Нормативные основания

Текущий implementation boundary задают:

- `ARCHITECTURE_BLUEPRINT_v0.1.md`;
- `IMPLEMENTATION_PLAN_v0.1.md`;
- `LOGICAL_DATA_MODEL_v0.1.md`;
- `DEPLOYMENT_AND_POLICY_PROFILES_v0.1.md`;
- `CONTRACT_PACK_v0.1.md` и `contracts/v0.1/`;
- `TECHNICAL_ARCHITECTURE_v0.3.md`;
- ADR-0001…ADR-0010.

Подробная классификация prototype-компонентов и порядок future selective
port фиксируются в `docs/reports/REPOSITORY_REBASELINE_MANIFEST_v0.1.md`.
Наличие полезной идеи в archive не разрешает вернуть старый файл в active
tree без новых контрактов, проверки scope/provenance и отдельного решения.

## 3. Непереходимые границы

Без отдельной authority и gate evidence не начинаются:

- последующие после G‑07 gates;
- PostgreSQL/S3/VPS production deployment;
- перенос legacy templates, binaries и данных конкретного ОКС;
- активация external VLM egress;
- использование pilot-specific paths или одного режима как product core.

WP-11 принят как implementation foundation по local и canonical CI evidence.
WP-12 и WP-13 приняты только как Tender/Support implementation slices. Они не
активируют production policy instances, не
отменяют `G-02B/G-07B BLOCKED` и не начинают WP-14 автоматически.

## 4. Воспроизводимость baseline

Активный baseline проверяется locked dependencies, Ruff, mypy, Contract Pack
fixtures, Alembic и PostgreSQL integration suite, а также структурными
проверками Markdown/whitespace и отсутствия секретов, моделей и pilot/ОКС
payload. Production readiness из этих проверок не следует.

Восстановление прежнего GitHub baseline выполняется чтением archive branch
или tag, но не переключением default branch без отдельного решения владельца
и нового контролируемого процесса.
