# ADR-0012: Bounded official NTD platform memory

- **Статус:** Accepted
- **Дата:** 2026-08-25
- **Владелец решения:** Олег Щербаков
- **Источник authority:** явная директива владельца NTD-SEED-01 от 2026-08-25

## Контекст

«Пособие по исполнительной документации» обнаруживает нормативные ссылки, но
не подтверждает редакцию, статус, применимость, обязательность или содержание
НТД. ADR-0009 установил постоянный platform-контур НТД, а ADR-0011 отделил от
него `methodological_practice`. Для первого доказательного наполнения выбран
bounded-корпус ссылок с PDF-страниц 15–19 пособия. Он не разрешает рекурсивное
скачивание связанных документов или массовую обработку всего каталога.

## Решение

1. Вводится отдельный permanent authority layer `normative_authority`. Его
   canonical данные не имеют `workspace_id`, доступны workspace read-only
   только через Knowledge Gateway и переживают reset/archive/destroy ОКС.
2. Источник discovery и нормативный источник разделены:

   - `PracticeGuideNormativeReference` хранит exact guide edition, печатную
     ссылку, PDF page/region и immutable resolution decision;
   - `NormativeDocument` задаёт stable identity;
   - `NormativeEdition` задаёт immutable official edition;
   - `NormativeArtifact` связывает edition с exact official catalog record,
     URL, `SourceVersion`, MIME, bytes и SHA-256;
   - `NormativeProvisionCandidate` хранит результат extraction/OCR/VLM до
     проверки;
   - `NormativeProvisionVersion` публикует только verified exact text с
     edition и locator;
   - `NormativeActivationDecision` и `NormativeApplicabilityDecision`
     отдельно и версионируемо выбирают edition/status/as-of/applicability.
3. Mutable `latest` запрещён. Повторная регистрация official edition и digest
   идемпотентна; новая редакция получает новую identity, а прежняя остаётся для
   provenance. Timeline строится только из official metadata или exact
   provisions посредством `NormativeEditionRelationship`.
4. Official acquisition использует bounded `MinstroyCatalogueClient` и только
   allowlisted HTTPS endpoint Минстроя. Search result является candidate, а не
   official edition. Каждая попытка получает immutable receipt, включая query,
   returned/selected/rejected records, HTTP metadata, digest и typed terminal
   outcome. Сторонняя копия не заменяет недоступный official artifact.
5. Source bytes и HTML находятся в content-addressed platform object plane вне
   Git. Canonical metadata, editions, provisions, gaps, conflicts и decisions
   находятся в PostgreSQL `platform`. Exact/FTS/vector/graph — удаляемые и
   воспроизводимые projections.
6. Обработка является native-first: MIME/signature, native text/layout и
   hierarchy предшествуют OCR. OCR применяется только к непригодным native
   regions; VLM — только к bounded unresolved regions. VLM создаёт candidate,
   но не определяет official status, edition, applicability или obligation.
7. `VerifiedNormativeProvision` требует exact edition, official artifact,
   page/section/clause/table/form locator, verbatim evidence digest и отдельное
   verification decision. Provision не становится `RuleVersion`: Rule Gate
   остаётся единственным путём в Deterministic Rule Registry.
8. Practice/NTD alignment является отдельной immutable связью. GuidanceUnit не
   переписывается: подтверждение, `practice_only`, edition warning, gap или
   conflict сохраняются как новые cross-layer decisions.
9. Gateway детерминированно разделяет `normative_provision`,
   `practice_recommendation`, `deterministic_rule` и `workspace_fact`. При
   отсутствии exact evidence возвращается `no_result`/`knowledge_gap`; при
   неоднозначности или конфликте content не выдаётся как действующее
   требование. Qwen не получает direct SQL.
10. Backup manifest pin-ит official object digests, SourceVersions, edition
    chains, verified provision fingerprints, decisions, gaps/conflicts и
    projection profile. Restore проверяет byte и semantic integrity; смена
    model/provider не меняет canonical fingerprint.

## Bounded seed

Seed строится детерминированно из exact geometry PDF-страниц 15–19 canonical
`PracticeGuideEdition`. Ожидаемая reconciliation — 37 отдельных печатных
упоминаний и 25 stable identities. Любое расхождение блокирует acquisition до
его доказательного объяснения. Cross-reference внутри НТД за пределами этих 25
identity сохраняется как `external_reference_gap` и не расширяет загрузку.

## Последствия

- Пособие остаётся методикой, а не нормативной authority.
- НТД является model-independent permanent platform memory.
- Конкретный ОКС получает отдельное `ApplicabilityDecision`; наличие edition в
  platform memory не означает её применимость.
- Partial official availability даёт честный `PARTIAL` с terminal gaps, но не
  допускает стороннюю подмену или empty success.
- Historical KG-ID receipts и acceptance decision не меняются.

## Отклонённые альтернативы

- считать печатную ссылку пособия подтверждённым НТД;
- выбирать current edition по mutable `latest` или похожести названия;
- хранить official artifacts в Git или workspace;
- публиковать OCR/VLM candidates без exact evidence;
- автоматически создавать RuleVersion из текста НТД;
- рекурсивно скачивать весь граф cross-references.

## Связанные решения

- [ADR-0005](0005-knowledge-platform-and-workspace-isolation.md)
- [ADR-0009](0009-platform-ntd-and-workspace-customer-regulation.md)
- [ADR-0011](0011-permanent-model-independent-id-practice-intelligence.md)

