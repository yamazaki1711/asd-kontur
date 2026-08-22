# Authorization & Audit Model АСД-КОНТУР v0.1

- **Статус документа:** `Accepted architecture baseline`
- **Дата:** 2026-08-21
- **Принято:** 2026-08-22 ведущим архитектором Codex по явным
  архитектурным полномочиям владельца продукта; конкретные grants и
  professional qualifications остаются policy data
- **Владелец продукта:** Олег Щербаков
- **Область:** объектно-независимый local-first доказательный комплекс;
  `Tender`, `Support`, `Audit`, `Restoration`
- **Основание:** `PRODUCT_SCOPE.md`, `FUNCTIONAL_MODEL_v0.1.md`,
  `ARCHITECTURE_BLUEPRINT_v0.1.md`,
  `DOMAIN_AND_KNOWLEDGE_MODEL_v0.1.md`,
  `LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md`,
  `PROCESS_AND_EVENT_SPECIFICATION_v0.1.md`,
  `AI_VLM_EXECUTION_AND_VERIFICATION_HARNESS_SPECIFICATION_v0.1.md`,
  ADR-0001—ADR-0008

## 0. Нормативная роль и статусы

Этот документ определяет модель идентичностей, полномочий, принятия
authorization decision и доказательного аудита. Он не является ORM-схемой,
описанием конкретного IAM-продукта или разрешением реализации.

Используются статусы:

- `Invariant` — свойство, которое будущая реализация не вправе ослабить;
- `Accepted` — явное решение владельца продукта;
- `Proposed` — проектное решение, требующее review в составе документа;
- `Owner Decision Required` — историческая метка; архитектурный вариант
  теперь может быть принят Codex в делегированных границах, но не
  evidence-dependent grant, qualification или professional decision.

**Синхронизация IA-OD 2026-08-22.** Shared deployment обязан проверять
`organization_id` поверх обязательного `workspace_id`; dedicated profile не
убирает tenant scope. Создание и concurrency ModeExecution требуют отдельных
capabilities. Archive import требует source/archive read, verify и
target-workspace create/import без прямого cross-workspace grant. Organization
overlays имеют steward/approver separation. Field facts подтверждаются по
risk-class matrix, а внешние электронные подписи только проверяются:
capability signing и private signing keys не входят в v0.1.

Явным сообщением владельца продукта Олега Щербакова от 2026-08-21 приняты:

1. `Accepted`: основной VLM — локальный `Qwen3.8-27B`; внешний VLM через
   `polza.ai` разрешён для policy-допустимой массовой обработки растровых PDF.
2. `Accepted`: архитектурная граница исполнения provider-neutral и задаётся
   контрактом `VlmExecutionProvider`; имя провайдера не входит в доменную
   модель результата.
3. `Accepted`: любой локальный или внешний VLM создаёт только `Candidate` или
   draft; он не подтверждает факт, геометрию, объём, юридический вывод или
   deliverable.
4. `Accepted`: единый VLM Verification Harness обязателен; его отдельная
   спецификация готовится позднее в установленной Blueprint очереди.
5. `Accepted`: официальный каталог Минстроя — приоритетный источник для
   управляемого пополнения канонической базы НТД.
6. `Accepted`: `HV-01/B…HV-08/B` — default-deny versioned data-class/purpose
   allowlist, budget matrix, critical qualification floors/zero-tolerance
   blockers, allowlisted finite provider retention, risk-based confirmation,
   encrypted workspace raw artifacts, ordered pre-authorized fallback и
   versioned cost envelope.
7. `Accepted` (ADR-0008): MBP — primary authoritative node, VPS — bounded
   coordination/integration node, S3 — mandatory durable object plane; ни VPS,
   ни S3 не получают human/domain authority или альтернативный SoR.

Владелец решений HV — Олег Щербаков; дата — 2026-08-21; подтверждение —
сообщение владельца продукта от 2026-08-21, начинающееся словами «Я, Олег
Щербаков, владелец продукта АСД‑КОНТУР, 21.08.2026 принимаю решения
HV‑01…HV‑08». Полные нормативные карточки и последствия находятся в
`AI_VLM_EXECUTION_AND_VERIFICATION_HARNESS_SPECIFICATION_v0.1.md` §28.

Эти решения не являются blanket-разрешением внешнего egress. Пока нет
применимых `WorkspaceEgressPolicy`, provider processing/retention policy и
точных allowlist, любой внешний VLM-вызов отклоняется (`default deny`).

## 1. Цели и границы

Модель должна доказуемо отвечать на пять вопросов:

1. кто или какой сервис запросил действие;
2. в каком активном полномочии, workspace и purpose он действовал;
3. какая версия политики разрешила или запретила действие;
4. что именно было сделано и с каким результатом;
5. какие данные допустимо сохранить в аудите после завершения retention.

Документ распространяется на людей, сервисы, очереди, интеграции, модели,
Knowledge Tool Gateway, НТД ingestion, экспорт и опасные lifecycle-команды.
Он не проектирует пользовательский интерфейс, конкретную network topology,
TLS/KMS/secret-store mechanism, provider adapter или API `polza.ai`.
Accepted roles узлов ADR-0008 являются входом, а их техническое enforcement —
предмет Technical Architecture v0.3.

