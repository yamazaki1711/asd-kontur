# Legacy pdfpipeline / Левашово: audit experience v0.1

- **Статус:** `CORRECTED; accessible evidence verified; volume coverage PARTIAL`
- **Дата:** 2026-08-23
- **Владелец контекста:** Олег Щербаков
- **Назначение:** восстановить практический опыт массовой обработки растровых
  PDF и уточнить DoR/acceptance WP-14 без переноса project-specific решений.
- **Граница:** в ходе исследования не выполнялись API-вызовы Polza.ai,
  inference, изменение удалённых файлов, обработка PDF, реализация WP-14,
  DDL/ORM/migrations или production operations.

## 1. Правила доказательности

В отчёте используются четыре метки:

- **ПРОВЕРЕНО** — подтверждено файлами, кодом, SQL, Git metadata либо
  согласованными независимыми отчётами на обследованных hosts;
- **СЛОВА ВЛАДЕЛЬЦА** — фактический контекст, сообщённый Олегом Щербаковым,
  но не полностью подтверждённый найденными цифровыми материалами;
- **ВЫВОД** — инженерная интерпретация проверенных наблюдений;
- **НЕ ПОДТВЕРЖДЕНО** — искомое утверждение или сокращение не найдено либо
  доступ к источнику отсутствовал.

Legacy evidence не получает нормативного, юридического или архитектурного
приоритета автоматически. Путь, имя файла, число совпадений, confidence и
успешный ответ модели не являются достаточным доказательством доменного факта.

## 2. Correction после PR #11

PR #11 нашёл и скопировал ключевое ТЗ, но отчёт не содержал per-file
доказательства последовательного чтения до EOF. Формулировка о 42
«семантически изученных» Markdown поэтому была шире доказанного. После вопроса
владельца выполнено полное перечитывание ключевого ТЗ и всех отобранных
high-relevance файлов; отдельно повторён inventory block devices.

Исправление не скрывает две границы:

1. machine content scan означает поиск/индексацию, а не полное чтение каждого
   Markdown;
2. шесть ранее пропущенных пользовательских/рабочих NTFS-разделов остаются
   недоступными: read-only `udisksctl` требует интерактивного polkit действия
   владельца. Они не считаются searched.

### 2.1. Coverage физических и логических томов

| Host / device | Discovered | Mounted/readable | Searched | Inaccessible / reason | Markdown | Relevant | Fully read |
|---|---:|---:|---:|---|---:|---:|---:|
| `king25 /dev/nvme0n1p6` (`/`) | yes | yes | yes | no | 389 | 8 paths | 8 paths |
| `king25 /dev/sda2` (NTFS, 223 GiB) | yes | no | no | interactive polkit required for read-only mount | unknown | unknown | 0 |
| `king25 /dev/sdb1` (NTFS, 931.5 GiB) | yes | no | no | interactive polkit required for read-only mount | unknown | unknown | 0 |
| `king25 /dev/sdc5` (`931GB`, NTFS, 651.2 GiB) | yes | no | no | interactive polkit required for read-only mount | unknown | unknown | 0 |
| `king25 /dev/sdc6` (`WIN10`, NTFS, 78.1 GiB) | yes | no | no | interactive polkit required for read-only mount | unknown | unknown | 0 |
| `king25 /dev/nvme0n1p4` (`System`, NTFS, 768.6 GiB) | yes | no | no | interactive polkit required for read-only mount | unknown | unknown | 0 |
| `king25` boot/recovery/reserved partitions | yes | not user data | no | filesystem/size classification; not a user/work volume | n/a | n/a | n/a |
| `ms-7e26 /dev/nvme0n1p5` (`/`) | yes | yes | yes | no | 14 131 current recount | 33 paths | 33 paths |
| `ms-7e26 /dev/sda1` (`Consultant`) | yes | yes, pre-existing | yes, read-only operations | no relevant evidence | 0 | 0 | 0 |
| `ms-7e26 /dev/nvme0n1p3` (NTFS, 441.6 GiB) | yes | no | no | interactive polkit required for read-only mount | unknown | unknown | 0 |
| `ms-7e26` EFI/MSR/recovery partitions | yes | not user data | no | filesystem/partition-type classification | n/a | n/a | n/a |

PR #11 зафиксировал 14 144 live Markdown на `ms-7e26`; correction recount дал
14 131. Это два dated inventory snapshots, а не основание молча выбрать большее
число. Один предыдущий scan имел transient `ENOENT` внутри `snap`. На доступном
perimeter также проверены 104 ZIP: 95 читаемых, 1 507 Markdown-members; девять
файлов с расширением ZIP не открылись как ZIP.

