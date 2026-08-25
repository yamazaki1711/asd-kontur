# Архитектура доменной базы знаний и памяти ASD-КОНТУР v0.1

Статус: **Accepted architecture baseline**
Принято: 2026-08-22 ведущим архитектором Codex по явным архитектурным
полномочиям владельца продукта; реализация и knowledge content не приняты
Область: платформенная архитектура, не привязанная к конкретному ОКС
Основание: развитие идей `mac_asd` (RAG, KAG, pgvector, Evidence Graph, Lessons Learned) без механического переноса реализации

## 1. Решение

ASD-КОНТУР получает не «векторную память для LLM», а **локальную
версионируемую платформу инженерных знаний**. Локальность здесь относится к
канонической platform/workspace memory и контролируемому Knowledge Tool
Gateway, а не устанавливает local-only VLM execution. По ADR-0006 вычисление
VLM является local-first hybrid; внешний provider никогда не становится
хранилищем канона и не получает прямого доступа к нему. Каноническое содержание
существует независимо от любой модели. LLM/VLM:

- извлекают кандидатов;
- планируют запросы к знаниям;
- получают только доказательный пакет;
- не публикуют нормативные факты и правила самостоятельно.

RAG является поисковым механизмом. KAG — способом связать структурированные знания, доказательства и многошаговый вывод. Ни RAG, ни граф, ни текст модели не являются источником истины.

## 2. Что сохраняется и что меняется относительно mac_asd

Сохраняются удачные идеи:

- PostgreSQL как системная база;
- pgvector и гибридный поиск;
- нормализация НТД до пунктов, таблиц, определений и ссылок;
- Evidence Graph;
- доменные ловушки и накопление проверенного опыта;
- контуры контекста для ИИ;
- очистка данных ОКС после завершения обработки.

Меняется принцип организации:

1. Разрозненные `NormativeClause`, `DomainTrap`, Lessons Learned, chunks и GML-граф объединяются общей моделью идентичности, версий и provenance.
2. Любая запись получает явную область: `platform` или `workspace_id`.
3. Проектное наблюдение не становится глобальным правилом автоматически — даже после повторения.
4. Граф является производной проекцией канонических таблиц, а не отдельной истиной.
5. Модель не получает неограниченную подстановку похожих чанков; она вызывает типизированные инструменты и получает Evidence Pack.
6. Векторизация версионируется и может быть полностью перестроена без изменения канонических знаний.

## 3. Пять слоёв платформы

### 3.1. Source & Evidence Ledger

Неизменяемый реестр первоисточников:

- SHA-256 и content-addressed путь;
- вид документа, издатель, юрисдикция;
- редакция, дата действия, статус и документ-замена;
- страницы, листы, координаты фрагментов;
- способ получения текста: native text, OCR, VLM, manual;
- качество извлечения и история проверок.

Оригиналы хранятся в файловом blob-store на SSD. PostgreSQL хранит идентификаторы, метаданные, структуру и ссылки. Изменение файла создаёт новую `source_version`, а не перезаписывает старую.

Для НТД приоритетным source является официальный каталог Минстроя. Пополнение
выполняется по версионированному реестру релевантности, а не неконтролируемым
массовым скачиванием. Для каждой редакции обязательны official URL, дата
получения, SHA-256 и точный locator; статус действия и применимость не
выводятся из имени файла, а отменённая редакция остаётся в provenance.

Методические руководства принимаются отдельным source kind
`MethodologicalPracticeGuide`. Для них обязательны те же immutable bytes,
`SourceVersion`, object receipt, acquisition provenance и page/region lineage,
но official-NTD registry и нормативная authority не присваиваются. Exact local
model/render/validation profiles и terminal page receipts составляют отдельный
platform ingestion ledger.

### 3.2. Canonical Knowledge Model

Канонические сущности:

