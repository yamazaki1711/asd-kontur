# АСД-КОНТУР — Repository Re-baseline Manifest v0.1

- **Статус:** `Accepted repository transition record`
- **Дата:** 2026-08-22
- **Владелец:** Олег Щербаков
- **Целевая ветка:** `architecture/rebaseline-v0.1`
- **Целевая default branch:** `main`
- **Область:** контролируемая замена активного prototype tree на
  architecture-only canonical baseline
- **Не является:** G-03 Contract Pack, реализацией, migration, deployment,
  production readiness или разрешением публикации данных ОКС

## 1. Исходная точка и сохранение

До re-baseline удалённый GitHub baseline был зафиксирован так:

| Record | Value |
|---|---|
| Repository | `yamazaki1711/asd-kontur` |
| Old default branch | `main` |
| Old remote HEAD | `223047b1a4d7747e36599dfe4ffe2dac2d358ad5` |
| Archive branch | `archive/pre-rebaseline-prototype-2026-08-22` |
| Annotated tag | `pre-rebaseline-prototype-2026-08-22` |
| New branch | `architecture/rebaseline-v0.1` |
| Separate worktree | `/Users/oleg/asd-kontur-rebaseline` |

Archive branch и peeled annotated tag указывают на exact old remote HEAD.
Они сохраняют последний канонический GitHub baseline prototype, а не
локальные незакоммиченные изменения.

Исходный `/Users/oleg/asd-kontur` находился на локальном `main` commit
`c0cbe39a96eaac160c3977b033583c17896ac8a2`, на четыре commit впереди
`origin/main`, и имел многочисленные tracked/untracked WIP changes. Его
working files не использовались как место сборки re-baseline, не очищались,
не добавлялись в index и не публиковались целиком. Контрольный digest
начального `git status --porcelain=v1 -z`:
`0c5d0e2b7d159551510be048b01a77d5918b06e322649e9bce1606c145cdc4e4`.

## 2. Причина re-baseline

Старый GitHub tree показывал Support-oriented prototype: функциональную
модель в DOCX, генератор этого DOCX и ранние документы. После принятия
G-00, G-01 и G-02A такой tree создавал ложное впечатление, что prototype,
один режим или один pilot являются активным продуктовым ядром.

Re-baseline делает каноническими:

- объектно-независимый pipeline для последовательной обработки разных ОКС;
- четыре режима `Tender`, `Support`, `Audit`, `Restoration` на одном ядре;
- три постоянных продуктовых результата;
- разделение `platform memory` и `workspace memory`;
- Candidate-only AI boundary;
- MBP-primary local-first hybrid topology;
- ID Generation & Template Platform как специфицированную, но не
  реализованную capability;
- gates Implementation Plan как единственную границу начала реализации.

## 3. Canonical baseline: включено

### 3.1. Repository governance

- `README.md` — продукт, scopes, четыре режима, три результата, memory/AI/
  topology boundaries и честный gate status;
- `LICENSE` — restrictive all-rights-reserved notice; open-source license
  этим re-baseline не предоставляется;
- `.gitignore` — исключает secrets, runtime data, staging, outputs, models и
  generated corpora.

### 3.2. Product и functional slices

- универсальные `docs/product/PRODUCT_SCOPE.md`, operating, automation и
  deterministic-rules models;
- `docs/mvp/README.md`, Functional Model и acceptance scenarios только как
  явно ограниченные functional slices, подчинённые правилу
  `Tender ∧ Support ∧ Audit ∧ Restoration`;
- исторический Domain Core plan сохранён с явным `Historical / Superseded`
  banner из-за действующих ссылок и provenance ранних решений.

Ни один файл в `docs/mvp/` не является объявлением готового MVP.

### 3.3. Architecture

Активный нормативный корпус:

- `ARCHITECTURE_BLUEPRINT_v0.1.md`;
- `IMPLEMENTATION_PLAN_v0.1.md`;
- `IMPLEMENTATION_BASELINE.md`;
- `INFORMATION_ARCHITECTURE_v0.1.md`;
- `TECHNICAL_ARCHITECTURE_v0.3.md`;
- `DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md`;
- `KNOWLEDGE_AND_MEMORY_ARCHITECTURE_v0.1.md`;
- `LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md`;
- `PROCESS_AND_EVENT_SPECIFICATION_v0.1.md`;
- `AUTHORIZATION_AND_AUDIT_MODEL_v0.1.md`;
- `DETERMINISTIC_RULES_CATALOGUE_v0.1.md`;
- `AI_VLM_EXECUTION_AND_VERIFICATION_HARNESS_SPECIFICATION_v0.1.md`;
- `LOGICAL_DATA_MODEL_v0.1.md`;
- `DEPLOYMENT_AND_POLICY_PROFILES_v0.1.md`;
- `ID_GENERATION_AND_TEMPLATE_PLATFORM_SPECIFICATION_v0.1.md`;
- ADR-0001…ADR-0010.

