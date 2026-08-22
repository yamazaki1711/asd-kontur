# Legacy ID Generator Asset Inventory v0.1

- **Статус:** Completed read-only inventory; MBP, `king25` и `ms-7e26`
  обследованы
- **Дата:** 2026-08-22
- **Назначение:** read-only опись наследия генерации исполнительной
  документации до проектирования Logical Data Model
- **Источники фактов:** filesystem и git history `/Users/oleg/mac_asd`, все
  доступные пользовательские/рабочие тома `king25` и `ms-7e26`, архивные
  листинги и выборочное read-only извлечение, статический разбор OOXML/PDF,
  обычный OpenSSH
- **Staging:** отобранные remote assets скопированы только во временный каталог
  вне проекта; manifest содержит source host/path, SHA-256, размер, MIME type и
  причину отбора
- **Запрет:** legacy-код, БД, модели, installers и deployment не запускались;
  находки не объявлялись каноническими либо active templates

## 1. Scope, метод и маркировка фактов

Аудит охватил tracked, untracked и безопасно перечислимые ignored paths,
git history, удалённые из текущего дерева пути, архивные каталоги,
документацию, mappings, schemas, tests и generated outputs. Содержимое `.env`,
ключей и credentials не читалось и не копировалось. Документы конкретных ОКС
учитывались только как evidence существования механизма или результата и не
включались в platform memory. Системные каталоги, dependencies, caches,
`node_modules`, virtual environments и служебные данные ОС исключались.

Метки:

- **ПРОВЕРЕНО** — наблюдено командой в текущем дереве или git object database;
- **ИСТОРИЧЕСКОЕ УТВЕРЖДЕНИЕ** — заявлено legacy-отчётом, но не подтверждено
  текущим деревом;
- **НЕ ПРОВЕРЕНО** — требует последующего контролируемого доступа/валидации.

`source authority` ниже означает доказанность происхождения asset, а не
профессиональное утверждение нормативной применимости.

## 2. Резюме находок

**ПРОВЕРЕНО:** `mac_asd` содержит большой `ISGenerator`: 19 Python-файлов,
8 839 строк, четыре заявленных пути построения исполнительных схем, parsers,
DXF/PDF renderers, completeness/event/batch контуры и связанные тесты.

**ПРОВЕРЕНО:** отдельно существует платформа текстовых форм: 153 определения
форм, 113 work-type mappings, DOCX filling через `docxtpl`, XLSX filling через
`openpyxl`, генераторы АОСР/АООК/КС-2/КС-3/реестра и три текущих binary template.

**ПРОВЕРЕНО:** каталог `library/templates/dxf` отсутствует. Текущий
`ISTemplateRegistry` продолжает ссылаться на 100+ YAML filenames.

**ПРОВЕРЕНО:** в git history существуют 25 YAML backup-шаблонов и удалённые
отчёты ISGenerator. Исторический отчёт заявляет 92 файла и покрытие 86/86, но
67 добавленных файлов не найдены как tracked blobs по пути
`library/templates/dxf`. Поэтому утверждение 86/86 не считается доказанным
asset inventory.

**ПРОВЕРЕНО:** `config/missing_templates_registry.yaml` сам фиксирует старый
срез: 324 уникальных документа, 15 найденных и 309 отсутствующих шаблонов.

**ПРОВЕРЕНО:** тесты в основном доказывают создание/открытие файла и наличие
структурных DXF entities/placeholders. Устойчивого набора print-render golden
documents и pixel/page comparison snapshots не найдено.

**ПРОВЕРЕНО на `king25`:** обнаружен отсутствующий на MBP бинарный корпус
`idprosto`: 149 DOCX и 82 XLSX пустых форм, а также 84 PDF-примера. Все 315
файлов отличаются по SHA-256 от файлов `/Users/oleg/mac_asd`. DOCX/XLSX
структурно исправны, но не содержат Jinja-плейсхолдеров, merge fields, content
controls, legacy form fields, XLSX formulas или data validation. Это ценный
корпус макетов и reference outputs, но не готовый binding/render mechanism.

**ПРОВЕРЕНО на `king25`:** найдены 54 DOCX обычного output и 274 тестовых
артефакта (251 DOCX и 23 ZIP). Корпус доказывает фактическую работу legacy
`OutputPipeline`, одновременно выявляя накопление предыдущих АОСР в следующих
файлах одного процесса, нулевые суммы КС-2/КС-3 и неполные реквизиты. Ни один
из этих файлов не является подтверждённым print-ready golden output.

**ПРОВЕРЕНО на `ms-7e26`:** текущий `/home/oleg/MAC_ASD` — более старый снимок
той же линии (`a9b64c26`, предок local HEAD). Его `data/gdrive/templates`
содержит 151 DOCX, 205 XLSX и 83 PDF, а `data/gdrive/samples` — 84 PDF. Из 205
XLSX 122 отсутствуют на `king25`; после исключения трёх ошибочно смешанных с
templates generated outputs остаются 119 универсально выглядящих пустых форм.
Это главный новый cross-host corpus, но не active templates.

**ПРОВЕРЕНО на `ms-7e26`:** live ID-код подтверждает ту же частичную
реализацию: `docxtpl`-АОСР, программный двухстраничный XLSX-АОСР, DXF/PDF
`ISGenerator`, parsers и структурные tests. Два заполненных test DOCX, три
generated XLSX и текущие КС-2/КС-3 не проходят критерий print-ready. Отдельные
`ISUID`, `id-track` и `Qwen_ASD` полезны как lifecycle/XLSX/schema prototypes,
но не являются готовым генератором ИД.

**ПРОВЕРЕНО:** все три среды обследованы. Legacy-механизм способен создавать
открываемые DOCX/XLSX/DXF и некоторые PDF, но доказательств нормативно
авторитетного, stateless, evidence-bound и print-qualified ID Generator нет.

## 3. Реестр assets