- `normative_document`, `document_edition`;
- `structural_unit` (раздел, пункт, подпункт, приложение);
- `table`, `figure`, `definition`;
- `requirement`, `permission`, `prohibition`, `exception`;
- `cross_reference`, `supersedes`, `amends`;
- `work_type`, `construction_element`, `material`, `control_operation`;
- `required_document_type`, `acceptance_event`;
- `contract_requirement`, `customer_regulation`;
- `knowledge_assertion` с интервалом действия и обязательным provenance.

Отдельный canonical authority layer `methodological_practice` содержит
`PracticeGuideEdition`, structural units, typed ID/form/field/workflow
guidance, evidence, uncertainties и явные conflicts. Он не является
`KnowledgeAssertion` нормативного слоя и не может изменять НТД или активную
`RuleVersion`. Пример заполнения не становится универсальным требованием.

По ADR-0011 этот слой строится не как RAG-набор независимых chunks, а как
постоянный versioned `ID Practice Intelligence`. Его физическая архитектура
состоит из пяти уровней:

1. permanent source bytes/metadata/receipt;
2. canonical typed Practice Intelligence;
3. deterministic operationalization и RuleCandidate boundary;
4. rebuildable exact/FTS/vector/sparse/graph projections;
5. ephemeral deterministic `IDPracticeContextPack` runtime context.

Исходный `SourceVersion` и canonical intelligence имеют retention class
`permanent_platform_core`. Workspace lifecycle не может адресовать их для
удаления. Новые bytes создают новую `PracticeGuideEdition`; прежняя не
перезаписывается. Backup/restore проверяет object SHA-256 и semantic
fingerprints до перестроения retrieval plane.

НТД, договорные требования, правила заказчика и знания конкретного ОКС не смешиваются. На запросе применяются дата, юрисдикция, стадия, вид работ и договорный контекст.

### 3.3. Deterministic Rule Registry

Исполняемые правила отделены от текстовых знаний. Для каждого правила обязательны:

- стабильный ключ и версия;
- условия применимости;
- типизированные входы и выходы;
- ссылки на конкретные редакции и пункты источников;
- именованную conflict group и утверждённую subject-specific policy разрешения конфликтов;
- набор положительных, отрицательных и граничных тестов;
- lifecycle-статус из полного перечня `drafted / evidence_attached / candidate /
  reviewed / approved / active / suspended / superseded / retired / rejected`;
- автор и протокол утверждения.

Полный контракт состояний, `RuleSetVersion`, applicability, evaluation и trace
определён в `DETERMINISTIC_RULES_CATALOGUE_v0.1.md`. ИИ может создать только
платформенный promotion candidate; Workspace RuleVersion не может быть создана
или утверждена моделью. По принятому `DR-02/B` переходы в
`reviewed`/`approved` требуют independent human reviewer и другого
class-qualified human approver; Product Owner управляет системой полномочий,
но не обязан утверждать каждое правило. Промышленный результат создаёт только
`active RuleVersion` в закреплённой approved RuleSetVersion. Изменение
evidence, predicate, output contract, effective interval или conflict policy
создаёт новую RuleVersion и новый review cycle.

Каждый workspace получает pin при создании. По `DR-01/B` controlled upgrade
допустим только после impact preview, schema/implementation compatibility,
authority approval и versioned recomputation с сохранением прежних
RuleTrace/results; до полного завершения действует прежний pin. Archived,
reset/destroyed workspace не обновляются, rolling rules запрещены.

По `DR-03/B` каждая conflict group ссылается на versioned subject-specific
`ConflictPolicy`; неразрешимый формально конфликт блокирует material process и
передаётся qualified human authority как typed scoped decision, но не LLM.
По `DR-04/B` workspace rule формальна, immutable, имеет обязательный
`workspace_id`, evidence/tests/authority и входит только в pinned RuleSet
данного workspace; она уничтожается по RetentionProfile и становится
platform rule только как новая сущность через Promotion Gate. Таким способом строятся
RequiredDocumentMatrix, проверки комплектности, зависимости работ и основания
для разногласий.