Ни один mount correction-аудитом не создан, поэтому размонтировать было нечего.
Том `Consultant` был смонтирован до исследования и оставлен как был. Полный
cross-volume coverage **не подтверждён** до подключения шести NTFS-разделов.

### 2.2. Coverage Markdown и полное чтение

В staging отобраны 42 remote Markdown paths. Они образуют 37 уникальных
SHA-256; пять paths — идентичные копии между hosts. Один уникальный файл про
другой ОКС (`reference_tm35_monitoring_site.md`) классифицирован как
object-specific outside WP-14 evidence и не использован. Все остальные 36
уникальных high-relevance Markdown полностью прочитаны до EOF; для каждого
записаны SHA-256, line count, диапазон чтения и извлечённое требование.

Git history проверен по всем 14 обнаруженным repositories на доступных томах.
Relevant deleted/renamed Markdown paths вошли в индекс; plugin/vendor noise не
считался project evidence. Эти числа описывают разные planes — live, archive,
Git object и staged copy — и не суммируются как уникальные документы.

## 3. Staging и manifest

Evidence staging создан вне Git repository и не удаляется автоматически:

```text
/Users/oleg/asd-wp14-pdfpipeline-evidence.tqMmOS
```

В нём находятся:

- `manifests/king25_markdown_live_paths.txt`;
- `manifests/ms-7e26_markdown_live_paths.txt`;
- `manifests/*_markdown_term_scan*.jsonl`;
- `manifests/*_zip_markdown_scan.jsonl`;
- `manifests/ms-7e26_MAC_ASD_git_markdown_history_paths.txt`;
- `manifests/ms-7e26_git_history_markdown_summary.tsv`;
- `manifests/evidence_manifest.json` и расширенный selected-evidence manifest;
- `manifests/correction_volume_coverage.tsv`;
- `manifests/correction_full_read_ledger.tsv`;
- `manifests/correction_traceability.tsv`;
- `manifests/tz_levashovo_v9_provenance.tsv`;
- выбранные Markdown, source, SQL и dashboard evidence.

Staging содержит project-specific evidence и **не предназначен для GitHub**.
В repository публикуются только обезличенные выводы. Manifest фиксирует host,
исходный путь/commit/archive member, SHA-256, размер, MIME, причину отбора,
evidence type, наличие данных ОКС и publishability.

### 3.1. Полное чтение `TZ_Levashovo_v9_0.md`

Три копии идентичны:

| Provenance | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| `king25:/home/oleg/Documents/asd-kontur/TZ_Levashovo_v9_0.md` | 1 165 | 205 795 | `76a1f0ac20633784f0f7a15fa1270c24edac884c14755e09c50ff237d9a90003` |
| `king25:/home/oleg/Downloads/archive-2026-08-23_02-52-34/archive/TZ_Levashovo_v9_0.md` | 1 165 | 205 795 | тот же |
| staged `king25/markdown/TZ_Levashovo_v9_0.md` | 1 165 | 205 795 | тот же |

Staged copy прочитана последовательно диапазонами `1–150`, `151–300`,
`301–450`, `451–600`, `601–750`, `751–825`, `826–900`, `901–1050` и
`1051–1165`. Проверены разделы: основания и принципы; роли; lifecycle
документа; packages/tomes; АОСР и схемы; incoming control; data model;
`Document`, file versions и status history; VK entities/metrics/stages;
functional requirements; `ActionRequest`; Customer/PTO dashboards; storage,
NFR, AI/raster processing, requirement matrix, generation/geometry; acceptance;
stop codes; physical packages; books/tomes; three-level registers/signatures;
electronic copies; Customer inspection; handover; post-signing stages.

### 3.2. Требования, пропущенные PR #11

Полное чтение выявило положения, которые ранее отсутствовали либо были отражены
только частично:

- package/folder не равен physical container; `Package`, `Volume/Book` и
  section — разные identities; document membership many-to-many и ordered;
- physical package readiness включает copies, registers, professional review,
  signers, return with comments, re-presentation, handover и acceptance;
- legacy stop-code фактически требовал action, addressee, affected object,
  deadline и подтверждение закрытия инициатором;
- формула ВК `(signed + unsigned) / total` даёт 100% при полном inventory даже
  при нуле подписанных и потому опасна;
- «последняя редакция побеждает» несовместима с authority, explicit
  supersession и conflict preservation;
