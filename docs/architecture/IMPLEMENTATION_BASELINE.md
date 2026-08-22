# Базовый уровень реализации АСД-КОНТУР

- **Статус:** `Accepted implementation baseline — G-04/G-05 PASS; G-06 candidate`
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
- `G-06 Workspace Lifecycle Foundation` — `CANDIDATE PASS 2026-08-23`:
  lifecycle/archive/import/reset/destruction foundation и A/B isolation
  проверены локально; canonical PostgreSQL 18 CI ожидается;
- mode workflows, production deployment и product deliverables — `NOT STARTED`.

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

- последующие после G‑06 gates;
- PostgreSQL/S3/VPS production deployment;
- перенос legacy templates, binaries и данных конкретного ОКС;
- активация external VLM egress;
- использование pilot-specific paths или одного режима как product core.

Следующий gate определяется `IMPLEMENTATION_PLAN_v0.1.md` как G-07; G‑06 не
активирует production policy instances и не отменяет `G-02B BLOCKED`.

## 4. Воспроизводимость baseline

Активный baseline проверяется locked dependencies, Ruff, mypy, Contract Pack
fixtures, Alembic и PostgreSQL integration suite, а также структурными
проверками Markdown/whitespace и отсутствия секретов, моделей и pilot/ОКС
payload. Production readiness из этих проверок не следует.

Восстановление прежнего GitHub baseline выполняется чтением archive branch
или tag, но не переключением default branch без отдельного решения владельца
и нового контролируемого процесса.
