# ASD-KONTUR — диагностический handoff по ОЗЕРО

**Снимок:** 2026-09-10 16:06–16:09 `UTC+12`  
**Режим:** read-only; код, БД, статусы задач, source objects, historical turns и службы не изменялись.  
**Запрошенный workspace:** `01a088aa-0491-7bdd-9127-8359fe927a27` (ОЗЕРО).  
**Исторический failed turn:** `01a088c6-a7a0-7fb4-8a64-732bac76b362`.  
**Итог инцидента:** **не исправлен**. Это диагностическая передача, а не acceptance.

## Прямые ответы

1. **Почему в UI нули?** Код `project_understanding_view` возвращает успешный, но семантически пустой объект, когда в `workspace.project_understanding_reconciliations` нет reconciliation. React затем считает длины пустых `fields`, `page_roles`, `work_packages` и `defects`, поэтому показывает `0/0/0/0`. В результате «0 замечаний» означает *нет reconciliation/анализа*, а не *анализ не нашёл замечаний*. Скриншот соответствует именно этому пути. Однако подтвердить row-level причину для ОЗЕРО нельзя: workspace отсутствует во всех доступных на MBP БД, включая БД запущенного API/worker. [E-04, E-05, E-09]
2. **Получает ли Qwen document jobs?** Для ОЗЕРО в текущей подключённой среде — **доказательств нет**. Локальный Qwen-сервер отвечает `ready`, а актуальный worker-код содержит Qwen image adapter, но БД этого worker не содержит ни workspace, ни его jobs/attempts. Историческая mission-запись о 22 source versions, 97 655 locators и 38 Qwen-страницах существует, но не подтверждается текущей runtime-БД и потому не является текущим фактом. [E-02, E-04, E-05, E-06, E-10]
3. **Где первый сквозной разрыв?** Первый установленный разрыв — **развязка между пользовательским контуром ОЗЕРО и текущим локально контролируемым API/worker/DB**. Запущенные API и оба worker используют `asd_kontur_public_demo`; в ней нет ни ОЗЕРО, ни вообще workspace rows. Поэтому невозможно проследить upload → extraction → retrieval → answer или безопасно чинить его «на глаз». Внутри кода следующий известный разрыв — отсутствие reconciliation маскируется пустым 200-response.
4. **Какие прошлые claims были уже пользовательского результата?** «Qwen runtime ready», «Qwen OCR adapter committed», «source locators/страницы extracted», «document page classification», «Gateway/assistant foundations» и зелёные unit/static проверки уже, чем пользовательский результат. Они не доказывают: наличие ОЗЕРО в исполняемой БД, durable completion всей dependency chain, assembled ProjectDefinition/WorkPackages/Matrix, evidence delivery в UI либо evidence-backed ответ на вопрос о котлованах.
5. **Точная последовательность к usable ОЗЕРО Tender:** (a) восстановить доказуемую привязку public UI → MBP API → БД с существующим ОЗЕРО и зафиксировать release/configuration; (b) снять baseline workspace/jobs/objects; (c) исправить empty-success view и full-corpus reconciliation scheduling/status; (d) довести affected jobs через Qwen/deterministic pipeline с lineage; (e) собрать и показать evidence-backed project model; (f) построить source-backed inventory котлованов, затем Tender outputs; (g) проверить UI, retrieval и answer path. Детали в разделе «Доставки».
6. **Что остаётся до ProductReady?** ОЗЕРО Tender — один реальный workflow, но не готовность продукта. Полный denominator: 143 capabilities; нужны complete E2E Tender, Support, Audit и Restoration, три постоянных профессиональных результата, outputs/ID package, field/offline и operational/scale acceptance. Сейчас формальный state проекта: `TrialReady=false`, `OKSReady=false`, `ProductReady=false`.

## 1. Продуктовая граница и meaning of ready

ASD-KONTUR обязан преобразовать ПД/РД, ПЗ, договор, ВОР/смету, регламент, НТД и подтверждённые факты в evidence-backed ProjectDefinition/структуру ОКС, работы/объёмы/материалы, control/evidence, ИД, предъявленные объёмы и оплату. Требуются: защитный protocol разногласий и переработанный договор; поиск omissions/constructability/geometric conflicts; исполнительные схемы только по подтверждённой проектной и фактической геометрии; заполненные акты и package ИД с реестром первым документом.

