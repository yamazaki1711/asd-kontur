# ADR-0009: Постоянная платформа НТД и workspace-scope регламента заказчика

- **Статус:** Accepted
- **Дата:** 2026-08-22
- **Владелец решения:** Олег Щербаков
- **Источник authority:** явное решение владельца от 2026-08-22 о смысле
  объектной обезличенности, постоянной базе НТД и scope регламента заказчика
- **Развивает:** ADR-0005; при конфликте заменяет прежние трактовки
  customer layer как автоматически переносимой между ОКС памяти

## Контекст

Объектная независимость АСД-КОНТУР ошибочно могла читаться как обязанность
возвращать весь комплекс к пустой базе между ОКС. Это уничтожило бы
нормативную оснастку и смешало бы две разные операции: очистку данных
конкретного ОКС и сохранение постоянного платформенного знания.

Одновременно историческая модель `mac_asd` помещала разобранный регламент
заказчика в устойчивый customer layer. В целевой архитектуре регламент,
полученный для конкретного ОКС, не получает автоматически применимость к
другому workspace даже того же заказчика.

## Решение

1. АСД-КОНТУР обезличен относительно последовательно обрабатываемого ОКС, но
   имеет постоянную platform memory.
2. Platform memory сохраняет официальные НТД, все известные редакции,
   структурные единицы и source-backed assertions, утверждённые
   `RuleVersion`/`RuleSetVersion`, универсальные классификаторы, официальные
   типовые формы и `TemplateVersion`, схемы полей, parsers/renderers,
   Knowledge Gateway и знания, прошедшие Promotion Gate.
3. Новая редакция НТД создаёт новую `NormativeEdition`; прежняя не удаляется.
   Применимость определяется датой, scope и доказанным основанием.
4. ПД/РД, договор, приложения и регламент заказчика являются workspace
   content конкретного ОКС. Они не переживают verified reset как контекст
   следующего workspace.
5. Регламент заказчика может уточнять организационную процедуру и оформление
   в пределах собственной authority, но не отменяет и не заменяет применимую
   НТД.
6. Противоречие регламента и применимой НТД создаёт типизированный
   conflict/blocker с обеими версиями источников и требует предусмотренного
   решения; автоматический приоритет регламента запрещён.
7. Organization overlay допустим только как отдельно утверждённая,
   версионированная organization-scoped конфигурация. Загрузка регламента в
   workspace не создаёт overlay и не является Promotion Gate.
8. Archive/reset уничтожает либо выводит из активного контура workspace
   content по `RetentionProfile`, не повреждая platform memory.

## Инварианты

- `NormativeDocument`, `NormativeEdition`, официальные source bytes и
  platform templates не имеют `workspace_id`.
- Регламент заказчика всегда имеет `workspace_id`, source version и locator.
- Ни один retrieval index не меняет scope источника.
- Перенос требования регламента в organization/platform scope требует нового
  артефакта, provenance, проверки обезличивания, applicability и authority.
- Новый workspace не получает контекст старого регламента по совпадению
  организации, имени файла или embedding similarity.

## Последствия и migration path

- Исторический `cust.` layer `mac_asd` рассматривается только как источник
  идей overlays; его записи нельзя переносить без повторной классификации.
- Старые поля `customer_policy`/`client_regulation`, не имеющие
  `workspace_id`, при будущем импорте помещаются в quarantine до установления
  источника и scope.
- Workspace reset должен иметь leak tests для текста, embeddings, graph,
  caches, generated documents и provider residues регламента.
- Решение должно быть отражено в Logical Data Model, но не создаёт его в
  рамках настоящего ADR.

## Отклонённые альтернативы

- пустая platform memory после каждого ОКС;
- копирование применимой НТД в workspace как единственный канон;
- автоматическое сохранение каждого регламента в customer/platform memory;
- автоматический приоритет регламента над НТД;
- удаление старой редакции НТД при публикации новой.

## Acceptance tests

1. Reset workspace удаляет регламент и его projections, но сохраняет НТД,
   RuleVersion и официальные TemplateVersion.
2. Второй workspace той же организации не получает первый регламент без
   явного versioned overlay decision.
3. Resolver выбирает edition по дате/scope и сохраняет историю supersession.
4. Конфликт регламента и НТД блокирует зависимое действие и выдаёт обе
   provenance chains.
5. Cross-workspace retrieval тест не возвращает фрагменты старого регламента.

## Связанные документы

- `../ARCHITECTURE_BLUEPRINT_v0.1.md`;
- `../DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md`;
- `../KNOWLEDGE_AND_MEMORY_ARCHITECTURE_v0.1.md`;
- `../INFORMATION_ARCHITECTURE_v0.1.md`;
- `../LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md`;
- `../ID_GENERATION_AND_TEMPLATE_PLATFORM_SPECIFICATION_v0.1.md`.