### 3.4. Retrieval & Graph Index Plane

Каноническая запись индексируется несколькими независимыми способами:

1. B-tree/GIN по точным реквизитам, кодам НТД, датам и типам.
2. PostgreSQL Full Text Search для русской лексики, номерации пунктов и точных терминов.
3. pgvector HNSW для семантического поиска.
4. Опциональный sparse-index для специализированной лексики.
5. Типизированные рёбра графа для cross-reference, applicability, requires, conflicts, supersedes и evidence_for.
6. Cross-encoder reranker после объединения lexical и dense кандидатов.

Результаты lexical и dense retrieval объединяются RRF, затем фильтруются по области, редакции и применимости, после чего reranker формирует короткий список. Граф расширяет только уже найденные и типизированные узлы.

На первом этапе отдельная графовая СУБД не нужна: рёбра хранятся в PostgreSQL, а графовая проекция пересобирается. Neo4j/OpenSPG рассматриваются только после измеренного узкого места в multi-hop запросах.

### 3.5. Knowledge Tool Gateway

«Нативный доступ Qwen» означает не прямой SQL и не память в весах модели, а
типизированные инструменты локального application boundary:

- `knowledge.search`;
- `knowledge.get_source_fragment`;
- `knowledge.get_applicable_rules`;
- `knowledge.trace_assertion`;
- `knowledge.explain_conflict`;
- `knowledge.get_required_documents`.

Additive methodological-guidance contract предоставляет:

- `knowledge.get_id_guidance`;
- `knowledge.get_form_guidance`;
- `knowledge.get_field_guidance`;
- `knowledge.trace_guidance`;
- `knowledge.explain_guidance_conflict`.

Эти tools всегда возвращают authority layer `methodological_practice` и exact
page/region EvidencePack. Внешний provider прямого доступа к ним не получает.

Любая ID-related операция обязана сначала выполнить version-pinned
`ContextAssemblyPolicy`. Она выбирает релевантные units по документу,
форме/полю, виду работ, разделу РД, этапу, контрольной операции, evidence,
комплектованию, режиму и задаче ID Generator. Модель не решает, вызывать ли
Gateway, и не получает все страницы пособия. `knowledge_incomplete`,
`guidance_normative_conflict` и `edition_mismatch` являются typed outcomes;
silent empty retrieval запрещён.

Gateway строит **Evidence Pack**:

- формулировка найденного знания;
- точная цитата;
- документ, редакция, пункт, страница;
- область и дата применимости;
- путь рассуждения по графу/правилу;
- оценка retrieval, но не «истинности»;
- явные пробелы и противоречия.

Локальный `Qwen3.8-27B` получает этот JSON-контракт и формирует кандидат
результата. External VLM integration не получает прямого доступа к Gateway:
trusted application layer выполняет retrieval/validation локально и может
передать только policy-разрешённый минимизированный фрагмент Evidence Pack в
точном workspace/purpose scope. Без источника утверждение не может перейти в
доменный факт.

## 4. Две памяти и шлюз продвижения

### Платформенная память

Сохраняется между партиями:

- проверенные НТД и их редакции;
- утверждённые правила;
- общие классификаторы и онтология;
- обезличенные и утверждённые паттерны ошибок;
- тестовые наборы и оценки качества;
- immutable редакции методических руководств и versioned ID Practice
  Intelligence с отдельной ненормативной authority
  `methodological_practice`.

### Workspace-память ОКС

Создаётся для одной партии:

- документы ОКС и чанки;
- факты, кандидаты и неопределённости;
- договорные и заказческие правила;
- реестр работ, замечаний, схем и решений;
- диалоги и временные индексы.

`workspace_id` обязателен во всех проектных таблицах, индексах, очередях, логах и графовых рёбрах. Изоляция обеспечивается не соглашением имён, а схемой БД, ограничениями и RLS/репозиторными guard'ами.

### Promotion Gate