Нормативный registry содержит 142 stable IDs по 13 planes, v2.3 добавляет `field.secure-android-client`: **143** обязательных capability. Delta v2.5 документирует 16 `CAPABILITY_READY`, 45 `PARTIAL`, 36 `FOUNDATION_ONLY`, 39 `CONTRACT_ONLY`, 7 `NOT_IMPLEMENTED`; это документированное состояние, не измерение этого deployed contour. Полный построчный ledger — `CAPABILITY_GAPS.csv`.

| Граница | Что требуется | Состояние в этом snapshot |
|---|---|---|
| Usable ОЗЕРО Tender | Документы доступны в той же БД, модель/анализ/доказательства видимы, grounded answer и Tender outcome | **Не доказано; live workspace недоступен текущему API/worker** |
| Capability accepted | Production-shaped surface, declared real formats, professional result, E2E evidence | Отдельные исторические foundations есть; incident-critical capability не принята |
| ModeReady | Полный admission → output/export/recovery workflow конкретного режима | Tender **не готов**, остальные modes не измерялись этим инцидентом |
| ProductReady | Четыре ModeReady + 3 продукта + system operational acceptance | **false** |

## 2. Фактическая topology и version skew

| Компонент | Наблюдаемое размещение/configuration | Версия/роль | Health/evidence | Риск для инцидента |
|---|---|---|---|---|
| Frontend | `ASD_FRONTEND_DIST` из release worktree `b67bcd6`; public ingress исторически проксирует через reverse SSH | React/Vite assets release `b67bcd6` | Browser binding в этой сессии отсутствует; внешний HTTPS запрос не завершился через текущий proxy | Нельзя подтвердить, что screenshot обслужен именно этим asset/API |
| API | MBP loopback `127.0.0.1:8765`, PID 29697 | executable worktree `b67bcd6`, DB `asd_kontur_public_demo` | Port listens; `/api/v1/health` is 404, поэтому health не принят | В его БД ОЗЕРО отсутствует |
| Assistant worker | PID 29715, same local DB | `b67bcd6` | Process exists, no OЗЕРО turn/jobs reachable | Не может обслужить исторический turn в текущем DB |
| Document worker | PID 37287, same local DB | executable `120006d`; launchd plist still declares `b26eb59` | Process exists; no OЗЕРО job rows in DB | Конфигурационный skew и нет доказательства обработки проекта |
| Supervisor/ingress | launchd; SSH `-R 127.0.0.1:18765:127.0.0.1:8765` | ingress log last write 2026-08-30 | Running state, но исторический log не доказывает current forwarding | Public UI can be disconnected/mismatched |
| PostgreSQL | MBP `127.0.0.1:5433` | `asd_kontur_public_demo`, Alembic `0038_consultant_request_id` | reachable read-only | 0 workspace rows; requested ID absent from every locally scanned workspace DB |
| Object store | local workspace-object configuration | path/content intentionally omitted | Cannot scope source objects without actual workspace DB | Do not infer object availability |
| Qwen | MBP loopback `127.0.0.1:8790`, PID 36891 | `Qwen3.8-27B` | `GET /health` = ready | Server availability ≠ document-job integration |
| Embedding/reranker | embedding process on 8791; reranker not identified | local profile only | 8791 health route returned 404; reranker runtime unqualified | No retrieval-quality acceptance |

`127.0.0.1` here is MBP loopback, not an external URL. The documented public architecture is VPS proxy → reverse tunnel → MBP loopback; the tunnel configuration itself is present, but no current end-to-end public request was verified. Exact keys, credentials and object paths are intentionally omitted.

## 3. The four zero counters — code-level trace

| UI metric | React mapping | API/query | Exact empty behaviour | Meaning of zero |
|---|---|---|---|---|
| Сведений | `Object.keys(definition.fields ?? {}).length` | `GET /api/v1/workspaces/{id}/project-understanding` → `project_understanding_view` | no reconciliation → `{definition:{fields:{},gaps:[]}}` | No assembled reconciliation, **not** absence of project facts |
| Разобрано страниц | `value.page_roles.length` | same | `page_roles: []` | No reconciliation view, not necessarily no pages/extraction |
| Пакетов работ | `value.work_packages.length` | same | `work_packages: []` | No assembled work package result |
| Замечаний | `value.defects.length` | same | `defects: []` | **No analysis** is indistinguishable from no defects — defect |

