# ADR-0011: Постоянный model-independent ID Practice Intelligence

- **Статус:** Accepted
- **Дата:** 2026-08-25
- **Владелец решения:** Олег Щербаков
- **Источник authority:** текущее явное сообщение владельца проекта от
  2026-08-25

## Решение владельца

> АСД-КОНТУР обладает собственной постоянной, версионируемой и независимой от
> конкретной VLM памятью. VLM является заменяемым вычислительным механизмом, а
> знания принадлежат платформе. «Пособие по ИД» принимается первым и основным
> пластом постоянной контекстной памяти АСД-КОНТУР по исполнительной
> документации. Исходное пособие, его редакции, доказательная структура и
> сформированный ID Practice Intelligence сохраняются в platform memory на
> протяжении всего жизненного цикла АСД-КОНТУР, не удаляются при reset,
> archive, purge или destroy отдельных workspace ОКС и используются как
> основная методическая призма при обработке документов всех ОКС. Пособие
> объясняет, как формировать, заполнять, проверять и комплектовать ИД, на что
> обращать внимание, почему применяются определённые действия и какие варианты
> практики допустимы. Оно не подменяет нормативную силу НТД: НТД определяет
> обязательные требования, а пособие — методику профессионального применения.

## Контекст

Pass A/B, qualification и model receipts являются средствами доказательного
построения памяти, а не продуктовой целью, benchmark corpus или промышленным
испытанием Qwen. Публикация набора независимых retrieval chunks также
недостаточна: платформа должна построить типизированный практический интеллект,
который одинаково доступен любой разрешённой VLM и всем workspace через один
Knowledge Gateway.

## Архитектурное решение

1. Каноническая цель KG-ID-01:

   `Пособие → verified source knowledge → ID Practice Intelligence →`
   `Context Assembly → Knowledge Gateway → любая VLM → обработка ИД любого ОКС`.

2. Вводится отдельный authority layer `methodological_practice`. Он объясняет
   профессиональную практику, но не является `normative_authority`, фактом ОКС
   или active `RuleVersion`.
3. Память разделена на пять уровней:

   - **Permanent Source Layer** — исходный PDF в platform object plane,
     immutable `SourceArtifact`/`SourceVersion`, SHA-256, edition, metadata и
     object receipt;
   - **Canonical Practice Intelligence** — versioned principles, workflow,
     form/field guidance, attention points, allowed variants, rationale,
     failures, dependencies, visual examples, checklists и playbooks;
   - **Deterministic Operationalization** — applicability predicates,
     completeness logic, checklists и `RuleCandidate`; active `RuleVersion`
     возникает только через Rule Gate;
   - **Rebuildable Retrieval Plane** — exact, FTS, vector, sparse и typed graph
     projections; их удаление не изменяет canonical knowledge;
   - **Runtime Context** — заново собранный `IDPracticeContextPack` для точной
     команды, документа и workspace; он не является источником истины.

4. Минимальная canonical model включает `PracticeGuide`,
   `PracticeGuideEdition`, `PracticePrinciple`, `IDWorkflowStep`,
   `DocumentFormGuidance`, `FormFieldGuidance`, `CompletionInstruction`,
   `AttentionPoint`, `AllowedPracticeVariant`, `PracticeRationale`,
   `CommonFailurePattern`, `VerificationChecklist`, `CompletenessGuidance`,
   `JournalSelectionGuidance`, `DocumentDependencyGuidance`,
   `SignerRoleGuidance`, `VisualCompletionExample`, `PracticePlaybook`,
   `GuidanceConflict`, `GuidanceGap`, `ContextAssemblyPolicy` и
   `IDPracticeContextPack`.
5. Каждая canonical unit имеет stable identity и immutable version, exact
   `SourceVersion`/page/region, fragment digest, applicability, связи с видами
   работ/документами/формами/полями, printed NTD references, verification,
   uncertainty/conflict и provenance модели/validators.
6. Printed ссылка на СП/ГОСТ/приказ сначала является
   `NormativeReferenceCandidate`. Связь с `NormativeEdition` допустима только
   через exact resolver; fuzzy/default edition запрещена.
7. Для любой ID-related операции deterministic Context Assembly обязательно
   до вызова VLM. Модель не выбирает, обращаться ли к пособию. Полные 425
   страниц в prompt не загружаются: policy выбирает релевантные units по типу
   документа, форме/полю, виду работ, разделу РД, этапу, контрольной операции,
   evidence requirement, комплектованию, режиму и задаче ID Generator.
