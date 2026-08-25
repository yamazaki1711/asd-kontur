# АСД-КОНТУР — ID Generation & Template Platform Specification v0.1

> **Foundation specification.** Product UI/API/render/print requirements are
> added by [v0.2](ID_GENERATION_AND_TEMPLATE_PLATFORM_SPECIFICATION_v0.2.md).
> v0.1 does not establish a production-ready generator.

- **Статус документа:** `Accepted architecture baseline`
- **Дата:** 2026-08-22
- **Владелец продукта:** Олег Щербаков
- **Архитектурное основание:** ADR-0010
- **Область:** обязательная capability общего ядра для режимов `Tender`,
  `Support`, `Audit`, `Restoration`
- **Evidence baseline:** завершённый read-only аудит `/Users/oleg/mac_asd`,
  `king25` и `ms-7e26`, зафиксированный в
  `../reports/LEGACY_ID_GENERATOR_ASSET_INVENTORY_v0.1.md`

## 0. Назначение и нормативная сила

Документ определяет архитектурный контракт выбора, версионирования,
заполнения, проверки, профессиональной финализации, печати, экспорта и
архивирования исполнительной документации и исполнительных схем.

Это принятый prerequisite для Logical Data Model. Документ не является ORM-схемой,
DDL, миграцией, API implementation, выбором конкретной очереди или разрешением
переносить legacy binaries в active registry.

Положения ADR-0010 имеют статус `Accepted`. Термины `Invariant` и `Required`
ниже обязательны для будущей реализации. Exact authority, редакция, права
использования и applicability конкретной формы остаются evidence-dependent
policy data: архитектурное принятие не делает найденный файл официальным.

Спецификация подготовлена после изучения обоих удалённых компьютеров. Она не
опирается на недоказанное допущение о наличии готового legacy генератора.

## 1. Результат решения

`ID Generation & Template Platform` входит в единое общее ядро и предоставляет
четырём режимам один semantic contract при разных целях:

| Режим | Использование capability | Допустимый результат |
|---|---|---|
| `Tender` | прогноз применимых форм, состава ИД, evidence и трудоёмкости | requirement/gap plan; не заполненная фиктивными фактами ИД |
| `Support` | формирование текущей ИД из подтверждённых фактов и измерений | candidate, затем профессионально финализированный документ |
| `Audit` | проверка существующих документов, редакций, полей и layout | findings, gaps, comparison; оригинал не переписывается |
| `Restoration` | восстановление структуры и предложение значений из evidence | только candidates с uncertainty; скрытая реконструкция запрещена |

Канонический процесс:

`RequiredDocumentType → applicability → TemplateVersion → binding plan →`
`confirmed facts/evidence → deterministic fill → structural/content/layout`
`validation → GeneratedDocumentCandidate → professional authority →`
`FinalizedDocument → export/print/archive`.

`methodological_practice` из проверенного `MethodologicalPracticeGuide`
обязательно подбирается deterministic Context Assembly до любой ID-related VLM
операции. `IDPracticeContextPack` может содержать workflow, RequiredInput,
EvidenceRequirement, form/field completion guidance, common errors, allowed
variants, rationale, signer guidance, review checklists и visual-example
locators с exact page/region EvidencePack. Этот слой не выбирает нормативную
применимость формы, не подменяет `FieldSchema`/`BindingPlan`, не создаёт Fact и
не заполняет неизвестное значение.

ID Generator rejects a VLM path without an exact `ContextAssemblyPolicy` and
source-edition pin. Missing relevant practice returns `knowledge_incomplete`;
a conflict with NTD returns `guidance_normative_conflict` with requirement and
advice separated; an edition conflict returns `edition_mismatch`. Verified
practice, NTD requirements and workspace facts remain separate input
partitions throughout binding, validation and finalization.

`GeneratedDocumentCandidate` никогда не равен `FinalizedDocument`. Успешная
запись файла, открытие ZIP или отсутствие exception не являются финализацией
и не доказывают print-ready.

## 2. Цели и non-goals

### 2.1. Цели

1. Сохранить неизменяемый официальный source и доказать его происхождение.
2. Выбирать точную применимую редакцию формы без неоднозначного `latest`.
3. Связать каждое материальное поле с подтверждённым фактом и evidence.
4. Заполнять DOCX, XLSX, fillable PDF, non-fillable PDF и геометрические схемы
   отдельными adapters без потери их форматной семантики.