`Сформировать модель объекта` calls `POST /api/v1/workspaces/{id}/project-understanding/runs` and only invalidates the project-understanding/jobs queries on success. Repository method selects one latest active non-zip document (`ORDER ... LIMIT 1`), derives a corpus digest, and creates/returns a `PROJECT_UNDERSTANDING_RECONCILIATION` job. It does **not** itself establish that every document dependency is complete. The UI has a generic pending notice and no factual upstream dependency/broken-chain explanation. No `project_understanding_runs` row can be checked for ОЗЕРО because the actual workspace is absent from the connected DB; therefore it is not established whether the button was ever invoked.

### Required repair behaviour

Return an explicit typed materialization state: `not_requested`, `queued`, `running`, `blocked` with upstream job IDs/reasons, `partial` with covered denominator, or `complete`. The UI must not render absence as completed zero findings. Reconciliation must use a complete versioned source manifest, not one document chosen by arbitrary recency; partial valid candidates should remain visible with their coverage boundary.

## 4. Processing chain reconciliation

### Current effective observation

For the **currently supervised API/worker database**, all OЗЕРО counts are unavailable because its workspace table has zero rows and the requested ID is absent. The table below keeps this distinct from earlier notes.

| Stage/unit | Current effective OЗЕРО count in connected DB | Historical note (not current fact) | Handler / output | What success would prove |
|---|---:|---:|---|---|
| admitted files/source versions | unavailable | 22 source versions | durable admission → `workspace.document_versions` | registered source/version only |
| page inventory | unavailable | unavailable | PDF inventory → `document_pages` | pages enumerated |
| native text/layout | unavailable | 97 655 source locators | native layout → `native_layout_element_versions`, `source_locators` | native extraction only |
| page health/routing | unavailable | unavailable | page health/routing tables | routing decision, not OCR result |
| OCR/VLM outcomes | unavailable | 38 Qwen OCR persisted pages | `ocr_extraction_versions` | validated output for specific pages only |
| classification | unavailable | unavailable | `document_page_role_candidates`, `document_role_decisions` | deterministic role result, not project model |
| aggregation/candidates | unavailable | unavailable | project field/work/quantity/material candidate tables | candidates, not confirmed facts |
| ProjectDefinition/structure/packages/matrix | unavailable | screenshot says zero, not a count | versioned project tables + reconciliation | assembled versioned model |
| evidence index/API/UI | unavailable | 206 matching fragments/12 docs/65 pages were discovery evidence only | index/API/view | retrieval coverage and displayed result |

The historical 22/97 655/38 figures are intentionally not added to a current denominator. They must be re-read from the database that owns ОЗЕРО, with attempts collapsed by source version and job retry lineage. A `succeeded` job must be paired with required output rows/digests; a job label alone does not prove output.

Likely dependency risks in the implementation, to verify on that DB: failed parent attempt should not permanently block a valid replacement; a native-text-sufficient page must not wait for unnecessary vision OCR; successful replacement must make downstream reconciliation runnable; leases must have live executor; placeholder/empty outputs must not advance a stage.

## 5. Qwen policy and actual execution path

### Policy

Current user instruction requires deterministic native work (hashing, inventory, native extraction, rendering, layout, exact parsers/calculation) and local **Qwen3.8-27B exclusively** for model-based recognition/semantic interpretation; Apple Vision, Tesseract, Codex inference and cloud fallback are prohibited. ADR-0006 additionally requires candidate-before-fact, locator/provenance and native-first routing.

### Code finding (not runtime acceptance)

At `120006d`, `application_spine/worker.py` constructs `IndustrialDocumentUnderstandingPipeline` with `QwenVisionOcrAdapter`. `ocr.py` serializes actual rendered image bytes (base64) to the local vision endpoint; `qwen_server.py` decodes image bytes through the vision runtime. This is a genuine image-interface design, not a filename prompt. Current code also includes bounded stream assembly and page-level schema/coordinate validation from commits `3aec486`, `1310872`, `120006d`.

But `document_understanding/semantic.py::classify_pages` and `extract_structured_candidates` remain deterministic phrase/regex/table-pattern processing. They do not invoke Qwen. That is acceptable only for deterministic classification/extraction contracts; it is **not** evidence of semantic Qwen understanding of project content. Any semantic entity extraction needed for pits, geometry or scope lacks a shown Qwen-backed candidate stage in this snapshot.

### What is actually proved now

* Qwen server is ready at 16:09 local time.
* No actual OЗЕРО Qwen request, source/page identity, input modality, completion, validated persisted output or dependent job completion is reachable in current worker DB.
* Thus the answer to “why did Qwen look idle?” is presently: **the current supervising worker is connected to a data store without the uploaded workspace; a ready Qwen process is irrelevant until that topology error is corrected.**

