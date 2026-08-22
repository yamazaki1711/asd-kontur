# АСД-КОНТУР — Architecture Blueprint v0.1

**Статус:** Accepted architecture baseline
**Дата:** 22 августа 2026
**Область:** универсальный программный комплекс АСД-КОНТУР; не архитектура пилота ТМ-35.

**Архитектурные полномочия:** владелец продукта Олег Щербаков 2026-08-22
явно уполномочил Codex принимать согласованные архитектурные решения с
фиксацией вариантов, оснований, последствий, проверок, migration path и
acceptance criteria. Полномочие не распространяется на факты ОКС,
professional/legal confirmation, утверждение RuleVersion вместо qualified
human approver, destructive production operations, egress/spend/provider
policies и evidence-dependent retention, qualification или budget values.

## 1. Назначение

Этот документ переводит утверждённую функциональную модель в исходную архитектурную рамку. Он фиксирует, **какой комплекс проектируется**, какие его части переиспользуются между ОКС, где проходит граница проектных данных и какие проектные артефакты обязательны до расширения кода и деплоя.

АСД-КОНТУР — не хранилище файлов, не разовый анализатор одного объекта и не набор LLM-агентов. Это доказательный инженерный комплекс, который обрабатывает очередной ОКС как изолированную рабочую область, а затем может быть подготовлен к следующему ОКС без смешения данных, правил, статусов и результатов.

## 2. Основания

- `README.md`, `docs/product/PRODUCT_SCOPE.md`;
- `docs/mvp/FUNCTIONAL_MODEL_v0.1.md`;
- ADR-0001…ADR-0008;
- `docs/architecture/TECHNICAL_ARCHITECTURE_v0.3.md` — accepted technical
  baseline принятой MBP/VPS/S3 topology; не факт реализации и не разрешение
  deploy;
- прямые решения владельца продукта: АСД-КОНТУР — обезличенный «конвейер»,
  очищаемый между партиями документов разных ОКС; VLM execution — local-first
  hybrid с provider-neutral boundary; официальный каталог Минстроя —
  приоритетный source НТД; промышленная готовность требует сквозной
  готовности всех четырёх режимов; MBP является primary authoritative node,
  VPS — coordination/integration node, S3-compatible storage — mandatory
  durable object plane одного логического комплекса.

При конфликте этот Blueprint не заменяет утверждённую функциональную модель: он конкретизирует её для последующего технического проектирования.

## 3. Ценность продукта и режимы

Комплекс должен формировать доказательные результаты:

1. протокол разногласий и редакцию договора, защищающую подрядчика;
2. анализ ПД/РД: неучтённые объёмы и МТР, конструктивные/геометрические коллизии и ошибки;
3. исполнительные схемы только по подтверждённым проектным и исполнительным геометрическим данным.

Режимы продукта: **Тендер**, **Сопровождение**, **Аудит**,
**Восстановление**. По ADR-0007 АСД-КОНТУР считается готовым только при
сквозной готовности всех четырёх режимов. Поэтапная внутренняя разработка
разрешена, но Support, ТМ-35 или любой иной отдельный режим/корпус не
является границей MVP либо промышленной готовности.

Для каждого режима обязательны: определённые входы; сквозной процесс через
общее ядро; pinned или контролируемо обновлённый применимый
`RuleSetVersion`; выходные документы/результаты; uncertainties и blocking
conditions; полномочия; E2E acceptance tests; terminal condition
промышленной готовности. Формальный режимный контракт задан в
`PROCESS_AND_EVENT_SPECIFICATION_v0.1.md` §5. Готовность продукта является
конъюнкцией terminal conditions всех режимов и общеплатформенных
инвариантов.

Базовая цепочка общего ядра:

```
ПД/РД + договорные требования + регламент заказчика + НТД
→ структура ОКС
→ виды и объёмы работ
→ МТР
→ контроли
→ обязательные доказательства
→ исполнительная документация
→ предъявляемые объёмы
→ КС
→ оплата
```

## 4. Архитектурный принцип: платформа и рабочая область ОКС

### 4.1. Платформа АСД-КОНТУР

Переиспользуемая часть комплекса:

- идентификация организаций, пользователей, ролей и прав;
- доменная модель и оркестрация режимов;
- каталоги правил, шаблонов, классификаторов и версий;
- библиотека НТД и механизм установления применимой редакции;
- механизм источников, версий, локаторов и доказательственного следа;
- аудит действий и решений;
- интерфейсы, отчётные представления и интеграционные контракты;
- инфраструктура развёртывания, резервирования и наблюдаемости.

### 4.2. Рабочая область ОКС

Изолированный набор данных одного объекта:

- исходные документы, их версии и структура поставки;
- договор, регламенты заказчика и применимые к данному ОКС правила;
- структура ОКС, работы, МТР, контроли, факты и документы ИД;
- кандидаты извлечения, подтверждения, неопределённости и блокировки;
- расчётные результаты, проекты документов и утверждённые выходы;
- журнал действий и доказательственные связи только этого ОКС.

Ни путь к папке, ни название раздела, ни классификатор конкретного ОКС не являются частью глобальной схемы без явного утверждения их как общего справочника.

## 5. Жизненный цикл ОКС

| Состояние | Назначение | Разрешённые действия |
|---|---|---|
| **Инициализация** | Создание рабочей области и фиксация контекста: организация, ОКС, режим, источники, профиль правил. | Загрузка и верификация источников; настройка доступа. |
| **Активная обработка** | Извлечение кандидатов, применение правил, фиксация фактов, подготовка результатов. | Работа режимов, синхронизация, исправления с версионированием. |
| **Контролируемое закрытие** | Проверка полноты, экспорт результата и фиксация неизменяемой версии выдачи. | Закрытие незавершённых задач, утверждение/архивирование. |
| **Архив/хранение** | Сохранение доказательств и аудита на срок, установленный политикой. | Только регламентированный доступ и экспорт. |
| **Сброс рабочей области** | Освобождение операционного контура для следующего ОКС. | Удаление/анонимизация/перенос — только по утверждённой политике хранения. |

Сброс удаляет operational project content только после verified portable archive/export, integrity verification, legal-hold check и двухстадийного разрешения по принятому `RetentionProfile`. WAL, backups, snapshots и portable archive учитываются как отдельные residues/copies до истечения своих policy periods; после verified reset сохраняются только content-free audit и `DestructionAttestation`.

Формальная state machine, различение `archive/reset/purge/destroy`, карта
носителей, протокол доказанной очистки и Decision Cards `RD-01…RD-05`
определены в
`docs/architecture/LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md`
(`Accepted architecture baseline`; `RD-01…RD-05` — `Accepted` владельцем
продукта 2026-08-21).
Принятие RD не является разрешением немедленно реализовать
destructive-операции или персистентность: сначала завершаются последующие
артефакты §11 и Implementation Plan.

## 6. Логические контуры

### A. Реестр источников и доказательств

Принимает файлы, записи и внешние ссылки; фиксирует хеш, тип, источник, версию, дату применимости и локатор фрагмента. Это единственная точка, из которой производный факт может получить доказательственную опору.

### B. Нормативно-правовой и договорный контур

Хранит НТД, договорные требования и регламенты заказчика как разные слои знаний. Для каждого правила сохраняются источник, редакция, период действия и область применимости. Нельзя сводить НТД, практику и экспертное мнение в неразмеченный текст.

Официальный каталог Минстроя является приоритетным source для планомерного
пополнения НТД. Пополнение идёт по управляемому реестру релевантности, а не
массовой выгрузкой сайта. Каждый документ и каждая редакция имеют раздельную
identity (`NormativeDocument`/`NormativeEdition`), official URL, дату получения,
SHA-256, точные locators и явную цепочку изменений. Статус и применимость не
выводятся из имени файла; отменённая редакция остаётся в provenance, а
FTS/embeddings/graph остаются перестраиваемыми производными индексами.

Платформа знаний, реализующая этот контур (Canonical Knowledge Model, Deterministic Rule Registry, Retrieval & Graph Index Plane, Knowledge Tool Gateway, Promotion Gate), формализована отдельно: `docs/architecture/KNOWLEDGE_AND_MEMORY_ARCHITECTURE_v0.1.md` и `docs/architecture/DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md` (`Accepted architecture baseline`, hard isolation platform/workspace). Knowledge Tool Gateway этого контура — единственная граница, через которую контур E (AI/OCR/VLM) обращается к знаниям; см. `DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md` §6.

### C. Детерминированное инженерное ядро

