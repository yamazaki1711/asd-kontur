# ADR-0005: Платформа знаний, изоляция workspace и Promotion Gate

- Статус: Accepted
- Дата: 2026-08-21
- Принято: 2026-08-22 ведущим архитектором Codex по явным архитектурным
  полномочиям владельца продукта; RD-01…RD-05 остаются прямыми решениями
  владельца продукта от 2026-08-21
- Основание: `docs/architecture/ARCHITECTURE_BLUEPRINT_v0.1.md`;
  `docs/architecture/KNOWLEDGE_AND_MEMORY_ARCHITECTURE_v0.1.md`;
  `docs/architecture/DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md`;
  `docs/architecture/LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md`;
  `docs/architecture/DOMAIN_CORE_SPEC_v0.1.md`; ADR-0001—ADR-0004

## Контекст

АСД-КОНТУР обрабатывает последовательность независимых ОКС одним и тем же
постоянным ядром (`README.md`, единое доменное ядро; `ARCHITECTURE_BLUEPRINT_v0.1.md`
§4). Это требует одновременно: (а) переиспользуемой платформенной памяти —
НТД, утверждённых правил, классификаторов, паттернов ошибок, которая
живёт дольше одного ОКС; (б) строго изолированной рабочей области для
данных каждого ОКС, не проникающей в следующий workspace; (в) безопасного
способа превратить проверенное наблюдение одного ОКС в платформенное
знание, не позволяя этому происходить автоматически по одному лишь
повторению или ответу модели.

Исследование `mac_asd` (детально — `docs/architecture/DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md`
раздел 9.1) показало конкретные, реализованные и впоследствии проблемные
паттерны, которые АСД-КОНТУР обязан не повторять: единственный глобальный
`nx.DiGraph`, являющийся хранилищем состояния, а не производной проекцией
(`src/core/evidence_graph.py`); удаление проектных данных по эвристике
обхода графа вместо структурной границы схемы (`remove_project_nodes`);
автоматическая мутация повторившегося наблюдения в правило после N
подтверждений без проверки применимости и без regression-тестов
(`src/core/lessons_service.py::verify_lesson`); фиксированная,
непереверсионированная колонка эмбеддинга, делающая смену модели
деструктивной миграцией (`DocumentChunk.embedding`).

## Решение

Принимаются пять взаимосвязанных архитектурных решений, формализованных
в `docs/architecture/DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md`:

1. **Канонические знания отделены от retrieval indexes и AI output.**
   Единственный источник истины для нормативного/правилового содержания —
   типизированные таблицы Canonical Knowledge Model
   (`NormativeDocument`/`NormativeEdition`/`StructuralUnit`/
   `KnowledgeAssertion`/`CrossReference`) и Deterministic Rule Registry
   (`Rule`/`RuleVersion`/`RuleEvidence`). Lexical/dense/sparse индексы и
   графовые проекции (`EmbeddingIndexVersion`, `GraphProjectionVersion`)
   — производные, полностью пересобираемые без потери канона. Вывод
   LLM/VLM (`ExtractionRecord`) — всегда кандидат, не факт и не правило.

2. **Platform memory отделена от workspace memory.** Каждая
   workspace-scoped таблица обязана иметь `workspace_id` — структурную,
   не факультативную колонку. Изоляция обеспечивается складывающимися
   механизмами: раздельные схемы PostgreSQL (`platform`/`workspace`),
   PostgreSQL RLS с политикой по умолчанию «запрет», составные внешние
   ключи, включающие `workspace_id`, обязательный `workspace_id` в
   репозиториях/очередях/индексах/аудите. Полная спецификация — раздел 4
   `DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md`.

3. **Граф — производная проекция канона, не источник истины.**
   `GraphProjectionVersion` пересобираем из `CrossReference`
   (платформенных) и workspace-scoped типизированных рёбер, хранящихся
   как обычные строки PostgreSQL, а не как единственный экземпляр
   in-memory графа с персистентностью в плоский файл.

