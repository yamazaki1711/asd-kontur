# G‑05 Platform Knowledge Foundation v0.1

- **Статус:** `Accepted implementation baseline — G‑05 PASS`
- **Gate:** `G‑05 Platform Knowledge Foundation`
- **Work packages:** `WP‑05`, `WP‑06`, `WP‑07`
- **Владелец:** Олег Щербаков
- **Дата:** 2026‑08‑23
- **Исходный baseline:** `bbd24bc06583bd7fe1e5c0408ed0fea8790dadd2`
- **Ветка:** `implementation/g05-platform-knowledge-foundation-v0.1`

## 1. Назначение и границы

G‑05 создаёт постоянную platform memory для официальных источников, редакций
НТД, канонических утверждений и детерминированных правил. Foundation общий для
Tender, Support, Audit и Restoration и не реализует процессы режимов либо
конечные результаты R‑1/R‑2/R‑3.

В G‑05 не загружались реальные НТД, не формулировалось содержание СП, не
обрабатывались документы ОКС, не запускались модели, VPS/S3/API и production
deployment. Все fixtures синтетические и объектно-независимые.

## 2. Реализованный stack

G‑05 продолжает G‑04 без смены persistence stack:

- Python 3.12, `uv` и lockfile;
- SQLAlchemy 2 Core/узкие application services, Alembic и psycopg 3;
- PostgreSQL; локальная qualification — PostgreSQL 17.10;
- pgvector 0.8.6; CI-профиль — PostgreSQL 18 + pgvector 0.8.6;
- PostgreSQL FTS с конфигурацией `russian`;
- pytest, Ruff и strict mypy.

Новая runtime dependency `pgvector` используется только как PostgreSQL type
adapter. Embedding-модель не вызывается; тестовые vectors детерминированы.

## 3. Physical model

Forward migration `0002_g05_platform_knowledge.py` следует после неизменённой
`0001_g04` и создаёт три физически разные области.

| Schema | System of record / роль | Основные relations |
|---|---|---|
| `platform` | постоянный canonical SoR | official registry, platform source ledger, NTD, assertions, rules/rule sets, Evidence Capsules |
| `workspace` | память одного ОКС под composite scope и FORCE RLS | project sources/evidence, workspace rules/evaluations/traces, promotion candidates |
| `projection` | полностью rebuildable derived plane | lexical, vector и typed graph versions/entries |
| `audit` | append-only content-minimal evidence | `platform_records` отдельно от G‑04 workspace audit |

Platform и workspace records не используют общий nullable `scope_id`.
Workspace relations содержат обязательные `organization_id, workspace_id`,
composite FK и `ENABLE/FORCE ROW LEVEL SECURITY`. App role получает только
workspace DML и platform/projection read. Curator и projection builder —
отдельные NOLOGIN capability roles; integration tests используют отдельные
non-owner, non-superuser login roles.

## 4. WP‑05 — Source and Evidence Ledger

### 4.1. Platform ledger

Реализованы:

- `OfficialSourceRegistryEntry` с stable family key, официальным URL, issuer,
  jurisdiction, metadata digest и observation revision;
- `SourceArtifact` как смысловая identity источника;
- `Object` и `ObjectReceipt` как отдельные identity bytes и adapter evidence;
- `AcquisitionAttempt` со стадиями `started → bytes_written → accepted` либо
  `failed/reconciliation_required`;
- immutable `SourceVersion`, typed `SourceLocator` и `EvidenceLink`.

`PlatformSourceLedger` сначала фиксирует attempt, затем требует verified object
receipt и только после этого создаёт accepted `SourceVersion`. Upload без
domain acceptance остаётся failed/reconciliation evidence. Retry с теми же
bytes идемпотентен внутри SourceArtifact. Path/URL и digest не являются
identity или access capability.

Provider-neutral `ObjectStorePort` не содержит S3 semantics. Его
`InMemoryObjectStore` доказывает unavailable, write failure, idempotency,
immutable conflict и residue handling без сетевого соединения.

### 4.2. Workspace ledger

Project source kinds физически ограничены `pd`, `rd`, `contract`,
`customer_regulation`, `project_evidence`, `field_document`. Они не могут быть
записаны в platform source kind. Workspace object receipt/source/version/
locator/evidence FK включают exact composite scope; physical cross-workspace
deduplication не вводилась.

Регламент Заказчика остаётся `workspace.source_artifacts.source_kind =
customer_regulation`. Application role имеет только `SELECT` к НТД и не может
изменять platform relations.

## 5. WP‑06 — NTD canon и projections

Каноническая цепочка реализована relations:

`OfficialSourceRegistryEntry → SourceArtifact → SourceVersion →
NormativeDocument → NormativeEdition → StructuralUnit → KnowledgeAssertion →
AssertionEvidence`.