Строит структуру ОКС, нормализует виды работ, рассчитывает применимость требований, полноту, блокировки, объёмы и статусы. Все расчётные результаты воспроизводимы по версии правил и входов.

### D. Контур фактов и исполнительной документации

Ведёт МТР, входной контроль, допуск, производство работ, лабораторные/геодезические факты, проекты ИД, подписи и предъявляемые объёмы. Подтверждённая история не переписывается; исправление создаёт новую версию с причиной.

### E. AI/OCR/VLM-контур

Извлекает и интерпретирует кандидаты из визуально или структурно сложных источников. Результат ИИ не становится фактом, видом работ, количеством, геометрией или юридическим выводом без доказательства и применения детерминированного правила. Компонент заменяем и опционален: отсутствие VLM не останавливает обработку источника, для которого достаточно нативного текста, таблицы или правила.

По ADR-0006 контур является **local-first, но не local-only**. Основной
локальный VLM — `Qwen3.8-27B`; для policy-разрешённой массовой обработки
растровых PDF допускается внешний provider (планируемый — `polza.ai`) через
provider-neutral `VlmExecutionProvider`. Любой внешний egress default-deny и
требует `WorkspaceEgressPolicy`, отдельной integration identity, точных
provider/model/profile allowlist, purpose limitation и минимизации payload.
Fallback не расширяет egress permission.

Локальный и внешний execution возвращают один логический typed result contract,
но раздельно версионируют provider, endpoint/profile, model revision,
quantization/execution format, prompt, schema, preprocessing, rendering и
verification policy. Одинаковое имя модели не означает эквивалентный результат.
Единый Verification Harness обязателен; он создаёт validated candidate,
unresolved uncertainty, rejected extraction или provider/model failure, но не
подтверждённый факт.

### F. Контур решений и выходных документов

Формирует доказательные представления: матрицы обязательных документов, дельты аудита, предупреждения до необратимых работ, проекты ИД, договорные документы, отчёты и исполнительные схемы. Выход хранит версию входов, правил, метода и автора/утвердившего лица.

### G. Полевой и синхронизационный контур

Поддерживает offline-first сценарии функциональной модели. Повторная синхронизация не создаёт дублей; конфликт не разрешается молча; права и аудит сохраняются при обмене.

## 7. Минимальные сквозные контракты

Каждый материальный вывод должен быть представлен как проверяемый результат:

```
Result {
  workspace_id
  subject_id
  source_version_id[]
  source_locator[]
  method
  rule_set_version
  status
  uncertainty[] | blocker[]
  produced_at
}
```

Для кандидата извлечения дополнительно обязательны: provider identity,
model/revision/execution profile, версии prompt/schema/preprocessing/rendering/
verification policy, цель извлечения, field-level evidence с locators,
uncertainty, validation results, timings, применимые cost metadata и
retry/repair history. Для нормативного вывода — редакция НТД и дата
применимости. Для расчёта — формула/алгоритм и исходные величины.

Эти контракты являются общей границей между контурами, а не форматом одного пилотного скрипта.

## 8. Инварианты

1. Данные и результаты одного ОКС не участвуют в расчётах другого ОКС.
2. Материальный вывод не существует без источника или явной записи об отсутствии достаточных данных.
3. ИИ не публикует инженерный, юридический или геометрический факт самостоятельно.
4. Изменение источника, правила или факта создаёт новую версию результата; прежняя версия остаётся объяснимой.
5. Нормативное требование не применяется без установленной редакции и области применимости.
6. Синхронизация не удаляет и не подтверждает конфликт молча.
7. Закрытие ОКС фиксирует состав выдачи и не смешивает её с последующей партией.

## 9. Развёртывание: требования, а не преждевременный выбор

ADR-0008 фиксирует accepted physical authority baseline: АСД-КОНТУР —
local-first distributed system; MBP M5 Max — единственный active primary
authoritative node с canonical PostgreSQL/domain core; VPS — обязательный
coordination/integration node; S3-compatible storage — обязательный durable
object plane. VPS и S3 не становятся альтернативным SoR. Restore требует
verification и explicit primary activation; split-brain и silent fallback
запрещены.

Техническая архитектура должна обеспечить:

- локальную работу с чувствительными документами и offline-first полевой контур;
- раздельные окружения разработки, пилота и эксплуатации;
- изоляцию рабочих областей, резервирование и проверяемое восстановление;
- наблюдаемость, журналирование и контроль доступа;
- воспроизводимое развёртывание и миграции;
- исключение неутверждённых внешних передач исходных материалов и
  policy-controlled egress только через разрешённые integration boundaries.