5. Получать воспроизводимый candidate и проверяемый print representation.
6. Разделить machine validation и профессиональную authority.
7. Сохранить полный lineage от requirement до финального export/archive.
8. Изолировать project data одного ОКС от platform templates и других
   workspaces.

### 2.2. Non-goals v0.1

- автоматическое утверждение нормативной применимости моделью;
- генерация неизвестных дат, объёмов, МТР, измерений, подписантов или геометрии;
- один универсальный renderer для всех форматов;
- превращение заполненного документа в platform template;
- прямой доступ LLM/VLM к SQL или object storage;
- электронное подписание: внешние подписи могут проверяться отдельной
  capability, но signing keys и право подписи не входят в эту спецификацию;
- выбор таблиц, колонок, индексов, PostgreSQL/pgvector schema или migrations.

## 3. Evidence baseline и уроки legacy

| Наблюдение | Архитектурное следствие |
|---|---|
| `ISGenerator` имеет DXF/PDF пути, parsers и tests, но active YAML corpus отсутствует | registry membership отделяется от физической доступности и qualification |
| 25 YAML восстановимы; отчёты заявляют 86/92 без найденных bytes | historical report — evidence, но не activation proof |
| DOCX через `docxtpl` и XLSX через `openpyxl` реально создаются | adapters можно модернизировать, но source, binding и render gates обязательны |
| stateful `OutputPipeline` накапливает предыдущие АОСР | renderer stateless; один fresh document на один run/output |
| blank corpus: 149 DOCX и 82 XLSX на `king25`; ещё 119 XLSX на `ms-7e26` | discovery corpus проходит quarantine, authority, mapping и golden qualification |
| blank DOCX не имеют полей, XLSX — mappings/formulas, PDF — AcroForms | наличие макета не означает автоматическое заполнение |
| generated АОСР/КС открываются, но имеют layout/date/total defects | openability — только нижний structural gate |
| `ISUID` имеет staging/promotion, `id-track` — XLSX mechanics, Qwen — JSON schemas | переносить contracts/algorithms раздельно; ни один prototype не становится ядром целиком |
| object-specific документы многочисленны | использовать только как изолированное evidence/defect reference; не platform memory |

## 4. Инварианты доверия

1. **Invariant:** Template discovery не означает qualification или activation.
2. **Invariant:** original source bytes неизменяемы; параметризованная
   производная — отдельная версия с lineage к source.
3. **Invariant:** каждый generation run закрепляет точные versions template,
   field schema, binding rules, applicability rules, validator и renderer
   profile; mutable aliases запрещены.
4. **Invariant:** каждое материальное поле имеет `EvidenceBinding` либо явный
   `Gap`; неизвестное не превращается в пустую строку, ноль или догадку.
5. **Invariant:** AI создаёт только Candidate с provenance/confidence и не
   подтверждает факт, подпись, геометрию или нормативную применимость.
6. **Invariant:** renderer stateless и deterministic для одинакового
   normalized input и execution profile.
7. **Invariant:** format-specific semantics не стираются общим API.
8. **Invariant:** fail-closed blockers не могут быть понижены warning-ом
   caller или silent fallback.
9. **Invariant:** профессиональная финализация требует human identity,
   действующего grant/qualification, passed validators и immutable review set.
10. **Invariant:** platform memory не содержит заполненные значения ОКС.
11. **Invariant:** workspace reset удаляет values, candidates, intermediate
    renders и caches, но не platform TemplateVersion.
12. **Invariant:** audit сохраняет identifiers, versions, digests и decisions,
    но после reset не удерживает уничтожаемое project content.
13. **Invariant:** смена VLM/provider не меняет canonical Practice Intelligence
    или deterministic field-level `IDPracticeContextPack` для одинаковых
    inputs и policy pins.
14. **Invariant:** visual completion example is guidance with an exact locator,
    never evidence that a workspace field is true or a normative form is
    applicable.

## 5. Владение и изоляция

### 5.1. Platform scope

Platform memory может владеть:

- immutable template source и его provenance;
- parameterized derivative и transformation record;
- field schema, binding-rule definitions и renderer/validator profiles;
- applicability rules и RequiredDocumentType catalog;
- sanitized fixtures, qualified goldens и compatibility baselines;
- authority, edition, rights и activation decisions;
- verified methodological guide sources/guidance with non-normative authority;
- universal parsers/renderers без project values.

### 5.2. Workspace scope

Workspace владеет:

- project sources, facts, candidates, conflicts и gaps;
- organizations, people, contracts, ПД/РД, НТД applicability decisions;
- measurements, materials, dates, volumes и geometry;
- generation requests/runs, field resolutions и review decisions;
- filled candidates, renders, finalized documents и export packages.

Заполненный документ не продвигается в platform scope. Вывод универсального
template из project document требует отдельного acquisition workflow,
sanitization/leakage tests, authority evidence и PromotionDecision.

## 6. Логические компоненты

| Компонент | Ответственность | Не имеет права |
|---|---|---|
| Template Intake & Qualification | ingest, hash, MIME/format checks, provenance, source/derivative split | активировать asset без review |
| Governed Template Registry | identity, versions, states, authority, applicability refs | хранить workspace values |
| Requirement & Applicability Engine | определить обязательные/условные документы для exact context/rule versions | выдумывать факт ради применимости |
| Binding Planner | сопоставить semantic fields, coordinates/cells/controls и rules | читать произвольный storage |
| Fact Resolver & Evidence Gateway | разрешить confirmed values, conflicts, gaps и locators | повышать Candidate до confirmed |
| Generation Orchestrator | freeze input set, вызвать adapter/validators, собрать lineage | финализировать документ |
| Format Adapters | детерминированно заполнить конкретный формат | менять source original |
| Validation Service | structural, content, cross-document, authority и layout checks | скрывать blocker |
| Render Service | создать канонический print representation по profile | считать viewer preview оригиналом |
| Professional Review & Finalization | review immutable candidate set, принять/отклонить | подтверждать вне grant/scope |
| Export/Package Service | exact bytes, manifest, print/export package | менять finalized bytes |
| Audit/Event Service | content-minimized immutable decisions и lineage | становиться альтернативным SoR |

Model/OCR/VLM вызываются только через ограниченный provider contract и могут
предлагать classifications/mappings/values. Fact Resolver принимает их как
Candidate, а не как authoritative input.

## 7. Концептуальные records, не Logical Data Model

Ниже перечислены обязательные смысловые records. Имена не задают таблицы.

| Record | Минимальная семантика |
|---|---|
| `RequiredDocumentType` | stable identity, назначение, class, applicable rule refs |
| `TemplateSource` | immutable bytes digest, acquisition locator, MIME, owner/right/source evidence |
| `TemplateVersion` | source/derivative lineage, edition/effective interval, state, format, authority decision |
| `FieldSchema` | stable field keys, types, cardinality, materiality, formatting and missing policy |
| `BindingRule` | field→source fact/evidence resolution and format target mapping |
| `RendererProfile` | adapter/version, deterministic options, fonts/toolchain/environment constraints |
| `ValidationProfile` | required validators, severity, accepted tolerances and golden refs |
| `GenerationRequest` | workspace, mode execution, required type, purpose and requested output |
| `GenerationRun` | frozen version set, input fingerprint, attempts, events and outcome |
| `FieldResolution` | normalized value, state, source fact version, evidence refs, conflicts/gap |
| `GeneratedDocumentCandidate` | exact bytes digest, render refs, validation report, non-final state |
| `ReviewDecision` | reviewer identity/role/grant, candidate digest, decision, reason and time |
| `FinalizedDocument` | immutable accepted candidate digest, finalization decision and export eligibility |
| `RenderArtifact` | canonical pages/previews, profile and digest; derived workspace data |
| `EvidenceBinding` | field/geometry locator to exact evidence/version and confirmation decision |

## 8. Template lifecycle

```text
discovered → quarantined → candidate → qualified → active → superseded
                                      ↘ rejected     ↘ withdrawn
```

- `discovered`: bytes найдены, digest и source locator записаны;
- `quarantined`: basic safety/type checks пройдены, использование запрещено;
- `candidate`: provenance, intended form/edition и preliminary structure
  описаны;