`TECHNICAL_ARCHITECTURE_v0.1.md`, v0.2 и
`DOMAIN_CORE_SPEC_v0.1.md` сохранены только как явно помеченные historical/
superseded precursors, поскольку действующие документы ссылаются на их
нумерованные разделы. Они не задают topology, readiness или implementation
authority.

### 3.4. NTD и reports

- `docs/NTD/` содержит только правила platform-corpus governance; NTD PDF
  не хранятся в Git;
- `LEGACY_ID_GENERATOR_ASSET_INVENTORY_v0.1.md` сохраняет проверенное
  evidence и migration conclusions без переноса legacy binaries;
- этот manifest является authoritative record самого re-baseline.

## 4. Удалено или не опубликовано в active tree

Из старого remote tree удалены:

- бинарный DOCX функциональной модели Support prototype;
- `tools/build_functional_model.py`.

Из локального dirty tree намеренно не переносились:

- `src/asd_kontur`, весь старый application/runtime prototype;
- `tests`, `tools`, `pyproject.toml`, `uv.lock`, `.python-version`;
- `config/pilots`, `data`, `docs/pilots`, pilot reports и benchmark outputs;
- `docs/devops/CI_CD_AND_OPERATIONS_v0.1.md` и
  `DEPLOYMENT_TOPOLOGY_v0.1.md`, поскольку их VPS-deploy baseline
  superseded MBP-primary Technical Architecture v0.3;
- `TM35_OCR_AND_VLM_EXTRACTION_POLICY_v0.1.md` и
  `TM35_PILOT_DELIVERY_PLAN_v0.1.md`;
- `CODEBASE_REALITY_AUDIT_2026-08-20.md` и старый DevOps audit: они описывают
  retired code/tree, а не новый baseline;
- незавершённые локальные `CONTRACT_PACK_v0.1.md` и `contracts/v0.1/`:
  это непроверенный WIP, он не закрывает G-03 и не публикуется этой задачей;
- DOCX/XLSX/PDF/DXF corpora, generated outputs и документы конкретных ОКС;
- `.env`, credentials, API/SSH/Tailscale secrets и access metadata;
- models, caches, dependencies, `/tmp` и legacy staging/binaries.

Исключённые локальные WIP assets остаются физически в исходном dirty
worktree. Archive branch/tag сохраняют только прежний remote baseline, как и
требовалось; manifest не утверждает обратного.

## 5. Классификация компонентов prototype

| Component | Class | Active-tree decision | Future rule / preservation |
|---|---|---|---|
| `README`, accepted product/architecture/ADR | `retain-active` | Перенесены и синхронизированы | Canonical normative baseline |
| `docs/mvp` Support artifacts | `historical-reference` | Только явно ограниченные Markdown сохранены | Не определяют MVP; доступны для traceability |
| Technical Architecture v0.1/v0.2, Domain Core precursor/plan | `historical-reference` | Сохранены с superseded banners | Только действующие ссылки/decision provenance |
| old DOCX deliverable | `remove-from-active` | Удалён | Old remote history/archive достаточны |
| DOCX build tool | `rejected` | Удалён | Недетерминированный documentation generator не product core |
| `src/asd_kontur/domain` | `future-selective-port` | Не опубликован | Идеи deterministic identifiers и typed domain primitives портируются позднее по новым contracts |
| `src/asd_kontur/ntd` | `future-selective-port` | Не опубликован | Edition/resolution concepts повторно проверяются против LDM/rules |
| `src/asd_kontur/corpus` | `pilot-only` | Не опубликован | Только generic deterministic scan/ranking ideas могут быть переписаны |
| `src/asd_kontur/extraction` | `future-selective-port` | Не опубликован | Adapter boundaries модернизируются; runner formats не становятся authority |
| `src/asd_kontur/bridge` | `pilot-only` / `future-selective-port` | Не опубликован | Provenance/mapping primitives — только после G-03 и без TM-35 paths |
| prototype `tests` | `historical-reference` | Не опубликованы | Сценарии могут стать input будущих contract tests, не переносом suite |
| runtime `tools`, configs, locks | `remove-from-active` | Не опубликованы | Новые toolchain/runtime contracts выбираются после gates |
| pilot configs/data/docs/benchmarks | `pilot-only` | Не опубликованы | Остаются workspace/test evidence, не platform memory |
| old DevOps topology | `rejected` как current authority | Не опубликована | Superseded MBP-primary/VPS-coordination/S3 plane |
| legacy ISGenerator/ISUID/id-track assets | `future-selective-port` | Binaries/templates не опубликованы | Preserve/modernize/reject decisions остаются в inventory и ID specification |
| incomplete local Contract Pack WIP | `remove-from-this-baseline` | Не опубликован | G-03 начинается отдельно с clean review; статус остаётся OPEN |

