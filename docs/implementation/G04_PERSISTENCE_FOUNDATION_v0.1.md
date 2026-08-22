# G‑04 Persistence Foundation v0.1

- **Статус:** `Accepted implementation baseline — G-04 PASS`
- **Дата:** 2026-08-23
- **Владелец:** Олег Щербаков
- **Ветка:** `implementation/g04-persistence-foundation-v0.1`
- **Нормативная база:** G‑01…G‑03 `PASS`; явные implementation authority
  владельца от 2026-08-23
- **Production readiness:** не утверждается; `G‑02B` остаётся `BLOCKED`

## 1. Gate contract

Точные критерии WP‑04 из `IMPLEMENTATION_PLAN_v0.1.md`:

| Поле | Принятый критерий | Реализация v0.1 |
|---|---|---|
| Capability | canonical PostgreSQL transaction boundary, RLS, repositories, audit, object ledger, inbox/outbox; M4/R123 | Реализовано в `src/asd_kontur/persistence/` |
| DoR | G‑01…G‑03 `PASS` и explicit implementation authority | Выполнено |
| Tests | migration up/down-forward, composite-scope FK, RLS negative matrix, append-only audit, idempotency/reconciliation | `PASS`: disposable PostgreSQL 17 локально и PostgreSQL 18 в GitHub Actions |
| DoD | G‑04 suite passes; canonical state отсутствует на VPS/S3; source/object admission atomic by contract | `PASS`: suite green, deployment отсутствует, admission реализован одной Unit of Work |
| Rollback | forward migration или verified backup; destructive reset запрещён | Production downgrade fail-closed; downgrade только для disposable test DB |
| Memory | отдельные platform/workspace schemas, content-minimal audit, residues inventoried | Реализовано для минимального G‑04 scope; distributed residues остаются G‑06 |

G‑04 создаёт только общий persistence foundation. Он не реализует Tender,
Support, Audit, Restoration, НТД ingestion, VLM, ID Generation, lifecycle
destruction, UI либо production deployment.

## 2. Stack decisions

| Область | Решение | Основание |
|---|---|---|
| Runtime | CPython 3.12, `uv`, locked dependencies | соответствует TA‑TD‑01; воспроизводимость без глобального mutable environment |
| SQL boundary | SQLAlchemy 2 Core + явные repositories/Unit of Work | типизированные узкие операции; физическая модель не скрывается generic repository |
| Driver | psycopg 3, synchronous transaction boundary | минимальный стек для canonical writes; async не нужен до появления измеренного concurrency requirement |
| Migration | Alembic, deterministic PostgreSQL-specific revision | миграция не импортирует application runtime и не читает сеть/policy |
| Contract runtime | `jsonschema` Draft 2020‑12 + `referencing` | стандартная проверка принятого Contract Pack и offline-only registry |
| Canonical JSON | `rfc8785` + SHA‑256 | exact JCS bytes; digest отделён от identity и capability |
| Quality | pytest, Ruff, mypy strict | локальный и CI evidence для первого нового ядра |
| PostgreSQL | local 17 для evidence, CI service 18 | реальные RLS/constraints локально; CI соответствует целевой major из TA v0.3 |

SQLite, broker, event store, Docker-based production topology и legacy ORM не
используются. GitHub Actions PostgreSQL — только disposable CI test service,
не deployment profile.

## 3. Package structure

```text
pyproject.toml
uv.lock
migrations/
  env.py
  versions/0001_g04_persistence_foundation.py
src/asd_kontur/
  contracts/       # accepted Contract Pack runtime adapter
  domain/          # UUIDv7 and registered UUIDv5 identity primitives
  persistence/     # tables, contexts, repositories, UoW, admission service
  settings/        # explicit PostgreSQL settings value object
tests/
  unit/            # identifiers, registry, schemas, semantic invariants
  integration/     # disposable real-PostgreSQL behavior
```

Здесь нет пустых mode packages, API server, ORM entity graph, deployment или
полной реализации LDM.

## 4. Physical schema slice

### 4.1. Schemas and system-of-record class