- `qualified`: source authority, rights, schema, bindings, renderer,
  validators и goldens утверждены для bounded profile;
- `active`: разрешён точный scope/effective interval;
- `superseded`: новая версия заменила старую, старые runs воспроизводимы;
- `withdrawn`: новые runs запрещены из-за дефекта/authority change;
- `rejected`: asset не соответствует назначению или qualification.

Переходы выполняются явными decisions. Re-import одинакового digest не создаёт
новую содержательную version, но может добавить acquisition evidence. Изменение
хотя бы одного байта derivative создаёт новую identity/version.

## 9. Applicability и выбор версии

1. Requirement Engine фиксирует exact workspace context, work type,
   construction stage, contract/customer overlay и версии НТД/rules.
2. Он возвращает `required`, `conditional`, `not_applicable` или `unresolved`
   с reason/evidence; отсутствие решения не трактуется как `not_applicable`.
3. Для required type Registry выбирает только `active` TemplateVersion, чьи
   edition/effective interval/scope однозначно применимы.
4. Ноль подходящих версий создаёт gap; несколько равноприоритетных — conflict.
5. Alias `latest` разрешён только UI как отображение уже разрешённой exact
   version; в run хранится immutable version identity.
6. Customer/organization overlay не может незаметно перезаписать universal
   template. Он является отдельной versioned layer с own authority и lineage.

## 10. Field schema, bindings и разрешение значений

### 10.1. Поля

Field schema задаёт stable semantic key, type, cardinality, units, precision,
normalization, display format, materiality, confidentiality и missing policy.
Layout target (`cell B14`, content control, bookmark, coordinate rectangle)
не является semantic field identity.

Обязательные классы включают identity/requisites, dates/intervals, work and
location, project documentation, materials/certificates, measurements,
evidence/control, normative references, signers/authority, appendices,
amounts/totals и geometry.

### 10.2. Состояния разрешения

`FieldResolution.state` принимает:

- `confirmed` — value связан с подтверждённым fact version и evidence;
- `candidate` — предложен OCR/AI/parser/human draft, но не подтверждён;
- `conflict` — два допустимых источника дают несовместимые values;
- `missing` — обязательный source отсутствует;
- `not_applicable` — доказано versioned applicability decision;
- `redacted_for_view` — value существует, но текущему viewer недоступен.

Только `confirmed` и доказанный `not_applicable` могут пройти финализацию.
Пустая строка, `0`, текущая дата, последний известный подписант и copied value
из другого документа не являются missing policy.

### 10.3. EvidenceBinding

Каждое материальное заполнение хранит field key, normalized/display value,
fact identity/version, evidence object/version, locator, confirmation decision,
resolver/rule version и transformation trace. Для списка/таблицы binding
существует на строку или однозначно определённую группу, а не только на весь
документ.

## 11. Детерминированный generation pipeline

1. Авторизовать atomic capability и exact workspace/purpose.
2. Разрешить RequiredDocumentType и applicability с pinned rule versions.
3. Выбрать единственную active TemplateVersion.
4. Зафиксировать source/derivative, field schema, binding, renderer и validator
   versions.
5. Разрешить все fields через Fact Resolver; materialize conflicts/gaps.
6. Проверить authority подписантов и иных professional claims без назначения
   их моделью.
7. Нормализовать значения, units, dates и lists; сохранить transformation trace.
8. Вычислить input fingerprint. Повтор с тем же idempotency key и fingerprint
   возвращает тот же run/result; другой fingerprint конфликтует.
9. Создать fresh adapter instance и candidate bytes во временном workspace
   storage; source original не изменяется.
10. Выполнить structural и content validators.
11. Создать canonical render и выполнить layout/golden validators.
12. Выполнить cross-document, evidence и authority validators.
13. При blockers завершить run как failed/blocked с сохранением допустимого
   diagnostic report; partial bytes не становятся candidate для finalization.
14. При успехе зафиксировать immutable `GeneratedDocumentCandidate`.
15. Получить professional review на exact candidate digest и validation set.
16. Создать `FinalizedDocument`; export/print/archive работают только с его
   immutable bytes либо доказанной canonical print representation.

## 12. Format adapters

### 12.1. DOCX

