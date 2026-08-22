# Техническая DevOps-архитектура АСД-КОНТУР v0.2

> **Historical / Superseded.** Эта редакция сохранена для трассировки
> решений и действующих ссылок. Действующий нормативный baseline —
> `TECHNICAL_ARCHITECTURE_v0.3.md`; v0.2 не разрешает deployment,
> persistence или возврат prototype runtime.

- Статус: проектная редакция для утверждения владельцем продукта
- Дата: 2026-08-19
- Владелец продукта: Олег Щербаков
- Основание: `README.md`; `docs/product/PRODUCT_SCOPE.md`;
  `docs/mvp/FUNCTIONAL_MODEL_v0.1.md`; ADR-0001—ADR-0004;
  `docs/product/PRODUCT_OPERATING_MODEL_v0.1.md`;
  `docs/product/DETERMINISTIC_RULES_MODEL_v0.1.md`;
  `docs/product/AUTOMATION_AND_EXCEPTIONS_v0.1.md`;
  `docs/mvp/MVP_ACCEPTANCE_SCENARIOS_v0.1.md`;
  `docs/architecture/IMPLEMENTATION_BASELINE.md`;
  `docs/architecture/AUTHORIZATION_AND_AUDIT_MODEL_v0.1.md`;
  `docs/architecture/decisions/0006-local-first-hybrid-vlm-execution.md`;
  `docs/architecture/decisions/0007-four-mode-product-readiness.md`;
  `docs/architecture/decisions/0008-mbp-primary-distributed-topology.md`;
  `docs/architecture/TECHNICAL_ARCHITECTURE_v0.1.md` (заменяется этой
  редакцией в части инфраструктурных решений, раздел 0.1)
- Область действия: исторический инфраструктурный срез для общего ядра
  «Изучение ОКС» и пилота ТМ-35 (Хабаровск). Он не является полной
  Technical Architecture продукта и не задаёт границу MVP/готовности:
  по ADR-0007 требуются все четыре режима. Код приложения, БД-миграции и
  UI не создаются.

> **Статус преемника на 2026-08-22.**
> `TECHNICAL_ARCHITECTURE_v0.3.md` подготовлена как `Proposed technical
> baseline` и заменяет целевые topology/mechanism choices этой редакции.
> Это не подтверждает реализацию и не открывает deployment/implementation
> gate; v0.2 сохраняется только как исторический evidence.

## 0. Статус относительно v0.1

### 0.1. Что заменяется

Две рекомендации v0.1 прямо отменены установкой владельца продукта в
этом задании — не как предпочтение, а как решённый вопрос:

| Пункт v0.1 | Было | Стало (v0.2) | Раздел |
|---|---|---|---|
| AD-01 | SQLite (сервер + клиент) | **PostgreSQL** как серверная БД | 5 |
| AD-02 | Event sourcing (полный) | **Версионируемые записи + append-only аудит** | 6 |

AD-03 (транспорт полевой синхронизации), AD-04 (формат идентификаторов),
AD-05 (гранулярность `SourceCorpus`/`StudyOfConstructionObject`) — без
изменений, переносятся из v0.1. `docs/architecture/TECHNICAL_ARCHITECTURE_v0.1.md`
сохраняется как исторический документ (в нём зафиксирован ход рассуждения
к AD-01/AD-02, полезный для понимания, почему отмена — не тривиальное
решение); его устаревшая граница Support/MVP помечена как superseded
ADR-0007.

### 0.2. Что не меняется

Логическая доменная модель (`docs/architecture/DOMAIN_CORE_SPEC_v0.1.md`)
не меняется этим документом: агрегаты, команды, события, инварианты —
те же. Меняется **реализация модели истины** (раздел 6) — событие домена
теперь материализуется как запись в append-only аудите и как новая
версия соответствующей записи, а не как единственный источник состояния,
требующий воспроизведения через replay.

### 0.3. Принятые решения этой редакции

Подтверждённые владельцем продукта факты об инфраструктуре VPS `kat-core`
закрывают часть открытых архитектурных решений v0.2 (раздел 13 в прошлой
редакции этого документа). Зафиксированы как принятые, не как рекомендации:

| Решение | Было (открыто) | Принято |
|---|---|---|
| AD-06 — фоновые задачи | рекомендация arq | **arq + Redis** |
| AD-08 — топология Nginx | не определено (системный/контейнерный) | **`kat_nginx` — существующий контейнер, сеть `kat_default`**; без публикации host-портов, без 127.0.0.1 (`docs/devops/DEPLOYMENT_TOPOLOGY_v0.1.md` §1) |
| AD-09 — квота TTL-кэша блобов | ориентир 5 GB | **2 GiB** |
| OD-DEVOPS-03 — стратегия deploy | не выбрано | **deploy по release-тегу** (`docs/devops/CI_CD_AND_OPERATIONS_v0.1.md` §4.2) |
| OD-DEVOPS-04 — retention бэкапов | рекомендация 14 дней + 3 месяца | **7 daily / 4 weekly / 12 monthly** (`docs/devops/CI_CD_AND_OPERATIONS_v0.1.md` §5) |
| OD-DEVOPS-06 — периодичность restore drill | не определена | **ежемесячно** (`docs/devops/CI_CD_AND_OPERATIONS_v0.1.md` §7) |
| — Доступ до RBAC | не рассматривалось | **Nginx Basic Auth на `tm.asd-kontur.ru`** на уровне `kat_nginx`, снимается только явным решением при вводе RBAC (`docs/devops/DEPLOYMENT_TOPOLOGY_v0.1.md` §1.4) |
| — БД, модель истины | — | без изменений §0.1: **PostgreSQL**, версионируемые записи + append-only `audit_log` |

PostgreSQL и версионируемые записи + `audit_log` (раздел 0.1) остаются
без изменений — перечислены здесь для полноты списка принятых решений,
не потому что были под вопросом в этом задании.

Не решено этой редакцией: AD-07 (провайдер/бакеты S3 — раздел 13, теперь
часть проверки перед первым деплоем,
`docs/devops/DEPLOYMENT_TOPOLOGY_v0.1.md` §0.1), AD-10 (архивирование
`audit_log` за пределами пилота).

### 0.4. Нормативный статус topology после ADR-0008

ADR-0008 принят владельцем продукта 2026-08-21 и **заменяет** placement-
утверждения этой v0.2 в части VPS-primary production core и PostgreSQL. Теперь
MBP является primary authoritative node с канонической PostgreSQL и domain
core; VPS — обязательный coordination/integration node; S3-compatible storage
— обязательный durable object plane, но не current state или доменная БД.

Поэтому VPS-centric diagram/stack/flow/resource/deployment details §§2–5,
8, 10–12 и связанные devops-документы являются историческим проектным срезом,
а не разрешённой целевой topology. Они могут служить evidence существующих
ограничений и вариантов, но не подлежат реализации до Technical Architecture
v0.3. Конкретные PostgreSQL replication, queue/broker, network, encryption,
RPO/RTO, restore/failover, S3 provider/layout и external-VLM route остаются
`TA-TD-*`; отсутствие решения означает fail-closed. Проверенные факты о
существующей инфраструктуре не превращаются этим замечанием в утверждение о
целевом размещении.

## 1. Контекст продукта и общего ядра «Изучение ОКС»

Без повторного изложения — см. `docs/product/PRODUCT_OPERATING_MODEL_v0.1.md`
§1–2. Инфраструктурно значимое:

- первый разворачиваемый функциональный контур — общее ядро «Изучение
  ОКС» (`SourceCorpus → StudyOfConstructionObject → WorkTypeRegister →
  RequirementApplicability → RequiredDocumentMatrix`,
  `docs/architecture/DOMAIN_CORE_SPEC_v0.1.md` §17.1), не сценарный слой
  «Сопровождение» — инфраструктура этой редакции спроектирована под
  нагрузку изучения (пакетная обработка корпуса документов пилота), не
  под непрерывный офлайн-полевой поток;
