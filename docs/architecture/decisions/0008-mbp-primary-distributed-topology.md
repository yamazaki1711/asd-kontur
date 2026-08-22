# ADR-0008: MBP-primary distributed topology

- **Статус:** Accepted
- **Дата:** 2026-08-21
- **Владелец решения:** Олег Щербаков
- **Подтверждение:** текущее явное сообщение владельца продукта от
  2026-08-21, начинающееся словами «Продолжай работу как ведущий системный
  архитектор АСД-КОНТУР» и содержащее принятый топологический принцип
  «АСД-КОНТУР физически базируется на MBP M5 Max, но обязан использовать
  возможности VPS и S3-совместимого объектного хранилища»
- **Заменяет:** placement-утверждения Technical Architecture v0.2 и ранних
  deployment-документов в части размещения production domain core и
  канонической PostgreSQL на VPS; их проверенные факты и исторический контекст
  не аннулируются

## Контекст

Ранее подготовленные технические и эксплуатационные документы рассматривали
локальный MBP преимущественно как узел разработки и VLM, VPS — как место
production API, worker и PostgreSQL, а S3 — как удалённое файловое хранилище.
Такое распределение противоречит принятой владельцем продукта роли MBP и
создаёт риск трёх разрозненных систем, конкурирующих источников истины и
неявного failover.

АСД-КОНТУР должен оставаться одним объектно-независимым комплексом с общей
канонической моделью для `Tender`, `Support`, `Audit` и `Restoration`.
Физическое распределение функций не меняет authority информации, hard
isolation, provenance, retention или правило, что AI/VLM создаёт только
`Candidate` либо draft.

## Решение

1. АСД-КОНТУР является local-first распределённым комплексом с одним
   логическим ядром.
2. MBP M5 Max выполняет роль `primary authoritative node`: на нём находятся
   каноническое доменное состояние и PostgreSQL, platform memory, база НТД,
   Rule Registry и `RuleSetVersion`, canonical workspace state, Knowledge
   Tool Gateway, детерминированное ядро, основной локальный Qwen3.8-27B,
   подтверждение профессионально значимых фактов, Promotion Gate,
   финализация результатов и подготовка/авторизация lifecycle-операций.
3. VPS выполняет сетевую, координационную и интеграционную роль: будущие API
   ingress, удалённый доступ, web/UI delivery, authentication gateway,
   bounded queues, приём команд и загрузок, webhooks, уведомления,
   интеграции, operational health/status и контролируемый external egress.
4. S3-совместимое хранилище выполняет роль обязательного durable object plane
   для разрешённых RetentionProfile platform/workspace objects: источников и
   крупных бинарных объектов, renders, временных raw artifacts, exports,
   portable logical archives, manifests/hashes, encrypted backups и recovery
   objects.
5. VPS и S3 не получают независимого доменного ядра и не являются
   альтернативными system of record для фактов, НТД, правил, workspace state
   или финальных результатов. PostgreSQL хранит identity, metadata, scope,
   lineage, policy state и ссылки; S3 хранит байты и доказательные объектные
   пакеты.
6. В комплексе существует одна логическая каноническая модель. Все узлы
   используют единые identifiers, scopes, schemas, provenance и retention.
7. Передача данных между MBP, VPS, S3 или external provider не изменяет их
   authority, classification либо статус подтверждения.
8. Недоступность узла не разрешает silent fallback, fire-and-forget success
   или создание альтернативного SoR. VPS не выдаёт staging/получение за
   каноническое принятие authoritative core; S3 write не является принятием
   доменного состояния.
9. Одновременно допустим только один active authoritative primary. VPS не
   становится primary автоматически, S3 не становится executable state, а
   automatic last-write-wins для доменного состояния запрещён.
10. Восстановление authoritative node на заменяющем оборудовании должно быть
    проверено и явно активировано уполномоченным решением. Конфликтующие
    primary claims переводят комплекс в `RECOVERY_REQUIRED` или
    `QUARANTINED`, а не разрешаются автоматически.
11. Identity комплекса не связывается с серийным номером или единственным
    физическим экземпляром MBP; доказанное восстановление authoritative role
    на заменяющем оборудовании является обязательной возможностью.
12. Точные механизмы синхронизации, репликации, encryption, network topology,
    RPO/RTO, failover, key management, S3 isolation и маршрута external VLM
    определяются в Technical Architecture v0.3. До их определения
    соответствующие операции действуют fail-closed.

## Последствия

- VPS остаётся обязательной полезной частью комплекса, но его accepted/staged
  envelopes, queues, projections и UI не получают доменную authority.
- S3 обязателен как durable object plane, но archive, active object, backup,
  WAL/snapshot и provider residue остаются разными информационными и
  retention-классами.
- Workspace isolation и доказанная очистка охватывают MBP, VPS, S3 и
  external-provider residues; `DestructionAttestation=verified` невозможен
  без проверки всех обязательных adapters.
- Все межузловые операции требуют scoped identity, schema/version, digest,
  authorization, idempotency, acknowledgement, audit и reconciliation при
  неизвестном результате.
- Отказ VPS не уничтожает каноническое состояние MBP; отказ S3 блокирует
  операции, для которых подтверждённая durable object write является
  precondition; отказ MBP блокирует каноническое принятие и финализацию.
- Восстановление не является автоматическим failover. Restore candidate
  сначала проверяется, затем отдельно активируется; split-brain запрещён.
- Technical Architecture v0.2 и ранние deployment/operations документы
  сохраняются как исторические источники проверенных деталей, но их
  VPS-primary placement нельзя реализовывать после принятия ADR-0008.
- Решение не открывает implementation gate и не выбирает конкретные протокол,
  PostgreSQL replication, KMS, S3 provider, bucket layout или network product.

## Отклонённые альтернативы

- local-only комплекс без обязательных ролей VPS и S3;
- VPS-primary или active-active domain core;
- S3 как доменная база либо authoritative current state;
- три независимые платформы с разными identities и schemas;
- автоматический failover или last-write-wins без verified restore и explicit
  primary activation;
- привязка authority к неизменяемому физическому идентификатору одного MBP.

## Связанные документы

- `../INFORMATION_ARCHITECTURE_v0.1.md`;
- `../AUTHORIZATION_AND_AUDIT_MODEL_v0.1.md`;
- `../LIFECYCLE_AND_RETENTION_SPECIFICATION_v0.1.md`;
- `../PROCESS_AND_EVENT_SPECIFICATION_v0.1.md`;
- `../KNOWLEDGE_AND_MEMORY_ARCHITECTURE_v0.1.md`;
- `../AI_VLM_EXECUTION_AND_VERIFICATION_HARNESS_SPECIFICATION_v0.1.md`;
- `../TECHNICAL_ARCHITECTURE_v0.2.md`;
- `../ARCHITECTURE_BLUEPRINT_v0.1.md`.