DOCX adapter поддерживает квалифицированные Jinja placeholders/content
controls/bookmarks только в рамках exact binding profile. Он обязан сохранять
sections, headers/footers, styles, fonts, tables, cell merges, numbering,
fields, images и page settings. Generic `python-docx` reconstruction не может
подменять официальный макет; она допустима только для явно synthetic forms.

Проверки: OOXML integrity, unresolved tokens, duplicated/omitted rows,
relationship validity, fonts, page/section count, clipping, line/table breaks,
header/footer equivalence и canonical PDF/page render.

### 12.2. XLSX

XLSX adapter заполняет exact cells/named ranges по mapping и сохраняет styles,
merged cells, formulas, number formats, row/column dimensions, page setup,
print areas/titles, images и protection expectations. Programmatic creation
новой workbook не считается заполнением source template.

Проверки: workbook integrity, mapping coverage, formulas/cached-result policy,
totals, merges, hidden rows/sheets, print areas, pagination, scaling, repeat
titles и render в квалифицированном spreadsheet profile.

### 12.3. Fillable PDF

AcroForm adapter работает только при наличии квалифицированных fields и
mapping: проверяет field types, appearances, fonts, overflow, flattening policy
и signatures. В найденном remote PDF corpus AcroForms отсутствуют; этот путь
архитектурно обязателен, но не считается legacy-ready.

### 12.4. Non-fillable PDF

Overlay adapter использует квалифицированные page/coordinate mappings,
rotation/crop boxes, embedded fonts и overflow rules. OCR-derived coordinates
могут быть только Candidate mapping до human qualification. Исходный PDF
остаётся immutable; overlay derivative имеет отдельный digest/version.

### 12.5. DXF/SVG/PDF исполнительные схемы

Geometry adapter сохраняет units, coordinate reference/frame, scale, project
baseline, survey/factual observations, transformations, tolerances, drawing
layers/entities и RD locator. `generate_from_params` запрещён при
неподтверждённых geometry/measurements.

DXF является structured candidate, SVG/PDF — derived renders. Ошибка PDF
экспорта не превращает run в success. Требуются entity checks, coordinate and
unit invariants, bounds/scale, stamp completeness, label collision, page size,
line weights/fonts и visual golden comparisons.

## 13. Validation model

| Layer | Обязательные проверки |
|---|---|
| Source/authority | digest, provenance, rights, form identity, edition/effective interval |
| Structural | container validity, relationships, sheets/pages/entities, no unresolved placeholders |
| Binding | full schema coverage, unique targets, type/unit/cardinality, no orphan value |
| Evidence | material field locator, confirmed state, no cross-workspace source |
| Content | required values, allowed ranges, dates/chronology, requisites, signatures metadata |
| Cross-document | common IDs/dates/volumes/materials, KS totals, appendices/register consistency |
| Geometry | CRS/frame/units/scale, RD/fact lineage, tolerances, collision/bounds |
| Layout/print | fonts, clipping, pagination, tables/merges, formulas, print area, page size/orientation |
| Security/privacy | macros/embedded objects/links, leakage, external refs, classification/egress policy |
| Finalization | exact digest, validator profile complete, reviewer grant and segregation constraints |

Severity — `blocker`, `error`, `warning`, `info` — задаётся versioned
ValidationProfile. Blocker/error, unknown validator, отсутствующий canonical
render или неполный evidence coverage останавливают finalization fail-closed.

## 14. Определение print-ready

Документ print-ready только если одновременно:

1. exact TemplateVersion и source authority однозначны;
2. обязательные fields подтверждены и evidence-bound;
3. structural/content/cross-document validators пройдены;
4. canonical renderer квалифицирован для format/profile;
5. page size/orientation/margins/print area/pagination/fonts/clipping пройдены;
6. formulas/totals/merges/rows/controls корректны для формата;
7. golden regression находится в принятом tolerance;
8. нет незакрытого geometry, signer, edition или authority gap;
9. candidate digest просмотрен и принят полномочным специалистом;
10. export package содержит exact bytes, manifest и validation/finalization
    evidence.

Preview, файл ненулевого размера, открытие LibreOffice/Word, наличие двух
страниц или успешный ZIP сами по себе не удовлетворяют этому определению.

## 15. Professional review и authorization