| Asset ID | Host / путь | Тип, формат, размер | Git status / history | Назначение, реализованность, тесты, зависимости | Authority / scope / privacy | Решение → target / основание |
|---|---|---|---|---|---|---|
| LID-001 | `local-authoritative-node`; `/Users/oleg/mac_asd/src/core/services/is_generator/` | source bundle; Python; 19 файлов, 8 839 строк | tracked, current; основные коммиты `00759c7`, `dc33f3c` | DXF-first, PDF-overlay, from-params, template path; batch/events/completeness; тесты `test_is_generator*`; `ezdxf`, PyMuPDF, CairoSVG, openpyxl | project source; platform candidate; без bytes ОКС; internal | **modernize** → ID Geometry/Render adapters; зрелые алгоритмы полезны, но нет workspace/evidence/version gates |
| LID-002 | `.../is_generator/is_generator.py` | orchestrator; Python; 777 строк | tracked, clean | создаёт DXF/PDF; file-existence verification; ловит render exceptions; допускает generation from params | project source; mixed platform mechanism/workspace input; internal | **modernize** → `GenerationRun`; исключить silent partial success и недоказанную геометрию |
| LID-003 | `.../is_generator/template_registry.py` | registry; Python; 341 строк | tracked; расширен `dc33f3c` | 100+ work-type→YAML ссылок, lazy load; target directory отсутствует | project source; platform candidate; internal | **preserve metadata, replace activation model** → Template Registry; registry membership не означает active/available |
| LID-004 | git history: `archive/deprecated/templates_backup_20260603/*.yaml` | 25 YAML parametric drawing templates; current size n/a | history-only blobs; добавлены `dc33f3c`, позже удалены cleanup-коммитом | параметры/геометрические drawing rules; historical tests reported | project source, authority не подтверждена; platform candidate; no known ОКС data in inspected metadata | **inspect-later** → Template recovery quarantine; извлекать только отдельной controlled migration после source/evidence review |
| LID-005 | git history: `docs/reports/is_generator_86_templates_report.md` | historical report; Markdown | history-only; удалён `04ae307` | заявляет 92 files, 86/86 и 72 tests; текущим деревом не подтверждено | historical assertion; internal | **preserve as evidence, reject as readiness proof** → recovery dossier |
| LID-006 | `/Users/oleg/mac_asd/library/templates/dxf/` | expected YAML directory | **отсутствует**; сам путь никогда не найден tracked в `git log --all` | нужен template-path generator | no asset | **recover/inspect-later** → Legacy Asset Recovery; blocker template migration |
| LID-007 | `.../library/templates/acts/344pr/3_AOSR.docx` | DOCX; 38 419 B; SHA-256 `6484d7d1708c8a155b802c6a8728f5ebd00be7ae318cf577abefbbd8dc23083a` | tracked, **modified**; базовый commit `dbdd579` | параметризованный АОСР, 20+ placeholders; tests проверяют placeholders/fonts/openability, не полный print render | заявлена форма 344/пр, official authority **не проверена**; platform candidate; moderate | **inspect-later** → candidate TemplateVersion; dirty bytes требуют отдельного provenance decision |
| LID-008 | `.../library/templates/acts/344pr/3_AOSR.xlsx` | XLSX; 15 724 B; SHA-256 `fb00ffd09ebee4bc7249b7d666ec74c57e528d593252cac94236992936139072` | tracked, clean; `720eb85` + print/layout fixes | двухстраничная Excel-форма АОСР, print area/margins/row heights; `openpyxl` | заявлена форма 344/пр, authority не проверена; platform candidate; moderate | **inspect-later** → XLSX TemplateVersion + golden print suite |
| LID-009 | `.../library/templates/acts/344pr/4_AOOK.docx` | DOCX; 38 476 B; SHA-256 `9da0d946ce68fb10a3438269ea320b5e9d9001386b8c4c0a84964d1504844cec` | tracked, clean; `9b2305f` | параметризованный АООК; limited current evidence | заявлена форма 344/пр, authority не проверена; platform candidate; moderate | **inspect-later** → DOCX TemplateVersion; needs source/layout validation |
| LID-010 | `.../library/schemas/` | 13 YAML field schemas; key hashes: AOSR `4d40…f9e9`, AOOK `f2d0…0ac5`, executive scheme `c44a…4433` | tracked, current | fields/type hints для актов, схем, журналов, КС, certificates | project source; mixed quality; platform candidate; internal | **modernize** → FieldSchema/BindingRule; add stable identity, evidence, versions |
| LID-011 | `.../data/knowledge/templates/template_forms.yaml` | registry; YAML; 67 752 B; SHA-256 `4b432942…9940`; 153 forms | tracked, current | form IDs, filenames, fields, normative labels; только одна `exists: true`, хотя два DOCX существуют | project source; platform candidate; internal | **modernize** → TemplateDefinition discovery import; inconsistent availability flags require quarantine |
| LID-012 | `.../data/knowledge/templates/work_type_templates.yaml` | mapping; YAML; 36 903 B; SHA-256 `bc88f755…5285`; 113 top-level mappings | tracked, current | work type→required/conditional forms; tests check coverage | mixed historical/normative claims; platform candidate; internal | **inspect-later** → applicability/rule candidates; no direct RuleVersion promotion |
| LID-013 | `.../config/missing_templates_registry.yaml` | deficit registry; YAML; 324 unique, 15 found, 309 missing | tracked snapshot dated 2026-06-08 | template deficit evidence; contains many unverified normative labels | generated audit evidence; platform planning only; internal | **preserve** → recovery backlog evidence; never active registry |
| LID-014 | `.../src/core/template_engine.py`, `template_context_processor.py` | DOCX generator/filler; Python; 1 203 строки | tracked, current | builds templates, preprocesses lists/dates, fills via docxtpl; tests largely file/openability | reusable mechanism; platform candidate; internal | **modernize** → DOCX adapter; retain layout-preserving operations, add provenance and render validation |
| LID-015 | `.../scripts/build_aosr_xlsx.py` | XLSX builder/filler; Python; 992 строки | tracked, history has print/layout fixes | fills AOSR, page setup, merged cells, row heights; only AOSR implemented | reusable mechanism; platform candidate; internal | **modernize** → XLSX adapter; remove form-specific core and add formula/print golden tests |
| LID-016 | `.../scripts/create_minstroy_templates.py` | DOCX template builder; Python; 453 строки | tracked | programmatically creates AOSR/AOOK forms/placeholders | source authority not embedded strongly enough; platform candidate | **inspect-later** → template acquisition tooling; generated form not official merely because layout resembles source |
| LID-017 | `.../src/core/output_pipeline.py` | document generators; Python; 765 строк | tracked | generates AOSR, KS-2, KS-3, ID register; uses created documents rather than immutable official binaries | project source; mixed platform/workspace | **modernize** → format adapters behind common generation contract |
| LID-018 | `.../src/core/production/acts.py`, PTO act/document generators | production facades; Python; 1 237+ строк | tracked | docxtpl rendering, mapping and production states; some forms `NotImplemented` | project source; workspace processing; internal | **modernize**, reject automatic “production” naming → Candidate/authority lifecycle |
| LID-019 | `.../config/id_requirements.yaml` | requirements registry; YAML; 138 098 B; SHA-256 `1b0b6872…d90b` | tracked; long correction history | work→document requirements; historical normative drift/fixes | mixed authority; platform candidate only after verification | **modernize** → RequiredDocumentType/applicability RuleVersion candidates |
| LID-020 | `.../config/id_composition_344pr.yaml` | composition source mapping; YAML; 11 002 B; SHA-256 `dfec0ba8…fb82` | **untracked** | 13-category composition with provenance to a supplied publication | source is not established here as official authority; platform candidate; internal | **inspect-later** → Knowledge/Rule intake; cannot promote as canonical NTD by filename/comment |
| LID-021 | eight relevant test files in `/Users/oleg/mac_asd/tests/` | tests; Python; 4 086 строк | tracked | structural entities, placeholders, file existence/openability, some print settings; many optional dependency skips/mocks | test evidence; no ОКС content in inspected tests | **preserve/modernize** → recovery regression suite; add evidence/layout/golden negatives |
| LID-022 | `.../data/artifacts/output/` | generated DOCX outputs | ignored; workspace outputs | samples exist, but are not governed golden files | workspace-specific/synthetic status not fully proven; restricted | **reject as platform template; inspect-later as test sample** after sanitization |
| LID-023 | `/Users/oleg/Documents/ASD-KONTUR-archive/.../[workspace-content]` | archive of PDF/XLSX/DOCX and manifests | outside git; read-only path metadata inspected | project documents and archive objects; no generator source/template registry found | workspace-specific; restricted/confidential | **reject for platform corpus**; usable only in isolated scenario tests under separate authority |
| LID-024 | git history: deleted `docs/id_pipeline_architecture.md` versions and ISGenerator reports | architecture evidence; Markdown | current main document plus history-only reports | describes unified ID pipeline but contains planned classes absent from current source | historical design; internal | **preserve concepts, modernize contracts** → ID Generation specification |
| LID-025 | `king25`; `/mnt/nvme_p4/idprosto/id_forms/` | 231 files; 149 DOCX + 82 XLSX; 4 394 853 B | вне git; third-party corpus | blank forms in 39 normative package directories; OOXML valid, but no fields/bindings | origin: `id-prosto`, official authority unverified; universal-looking; quarantine | **preserve in controlled staging, inspect-later** → immutable source candidates; never auto-activate |
| LID-026 | `king25`; `/mnt/nvme_p4/idprosto/id_samples/` | 84 PDF; 12 738 308 B; 129 pages | вне git | mostly A4 static filled examples; all `Form: none`, one A3 sample; layout evidence only | third-party/reference; several samples contain example/object values | **preserve only in isolated reference quarantine**; sanitize before golden use |
| LID-027 | `king25`; `/mnt/nvme_p4/idprosto/` metadata | JSON + acquisition source; 31 work types, 569 document relations, 356 references, 231 forms, 84 samples | вне remote git; JSON descendants are tracked in old `MAC_ASD` | source catalog, download links, parsed DOCX structures, package/template inventories | third-party source metadata; no normative approval | **modernize** → discovery/import evidence; verify every authority/version |
| LID-028 | `king25`; `/mnt/nvme_p4/tmp/asd_output/` | 54 DOCX; 27 КС-2 + 27 КС-3 | generated, вне git | files open, but amounts are zero and forms omit required official detail | synthetic/generated evidence | **reject as final/golden**; retain sanitized defect cases only |
| LID-029 | `king25`; `/mnt/nvme_p4/tmp/asd_test_output/` | 251 DOCX + 23 ZIP | generated, вне git | 250 AOSR + one register; archive packaging works; cumulative-document defect proven | synthetic test values; not ОКС authority | **preserve selected sanitized regressions**, reject as print-ready |
| LID-030 | `king25`; `/mnt/nvme_p4/MAC_ASD/` | git repository; HEAD `a154a2a`; 87 MB tree + 57 MB `.git` | `main`; feature/legal ref `932c`; both objects already in local repo | older v15 source/docs/tests; no `library/` binary corpus in worktree or HEAD | project source | **do not migrate duplicate source**; use only as provenance snapshot |
| LID-031 | `king25`; `/mnt/sdb1/Users/OLEG/Documents/2026/GitHub/ProjectASD/` | git repository; 2.1 MB; four commits; HEAD `e51caf1` | current main, no deleted paths | LLM extraction plus generic `python-docx` AOSR; AOOK/journal JSON only | predecessor prototype | **preserve concepts, reject readiness claims**, modernize deterministic bindings |
| LID-032 | `king25`; root `/mnt/nvme_p4/.git` | orphan object store; about 37 GB | no refs, logs or index; unusable as repository | no safely attributable history | unknown | **reject from staging/migration** |
| LID-033 | `king25`; `/home/oleg/Downloads/Проекты-*.zip` | ZIP; 258 840 378 B; 24 PDF entries | archive, listed only | object-specific ПД/РД package; no generator source | ОКС-specific/restricted | **do not transfer to platform memory** |
| LID-034 | `king25`; `/home/oleg/Downloads/SYNC_GDRIVE.zip` | ZIP; about 2.1 MB; 7 entries | archive, README inspected; credentials entries intentionally skipped | sync utility, not ID generator | contains secrets | **reject**; no secret copied |
| LID-035 | `king25`; trash archive `archive-2026-08-01_05-40-46.zip` | ZIP; about 338 KB; 18 entries | archive; 11 relevant MD byte-equivalent to current remote copies | no unique generator asset | historical docs | **do not migrate duplicate** |
| LID-036 | `ms-7e26`; `/home/oleg/MAC_ASD/data/gdrive/templates/` | 439 files: 151 DOCX + 205 XLSX + 83 PDF; about 18.7 MB | live data, outside tracked source | static qualification: all OOXML containers valid; DOCX: 0 Jinja/merge fields/content controls; XLSX: 0 Jinja/formulas/data validation, all have print setup; PDF: 0 AcroForms | mostly universal-looking third-party/reference forms; authority unverified | **quarantine and deduplicate**; 119 XLSX blank-form candidates and one PDF variant are unique versus `king25` |
| LID-037 | `ms-7e26`; `.../library/templates/acts/344pr/3_AOSR.docx` | DOCX; 17 861 B; SHA-256 `dffd8bf999a43754fcbd93a919436e78cf5a29b8119081e9673ba22c5c2ce4c9`; 31 unique Jinja keys | live older candidate; differs from dirty MBP binary | actual `docxtpl` source for AOSR; list/date context preprocessing; formatting preservation not render-qualified | claimed 344/пр-like source, authority/edition unverified | **inspect-later** as immutable source/derivative pair; do not replace newer local candidate automatically |
| LID-038 | `ms-7e26`; `.../library/templates/acts/344pr/3_AOSR.xlsx` | XLSX; 15 724 B; SHA-256 `fb00ffd09ebee4bc7249b7d666ec74c57e528d593252cac94236992936139072` | byte-exact with MBP current file | two-page AOSR with merges, margins and print area | same qualification gap as LID-008 | **deduplicate** against LID-008; retain provenance only |
| LID-039 | `ms-7e26`; `/home/oleg/MAC_ASD_04062026.zip` selected entries | 25 YAML + five archive-only ISGenerator reports and selected source/tests | read-only extraction; 25 YAML byte-equivalent to locally recoverable history blobs | reports describe stages 1–3 and later 86-template claim; assets prove only 25 parametric templates | historical project evidence | **preserve reports and one deduplicated YAML set**; reject reported 86/92 readiness as unverified |
| LID-040 | `ms-7e26`; `/home/oleg/Desktop/Yandex/ASD_KAT/ISUID_repo/ISUID/` and adjacent app | source/docs/SQL prototype; about 268 KB core | not a git repository | staging→promotion, check results and document lifecycle; specification defers `docxtpl` forms and executive/geodetic schemes | project prototype; contains existing SQL inspected but not executed | **preserve lifecycle concepts, modernize contracts**; not an ID renderer and not a migration/DDL source |
| LID-041 | `ms-7e26`; `/home/oleg/id-track/` | Python/openpyxl source, tests and deploy examples; about 106 MB repository tree, selected files staged | separate git repository | schedule import/export, repair and forecasting workbooks; no AOSR/DOCX/PDF generation | adjacent reusable spreadsheet mechanics | **inspect-later** for safe XLSX parsing/repair patterns; reject as ID Generator |
| LID-042 | `ms-7e26`; `/home/oleg/Qwen_ASD/src/modules/id_engineer/` | Python LLM extraction + generic `python-docx` renderer | git `main` @ `e51caf1`; modified/untracked related source present | JSON schemas for AOSR/AOOK/journal/completeness; only generic AOSR DOCX is rendered | predecessor prototype, no template/evidence/layout authority | **preserve schema ideas, reject renderer/readiness**; candidate values must never become facts automatically |
| LID-043 | `ms-7e26`; generated evidence in `data/gdrive/templates`, `data/artifacts/output` and filled AOSR tests | 2 filled DOCX + 3 generated XLSX + current KS-2/KS-3 outputs | outside governed test corpus | files open; visual/static checks reveal malformed date line, dense layout, zero totals and incomplete requisites | synthetic or object-specific evidence | **retain only sanitized defect samples**; reject as templates, goldens and print-ready outputs |
| LID-044 | `ms-7e26`; `/home/oleg/MAC_ASD/data/real_id_samples/` | 11 DXF: 8 generated + 3 control | live data | demonstrates DXF creation/control examples; corresponding governed PDF goldens absent | sample provenance/geometry authority unverified | **quarantine selected geometry regressions** after sanitization; never platform truth |
| LID-045 | `ms-7e26`; `MAC_ASD.zip`, `MAC_ASD_08052026.zip`, `MAC_ASD_04062026.zip`, Qwen/ISUID/ID-track backups | archives from 67 KB to 7.32 GB | read-only listings and selected entry extraction | preserve older source/report/template states; most source duplicates current or other hosts | mixed project, third-party and ОКС scope | **retain inventory metadata; transfer only specifically qualified entries**, never whole archives into platform memory |

Полные SHA-256 приведены только для безопасных текущих universal candidate
assets. Для multi-file source bundles authority определяется git object IDs;
для workspace content hashes намеренно не вычислялись и не публикуются.

## 4. Компоненты генерации

### 4.1. Почти завершённые механизмы

| Механизм | Наблюдаемое состояние | Ограничение целевого использования |
|---|---|---|
| `ISGenerator.generate` | DXF-first/PDF-overlay, annotations, deviations, stamp, PDF attempt | нет workspace/evidence identities; exceptions могут дать partial output; output verification в основном existence |
| `generate_from_params` | строит DXF с нуля и пытается PDF | параметры нельзя принимать без confirmed geometry; иначе создаётся фиктивная схема |
| `generate_from_template` | API и registry реализованы | активные YAML отсутствуют; registry coverage не равен template availability |
| `ParametricTemplate`/`DXFBuilder` | tables/hatches/dimensions/axes/material notes | нуждается в CRS, measurement lineage, template version и golden render gates |
| `TemplateFiller`/PTO generators | DOCX filling через docxtpl | field provenance отсутствует; file save не финализация |
| `XLSXActFiller` | АОСР XLSX с print configuration | только АОСР; нужна проверка formulas, merges, pagination и viewer variance |
| `OutputPipeline` | AOSR/KS2/KS3/register document creation | один `AOSRGenerator` переиспользует один `Document`; фактические outputs на `king25` накапливают предыдущие акты; программно создаваемая форма не отделена от официального TemplateVersion |

### 4.2. Parsers

- `DXFParser`: проектные оси и bbox/clip;
- `GeodataParser`: CSV, Leica GSI, CREDO TXT и XLSX;
- `RDIndex`: in-memory индекс листов РД;
- `ParametricTemplate.from_yaml`: parsing drawing descriptors;
- DOCX OOXML/docxtpl и `python-docx` adapters;
- XLSX/openpyxl adapters;
- PyMuPDF PDF page/background path;
- `VLMProjectAnalyzer`: распознавание с **silent stub fallback** — отклонить как
  production pattern.