Модель включает:

- stable `NormativeDocument` и immutable `NormativeEdition`;
- append-only edition state history, effective interval и
  supersedes/replaces/amends lineage;
- edition-bound `StructuralUnit` с exact structural path и SourceLocator;
- `Definition`, `Requirement`, `Exception`, `CrossReference`;
- versioned `ApplicabilityContext`, `NormativeConflict`, `KnowledgeGap`;
- published assertion только с exact structural unit либо разрешённой
  Evidence Capsule и с deferred evidence constraint.

`NormativeKnowledgeRepository.resolve_edition()` возвращает ровно одну active
edition для даты. Ноль или несколько кандидатов дают typed
`knowledge.edition_ambiguous`; отсутствие данных не превращается в успешный
отрицательный нормативный вывод. Cancelled edition не удаляется.

### 5.1. Rebuildable projection plane

Каждая projection version pins canonical snapshot digest и exact profile:

- `LexicalIndexVersion` + PostgreSQL FTS entries;
- `EmbeddingIndexVersion` + pgvector entries с model revision, dimension,
  dtype, metric, chunker/instruction и index profile;
- `GraphProjectionVersion` + typed relational edges.

Qualification vector profile имеет dimension 3 и HNSW cosine index только для
синтетических vectors. Variable future dimensions остаются explicit profile
data. Отсутствие extension приводит к migration failure; silent fallback нет.

`ProjectionBuilder` читает exact canonical StructuralUnit, строит versions,
выполняет FTS/vector/typed traversal и физически удаляет projections. Тест
delete/rebuild подтверждает одинаковый entry digest для одного canonical
snapshot и сохранность canonical rows. `empty/stale/failed/building/deleted`
не интерпретируются как «нормы нет».

## 6. Knowledge Tool Gateway

Внутренний transport-neutral interface реализует ровно шесть allowlisted tools:

1. `knowledge.search`;
2. `knowledge.get_source_fragment`;
3. `knowledge.get_applicable_rules`;
4. `knowledge.trace_assertion`;
5. `knowledge.explain_conflict`;
6. `knowledge.get_required_documents`.

Gateway принимает exact Contract Pack `0.1.0`, exact capability и согласованный
organization/workspace context. Он не принимает SQL, имя table/repository или
произвольный object key. Ответ содержит typed `EvidencePack`: SourceVersion,
edition, structural path, content digest, access reference, applicability,
conflicts, gaps и uncertainties.

Различаются `ok`, `no_result`, `index_unavailable`, `knowledge_incomplete` и
`edition_ambiguous`. Required-document runtime относится к WP‑09, поэтому без
активного pinned правила tool возвращает `knowledge_incomplete`, а не пустой
успех. Каждый вызов пишет content-minimal platform audit без query text,
source fragment или результата.

## 7. WP‑07 — Rule Registry и runtime

PostgreSQL registry содержит:

- `Rule`, immutable `RuleVersion`, `RuleEvidence`;
- append-only `RuleVersionState`, review и approval records;
- subject-specific immutable `ConflictPolicyVersion`;
- immutable `RuleSetVersion` и exact memberships/fingerprints;
- workspace-specific RuleVersion family под composite RLS scope;
- immutable workspace `RuleEvaluation` и `RuleTrace`;
- `ControlledRuleSetUpgrade` с source/target pins и impact digest.

`RuleRegistryService` регистрирует immutable definition, требует RuleEvidence,
проводит lifecycle
`drafted → evidence_attached → candidate → reviewed → approved → active` и
публикует RuleSet только из active members. Author, independent reviewer и
qualified approver различаются. Model/service identity не может review,
approve или activate.

`DeclarativeRuleRuntime` использует минимальный versioned predicate language
(`eq`, `in`, `exists`) и three-valued applicability:
`applicable/not_applicable/indeterminate`. Неизвестное поле или формальный
конфликт никогда не дают permissive result. Exact inputs, RuleVersion,
RuleSetVersion и policy versions входят в deterministic SHA‑256 fingerprint.
Rolling `latest` запрещён.

## 8. Promotion Gate

Реализован fail-closed state machine:

`observed → candidate → anonymized → evidence_verified →
applicability_defined → regression_tested → approved/rejected → published`.

Только human identity с `promotion.approve` может approve/publish. Confidence
не входит в Evidence Capsule. Capsule reject-ит filename, workspace reference
и reconstructive content. Published `platform.evidence_capsules` и
`platform.promotion_publications` физически не содержат organization/workspace
columns и не имеют FK в workspace. До publication material остаётся в
workspace RLS scope.

G‑05 не выполняет reset/destroy: это G‑06. Отсутствие обратного live-link
позволяет G‑06 уничтожить project material, сохранив разрешённую RD‑05/B
platform identity.