Знание ОКС может стать платформенным только после:

1. удаления идентификаторов объекта и участников;
2. классификации источника;
3. подтверждения повторяемости и области применимости;
4. привязки к первичным основаниям;
5. экспертного или регламентированного утверждения;
6. прохождения regression-тестов.

Автоматическое превращение повторившегося Lessons Learned в правило запрещено.

### Принятая retention-граница Promotion Gate

Решением владельца продукта от 2026-08-21 приняты RD-01…RD-05; полные
нормативные формулировки находятся в
`LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md` §19. Для этой архитектуры это
означает:

- после verified reset project content не остаётся в platform memory;
- approved promoted knowledge переживает reset только как минимальный
  Evidence Capsule по allowlist Lifecycle Specification §10.2, без live-link,
  project memory, project embeddings или unresolved AI candidates;
- project blobs разных workspace физически не дедуплицируются в промышленном
  v0.1; platform blobs образуют отдельный scope;
- portable logical archive и physical recovery backup — независимые копии с
  разными контрактами и retention entries.

Эти положения не назначают календарные сроки: их задаёт полный versioned
`RetentionProfile` конкретного промышленного workspace.

## 5. Конвейер обработки НТД

1. Выбор документа по управляемому реестру релевантности; официальный каталог
   Минстроя — приоритетный source (включая релевантные СП 48, СП 70, СП 543,
   но без hard-coded исчерпывающего списка).
2. Регистрация `NormativeDocument`, official URL, retrieval timestamp и
   SHA-256; каждая редакция — отдельная `NormativeEdition`.
3. Экспертно проверяемое определение статуса, дат, области применимости и явной
   цепочки supersedes/amends; имя файла не является основанием.
4. Структурный разбор по пунктам, таблицам и приложениям — не произвольная нарезка по размеру; точные locators сохраняются независимо от индексов.
5. Native text first; OCR/VLM только для неразрешённых визуальных областей.
6. Извлечение кандидатов определений, требований, исключений и ссылок.
7. Проверка схемы, ссылочной целостности, нумерации и конфликтов.
8. Экспертное подтверждение канонических assertions и rules.
9. Связь применимости с `WorkType`, `ConstructionElement`, `Material`,
   `ControlOperation` и `RequiredDocumentType`.
10. Построение lexical/dense/sparse/graph индексов как производных данных.
11. Публикация неизменяемой версии knowledge base без удаления отменённых редакций из provenance.
12. Прогон регрессионного набора вопросов и правил.

## 6. Использование ресурсов MBP M5 Max 128 GB / 2 TB

Целевая authoritative конфигурация на MBP по ADR-0008:

- PostgreSQL 18 + pgvector;
- локальные APFS cache/temp/recovery representations разрешённых объектов;
- обязательный S3-compatible durable object plane для разрешённых source
  bytes, крупных artifacts, exports, portable archives и encrypted recovery
  objects; canonical identity/scope/lineage/policy остаются в PostgreSQL MBP;
- MLX для локального generation/embedding/reranking;
- Qwen3.8-27B-MLX-8bit — основной reasoning/generation runtime;
- отдельная embedding-модель Qwen3 Embedding и reranker, выбранные внутренним benchmark.

M5 Max допускает до 128 GB unified memory и 614 GB/s bandwidth; это позволяет держать Qwen3.8-27B 8-bit и инфраструктуру БД локально. Однако одновременная тяжёлая генерация, embedding и reranking конкурируют за общую память и Metal bandwidth. Поэтому вводится Model Runtime Manager:

- один тяжёлый GPU-сеанс за раз;
- ingestion-эмбеддинг выполняется пакетно вне интерактивной генерации;
- query embedding может быть резидентным только после измерения;
- reranker загружается по требованию или держится резидентно, если benchmark подтвердит выгоду;
- PostgreSQL/FTS и чтение evidence могут выполняться на CPU параллельно.