### 4.3. Renderers

- `DXFBuilder`, `DXFAnnotator`, `ParametricTemplate`;
- `SVGExporter` и `PDFOverlayBuilder`;
- `TemplateGenerator`/`TemplateFiller` для DOCX;
- `XLSXActFiller`/`build_aosr_workbook`;
- `OutputPipeline` для программно создаваемых DOCX;
- PPR DOCX/PDF exporters — смежные, не доказаны как ID template core.

### 4.5. Реализации, подтверждённые на `king25`

#### Старый `MAC_ASD` (`a154a2a`)

- `OutputPipeline` фактически создаёт DOCX АОСР, КС-2, КС-3 и реестр через
  `python-docx`; `docxtpl` в этом пути не используется.
- `AOSRGenerator` хранит `Document` как состояние экземпляра. Singleton в
  `OutputPipeline` приводит к накоплению актов: в каждой из 25 тестовых серий
  файлы 1…10 содержат соответственно 1…10 актов. Page break между актами не
  добавляется.
- ZIP packaging фактически работает, но валидирует наличие файлов, а не их
  нормативную или печатную пригодность.
- КС-2/КС-3 создаются с нулевыми суммами и упрощённым составом реквизитов.
- `template_registry.py` индексирует filenames/work types/normative labels, но
  не заполняет binaries. Сохранённые абсолютные Windows paths не переносимы.
- `docx_template_structures.json` содержит извлечённые paragraphs/tables для 26
  packages, но не field mappings и не binding rules.

#### `ProjectASD` (`e51caf1`)

- `act_generator.py` извлекает через LLM work description, project documents,
  materials, dates и next works; при ошибке возвращает текст ошибки.
- `full_generation.py` просит LLM сформировать JSON и строит новый generic DOCX
  через `python-docx`. Официальный binary template не используется, сохранение
  исходного оформления не доказано.
- АООК и журнал возвращаются только как JSON; renderer для них отсутствует.
- Контекст ограничен первыми 10 chunks по 1000 символов. Детерминированного
  evidence binding, chronology/completeness validation и render regression нет.
- Dependencies: `python-docx`, `openpyxl`, PyMuPDF; `docxtpl` в этом prototype
  path не найден. Отдельных unit tests, fixtures или golden files нет.

#### Историческое описание `id_pipeline_architecture.md`

Документ полезен как перечень понятий chain/completeness/chronology/lifecycle,
но описывает отсутствующие classes и частично выдаёт план за реализацию.
Предложения восстанавливать отсутствующие журналы/протоколы или скрывать факт
реконструкции отвергаются: новая платформа обязана хранить provenance,
неизменяемый audit trail и требовать подтверждения полномочного человека.

### 4.4. Mappings и registries

- `template_forms.yaml`: 153 form definitions;
- `work_type_templates.yaml`: 113 work-type mappings;
- `STANDARD_TEMPLATES`: 100+ ссылок на отсутствующий DXF/YAML corpus;
- `id_requirements.yaml` и `id_composition_344pr.yaml`;
- `library/schemas/*.yaml`;
- `missing_templates_registry.yaml`;
- `config/work_documentation_perechen_id.yaml` и
  `customer_list_priority_rules.yaml` как untracked evidence requiring review.

### 4.6. Реализации и field flow на `ms-7e26`

Текущий `MAC_ASD` подтверждает четыре разных, не сведённых в единый
production contract пути:

1. `TemplateEngine` заполняет `3_AOSR.docx` через `docxtpl`; context processor
   преобразует русские даты и списки. При отсутствии binary он умеет создать
   generic template через `python-docx`, что в новом ядре запрещается для
   нормативной формы без отдельного source-authority workflow.
2. `ActGenerator` направляет АОСР в `build_aosr_xlsx.py`, а другие известные
   формы — в DOCX template engine. XLSX строится программно, имеет две страницы,
   merge cells, margins и print areas, но аргумент `templates_root` фактически
   не определяет источник макета, а default context содержит примерные
   объектные значения.
3. `ISGenerator` реализует DXF-first, PDF-overlay, from-params и template path;
   читает CSV/GSI/CREDO/XLSX, индексирует РД, вычисляет отклонения и поддерживает
   batch/events/completeness. Активного `library/templates/dxf` нет.
4. `OutputPipeline` программно создаёт DOCX АОСР/КС и реестр. Это тот же
   stateful lineage, дефект накопления документов и нулевые суммы которого
   доказаны на `king25`.

Для АОСР описаны object/developer/builder/designer и SRO, subcontractor,
act number/date, work description/start/end, project documentation, materials,
evidence, normative/project match, next works, appendices, special/additional
conditions и copies count. Значения поступают из caller dictionaries,
LLM-кандидатов, project chunks и hard-coded fixtures/defaults. Field-level
`EvidenceBinding`, authoritative source identity и confirmation status не
реализованы. Поддерживаемые библиотеки: `docxtpl`, `python-docx`, `openpyxl`,
PyMuPDF, CairoSVG, `ezdxf`, `pdf2image`, `pytesseract`, `reportlab` и PyPDF2;
`xlsxwriter` в проверенных generator paths не найден.

`ISUID` реализует только lifecycle/staging-promotion boundary; `id-track` —
XLSX schedule import/export; `Qwen_ASD` — LLM JSON extraction и generic
`python-docx` AOSR. Их полезные механизмы должны переноситься раздельно, без
объявления любого из трёх готовой платформой генерации ИД.

## 5. Templates

### 5.1. Official/universal candidates

Найдено три current binary candidate templates:

1. `3_AOSR.docx` — dirty working-tree version;
2. `3_AOSR.xlsx` — tracked version с несколькими print-layout corrections;
3. `4_AOOK.docx` — tracked version.

Они являются **candidate assets**, а не approved official TemplateVersion:
нужно доказать официальный source, точную редакцию, неизменённость оригинала,
field mapping и print equivalence. Оригинал и параметризованная производная
должны быть разными objects.

В git history дополнительно доступны 25 parametric YAML drawing candidates.
Они не считаются официальными формами и не должны автоматически попадать в
platform memory как active templates.

На `king25` дополнительно найдены 231 blank-form binaries:

- 149 DOCX: все открываются как OOXML; 0 Jinja placeholders, 0 MERGEFIELD,
  0 content controls, 0 legacy form fields, 0 simple fields;
- 82 XLSX: все открываются; 0 Jinja placeholders, 0 formulas, 0 data
  validations; у всех есть page setup, у 67 — print area, у трёх — print
  titles;
- 84 sample PDF: 129 страниц, 82 A4, один A3 и один нестандартный A4; у всех
  отсутствует AcroForm (`Form: none`).

Следовательно, remote corpus поддерживает ручное/визуальное использование
DOCX, XLSX и PDF, но сам по себе не реализует автоматическое заполнение.
Потенциальные renderer strategies — OOXML placeholder injection, cell mapping
или fixed-coordinate PDF overlay — должны создаваться и квалифицироваться
отдельно. Третьестороннее происхождение не заменяет official-source evidence.

На `ms-7e26` проверены ещё 439 файлов `data/gdrive/templates` и 84 PDF samples:

- 149 из 151 DOCX byte-exact совпадают с `king25`; два оставшихся — уже
  заполненные test outputs, а не blank templates;
- 83 из 205 XLSX совпадают по файлам с `king25`; из 122 остальных три являются
  generated `PRJ-001_KS2/KS3/LSR.xlsx`, а 119 — новые universal-looking blank
  form candidates;
- 82 из 83 template PDF совпадают с `king25`; один static reference уникален;
- все 84 sample PDF byte-exact совпадают с `king25`;
- ни один из 151 DOCX не содержит Jinja, merge field или content control;
  ни один из 205 XLSX — Jinja, formula или data validation; все XLSX содержат
  print setup; ни один из 167 PDF template/sample не содержит AcroForm.

Точных SHA-совпадений этих gdrive binaries с текущим деревом
`/Users/oleg/mac_asd` нет. Это расширяет source/reference corpus, но не
подтверждает field mappings, renderer или authority.

У текущей локальной параметризованной формы АОСР найдены 29 placeholder keys:
номер/дата акта, объект, developer/builder/designer и их SRO, subcontractor,
описание и даты работ, project documents, materials, evidence documents,
normative/project match, next works, appendices, special/additional conditions
и copies count. Значения берутся из caller context. В production script
`build_aosr_xlsx.py` `_default_context()` содержит конкретные объектные
организации/лица; этот sample context не является platform memory и подлежит
замене обезличенной fixture.

### 5.2. Project-specific templates/documents

Локальный архив и ignored data содержат документы конкретных ОКС и generated
outputs. Они классифицированы как workspace-specific. Их содержимое, имена ОКС
и field values не переносились в отчёт или platform corpus. Универсальный
шаблон может быть выведен из такого документа только отдельным Promotion Gate
с leakage tests и доказанной authority.

## 6. Tests, fixtures и golden outputs

- relevant test source: 8 файлов, 4 086 строк;
- сильные части: DXF entity checks, required placeholders, template openability,
  some print settings, deterministic calculations;
- слабые части: extensive mocks/skips, existence/size checks, отсутствие
  field-level evidence tests;
- **golden output corpus не найден** как управляемый versioned asset;
- ignored generated DOCX не являются golden documents;
- remote corpus содержит 305 generated DOCX и 23 ZIP, но это defect/reference
  evidence, а не goldens: АОСР кумулятивны, КС-формы нулевые/неполные, register
  имеет пустые даты и draft statuses;
- статический и визуальный spot-check подтвердил, что blank 344/пр-like DOCX и
  XLSX сохраняют сложный layout, а generated АОСР/КС-2 заметно упрощены;
- `id_samples/344-pr_new-aosr.pdf` — двухстраничный A4 filled reference с
  third-party watermark и без AcroForm; это expected-layout evidence, не
  доказанный результат найденного generator;
- legacy statements `72 passed`/`99+ tests` сохранены только как historical
  evidence и не воспроизводились по запрету запуска legacy code.

На `ms-7e26` дополнительно установлено:

- ID tests создают временные files и проверяют entities, placeholders,
  openability и некоторые layout settings; стабильных binary fixtures,
  page/pixel goldens и cross-viewer comparisons нет;
- `F6.10_golden_weld_act.docx` — только именованный blank/reference asset и не
  используется как управляемый render golden;
- два `AOSR_test_20260610*.docx` визуально читаемы, но один содержит
  некорректно собранную строку даты и плотный непроверенный layout;
- `PRJ-001_KS2/KS3/LSR.xlsx` ошибочно лежат среди templates; текущие КС outputs
  имеют нулевые суммы/неполные реквизиты;
- 8 generated и 3 control DXF не имеют соответствующего versioned PDF golden.

Итого: готовых print-ready документов, созданных найденным механизмом и
подтверждённых reproducible golden suite, не найдено ни на одном компьютере.

## 7. Git history и потерянные assets

Ключевые наблюдения:

1. `dc33f3c` расширил registry и создал backup 25 шаблонов.
2. Отчёт того периода заявил 92 YAML files и 86/86 coverage.
3. `git log --all -- library/templates/dxf` не показывает tracked history
   активного каталога; следовательно, основной corpus, вероятно, был ignored
   или никогда не попал в git.
4. 25 backup YAML доступны только через git history после cleanup.
5. Текущий registry остался, а binaries исчезли — это dangling registry.
6. `id_pipeline_architecture.md` описывает ряд якобы завершённых классов, но
   `src/core/services/id_pipeline/` и классы `InventoryEngine`,
   `AOSRChainBuilder`, `ChronoValidator`, `DocumentLifecycleManager` в текущем
   source не найдены.
7. Remote `MAC_ASD` HEAD `a154a2a` является предком текущего local HEAD;
   remote branch `feature/legal-v2` (`932c`) также присутствует в локальном
   object database. Уникальной истории исходного кода на `king25` не найдено.
8. В remote history найдены удалённые audits/plans и re-export
   `gost_stamp.py`; они уже представлены локально либо не содержат уникальной
   реализации. Активный `library/` отсутствует и в remote worktree, и в HEAD.
9. `ProjectASD` содержит четыре коммита и не имеет deleted paths.
10. Корневой `/mnt/nvme_p4/.git` не имеет refs/logs/index и не позволяет
    доказуемо восстановить дерево или ветвь.