Generation, validation, template qualification, professional confirmation,
finalization и export — отдельные atomic capabilities. Human reviewer действует
в одной active role, exact workspace/scope и на exact candidate digest.

Для high-risk forms policy может требовать separation of duties между:

- автором binding/template derivative;
- подтвердившим project facts/geometry;
- профессионально финализирующим документ;
- утвердившим platform TemplateVersion.

Изменение bytes, evidence, rule или validation report после review делает
решение неприменимым и требует нового candidate/review. Service, model, queue,
template author и storage не имеют human authority.

## 16. Fingerprint, идемпотентность и воспроизводимость

Input fingerprint включает identities/digests всех pinned templates,
schemas/rules/profiles, normalized field resolutions и evidence versions,
execution/toolchain profile и deterministic options. Время запуска, путь
временного файла и случайный ID не входят в semantic fingerprint.

Один fingerprint обязан давать те же semantic bytes/render в том же
квалифицированном profile. Если формат/toolchain содержит недетерминированные
metadata, adapter нормализует их либо явно включает controlling version в
fingerprint. Любая viewer variance хранится как qualification evidence, а не
скрывается.

## 17. Ошибки, retry и partial success

- retry использует тот же operation/idempotency key и frozen input set;
- изменение facts/rules/template создаёт superseding run;
- output adapter пишет только во временную область и атомарно публикует
  candidate после всех pre-candidate checks;
- partial DOCX/DXF/PDF, failed conversion и incomplete package не публикуются
  как candidate;
- unavailable validator/renderer/authority service даёт blocked/failed, не
  silent fallback;
- diagnostic artifacts имеют отдельный type/retention и не могут быть
  экспортированы как финальная ИД.

## 18. Events и audit

Минимальные события:

- `TemplateDiscovered`, `TemplateQuarantined`, `TemplateQualified`,
  `TemplateActivated`, `TemplateWithdrawn`, `TemplateSuperseded`;
- `ApplicabilityResolved`, `BindingPlanCreated`, `FieldResolutionChanged`,
  `GenerationRequested`, `GenerationStarted`, `GenerationBlocked`,
  `CandidateGenerated`;
- `ValidationCompleted`, `ProfessionalReviewRecorded`, `DocumentFinalized`,
  `DocumentExported`, `GenerationArtifactsPurged`.

Audit фиксирует actor/service/node identities, workspace/platform scope,
capability, purpose, correlation/causation, exact versions/digests, policy and
authorization decisions, validator outcomes и timestamps. Credentials, raw
project payload и full document content в platform logs запрещены.

## 19. Security, privacy и object boundaries

1. Template intake проверяет ZIP bombs, path traversal, macros, external links,
   embedded executables/objects, malformed OOXML/PDF и MIME mismatch.
2. Macros и active content default-deny; исключение требует отдельного
   qualified profile и authorization.
3. Workspace adapter не читает blob по одному digest без scoped capability.
4. External provider не получает прямой storage/SQL access; egress проходит
   classification, purpose allowlist и exact object envelope.
5. Raw renders, intermediate OOXML и OCR outputs — workspace data classes с
   retention/reset policy.
6. Golden/fixture promotion требует leakage scan; реальные организации, лица,
   договоры, координаты и подписи заменяются доказуемо synthetic values.

## 20. Lifecycle, archive и reset

Freeze запрещает новым/старым generation jobs публиковать результат поверх
зафиксированной workspace revision. Finalize workspace включает manifest exact
`FinalizedDocument`, template/rule/renderer versions, evidence coverage,
uncertainties и validation reports.

Archive хранит finalized bytes и достаточный provenance для проверки, но не
превращает project document в platform memory. Archive import создаёт новый
workspace и новые scoped lineage/versions; прямое оживление старого workspace
или cross-workspace read запрещены.

Reset/purge удаляет workspace facts/values, candidates, intermediate renders,
temporary files, caches, extraction/model artifacts и разрешённые exports в
соответствии с deletion plan. Platform TemplateSource/TemplateVersion,
sanitized goldens и universal renderer versions сохраняются. Audit после reset
содержит только разрешённые content-free identifiers/digests/decisions.

## 21. Dependencies и execution profiles