`TECHNICAL_ARCHITECTURE_v0.3.md` принята как `Accepted architecture baseline`
и выбрала механизмы single-primary/fencing,
synchronization/acknowledgement/reconciliation, private network/mTLS,
key/envelope encryption, S3 isolation/versioning, backup/restore,
external-VLM route, observability, updates и offline clients. Выбор механизма
не означает реализации или успешной эксплуатационной проверки. Конкретные
external provider/region, KMS product,
численные RPO/RTO и policy instances остаются versioned deployment/operating
profiles с `default deny` до утверждения.

## 10. Роль ТМ-35

ТМ-35 — тестовый корпус для проверки будущих acceptance-сценариев режима «Сопровождение». Его неполнота полезна как сценарий `missing_source / uncertainty`, но:

- не определяет модель данных;
- не вводит обязательные разделы документов;
- не определяет глобальный классификатор работ;
- не является условием проектирования остальных режимов;
- не должен блокировать разработку универсального каркаса;
- не может доказать готовность Support целиком, другого режима или продукта.

## 11. Очередность проектных артефактов

До расширения прикладного кода должны быть подготовлены и согласованы:

1. **Domain Model v0.1** — принят как architecture baseline и синхронизирован с IA-OD-02/03, единым значением `SourceArtifact`, hard isolation и принятыми retention-решениями. ADR-0005 принят 2026-08-22.
2. **Lifecycle & Retention Specification v0.1** — `Accepted architecture baseline`; RD-01…RD-05 остаются прямыми решениями владельца продукта.
3. **Process/Event Specification v0.1** — `Accepted architecture baseline`; сохраняет canonical current state без полного event replay.
4. **Authorization & Audit Model v0.1** — `Accepted architecture baseline`; определяет capabilities, segregation of duties, default-deny egress и content-minimal audit.
5. **Deterministic Rules Catalogue v0.1** — `Accepted architecture baseline`; DR-01/B…DR-04/B сохраняют qualified human approval и object-independent Rule Registry.
6. **AI/VLM Execution & Verification Harness Specification v0.1** — `Accepted architecture baseline`; HV-01/B…HV-08/B сохраняют native-first, Candidate boundary, default-deny egress, qualification и bounded repair. Численные values требуют evidence.
7. **Information Architecture v0.1** — информационные объекты, system of
   record, scopes `platform/organization/ОКС/workspace`, identity/versioning,
   provenance/lineage, canonical/derived representations и информационные
   контракты четырёх режимов. Проектная редакция подготовлена:
   [`INFORMATION_ARCHITECTURE_v0.1.md`](INFORMATION_ARCHITECTURE_v0.1.md)
   (`Accepted`). Это не архитектура UI, меню или рабочих мест. Документ
   синхронизирован с ADR-0008: содержит physical authority map MBP/VPS/S3,
   inter-node contracts, offline/degraded semantics, no-split-brain/restore,
   S3 object model и `TA-TD-01…TA-TD-22`. Он формализует вход для будущей
   Technical Architecture и Logical Data Model, но не разрешает ORM, DDL,
   миграции или persistence implementation. Открытые product decisions
   `IA-OD-01…IA-OD-06` приняты 2026-08-22; evidence-dependent policy
   instances остались fail-closed.
8. **Technical Architecture v0.3** — проектная редакция подготовлена:
   [`TECHNICAL_ARCHITECTURE_v0.3.md`](TECHNICAL_ARCHITECTURE_v0.3.md)
   (`Accepted architecture baseline`). Она выбрала `IA-TD-01` и варианты
   `TA-TD-01…TA-TD-22`, определила компоненты и stores на MBP/VPS/S3,
   mTLS/identity/encryption, inbox/outbox, acknowledgement/reconciliation,
   S3 admission, external-egress, backup/restore/fencing, degraded semantics
   и 22 architecture acceptance tests. Она не создаёт ORM/DDL/deployment.
9. **Implementation Plan v0.1** — принят 2026-08-22: gates G-00…G-10,
   work packages всего комплекса, dependency graph, critical path, mode и
   deliverable slices, migration/readiness/risk model.