4. **Модели получают доступ к знаниям только через Knowledge Tool
   Gateway.** Ни одна LLM/VLM не имеет прямого доступа к PostgreSQL.
   Единственный канал — типизированные инструменты (`knowledge.search`,
   `knowledge.get_source_fragment`, `knowledge.get_applicable_rules`,
   `knowledge.trace_assertion`, `knowledge.explain_conflict`,
   `knowledge.get_required_documents`), возвращающие структурированный
   `EvidencePack` с обязательными полями пробелов/противоречий, не
   только результатов.

5. **Проектные знания проходят Promotion Gate.** Наблюдение одного
   workspace не становится платформенной сущностью автоматически —
   ни по количеству подтверждений, ни по уверенности модели, ни по
   ответу LLM. Обязательная последовательность состояний: `кандидат →
   обезличен → доказательства_подтверждены → применимость_определена →
   regression_протестирован → approved/rejected → опубликован`, с
   решающими переходами (`approved`/`rejected`, определение области
   применимости), выполняемыми исключительно уполномоченным человеком.

### Принятые retention-ограничения решения

Нормативные формулировки и реквизиты принятия находятся только в
`LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md` §19. Владелец продукта Олег
Щербаков 2026-08-21 принял:

- RD-01/B — полный versioned `RetentionProfile` для каждого промышленного
  workspace и каждого data class; отсутствие значения fail-closed;
- RD-02/C — portable logical archive как product evidence и независимый
  physical backup/PITR только для recovery;
- RD-03/A — после verified reset только content-free audit и
  `DestructionAttestation`; project content не переживает reset;
- RD-04/C — versioned Basis Registry, evidence, полный deletion plan,
  legal-hold check и независимые полномочия запроса/подтверждения;
- RD-05/B — только минимальный Evidence Capsule для approved promoted
  knowledge, без live workspace link и project memory.

Эти ограничения являются обязательной границей решений 2 и 5. В частности,
cross-workspace physical deduplication project blobs в промышленном v0.1
запрещена, а `PromotionDecision` переживает reset только в составе разрешённого
Evidence Capsule. Архитектурная связка knowledge platform, workspace
isolation и Promotion Gate принята 2026-08-22. Это не задаёт календарные
retention values или конкретные Basis Registry entries.

## Последствия

- Персистентность (PostgreSQL-схема, миграции, RLS-политики) реализуется
  как минимум с двумя схемами верхнего уровня (`platform`/`workspace`) и
  обязательным `workspace_id` на каждой workspace-таблице без исключений
  — это ограничение на дизайн будущих миграций, принимаемое заранее, до
  их написания.
- Ни одна функция очистки/сброса workspace не может полагаться на
  ручной, поколоночный порядок удаления в прикладном коде — обязательна
  структурная граница (каскад на уровне схемы/RLS) и исполняемая
  пост-проверка отсутствия строк с данным `workspace_id`
  (`DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md` §4.4).
- Смена embedding-модели, добавление графовой СУБД (Neo4j) или замена
  reranker'а не требуют миграции канонических таблиц — только создания
  новой версии производного индекса и последующего переключения.
- Любой инструмент, предложенный для доступа LLM к знаниям сверх шести
  перечисленных, обязан пройти тот же контракт (`workspace_id`, явные
  `gaps`/`error`, отсутствие произвольного SQL-параметра) — расширение
  набора инструментов не требует нового ADR, но обязано соответствовать
  этому решению.
- Ни одно платформенное правило, классификатор или НТД-знание не может
  быть создано напрямую из пилотных данных (включая ТМ-35) без прохождения
  Promotion Gate — в том числе результаты, уже полученные и опубликованные
  в `docs/pilots/`, остаются workspace-наблюдениями пилота, не
  платформенным знанием, пока не пройдут раздел 10
  `DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md`.
- Retention-решения RD-01…RD-05 приняты владельцем продукта и обязательны для
  будущих persistence contracts. Конкретные календарные сроки и basis codes
  остаются версионированными policy data с provenance, а не defaults ADR.
- Остальные открытые продуктовые решения — организационная модель
  параллельных workspace одного ОКС и состав роли «нормативный эксперт» — не
  разрешены этим ADR и остаются в
  `DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md` §11.
