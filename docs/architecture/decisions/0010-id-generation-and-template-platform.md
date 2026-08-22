# ADR-0010: ID Generation & Template Platform как capability общего ядра

- **Статус:** Accepted
- **Дата:** 2026-08-22
- **Владелец решения:** Олег Щербаков
- **Источник authority:** явное решение владельца от 2026-08-22 о генераторе
  исполнительной документации как одной из ключевых capabilities комплекса

## Контекст

Архитектура ранее фиксировала проекты ИД и исполнительные схемы как результаты,
но не определяла общий bounded context выбора, версионирования, заполнения,
проверки и финализации шаблонов DOCX/XLSX/PDF. Наследие `mac_asd` содержит
развитые, но разобщённые генераторы, реестры и шаблоны. Наличие сохранённого
файла или заявления о количестве шаблонов не доказывает print-ready результат.

## Решение

1. `ID Generation & Template Platform` является обязательной capability
   единого общего ядра АСД-КОНТУР, а не pilot/support-only модулем.
2. Capability используется всеми режимами: Tender прогнозирует формы и
   evidence; Support формирует текущую ИД; Audit проверяет существующую ИД;
   Restoration создаёт только evidence-grounded candidates.
3. Канонический процесс:

   `RequiredDocumentType → applicability → TemplateVersion → binding plan →`
   `confirmed facts/evidence → deterministic fill → structural/content/layout`
   `validation → GeneratedDocumentCandidate → professional authority →`
   `FinalizedDocument → export/print`.
4. Официальный универсальный шаблон, его неизменяемый binary, field schema и
   renderer profile являются platform memory. Заполненный документ и значения
   его полей являются workspace memory/result.
5. DOCX, XLSX, fillable PDF и non-fillable PDF имеют разные adapters и
   format-specific validation; общий semantic contract не стирает layout.
6. Каждое материальное заполненное поле имеет `EvidenceBinding`. Отсутствующий
   или конфликтующий факт создаёт gap/uncertainty и блокирует финализацию.
7. AI может предложить классификацию, mapping или текстовый Candidate, но не
   подтверждает факт, не назначает подписанта и не заполняет догадкой дату,
   объём, МТР, измерение, контроль или геометрию.
8. `GeneratedDocumentCandidate` не является `FinalizedDocument`.
   Финализация требует профессиональной authority и пройденных validators.
9. Успешная запись файла не является print-ready acceptance. Обязательны
   render/layout, pagination, clipping, fonts, tables/formulas/print-area и
   deterministic fingerprint checks.
10. Legacy templates проходят recovery inventory, source-authority check,
    parsing, mapping, regression и approval; обнаружение в `mac_asd` не делает
    шаблон active.

## Последствия и migration path

- До Logical Data Model вводится архитектурный prerequisite `G-00-ID`:
  спецификация capability, ADR и legacy inventory должны быть Accepted.
- После принятия этих артефактов `G-00-ID` закрывается и G-00 может оставаться
  пройденным; отсутствие recovered binaries остаётся blocker соответствующего
  TemplateVersion, но не архитектурного baseline.
- Наследие разделяется на reusable algorithms, candidate templates,
  workspace-specific outputs и rejected unsafe assumptions.
- Contracts для generation/provider/storage/authorization входят в G-03;
  persistence начинается только после G-01…G-03.

## Отклонённые альтернативы

- отдельный генератор только АОСР;
- один универсальный механизм заполнения всех форматов;
- сохранение заполненного документа как новой platform TemplateVersion;
- генерация пустых обязательных facts моделью;
- финализация по признаку `file exists`;
- прямой доступ модели к SQL или template object storage.

## Acceptance tests

1. Одна и та же `TemplateVersion` детерминированно создаёт тот же fingerprint
   при одинаковых confirmed facts, rules и generation profile.
2. Каждое материальное поле разрешается в evidence locator либо явный gap.
3. DOCX, XLSX и оба PDF-пути имеют отдельные structural/layout tests.
4. Missing fact, ambiguous edition, unconfirmed signer/geometry и layout
   blocker останавливают generation/finalization fail-closed.
5. Golden render regression обнаруживает clipping, pagination, font, merged
   cell, formula и print-area regression.
6. Reset уничтожает workspace values/candidates/renders, сохраняя platform
   TemplateVersion и renderer/parser versions.

## Связанные документы

- `../ID_GENERATION_AND_TEMPLATE_PLATFORM_SPECIFICATION_v0.1.md`;
- `../ARCHITECTURE_BLUEPRINT_v0.1.md`;
- `../IMPLEMENTATION_PLAN_v0.1.md`;
- `../DETERMINISTIC_RULES_CATALOGUE_v0.1.md`;
- `../AUTHORIZATION_AND_AUDIT_MODEL_v0.1.md`.