10. **Logical Data Model v0.1** — принят 2026-08-22 и закрывает G-01 без
    ORM/DDL/migrations; scope, identity, canonical/derived, lifecycle,
    Candidate/Fact, geometry, deliverables и ID Generation entities
    формализованы.
11. **Deployment and Policy Profiles v0.1** — принят 2026-08-22 и закрывает
    архитектурный G-02 как полный fail-closed profile contract. Concrete
    production instances остаются `BLOCKED`.
12. **Contract Pack v0.1** — принят 2026-08-22 и закрывает G-03: stable
    registry, Draft 2020-12 schemas, valid/hostile fixtures, compatibility,
    scope/provenance/authority/error contracts. Его offline runtime adapter
    реализован и проверен в G-04 без изменения принятых schemas.
13. **G-04 Persistence Foundation v0.1** — принят 2026-08-23: Python 3.12
    scaffold, Contract Pack runtime, PostgreSQL schemas/Alembic, composite
    scope/RLS, Unit of Work, audit, object и messaging ledgers проверены на
    real PostgreSQL локально и в CI; production deployment не создавался.
14. **G-05 Platform Knowledge Foundation v0.1** — принят 2026-08-23: отдельные
    platform/workspace source ledgers, NTD canon,
    rebuildable FTS/pgvector/typed graph, six-tool Knowledge Gateway,
    RuleVersion/RuleSet runtime и Promotion Gate прошли local PostgreSQL 17.10
    qualification и canonical PostgreSQL 18.6 + pgvector 0.8.6 CI.
15. **G-06 Workspace Lifecycle Foundation v0.1** — accepted implementation baseline
    2026-08-23: единый lifecycle четырёх режимов, portable archive/import,
    adapter-bound reset/destroy, recovery/quarantine и content-free
    DestructionAttestation прошли local PostgreSQL 17.10 и canonical
    PostgreSQL 18.6 + pgvector 0.8.6 CI.
16. **G-07 AI/VLM Harness v0.1** — G-07A accepted implementation foundation
    2026-08-23: native-first, provider-neutral local/synthetic execution,
    Candidate-only lifecycle, validators/repair, qualification,
    batch/reconciliation and workspace retention integration. G-07B,
    production qualification/egress и реальный external provider остаются
    `BLOCKED`.
17. **WP-11 Common Domain Process Kernel v0.1** — accepted implementation foundation
    2026-08-23: Candidate→Fact authority, common construction/work/MTR/control/
    evidence/ID/volume/KS/payment state, four-mode reuse and scoped reset pass
    locally and in canonical PostgreSQL 18 CI.

## 12. Принятые решения и evidence-dependent policy gates

| Решение | Почему нельзя угадать |
|---|---|
| IA-OD-01…IA-OD-06 | `Accepted` 2026-08-22 в Information Architecture по делегированным полномочиям; tenancy/workspace/archive/overlay/field trust/signature variants закрыты. |
| Конкретные версии `RetentionProfile` и Basis Registry | Архитектурные варианты RD-01…RD-05 приняты 2026-08-21; календарные сроки и basis codes утверждаются как policy data с provenance и периодом действия, не как defaults доменной модели. |
| Модель доверия к полевым фактам и электронным подписям | Имеет юридические и операционные последствия. |
| Точные внешние integration policy instances | Архитектура принята HV-01/B, HV-04/B, HV-07/B; конкретные classifications, `WorkspaceEgressPolicy`, provider terms/allowlists и fallback matrix остаются утверждаемыми policy data. Без exact values egress запрещён. |
| Numerical Harness policy instances | HV-02/B, HV-03/B, HV-05/B, HV-06/B, HV-08/B приняты; benchmark-derived budgets/floors, ConfirmationPolicy, raw-storage classes и cost envelopes ещё должны быть утверждены. До этого production profile fail-closed. |
| Deployment/policy values для выбранных механизмов MBP/VPS/S3 | `TECHNICAL_ARCHITECTURE_v0.3.md` выбрала `IA-TD-01` и варианты `TA-TD-01…TA-TD-22`, но не вправе выдумать external provider/region/residency, KMS product, numerical RPO/RTO и owner-controlled policy instances. Без применимого утверждённого profile зависимая capability закрыта. |