11. `ms-7e26:/home/oleg/MAC_ASD` — `main` @ `a9b64c26`; этот commit является
    предком local HEAD `84099c3`. `origin/night-audit` @ `a2eaee93`,
    `origin/ozhr-clean` @ `a85618e9` и `origin/feature/legal-v2` @ `932c32db`
    уже присутствуют локально.
12. Уникальная remote branch `backup-local-20260615` @ `470ae2eb` добавляет
    только инфраструктуру rclone sync и не содержит ID-generator assets.
13. Remote stash @ `72a37d28` изменяет 21 файл преимущественно модели
    проекта/ППР и не скрывает отдельный generator corpus.
14. В history `MAC_ASD` найдено 2 556 удалённых уникальных paths, включая
    reports, 25 YAML backups и старые idprosto paths. Доступные template bytes
    покрываются live gdrive corpus; 25 YAML byte-exact совпадают с локально
    восстановимыми history blobs.
15. `MAC_ASD_08052026` — `main` @ `ba6ae46`, backup branch @ `855642c`; это
    более старый snapshot. `Qwen_ASD` — `main` @ `e51caf1`, тот же predecessor,
    что `ProjectASD` на `king25`, с локальными modified/untracked source files.
    `/home/oleg/ProjectASD` не является git repository. Windows `/ASD/.git` —
    пустой repository без commits.
16. June-4 archive содержит только 25 YAML backup assets, несмотря на отчёты
    о 86/92. Остальные 67 заявленных templates не найдены ни в live trees, ни
    в проверенных archives, ни как атрибутируемые tracked blobs.

## 8. Read-only inventory компьютеров и томов

### 8.1. `king25` — завершённое обследование

- ОС: Ubuntu 26.04 LTS; kernel 7.x.
- Root filesystem: ext4, около 180.7 GiB.
- Дополнительные рабочие тома: NTFS 223 GiB, 931.5 GiB, 651.2 GiB, 78.1 GiB и
  768.6 GiB. Они были временно подключены read-only (`fuseblk,ro`) только для
  поиска, затем каждый отдельно отключён; финальный `findmnt` не вернул ни
  одного из пяти mount points.
- Проверены `/home/oleg` и все пять томов. На томах 223/651/78 GiB релевантных
  ASD/ID Markdown или repositories не найдено; системные/recovery/media areas
  исключены.
- `git` и `rg` на host отсутствуют; поиск выполнен стандартными read-only
  filesystem tools, а git-репозитории изучены через локально скопированные
  metadata/object stores.
- Исходные remote files не изменялись и не удалялись.

Найденные repositories:

| Путь | HEAD / ветки | История и уникальность |
|---|---|---|
| `/mnt/nvme_p4/MAC_ASD` | `main` @ `a154a2a`; `feature/legal-v2` @ `932c` | оба commits/objects уже есть в `/Users/oleg/mac_asd`; remote snapshot старше local |
| `/mnt/sdb1/Users/OLEG/Documents/2026/GitHub/ProjectASD` | `main` @ `e51caf1`; 4 commits | отдельный predecessor prototype; deleted paths нет |
| `/mnt/nvme_p4/.git` | refs/logs/index отсутствуют | orphan 37-GB object store; доказуемого дерева нет |

Найденные archives/backups:

- `Проекты-*.zip`: 24 object-specific PDF ПД/РД, только listing;
- `SYNC_GDRIVE.zip`: sync tooling; credential/token entries не читались и не
  копировались;
- trash archive `archive-2026-08-01_05-40-46.zip`: релевантные MD совпадают с
  текущими файлами `/home/oleg/Documents/asd-kontur`;
- отдельные `idprosto`, `asd_output`, `asd_test_output` — не archives исходного
  проекта, а уникальные data/output corpora, описанные выше.

### 8.2. `ms-7e26` — завершённое обследование

- ОС: Ubuntu 24.04.4 LTS, kernel 7.0.0-28, x86_64.
- Root: `/dev/nvme0n1p5`, ext4, 488.3 GB, около 393 GB занято и 63 GB свободно.
- Windows data: `/dev/nvme0n1p3`, NTFS, 441.6 GB. Для обследования раздел был
  подключён в отдельную точку строго `ro`, после scan отключён; финальная
  проверка подтвердила отсутствие mount и созданной точки.
- External volume `Consultant`: `/dev/sda1`, NTFS, 59 GB, уже был подключён ОС
  в `/media/oleg/Consultant`; просмотрен без записи. На нём только приложение и
  данные ConsultantPlus, релевантных ASD/generator assets нет.
- Recovery partition 795 MB, системные каталоги, caches, models, dependencies,
  virtual environments и служебные данные ОС исключены.
- Подключение выполнено обычным OpenSSH к LAN endpoint с явным source bind из
  той же подсети; `tailscale ssh` и web-auth не использовались.
- Исходные remote files, repositories и archives не изменялись; legacy-код,
  БД, models, installers и deployment не запускались.

Основные рабочие каталоги: `MAC_ASD` (12 GB, включая `.venv` и объектные
данные), `MAC_ASD_08052026` (7 GB), `Qwen_ASD` (6.9 GB), `ProjectASD` (29 GB),
`id-track` (106 MB), `asd-kontur` study logs, Desktop/Downloads/Documents.
Объектная папка `LEVASHOVO` занимает около 3.9 GB и классифицирована как
workspace-specific: её документы учитывались только агрегированно как evidence
и не переносились в platform memory.

Найденные repositories:

| Путь | HEAD / ветки | История и уникальность |
|---|---|---|
| `/home/oleg/MAC_ASD` | `main` @ `a9b64c26`; backup @ `470ae2eb`; remote audit/legal refs | основной legacy snapshot; source старше MBP, но gdrive binary corpus расширен; stash/history проверены без checkout |
| `/home/oleg/MAC_ASD_08052026` | `main` @ `ba6ae46`; backup @ `855642c` | старый v11/v12 snapshot; уникального готового generator нет |
| `/home/oleg/Qwen_ASD` | `main` @ `e51caf1`; modified/untracked source | predecessor с LLM schemas и generic AOSR renderer; совпадает по commit lineage с `ProjectASD` на `king25` |
| Windows `/ASD` | `main`, no commits | пустой инициализированный repository |

`/home/oleg/ProjectASD`, `ISUID_repo/ISUID` и adjacent `isuid_app` не имеют
собственной пригодной git history; они изучены как loose source trees.

Найденные archives/backups:

- `MAC_ASD.zip` — 3.25 GB; старый snapshot;
- `MAC_ASD_08052026.zip` — 4.98 GB; backup старой линии;
- `MAC_ASD_04062026.zip` — 7.25 GB; пять archive-only ISGenerator reports и
  25 YAML backups, selected entries прочитаны без изменения archive;
- Qwen archives — 3.86/7.32 GB; predecessor snapshots;
- ISUID archive — около 67 KB; small ASD/Antigravity backups — 24/27 KB;
  `archive-2026-08-20` — около 361 KB; ID-track deployment backups — 458–463 KB;
- object-specific ID archives 45/69/98 MB перечислены, но не перенесены;
- May-8 snapshot содержит 16 AOSR-family blank forms: 15 совпадают с
  `king25`; уникальный `1._Шаблон_акта_выполненных_работ.xlsx` — generic
  commercial acceptance act, не форма ИД, поэтому отклонён.

Windows user area дала 11 relevant Markdown и generic downloads/software, но
не второй ASD repository или generator corpus.

### 8.3. Временный staging

Staging создан вне обоих проектов в
`/tmp/asd-kontur-legacy-audit.vWo2u0`; manifest —
`/tmp/asd-kontur-legacy-audit.vWo2u0/copied_files_manifest.tsv`. Итоговый
manifest содержит 2 308 файлов
`king25` (141 480 934 B) и 1 360 файлов `ms-7e26` (87 496 345 B), всего 3 668
файлов. Каждая строка фиксирует `source_host`,
`source_path`, SHA-256, `size_bytes`, MIME type, `selection_reason` и staging
relative path. Для archive entries source path имеет форму
`archive.zip!/entry`. Секреты, `.env`, askpass helpers, credentials, caches и
dependencies исключены. Manifest и staging не добавлены в `asd-kontur`.

## 9. Изученные Markdown

Поиск выполнялся не только по filename: каждый `.md` проверен по содержимому
на ASD/АСД, ID/ИД/АОСР, templates/forms, НТД, ПД/РД, geometry, Evidence Graph,
RAG/KAG, memory, PostgreSQL/pgvector, lifecycle/archive/reset, contracts/legal,
architecture/audit/report/plan terms. Binary, cache и dependency directories
исключены. Точное совпадение копий определялось по нормализованному тексту.

### 9.1. `/Users/oleg/mac_asd` на MBP

Изучены 112 current Markdown. Полный current список:

- root/operations: `AGENTS.md`, `CLAUDE.md`, `README.md`, `STATUS.md`,
  `CHANGELOG.md`, `PROMPT_mac_asd_v4_2.md`, `worklog.md`, две ASD skill copies;
- agents: prompts `clerk`, `legal`, `logistics`, `pm`, `procurement`, `pto`,
  `smeta`, `stroycontrol`; `agent-ctx/part3-lab-test-skill.md`;
- archive: 12 `archive/**/README.md` copies, включая legacy backups,
  inventory remnants и test uploads;
- data: `benchmark_report_los.md`, `infolend_inventory/summary_report.md`,
  `sessions/session_20260518_izm_detector_v2.md`, все девять `data/wiki/*.md`;
- core docs: `ARCHITECTURE`, `COMPONENT_ARCHITECTURE`, `CORE_LOGIC_DESIGN`,
  `DATA_SCHEMA`, `BUILDING_LIFECYCLE_WORKFLOW`, `DEPLOYMENT_PLAN`,
  `DEPLOYMENT_PLAN_M5_MAX`, `MODEL_STRATEGY`, `MCP_TOOLS_SPEC`, `STRATEGY`,
  `ROADMAP_SOPROVOZHDENIE`, `id_pipeline_architecture`, `ppr_generator`;
- August/current audits: `A1_OBJECT_MATERIALISATION_2026-08`, `ASSUMPTIONS_2026-08`,
  `AUDIT_2026-08`, `B1_AUDIT_2026-08`, `DATA_INVENTORY_2026-08`,
  `DESIGN_STUDY`, `DESIGN_TARGET`, `DEVOPS_AUDIT_2026-08-10`, `DEV_PLAN`,
  `DICTIONARY_COLLISIONS`, `DUBLI_RAZRESHENY`, `FUNCTIONALITY_2026-08`,
  `KNOWLEDGE_FRAME_INVENTORY_2026-08`, `KNOWN_ANSWER_61.17-ITP_2026-08`,
  `KNOWN_ANSWER_MUSEUM_2026-08`, `KNOWN_ISSUES`, `NIGHT_2026-08-10`,
  `O1_KANDIDATY`, `PERECHEN_ID_NORMATIVES_2026-08`,
  `POSOBIE_CH5_CANDIDATES`, `R0_TRETYA_MASHINA`, `READINESS_REPORT`,
  `RESET_SCOPE_DEFECT_2026-08`, `RESUME`, `SECTION5_ATOM_AND_IDENTITY_2026-08`,
  `SH4B_KRASNOGORSK_2026-08`, `STACK_2026-08`, `STATUS_2026-08-09`,
  `STATUS_v16.1`, `STEP5_SVERKA_61.17-ITP_2026-08`, `TZ_SVERKA`,
  `WORK_JOURNAL` и `docs/README.md`;
- ADR: `ADR-001-audit-pipeline-sequence`, оба `ADR-002-*`,
  `ADR-003-vlm-qwen3-vl-vs-gemma4`;
- catalog/reports: оба `docs/id_prosto_catalog/*.md`, два legacy archive docs,
  четыре `docs/reports/2026-06-08_*.md` и reports README;
- remaining design docs: `agents.md`, deployment playbook, mobile/UI design и
  два reality reports, а также `mobile/android/README.md`.

### 9.2. `king25`

Отобрано и прочитано 155 relevant Markdown paths, 144 уникальных
нормализованных текста, 63 408 строк. Полный список по source roots:

- `/home/oleg/Downloads`: `FUNCTIONALITY_2026-08.md`,
  `LESSONS_LEVASHOVO.md`, `STACK_2026-08.md`, плюс `LV_CLAUDE.md` в home;