- пилот — ТМ-35, Хабаровск, целевой адрес `https://tm.asd-kontur.ru`.
  Это первое содержательное определение D-02 (пилотный ОКС) с прошлой
  редакции — само по себе не закрывает D-02 полностью (технологическая
  цепочка пилота внутри ТМ-35 всё ещё не зафиксирована), но снимает
  блокировку с инфраструктурной части работы.

Эта последовательность допустима только как поэтапная внутренняя разработка.
Она не откладывает Tender, Audit или Restoration за границу готовности и не
позволяет объявить продукт готовым после ввода общего ядра, Support либо
успешного прогона ТМ-35.

## 2. Логическая архитектура и границы модулей

Без изменений от `TECHNICAL_ARCHITECTURE_v0.1.md` §3 в части разделения
общего ядра и сценарного слоя, в части независимости домена от фреймворка.
Уточнение физической реализации:

```text
┌──────────────────────────────────────────────────────────────────┐
│ Adapters                                                          │
│  FastAPI HTTP Adapter (Core Command/Query, раздел 8)               │
│  PostgreSQL Repository Adapter (версионируемые записи + аудит)     │
│  S3 Blob Adapter (контент-адресуемое хранилище)                    │
│  Google Drive Import Adapter (разовый/периодический импорт корпуса)│
│  Extraction Candidate Adapter (приём кандидатов из контура OCR)     │
│  Redis Queue Adapter (фоновые задачи rules engine)                 │
├──────────────────────────────────────────────────────────────────┤
│ Application слой (FastAPI, worker)                                  │
│  Command Handlers | Query Handlers | Rules Engine Orchestrator      │
├──────────────────────────────────────────────────────────────────┤
│ Domain Core — без изменений от DOMAIN_CORE_SPEC_v0.1.md              │
│  SourceCorpus, StudyOfConstructionObject, WorkTypeRegister,         │
│  Requirement/RequirementApplicability, RequiredDocumentMatrix,      │
│  Source (полная модель)                                             │
└──────────────────────────────────────────────────────────────────┘
                              ▲
                              │ кандидаты (никогда решения — раздел 7)
┌──────────────────────────────────────────────────────────────────┐
│ Контур OCR/VLM-извлечения — provider-neutral boundary               │
│  (раздел 7): local-first MBP + policy-authorized external provider  │
│  вне процесса FastAPI/worker на VPS                                 │
└──────────────────────────────────────────────────────────────────┘
```

Правило зависимости не изменилось: Domain Core не знает о FastAPI,
PostgreSQL или S3 — эти адаптеры реализуют порты, определённые доменом
(`TECHNICAL_ARCHITECTURE_v0.1.md` §3, без изменений).

## 3. Технологический стек

| Компонент | Выбор | Обоснование |
|---|---|---|
| Язык/рантайм | Python 3.12, `uv` | без изменений (`IMPLEMENTATION_BASELINE.md`) |
| API-фреймворк | **FastAPI** | новое в v0.2 — типизированный контракт Core Command/Query (раздел 8), встроенная валидация, совместим с async-обработкой очереди |
| Серверная БД | **PostgreSQL 17** (или последняя LTS-подобная стабильная на момент разворачивания — раздел 12.1) | реальная многопользовательская конкурентность (FastAPI + worker пишут одновременно), встроенная поддержка `JSONB` для гибких полей `EvidenceRequirement`/`RegulatoryRowReference`, зрелая экосистема миграций (Alembic, `CI_CD_AND_OPERATIONS_v0.1.md` §1) |
| Очередь/кэш | **Redis 7** | брокер задач для контура правил (запуск `RerunStudyOfConstructionObject` и т.п.), лёгкий footprint при 7.8 GiB RAM (раздел 10) |
| Фоновые задачи | **arq** (принято, раздел 0.3) | async-нативная, Redis-based, легче Celery по памяти и числу процессов — существенно при ограничении VPS |
| Файловое хранилище | **S3-совместимое** (провайдер — открытое решение AD-07, теперь часть проверки перед первым деплоем, `DEPLOYMENT_TOPOLOGY_v0.1.md` §0.1) | контент-адресуемое хранение блобов (`TECHNICAL_ARCHITECTURE_v0.1.md` §5.3, без изменений принципа), резервные копии PostgreSQL (`CI_CD_AND_OPERATIONS_v0.1.md` §5) |
| Reverse proxy | **`kat_nginx`** — существующий контейнер reverse proxy на VPS `kat-core`, подключён к сети `kat_default`; не разворачивается заново | маршрутизация по домену без занятия 80/443; `asd-kontur-api` подключается к `kat_default` и доступен `kat_nginx` по имени контейнера `asd-kontur-api:8000`, без публикации host-портов (`DEPLOYMENT_TOPOLOGY_v0.1.md` §1, §3) |
| Контейнеризация | Docker Compose, отдельный проект `asd-kontur` (`DEPLOYMENT_TOPOLOGY_v0.1.md` §2) | изоляция от существующего `kat_*`; единственная точка соприкосновения — членство `asd-kontur-api` во внешней сети `kat_default` |