## 2. Базовые инварианты доверия

1. `Invariant`: аутентификация устанавливает identity, но сама по себе не
   даёт полномочия.
2. `Invariant`: authorization вычисляется для одной atomic capability,
   одного scope, purpose и версии ресурса; wildcard authority для сервисов и
   интеграций запрещена.
3. `Invariant`: каждый workspace-scoped запрос, job, tool call, audit record
   и artifact содержит `workspace_id`; platform operation помечается явным
   `scope=platform`, а не отсутствием контекста по ошибке.
4. `Invariant`: авторизация fail-closed. Ошибка policy engine, отсутствие
   версии политики, невозможность записать обязательный audit или
   неоднозначная классификация означают `deny`.
5. `Invariant`: одна identity может иметь несколько ролей, но действие
   совершается только в одной явно выбранной active role.
6. `Invariant`: LLM/VLM/OCR, очередь, prompt, документ и внешний provider не
   обладают human authority.
7. `Invariant`: знание hash или object ID не является capability и не даёт
   доступа к blob другого workspace.
8. `Invariant`: внешняя интеграция не получает прямой SQL, прямой доступ к
   workspace storage или право произвольного обхода документов.
9. `Invariant`: sensitive read, export, external egress, professional
   confirmation, PromotionDecision и destructive lifecycle action всегда
   аудитируются.
10. `Invariant`: audit не копирует уничтожаемое проектное содержимое ради
    доказательности; после verified reset действует RD-03/A.

## 3. Идентичности и principals

| Тип | Назначение | Может иметь human authority | Обязательные атрибуты |
|---|---|---:|---|
| `HumanIdentity` | пользователь, эксперт, администратор, аудитор | да, через active role и grant | identity ID, organization, status, assurance level |
| `ServiceIdentity` | внутренний API, worker, rule engine, audit writer | нет | service ID, environment, workload credential, capability set |
| `IntegrationIdentity` | конкретная внешняя система или provider boundary | нет | integration ID, provider ID, endpoint/profile ID, credential ref, policy refs |
| `DeviceIdentity` | доверенное рабочее место/полевое устройство, если применяется | нет | device ID, binding, status, assurance attributes |
| `ModelExecutionIdentity` | provenance-конверт исполнения модели, не actor | нет | provider, model/revision, execution profile, quantization/format |
| `NodeIdentity` | аутентифицированный физический/виртуальный execution node в принятой ADR-0008 топологии | нет | logical installation ID, node instance ID, node role, credential/version, activation interval, assurance and attestation attributes |

`ModelExecutionIdentity` не заменяет service/integration principal. Локальный
runtime вызывается внутренней `ServiceIdentity`; внешний VLM — отдельной
`IntegrationIdentity`. Одинаковая строка `Qwen3.8-27B` у двух providers не
означает одинаковую identity, qualification или эквивалентность результата.

Запрещены shared human accounts. Service и integration credentials не могут
использоваться как пользовательская сессия. Credential хранится по ссылке на
secret store, ротируется независимо от policy и никогда не пишется в audit,
prompt, job payload или artifact.

### 3.1. Node identity и физическая authority по ADR-0008

`NodeIdentity` не заменяет `HumanIdentity`, `ServiceIdentity`,
`IntegrationIdentity` или `ModelExecutionIdentity`: межузловой вызов требует
как полномочия действующего service/integration principal, так и доказанной
identity узла исполнения. Неподтверждённая, отозванная, конфликтующая или
просроченная node identity даёт `deny`.

| Node role | Разрешённая authority | Явно запрещено |
|---|---|---|
| MBP `primary_authoritative` | принимать/отклонять канонические команды; исполнять детерминированное ядро; хранить canonical PostgreSQL; применять уже выданные human/domain decisions; формировать authoritative acknowledgement | самостоятельно присваивать human authority сервису/модели; обходить SoD, legal hold, RD/DR/HV policies |
| VPS `coordination_integration` | authenticate ingress; принять bounded `IngressEnvelope`; хранить разрешённый encrypted staging; доставлять UI/status; выполнять разрешённую интеграцию/egress после отдельного authorization | canonical acceptance; professional confirmation; PromotionDecision; Rule approval; deliverable finalization; purge/destroy authorization; самостоятельная смена primary |
| S3 `durable_object_plane` | хранить/выдавать точную разрешённую object version по scoped capability и retention policy | доменное решение, current state, подтверждение, исполнение команды, делегирование доступа |
| External provider node | выполнить единственный authorized provider request в точном profile | прямой SQL/storage/Gateway; доступ к другим объектам; confirmation/finalization/promotion/destruction |

Каждое перемещение MBP↔VPS↔S3↔external provider требует отдельной atomic
capability (`node.data.send`, `node.data.receive`, `object.stage`,
`object.transfer`, `object.read`, `external.execute` либо более узкой), exact
source/destination `NodeIdentity`, scope, object/envelope identity+version,
classification/purpose, digest, schema, retention и authorization decision.
Получение VPS/S3 не наследует authority отправителя и не означает принятия
доменным ядром.