8. Gateway возвращает `IDPracticeContextPack` и точные citations. Отсутствие,
   конфликт, другая редакция и непроверенное знание дают соответственно
   `knowledge_incomplete`, `guidance_normative_conflict`, `edition_mismatch`
   или отказ передавать unit как verified. Silent empty retrieval запрещён.
9. Существенный ID-ответ разделяет: обязательное требование НТД,
   методическую рекомендацию пособия, факты конкретного ОКС и отсутствующие
   сведения. VLM не получает прямой SQL или mutation authority.
10. Canonical memory независима от Qwen, MLX, provider, embeddings и graph.
    Смена execution profile не меняет source/version identities, canonical
    semantic fingerprints или EvidencePack при одинаковом запросе и policy.
11. Retention class источника и canonical intelligence —
    `permanent_platform_core`. Workspace `RetentionProfile`, reset, archive,
    purge и destroy не могут включать этот слой в deletion plan. Удаление
    разрешается только при decommission всей платформы по отдельному owner
    decision.
12. Backup manifest содержит exact SourceVersion, object SHA-256, canonical
    knowledge versions, semantic fingerprints и `ContextAssemblyPolicy`.
    Restore проверяет byte integrity и semantic fingerprints; retrieval
    projections после этого пересобираются. Raw prompts, responses и renders
    не получают permanent retention автоматически.
13. Новая редакция пособия создаёт новую identity и новые immutable versions.
    Прежняя редакция не перезаписывается, остаётся доступной для provenance;
    runtime обязан pin edition и возвращать `edition_mismatch` при конфликте.
14. При конфликте НТД имеет нормативный приоритет, но совет пособия не
    уничтожается: создаётся `GuidanceConflict`, оба слоя показываются раздельно,
    а неразрешённая практическая guidance исключается из authoritative context.
15. При недоступной, повреждённой или неполной памяти ID-related операция
    fail-closed возвращает typed gap/degraded status. Она не подменяет память
    общей модельной догадкой и не создаёт empty success.

## Последствия для режимов и ID Generator

- **Tender:** context по договорным требованиям к ИД, журналам, evidence и
  процедурам сдачи с явным разделением НТД, практики и условий закупки.
- **Support:** своевременное формирование, заполнение, проверка и комплектование
  ИД по workflow, attention points и dependencies.
- **Audit:** common failures, field/form checks, completeness и verification
  checklists с exact evidence.
- **Restoration:** recovery playbooks и допустимые варианты без выдумывания
  отсутствующих фактов или доказательств.
- **ID Generator:** field-level instructions, источники значений, проверки,
  signer guidance и visual-example locators до generation/finalization.

Память доступна workspace read-only через Gateway. Общий platform context не
создаёт доступа к данным другого workspace.

## Acceptance

Решение доказано только если тесты подтверждают: survival после reset/destroy;
одинаковые platform versions для изолированных workspace; model/provider
independence; rebuild retrieval projections; обязательность Context Assembly;
typed gaps/conflicts/edition mismatch; сохранение старой edition; field-level,
Audit и Restoration scenarios; backup/restore byte и semantic integrity;
отсутствие PDF/extracted content в Git; `ProductReady=false` до общего gate.

## Отклонённые альтернативы

- knowledge в весах или session context конкретной VLM;
- обычный RAG-document или набор независимых chunks;
- повторное построение памяти при смене provider/model;
- перенос practical guidance в НТД или автоматическое создание RuleVersion;
- удаление platform practice memory вместе с workspace;
- silent empty retrieval или модельный fallback при недоступной памяти.

## Связанные документы

- `../KNOWLEDGE_AND_MEMORY_ARCHITECTURE_v0.1.md`;
- `../INFORMATION_ARCHITECTURE_v0.1.md`;
- `../LOGICAL_DATA_MODEL_v0.1.md`;
- `../LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md`;
- `../AI_VLM_EXECUTION_AND_VERIFICATION_HARNESS_SPECIFICATION_v0.1.md`;
- `../ID_GENERATION_AND_TEMPLATE_PLATFORM_SPECIFICATION_v0.1.md`;
- `../IMPLEMENTATION_PLAN_v0.1.md`;
- `../../implementation/KG_ID_PRACTICE_GUIDE_INGESTION_v0.1.md`.