Domain Core (раздел 2) остаётся зависим только от стандартной библиотеки
— ни PostgreSQL, ни FastAPI, ни Redis не проникают в пакет домена;
зависимость идёт от Application слоя к портам, реализуемым адаптерами
(`TECHNICAL_ARCHITECTURE_v0.1.md` §3, без изменений).

## 4. Размещение компонентов — accepted baseline ADR-0008

| Площадка | Роль | Что размещается | Что НЕ размещается |
|---|---|---|---|
| MBP authoritative node | единственный active primary и каноническое ядро | canonical PostgreSQL/domain/workspace state, platform knowledge/НТД/rules, Knowledge Gateway, deterministic core, local Qwen, confirmation/promotion/finalization/lifecycle authorization | identity, привязанная к серийному номеру; silent failover; обход human/policy authority |
| VPS coordination/integration node | ingress, remote/UI/auth gateway, bounded queues/staging, integrations/status, controlled egress | только разрешённые envelopes, projections, encrypted staging и integration state по будущим TA contracts | независимый domain core/SoR, fact confirmation, Rule/Promotion approval, finalization, destructive authorization, automatic primary |
| External VLM provider (планируемый `polza.ai`) | policy-разрешённая массовая обработка растровых PDF через provider-neutral boundary | только минимизированные pages/regions точного workspace invocation | SQL, workspace storage, соседние документы, human authority, credentials платформы, произвольные tools |
| S3-compatible durable object plane | workspace/platform-scoped byte storage, archive and recovery plane | permitted source/large/raw/export/archive/backup/recovery objects, versions, manifests and hashes | domain current state, fact/rule/result authority, executable restored state, cross-workspace physical deduplication |

Ранее приведённые для VPS `kat-core`, Docker Compose, Redis/arq, Google Drive
и пилота ТМ-35 конкретные placements являются историческими v0.2 proposals.
Они не подтверждают текущую конфигурацию и не определяют Technical
Architecture v0.3.

## 5. Поток загрузки, хеширования, версионирования и обработки документов

Следующая схема сохранена как исторический pilot-flow v0.2. После ADR-0008
регистрация canonical metadata, принятие команд и deterministic processing
принадлежат MBP authoritative core; VPS может только доставлять bounded
ingress, а S3 write не означает admission. Точный inter-node flow будет
определён Technical Architecture v0.3.

```text
Google Drive (корпус ТМ-35)
   │  Google Drive Import Adapter — первичный импорт выполняется ОТДЕЛЬНО
   │  на MBP или на выделенном ingestion-узле (раздел 4), НЕ запускается
   │  из GitHub Actions/CI (docs/devops/CI_CD_AND_OPERATIONS_v0.1.md §1.3)
   │  и НЕ является постоянной runtime-зависимостью боевого контура на VPS
   ▼
Вычисление SHA-256 → загрузка блоба в S3 (контент-адресуемо,
   TECHNICAL_ARCHITECTURE_v0.1.md §5.3, без изменений схемы адресации)
   ▼
Регистрация SourceCorpusEntry в PostgreSQL (метаданные: SourceType,
   ContentHash, EffectivePeriod, происхождение — DOMAIN_CORE_SPEC_v0.1.md §5.1)
   ▼
StudyOfConstructionObject запускается (worker, очередь Redis)
   ▼
Контур OCR/извлечения (раздел 7): trusted adapter читает разрешённый блоб,
   сначала использует пригодный native text, затем выбирает local-first MBP
   либо policy-разрешённый external provider; внешнему provider передаёт
   только минимизированные pages/regions, не S3/workspace capability;
   публикует КАНДИДАТОВ через Extraction Candidate Adapter
   ▼
Rules Engine (раздел 6) — единственный писатель в WorkTypeRegister/
   RequirementApplicability/RequiredDocumentMatrix; каждое решение —
   новая версия записи (раздел 6) + запись в append-only аудите
   (источник → версия → извлечение → правило → результат,
   docs/product/DETERMINISTIC_RULES_MODEL_v0.1.md §7)
```