Node/data-movement audit фиксирует node identities/roles, principal,
capability, workspace/platform scope, object/envelope identity+version,
classification/purpose, schema, digests, policy/authorization decision,
correlation/causation, acknowledgement и outcome. В platform/VPS logs
запрещены full project payload, исходные документы, raw prompt/response,
credentials и секреты.

`TECHNICAL_ARCHITECTURE_v0.3.md` выбирает по `TA-TD-08…TA-TD-10` mTLS для
node-to-node traffic, hybrid OS-bound/envelope-key model и client/envelope
encryption плюс S3 server-side encryption. Конкретный secret/KMS product,
enrollment/rotation/revocation profile и hardware recovery evidence остаются
deployment security policy. До их утверждения, реализации и проверки
межузловой production data movement запрещён fail-closed.

## 4. Модель полномочий

### 4.1. Authorization tuple

Каждое решение вычисляется над закрытым конвертом:

```text
AuthorizationRequest {
  actor_identity_id
  actor_kind
  active_role | service_identity | integration_identity
  atomic_capability
  organization_id
  workspace_id | platform_scope
  resource_type + resource_id + expected_version
  lifecycle_state
  purpose_code
  data_classification
  source/page/region scope when applicable
  destination/provider/model/execution_profile when applicable
  authority_grant_id + validity interval
  policy_versions[]
  correlation_id + causation_id
}
```

`purpose_code`, classification и resource scope не берутся из prompt или
ответа модели. Их формирует доверенный application layer до вызова
интеграции.

### 4.2. Порядок проверки

Policy decision point последовательно проверяет:

1. подлинность и активный статус identity;
2. активную роль либо точную service/integration identity;
3. organization/workspace membership и hard isolation;
4. atomic capability и действительность grant;
5. lifecycle и текущую версию ресурса;
6. purpose limitation и entity status;
7. data classification и effective classification выбранных частей;
8. legal hold и retention guards, если применимо;
9. segregation of duties;
10. для egress — `WorkspaceEgressPolicy`, destination/provider/model/profile
    allowlist, processing/retention policy и payload minimization;
11. возможность записать обязательный authorization audit.

Первый отрицательный или неопределённый guard завершает запрос `deny`. После
решения нельзя расширить pages, destination, purpose или tool set: изменение
любого поля создаёт новый `AuthorizationRequest` и новый decision ID.

### 4.3. Atomic capabilities

Минимальный каталог целевых capability:

| Группа | Atomic capabilities |
|---|---|
| Workspace | `workspace.create`, `workspace.configure`, `workspace.read`, `workspace.freeze`, `workspace.finalize`, `workspace.reopen` |
| Sources | `source.admit`, `source.read`, `source.classify`, `source.export` |
| Candidate/fact | `candidate.produce`, `candidate.validate`, `candidate.reject`, `fact.confirm`, `fact.supersede` |
| Deliverables | `deliverable.draft`, `deliverable.finalize`, `deliverable.export` |
| Tools/models | `knowledge.tool.invoke`, `vlm.local.invoke`, `vlm.external.invoke` |
| Knowledge/rules | `ntd.source.register`, `ntd.edition.admit`, `ntd.assertion.review`, `ntd.applicability.publish`, `rule.create`, `rule.evidence.attach`, `rule.review`, `rule.approve`, `rule.suspend`, `rule.retire`, `ruleset.publish`, `workspace.ruleset.upgrade`, `rule.conflict.resolve`, `promotion.decide` |
| Lifecycle/archive | `archive.create`, `archive.read`, `archive.export`, `archive.reimport.request`, `purge.plan`, `purge.request`, `purge.confirm`, `destroy.request`, `destroy.confirm`, `legal_hold.manage`, `attestation.confirm` |
| Policy/audit | `egress.policy.manage`, `integration.allowlist.manage`, `vlm.budget_policy.manage`, `vlm.cost_envelope.authorize`, `authority.grant.manage`, `audit.read`, `audit.export` |
| Node/object movement | `node.data.send`, `node.data.receive`, `ingress.accept`, `object.stage`, `object.transfer`, `object.read`, `replica.read`, `restore.propose`, `restore.verify`, `primary.activate` |

`vlm.external.invoke` выбрана как отдельная capability, а не неограниченная
`tool.invoke`: это исключает наследование egress-права сервисом, которому
разрешены только локальные tools. Названия уточняются в будущих API contracts,
но атомарность и разделение local/external являются инвариантами.

## 5. Роли, active role и segregation of duties

Бизнес-роли наследуются из `FUNCTIONAL_MODEL_v0.1.md`: Product Owner,
Organization Admin, Workspace Admin, PTO Engineer, Foreman, Incoming Control,
Laboratory, Surveyor, Construction Control, Customer Representative и
Auditor. Роль сама по себе не является глобальным доступом: grant ограничен
organization, workspace/zone, capability, типом сущности и сроком.

Дополнительные governance-функции могут быть назначены существующим людям как
ограниченные роли, но не создают новых продуктовых акторов автоматически:

| Функция | Необходимое полномочие | Обязательное разделение |
|---|---|---|
| Workspace administration | configure grants/policies в workspace | не даёт professional confirmation автоматически |
| Professional confirmation | профильный инженер/юрист по виду факта | модель и producer candidate не подтверждают |
| Normative curation | регистрация official source/edition | публикация assertion/applicability требует reviewer authority |
| Rule author | `rule.create`/`rule.evidence.attach` в разрешённом class/scope | не review/approve собственного RuleVersion; model/service не author Workspace RuleVersion |
| Rule reviewer | `rule.review`, human identity, independent от author | не подменяет class-qualified approver; model/service denied |
| Rule approver | `rule.approve` + active class-qualified authority | другая human identity относительно reviewer; incomplete evidence/tests/policy denied |
| RuleSet publisher | `ruleset.publish` | только approved/compatible RuleVersion и immutable manifest |
| Workspace RuleSet upgrader | `workspace.ruleset.upgrade` | только non-terminal workspace, approved target, impact/compatibility preview и scoped authority |
| Conflict resolver fallback | `rule.conflict.resolve` + subject/domain authority | только unresolved `DR-03/B` conflict; не global rule и не LLM |
| Promotion review | `promotion.decide` | не модель, не originating process; проверяется conflict of interest |
| Purge/destroy requester | `purge.request`/`destroy.request` | не может подтвердить собственный запрос |
| Purge/destroy confirmer | `purge.confirm`/`destroy.confirm` | независимый grant по RD-04/C |
| Audit review | scoped read/export | не даёт mutation или operational credential access |

Точный mapping людей на роли — organization policy data. Наличие у человека
двух grant не отменяет SoD: для одной необратимой операции requester и
confirmer должны быть разными identities и независимыми полномочиями.

## 6. AI, OCR и VLM как неавторитетные исполнители

Локальный `Qwen3.8-27B` является основным VLM на MBP M5 Max. Он предпочтителен
для юридических, конфиденциальных, сложных, интерактивных задач и подготовки
draft исполнительных схем. Модель может распознавать, классифицировать,
компоновать и предлагать, но не вправе придумывать или подтверждать геометрию,
координаты, размеры, объёмы и юридические факты. Итоговая исполнительная схема
строится только из подтверждённых проектных и фактических геометрических
данных.

Для разрешённых массовых растровых PDF допускается внешний provider;
планируемый provider — `polza.ai`, модель — `Qwen3.8-27B` либо совместимая,
прошедшая qualification. Домен не зависит от provider или transport API.

Ни локальный, ни внешний VLM не вправе:

- создавать `FactVersion` или менять каноническое состояние;
- подтверждать `Candidate`, `Uncertainty`, геометрию или юридический вывод;
- финализировать deliverable;
- принимать `PromotionDecision`;
- создавать или утверждать Workspace RuleVersion, выполнять human review либо
  class-qualified approval;
- разрешать RuleConflict или controlled RuleSet upgrade;
- инициировать или подтверждать purge/destroy;
- менять provider, destination, egress scope, classification или retention;
- вызывать произвольные tools или SQL.

## 7. Provider-neutral VLM execution

### 7.1. `VlmExecutionProvider` contract

Локальный runtime и внешний provider реализуют один логический порт:

```text
VlmExecutionRequest {
  authorization_decision_id
  workspace_id
  source_version_id
  permitted_locators[]
  extraction_purpose
  data_classification
  provider_profile_id
  model_profile_id
  prompt_template_version
  output_schema_version
  preprocessing_version
  rendering_parameters_version
  verification_policy_version
  minimized_payload
  correlation_id + causation_id
}

VlmExecutionResult {
  provider_identity
  model_identity
  model_revision
  execution_profile
  prompt_template_version
  output_schema_version
  source_version_id
  page_image_locators[]
  extraction_purpose
  typed_candidates[]
  field_level_evidence[]
  uncertainties[]
  validation_results[]
  timings
  cost_usage_metadata | not_applicable
  retry_repair_history[]
  correlation_id + causation_id
}
```

Отдельно версионируются provider, endpoint/profile, model revision,
quantization/execution format, prompt, schema, preprocessing, rendering
parameters и verification policy. Результаты сравниваются по qualification и
quality profile; совпадение model name не позволяет взаимозаменять provenance.

### 7.2. Routing policy

Router применяет правила в следующем порядке:

1. пригодный native text извлекается детерминированно до VLM;
2. документ и страницы классифицируются, цель извлечения фиксируется;
3. проверяются data classification, workspace egress permission и purpose;
4. учитываются тип документа, raster/text state, объём страниц, сложность,
   latency, стоимость, qualification, availability и verification profile;
5. конфиденциальные, юридические, сложные, интерактивные и связанные с
   исполнительными схемами задачи направляются в локальный профиль;
6. policy-разрешённые массовые растровые PDF могут направляться внешнему
   provider;
7. fallback допускается только exact entry versioned ordered matrix
   `data class × purpose × primary profile → fallback profiles`; каждый switch
   создаёт новые routing/authorization decision и immutable attempt;
8. до external batch выполняется reservation внутри действующего versioned
   cost envelope; недостаточный остаток даёт controlled stop до вызова.

Недоступность внешнего provider не разрешает отправить данные в иной endpoint.
Недоступность локального runtime не превращает local-only classification в
external-eligible.

### 7.3. External VLM authorization envelope

Внешний вызов разрешён только при одновременном выполнении условий:

- authenticated `IntegrationIdentity` и capability `vlm.external.invoke`;
- точный `workspace_id`; cross-workspace batch запрещён;
- известная data classification и применимая `WorkspaceEgressPolicy`;
- provider, destination, model и execution profile в точных allowlist;
- purpose входит в закрытый реестр и разрешён для этой classification;
- exact `data class × purpose` входит в versioned allowlist; отсутствующая,
  неоднозначная или просроченная classification даёт `deny`;
- payload содержит только разрешённые page/region locators;
- provider processing/retention policy имеет принятую применимую версию;
- credentials, лишние страницы и несвязанные документы отсутствуют;
- authorization decision записан до сетевого side effect.

Без отдельного allowlist-разрешения external VLM запрещён для legal-sensitive
материалов, confidential contracts/attachments, personal data,
credentials/secrets, закрытых сведений заказчика, подтверждённой геометрии/
геодезии, материалов исполнительных схем и иных sensitive/restricted classes.
Полный документ запрещён, если purpose достигается отдельными pages/regions.

Даже classification с низкой чувствительностью не разрешает egress без всех
остальных guards. Точные data classes и разрешённые сочетания являются
versioned workspace/organization policy data; эта спецификация не назначает
им blanket-default.

Внешний provider получает только payload, собранный доверенным adapter по
allowlist locators. Он не получает URL/capability на workspace blob, прямой
SQL, произвольный Knowledge Tool Gateway, список соседних документов,
credentials, human role или доступ к другому workspace.

### 7.4. Prompt injection boundary

Документ, страница, OCR-текст, image metadata и model output считаются
недоверенными данными. Инструкция внутри них не может изменить:

- provider/destination/model/profile;
- workspace, purpose или data classification;
- список pages/regions и payload budget;
- разрешённые tools;
- egress или provider retention policy;
- authority и terminal outcome.

Routing и authorization envelope формируются вне prompt. Model response не
исполняется как команда. Любое tool request из response проходит новую
типизированную authorization evaluation; внешнему VLM такой tool access по
умолчанию запрещён.

## 8. VLM Verification Harness boundary

Подготовленный
`AI_VLM_EXECUTION_AND_VERIFICATION_HARNESS_SPECIFICATION_v0.1.md` определяет
единый quality harness. В этой модели обязательны:

- native text first, deterministic page/region selection и typed schema;
- field-level locators, JSON/schema, type/range/unit/required-field checks;
- cross-field/cross-page consistency и сверка с native text/OCR;
- сверка с каноническими сущностями и применимыми НТД через локальный
  Knowledge Tool Gateway;
- targeted repair только по машинно сформированным validation failures;
- ограниченное число cycles и терминальные outcomes:
  `validated_candidate`, `unresolved_uncertainty`, `rejected_extraction`,
  `provider_model_failure`;
- полный provenance cycles, regression corpus и golden cases;
- сравнение execution profiles по качеству, а не только latency/cost;
- запрет считать согласие двух прогонов доказанным фактом;
- запрет бесконечного self-reflection без deterministic validator feedback.

Принятые HV дополнительно требуют:

- versioned execution/repair budget matrix; отсутствие numerical policy
  блокирует qualification, repeated failure fingerprint/no-progress/limit/
  non-repairable blocker прекращают repair;
- qualification по approved corpus с critical field/class/stratum floors и
  zero-tolerance blockers; average accuracy и runtime availability
  недостаточны;
- `ConfirmationPolicy`: обязательное human/domain-authority confirmation для
  legal effect, precedence, contracts, geometry/CRS/measurements, material
  quantities/KS/payment, signers/authority, blockers, PromotionDecision и
  executive-scheme finalization; auto-confirm допускается только через active
  RuleVersion, confirmed source, полный validator pass/RuleTrace и отсутствие
  conflict/uncertainty/professional authority;
- provider terms version, region, no-training, finite retention/deletion/
  subprocessors входят в policy и qualification; изменение terms suspends
  qualification;
- raw artifacts — только encrypted workspace-scoped data по RetentionProfile
  либо `no_raw_storage`; никакого full content в platform logs/audit;
- fallback — только ordered pre-authorized profiles без переноса primary
  authorization; sensitive/local-only не выходит наружу;
- external cost — reservation/commit/release и reconciliation в пределах
  authorized workspace/purpose/provider envelope.

Внешний provider не обращается к канонической базе НТД. Локальный application
layer выполняет retrieval/validation и при необходимости передаёт только
разрешённый минимизированный EvidencePack fragment, сохраняя scope и egress
guards.

## 9. Audit model

### 9.1. Семантика

`AuditRecord` — append-only доказательство попытки, authorization decision,
доступа, исполнения, проверки или результата. Он не является domain event,
event store, model artifact или копией source. Append-only действует внутри
применимой retention boundary: RD-03/A требует уничтожить content-bearing
workspace audit при reset и сохранить только content-free audit projection и
`DestructionAttestation`.

Для каждого существенного действия различаются как минимум:

1. `AuthorizationDecisionAudit` — разрешение/запрет до side effect;
2. `ExecutionAudit` — попытка и технический outcome;
3. `ValidationDecisionAudit` — validator/human outcome, если применимо;
4. `DomainTransitionAudit` — совершившийся канонический переход.

