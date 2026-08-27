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
| `https://asd-kontur.ru` | публичный website ООО «АСД-КОНТУР» | AVAILABLE; внешний Chromium и `king25` подтвердили exact website bytes |
| `https://app.asd-kontur.ru` | авторизованный Product Application Spine | AVAILABLE; DNS, TLS и внешний authenticated E2E подтверждены |
| `https://bi.asd-kontur.ru/levashovo/intake-control/` | изолированный архив прежнего входного контроля | route активен, existing Basic Auth и `noindex` сохранены |
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

Отдельный `ru.asd-kontur.spine.ingress` launchd process поддерживает reverse
SSH endpoint `127.0.0.1:18765` на VPS. Systemd socket proxy публикует его только
в docker bridge как `172.18.0.1:18766`; nginx не получает доступ ни к
PostgreSQL, ни к object plane. Остановка ingress была проверена: API вернул
`503 authoritative_primary_unavailable`, UI — явную unavailable surface, после
перезапуска readiness восстановился без подмены данных.

## Legacy Levashovo archive

- owner repository: `yamazaki1711/ISUID`;
- прежний runtime worktree: `/opt/kat/s3`;
- прежний runtime commit: `ba93408746bc7519345c50a9f996c73da9af7fdf`;
- clean archival branch:
  `archive/levashovo-intake-control-2026-08-27`;
- archival commit: `256e72353bbbc03917a8fe7cffb8f53b8162b7a9`;
- archived service: `levashovo-intake-control.service`, port `8088`;
- isolated database binding: PostgreSQL `kat_core` on VPS;
- pre-cutover nginx SHA-256:
  `bd02f9167ffb29719beffc941122c298adcad7af7142d0bff9d1bc588d56f8e6`.

The archival branch is an intentionally clean code/schema/config snapshot. It
contains no Levashovo document bytes, database dumps, object payloads, logs or
credentials. The original dirty worktree was not reset or rewritten. Existing
BI authentication remains at nginx; all rendered links and redirects are
confined to `/levashovo/intake-control/`.

## External cutover checkpoint

- `asd-kontur.ru` root nginx digest:
  `5803c6fe7a5d172b4e2e57481c32c89c9ad2e9aadb0704c82911613db687f24a`;
- website HTML digest:
  `cf20cb2b1cd2bd21f14d0a8a970a6d2f811f8b4833d191ed1bde55af1132ff4d`;
- active BI nginx digest:
  `71c546542cecec81c648b6bfa74e8f915df8ebf6219a564f161c53c65867360c`;
- TM-35 nginx digest remained
  `0ed133f83893702b39acf407180311833865ecb6790aee69691767d9fb8b896a`;
- public website Playwright against the external URL: PASS;
- independent `king25` website digest: exact match;
- `bi` archive and `tm` unauthenticated states: `401`, both retain
  `X-Robots-Tag: noindex, nofollow`.

The full application proxy is active at the public hostname. Timeweb's four
authoritative nameservers and independent public resolvers return
`app.asd-kontur.ru A 147.45.251.207`. The exact Let's Encrypt certificate has
SAN `app.asd-kontur.ru`, SHA-256 fingerprint
`85:7C:24:1F:7E:E4:DC:D2:98:DE:C1:85:F1:7D:09:D2:00:6D:F7:16:3C:2C:2B:7F:9E:E6:CD:43:69:AA:E4:52`
and is valid through 2026-11-25.

External Playwright without host override or TLS bypass passed before and after
an explicit API/worker restart. It covered login/logout, unauthorized `401`,
Documents, Evidence, Work Matrix, all four modes, SSE, four immutable
package/register versions, finalized PDF and a 32-byte Range response. The PDF
digest remained
`sha256:6cff1f024c90b6fe5414af417b19f750310c0e4caa15a84b270995c299eafb5a`.
After restart the canonical counts remained 4 package versions, 4 volume books,
4 registers and 1 finalized document.

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
- PostgreSQL pytest: 485 passed, no skips, one upstream Starlette deprecation
  warning;
- frontend format/typecheck/lint: PASS;
- frontend tests: 2 files / 3 tests, PASS;
- frontend production build: PASS;
- local live Playwright: 3 passed, one explicit opt-in NTD skip;
- full PDF response: 200; Range response: 206 / 32 bytes; digest match: PASS;
- public website desktop/mobile render: PASS;
- external Playwright before API/worker restart: 2 passed;
- external Playwright after API/worker restart: 2 passed;
- independent `king25`: website SHA exact, app readiness/TLS PASS,
  unauthenticated app API `401`, BI and TM-35 `401` with `noindex, nofollow`.

The immutable deployment receipt is
`deployment/public/records/product-application-public-deployment-01.json`.
Contract Pack v2.4 records only the evidence-backed `PARTIAL` capability delta;
no mode or product readiness is promoted.

## Remaining product gates

The public development contour is externally usable, but it is not a production
or real-OKS acceptance. Remaining gaps include incomplete NTD/raster coverage,
one qualified output family, missing executive scheme and quality documents,
no complete ready mode, and unqualified real operational personnel/processes.

## Readiness

- `TrialReady=false`;
- `OKSReady=false`;
- `ProductReady=false`.

All four externally observable URL outcomes are proven for this deployment
slice. Product-wide readiness remains unchanged.