## 6. Three-document and assistant traces

The requested three source traces cannot be honestly produced from the current environment: no `document_records`, `source_versions`, `document_pages`, source objects or assistant turn for the given workspace exists in the database read by the current services. Selecting names from old chat observations would violate the requested evidence standard. This is an explicit evidence gap, not a claim of absent files.

Required trace once the owner DB is located, for three actual source IDs covering available native text, scan/image and a construction/table/drawing input:

`source_version (hash/path) → document_version → page → native/layout or Qwen OCR attempt → role/candidate → reconciliation version → evidence locator → API response → rendered UI field`.

The original pit-count turn cannot be reconstructed here either. In the connected database no matching assistant turn exists. The earlier report that it had metadata/NTD but no project text is a user observation to validate on the owning DB, not a substitute for receipts. The reported 206 matches in 12 docs/65 pages are discovery evidence, not a distinct-pit inventory. No verified count can be published.

Correct project-wide pit answer requires: source-backed, version-aware `ExcavationPitCandidate`/entity identities; normalized alias/location/section/stage fields; explicit inclusion/deduplication policy; deterministic aggregate over reconciled identities; coverage of authoritative enumeration; citations to source/page/sheet/region. Keyword occurrence, top-k hits, filenames and work-package rows cannot establish a total.

## 7. Knowledge and assistant readiness

| Layer | Current result | Consequence |
|---|---|---|
| Platform NTD | The expected 113-searchable assertion is **not demonstrated in `asd_kontur_public_demo`**; do not import it from another database as fact. | Normative conclusion must remain unavailable/typed until source/version/authority is present. |
| Practice Intelligence | Contract/code may exist; no OЗЕРО path verified | Cannot replace project evidence for project-specific count |
| Active RuleVersions | No OЗЕРО-aware applicability trace in connected DB | Rules cannot prove project facts |
| Workspace retrieval | OЗЕРО source scope absent from worker/API database | assistant cannot retrieve project content there |
| General consultant | Foundations historically referenced; no real Qwen E2E in this snapshot | Not accepted |
| Workspace assistant | Original failed turn not reachable; 0 reproducible receipts | Not accepted; cannot answer pit count |

Project facts from PD/RD can be answered independently of NTD once document extraction/index/retrieval works. Normative excerpts cannot establish the number of this project’s котлованов.

## 8. Prioritized defect ledger

| Priority | Demonstrated evidence | Consequence | Proposed repair |
|---:|---|---|---|
| P0 | Current API/assistant/document workers share `asd_kontur_public_demo`; workspace table is empty and requested ID is absent from scanned local workspace DBs | No safe reproduction, recovery or answer verification for the user's real project | Locate/restore the actual public-contour DB/configuration, bind all writers/readers to it, capture exact release/config and verify one harmless scoped read before mutation |
| P0 | UI displays fallback empty response as zero metrics; `defects=[]` means no reconciliation | User sees an untruthful apparent analysis result | Typed materialization state and coverage/blocker display; preserve partial results |
| P1 | Document worker executes `120006d`, API/frontend/assistant `b67bcd6`; worker launchd declares older `b26eb59` | Behavior/release claims are non-reproducible | Single qualified release manifest; restart only approved affected services after staging/rollback check |
| P1 | Qwen `/health` only; no OЗЕРО job receipts in DB | “Qwen processing” unsubstantiated | Persist request/provenance/result receipts and prove one production-shaped job through actual source/page |
| P1 | Project-understanding command selects one newest source and no evidence of complete manifest prerequisites | Can assemble an incomplete model or hide blocked dependency | Versioned complete corpus manifest, dependency graph and reconciliation coverage semantics |
| P2 | Semantic page classification/extraction is deterministic matching | No evidence-backed semantic entity inventory for pits/scope | Add bounded Qwen semantic candidate adapter where deterministic parser is insufficient, preserve candidates/evidence and deterministic reconciliation |
| P2 | No qualified reranker/actual workspace retrieval path | Relevant evidence may not reach Qwen | Qualify local runtime, inspect runtime config and end-to-end evidence packing without full-corpus prompts |

## 9. Coherent completion deliveries

### D1 — restore an observable authoritative contour