- `/home/oleg/Documents/asd-kontur`: `TZ_Levashovo_v8_0`,
  `TZ_Levashovo_v9_0`, `status_report_2026-07-30`,
  `status_report_2026-08-06_blocked`, `claude_code_handoff_context`,
  `asd_kontur_tech_description`, `datamining`, `datamining_12_27`,
  `papka_200_final_report`, `papka_200_split_final_report`,
  `critical_vars_gemma_vs_manual_final`, `prompt_gemma4_31B`;
- `/home/oleg/Desktop/Yandex`: `NIGHT_2026-08-10`,
  `chast_d_stepCDE_audit_06082026`, `fix_9_1_number_2026-08-07`,
  `git_setup_2026-08-08`, `idle_recovery_2026-08-07`,
  `intake_phase2_2026-08-08`, `invariant_9_1_doctype_exclusion_2026-08-07`,
  `itp_uute_and_undercut_bug_2026-08-07`, `kat_perimeter_fix_2026-08-07`,
  `kat_search_rebuild_2026-08-08`, `manual_queue_494_final_report_09082026`,
  `matrix_missing_norms_09082026`, `normative_library_audit_09082026`,
  `search_section_dropdown_fix_2026-08-07`, `step5_blocked_dwg_gate1_2026-08-07`,
  `step5_dwg_mass_complete_2026-08-08`, `step5_dwg_pilot_2026-08-08`,
  `triangulation_9_1_9_4_2026-08-07`, `undercut_fix_launched_2026-08-08`,
  `undercut_sample200_final_2026-08-08`, `undercut_stop_and_sample_2026-08-08`,
  `undercut_timeout_scope_fix_2026-08-08`,
  `undercut_tmp_contamination_fix_2026-08-08`, `zones_reading_2026-08-07`;
- `/home/oleg/.claude/projects/**/memory`: `MEMORY`,
  `feedback_asd_kontur_conventions`, `project_asd_kontur`,
  `project_asd_kontur_open_items`, `reference_asd_kontur_access`,
  `user_oleg_asd_kontur`;
- Windows memory under `/mnt/nvme_p4/Users/olegs/.claude/...`: `MEMORY`,
  `current_task`, `idprosto_knowledge_base`;
- `/mnt/sdb1/.../ProjectASD`: root `README` and docs `ARCHITECTURE`,
  `COMPONENT_ARCHITECTURE`, `CONCEPT_v10`, `CONCEPT_v11`, `DATA_SCHEMA`,
  `DEPLOYMENT_PLAN`, `DEV_STATUS`, `HERMES_MCP_INTEGRATION`, `MCP_HERMES_SETUP`,
  `MCP_OLLAMA_INTEGRATION_REPORT`, `MCP_TEST_REPORT`, `MCP_TOOLS_SPEC`,
  `MODEL_STRATEGY`, `PROMPTS_GEMMA4`, `RSS_scout_2026-05-10`,
  `RSS_scout_first_run_report_2026-05-10`;
- `/mnt/nvme_p4/MAC_ASD` root: `CLAUDE`, `README`, `STATUS`, `agents`, `worklog`;
  all eight agent prompts; docs `ARCHITECTURE_v15`,
  `BUILDING_LIFECYCLE_WORKFLOW`, `COMPONENT_ARCHITECTURE`,
  `COMPREHENSIVE_ANALYSIS_20260505`, `CORE_LOGIC_DESIGN`, `DATA_SCHEMA`,
  `DEPLOYMENT_PLAN`, `DEPLOYMENT_PLAN_M5_MAX`, `MCP_TOOLS_SPEC`,
  `MODEL_STRATEGY`, `SMETTER_API_INTEGRATION`, `STATUS`, `STRATEGY`, `dev-notes`,
  `id_pipeline_architecture`, `ppr_generator`, wiki `PTO_Rules`, оба
  `id_prosto_catalog` documents; all 18 `NBLM/*.md`; two `agent-ctx/*.md`, all
  seven `data/wiki/*.md` и `data/sessions/session_20260518_izm_detector_v2.md`;
- `/mnt/sdb1/Users/OLEG/Downloads/2026`: `ASD_v9_TechDescription`,
  `ASD_v832r_TechDescription`, `ARCHITECTURE`, `ARCHITECTURE_v15` и duplicate,
  `MAC_ASD_FULL_ARCHITECTURE`, `COMPONENT_ARCHITECTURE` и duplicate,
  `BUILDING_LIFECYCLE_WORKFLOW` и duplicate, `mac_asd_deployment_topology_v2`,
  `ppr_generator`, `id_pipeline_architecture`, `MAC_ASD_v16_Audit_Report`,
  `2026-06-04_documentation_audit` и четыре numbered copies,
  `2026-06-06_integrity_audit`, `2026-06-08_full_documentation_audit`,
  `AUDIT_REPORT`, `Техописание_Левашово_учет_ИД`, `ТЗ_Левашово_v8_0`,
  `TZ_Levashovo_v7_0`, `Левашово_Пользовательский_мануал`,
  `levashovo_audit_2026-07-11` и duplicate, `levashovo_audit_addendum_2026-07-11`,
  `объемы_папок_Левашово` и duplicate.

Четыре Markdown из Telegram transfer folder также просмотрены; они не содержат
уникальных ID-generator contracts и оставлены только в staging manifest.

### 9.3. `ms-7e26`

Полностью прочитано 426 live relevant Markdown paths и пять уникальных
archive-only ISGenerator reports: всего 431 изученный source path, 387
уникальных нормализованных текстов, 416 634 строки и 43 808 903 B. Ещё два
archive copies `id_pipeline_architecture.md` byte/semantic-дублируют изученные
версии и учтены в manifest, но не увеличивают число unique studied paths.

Распределение live paths: 77 `MAC_ASD`, 64 `Desktop/Yandex`, 49 `Downloads`,
46 `MAC_ASD_08052026`, 42 `ProjectASD`, 36 `.gemini/antigravity`, 23 `.claude`,
19 `Documents/КСК-1`, 18 `Qwen_ASD`, 12 `id-track`, 11 Windows user area,
8 `Documents/honcho`, 6 `asd-kontur`, 6 `Documents/00_ОБЩЕЕ`, 3
`Documents/ЭКОСФЕРА`, 2 `Documents/TM35` и по одному в Desktop root,
`tm35-research`, Documents root и `.hermes`.

Высокосигнальные группы: current/backup `id_pipeline_architecture`, архитектура,
аудиты и matrices; `ISUID/TZ_Levashovo_v7_0`, road map и result checks;
idprosto/template reports; `LESSONS_LEVASHOVO`; NTD-extracted Markdown из
`ProjectASD`; Qwen ID engineer docs; lifecycle/archive/reset, legal/contracts,
ПД/РД, geometry/executive schemes, RAG/domain-memory и PostgreSQL/pgvector
materials. Пять archive-only reports прочитаны полностью:
`is_generator_audit_and_plan.md`, `is_generator_stage1_complete.md`,
`is_generator_stage2_report.md`, `is_generator_stage3_report.md` и
`is_generator_86_templates_report.md`.

Ниже приведён полный source-path список 426 live Markdown. Archive-only пять
указаны абзацем выше; точные archive member paths, SHA-256, размеры и MIME
также находятся в staging manifest.