## 9. Transaction, authority и immutability

- все application writes заключены в explicit SQLAlchemy transaction;
- нет generic repository с caller-provided SQL/table name;
- immutable platform/workspace version/result rows защищены DB triggers;
- source attempt — единственная mutable orchestration record до terminal state;
- app, curator и projection builder capabilities физически разделены;
- audit UPDATE/DELETE запрещены trigger и отсутствием grant;
- projections могут CASCADE-delete свои entries, но не canonical knowledge;
- workspace source/rule/promotion relations остаются под G‑04 transaction-local
  scope guard и pool-leak tests.

## 10. Migration и rollback

`0002_g05`:

- выполняется после `0001_g04` и не изменяет её;
- создаёт extension `vector`, schema `projection`, roles, tables, constraints,
  triggers, grants и RLS без network/policy reads;
- проходит clean `base → head` и `0001_g04 → head`;
- disposable downgrade разрешён только с
  `ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1`;
- production rollback остаётся forward repair либо verified restore;
- downgrade сохраняет cluster roles и extension, удаляя только G‑05 schema
  objects, затем повторный upgrade восстанавливает foundation.

## 11. Legacy decisions

Read-only изучены ранее инвентаризированные `mac_asd` компоненты.

| Legacy idea | Решение G‑05 | Основание |
|---|---|---|
| exact clause/FTS retrieval | `preserve + modernize` | добавлены edition, locator, evidence, gap semantics |
| vector retrieval | `modernize` | versioned rebuildable pgvector profile, не SoR |
| Evidence/Construction graph vocabulary | `preserve vocabulary` | typed relational projection, не GML/NetworkX authority |
| Knowledge MCP tool facade | `modernize` | internal capability/scope Gateway; transport отложен |
| temporal NTD registry | `modernize` | immutable editions/state/effective intervals/provenance |
| Lessons/DomainTrap | `quarantine` | только Promotion Gate; нет automatic Lesson→Rule |
| silent GraphRAG/Neo4j empty fallback | `reject` | typed index unavailable/gap |
| dummy pgvector fallback | `reject` | extension/backend failure fail-closed |
| legacy ORM/SQLite/event store | `reject` | не переносились |

Ни один legacy-файл или алгоритм не копировался. Заимствованы только проверенные
понятия через новую модель, authority gates и тесты.

## 12. Verification evidence

Локально на одноразовом PostgreSQL 17.10 + pgvector 0.8.6:

- `uv lock --check` — PASS;
- Ruff format/lint — PASS;
- strict mypy — PASS (`26 source files`);
- pytest — PASS (`49 passed`), из них `33` unit/contract и `16` real PostgreSQL;
- clean migration, G‑04→G‑05 и disposable downgrade/upgrade — PASS;
- non-owner/non-superuser RLS, pool isolation и append-only audit — PASS;
- FTS/vector/typed graph build/search/delete/rebuild — PASS;
- Contract Pack v0.1 regression fixtures — PASS.

Canonical GitHub Actions runs `32578088790` и `32578100005` — PASS. Run
`32578100005` использовал PostgreSQL 18.6 + pgvector 0.8.6 и выполнил те же
`49 passed` без skips.

## 13. Gate self-check

| Sub-gate | Состояние | Evidence |
|---|---|---|
| WP‑05 Source/Evidence Ledger | `PASS` | admission/idempotency/conflict/unavailable/residue/RLS tests |
| WP‑06 NTD canon/projections/Gateway | `PASS` | edition/evidence/gap + real FTS/pgvector/graph + six-tool tests |
| WP‑07 Rule Registry/runtime | `PASS` | lifecycle/authority/three-valued/pin/fingerprint/rule-set tests |
| Promotion Gate | `PASS` | positive/reject/authority/capsule/no-live-FK tests |
| PostgreSQL 18 CI qualification | `PASS` | PostgreSQL 18.6 + pgvector 0.8.6, 49 tests, no skips |
| G‑05 overall | `PASS 2026-08-23` | all three work packages and cross-cutting acceptance evidence complete |

## 14. Намеренно не реализовано

- реальные НТД и нормативные rules;
- production policy/qualification values;
- external object store, VPS, egress или model adapters;
- embeddings/reranking model execution;
- mode workflows и deliverable generation;
- full required-document domain catalogue (WP‑09);
- lifecycle reset/destroy (G‑06);
- HTTP/MCP/API transport;
- ProductReady или G‑02B readiness.

## 15. Extension points

После принятия G‑05 единственный следующий gate — `G‑06 Workspace Lifecycle
Foundation`. Он использует source contracts, но не меняет platform canon,
должен доказать archive/import/reset/destruction и residue accounting. До
отдельной authority G‑06 не начинается.