Ни один шаг после регистрации `SourceCorpusEntry` не имеет прямого пути
записи в домен в обход Rules Engine — в том числе контур OCR/извлечения
(раздел 7).

## 6. Версионируемые записи и append-only аудит (замена event sourcing)

### 6.1. Принцип

Вместо единственного источника истины в виде журнала событий, из
которого пересобирается состояние (v0.1, AD-02, отменено), — два
параллельных, более лёгких по нагрузке механизма:

- **версионируемые записи.** Значимые таблицы (`work_type_entry`,
  `required_document_matrix_entry`, `requirement`, `source_version` и
  т.д.) никогда не обновляются `UPDATE` по значимым полям. Изменение
  состояния — это `INSERT` новой строки с новым `version`,
  `valid_from`, ссылкой `supersedes_version_id`, и установка
  `valid_to`/`is_current = false` у предыдущей строки в той же
  транзакции. Текущее состояние читается прямым запросом
  (`WHERE is_current`), не пересборкой из истории — дешевле на CPU и
  проще для 7.8 GiB RAM, чем поддержание проекций event-sourced системы;
- **append-only аудит.** Отдельная таблица (или партиционированный
  набор таблиц по месяцу) `audit_log`, в которую пишется запись при
  КАЖДОМ применении правила и при каждой команде — независимо от того,
  создала ли она новую версию. Обязательные поля соответствуют формату
  объяснения (`docs/product/DETERMINISTIC_RULES_MODEL_v0.1.md` §7):
  правило, версия правила, ссылки на источники/локаторы, digests или
  разрешённые типизированные inputs без копирования project content,
  результат, актор/инициатор, authorization/policy versions и время.
  Точный content allowlist и post-reset projection определены
  `AUTHORIZATION_AND_AUDIT_MODEL_v0.1.md` §9 и RD-03/A. `audit_log` —
  `INSERT`-only на уровне прав доступа роли приложения (раздел 9.2), без
  `UPDATE`/`DELETE` прав вообще, не только по соглашению.

### 6.2. Почему это не ослабляет ADR-0003

ADR-0003 требует происхождения и невозможности молчаливого разрешения
конфликта — оба требования выполняются версионируемыми записями (история
не теряется, каждая версия хранит предыдущую ссылку) и аудитом (решение
и его причина воспроизводимы). Событийная модель домена
(`DOMAIN_CORE_SPEC_v0.1.md` §9, каталог доменных событий) не переименована
и не удалена. Доменное событие и запись `audit_log` логически различны и
связываются через command/correlation/causation: отклонённая команда или
аудит доступа могут не порождать доменное событие, а один материальный
переход может требовать нескольких audit-записей. Точные контракты определены
в `PROCESS_AND_EVENT_SPECIFICATION_v0.1.md` §§2, 6–8. Отличие от event
sourcing в том, что ни событие, ни `audit_log` не обязаны быть способом
реконструкции текущего состояния — оно лежит в версионируемых записях
напрямую.

### 6.3. Стоимость и ограничение

`audit_log` растёт монотонно и не сжимается партиционированием состояния
(в отличие от event sourcing, где можно строить снапшоты и архивировать
старые события отдельно от чтения). Для масштаба пилота (один ОКС, один
подрядчик) объём предсказуемо мал; при расширении за пределы пилота
потребуется политика архивирования старых партиций `audit_log` в S3 —
зафиксировано как открытое решение (раздел 13).