- legacy confidence rule несовместим с `Provider result ≠ Candidate ≠
  validated Candidate ≠ Fact`;
- reclassification меняла document type, но не восстанавливала обязательные
  type-specific attributes;
- signature/seal detection не доказывает signer authority;
- handed over и accepted — разные состояния, как и found/classified/
  evidence-bound/packaged/signed.

### 3.3. Traceability correction

| Source / section | Extracted requirement | Report / WP-14 impact | Status |
|---|---|---|---|
| TZ lines 215–229, 323–385 | independent Package/Volume/Book and many-to-many membership | §§8, 10; third readiness delta | missing in PR #11; covered now |
| TZ lines 1059–1091 | stop-code becomes governed ActionRequest | §§10.3, 11 | missing; covered now |
| TZ lines 1093–1165 | physical assembly, copies, registers, signing, handover, acceptance | §§8, 10.2 | partially covered; completed now |
| TZ lines 282–300, 440–468 | incoming-control metric dimensions | §10.1 and impact assessment | dangerous legacy formula rejected |
| TZ version rule | no automatic last-write-wins | §11 | rejected with reason |
| TZ confidence rule | confidence only prioritizes queue | §§6.5, 11 | rejected with reason |
| `aosr_aorpi_reclassify_06082026.md` | type change leaves required attrs absent | §§6.5, 10.3 | covered now |
| `LESSONS_LEVASHOVO.md` | attempt before side effect; no empty success; generation markers | §§6.4, 11 | covered |
| `papka_200_*` | one file/container has many documents; duplicates not only byte-equal | §§6.1–6.2 | covered |
| `status_report_*`, `LEVASHOVO_16.md` | process `FINAL` can contradict receipts | §§6.4, 10 | covered |
| `delta_*`, `kaskad_privyazki_*` | search scope and missing relation are not negative proof | §§7–9 | covered |
| `Левашово_Паспорт_системы_v28.md` | useful flow/aging/stop projections; direct cell status is weak canon | §§10, 13 | modernized |
| object-specific stages/copy counts | configurable requirements, not platform constants | §12 | object-specific only |
| `reference_tm35_monitoring_site.md` | different ОКС and outside pdfpipeline/WP-14 scope | none | rejected from evidence set |

## 4. Индекс основного evidence

### 4.1. `king25`

- `/home/oleg/Documents/asd-kontur/papka_200_split_final_report.md` — Polza
  segmentation, sliding windows, partial failures, cost and duplicate attempts;
- `/home/oleg/Documents/asd-kontur/datamining_12_27.md` — массовый corpus,
  workers, OOM, promotion defects, dedup и VLM content checks;
- `/home/oleg/Documents/asd-kontur/papka_200_final_report.md` — container
  inventory и earlier classification;
- `/home/oleg/Documents/asd-kontur/status_report_2026-07-30.md` — status model;
- `/home/oleg/Documents/asd-kontur/TZ_Levashovo_v9_0.md` — object-specific
  workflow vocabulary; не является универсальной НТД.

### 4.2. `ms-7e26`: отчёты и operational evidence

- `/home/oleg/Desktop/Yandex/datamining.md`;
- `/home/oleg/Desktop/Yandex/datamining_12_27.md`;
- `/home/oleg/Desktop/Yandex/papka_200_split_final_report.md`;
- `/home/oleg/Desktop/Yandex/LEVASHOVO_11.md`;
- `/home/oleg/Desktop/Yandex/LEVASHOVO_15.md`;
- `/home/oleg/Desktop/Yandex/LEVASHOVO_16.md`;
- `/home/oleg/Desktop/Yandex/status_report_02082026.md`;
- `/home/oleg/Desktop/Yandex/raw_integrity_gap_06082026.md`;
- `/home/oleg/Desktop/Yandex/aosr_aorpi_reclassify_06082026.md`;
- `/home/oleg/Desktop/Yandex/delta_klassifikaciya_02082026.md`;
- `/home/oleg/Desktop/Yandex/matrica_delta_status_02082026.md`;
- `/home/oleg/Desktop/Yandex/kaskad_privyazki_22781_03082026.md`;
- `/home/oleg/.claude/projects/-home-oleg/memory/pdfpipe_server_reference.md`;
- `/home/oleg/Downloads/АСД/06_Система_и_разработка/Левашово_Паспорт_системы_v28.md`.

### 4.3. `ms-7e26`: код, SQL и dashboard