Полная копия prototype не создаётся в `legacy/`: history, archive refs и
исходный dirty worktree обеспечивают доступ без загрязнения active tree.

## 6. Commit plan и lineage

| Order | Commit | Purpose |
|---|---|---|
| 1 | `4dd9dd4` — `docs: establish ASD-KONTUR architecture baseline` | Canonical README, product/architecture/ADR/NTD/report corpus and governance |
| 2 | `1080a9f` — `chore: retire superseded prototype from active tree` | Remove DOCX/tool and close Git-as-object-store ambiguity for NTD |
| 3 | commit containing this file — `docs: record repository rebaseline` | Preservation, classification, exclusions, gate and verification record |

Все commits имеют старый remote `main` как ancestor. History не
переписывалась; force-push, reset, stash, merge/rebase и destructive changes
исходного worktree не применялись.

## 7. Security, privacy и publication boundary

Active tree содержит только text governance/architecture artifacts. Проверки
не обнаружили:

- binary/model/archive/Office payload;
- `src/`, tests, tools, runtime/deployment folders или dependency locks;
- secret files и token/private-key/password patterns;
- filename, предназначенный одному ОКС или pilot;
- staging, cache, data, output или generated corpus;
- `contracts/`, поскольку G-03 ещё не начат нормативно.

Legacy inventory упоминает hosts, paths и названия ОКС только как
content-minimal audit evidence. Он не содержит скопированных project
documents, secret values, capability URLs или executable legacy artifacts.

## 8. Gate status и связь с Implementation Plan

| Gate | Status after re-baseline | Meaning |
|---|---|---|
| `G-00 Architecture Baseline` | `PASS` | Accepted architecture/ADR are canonical |
| `G-01 Logical Data Model` | `PASS` | LDM accepted; no ORM/DDL created |
| `G-02A Deployment and Policy Profiles` | `PASS` | Fail-closed normative profile complete |
| `G-02B production instance readiness` | `BLOCKED` | Evidence-backed production values/drills absent |
| `G-03 Contract Pack` | `OPEN / NEXT` | No Contract Pack published by re-baseline |
| Implementation authority | `CLOSED` | No application code, ORM, DDL, migrations or deployment |

Re-baseline меняет каноническое содержимое репозитория, но не пропускает gate
и не активирует production policy instance.

## 9. Verification record

До добавления manifest подтверждено:

- old tree: 12 tracked files, 137,034 active-tree bytes;
- new architecture tree: 42 tracked text files, 1,646,609 active-tree bytes;
- рост вызван нормативными Markdown, при этом старый binary удалён;
- `git diff --check origin/main...HEAD` — PASS;
- trailing whitespace во всех Markdown — PASS;
- internal relative Markdown links — PASS;
- secret-pattern scan — PASS;
- prohibited path/extension scan — PASS;
- ОКС/pilot-specific filename scan — PASS;
- tracked file review — PASS.

Manifest проходит те же проверки перед commit и весь branch повторно
проверяется перед push/PR. Architecture-only branch не имеет активного Python
package или test suite; поэтому новый `pytest` не заявляется. Последний
pre-rebaseline prototype baseline — `224 passed, 2 deselected` и остаётся
только историческим evidence.

## 10. Восстановление старого baseline

Read-only inspection или отдельный worktree создаётся от:

- `archive/pre-rebaseline-prototype-2026-08-22`; либо
- `pre-rebaseline-prototype-2026-08-22`.

Возврат старого prototype в default branch не выполняется reset/force-push.
Он требует отдельного owner decision, новой ветки, обычного PR и проверки,
что возвращаемые файлы не нарушают текущие contracts, privacy и gates.

## 11. Дальнейший порядок разработки

Единственный следующий нормативный шаг — `G-03 Contract Pack` по
`IMPLEMENTATION_PLAN_v0.1.md`. Он выполняется отдельной задачей после merge
re-baseline. Только принятый G-03 и отдельная implementation authority могут
открыть следующий implementation gate; production readiness G-02B остаётся
самостоятельно заблокированной.