`DR-01/B…DR-04/B` больше не входят в перечень открытых owner decisions: они
приняты Олегом Щербаковым 2026-08-21 и нормативно записаны в
`DETERMINISTIC_RULES_CATALOGUE_v0.1.md` §23. Конкретные organization grants,
approved ConflictPolicy instances и RuleSet upgrade requests являются
версионированными policy/operational data в рамках принятых решений, а не
новыми скрытыми продуктовыми defaults.

`HV-01/B…HV-08/B` также больше не являются открытыми owner decisions:
они приняты Олегом Щербаковым 2026-08-21 и записаны в Harness §28. Exact
classification/purpose/provider policies, numerical budgets/floors,
ConfirmationPolicy, fallback matrix и cost envelopes требуют последующего
authority approval как versioned policy instances; это не новые варианты HV.

## 13. Критерий следующего этапа

Следующий этап считается завершённым не после нового прогона документов, а после согласования **Domain Model v0.1** и **Lifecycle & Retention Specification v0.1**. Они дадут недостающую несущую конструкцию: что существует в комплексе, кому принадлежит, как меняется, что доказывает результат и что происходит с данными после завершения ОКС.

Domain Model v0.1 и Lifecycle & Retention Specification v0.1 подготовлены.
Владелец продукта Олег Щербаков 2026-08-21 принял `RD-01…RD-05`; Domain Model,
Knowledge & Memory Architecture, ADR-0005, Lifecycle Specification и настоящий
Blueprint синхронизированы. Проверка не выявила оставшихся нормативных
противоречий по retention, hard isolation, archive/backup и Promotion Gate.

Критерий §13 **закрыт 2026-08-21** на основании этого явного решения владельца
и междокументной проверки. Архитектурных retention-блокировок перед
`Process/Event Specification v0.1` не было; на следующем архитектурном этапе
его проектная редакция подготовлена без изменения принятого retention-gate.

Закрытие §13 не является разрешением реализации персистентности. До завершения
последующих артефактов §11, трассировки acceptance tests в Implementation Plan
и отдельного начала реализации запрещено писать ORM-модели, создавать
миграции, реализовывать PostgreSQL/RLS или content-addressed storage,
archive/reset/purge и расширять прикладной код под персистентность.

## 14. Architecture Baseline и implementation gate

На 2026-08-22 Blueprint, Domain/Knowledge, Knowledge/Memory,
Lifecycle/Retention, Process/Event, Authorization/Audit, Rules Catalogue,
VLM Harness, Information Architecture, Technical Architecture v0.3 и ID
Generation/Template Platform baseline приняты как согласованный
**G-00 Architecture Baseline**. ADR-0001…ADR-0010
проверены: ADR-0002 остаётся `Superseded`, остальные действующие ADR —
`Accepted`; ADR-0008 существует и согласован с MBP-primary topology,
ADR-0009 — с постоянной НТД, ADR-0010 — с общей ID capability.

`IA-OD-01…IA-OD-06`, `IA-TD-01` и `TA-TD-01…TA-TD-22` приняты и имеют
validation records в `IMPLEMENTATION_PLAN_v0.1.md`. Это сохраняет одно
логическое ядро, обязательность четырёх режимов, три продуктовых результата,
platform/workspace isolation, evidence/provenance и Candidate-only boundary
AI/VLM. ТМ-35 остаётся только test stratum.

G-00 не означает готовность инфраструктуры или продукта и не разрешает
прикладную реализацию. G-01 закрыт принятой
`LOGICAL_DATA_MODEL_v0.1.md`. G-02 закрыт принятой
`DEPLOYMENT_AND_POLICY_PROFILES_v0.1.md` как полный fail-closed profile
contract; конкретная production local-first hybrid instance, external egress,
recovery/failover и professional/renderer/provider policy instances остаются
`BLOCKED` до evidence и applicable authority. G-03 закрыт принятым
machine-readable Contract Pack.

Новые ORM/DDL/migrations и persistence modules вне явно разрешённого gate
запрещены. Deployment и external egress отдельно запрещены до
active production policy instances. G-04 Persistence Foundation закрыт
2026-08-23 на PostgreSQL/Contract Pack evidence. G‑05 закрыт 2026-08-23 по
локальному и canonical CI evidence. G‑06 закрыт 2026-08-23 по local и
canonical CI evidence. G‑07A закрыт 2026-08-23 как synthetic/local foundation;
G‑07B и production policy instances остаются `BLOCKED`. WP-11 принят;
WP-12 не начинается автоматически.