2 TB не трактуются как бесконечное хранилище. Вводятся квоты для моделей, исходников, индексов, workspaces и snapshots; минимум 25% диска резервируется под рабочий запас, WAL, перестроение индекса и восстановление.

### 6.1. Local-first hybrid VLM execution

Локальная конфигурация остаётся основной для юридических, конфиденциальных,
сложных, интерактивных задач и draft исполнительных схем. Для
policy-разрешённой массовой обработки растровых PDF допускается внешний
`VlmExecutionProvider`; планируемый provider — `polza.ai`, но архитектура от
него не зависит.

Local и external execution используют один логический result contract:
provider/model identity и version, execution profile, версии prompt/schema/
preprocessing/rendering/verification policy, source/page/image locators,
purpose, typed Candidate, field-level evidence, uncertainty, validation,
timings, применимые cost metadata и retry/repair history. Совпадение model name
не означает эквивалентность результата.

External invocation разрешается только Authorization Model: точный
`workspace_id`, data classification, `WorkspaceEgressPolicy`,
provider/model/profile allowlist, purpose limitation и payload minimization.
Project request/response artifacts остаются workspace memory. Ни local, ни
external VLM не публикует знание; Verification Harness и последующий
validation/confirmation process обязательны.

### 6.2. Physical knowledge authority по ADR-0008

Каноническая knowledge platform физически принадлежит MBP authoritative core:
Source & Evidence Ledger metadata, Canonical Knowledge, Rule Registry,
Promotion Gate и Knowledge Tool Gateway используют одну каноническую модель и
PostgreSQL MBP. Роль переносима на заменяющее оборудование только через
verified restore и explicit primary activation; она не привязана к серийному
номеру устройства.

VPS не получает самостоятельную platform/global memory.
`TECHNICAL_ARCHITECTURE_v0.3.md` выбирает по `TA-TD-02` только минимальную
filtered status projection, а не PostgreSQL/knowledge replica. Она обязана
указывать canonical checkpoint/fingerprint, schema, scope, expiry и staleness,
полностью перестраиваться и никогда не отвечать как SoR. Выбор остаётся
`Proposed` и не означает, что projection уже реализована.

S3 хранит разрешённые official/source bytes, renders, exports, portable
archives и recovery artifacts, но наличие объекта или hash не создаёт
`KnowledgeAssertion`, применимость или доступ. Platform/workspace object
identity, version, authority, lineage, classification и retention закреплены
в канонических metadata MBP. Cross-workspace physical deduplication project
objects запрещена.

External VLM не получает прямого доступа к MBP PostgreSQL, S3 workspace
namespace или Knowledge Gateway. Он получает только минимизированный exact
payload через provider boundary. `TECHNICAL_ARCHITECTURE_v0.3.md` выбирает
VPS controlled-egress gateway как proposed production route; на нём действуют
те же HV-01…HV-08 decisions. Смена execution node создаёт отдельный
route/profile identity и не переносит qualification или authorization
автоматически. Request/response artifacts остаются workspace memory и
уничтожаются по RetentionProfile.

## 7. Embedding и pgvector

Текущая отправная точка — семейство Qwen3 Embedding/Reranker, а не генеративная Qwen3.8. Qwen3-Embedding-8B поддерживает размерность до 4096 и MRL-сокращение. pgvector HNSW для `vector` индексирует до 2000 измерений, для `halfvec` — до 4000.

Поэтому размерность и модель не фиксируются по рейтингу. Проверяются варианты:

- Qwen3-Embedding-4B и 8B;
- 1024, 1536 и 2000 измерений `vector`;
- при доказанной выгоде — `halfvec`;
- Qwen3-Reranker 0.6B/4B/8B.

Каждый embedding хранит:

- `embedding_model_id`;
- `model_revision`;
- `dimension`;
- `dtype`;
- `instruction_version`;
- `chunker_version`;
- `source_version_id`.

