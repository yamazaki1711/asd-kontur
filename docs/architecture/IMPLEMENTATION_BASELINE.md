# Базовый уровень реализации АСД-КОНТУР

- **Статус:** `Accepted architecture-only repository baseline`
- **Дата:** 2026-08-22
- **Владелец:** Олег Щербаков
- **Ветка re-baseline:** `architecture/rebaseline-v0.1`
- **Область:** граница между принятой архитектурой и ещё не начатой
  реализацией нового общего ядра

## 1. Текущее состояние

Репозиторий намеренно переведён в architecture-only baseline:

- `G-00 Architecture Baseline` — `PASS`;
- `G-01 Logical Data Model` — `PASS`;
- `G-02A Deployment and Policy Profiles` — `PASS` как полный fail-closed
  нормативный профиль;
- `G-02B production instance readiness` — `BLOCKED`;
- `G-03 Contract Pack` — `OPEN`, следующий нормативный gate;
- ORM, DDL, migrations, persistence, deployment и прикладное ядро —
  `NOT STARTED`.

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
- `TECHNICAL_ARCHITECTURE_v0.3.md`;
- ADR-0001…ADR-0010.

Подробная классификация prototype-компонентов и порядок future selective
port фиксируются в `docs/reports/REPOSITORY_REBASELINE_MANIFEST_v0.1.md`.
Наличие полезной идеи в archive не разрешает вернуть старый файл в active
tree без новых контрактов, проверки scope/provenance и отдельного решения.

## 3. Непереходимые границы

До закрытия `G-03` и отдельной implementation authority запрещены:

- прикладной код, ORM, DDL и migrations;
- persistence repositories и PostgreSQL/S3/VPS deployment;
- перенос legacy templates, binaries и данных конкретного ОКС;
- активация external VLM egress;
- использование pilot-specific paths или одного режима как product core.

После `G-03` следующий шаг определяется `IMPLEMENTATION_PLAN_v0.1.md`; сам
факт прохождения gate не активирует production policy instances и не отменяет
`G-02B BLOCKED`.

## 4. Воспроизводимость baseline

Architecture-only branch проверяется структурно: tracked file manifest,
Markdown links, trailing whitespace, отсутствие секретов, моделей,
pilot/ОКС payload и prototype runtime. `pytest` к этой ветке неприменим,
поскольку активной реализации и test suite в baseline намеренно нет.

Восстановление прежнего GitHub baseline выполняется чтением archive branch
или tag, но не переключением default branch без отдельного решения владельца
и нового контролируемого процесса.