| Schema/relation | Scope | Class | Identity / key | Deletion and retention |
|---|---|---|---|---|
| `platform.contract_schema_versions` | platform | canonical registry metadata | (`schema_id`, `schema_version`), unique fingerprint | immutable release metadata; no workspace reset |
| `organization.organizations` | organization | canonical current aggregate | `organization_id`; external ID alternate | `RESTRICT`; organization retention |
| `organization.construction_objects` | organization/ОКС | canonical current aggregate | (`organization_id`, `construction_object_id`) | `RESTRICT`; organization/ОКС retention |
| `workspace.workspaces` | workspace | canonical current aggregate | (`organization_id`, `workspace_id`) | `RESTRICT`; lifecycle-driven only |
| `workspace.workspace_revisions` | workspace | immutable lifecycle history | scope + `revision`; alternate `workspace_version_id` | no destructive cascade |
| `workspace.mode_executions` | workspace | canonical current aggregate | scope + `mode_execution_id` | lifecycle-driven; four enum modes share one table |
| `workspace.objects` | workspace | canonical object ledger metadata | scope + `object_id`; version alternate | digest is attribute; no access by digest |
| `workspace.object_links` | workspace | canonical typed association | scope + `link_id`; same-scope composite FKs | source/target `RESTRICT` |
| `audit.workspace_records` | workspace | append-only, content-minimal | scope + `audit_record_id` | application UPDATE/DELETE/TRUNCATE denied |
| `messaging.workspace_outbox` | workspace | operational transactional ledger | scope + `outbox_record_id`; event alternate | retry metadata; not canonical domain state |
| `messaging.workspace_inbox_receipts` | workspace | operational dedup ledger | scope + consumer + message | scoped idempotent receipt |
| `messaging.workspace_idempotency` | workspace | operational command ledger | scope + handler + idempotency key | semantic digest conflict is explicit |

`organization_id` и `workspace_id` не nullable в workspace relations. Platform
и workspace data не разделяют nullable `scope_id`. Все persisted contract,
schema, policy и RuleSet references используют exact versions; `latest`
отклоняется constraints и runtime validation.

### 4.2. Constraints

- UUID instance identities создаются RFC 9562 UUIDv7; deterministic semantic
  identity использует зарегистрированный UUIDv5 namespace и NFC/trim v1.
- `ConstructionObject` имеет composite FK к своей organization.
- `Workspace` имеет composite FK
  (`organization_id`, `construction_object_id`).
- Все workspace descendants имеют composite FK
  (`organization_id`, `workspace_id`).
- `object_links` включает scope во внешние ключи источника и цели: digest либо
  совпадающий UUID другого workspace не может пройти integrity check.
- revision положительна; ModeExecution update использует
  (`mode_execution_id`, expected revision) и выдаёт typed concurrency error.
- contract/schema/policy/rules references запрещают mutable `latest`.
- SHA‑256 хранится как `sha256:<64 lowercase hex>` и не заменяет stable ID,
  locator либо capability.
- canonical relations не имеют опасных cascade; reset/whole-schema delete не
  реализован.

## 5. RLS and roles

Migration создаёт capability role `asd_app` как `NOLOGIN`, без superuser,
createdb и createrole. Конкретная environment identity должна получать её
через управляемый grant; credentials в repository отсутствуют.

На organization, workspace, audit и messaging relations включены одновременно
`ENABLE ROW LEVEL SECURITY` и `FORCE ROW LEVEL SECURITY`. Policies сравнивают
scope columns с transaction-local:

```text
current_setting('asd.organization_id', true)
current_setting('asd.workspace_id', true)
```

Отсутствующее либо пустое значение не совпадает ни с одной строкой и даёт
default-deny. Integration tests работают отдельной login role, наследующей
`asd_app`; эта role не owner и не superuser. Owner-role test не считается
evidence isolation.

## 6. Transaction and Unit of Work

`OrganizationUnitOfWork` и `WorkspaceUnitOfWork`:

1. открывают новую explicit transaction;
2. устанавливают organization/workspace через PostgreSQL `set_config(...,
   true)`, то есть `SET LOCAL` semantics;
3. создают только repositories допустимого scope;
4. commit выполняют только при чистом выходе;
5. rollback выполняют при любой ошибке;
6. закрывают session и очищают repository handles;
7. pool reset дополнительно выполняет rollback.

`WorkspaceContext` обязателен и переносит actor/service identity,
correlation и causation. Нельзя открыть workspace Unit of Work без явных
organization/workspace identifiers и хотя бы одной actor/service identity.
Application role вне UoW не видит строки из-за RLS.

Нет generic repository, принимающего имя таблицы или arbitrary SQL/payload.
Object admission — узкий transactional service: idempotency claim, object
ledger write, exact-version outbox record и completed outcome фиксируются в
одной transaction. Retry с тем же scoped idempotency key/digest возвращает
первичный result и не создаёт второй canonical object.

## 7. Audit and messaging

Audit хранит только identity/scope, capability, operation, outcome, exact
contract/policy versions, correlation/causation, safe message key,
diagnostic reference, retention class и digest. Full project payload,
prompt/response, credentials и reconstructive content колонок не имеют.

Append-only обеспечивается одновременно grants и BEFORE UPDATE/DELETE
triggers. Application role может `SELECT`/`INSERT`, но не `UPDATE`, `DELETE`
или `TRUNCATE`.

Outbox создаётся в canonical transaction. Inbox использует composite scoped
dedup key. Idempotency конфликтует при повторном key с другим semantic digest.
Delivery remains at-least-once with reconciliation; broker и VPS coordinator
не реализованы, exactly-once не обещается.

## 8. Contract Pack runtime