## 7. Раздельный provider-neutral контур OCR/VLM-извлечения

Не входит в тот же процесс/контейнер, что Rules Engine — структурное
ограничение, не только организационное:

- физически: контур OCR/VLM выполняется вне VPS-развёртывания этой редакции.
  Основной local-first runtime — `Qwen3.8-27B` на MBP; для
  policy-разрешённой массовой обработки растровых PDF допускается внешний
  `VlmExecutionProvider` (планируемый provider — `polza.ai`). VPS не
  располагает ресурсами для OCR/VLM-инференса (раздел 10), но это ограничение
  topology не означает local-only architecture;
- логически: контур обращается к боевому контуру исключительно через
  `Extraction Candidate Adapter` — публикует кандидатов
  (`docs/product/PRODUCT_OPERATING_MODEL_v0.1.md` §3.1), не имеет
  прав записи ни в одну из версионируемых доменных таблиц и не имеет
  доступа к `audit_log` на запись;
- отказ или недоступность контура OCR/извлечения не останавливает
  Rules Engine — при отсутствии кандидатов правило создаёт исключение
  «недостаточная определённость» (`docs/product/AUTOMATION_AND_EXCEPTIONS_v0.1.md`
  §4.3, категория 3.5), не блокирует систему целиком;
- итоговый статус (`ГОТОВ К ВЫПУСКУ`/`ЗАБЛОКИРОВАН`/`ИСКЛЮЧЕНИЕ`,
  `docs/product/DETERMINISTIC_RULES_MODEL_v0.1.md` §8) не может зависеть
  от контура OCR/извлечения напрямую — только через прохождение решения
  Rules Engine, что технически выражается отсутствием у контура прав
  записи (предыдущий пункт), а не только регламентным запретом.

По принятому ADR-0006 local и external providers реализуют один логический
request/result contract. Обязательный execution provenance раздельно
версионирует provider, endpoint/profile, model revision,
quantization/execution format, prompt, output schema, preprocessing, rendering
parameters и verification policy. Имя модели само по себе не определяет
эквивалентность результата.

Router выполняет native deterministic extraction первым и выбирает provider по
data classification, `WorkspaceEgressPolicy`, document/raster state, объёму,
сложности, latency/cost, qualification, availability и verification profile.
Внешний вызов требует отдельной integration identity,
`vlm.external.invoke`, точного `workspace_id`, provider/model/profile
allowlist, purpose limitation, минимизированных page/region locators и
provider processing/retention policy. Cross-workspace batch запрещён;
fallback проходит новую authorization evaluation и не расширяет egress.

Ответ любого provider остаётся typed Candidate/draft. Внешний provider не
получает прямой SQL, workspace storage, произвольный Knowledge Tool Gateway,
human authority или право confirmation/finalization/promotion. Prompt injection
в документе не меняет authorization envelope. Единый quality contract будущего
`AI_VLM_EXECUTION_AND_VERIFICATION_HARNESS_SPECIFICATION_v0.1.md` обязателен,
но не реализуется этой редакцией.

## 8. Интерфейсные границы (FastAPI)

Уточнение `TECHNICAL_ARCHITECTURE_v0.1.md` §11 под конкретный фреймворк —
границы не меняются, добавляется физическая реализация:

| Граница v0.1 | Реализация в v0.2 |
|---|---|
| Core Command/Query | FastAPI-роуты, вызывающие Application слой; без прямого доступа роутов к репозиториям в обход команд |
| Field Sync Boundary | зарезервировано (раздел 9), не реализуется в этой редакции — общее ядро не требует полевого клиента на первом этапе |
| Export/Report Boundary | FastAPI read-only роуты поверх версионируемых записей |
| AI Candidate Boundary | `Extraction Candidate Adapter` (раздел 7) принимает единый typed Candidate contract; local runtime использует service identity, внешний provider — отдельную integration identity и `vlm.external.invoke`; endpoint не даёт provider прямой записи в домен |
| External Estimation/Legal Boundary | не реализуется, зарезервировано (`TECHNICAL_ARCHITECTURE_v0.1.md` §10, без изменений) |