Legacy evidence подтверждает пригодность отдельных libraries: `docxtpl` и
`python-docx` для DOCX, `openpyxl` для XLSX, `ezdxf` для DXF, PyMuPDF,
CairoSVG, `reportlab`, PyPDF2, `pdf2image` и `pytesseract` для PDF/render/OCR.
Это inventory, не фиксированный target stack.

Каждый production adapter имеет qualified execution profile: OS/container,
library/tool versions, fonts, locale/timezone, renderer/viewer, deterministic
options, resource limits и supported template feature set. Unsupported feature
даёт blocker. Optional dependency skip допустим только в unit test, но не в
production qualification/finalization.

## 22. Migration legacy assets

Migration выполняется после architecture contracts и не активирует assets
пакетно.

### 22.1. Очередь qualification

1. Зафиксировать immutable staging manifest и source archives вне project.
2. Дедуплицировать exact bytes, затем semantic/layout variants.
3. Разделить universal source candidates, parameterized derivatives,
   project-specific outputs, defect samples и rejected assets.
4. Первыми квалифицировать одну DOCX и одну XLSX АОСР только при доказанном
   official source/edition; не выбирать форму по имени файла.
5. Отдельной batch проверить 149 DOCX + 82 XLSX `king25` и 119 unique XLSX +
   один PDF `ms-7e26`; filled/generated files исключить из template intake.
6. Восстановить один дедуплицированный набор 25 YAML в quarantine; не создавать
   отсутствующие 67 assets по историческому отчёту.
7. Выбрать sanitized defect cases: cumulative AOSR, zero KS, malformed date,
   layout overflow; запретить реальные ОКС values.
8. Портировать algorithms только после contract tests: geometry/parsers,
   stateless DOCX/XLSX adapters, render checks, ISUID lifecycle concepts и
   безопасные XLSX repair mechanics.

### 22.2. Preserve / modernize / reject

| Решение | Assets/механизмы |
|---|---|
| Preserve | immutable source bytes/provenance; 25 YAML/report evidence; catalogs; deterministic geometry/math; sanitized defect references |
| Modernize | Template Registry, field schemas/bindings, stateless adapters, applicability, validation, lifecycle, XLSX parser/repair patterns |
| Reject | object-specific corpus as platform memory; generated files as templates; generic form reconstruction; silent fallback; file-exists readiness; invented facts/geometry |

Никакой whole archive, `.git` object store, deployment, secret-bearing sync
tooling или workspace dataset не переносится в контролируемый staging проекта.
Рекомендованные batches создаются позднее отдельной authorized migration с
повторным manifest/leakage/rights review.

## 23. Acceptance tests архитектуры

### 23.1. Registry и authority

1. Одинаковый digest deduplicates bytes, сохраняя два acquisition evidence.
2. Modified derivative не меняет source и получает новую identity.
3. Discovered/quarantined/candidate asset нельзя использовать в generation.
4. Ambiguous edition, missing authority/right или withdrawn template блокирует
   run.

### 23.2. Fields и evidence

5. Каждое material field разрешается в confirmed evidence locator либо gap.
6. Candidate/conflict/missing signer/date/volume/material/measurement блокирует
   finalization.
7. AI value не становится confirmed без отдельного authorized decision.
8. Cross-workspace evidence reference отклоняется.

### 23.3. Format и layout

9. DOCX regression обнаруживает unresolved token, duplicated act, lost header,
   table split, font substitution и pagination drift.
10. XLSX regression обнаруживает lost formula/merge/print area/title, changed
    scaling, zero/inconsistent totals и clipped rows.
11. Fillable PDF test проверяет appearances/overflow/flattening; non-fillable
    PDF test — coordinates, crop/rotation, fonts и clipping.
12. DXF/PDF test проверяет units/CRS/frame/scale, entities, RD/fact lineage,
    label collision, page size и render equivalence.

### 23.4. Pipeline, authority и lifecycle

13. Одинаковые confirmed inputs/versions/profile дают тот же fingerprint и
    воспроизводимый result; state другого run не протекает.
14. Renderer/validator failure не публикует partial candidate.
15. Review exact digest нельзя применить к изменённым bytes/evidence/report.
16. Service/model не может выполнить professional finalization.
17. Export до finalization запрещён для purpose `official-deliverable`.
18. Freeze отвергает late worker result.
19. Reset удаляет workspace values/candidates/renders, сохраняя platform
    template/renderer versions.
