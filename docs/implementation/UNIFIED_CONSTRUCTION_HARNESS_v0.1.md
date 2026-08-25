# UNIFIED-HARNESS-01 — единое детерминированное ядро строительства

> **Superseding readiness notice:** the recorded PASS is a bounded backend
> implementation result. It does not provide a UI/application process and does
> not make Tender, Support, Audit or Restoration `MODE_READY`. See
> [ADR-0013](../architecture/decisions/0013-platform-kernel-to-product-application.md).

Статус: **PASS (bounded implementation)**

Дата: 2026-08-25

ProductReady: `false`

## Назначение

`UNIFIED-HARNESS-01` соединяет workspace-факты конкретного ОКС и существующую
platform memory в один воспроизводимый процесс:

`ПД/РД → ProjectDefinition → ConstructionWorkPackage → WorkRequirementMatrix → Tender / Support / Audit / Restoration`.

Это orchestration/process layer поверх существующих G-05, KG-ID, NTD и WP-11,
а не новая база знаний. Пять входных слоёв сохраняют разную authority:

1. `workspace_fact` — проверенные сведения ПД/РД, сметы/ВОР и договора ОКС;
2. `methodological_practice` — Practice Intelligence и playbooks из пособия;
3. `normative_authority` — только verified exact NormativeEdition/Provision;
4. `deterministic_rule` — только активные RuleVersion из exact RuleSetVersion;
5. `customer_regulation_addition` — workspace-only дополнение, не ослабляющее минимум.

Historical `KG-ID-01 = PARTIAL` и `NTD-SEED-01 = PARTIAL` не изменяются.
При нынешних 25 `official_access_blocked` Harness сохраняет work packages и
выполняет ненормативные вычисления, но возвращает `knowledge_gap`, не публикует
нормативное подтверждение и не создаёт RuleVersion.

## Доменная модель

- `ProjectCharacteristicCandidate` и `WorkPackageCandidate` являются AI/native
  extraction candidates. В verified значения они переходят только после
  детерминированной проверки с exact SourceVersion/locator/evidence.
- `ProjectDefinition` объединяет назначение, класс, характеристики и source-pinned
  work packages одного workspace. Запрашивать повторно сведения, уже извлечённые
  из ПЗ, не требуется.
- `ConstructionWorkPackage` хранит объёмы, материалы, зависимости и проектные
  ссылки на НТД.
- `WorkRequirementMatrix` — одна immutable версия требований для всех четырёх
  mode views.
- `ConstructionHarnessContextPack` детерминированно объединяет workspace facts,
  Practice Intelligence, verified NTD, активные rules, customer additions и gaps.
- `KnowledgeConsistencyDefect` блокирует затронутый RuleVersion; дефект не
  превращается в штатный выбор между пособием и НТД.

`DrawingIntelligenceReference` является только будущим интеграционным контрактом.
CAD/VLM-анализ чертежей, САПР + ИИ и Drawing Intelligence в этот этап не входят.

## Обязательный AI boundary

`ConstructionAIContextGate` отклоняет существенную AI/VLM-операцию без базового
`ConstructionHarnessContextPack`. Модель получает раздельные authority layers и
может делать дополнительные типизированные запросы через общий Knowledge Gateway:

- `knowledge.get_construction_harness_context`;
- `knowledge.trace_work_requirement`;
- существующие practice и NTD tools.

Прямой SQL отсутствует. Fingerprint ContextPack не включает model/provider, поэтому
локальный или внешний Qwen получает одинаковую canonical evidence composition.

## Четыре mode views

Один multi-work contract fixture содержит земляные работы, железобетонную
конструкцию и монтаж трубопровода.

- Tender сравнивает ПД/РД со сметой/ВОР и формирует вывод о согласовании срока и
  стоимости только при детерминированном quantity/material delta с evidence.
- Support выдаёт контроль, evidence, требуемую ИД и blockers предъявления.
- Audit сопоставляет expected/actual комплект: present, missing, incomplete,
  invalid, wrong edition/form, duplicate и evidence gap.
- Restoration различает recoverable и non-recoverable документы по сохранившимся
  исходным фактам и всегда запрещает фабрикацию.

## Persistence и lifecycle

Migration `0017_unified_harness` добавляет immutable workspace versions для
ProjectDefinition, candidates/verified characteristics, work packages, matrix,
customer additions, ContextPack, consistency defects, mode views и backup
manifest. Все таблицы имеют composite workspace scope, RLS/default-deny и входят
в exact PostgreSQL lifecycle inventory/reset allowlist.

Practice Intelligence, NTD и Rule Registry остаются в `platform` schema и поэтому
не удаляются вместе с workspace. `projection.construction_harness_matrix_entries`
является rebuildable projection; canonical fingerprints находятся в workspace
versions и backup manifest.

## Contract Pack и acceptance

Additive Contract Pack v1.8 фиксирует:

- минимум три связанных work packages в cross-mode fixture;
- один matrix fingerprint во всех mode views;
- обязательный базовый evidence pack;
- `automatic_rule_promotion=false`;
- additive-only customer overlay;
- exact versioned Knowledge Gateway requests.

Локальный acceptance на PostgreSQL 17 завершён: `350 passed`, без skips. Проверены
Contract Pack v1.8, RLS/default-deny, cross-workspace `no_result`, clean
downgrade/upgrade, lifecycle reset, semantic backup verification и physical
projection delete/rebuild с неизменным fingerprint. Ruff format/lint, strict mypy,
`uv lock --check`, whitespace и forbidden-artifact/secret scans прошли. Canonical
GitHub PR/CI и post-merge main evidence приводятся в итоговом отчёте задачи.

## Отложенный технический долг

- Уже распарсенный на `king25` перечень видов работ подлежит отдельному будущему
  evidence recovery. Он не исследован, не скопирован и не блокирует Harness.
- Полный CAD/VLM Drawing Intelligence и интеграция САПР + ИИ требуют отдельного
  owner-approved этапа.
- Official NTD acquisition остаётся отдельным blocked процессом; сторонние тексты
  в Harness не подставляются.