Один domain event не обязан соответствовать одной audit-записи. Отклонённая
команда создаёт audit, но не domain event.

### 9.2. Общий audit envelope

```text
AuditRecord {
  audit_record_id
  record_kind
  workspace_id | explicit platform_scope
  organization_id
  actor_identity_id + actor_kind
  active_role | service_identity | integration_identity
  atomic_capability
  resource_type + opaque resource_ref + version
  purpose_code
  authorization_decision_id + outcome + reason_codes[]
  policy_versions[]
  lifecycle_state_before | after
  correlation_id + causation_id
  occurred_at + recorded_at
  execution_outcome
  integrity_metadata
}
```

Audit хранит IDs, code values, versions, counts и digests, но не секреты или
payload по умолчанию. Human-readable reason допускается только из
версионированного каталога шаблонов, который не вставляет project content.

### 9.3. Audit внешнего VLM-вызова

Без копирования документа обязательны:

- `workspace_id`, `source_version_id`;
- разрешённые page/region locators;
- integration/provider identity;
- model identity и execution profile;
- purpose и data classification;
- egress/authorization policy versions и decision outcome;
- prompt template, output schema, preprocessing, rendering и verification
  policy versions;
- digest точного request envelope/payload и digest response artifact;
- request/response timestamps и duration;
- cost/usage metadata, если применимо;
- provider processing/retention policy version и declared residue;
- budget-policy и cost-envelope IDs/versions, reservation/commit/release и
  reconciliation outcome;
- primary/fallback routing decision, switch reason и attempt identity;
- invocation outcome и validation status;
- retry/repair count;
- correlation/causation IDs.

Audit внешнего вызова не содержит:

- API key, credential, token или secret reference, раскрывающий secret;
- полный исходный документ или image bytes;
- полный prompt с проектным содержимым;
- полный model response;
- имена файлов и текстовые фрагменты, запрещённые RD-03/A;
- данные другого workspace.

Request/response, page render, prompt expansion и repair artifacts являются
workspace memory. Они перечисляются в `RetentionProfile`, уничтожаются по
deletion plan и после verified reset не остаются в platform audit. Digests не
используются как обратная ссылка/capability и сохраняются после reset только
если входят в content-free allowlist; RD-03/A запрещает project source hashes
по умолчанию.

### 9.4. Целостность и доступ к audit

- запись обязательного audit должна быть подтверждена до необратимого side
  effect; недоступность audit writer блокирует действие;
- записи имеют monotonic sequence в scope и integrity metadata (hash chain,
  подпись или эквивалент выбираются Technical Architecture v0.3);
- application role не имеет произвольных `UPDATE/DELETE`;
- чтение и export аудита — отдельные capabilities и сами аудитируются;
- workspace audit не доступен другому workspace;
- redaction не маскирует изменение: исправление создаёт новую correction
  record, а retention purge выполняется только lifecycle protocol;
- telemetry/log/trace не заменяют audit и подчиняются собственной retention
  строке и residual scan.

## 10. Управляемое пополнение НТД

Официальный каталог Минстроя является приоритетным source, но не единственным
возможным доказательным источником. Пополнение выполняется по
версионированному реестру релевантности, а не массовым скачиванием сайта.
Приоритетные примеры (`СП 48`, `СП 70`, `СП 543`) не являются hard-coded
архитектурным списком.

Для каждой единицы обязательны:

- `NormativeDocument` для identity документа;
- отдельная `NormativeEdition` для каждой редакции и явная цепочка изменений;
- official URL, retrieval timestamp, SHA-256 и точный locator;
- independently reviewed status/effective period/applicability; имя файла не
  является доказательством действия;
- сохранение отменённой редакции в provenance;
- канонический текст и structural units независимо от embedding-модели;
- производные FTS/vector/sparse/graph индексы, которые можно перестроить;
- типизированные связи применимости с `WorkType`, `ConstructionElement`,
  `Material`, `ControlOperation`, `RequiredDocumentType`;
- выдача модели только через Knowledge Tool Gateway как EvidencePack.

Минимальное разделение полномочий: ingestion service с
`ntd.source.register` может получить и зарегистрировать bytes/metadata, но не
может объявить редакцию действующей или assertion применимым. Reviewer с
`ntd.edition.admit`/`ntd.assertion.review` проверяет provenance; публикация
применимости требует `ntd.applicability.publish`. Ошибка official source,
hash, edition chain или review даёт quarantine/uncertainty, не молчаливую
публикацию.

## 11. Опасные lifecycle и knowledge operations

Доступ к portable archive не наследуется из прежнего active-workspace grant.
`archive.read`/`archive.export` требуют действующих organization/workspace
scope, purpose, retention/legal-hold checks и отдельного audit. Чтение архива
не означает `reopen`; повторный импорт требует `archive.reimport.request`,
проверки manifest/integrity/schema compatibility и создания разрешённого
lifecycle target по Lifecycle Specification. Recovery backup не является
пользовательским архивом и недоступен через эти capabilities.

RD-04/C применяется без ослабления:

- basis выбирается из versioned Basis Registry;
- deletion plan содержит evidence и полный перечень storage adapters;
- legal-hold check обязателен;
- requester и confirmer необратимого purge/destroy — разные identities с
  независимыми capabilities;
- routine automation действует только внутри уже подтверждённого immutable
  deletion plan;
- LLM, queue, worker или integration identity не подтверждают удаление;
- partial adapter failure означает `failed`/`incomplete`, никогда `verified`.

PromotionDecision принимает только уполномоченный человек. Повторяемость,
confidence, согласие двух моделей или внешний provider не дают
`promotion.decide`. После reset выживает только RD-05/B Evidence Capsule;
unresolved/rejected candidate и project content уничтожаются по Lifecycle
Specification.

Rule governance подчинено принятым `DR-01/B…DR-04/B`:

- RuleVersion получает `approved/active` только после independent human review
  и решения другого class-qualified human approver; автор не reviewer, а
  model/service identity не reviewer и не approver;
- изменение evidence, predicate, output contract, effective interval или
  ConflictPolicy создаёт новую RuleVersion и новый approval cycle;
- каждая conflict group использует versioned subject-specific ConflictPolicy;
  unresolved conflict блокирует material operation, а `rule.conflict.resolve`
  доступна только human actor с exact subject/domain authority и создаёт typed
  scoped decision;
- Workspace RuleVersion имеет обязательный `workspace_id`, не доступна другому
  workspace, не является free-form override и входит только в конкретный pinned
  RuleSetVersion; её platform promotion создаёт новую RuleVersion через
  Promotion Gate;
- `workspace.ruleset.upgrade` допускается только после approved target,
  impact/compatibility checks и authority approval; старый pin действует до
  полного verified completion, terminal workspace и rolling adoption denied.

## 12. Отказы, отзыв полномочий и reconciliation

| Отказ | Fail-closed результат | Восстановление |
|---|---|---|
| identity/grant expired или revoked | deny; активный job не получает новый side effect | re-auth и новое decision |
| policy/allowlist version отсутствует | deny | публикация полной версии policy |
| audit writer недоступен | критическое действие не исполняется | retry authorization после восстановления |
| provider credential rejected | invocation failed; candidate не создаётся | rotation + новый attempt, тот же scope |
| provider outcome unknown | никаких blind retries | reconciliation по invocation ID/digest |
| response schema invalid | rejected extraction либо targeted repair по policy | bounded repair; затем terminal outcome |
| provider/model потерял qualification | новые вызовы deny | явная requalification/version update |
| fallback requested | старое решение не переиспользуется | новая routing + authorization evaluation |
| prompt injection detected | payload/candidate quarantined | review; policy envelope неизменён |
| cross-workspace reference/batch | deny + critical security audit | исправленный request с одним workspace |
| reviewer совпадает с author либо approver не class-qualified | deny; RuleVersion остаётся pre-approved | новый независимый review/действующий grant |
| Workspace RuleVersion запрошена из другого workspace | deny + critical isolation audit | запрос в owning scope либо platform rule после Promotion Gate |
| RuleSet upgrade target/preview/compatibility неполны или workspace terminal | deny/block; прежний pin остаётся | новая полная upgrade authorization request |
| ConflictPolicy отсутствует, а human actor не имеет subject authority | conflict/indeterminate; material process blocked | approved policy либо authorized typed fallback decision |
| legal hold появился до side effect | destructive action deny/pause | новый check и authorization после снятия hold |

Отзыв grant влияет на новые actions и continuations. Уже совершившийся факт не
стирается; его исправляет новая authorized domain version. Долгий job обязан
проверять lease, policy validity и resource version перед каждым внешним
side effect, а не только при постановке в очередь.

## 13. PE-01: integration/egress policy

`PE-01` разрешён на уровне архитектурного контракта следующим образом:

> Любой integration event и внешний destination запрещены по умолчанию.
> Разрешение задаётся версионированными allowlist для event contract,
> destination/provider, endpoint/execution profile, model qualification,
> purpose и data classification. Для VLM дополнительно обязательны
> `WorkspaceEgressPolicy`, минимизированные page/region locators и provider
> processing/retention policy. Fallback не расширяет разрешение.

Точные allowlist entries являются deploy/workspace policy data, а не
константами доменной модели. Их отсутствие блокирует конкретный внешний вызов,
но не local execution и не подготовку следующего архитектурного документа.

## 14. Acceptance Test Catalogue

Будущая реализация должна трассировать минимум:

| ID | Сценарий | Ожидаемый результат |
|---|---|---|
| AT-AA-01 | valid user, нет active role | deny; audit reason |
| AT-AA-02 | workspace A читает resource B | deny; critical isolation audit |
| AT-AA-03 | expired authority | новая команда deny; старый факт неизменён |
| AT-AA-04 | service пробует human capability | deny |
| AT-AA-05 | local VLM создаёт high-confidence candidate | FactVersion не создаётся |
| AT-AA-06 | external VLM без WorkspaceEgressPolicy | deny до network side effect |
| AT-AA-07 | provider allowed, model/profile нет | deny |
| AT-AA-08 | classification не определена | deny |
| AT-AA-09 | cross-workspace external batch | deny + security audit |
| AT-AA-10 | payload содержит лишнюю страницу/credential | deny/quarantine; вызова нет |
| AT-AA-11 | prompt injection требует сменить destination/tool | envelope неизменён; request не исполняется как command |
| AT-AA-12 | provider fallback после failure | новая authorization evaluation; egress не расширен |
| AT-AA-13 | одинаковое имя модели у local/external | разные execution identity/provenance |
| AT-AA-14 | invalid response schema | rejected/repair, не fact |
| AT-AA-15 | два VLM согласились | candidate не становится подтверждённым фактом |
| AT-AA-16 | audit writer недоступен | external/destructive side effect не начинается |
| AT-AA-17 | audit scan for secrets/full payload | ни одного запрещённого значения |
| AT-AA-18 | reset workspace с VLM artifacts | request/response/prompts/renders удалены; только RD-03 allowlist |
| AT-AA-19 | requester подтверждает свой purge | deny по SoD |
| AT-AA-20 | model/queue подтверждает purge/promotion | deny |
| AT-AA-21 | NTD edition без official provenance/hash | quarantine, не publication |
| AT-AA-22 | отменённая edition заменена | provenance остаётся, active applicability versioned |
| AT-AA-23 | audit reader экспортирует чужой workspace | deny; access attempt audited |
| AT-AA-24 | revoked provider/model qualification | новые invocation deny |
| AT-AA-25 | author пытается review собственной RuleVersion | deny; status не меняется |
| AT-AA-26 | reviewer/service пытается approve RuleVersion без class-qualified human grant | deny |
| AT-AA-27 | workspace A включает/читает RuleVersion workspace B | deny + isolation audit |
| AT-AA-28 | model создаёт или утверждает Workspace RuleVersion | deny |
| AT-AA-29 | RuleSet upgrade без полного impact/compatibility evidence либо terminal workspace | deny; old pin remains active |
| AT-AA-30 | unresolved conflict передан LLM или unqualified human | deny; conflict/indeterminate остаётся blocker |
| AT-AA-31 | data classification missing/ambiguous/expired | external invoke deny |
| AT-AA-32 | sensitive/local-only payload запрошен external без explicit allow | deny до adapter/network |
| AT-AA-33 | budget policy/floors отсутствуют | qualification/invocation deny |
| AT-AA-34 | professional-impact Candidate без required confirmer | auto-confirm deny; authority task |
| AT-AA-35 | provider terms version changed | qualification suspended; invoke deny |
| AT-AA-36 | fallback пытается унаследовать primary authorization | deny; required new decision/attempt |
| AT-AA-37 | raw artifact читается другой workspace/ролью | deny + security audit |
| AT-AA-38 | cost reservation выше remaining envelope | invoke deny; controlled batch stop |
| AT-AA-39 | VPS NodeIdentity пытается подтвердить Fact/Rule/Promotion/finalization/destruction | deny; node role has no human/domain authority |
| AT-AA-40 | inter-node transfer с unknown/revoked NodeIdentity | deny before payload movement; identity failure audited |
| AT-AA-41 | VPS accepted staging выдаётся как canonical acceptance | rejected contract/status; only MBP acknowledgement may be authoritative |
| AT-AA-42 | S3 credential workspace A запрашивает object B | deny without disclosure; critical isolation audit |
| AT-AA-43 | external VLM route меняется с MBP на VPS | fresh routing/auth/qualification required; inherited decision denied |
| AT-AA-44 | platform/VPS log contains project payload or secret | security failure; quarantine/incident and purge workflow |

## 15. Открытые policy data и архитектурный gate

Нового `Owner Decision Required` для local-first hybrid VLM и Harness policy
architecture нет: ADR-0006 и `HV-01/B…HV-08/B` явно приняты владельцем
2026-08-21.

До первого реального external egress обязательно должны существовать и пройти
утверждение в установленной организации процедуре:

- taxonomy data classifications и mapping документов/страниц, включая
  sensitive/restricted/local-only classes;
- точная `WorkspaceEgressPolicy`;
- provider/destination/model/execution-profile allowlist;
- provider no-training, processing, finite retention, deletion, region,
  subprocessors и credential policy;
- purpose registry и payload minimization limits;
- numerical execution/repair budget matrix;
- approved golden/regression corpus, numerical floors и zero-tolerance tests;
- versioned ConfirmationPolicy и class-authority grants;
- ordered fallback matrix;
- versioned external cost envelope и accounting semantics;
- qualification result для точной model revision/profile;
- incident/revocation/reconciliation runbook.

Это операционные policy instances, а не разрешение «по умолчанию». До их
появления внешний вызов технически должен завершаться `deny`; локальная
обработка и архитектурная очередь не блокируются.

Authorization & Audit Model подготовлена как пункт 4 Blueprint §11. Она не
открывает реализацию персистентности и не разрешает создание provider adapter.
`Deterministic Rules Catalogue v0.1` и Verification Harness Specification
подготовлены; `DR-01/B…DR-04/B` и `HV-01/B…HV-08/B` приняты владельцем
2026-08-21. Harness готов как нормативный вход Information Architecture, но
IA в этой задаче не начинается. Реализация, загрузка НТД и model/API runs этой
спецификацией не разрешаются.