- `/home/oleg/.claude/projects/-home-oleg-MAC-ASD/memory/MEMORY.md`
- `/home/oleg/.claude/projects/-home-oleg-MAC-ASD/memory/ai_pto_strategic_transformation.md`
- `/home/oleg/.claude/projects/-home-oleg-MAC-ASD/memory/filtered_grok_recommendations.md`
- `/home/oleg/.claude/projects/-home-oleg-MAC-ASD/memory/full_technical_analysis.md`
- `/home/oleg/.claude/projects/-home-oleg-MAC-ASD/memory/grok_roadmap_v14.md`
- `/home/oleg/.claude/projects/-home-oleg-MAC-ASD/memory/pto_ai_strategy.md`
- `/home/oleg/.claude/projects/-home-oleg-MAC-ASD/memory/strategic_goal.md`
- `/home/oleg/.claude/projects/-home-oleg-Qwen-ASD/memory/MEMORY.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/MEMORY.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/architecture_decision_isuid_vs_mac_asd.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/asd_project_overview.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/feedback_no_password_paranoia.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/feedback_no_stepwise_confirmation.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/feedback_no_unsolicited_security_nagging.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/id_track_deploy_notes.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/kat_project_portfolio.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/levashovo_session_log_index.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/mac_asd_overview.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/pdfpipe_server_reference.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/reference_gdrive_kat_rclone.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/reference_perechen_id_xlsx.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/reference_tm35_monitoring_site.md`
- `/home/oleg/.claude/projects/-home-oleg/memory/verification_before_trusting_project_claims.md`
- `/home/oleg/.gemini/antigravity/brain/09cd591f-2410-4c6d-97d3-b80a9ee0a4ea/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/09cd591f-2410-4c6d-97d3-b80a9ee0a4ea/task.md`
- `/home/oleg/.gemini/antigravity/brain/09cd591f-2410-4c6d-97d3-b80a9ee0a4ea/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/0bdb2418-9bde-4b9f-a246-f349649660b6/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/0bdb2418-9bde-4b9f-a246-f349649660b6/task.md`
- `/home/oleg/.gemini/antigravity/brain/0bdb2418-9bde-4b9f-a246-f349649660b6/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/187e2de6-4583-4841-b2c5-0e256decf557/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/187e2de6-4583-4841-b2c5-0e256decf557/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/1ee0f53c-f83e-4f6e-95a3-970c4610c9ff/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/1ee0f53c-f83e-4f6e-95a3-970c4610c9ff/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/2d89fee4-7c29-4b23-9e30-6c7c4c0b64f6/IS_module_plan.md`
- `/home/oleg/.gemini/antigravity/brain/6ef4e92f-b6ac-4de6-a0c2-ab4e42d29523/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/6ef4e92f-b6ac-4de6-a0c2-ab4e42d29523/task.md`
- `/home/oleg/.gemini/antigravity/brain/6ef4e92f-b6ac-4de6-a0c2-ab4e42d29523/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/809808bf-ef68-491c-b926-252475182320/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/809808bf-ef68-491c-b926-252475182320/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/81a5bcca-56e1-4d08-bf41-f4cb3e74d8c4/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/996ae9cd-5479-4a16-8aa2-770611889805/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/996ae9cd-5479-4a16-8aa2-770611889805/task.md`
- `/home/oleg/.gemini/antigravity/brain/996ae9cd-5479-4a16-8aa2-770611889805/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/a80d1073-3ef8-48ca-9306-a2663df2586d/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/a80d1073-3ef8-48ca-9306-a2663df2586d/task.md`
- `/home/oleg/.gemini/antigravity/brain/a80d1073-3ef8-48ca-9306-a2663df2586d/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/d5516745-65ce-4b0c-bea9-d27a24bff769/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/d5516745-65ce-4b0c-bea9-d27a24bff769/task.md`
- `/home/oleg/.gemini/antigravity/brain/d5516745-65ce-4b0c-bea9-d27a24bff769/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/debc8b80-eff7-4086-8c29-5d5daaa10387/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/debc8b80-eff7-4086-8c29-5d5daaa10387/task.md`
- `/home/oleg/.gemini/antigravity/brain/debc8b80-eff7-4086-8c29-5d5daaa10387/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/e6ad0b02-6db2-43cf-b87b-f26bc5ad9757/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/e6ad0b02-6db2-43cf-b87b-f26bc5ad9757/task.md`
- `/home/oleg/.gemini/antigravity/brain/e6ad0b02-6db2-43cf-b87b-f26bc5ad9757/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/e84e8349-e10f-4cc4-bc02-1d955d91a13d/implementation_plan.md`
- `/home/oleg/.gemini/antigravity/brain/e84e8349-e10f-4cc4-bc02-1d955d91a13d/task.md`
- `/home/oleg/.gemini/antigravity/brain/e84e8349-e10f-4cc4-bc02-1d955d91a13d/walkthrough.md`
- `/home/oleg/.gemini/antigravity/brain/f52f7189-df94-422f-ab2d-a26d7350b498/implementation_plan.md`
- `/home/oleg/.hermes/memories/USER.md`
- `/home/oleg/Desktop/MAC_ASD_FULL_ARCHITECTURE.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/20.07.2026/normbase_matrix_ID.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/20.07.2026/ТЗ_Левашово_v8_0.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/ISUID_repo/ISUID/README.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/ISUID_repo/ISUID/docs/Dorozhnaya_karta_v2.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/ISUID_repo/ISUID/docs/PROMPT_CLAUDE_CODE.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/ISUID_repo/ISUID/docs/Reshenie_rezultaty_proverki.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/ISUID_repo/ISUID/docs/TZ_Levashovo_v7_0.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/OPS_NOTES_11.11_memory.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/PROMPT_CLAUDE_CODE.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/Дорожная_карта_v2.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/ОТЧЁТ_прототип_2026-07-16.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/Рекомендация_архитектура_ИСУИД_vs_MAC_ASD_2026-07-15.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/ТЗ_Левашово_v7_0.md`
- `/home/oleg/Desktop/Yandex/ASD_KAT/ШАГ_A_спецификация_реквизитов.md`
- `/home/oleg/Desktop/Yandex/CC_skill/CLAUDE.md`
- `/home/oleg/Desktop/Yandex/LEVASHOVO_08.md`
- `/home/oleg/Desktop/Yandex/LEVASHOVO_09.md`
- `/home/oleg/Desktop/Yandex/LEVASHOVO_10.md`
- `/home/oleg/Desktop/Yandex/LEVASHOVO_11.md`
- `/home/oleg/Desktop/Yandex/LEVASHOVO_12.md`
- `/home/oleg/Desktop/Yandex/LEVASHOVO_15.md`
- `/home/oleg/Desktop/Yandex/LEVASHOVO_16.md`
- `/home/oleg/Desktop/Yandex/SKILL.md`
- `/home/oleg/Desktop/Yandex/TZ_Levashovo_v8_0.md`
- `/home/oleg/Desktop/Yandex/TZ_Levashovo_v9_0.md`
- `/home/oleg/Desktop/Yandex/TZ_Levashovo_v9_1.md`
- `/home/oleg/Desktop/Yandex/aosr_aorpi_reclassify_06082026.md`
- `/home/oleg/Desktop/Yandex/asd_kontur_tech_description.md`
- `/home/oleg/Desktop/Yandex/chast_c_materializaciya_pilot_03082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_criterion_seed_cpu_04082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_deadletter_root_cause_fix_04082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_dedup_taxonomy_04082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_etap0_razvedka_03082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_final_03082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_massovyi_final_06082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_popravka2_perimetr_03082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_popravka_gate_03082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_stazhery_sample_probe_04082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_stepc_design_04082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_talon_audit_codeversion_04082026.md`
- `/home/oleg/Desktop/Yandex/chast_d_taxonomy_2fixes_04082026.md`
- `/home/oleg/Desktop/Yandex/claude_code_handoff_context.md`
- `/home/oleg/Desktop/Yandex/code_confusion_02082026.md`
- `/home/oleg/Desktop/Yandex/datamining.md`
- `/home/oleg/Desktop/Yandex/datamining_12_27.md`
- `/home/oleg/Desktop/Yandex/delta_is_gs_02082026.md`
- `/home/oleg/Desktop/Yandex/delta_klassifikaciya_02082026.md`
- `/home/oleg/Desktop/Yandex/delta_slepaya_zona_02082026.md`
- `/home/oleg/Desktop/Yandex/edinyi_poisk_02082026.md`
- `/home/oleg/Desktop/Yandex/kaskad_privyazki_22781_03082026.md`
- `/home/oleg/Desktop/Yandex/kat_search_shum_terminy_filtr_03082026.md`
- `/home/oleg/Desktop/Yandex/kat_search_undefined_fix_03082026.md`
- `/home/oleg/Desktop/Yandex/komplektnost_paketov_02082026.md`
- `/home/oleg/Desktop/Yandex/matrica_delta_status_02082026.md`
- `/home/oleg/Desktop/Yandex/papka_200_final_report.md`
- `/home/oleg/Desktop/Yandex/papka_200_split_final_report.md`
- `/home/oleg/Desktop/Yandex/poisk_kat_4ip_03082026.md`
- `/home/oleg/Desktop/Yandex/promt_chast_d_massovyi_aorpi.md`
- `/home/oleg/Desktop/Yandex/promt_matrica_delta.md`
- `/home/oleg/Desktop/Yandex/promt_shag7_priemnyi_marshrut.md`
- `/home/oleg/Desktop/Yandex/raw_integrity_gap_06082026.md`
- `/home/oleg/Desktop/Yandex/session_02082026.md`
- `/home/oleg/Desktop/Yandex/status_report_02082026.md`
- `/home/oleg/Desktop/Yandex/status_report_2026-07-30.md`
- `/home/oleg/Documents/00_ОБЩЕЕ/CHARU_r2/CONCEPT.md`
- `/home/oleg/Documents/00_ОБЩЕЕ/CHARU_r2/README_GEMINI.md`
- `/home/oleg/Documents/00_ОБЩЕЕ/CHARU_r2/SKILLS_ARCHITECTURE.md`
- `/home/oleg/Documents/00_ОБЩЕЕ/CHARU_r2/SKILLS_UI.md`
- `/home/oleg/Documents/00_ОБЩЕЕ/charu/ANDROID_STUDIO_SETUP.md`
- `/home/oleg/Documents/00_ОБЩЕЕ/charu/CHARU_CONCEPT.md`
- `/home/oleg/Documents/CLAUDE.md`
- `/home/oleg/Documents/TM-35/CLAUDE.md`
- `/home/oleg/Documents/TM-35/TECH_REPORT.md`
- `/home/oleg/Documents/honcho/.claude/skills/honcho-integration/SKILL.md`
- `/home/oleg/Documents/honcho/.claude/skills/honcho-integration/references/bot-frameworks.md`
- `/home/oleg/Documents/honcho/.claude/skills/migrate-honcho-ts/DETAILED-CHANGES.md`
- `/home/oleg/Documents/honcho/.claude/skills/migrate-honcho-ts/SKILL.md`
- `/home/oleg/Documents/honcho/CHANGELOG.md`
- `/home/oleg/Documents/honcho/README.md`
- `/home/oleg/Documents/honcho/sdks/typescript/CHANGELOG.md`
- `/home/oleg/Documents/honcho/tests/alembic/README.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/AGENTS.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/ASD_v832r_TechDescription.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/ASD_v9_TechDescription.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/CLAUDE.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/DC_KSK.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/N8N_README.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/OPENCLAW_README.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/STRATEGIC_VISION.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/architecture_KSK1.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/id-prosto-analysis.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/posobie_ID_v2.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/prompt_fix_llm_status.md`
- `/home/oleg/Documents/КСК-1/01_АСД_Project/prompt_for_gemini_telegram_import.md`
- `/home/oleg/Documents/КСК-1/02_Стройка_Причалы/STRATEGIC_VISION (1).md`
- `/home/oleg/Documents/КСК-1/02_Стройка_Причалы/ИИ для инженера ПТО_ внедрение и применение.md`
- `/home/oleg/Documents/КСК-1/02_Стройка_Причалы/УСТАНОВКА (1).md`
- `/home/oleg/Documents/КСК-1/02_Стройка_Причалы/УСТАНОВКА.md`
- `/home/oleg/Documents/КСК-1/07_Проект_Камчатка_Причалы/КАРТА_ЗНАНИЙ.md`
- `/home/oleg/Documents/КСК-1/07_Проект_Камчатка_Причалы/Раздел ПД №11.3-СМ.md`
- `/home/oleg/Documents/ЭКОСФЕРА/content_plan.md`
- `/home/oleg/Documents/ЭКОСФЕРА/Промпт_морской_юрист_Экосфера.md`
- `/home/oleg/Documents/ЭКОСФЕРА/ТЗ_Экосфера_Сайт.md`
- `/home/oleg/Downloads/1688_wholesale_research_report.md`
- `/home/oleg/Downloads/Answers.md`
- `/home/oleg/Downloads/DEVOPS_AUDIT_2026-08-10.md`
- `/home/oleg/Downloads/MAC_ASD_NTD_STUDY_LOG.md`
- `/home/oleg/Downloads/MAC_ASD_stack_MBP_05082026.md`
- `/home/oleg/Downloads/PROMPT_mac_asd_production.md`
- `/home/oleg/Downloads/README.md`
- `/home/oleg/Downloads/TZ_Levashovo_v9_2.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/Answers.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/TZ_Levashovo_v8_0.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/TZ_Levashovo_v9_0.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/asd_kontur_tech_description.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/claude_code_handoff_context.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/critical_vars_gemma_vs_manual_final.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/datamining.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/datamining_12_27.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/papka_200_final_report.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/papka_200_split_final_report.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/prompt_gemma4_31B.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/session_02082026.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/status_report_2026-07-30.md`
- `/home/oleg/Downloads/archive-2026-08-20_03-52-01/archive/ПАМЯТКА.md`
- `/home/oleg/Downloads/prompt_gemma4_31B.md`
- `/home/oleg/Downloads/promt_chast_c_materializaciya.md`
- `/home/oleg/Downloads/promt_chast_d_massovyi_aorpi.md`
- `/home/oleg/Downloads/promt_delta_IS_GS.md`
- `/home/oleg/Downloads/promt_delta_klassifikaciya.md`
- `/home/oleg/Downloads/promt_delta_slepaya_zona.md`
- `/home/oleg/Downloads/promt_edinyi_poisk.md`
- `/home/oleg/Downloads/promt_komplektnost_paketov.md`
- `/home/oleg/Downloads/АСД/01_Отчёты_аудиты/ARCHITECTURE_v15.md`
- `/home/oleg/Downloads/АСД/01_Отчёты_аудиты/ASD_v15_Full_Architectural_Audit_2026-05-27.md`
- `/home/oleg/Downloads/АСД/01_Отчёты_аудиты/ASD_v16.1_Status_Report_Claude.md`
- `/home/oleg/Downloads/АСД/01_Отчёты_аудиты/MAC_ASD_FULL_ARCHITECTURE.md`
- `/home/oleg/Downloads/АСД/01_Отчёты_аудиты/STATUS.md`
- `/home/oleg/Downloads/АСД/01_Отчёты_аудиты/АСД_v16.1_Комплексный_Аудит.md`
- `/home/oleg/Downloads/АСД/06_Система_и_разработка/audit_report.md`
- `/home/oleg/Downloads/АСД/06_Система_и_разработка/soul_template.md`
- `/home/oleg/Downloads/АСД/06_Система_и_разработка/telegram_команды.md`
- `/home/oleg/Downloads/АСД/06_Система_и_разработка/Левашово_Паспорт_системы_v28.md`
- `/home/oleg/Downloads/АСД/06_Система_и_разработка/Описание_системы_Левашово.md`
- `/home/oleg/Downloads/АСД/06_Система_и_разработка/промты_10_автоматизаций.md`
- `/home/oleg/Downloads/АСД/06_Система_и_разработка/ссылки_и_материалы.md`
- `/home/oleg/Downloads/ПАМЯТКА.md`
- `/home/oleg/Downloads/Разное/Antigravity IDE/resources/app/extensions/ms-vscode.js-debug-companion/SECURITY.md`
- `/home/oleg/Downloads/Разное/ТЕХНИЧЕСКАЯ РАСШИФРОВКА ЖУРНАЛА ОБЩИХ РАБОТ №1 (ЗАПИСИ 1–168).md`
- `/home/oleg/Downloads/Разное/ТЕХНИЧЕСКАЯ РАСШИФРОВКА ЖУРНАЛА ОБЩИХ РАБОТ №1 (ЗАПИСИ №1 – №85).md`
- `/home/oleg/Downloads/Разное/ТЕХНИЧЕСКИЙ ОТЧЕТ_ ПОЛНАЯ РАСШИФРОВКА ЖУРНАЛОВ ОБЩИХ РАБОТ (ОЖР).md`
- `/home/oleg/Downloads/Разное/Техническая расшифровка Общего журнала работ №1 (Записи №86 – №168).md`
- `/home/oleg/MAC_ASD/CHANGELOG.md`
- `/home/oleg/MAC_ASD/CLAUDE.md`
- `/home/oleg/MAC_ASD/README.md`
- `/home/oleg/MAC_ASD/STATUS.md`
- `/home/oleg/MAC_ASD/agent-ctx/part3-lab-test-skill.md`
- `/home/oleg/MAC_ASD/agents/clerk/prompt.md`
- `/home/oleg/MAC_ASD/agents/legal/prompt.md`
- `/home/oleg/MAC_ASD/agents/logistics/prompt.md`
- `/home/oleg/MAC_ASD/agents/pm/prompt.md`
- `/home/oleg/MAC_ASD/agents/procurement/prompt.md`
- `/home/oleg/MAC_ASD/agents/pto/prompt.md`
- `/home/oleg/MAC_ASD/agents/smeta/prompt.md`
- `/home/oleg/MAC_ASD/agents/stroycontrol/prompt.md`
- `/home/oleg/MAC_ASD/archive/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/docs_backup_20260604/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/docs_backup_20260604_postfix/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/docs_lab_update_backup_20260607/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/docs_sync_backup_20260605/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/docs_sync_backup_20260605/docs/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/docs_update_backup_20260606/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/docs_update_designspec_backup_20260607/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/final_sync_backup_20260606/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/full_docs_sync_backup_20260608/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/full_docs_sync_backup_20260608/docs/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/inventory_remnants/README.md`
- `/home/oleg/MAC_ASD/archive/legacy/test_uploads/README.md`
- `/home/oleg/MAC_ASD/data/benchmark_report_los.md`
- `/home/oleg/MAC_ASD/data/infolend_inventory/summary_report.md`
- `/home/oleg/MAC_ASD/data/sessions/session_20260518_izm_detector_v2.md`
- `/home/oleg/MAC_ASD/data/wiki/Archive_Rules.md`
- `/home/oleg/MAC_ASD/data/wiki/Hermes_Core.md`
- `/home/oleg/MAC_ASD/data/wiki/Jurist_Rules.md`
- `/home/oleg/MAC_ASD/data/wiki/Logistics_Rules.md`
- `/home/oleg/MAC_ASD/data/wiki/PTO_Rules.md`
- `/home/oleg/MAC_ASD/data/wiki/Procurement_Rules.md`
- `/home/oleg/MAC_ASD/data/wiki/SK_Remarks_Patterns.md`
- `/home/oleg/MAC_ASD/data/wiki/Smeta_Rules.md`
- `/home/oleg/MAC_ASD/data/wiki/index.md`
- `/home/oleg/MAC_ASD/docs/ARCHITECTURE.md`
- `/home/oleg/MAC_ASD/docs/BUILDING_LIFECYCLE_WORKFLOW.md`
- `/home/oleg/MAC_ASD/docs/COMPONENT_ARCHITECTURE.md`
- `/home/oleg/MAC_ASD/docs/CORE_LOGIC_DESIGN.md`
- `/home/oleg/MAC_ASD/docs/DATA_SCHEMA.md`
- `/home/oleg/MAC_ASD/docs/DEPLOYMENT_PLAN.md`
- `/home/oleg/MAC_ASD/docs/DEPLOYMENT_PLAN_M5_MAX.md`
- `/home/oleg/MAC_ASD/docs/KNOWN_ISSUES.md`
- `/home/oleg/MAC_ASD/docs/MCP_TOOLS_SPEC.md`
- `/home/oleg/MAC_ASD/docs/MODEL_STRATEGY.md`
- `/home/oleg/MAC_ASD/docs/README.md`
- `/home/oleg/MAC_ASD/docs/ROADMAP_SOPROVOZHDENIE.md`
- `/home/oleg/MAC_ASD/docs/SMETTER_API_INTEGRATION.md`
- `/home/oleg/MAC_ASD/docs/STATUS_v16.1.md`
- `/home/oleg/MAC_ASD/docs/STRATEGY.md`
- `/home/oleg/MAC_ASD/docs/adr/ADR-001-audit-pipeline-sequence.md`
- `/home/oleg/MAC_ASD/docs/adr/ADR-002-id-requirements-single-source-and-evidence-gating.md`
- `/home/oleg/MAC_ASD/docs/adr/ADR-002-key-mapping.md`
- `/home/oleg/MAC_ASD/docs/agents.md`
- `/home/oleg/MAC_ASD/docs/archive/COMPREHENSIVE_ANALYSIS_20260505_legacy.md`
- `/home/oleg/MAC_ASD/docs/archive/dev-notes_legacy.md`
- `/home/oleg/MAC_ASD/docs/deployment_playbook.md`
- `/home/oleg/MAC_ASD/docs/id_pipeline_architecture.md`
- `/home/oleg/MAC_ASD/docs/id_prosto_catalog/ID_Kits_by_Work_Type.md`
- `/home/oleg/MAC_ASD/docs/id_prosto_catalog/id_prosto_complete_catalog.md`
- `/home/oleg/MAC_ASD/docs/mobile/android_client_architecture.md`
- `/home/oleg/MAC_ASD/docs/ppr_generator.md`
- `/home/oleg/MAC_ASD/docs/reality_check_report_v16.md`
- `/home/oleg/MAC_ASD/docs/reality_gap_report_v16.md`
- `/home/oleg/MAC_ASD/docs/reports/2026-06-08_FINAL_HONEST_AUDIT.md`
- `/home/oleg/MAC_ASD/docs/reports/2026-06-08_nce_and_scraper_implementation.md`
- `/home/oleg/MAC_ASD/docs/reports/2026-06-08_scraping_integration_results.md`
- `/home/oleg/MAC_ASD/docs/reports/2026-06-08_storage_cleanup.md`
- `/home/oleg/MAC_ASD/docs/reports/README.md`
- `/home/oleg/MAC_ASD/docs/ui/desktop_interface_design.md`
- `/home/oleg/MAC_ASD/docs/wiki/PTO_Rules.md`
- `/home/oleg/MAC_ASD/mobile/android/README.md`
- `/home/oleg/MAC_ASD/worklog.md`
- `/home/oleg/MAC_ASD_08052026/.hermes/audit_report.md`
- `/home/oleg/MAC_ASD_08052026/.hermes/audit_report_2026-05-03.md`
- `/home/oleg/MAC_ASD_08052026/.hermes/plans/2026-05-02_autonomous-inventory-vlm.md`
- `/home/oleg/MAC_ASD_08052026/.hermes/plans/2026-05-02_evidence-graph-v2-architecture.md`
- `/home/oleg/MAC_ASD_08052026/CLAUDE.md`
- `/home/oleg/MAC_ASD_08052026/README.md`
- `/home/oleg/MAC_ASD_08052026/STATUS.md`
- `/home/oleg/MAC_ASD_08052026/agents.md`
- `/home/oleg/MAC_ASD_08052026/agents/archive/prompt.md`
- `/home/oleg/MAC_ASD_08052026/agents/auditor/prompt.md`
- `/home/oleg/MAC_ASD_08052026/agents/legal/prompt.md`
- `/home/oleg/MAC_ASD_08052026/agents/logistics/prompt.md`
- `/home/oleg/MAC_ASD_08052026/agents/pm/prompt.md`
- `/home/oleg/MAC_ASD_08052026/agents/procurement/prompt.md`
- `/home/oleg/MAC_ASD_08052026/agents/pto/prompt.md`
- `/home/oleg/MAC_ASD_08052026/agents/smeta/prompt.md`
- `/home/oleg/MAC_ASD_08052026/data/benchmark_report_los.md`
- `/home/oleg/MAC_ASD_08052026/data/wiki/Archive_Rules.md`
- `/home/oleg/MAC_ASD_08052026/data/wiki/Hermes_Core.md`
- `/home/oleg/MAC_ASD_08052026/data/wiki/Jurist_Rules.md`
- `/home/oleg/MAC_ASD_08052026/data/wiki/Logistics_Rules.md`
- `/home/oleg/MAC_ASD_08052026/data/wiki/PTO_Rules.md`
- `/home/oleg/MAC_ASD_08052026/data/wiki/Procurement_Rules.md`
- `/home/oleg/MAC_ASD_08052026/data/wiki/Smeta_Rules.md`
- `/home/oleg/MAC_ASD_08052026/data/wiki/index.md`
- `/home/oleg/MAC_ASD_08052026/docs/BUILDING_LIFECYCLE_WORKFLOW.md`
- `/home/oleg/MAC_ASD_08052026/docs/COMPONENT_ARCHITECTURE.md`
- `/home/oleg/MAC_ASD_08052026/docs/COMPREHENSIVE_ANALYSIS_20260505.md`
- `/home/oleg/MAC_ASD_08052026/docs/CONCEPT_v12.md`
- `/home/oleg/MAC_ASD_08052026/docs/CORE_LOGIC_DESIGN.md`
- `/home/oleg/MAC_ASD_08052026/docs/DATA_SCHEMA.md`
- `/home/oleg/MAC_ASD_08052026/docs/DEPLOYMENT_PLAN.md`
- `/home/oleg/MAC_ASD_08052026/docs/MCP_TOOLS_SPEC.md`
- `/home/oleg/MAC_ASD_08052026/docs/MODEL_STRATEGY.md`
- `/home/oleg/MAC_ASD_08052026/docs/PROMPTS_GEMMA4.md`
- `/home/oleg/MAC_ASD_08052026/docs/STATUS.md`
- `/home/oleg/MAC_ASD_08052026/docs/STRATEGY.md`
- `/home/oleg/MAC_ASD_08052026/docs/dev-notes.md`
- `/home/oleg/MAC_ASD_08052026/docs/id_pipeline_architecture.md`
- `/home/oleg/MAC_ASD_08052026/docs/id_prosto_catalog/ID_Kits_by_Work_Type.md`
- `/home/oleg/MAC_ASD_08052026/docs/id_prosto_catalog/id_prosto_complete_catalog.md`
- `/home/oleg/MAC_ASD_08052026/docs/ppr_generator.md`
- `/home/oleg/MAC_ASD_08052026/docs/wiki/PTO_Rules.md`
- `/home/oleg/MAC_ASD_08052026/gemma4_recomends.md`
- `/home/oleg/MAC_ASD_08052026/library/README.md`
- `/home/oleg/MAC_ASD_08052026/library/normative/INDEX_MISSING.md`
- `/home/oleg/ProjectASD/ASD_v832r_TechDescription.md`
- `/home/oleg/ProjectASD/README.md`
- `/home/oleg/ProjectASD/data/processed/gkodeksrf_2982d8c5.md`
- `/home/oleg/ProjectASD/data/processed/gkodeksrf_5fa5b8db.md`
- `/home/oleg/ProjectASD/data/processed/gkodeksrf_70a63936.md`
- `/home/oleg/ProjectASD/data/processed/gkodeksrf_839f5946.md`
- `/home/oleg/ProjectASD/data/processed/gkodeksrf_85b1815f.md`
- `/home/oleg/ProjectASD/data/processed/gkodeksrf_b0f823fd.md`
- `/home/oleg/ProjectASD/data/processed/gkodeksrf_b8af9d3c.md`
- `/home/oleg/ProjectASD/data/processed/gkodeksrf_c75413bc.md`
- `/home/oleg/ProjectASD/data/processed/gkodeksrf_f5cfc87b.md`
- `/home/oleg/ProjectASD/data/processed/grkodeksrf_4bb281f2.md`
- `/home/oleg/ProjectASD/data/processed/grkodeksrf_6d3ad276.md`
- `/home/oleg/ProjectASD/data/processed/grkodeksrf_b7c3ee40.md`
- `/home/oleg/ProjectASD/data/processed/СП4513330_1e452f00.md`
- `/home/oleg/ProjectASD/data/processed/СП4513330_847ff43b.md`
- `/home/oleg/ProjectASD/data/processed/СП4513330_b46698d1.md`
- `/home/oleg/ProjectASD/data/processed/СП4513330_ceb2689c.md`
- `/home/oleg/ProjectASD/data/processed/СП4513330_f7532238.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_501a7372.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_515445bb.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_6c35a664.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_6f53d360.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_88838e6a.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_8f012966.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_a48dcf30.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_ad3b327d.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_aebbc800.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_b857f0c6.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_c218c47e.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_c4ba25c2.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_c7b70a1c.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_d61846ae.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_d96bbceb.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_ea2bff93.md`
- `/home/oleg/ProjectASD/data/processed/СП4813330_ff8127bc.md`
- `/home/oleg/ProjectASD/docs/LARGE_PDF_PROCESSING.md`
- `/home/oleg/ProjectASD/docs/RAG_CHAT_FEATURES.md`
- `/home/oleg/ProjectASD/docs/SOURCES_GUIDE.md`
- `/home/oleg/ProjectASD/docs/ZERO_HALLUCINATION_ARCHITECTURE.md`
- `/home/oleg/ProjectASD/src/modules/estimator/README.md`
- `/home/oleg/ProjectASD/src/modules/pto/README.md`
- `/home/oleg/Qwen_ASD/README.md`
- `/home/oleg/Qwen_ASD/docs/ARCHITECTURE.md`
- `/home/oleg/Qwen_ASD/docs/ARCHITECTURE_COMPARISON.md`
- `/home/oleg/Qwen_ASD/docs/COMPONENT_ARCHITECTURE.md`
- `/home/oleg/Qwen_ASD/docs/CONCEPT_v10.md`
- `/home/oleg/Qwen_ASD/docs/CONCEPT_v11.md`
- `/home/oleg/Qwen_ASD/docs/DATA_SCHEMA.md`
- `/home/oleg/Qwen_ASD/docs/DEPLOYMENT_PLAN.md`
- `/home/oleg/Qwen_ASD/docs/DEV_STATUS.md`
- `/home/oleg/Qwen_ASD/docs/HERMES_MCP_INTEGRATION.md`
- `/home/oleg/Qwen_ASD/docs/MCP_HERMES_SETUP.md`
- `/home/oleg/Qwen_ASD/docs/MCP_OLLAMA_INTEGRATION_REPORT.md`
- `/home/oleg/Qwen_ASD/docs/MCP_TEST_REPORT.md`
- `/home/oleg/Qwen_ASD/docs/MCP_TOOLS_SPEC.md`
- `/home/oleg/Qwen_ASD/docs/MODEL_STRATEGY.md`
- `/home/oleg/Qwen_ASD/docs/PROMPTS_GEMMA4.md`
- `/home/oleg/Qwen_ASD/docs/WORKFLOW_DRAFT.md`
- `/home/oleg/Qwen_ASD/frontend/README.md`
- `/home/oleg/asd-kontur/MAC_ASD_DOMAIN_READING_LOG(1).md`
- `/home/oleg/asd-kontur/MAC_ASD_DOMAIN_READING_LOG(2).md`
- `/home/oleg/asd-kontur/MAC_ASD_DOMAIN_READING_LOG(3).md`
- `/home/oleg/asd-kontur/MAC_ASD_DOMAIN_READING_LOG.md`
- `/home/oleg/asd-kontur/MAC_ASD_NTD_STUDY_LOG (1).md`
- `/home/oleg/asd-kontur/MAC_ASD_NTD_STUDY_LOG (2).md`
- `/home/oleg/id-track/ARCHITECTURE.md`
- `/home/oleg/id-track/DEPLOYMENT.md`
- `/home/oleg/id-track/ID_Track_Deployment_v0.2.0_2026-08-11/ARCHITECTURE.md`
- `/home/oleg/id-track/ID_Track_Deployment_v0.2.0_2026-08-11/DEPLOYMENT.md`
- `/home/oleg/id-track/ID_Track_Deployment_v0.2.0_2026-08-11/PROMPTS_CODEX.md`
- `/home/oleg/id-track/ID_Track_Deployment_v0.2.0_2026-08-11/README.md`
- `/home/oleg/id-track/ID_Track_Deployment_v0.2.0_2026-08-11/UPDATE_FROM_V0.1.md`
- `/home/oleg/id-track/PROMPTS_CODEX.md`
- `/home/oleg/id-track/README.md`
- `/home/oleg/id-track/UPDATE_FROM_V0.1.md`
- `/home/oleg/id-track/audit/CLAUDE_DEPLOYMENT_REPORT.md`
- `/home/oleg/id-track/audit/README.md`
- `/home/oleg/tm35-research/docs/GDRIVE_INVENTORY.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/.gemini/GEMINI.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/.gemini/antigravity/brain/fc183de3-669f-4288-89a1-bd48fe32c132/implementation_plan.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/.gemini/antigravity/brain/fc183de3-669f-4288-89a1-bd48fe32c132/task.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/.gemini/antigravity/brain/fc183de3-669f-4288-89a1-bd48fe32c132/walkthrough.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/Downloads/BUILDING_LIFECYCLE_WORKFLOW.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/Downloads/Mastering RAG for AI Agents_ Build Smarter, Data-Driven AI -- Jason Brener/input.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/Downloads/Qwen_markdown_20251201_st2qdx47k.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/Downloads/Telegram Desktop/Сравнение GPT Plus и GPT Business на 2026 год.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/Downloads/construction_ai_system_complete_instruction.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/Downloads/frontend/frontend/README.md`
- `/mnt/asd_audit_nvme_p3/Users/Oleg/Downloads/stack_analysis.md`