* **Resolves:** P0 topology mismatch and inability to reproduce.
* **Reuse:** existing launchd API/worker/assistant services, RLS workspace model, durable jobs, reverse ingress.
* **Actions:** identify database/host actually serving screenshot; compare frontend asset/API/worker commit and Alembic revision; create recoverable backup and source-object protection; configure a single writer and explicitly hand over/restart only affected services after isolated qualification.
* **Acceptance:** exact OЗЕРО workspace and original failed turn read through the same public API/session, a known source locator opens, current DB and jobs agree. No migration/deploy follows merely from discovery.
* **Recovery:** no automatic code downgrade after a schema move; restore path is versioned backup plus compatible release.

### D2 — make materialization truthful and complete

* **Resolves:** empty-success counters and blocked/partial pipeline invisibility.
* **Affected:** project-understanding repository/API model, React page, durable dependency/reconciliation handlers, regression fixtures.
* **Actions:** materialization state/coverage contract; complete active source manifest; reconcile replacement attempts; use native-first; only re-run affected source/page jobs; retain historical attempts and output lineage.
* **Acceptance:** OЗЕРО UI shows admitted/covered/queued/failed/not-required denominators, real partial candidates/evidence, and explicit reason for missing model. `0 defects` only after completed analyzed denominator.

### D3 — actual local-Qwen evidence path

* **Resolves:** unproven Qwen processing and missing semantic inventory.
* **Affected:** Qwen vision adapter, bounded semantic candidate adapter, worker receipts, candidate validation/persistence, UI progress.
* **Actions:** after D1, choose a truly affected scan/image page; run one durable job through worker; capture source/page, model/profile, request digest/modality, validation and persisted candidate; then process remaining eligible queue sequentially. Do not force OCR on native-sufficient page.
* **Acceptance:** durable, source-bound result and dependent stage actually runnable; UI distinguishes effective retry from history; no Apple/Tesseract/cloud fallback.

### D4 — evidence-backed model, pits and usable Tender

* **Resolves:** absent model and unsupported count.
* **Reuse:** workspace model, locator/evidence infrastructure, Knowledge Gateway, deterministic reconciliation.
* **Actions:** compile source-backed ProjectDefinition/structure/work/material/quantity candidates; establish pit identities and coverage; run Tender discrepancy/risk/clarification/scope analysis; preserve sheet-piling scope as preliminary candidate, not fact.
* **Acceptance:** user sees model and evidence links; new assistant turns answer “сколько котлованов”, enumeration and sheets using retrieved project evidence; if coverage unresolved, answer gives established subset plus exact uncertainty rather than an invented total.
* **Support continuity:** retain same workspace/mode executions and selected work-package candidates, interfaces, accepted revisions, quantity confirmation status, unresolved Tender clarifications and proposed control/ID requirements. Do not activate Support as award/commencement.

### D5 — mode and product completion

* **Resolves:** remaining capability ledger rather than relabelling a Tender slice as product readiness.
* **Order:** Tender R1/R2 outputs → Support control/ID/output package → Audit report workflow → Restoration non-fabricating workflow → CAD/verified geometry R3 → Field/offline → operations/scale → four mode E2E and formal decisions.
* **Acceptance:** each mode passes admission-to-output/export/recovery with evidence. ProductReady only after all four, three permanent professional results and system operational acceptance. Some of this work is executable under existing development authorization; formal Trial/Mode/Product decisions and any real legal/professional authority remain external.

## 10. Capability-gap ledger and next executable action

`CAPABILITY_GAPS.csv` lists every one of the 143 required capabilities with its stable ID, documented readiness, observed evidence boundary, actual unverified gap, dependency and user-facing result. It deliberately does not turn old contract/fixture claims into live acceptance.

**Next implementation action after this handoff:** identify the authoritative database/configuration behind the authenticated public OЗЕРО UI and validate a scoped read of workspace `01a088aa-0491-7bdd-9127-8359fe927a27`. Only then capture its immutable baseline and implement the D2 materialization-state correction against the service that actually owns the project. This needs no new upload and no project deletion. It is currently blocked by a demonstrated topology/observability gap, not by the source corpus or by Qwen capability.

## Evidence classification

* **Direct runtime observations:** E-01–E-08.
* **Code findings:** E-09–E-10.
* **Contract/readiness findings:** E-11.
* **Unavailable evidence:** E-12 plus all OЗЕРО row-level data in the current configuration.

See `EVIDENCE_INDEX.md` for exact command classes and limits, and `STATE.json` for machine-readable snapshot.