## 9. Offline-first в будущей полевой части

Не реализуется в этой редакции (общее ядро «Изучение ОКС» не требует
полевого клиента — работа с документами и корпусом, не с фактами на
площадке). Зарезервировано архитектурно без изменений принципа
(`TECHNICAL_ARCHITECTURE_v0.1.md` §6): устойчивый `OperationId`,
идемпотентный приём, конфликт не разрешается молча. При появлении
сценарного слоя «Сопровождение» с реальным полевым вводом — `Field Sync
Boundary` (раздел 8) получит реализацию поверх той же версионируемой
модели (раздел 6): операция клиента = попытка создать новую версию
записи, идемпотентность обеспечивается уникальным индексом по
`OperationId` в PostgreSQL, не отдельным журналом.

## 10. Исторические ресурсные ограничения VPS (не target placement)

VPS `kat-core`: Ubuntu 26.04 LTS, ~7.8 GiB RAM, 35 GB свободного места,
порты 80/443 заняты существующим контейнером `kat_nginx` (сеть
`kat_default`), существует отдельный Compose-проект `kat_*`.

### 10.1. Бюджет RAM (ориентировочный, требует замера на пилоте)

| Компонент | Ориентир RAM | Комментарий |
|---|---|---|
| PostgreSQL | 512 МБ–1 ГиБ | `shared_buffers` уменьшен под малый датасет пилота (раздел 12.1) |
| Redis | 128–256 МБ | только очередь задач + лёгкий кэш, без больших структур в памяти |
| FastAPI (uvicorn, N воркеров) | 300–600 МБ | 2 воркера достаточно для пилота одного ОКС |
| arq worker | 200–400 МБ | без параллельного OCR/VLM (раздел 7) |
| ОС + Docker + существующий `kat_*` | остаток | `kat_*` уже занимает часть RAM — точный остаток требует замера на самом VPS перед деплоем (раздел 13, открытое решение) |

Явное ограничение: **VPS не размещает OCR/VLM-инференс** (раздел 7) —
это не рекомендация, а условие, при котором бюджет RAM вообще сходится.

### 10.2. Бюджет диска (35 GB)

| Категория | Оценка | Политика |
|---|---|---|
| Docker images (app, worker, postgres, redis) | 2–4 GB | слим-образы, регулярная очистка неиспользуемых слоёв |
| PostgreSQL данные (метаданные + аудит, БЕЗ блобов) | растёт медленно (раздел 6.3) | мониторинг роста, алерт при приближении к порогу (`CI_CD_AND_OPERATIONS_v0.1.md` §6) |
| Локальный TTL-кэш блобов | **2 GiB** (принято, раздел 0.3) | автоочистка по TTL и по LRU при достижении квоты — раздел 11 |
| Логи | ограничены ротацией (`CI_CD_AND_OPERATIONS_v0.1.md` §6) | logrotate/Docker `max-size` |
| Резервные копии | **0 постоянно на VPS** | бэкапы уходят в S3 немедленно, локальная копия не хранится дольше времени выгрузки (раздел 11, `CI_CD_AND_OPERATIONS_v0.1.md` §5) |

## 11. Историческая VPS cache policy и сохраняемый принцип data minimization

Жёсткое архитектурное ограничение, не рекомендация:

- источник истины для блобов — S3 (раздел 4); VPS никогда не является
  местом постоянного хранения ни одного блоба;
- допустим только **TTL-кэш** ограниченного объёма (раздел 10.2) для
  блобов, к которым контур OCR/извлечения или Rules Engine обращаются в
  моменте — кэш очищается по TTL и по квоте, отсутствие записи в кэше не
  является ошибкой (перечитывается из S3);
- при импорте из Google Drive (раздел 5) файл не сохраняется на диске
  VPS постоянно — загрузка идёт потоком в S3, локальная временная копия
  (если используется для вычисления хеша) удаляется сразу после загрузки;