## 10. Уникальные артефакты и отличия компьютеров

### 10.1. Уникально на `king25` относительно MBP

- 231 `idprosto/id_forms` binary (149 DOCX + 82 XLSX): точных SHA-совпадений на
  MBP нет;
- 84 `idprosto/id_samples` PDF: точных SHA-совпадений на MBP нет;
- 54 `asd_output` DOCX и 274 `asd_test_output` artifacts: точных SHA-совпадений
  на MBP нет;
- independent `ProjectASD` predecessor repository;
- remote `MAC_ASD` source/history не уникальны относительно local object
  database, несмотря на отличия line endings и более старый worktree.

### 10.2. Уникально на MBP относительно `king25`

- текущая развитая версия `ISGenerator`, его tests и local commits после
  `a154a2a`;
- 25 recoverable history-only YAML parametric drawing templates;
- три current 344/пр-like parameterized binaries в `library/templates/acts`;
- 153-form registry, 113 work-type mappings и более новый
  `idprosto_worktype_docs.json`: 68 work types и 402 references вместо remote
  31/356;
- текущие ASD-KONTUR architecture/lifecycle/domain documents.

### 10.3. `ms-7e26`

Уникально относительно текущего MBP и, где указано, `king25`:

- 119 universal-looking blank XLSX forms в `data/gdrive/templates`, которых
  нет среди 82 форм `king25`; они не имеют mappings/formulas/data validation,
  поэтому являются source candidates, а не готовыми templates;