Новая модель создаёт параллельный индекс; старый удаляется только после сравнения и переключения. Перевекторизация никогда не изменяет канонические знания.

## 8. Обязательный benchmark

До выбора моделей формируется русский строительный набор минимум из следующих классов:

- точный поиск пункта и документа;
- смысловой поиск требования;
- определение применимой редакции на дату;
- переходы по ссылкам и исключениям;
- извлечение из таблиц;
- связь «вид работ → контроль → обязательный документ»;
- договорное отклонение от базовой нормы;
- отрицательные запросы и недостаточность данных;
- конфликт источников.

Метрики:

- Recall@k, MRR/nDCG;
- precision цитат;
- правильность редакции и применимости;
- доля неподтверждённых утверждений;
- accuracy исполняемого правила;
- p50/p95 latency;
- пиковая unified memory;
- размер и время перестроения индекса.

Выбирается минимальная конфигурация, прошедшая пороги качества. Лидер публичного benchmark не является достаточным основанием.

## 9. Что не принимается сейчас

- прямой доступ LLM к таблицам PostgreSQL;
- GraphRAG/OpenIE как канонический источник;
- перенос OpenSPG/KAG целиком до проверки эксплуатационной цены;
- отдельный Neo4j без измеренной необходимости;
- глобальная таблица Lessons Learned без области и promotion gate;
- автоматическое создание нормативного правила из текста модели;
- хранение единственной версии embedding;
- смешивание НТД и фактов ОКС в одном пространстве без hard isolation.

OpenSPG/KAG и Microsoft GraphRAG используются как источники архитектурных приёмов: schema-constrained knowledge, взаимная индексация текста и графа, logical/hybrid retrieval. Их runtime не становится обязательной зависимостью ядра.

## 10. Последовательность реализации

### Этап A — контракты памяти

Сущности source/version/locator/assertion/rule/workspace, области данных и Promotion Gate. Без LLM.

### Этап B — минимальная вертикаль НТД

Один нормативный документ: структурный импорт → канонические units → FTS → цитируемый Evidence Pack.

### Этап C — hybrid retrieval

pgvector, embedding registry, RRF, reranker и benchmark.

### Этап D — typed KAG

Cross-reference/applicability/requires/conflicts, rule registry и multi-hop query plans.

### Этап E — provider-neutral AI boundary

Knowledge Tool Gateway, локальный основной Qwen, `VlmExecutionProvider`,
JSON-контракты, Authorization & Audit boundary и запрет публикации утверждений
без provenance. External provider adapter не создаётся до завершения
архитектурной очереди и утверждения точных egress policy instances.

### Этап F — жизненный цикл ОКС

Создание workspace → обработка → архив → проверяемая очистка → новая партия; продвижение обезличенных знаний только через Promotion Gate.

## 11. Критерий готовности

Архитектура считается реализованной не тогда, когда Qwen «хорошо отвечает», а когда:

- любой вывод трассируется до версии источника и правила;
- смена LLM не разрушает базу знаний;
- векторные индексы перестраиваются без потери канона;
- данные завершённого ОКС не доступны следующему workspace;
- утверждённые платформенные знания переживают очистку;
- неопределённость остаётся явной;
- четыре режима ASD-КОНТУР используют одну платформу знаний без специальных ветвей под пилот.

## 12. Технологические основания

- Qwen3 Embedding: https://huggingface.co/Qwen/Qwen3-Embedding-8B
- pgvector hybrid search и ограничения индексов: https://github.com/pgvector/pgvector
- PostgreSQL Full Text Search: https://www.postgresql.org/docs/18/textsearch.html
- OpenSPG/KAG: https://github.com/OpenSPG/KAG
- Microsoft GraphRAG architecture: https://microsoft.github.io/graphrag/index/architecture/
- MLX: https://github.com/ml-explore/mlx
- Apple M5 Max: https://www.apple.com/newsroom/2026/03/apple-introduces-macbook-pro-with-all-new-m5-pro-and-m5-max/
