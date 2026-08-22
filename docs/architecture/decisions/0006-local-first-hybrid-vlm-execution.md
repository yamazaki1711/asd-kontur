# ADR-0006: Local-first hybrid VLM execution

- **Статус:** Accepted
- **Дата:** 2026-08-21
- **Владелец решения:** Олег Щербаков
- **Подтверждение:** сообщение владельца продукта от 2026-08-21,
  начинающееся словами «Важное архитектурное уточнение владельца продукта
  Олега Щербакова от 2026‑08‑21»
- **Связанные документы:** `ARCHITECTURE_BLUEPRINT_v0.1.md`,
  `AUTHORIZATION_AND_AUDIT_MODEL_v0.1.md`,
  `KNOWLEDGE_AND_MEMORY_ARCHITECTURE_v0.1.md`,
  `PROCESS_AND_EVENT_SPECIFICATION_v0.1.md`,
  `TECHNICAL_ARCHITECTURE_v0.2.md`

## Контекст

Ранние документы и текущий пилотный runtime исходили из локального исполнения
OCR/VLM на MBP или другом собственном compute resource. Это было безопасным
исходным ограничением, но не покрывало экономически и по времени массовую
обработку больших корпусов растровых PDF. Одновременно blanket cloud access
несовместим с hard isolation workspace, purpose limitation и доказательностью
АСД-КОНТУР.

Требуется разрешить внешний массовый execution, не отдавая provider доменную
власть, storage access или право расширять egress. Одинаковое имя модели у
локального и внешнего runtime не доказывает эквивалентность ревизии,
квантизации, preprocessing, prompt, схемы, качества или политики обработки.

## Решение

1. АСД-КОНТУР использует **local-first, но не local-only** VLM-архитектуру.
2. Основной локальный VLM на MBP M5 Max 128 GB — `Qwen3.8-27B`. Локальный
   маршрут предпочтителен для юридических, конфиденциальных, сложных,
   интерактивных задач и draft, связанных с исполнительными схемами.
3. Для разрешённой workspace policy массовой обработки растровых PDF допускается
   внешний VLM. Планируемый provider — `polza.ai`; архитектура и доменный
   контракт от него не зависят. Используется `Qwen3.8-27B` либо совместимая
   model revision/execution profile, прошедшая qualification.
4. Все providers реализуют один логический `VlmExecutionProvider` contract.
   Отдельно версионируются provider, endpoint/profile, model revision,
   quantization/execution format, prompt, output schema, preprocessing,
   rendering parameters и verification policy.
5. Любой VLM возвращает только typed `Candidate`/draft с field-level evidence,
   uncertainty, validation results и полным provenance. Ни один ответ модели,
   confidence или согласие нескольких прогонов не является подтверждённым
   фактом.
6. VLM не придумывает и не подтверждает геометрию, координаты, размеры,
   объёмы или юридические факты. Итоговая исполнительная схема строится только
   из подтверждённых проектных и фактических геометрических данных.
7. Native deterministic extraction выполняется первой, если текстовый слой
   пригоден. Provider выбирается router по data classification, workspace
   egress policy, типу/объёму/сложности документа, latency/cost, qualification,
   availability и verification profile.
8. External egress по умолчанию запрещён. Каждый вызов требует отдельной
   integration identity, capability `vlm.external.invoke`, точного
   `workspace_id`, purpose, classification, provider/model/profile allowlist,
   минимизированных page/region locators и применимой provider
   processing/retention policy. Cross-workspace batch запрещён. Fallback не
   расширяет egress permission.
9. Prompt/document content является недоверенным вводом и не может менять
   provider, scope, destination, pages, tools, classification, authority или
   retention policy.
10. Единый VLM Verification Harness обязателен. Он использует конкретные
    machine-generated validation failures, bounded targeted repair cycles,
    terminal typed outcomes и regression/golden corpus. Его отдельная
    спецификация создаётся позднее по Blueprint и не реализуется этим ADR.

## Последствия

- Прежнее универсальное допущение «OCR/VLM выполняется локально/на собственном
  compute resource» заменено provider-neutral external execution boundary.
  Ограничение «VPS `kat-core` не размещает VLM inference» остаётся в силе и не
  означает local-only.
- `Extraction Candidate Adapter` остаётся единственным входом результата в
  application/domain boundary. Внешний provider не получает SQL, Knowledge
  Gateway или прямой доступ к workspace storage.
- Authorization Model обязан различать internal service identity, external
  integration identity и model execution identity; audit сохраняет digests и
  provenance вызова без полного документа, prompt, response или credentials.
- Project request/response/render artifacts остаются workspace memory и
  уничтожаются по `RetentionProfile`; RD-03/A не позволяет переносить их в
  platform audit после reset.
- До утверждения точных data classification, `WorkspaceEgressPolicy`,
  provider processing/retention policy и allowlist внешний маршрут остаётся
  fail-closed. Сам ADR не разрешает отправку конкретного документа.
- Будущий `AI_VLM_EXECUTION_AND_VERIFICATION_HARNESS_SPECIFICATION_v0.1.md`
  становится обязательным module/API/AI-tool contract после Deterministic
  Rules Catalogue и до Information Architecture.

## Рассмотренные и отклонённые альтернативы

### A. Local-only

Отклонено как общее продуктовое ограничение: не обеспечивает требуемую
пропускную способность массовых растровых корпусов и не использует допустимый
экономический внешний execution. Local execution сохраняется как основной и
обязательный безопасный маршрут.

### B. External-first или provider lock-in

Отклонено: создаёт зависимость домена от одного API, ослабляет локальность
чувствительных сценариев и смешивает transport contract с evidence model.

### C. Blanket egress для workspace

Отклонено: противоречит purpose limitation, data minimization и hard
isolation. Разрешение вычисляется для точных pages/regions, provider,
model/profile и purpose.

### D. Два независимых контракта local/external

Отклонено: делает provenance, validation и сравнение качества несопоставимыми.
Физические adapters различаются, логический request/result contract един.

### E. Согласие двух VLM как подтверждение

Отклонено: коррелированные ошибки и одинаковый model lineage не дают
независимого доказательства. Confirmation остаётся детерминированным и/или
профессиональным процессом по типу факта.

## Проверки принятого решения

Будущие acceptance tests должны доказать: default deny внешнего egress,
изоляцию workspace, невозможность prompt-driven scope escalation, раздельный
provenance одинаково названных моделей, отсутствие секретов/контента в audit,
bounded verification/repair, невозможность создания FactVersion моделью и
полное удаление workspace VLM artifacts при reset.

Этот ADR не создаёт provider adapter, не выбирает transport API `polza.ai`, не
загружает НТД, не запускает модели и не разрешает реализацию персистентности.
