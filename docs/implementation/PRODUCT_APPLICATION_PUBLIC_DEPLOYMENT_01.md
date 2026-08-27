# PRODUCT-APPLICATION-PUBLIC-DEPLOYMENT-01

## Что теперь умеет АСД-КОНТУР как продукт

- Public website ООО «АСД-КОНТУР» реализован отдельной адаптивной поверхностью и
  ведёт в авторизованный Product Application, а не в объектный BI-контур.
- Durable synthetic workspace на authoritative MBP воспроизводит доказанный
  `SUPPORT-PRODUCTION-ID-02`: 28 подтверждённых полей АОСР, официальный
  `TemplateVersion 344pr-2023@1.0.0`, четыре immutable `PackageVersion`, четыре
  `VolumeBookVersion`, четыре версии реестра и один `FinalizedDocument`.
- Support UI показывает не только текущий комплект, но и все четыре связанные
  версии package/register с их fingerprints.
- Финализированный АОСР доступен через Application API как PDF; полный ответ и
  `Range: bytes=0-31` проверены, canonical SHA-256 совпадает.
- Operations показывает version-pinned deployment identity: source commit,
  runtime profile, migration head, frontend/OpenAPI digests и deployment time.

## Граница поверхностей

| URL | Назначение | Состояние на checkpoint |
| --- | --- | --- |
| `https://asd-kontur.ru` | публичный website ООО «АСД-КОНТУР» | source готов; внешний cutover ожидает VPS access |
| `https://app.asd-kontur.ru` | авторизованный Product Application Spine | MBP runtime ready; DNS/ingress ожидают VPS access |
| `https://bi.asd-kontur.ru/levashovo/intake-control/` | изолированный архив прежнего входного контроля | ожидает reversible VPS cutover |
| `https://tm.asd-kontur.ru` | независимый пилот ТМ-35 | не изменяется |

Публичный website не содержит переходов к `bi` или `tm`. Объектные данные
Левашово и ТМ-35 не импортируются в новый Product Application.

## Public website

Source находится в `website/` и не зависит от React Product Application bundle.
Он содержит только подтверждённое владельцем наименование ООО «АСД-КОНТУР» и
описание продукта; неподтверждённые реквизиты, адреса, сотрудники, клиенты,
сертификаты и показатели отсутствуют. Desktop 1280 px и mobile 390 px были
отрендерены Playwright; обязательная кнопка входа присутствует в header и hero.

## Authoritative MBP runtime

- database: `asd_kontur_public_demo`, PostgreSQL на MBP;
- migration head: `0027_public_deployment`;
- API launchd identity: `ru.asd-kontur.spine.api`;
- worker launchd identity: `ru.asd-kontur.spine.worker`;
- API bind: explicit loopback `127.0.0.1:8765`, session profile
  `protected_remote`;
- object and archive planes: deployment-owned paths outside Git;
- database replicas на VPS отсутствуют.

Миграция `0027_public_deployment` даёт runtime group roles только `SELECT` на
`alembic_version`, чтобы readiness проверял exact head без owner connection.
Никакие domain tables или semantics миграция не меняет.

## Synthetic demonstration receipt

Durable idempotent seeder `tools/seed_public_product_demo.py` публикует receipt
вне Git и прекращает работу при несовпадении denominator. Проверенный результат:

- `PackageVersion`: 4;
- `VolumeBookVersion`: 4;
- register versions: 4;
- finalized documents: 1;
- exact finalized-run field resolutions: 28;
- readiness: required 4, finalized 1, missing 2, blocked 1;
- finalized PDF SHA-256:
  `sha256:6cff1f024c90b6fe5414af417b19f750310c0e4caa15a84b270995c299eafb5a`.

Сценарий явно synthetic. Исполнительная схема и документы качества остаются
gaps; реальные сведения ОКС не фабрикуются.

## Runtime и deployment identity

`SpineSettings` принимает version-pinned release metadata из runtime environment.
`render-launchd` сохраняет venv interpreter path и создаёт self-contained
deployment-owned plists с mode `0600`. Это исправляет обнаруженный на canary
дефект, при котором symlink resolution запускал base Python без пакета
`asd_kontur`.

Health readiness ожидает настроенный migration head вместо hardcoded revision.
API/worker работают отдельными launchd processes и используют существующий
durable PostgreSQL job ledger.

## Проверки checkpoint

- `uv lock --check`: PASS;
- Ruff format/lint: PASS;
- strict mypy: 153 source files, PASS;
- PostgreSQL pytest: 480 passed, no skips, one upstream Starlette deprecation
  warning;
- frontend format/typecheck/lint: PASS;
- frontend tests: 2 files / 3 tests, PASS;
- frontend production build: PASS;
- local live Playwright: 3 passed, one explicit opt-in NTD skip;
- full PDF response: 200; Range response: 206 / 32 bytes; digest match: PASS;
- public website desktop/mobile render: PASS;
- external Playwright contract exists in `frontend/e2e-external/` and cannot be
  called PASS until it runs against the deployed domains.

## Remaining deployment gates

At this checkpoint Tailscale requires an interactive check before MBP can use
the existing `ms-7e26` VPS key path. Until it is approved, the following remain
open and must not be represented as complete:

1. exact legacy source/service/database/nginx inventory and archival branch;
2. `bi.asd-kontur.ru/levashovo/intake-control/` cutover;
3. `app.asd-kontur.ru` DNS/TLS/nginx ingress;
4. public website cutover on `asd-kontur.ru`;
5. external Playwright, king25 reachability and API/worker restart acceptance;
6. final deployment record, merged-commit redeploy and issue #19 comment.

## Readiness

- `TrialReady=false`;
- `OKSReady=false`;
- `ProductReady=false`.

This record remains **IN PROGRESS** until all four externally observable URL
outcomes are proven.