- `/home/oleg/Desktop/Yandex/ASD_KAT/ingest.py`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/worker.py`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/worker_lib.py`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/providers.py`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/container_worker.py`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/promote.py`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/001_core_schema.sql`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/003_source_wave_and_m2m.sql`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/004_segment_embeddings.sql`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/005_tier1_requisites.sql`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/006_promote_upsert.sql`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/007_embeddings_cascade.sql`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/isuid_app/main.py`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/isuid_app/db.py`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/isuid_app/templates/dashboard.html`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/isuid_app/templates/review.html`;
- `/home/oleg/Desktop/Yandex/ASD_KAT/isuid_app/templates/section.html`.

Полный индекс длиннее этого curated списка и хранится в staging. В отчёт не
включены пути к исходным PDF, object keys, персональные данные или содержимое
документов ОКС.

## 5. Практический контекст Левашово

**СЛОВА ВЛАДЕЛЬЦА:** подрядчик АИР Магистраль сократил собственный ПТО; для
входного контроля привлекались 12 студентов; процесс ВК был организован
ненадлежащим образом; позднее четыре аутсорсных ИП пытались сформировать ИД,
но ни одна папка не была подписана. Первичные документы, включая названные
владельцем АОПРИ, АВК и журналы верификации, отсутствовали либо находились в
ненадлежащем состоянии. КС и оплата оказались зависимы от доказательной
готовности ИД.

**ПРОВЕРЕНО частично:** evidence многократно фиксирует четыре ИП, corpus
«Студенты АИР», массовые gaps входного контроля, большое число неподписанных
актов и зависимость operational readiness от комплекта доказательств. Точное
число студентов и утверждение «ни одна папка не подписана» в найденных
Markdown независимо не подтверждены.

### 5.1. Уточнение АОПРИ / АОРПИ

**НЕ ПОДТВЕРЖДЕНО:** точное сокращение `АОПРИ` не найдено ни в одном
проиндексированном Markdown на обоих hosts.

**ПРОВЕРЕНО:** найденный термин — `АОРПИ`, раскрытый в
`/home/oleg/Desktop/Yandex/ASD_KAT/ШАГ_A_спецификация_реквизитов.md` как
«Акт о результатах проверки изделий (материалов)». В object-specific
материалах он связан с партией и supporting quality documents. Отчёт не
подменяет одно сокращение другим молча: WP-14 обязан использовать тип
документа из exact applicable rule/customer regulation и возвращать
`unknown_document_type`/`terminology_conflict`, если идентичность не доказана.

## 6. Как фактически работал pdfpipeline

### 6.1. Intake, identity и storage

**ПРОВЕРЕНО:** `ingest.py` регистрировал raw path/object, вычислял SHA-256,
записывал bytes в S3-compatible storage и создавал rows. Глобальный
`ON CONFLICT (sha256) DO NOTHING` использовал digest как дедупликационную
identity. `001_core_schema.sql` хранил `storage_key`, SHA-256, mutable status,
integer revision, AI confidence и loose source segment reference без FK.
Workspace/organization composite scope, RLS и lifecycle boundary отсутствовали.

**ПРОВЕРЕНО:** path не был устойчивой identity. Один физический container мог
включать много logical documents; после segmentation logical rows могли
ссылаться на общий container blob вместо собственных materialized bytes.
В одном измерении 527 digest groups / 11 847 document rows (58% corpus)
указывали на shared container content; для passport/certificate classes это
делало чтение по `storage_key` небезопасным.

**ВЫВОД:** legacy `Document` смешивал по меньшей мере четыре понятия:
ingested file/object, logical document occurrence, mutable classified record и
page segment. Модель `one row = one file` не выдерживала multi-document PDF,
версии и materialization lineage. SHA-256 доказывал byte equality, но ошибочно
участвовал в identity/authority semantics.

### 6.2. Raster/native route и rendering

**ПРОВЕРЕНО:** маршрутизация опиралась на file/media inspection и извлечённый
text; raster/multi-document containers направлялись в page rendering и VLM.
`container_worker.py` обрабатывал windows по 25 страниц с overlap 4,
стабилизировал границы и пытался заполнить gaps. Rendering был page-oriented,
но не имел полного immutable transform lineage современной модели.

**ПРОВЕРЕНО:** один документ мог быть случайно разделён на несколько logical
documents. На repeating passport pages pilot получил 44 VLM segments против
30 trusted boundaries; confidence оставался высоким. Позднее 23 invalid page
boundaries были найдены даже среди rows со статусом `verified_match`, включая
выход за фактическое число страниц.

### 6.3. Polza workflow

**ПРОВЕРЕНО по коду и отчётам, не прямым API-наблюдением:** provider adapter
использовал OpenAI-compatible chat-completions transport, base64 page images,
JSON response и bounded HTTP retries. `providers.py` пытался исправлять
некорректные escape-последовательности перед parsing. `worker_lib.py` задавал
prompt с object-specific labels и JSON example, а не полноценный persisted
Draft 2020-12 contract.

Для 34 multi-document containers зафиксировано 557 успешных calls, 82 errors
и заявленная стоимость 198,27 руб. Это историческая запись, а не актуальная
цена/условия provider. Ошибки включали `402 Payment Required`, timeout,
malformed JSON и transient PostgreSQL failures. Реальные credentials/endpoints
в GitHub не публикуются; фактические provider terms, region, retention и
no-training status **НЕ ПОДТВЕРЖДЕНЫ**.

### 6.4. Batch, retry, resume и unknown outcomes

**ПРОВЕРЕНО:** queue применяла `SKIP LOCKED`, mutable statuses и ограничение
attempts. Container windows выполнялись независимо, затем результаты
стягивались. Однако:

- один запуск мог повторно обработать уже completed acts: 73% attempts в одном
  прогоне были повторами из-за reset queue;
- duplicate first/second attempts оставили 187 duplicate rows;
- partial provider failure мог завершиться статусом ready;
- если все windows failed, `fill_gaps([], pages)` давал пустой результат, а act
  мог стать `ok_empty`;
- process counter/`STATE.md` мог говорить `FINAL`, когда поздние steps и report
  завершились ошибкой;
- 34 containers требовали ручного восстановления после provider failures;
- worker kill через `SIGKILL` оставил 122 temporary files / около 2,8 GB;
- чрезмерная concurrency привела к OOM; stable operation потребовала
  уменьшения worker count и явного resource control.

**ВЫВОД:** at-least-once execution без immutable item manifest, per-page
terminal outcome и authoritative reconciliation создавал дубликаты, пропуски и
ложный success. Resume должен строиться по immutable attempt/receipt state, а
не по массовому reset mutable status.

### 6.5. Validation и ручные исправления

**ПРОВЕРЕНО:** применялись JSON parsing, page coverage, classification,
confidence и поздние SQL/manual corrections. Массовая VLM-проверка показала:
66,4% match, 27,5% mismatch и 6,1% pending на 20 412 checked rows. В known
containers mismatch достигал 40,4%; random sample — 43,3%. Это показывало не
единичный сбой, а общий boundary/classification defect.

**ПРОВЕРЕНО:** 167 из 736 rows, маркированных как АОСР, были определены как
АОРПИ, ещё 71 оставались ambiguous. Reclassification меняла label, но не
добавляла отсутствующие type-specific fields. 0 из 25 tested references от
АОСР к приложениям разрешились автоматически. Отсутствие связи не доказывало
отсутствие документа, а найденный файл не доказывал закрытие requirement.

## 7. Реальная модель входного контроля

Найденные материалы позволяют подтвердить следующую **object-specific process
hypothesis**, но не универсальную юридическую норму:

```text
поставка / партия МТР
→ применимые требования входного контроля
→ паспорт / сертификат / supporting quality evidence
→ журнал входного контроля / журнал верификации
→ АВК, АОРПИ и другие применимые control records
→ решение о допуске партии
→ применение партии к работе / конструкции
→ контроль выполнения и timely hidden-work evidence
→ комплектность и подписываемость ИД
→ предъявленный объём
→ КС
→ payment readiness
```

В найденном customer-specific ТЗ `журнал верификации` использовался как
операционное наименование/alias журнала входного контроля; АОРПИ ожидался по
партии вместе с quality documents. Применимость, обязательность, signer roles
и сроки должны выводиться только из exact НТД, договора, customer regulation,
WorkType/Material/control rules и effective versions.

### 7.1. Типизация обнаруженных документов

| Наблюдаемый тип | Роль для будущего Audit | Ограничение |
|---|---|---|
| Паспорт / сертификат качества | source + supporting evidence партии | Наличие файла не подтверждает применимость, authenticity или связь с партией. |
| Журнал входного контроля / «журнал верификации» | register + evidence of process timing/status | Alias и exact required fields зависят от applicable rule/profile. |
| АВК | control/admission evidence candidate | Раскрытие, обязательность и signer requirements должны идти из exact contract/rule, а не из имени файла. |
| АОРПИ | control result / admission-decision evidence candidate | Подтверждённое legacy раскрытие; `АОПРИ` остаётся unresolved terminology. |
| Лабораторный/control result | control result + measurement evidence | Требует method, unit, calibration, actor/authority и locator. |
| АОСР и приложения | ID component + derived evidence package | Late/generated form не доказывает timely underlying event. |
| Реестр документов | derived report / projection | Не является system of record и не закрывает gaps сам по себе. |

## 8. Почему формирование ИД не сработало

**ПРОВЕРЕНО:** corpus содержал тысячи файлов, но logical boundaries,
classification, version identity и evidence links были ненадёжны. Значимая
часть rows указывала на container bytes; дубликаты и ghost rows оставались после
promotion. АОСР смешивались с АОРПИ, приложения не связывались с актами,
type-specific attributes отсутствовали, а status counters иногда сообщали
завершение при неполном результате.

**СЛОВА ВЛАДЕЛЬЦА:** четыре ИП вручную пытались собирать папки из этого
материала, но отсутствие/ненадлежащее состояние первичных records не позволяло
получить подписанную ИД.

**ВЫВОД:** проблема была не только в распознавании PDF. Pipeline мог найти и
классифицировать файл, но не доказывал:

1. к какой партии, работе, конструкции и control event относится документ;
2. существовал ли контроль в требуемое время;
3. кем и в рамках какой authority принято решение о допуске;
4. какая version действительна и почему конфликтующие versions не применимы;
5. закрывает ли evidence exact `DocumentRequirement`;
6. готов ли пакет к подписи и какие downstream volumes/claims затронуты.

Поздно заполненный формуляр мог улучшить внешний вид папки, но не восстановить
утраченное событие, measurement, authority или contemporaneous evidence.
Audit обязан различать `document found`, `content extracted`, `evidence
validated`, `requirement covered`, `signable`, `presentable` и `payment-ready`.

### 8.1. Комплект, том, книга и occurrence документа

**ПРОВЕРЕНО:** legacy ТЗ различало section, комплект/папку, том/книгу и
документ; стадия была свойством комплекта, а один document мог входить в
несколько комплектов. Комплект не всегда соответствовал одному physical
container. Отдельно описывались ordering, приложения, требуемое число
экземпляров и трёхуровневые реестры.

**ВЫВОД:** совместимая с ASD-КОНТУР модель требует самостоятельных immutable
versions `Package`, `Volume/Book` и `DocumentMembership/Occurrence`.
Membership содержит exact document version, package/book, position/order,
role, required copies, stage/scope and provenance. `SourceArtifact` и
`SourceVersion` не дублируются при участии одного документа в нескольких
packages. Section остаётся предметной классификацией, а не package identity.

Физическая готовность — отдельная оценка, а не расширенный file count:

```text
document found/recognized/classified/evidence-bound
→ package membership and ordering
→ required copies/registers/attachments
→ professional review
→ signer authority and signatures
→ handover
→ returned with comments / re-presented
→ accepted
```

Ни один одинарный `ready/final` не может заменить эти состояния. Значения вроде
конкретного числа листов, книг или копий из Левашово являются object-specific
requirements и применяются только через exact rule/customer/contract evidence.

## 9. Причинная связь с КС и оплатой

**ПРОВЕРЕНО:** legacy corpus содержал упоминания форм КС, но проверенные 42
записи были пустыми contractual forms и не доказывали выполнение либо
entitlement. Operational evidence также показывало большой unsigned backlog и
незакрытый incoming-control stage.

**ВЫВОД:** разрыв раннего evidence может создавать downstream blocker:

- непроверенная партия → admission indeterminate;
- admission indeterminate → material application/work evidence incomplete;
- work evidence incomplete → ID requirement uncovered;
- ID uncovered/unsigned → presentation/KS/payment readiness blocked or
  indeterminate.

Это не универсальное юридическое утверждение «оплата невозможна». WP-14 должен
создавать typed `risk`, `gap`, `blocker` или `uncertainty` с exact applicable
contract/rule/evidence trace. Entitlement решает уполномоченный специалист.

## 10. Dashboard experience

### 10.1. Dashboard Заказчика

**ПРОВЕРЕНО:** более поздняя модель показывала total/signed/in-work/risk/%
ready, stage flow, section×stage traffic-light matrix, contractor filter,
unsigned backlog и stop codes. В одном snapshot было 62 sections и 1 016 acts;
39 sections находились на incoming control, только 4 имели signed result.
Supporting-evidence location было заполнено для 27 sections, но не выводилось;
incoming-control readiness percentage почти не заполнялся.

Полезны:

- causal drill-down от показателя к exact gaps и affected entities;
- signed/unsigned и blocking reasons;
- evidence coverage отдельно от workflow stage;
- динамика, stale/unknown status и reconciliation freshness;
- readiness для ID, presentation, KS и payment как разные projections.

Вводят в заблуждение:

- progress по числу файлов или заполненных rows;
- единый процент без denominator provenance;
- `ready/final` по process counter;
- сокрытие ambiguous, failed, pending и unverifiable elements.

### 10.2. Dashboard ПТО

**ПРОВЕРЕНО:** prototype позволял классифицировать документы, менять attrs и
status, review confidence, работать с stop code/comments, incoming-control
completeness и act signing. Early FastAPI UI использовал прямые SQL-запросы и
не имел workspace isolation/typed command boundary; spreadsheet UI позволял
редактировать operational cells напрямую.

Для ASD-КОНТУР следует сохранить операции пользователя, но модернизировать их:

- classification correction → новая immutable version + decision + audit;
- Candidate accept/reject → authority-checked command;
- document↔batch/work/control linkage → typed EvidenceLink/coverage command;
- duplicate/conflict resolution → explicit decision, original versions remain;
- page retry → new attempt with exact locator and reconciliation;
- package/signing status → derived projection from canonical decisions;
- dashboard rebuild → no canonical state change.

### 10.3. Ложная метрика ВК

**ПРОВЕРЕНО:** legacy использовало формулу `(signed + unsigned) / total`.
Если `unsigned = total - signed`, результат равен 100% при полном inventory
даже тогда, когда `signed = 0`. Это измеряет распределение найденных записей по
двум статусам, но ошибочно называлось readiness.

WP-14 обязан хранить version/provenance numerator и denominator, не включать
unsigned/unknown/indeterminate в signed readiness, не усреднять разные
readiness dimensions и показывать counts/causal blockers рядом с процентом.
Критический blocker не скрывается aggregate percentage. Negative acceptance:
все documents найдены, ни один не подписан — signed-ID и KS readiness не могут
быть 100%.

### 10.4. Stop-code и `ActionRequest`

**ПРОВЕРЕНО:** stop-code в legacy задавал не только статус, а запрос действия:
инициатор, исполнитель/адресат, affected object, reason/evidence, deadline и
этапы выполнения. Закрытие требовало подтверждения инициатора.

**ВЫВОД:** WP-14 моделирует typed immutable `ActionRequestVersion` и decisions:
`created → accepted → in_progress → performed → verified_closed` либо
`rejected/cancelled/superseded/overdue`. Policy задаёт инициатора, исполнителя,
кто подтверждает устранение и кто может отменить blocker. Исполнитель не может
сам закрыть запрос, если требуется независимая проверка. Исчезновение файла из
очереди, reclassification или изменение process counter не закрывает запрос;
нужны closure evidence, authority decision и audit trail. Notification UI в
WP-14 не требуется.

### 10.5. Reclassification

Reclassification создаёт новую immutable classification version и сохраняет
lineage прежней. Затем запускаются validators нового document type,
вычисляются missing required attributes и создаются targeted repair либо
`ActionRequest`. Новый label сам по себе не делает документ ready и не закрывает
Document Delta. High confidence может только приоритизировать review queue.

## 11. Подтверждённые defects и bottlenecks

| Defect | Практическое последствие | Требование к WP-14 |
|---|---|---|
| Global digest dedup | Одинаковые bytes могли терять самостоятельный scope/authority | Digest equality отдельно от identity, ownership и evidence authority. |
| Container row used as logical document | Неверный content при чтении по document row | Exact logical boundary and container/page lineage. |
| Over-segmentation | Один документ становился несколькими | Boundary validator + integrity reconciliation against page inventory. |
| Document mixing | Несколько logical documents могли попасть в общий batch/result | Single-workspace immutable item manifest and result-to-item binding. |
| Partial success reported ready | Необработанные страницы исчезали из completeness | Per-page terminal state; no empty-success; aggregate success only by receipts. |
| Mutable retry/reset | Duplicate rows/findings and repeated cost | Idempotency, immutable attempts, result reconciliation. |
| Confidence-driven review | Высокая уверенность скрывала systematic mismatch | Candidate/Fact/authority separation; deterministic validators. |
| Generic JSON metadata | Type-specific fields missing after reclassification | Versioned typed schema; correction appends version. |
| Loose refs/no FK | Ghost documents and unresolved attachments | Same-scope composite FK and referential integrity. |
| File-count progress | Папка выглядела готовой при causal gaps | Evidence coverage and causal readiness projections. |
| `(signed + unsigned) / total` as readiness | 100% возможно при нуле подписанных | Separate denominators; unsigned/unknown never add to signed readiness. |
| Package/section/container conflation | Physical assembly/signing/handover state терялся | Typed Package, Volume/Book and ordered DocumentMembership. |
| Stop-code as mutable status | Blocker исчезал без authority/evidence closure | Typed ActionRequest, SoD, closure evidence and supersession. |
| Last uploaded revision wins | Поздний файл молча вытеснял prior authority/conflict | Immutable versions, explicit supersession, authority and effective interval. |
| Reclassification only changed label | Обязательные attrs нового типа оставались пустыми | New classification version, validators and targeted repair/action requests. |
| Direct UI edits | History/authority unclear | Typed commands, optimistic concurrency, immutable audit. |
| `FINAL` from process state | False completion despite failed steps | Canonical reconciliation and explicit incomplete/unknown outcome. |

## 12. Object-specific решения и универсальные уроки

Object-specific, не переносимые автоматически:

- labels/sections and customer-specific document matrix;
- конкретные counts, folder names и stage nomenclature;
- prompt examples, model choice, window sizes and retry numbers;
- customer-specific interpretation of journal aliases;
- any claimed document obligation without exact applicable evidence.

Универсальные уроки:

- file, logical document, source version, physical bytes and page occurrence
  are distinct identities;
- recognition is an attempt/result, not evidence acceptance;
- partial work must remain visible and resumable;
- correction is a versioned decision;
- completeness is required-vs-actual evidence coverage, not file count;
- readiness is a typed causal graph with explicit applicability and unknowns;
- Audit diagnoses gaps and downstream impact; Restoration acquires/reconstructs
  evidence under a separate process;
- projection/status/dashboard is rebuildable and never system of record.

## 13. Preserve / modernize / reject

| Decision | Legacy lesson |
|---|---|
| Preserve | Native/raster distinction; page-level processing; batch manifests; bounded concurrency; retry/resume need; source bytes in object storage; operational dashboard; manual review queue; hashes and reconciliation reports; explicit package/book/register/signing/handover vocabulary; action requests. |
| Modernize | File/document identity into `SourceArtifact/SourceVersion/PhysicalObject/Locator`; package relations into typed immutable Package/Volume/Book/Membership; JSON attrs into typed immutable versions; Polza result into provider attempt/result/Candidate; retries into idempotent reconciliation; stop codes into authority-checked ActionRequest; UI edits into typed commands; progress into three separate readiness deltas. |
| Reject | Path/hash as authority; global project memory; one nullable/global scope; mutable current JSON as canon; last-write-wins; confidence-as-truth; `(signed + unsigned) / total` as signed readiness; silent JSON repair/empty success; gap-fill that fabricates coverage; broad queue reset; direct SQL corrections; file-count completeness; project-specific rules promoted automatically. |

## 14. Что не удалось подтвердить

- exact `АОПРИ` meaning; evidence consistently uses `АОРПИ`;
- exact number of students and the absence of every signed folder;
- current Polza.ai terms, pricing, region, retention/no-training guarantees;
- live state of historical pdfpipe server referenced by notes (сервер не
  обследовался по заданию);
- contents of unmounted `king25` NTFS volumes;
- contents of unmounted `ms-7e26 /dev/nvme0n1p3`;
- nine malformed/non-ZIP archive containers on `ms-7e26`;
- legal universality of the full VK→ID→KS→payment chain;
- production users' acceptance of either dashboard;
- authority/authenticity of the underlying project documents without opening
  and publishing their contents, which was intentionally prohibited.

## 15. Итог

На доступных томах correction coverage и full-read ledger закрыты. Полный
cross-volume статус остаётся **PARTIAL**, пока шесть NTFS-разделов не станут
readable либо владелец не зафиксирует их как недоступные. Поэтому отчёт не
утверждает «проверены все пользовательские Markdown».

pdfpipeline доказал практическую ценность массового intake, page processing,
object storage, provider batching и operational visibility. Он одновременно
доказал, что тысячи распознанных файлов не создают ИД: без versioned identity,
exact evidence binding, authority, temporal control and causal readiness
reconciliation pipeline может масштабировать ошибку быстрее, чем исправлять
её. Эти lessons уточняют WP-14, но не заменяют современную архитектуру.