20. Archive import создаёт новый workspace и не даёт прямой read старого.

### 23.5. Legacy defect gates

21. Stateful cumulative-AOSR sequence воспроизводится как negative test и
    проходит только после fresh-document isolation.
22. Zero-total/incomplete KS files не проходят content/cross-document checks.
23. Filled test DOCX и generated PRJ XLSX не принимаются Template Intake как
    universal source.
24. Отсутствующие 67 YAML не считаются доступными из-за текста historical
    report или registry references.

## 24. Архитектурные gates и дальнейшая очередь

- `G-00-ID`: ADR-0010, legacy inventory и эта specification приняты — закрыт.
- `G-01`: принят `LOGICAL_DATA_MODEL_v0.1.md`; сущности generation/template,
  scope, версии, evidence, render и finalization формализованы.
- `G-02`: принят `DEPLOYMENT_AND_POLICY_PROFILES_v0.1.md`; template,
  renderer/font/toolchain, geometry, print-ready, retention, authority и
  resource policies имеют complete fail-closed schemas, а отсутствующие
  production instances остаются `UNSET/BLOCKED`.
- `G-03`: `PASS 2026-08-22`; generation, template, evidence, storage, render,
  print, professional review, finalization и authorization contracts
  опубликованы в `CONTRACT_PACK_v0.1.md` и `contracts/v0.1/`.
- `Template Migration Qualification`: выполняется по asset batches после
  contracts, goldens, authority и leakage review.

Закрытие G-03 не разрешает начинать ORM, DDL, migrations или прикладную
реализацию без отдельной implementation authority; production operations
дополнительно требуют активации обязательных policy instances.

## 25. Открытые evidence-dependent вопросы

Это не архитектурные blockers baseline, а будущие qualification decisions:

1. официальный источник, exact edition/effective interval и права каждой
   candidate form;
2. утверждённые semantic field schemas и field-level authority;
3. точные professional qualifications/SoD для видов ИД;
4. qualified renderer/toolchain/font profiles и допустимая viewer variance;
5. правила формул, округления, totals, signing/verification и export package;
6. CRS/frame/tolerance profiles для классов исполнительных схем;
7. sanitized golden corpus, не содержащий данных конкретных ОКС;
8. какие из 119 уникальных XLSX `ms-7e26` действительно относятся к scope ИД,
   не являются variants/duplicates и имеют доказуемую authority.

До решения соответствующий TemplateVersion или output profile остаётся
quarantined/blocked; платформа в целом не подменяет gap догадкой.

## 26. Трассировка

- `decisions/0010-id-generation-and-template-platform.md` — Accepted decision;
- `../reports/LEGACY_ID_GENERATOR_ASSET_INVENTORY_v0.1.md` — фактическая опись
  legacy source/templates/tests/outputs всех трёх компьютеров;
- `ARCHITECTURE_BLUEPRINT_v0.1.md` — границы общего ядра и gates;
- `DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md` — platform/workspace memory, evidence и
  promotion boundaries;
- `DETERMINISTIC_RULES_CATALOGUE_v0.1.md` — versioned deterministic rules;
- `AUTHORIZATION_AND_AUDIT_MODEL_v0.1.md` — identities, capabilities,
  professional authority и audit;
- `PROCESS_AND_EVENT_SPECIFICATION_v0.1.md` — commands/events/idempotency;
- `LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md` — freeze/finalize/export,
  archive/import/reset/purge;
- `AI_VLM_EXECUTION_AND_VERIFICATION_HARNESS_SPECIFICATION_v0.1.md` —
  Candidate-only AI/VLM boundary и provider qualification.

## 27. Итог

Целевое ядро не «печатает форму из словаря», а доказуемо связывает exact
requirement, applicable rule, immutable template version, confirmed facts,
evidence, deterministic adapter, validation/render profile и professional
decision. Только такая цепочка может создать `FinalizedDocument`.

Legacy сохраняется как источник algorithms, candidates и defect evidence, но
не как authority. Ни крупный binary corpus, ни исторический test count, ни
открываемый generated файл не обходят qualification gates.