- проверка соблюдения — не только архитектурная декларация: healthcheck/
  cron-проверка объёма локального кэша блобов против квоты
  (`CI_CD_AND_OPERATIONS_v0.1.md` §6) как эксплуатационный контроль, а не
  только договорённость в тексте документа.

## 12. Данные о PostgreSQL

### 12.1. Настройка под малую машину

Пилот — один ОКС, один подрядчик (`FUNCTIONAL_MODEL_v0.1.md` §3.1) — не
требует настройки под высокую нагрузку. Ориентиры (уточняются при
первом деплое, не хардкодятся сейчас): `shared_buffers` ~ 256 МБ,
`max_connections` ограничен (пул соединений на стороне FastAPI/arq, не
десятки прямых соединений), `work_mem` консервативный. Точные значения
— задача первой реализации (раздел «Задачи первой реализации» в отчёте),
не архитектурное решение уровня этого документа.

### 12.2. Миграции

Alembic (стандартный инструмент для PostgreSQL в экосистеме Python,
без установленной альтернативы в проекте) — управляет схемой
версионируемых таблиц и `audit_log`. Миграции только вперёд в проде
(`CI_CD_AND_OPERATIONS_v0.1.md` §1); откат схемы — через новую миграцию,
не через `downgrade` на боевых данных (несовместимо с неизменяемостью
истории, `DOMAIN_CORE_SPEC_v0.1.md` §7.2).

## 13. Открытые архитектурные решения (v0.2)

После ADR-0008 этот раздел сохраняет историю вопросов v0.2, но не является
актуальным decision packet. Нормативный пакет для Technical Architecture
v0.3 — `INFORMATION_ARCHITECTURE_v0.1.md` §6.8,
`TA-TD-01…TA-TD-22`: single-primary/fencing, VPS projection/staging,
sync/network/TLS/keys/encryption, S3 provider/isolation/versioning,
backup/RPO/RTO/restore, outage/egress/observability/update/remote/offline.
Ни один вариант там не принят этим документом.

В частности, AD-07 не является просто проверкой перед первым deploy: provider,
region и namespace/isolation S3 требуют TA-TD-11…TA-TD-13 и применимых
policy approvals. AD-03 входит в TA-TD-05/22. AD-10 является RetentionProfile/
operations policy instance и не может зависеть от «пилота одного ОКС».
Ни ТМ-35, ни второй ОКС не задают границу принятия решения или готовности.

Закрытые этой редакцией решения (AD-06, AD-08, AD-09) перечислены с их
итоговым значением в разделе 0.3, не повторяются здесь.

- **AD-07** — провайдер и регион S3-совместимого хранилища, схема
  именования бакетов (блобы отдельно от бэкапов БД или один бакет с
  префиксами) — не указан пользователем; переведено из абстрактного
  архитектурного решения в конкретный пункт проверки перед первым деплоем
  (`docs/devops/DEPLOYMENT_TOPOLOGY_v0.1.md` §0.1) — это внешний доступ,
  не решение, которое можно принять на уровне архитектуры.
- **AD-10** — политика архивирования `audit_log` при росте за пределы
  пилота (раздел 6.3) — не актуально для пилота одного ОКС, но должна
  быть решена до расширения на второй ОКС/подрядчика.
- Перенесены без изменений из v0.1: AD-03 (транспорт полевой
  синхронизации — раздел 9, отложено), AD-04 (формат идентификаторов),
  AD-05 (гранулярность `SourceCorpus`/`StudyOfConstructionObject`).
- D-02 (пилотный ОКС) — частично снято: ОКС определён как ТМ-35,
  Хабаровск; технологическая цепочка внутри пилота — всё ещё не
  зафиксирована. D-04 (организационная модель использования) — без
  изменений, не снято.
- Local-first hybrid VLM execution принято ADR-0006 и не является открытым
  решением. До первого внешнего вызова остаются обязательными policy data:
  data classification taxonomy, точная `WorkspaceEgressPolicy`, provider
  processing/retention policy, destination/provider/model/profile allowlist и
  qualification конкретной revision/profile. Их отсутствие означает default
  deny, а не возврат к blanket local-only или разрешение другого provider.