- один static template PDF variant, отсутствующий на `king25`; AcroForm нет;
- две заполненные AOSR test DOCX и три generated PRJ XLSX; это defect/output
  evidence, не универсальные assets;
- 8 generated + 3 control DXF current sample set без governed PDF goldens;
- пять archive-only ISGenerator stage/audit reports; 25 archive YAML не
  уникальны по bytes относительно local git history;
- `ISUID` lifecycle/promotion prototype и `id-track` XLSX schedule tooling;
- modified/untracked `Qwen_ASD` source отличается от snapshot `king25`, но не
  образует квалифицированного генератора и требует отдельного code review;
- backup branch `470ae2eb` уникальна по commit, но содержит лишь rclone sync
  infrastructure и не рекомендуется к переносу в generator core.

Live `MAC_ASD` source в основном старше MBP. Расширенный gdrive corpus не имеет
точных SHA-совпадений с current `/Users/oleg/mac_asd`, поэтому его последующий
перенос допустим только в контролируемый quarantine staging с сохранением
manifest, а не в active registry.

## 11. Готовность ID Generator

| Capability | Реально работает | Частично/только описано | Итог |
|---|---|---|---|
| Parametric executive schemes | DXF generation, annotations, parsers, PDF attempt, tests | missing active YAML corpus; weak evidence/geometry gates | переносить алгоритмы после contract hardening |
| DOCX AOSR/AOOK | `docxtpl` fill для 2 local candidates; generic `python-docx` outputs | official authority/layout equivalence; AOOK limited; state accumulation bug in old pipeline | не production-ready |
| XLSX AOSR | current builder/filler creates 2-page print-configured workbook | only AOSR; object-contaminated default context; no viewer goldens | strong modernization candidate |
| PDF | static backgrounds/overlay in ISGenerator; 84 static examples found | no AcroForms in remote corpus; no generalized form mapping | adapter-specific work required |
| Template registry | filename/work-type lookup and 153/113 metadata exist | registry availability drifts; binary activation/version/authority absent | rebuild as governed registry |
| Field mappings | 29-field AOSR context and schemas exist | remote blank corpus has none; evidence source per field absent | introduce typed, versioned bindings |
| Validators | structural DXF/placeholder/openability/print settings | chronology, authority, evidence, layout, formulas, cross-doc totals absent | fail-closed suite required |
| Packaging | ZIP output works | content correctness/finalization not proven | retain only packaging primitive |
| Lifecycle/promotion | `ISUID` показывает staging→promotion и check-results skeleton | template/version/evidence/render contracts не интегрированы; SQL не оценивался как target model | preserve concepts, redesign boundary |
| Print-ready output | blank layouts and static references render | generated AOSR/KS forms materially incomplete; no golden suite | **not demonstrated** |

Значения в legacy генераторах поступают из caller dictionaries, LLM-extracted
JSON, project chunks и hard-coded/default fixture contexts. Только первый путь
может стать production input после typed validation и field-level provenance.
LLM extraction допустима лишь как candidate proposal; hard-coded object values
должны быть удалены из production defaults.

## 12. Preserve, modernize, reject и controlled staging

### Preserve

- immutable bytes + hashes + source paths `idprosto` forms/samples в quarantine;
- git provenance, deleted reports и 25 history YAML как recovery evidence;
- deterministic geometry/math and OOXML/XLSX layout-building algorithms;
- format/openability tests и небольшие sanitized defect samples;
- metadata catalogs как discovery evidence, не нормативная истина.
- пять archive-only stage/audit reports `ms-7e26` и один дедуплицированный
  набор из 25 YAML как provenance/recovery evidence.

### Modernize

- Template Registry: separate source original, parametrized derivative,
  TemplateVersion, authority, applicability and activation state;
- typed field schemas/bindings with source Evidence IDs and confirmation state;
- stateless DOCX/XLSX/PDF/DXF renderers; one fresh document per GenerationRun;
- validation: required fields, dates/chronology, cross-document consistency,
  formula/merge/print settings, render-page/pixel goldens and viewer variance;
- generated output lifecycle: Candidate → review → authorized finalization →
  immutable export/archive; generation never equals approval;
- sanitized fixtures instead of project organizations, people and values.
- lifecycle/promotion concepts из ISUID и безопасные XLSX parsing/repair
  patterns из `id-track`, но не их storage/deployment implementation целиком.

### Reject

- file existence/ZIP success as readiness;
- hidden reconstruction, audit suppression or invented documents/dates;
- registry membership as proof of binary availability or normative authority;
- object-specific outputs as platform templates/memory;
- silent model/render fallbacks and unconfirmed geometry;
- orphan object store and duplicate remote source snapshots.
- filled outputs, generated PRJ workbooks и generic commercial acceptance act,
  ошибочно размещённые/названные как templates;
- generic `python-docx` reconstruction как подмена авторитетного source layout.

### Recommended later controlled transfer

1. `idprosto/id_forms` and only sanitized `id_samples` → quarantine with current
   manifest; source-authority and leakage review before any promotion.
2. Selected cumulative-AOSR and zero-KS outputs → tiny defect regression corpus.
3. `ProjectASD` extraction prompts/schemas → design evidence only; do not port
   generic renderer unchanged.
4. Local 25 YAML history candidates and three active binary candidates → same
   immutable/source/derivative qualification process.
5. Field schemas, mappings and parsers/renderers → port only against target
   contracts after architecture acceptance.
6. 119 уникальных blank XLSX и один unique PDF с `ms-7e26` → отдельная
   quarantine batch; сначала leakage, authority, edition, layout и semantic
   dedup review, затем cell/coordinate mapping.
7. Пять archive-only reports и 25 YAML → recovery dossier; не переносить
   дублирующие bytes и не восстанавливать заявленные 67 отсутствующих assets
   путём догадки.
8. `ISUID`, `id-track` и Qwen schemas → переносить только выбранные contracts,
   algorithms и sanitized tests после code review; legacy SQL/deployment и
   generic renderer не переносить.

Migration gate remains `G-00-ID → G-01 → G-03 → Template Migration
qualification`. Никакой asset не переносится напрямую в active registry.

## 13. Итоговая граница доказанности

MBP, `king25` и `ms-7e26` обследованы. Архитектурный вывод теперь основан на
фактических source, tests, binaries, outputs, git history и archives всех трёх
сред: есть переносимые algorithms и крупный corpus source/reference forms, но
нет доказанного end-to-end print-ready ID Generator.

Оставшиеся вопросы являются не пробелом файлового поиска, а qualification
work: официальный источник и редакция каждой формы, права использования,
field bindings, evidence authority, viewer/render equivalence и controlled
goldens. До прохождения этих gates ни один найденный binary, mapping или
historical report не получает статус active. Целевая архитектура зафиксирована
в `docs/architecture/ID_GENERATION_AND_TEMPLATE_PLATFORM_SPECIFICATION_v0.1.md`;
Logical Data Model, ORM, DDL, migrations и прикладная реализация в рамках этого
аудита не начинались.
