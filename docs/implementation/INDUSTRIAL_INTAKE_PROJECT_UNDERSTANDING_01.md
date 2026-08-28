# INDUSTRIAL-INTAKE-PROJECT-UNDERSTANDING-01

Статус записи: implementation acceptance, 2026-08-28. Эта запись дополняет, но не
переписывает прежние readiness decisions и immutable receipts.

## Что теперь умеет АСД-КОНТУР как продукт

Внутри выбранного режима и объекта пользователь может добавить отдельные файлы,
пакет, папку с сохранением относительных путей или ZIP-архив. До отправки видны состав,
число и общий объём выбранных файлов; ошибочно выбранный файл можно исключить.

После приёма АСД-КОНТУР показывает понятные состояния документов и устойчивых заданий,
обрабатывает пригодный текстовый слой раньше распознавания, изолирует повреждённый файл в
карантине и не теряет уже принятые bytes при сбое worker. Задание в очереди можно
приостановить, продолжить или отменить; для терминальной ошибки создаётся отдельная
прослеживаемая повторная попытка.

Действие `Сформировать модель объекта` создаёт версионируемые `ProjectDefinition`,
`ConstructionWorkPackage` и `WorkRequirementMatrix`. В одном разделе доступны общие
сведения, структура ОКС, работы и объёмы, материалы, пакеты работ, матрица требований,
расхождения и пробелы. Кандидат можно подтвердить, отклонить или исправить с причиной;
предыдущий результат и исходный locator не переписываются. Одна модель используется во
всех четырёх режимах одного workspace.

## Capability denominator

Exact denominator Contract Pack v2.5: `17 intake.* + 12 project-understanding.* = 29`.

- `CAPABILITY_READY`: batch upload, streamed hashing, MIME/content validation,
  deduplication, PDF/page inventory, crash recovery — 6 из 17 intake capabilities;
- `PARTIAL`: recursive folder admission, ZIP archive handling, native extraction, OCR,
  backpressure, quarantine и профили 1k/5k/10k — 9 intake capabilities;
- `FOUNDATION_ONLY`: VLM routing и page/region sharding — 2 intake capabilities;
- все 12 `project-understanding.*` переведены из `CONTRACT_ONLY`/`FOUNDATION_ONLY` в
  `PARTIAL` только на основании обезличенного representative corpus.

Итоговая effective distribution всего product denominator 143 после additive delta:
`CAPABILITY_READY=16`, `PARTIAL=45`, `FOUNDATION_ONLY=36`, `CONTRACT_ONLY=39`,
`NOT_IMPLEMENTED=7`.

## Приём и устойчивое выполнение

Миграция `0028_industrial_intake` добавляет append-only archive-member lineage,
candidate review decisions и job control decisions. Она также устраняет schema defect:
typed admission outcome `quarantined` теперь допустим в canonical processing state.

Безопасное раскрытие ZIP ограничивает число, общий размер, compression ratio, traversal,
symlinks, encrypted members и повторные пути. ZIP-контейнер сохраняется вместе с
отдельными SourceVersion его членов. DOCX/XLSX не подменяются generic ZIP.

Durable control semantics:

- `queued → paused → queued` имеет immutable control receipt;
- cancel для `queued` и `paused` создаёт terminal receipt без semantic effect;
- manual retry не переписывает terminal job, а создаёт derived job с exact input digest;
- reset coordinator удаляет archive/review/control relations до их parent relations;
- другой workspace и platform knowledge остаются неизменными.

## Квалифицированный synthetic corpus

Corpus `industrial-intake-synthetic@1.0.0` не содержит данных реального ОКС.
Logical fingerprint:
`sha256:6f40a9a5a0d5a280c771af2178bf8e0b466e21a00405803a27690048844c1154`.

13 выбранных файлов включают ПЗ, ПД, mixed РД, договор, регламент заказчика, ВОР,
смету, спецификацию материалов, DOCX/XLSX/PDF, ZIP, exact-byte copies, неверное
расширение, неподдерживаемый IFC и намеренно повреждённый PDF.

Фактический PostgreSQL acceptance:

- selected 13; registered 14 (ZIP container + 2 members, 1 unsupported rejected);
- duplicate replay 1; quarantine 1;
- page routing: born-digital native 7, table-heavy native 4, raster recovery 2;
- jobs: 196 succeeded, 2 original typed failures, 26 reconciliation-required; the
  deliberately repeated failed job produced a third immutable typed failure;