Runtime загружает только exact `contracts/v0.1/registry.json`, проверяет
registry version, 13 unique `$id`, Draft 2020‑12 dialect и SHA‑256 fingerprint
каждого schema file. `$ref` разрешается только из локального URN store;
network/foreign URI и unresolved pointer fail closed.

Validator выбирает зарегистрированные contract key/family/schema/version,
запрещает `latest`, не выполняет coercion и возвращает typed issues. Schema
validation и восемь cross-record semantic validators имеют отдельный
`validation_layer`. RFC 8785 canonicalization исключает только собственное
поле `digest` и вычисляет `sha256:` над exact canonical bytes.

## 9. Migration and rollback

Initial revision `0001_g04` создаёт schemas, relations, constraints, grants,
RLS policies, audit triggers и exact Contract Pack registry metadata. Она:

- принимает URL только через explicit Alembic `-x database_url=...`;
- принимает только PostgreSQL URL;
- не импортирует application tables/settings;
- не обращается к сети или внешней policy;
- выполняется transactional DDL;
- повторно проверяется schema inspection tests.

Production evolution — forward-only либо восстановление verified backup.
Downgrade отказывается выполняться без
`ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1`; этот flag допустим только для disposable
development/test DB. Whole-schema reset не является lifecycle implementation.

## 10. Verification evidence

| Evidence | Состояние на ветке |
|---|---|
| Lock consistency | `PASS` |
| Ruff format/lint | локально `PASS` |
| mypy strict | локально и CI `PASS`, 17 source files |
| Contract Registry | `PASS`: 13 unique schemas, fingerprints, offline refs |
| Contract fixtures | `PASS`: 17 valid, 2 schema-invalid, 8 semantic-invalid |
| Identity/JCS | `PASS`: RFC 9562 vector, UUIDv5 vector, RFC 8785/SHA‑256 |
| PostgreSQL migrations | `PASS` на disposable PostgreSQL 17.10 |
| PostgreSQL behavior | `PASS`: 8 grouped integration tests, покрывающих 15 DB scenarios; fixture isolation и secret/project-data scan проверяются unit tests |
| Application role | подтверждена non-owner/non-superuser role с enforced RLS |
| Downgrade/upgrade | `PASS` только в отдельной disposable DB |
| CI PostgreSQL 18 | `PASS`, GitHub Actions run `32573117497` и duplicate PR run `32573120306` |

Integration cases проверяют поведение, а не поиск SQL-текста: clean upgrade,
schema/RLS inspection, organization A/B, workspace A/B, отсутствующий scope,
pool reuse, cross-workspace FK, optimistic concurrency, idempotent retry,
audit UPDATE/DELETE, atomic object/outbox, rollback и disposable round trip.

## 11. Implementation-state matrix

| Item | Implemented | Unit/contract | PostgreSQL | CI | State |
|---|---:|---:|---:|---:|---|
| Contract runtime | yes | yes | n/a | yes | verified |
| UUID identities | yes | yes | n/a | yes | verified |
| Physical schema/migration | yes | inspection | yes | yes | verified |
| Composite scope/RLS | yes | n/a | yes | yes | verified |
| Unit of Work/repos | yes | typed checks | yes | yes | verified |
| Audit append-only | yes | n/a | yes | yes | verified |
| Object ledger/admission | yes | n/a | yes | yes | verified |
| Inbox/outbox/idempotency | yes | n/a | yes | yes | verified |
| VPS/S3 deployment | no | n/a | n/a | n/a | intentionally out of scope |
| Lifecycle destruction | no | n/a | n/a | n/a | future G‑06 |
| Business workflows | no | n/a | n/a | n/a | future gates |

## 12. Legacy selective port

Selective port не выполнялся. UUID algorithms, tables, ORM, SQLite patterns,
AuditLog и reset из archive prototype не копировались. Реализация создана из
accepted LDM/Contract Pack; legacy остаётся migration evidence только через
существующие normative maps и archive history.

## 13. Risks and extension boundaries

- Initial slice не содержит SourceArtifact/Evidence/Candidate/Fact/Rule/NTD;
  они добавляются отдельными forward migrations после соответствующего gate.
- RLS не заменяет authorization decision: capability/policy enforcement
  появится поверх DB scope, сохраняя default-deny.
- PostgreSQL owner/superuser bypass учитывается operational role design;
  application connections не должны использовать owner credentials.
- Distributed object/WAL/backup residues, archive/reset/destruction и legal
  hold остаются G‑06; текущие retention classes — references, не periods.
- Численные pool/resource/retention/provider values не объявлены production
  policy; `G‑02B` остаётся blocked.
- Schema v0.1 является минимальным slice, не разрешением реализовать весь LDM
  одним migration.

Все четыре режима используют одни `Workspace`, `ModeExecution`, UoW,
contract registry и persistence boundaries. Три постоянных результата и ID
Generation будут ссылаться на тот же scope/object/evidence foundation; G‑04
не создаёт mode-specific store и не заявляет готовность deliverables.