- project fields 8; work candidates 5; quantity candidates 5; materials 3;
- work packages 3; matrix rows 3; reconciliation defects 5;
- exact source locator opens through the existing viewer;
- one review decision was accepted, revised model remained reproducible;
- populated workspace reset and cross-workspace isolation passed.
- deletion and rebuild of `projection.project_understanding_entries` reproduced the same
  semantic fingerprint from canonical ProjectDefinition/packages/matrix.

Control denominator deliberately includes 2 object parts, 2 zones, 2 levels, 2 work
fronts, 3 work types, 3 quantities, 3 materials, 2 dependencies, 2 VOR/estimate
mismatches, missing confirmed geometry and missing material-quality documents. Extracted
candidate counts can be larger because the same source statement may occur in several
documents; this is not silently collapsed into a confirmed fact.

## Scale qualification

Scale profiles exercise admission, streamed hashing, registry, queue creation,
backpressure and restart only. They do not send 10,000 files to OCR/VLM.

| Files | Accepted | Jobs | Admission, s | Peak RSS | Restart result |
|---:|---:|---:|---:|---:|---|
| 1,000 | 1,000 | 17,000 | 16.509071 | 181,813,248 B | 2 succeeded; 16,998 queued |
| 5,000 | 5,000 | 85,000 | 98.261001 | 181,731,328 B | 2 succeeded; 84,998 queued |
| 10,000 | 10,000 | 170,000 | 146.161072 | 181,616,640 B | 2 succeeded; 169,998 queued |

Во всех трёх профилях registry identity count совпал с denominator, rejected=0.
Threshold status остаётся `UNSET_MEASURED_ONLY`; readiness на основании измерения не
повышалась.

## Project Understanding и review

Assembly учитывает только exact SourceVersion/locator candidates и latest append-only
review decision. `confirmed` сохраняет исходное значение, `rejected` исключает его из
новой материализации, `corrected` создаёт новую materialization input с исходным и новым
значением. Candidate-specific review не зависит от несвязанных страниц документа.

Нормативный слой остаётся раздельным: матрица показывает только доступный verified
subset; отсутствие exact edition/rule остаётся gap. Practice guidance не превращается в
нормативную обязанность.

## API и Product Application

Добавлены typed commands для формирования модели, review, pause/resume/manual retry.
Frontend сохраняет mode-first flow и предоставляет:

- `Добавить исходные документы` как первое действие режима;
- drag/drop, multi-file, folder and ZIP intake без manifest/UUID;
- русские состояния intake/jobs без provider/model codes как основного текста;
- семь страниц модели объекта и переход к точному фрагменту источника;
- responsive layout без отдельного frontend или отдельной intake memory.

OpenAPI и generated TypeScript client version-pinned и воспроизводимы.

## Quality gate до deployment

- clean migration upgrade/downgrade/upgrade: PASS, head `0028_industrial_intake`;
- PostgreSQL/RLS/reset/projection suite: `491 passed`;
- Ruff format/check: PASS; strict mypy (153 source files): PASS; `uv lock --check`: PASS;
- frontend format/typecheck/lint: PASS; Vitest `3 passed`; production build: PASS;
- local Playwright: `6 passed`, `2` explicitly skipped NTD/Support canaries outside их
  materialization profile;
- OpenAPI digest `sha256:ccfa46f412e553014e1f84e19fdefd6fde69ffb96b590ac5c2f1334b9ed1bfca`;
- generated client digest
  `sha256:482591325ad6b6b8d73ec644fd2c1c8dd83943146bb865f88846cb56bc6f6365`;
- повторная генерация обоих artifacts дала те же digests; `git diff --check`: PASS.

## Оставшиеся пробелы

- производственные thresholds 1k/5k/10k не утверждены;
- folder admission не квалифицирован во всех браузерах;
- поддержан только ZIP, не весь archive denominator;
- OCR profile доказан на representative corpus, не на полном промышленном denominator;
- general VLM routing и region sharding остаются `FOUNDATION_ONLY`;
- CAD, специализированные сметные форматы, confirmed geometry и material quality docs
  отсутствуют;
- work/material catalog mapping и unit-conversion denominator неполны;
- corpus synthetic: профессиональная приёмка на реальном ОКС не выполнялась.

`TrialReady=false`, `OKSReady=false`, `ProductReady=false`.
