# SUPPORT-PRODUCTION-ID-01

Status: `PARTIAL — production-shaped candidate workflow implemented; authoritative template/finalization blocked`

## Что теперь умеет АСД-КОНТУР как продукт

Для evidence-bound `ConstructionWorkPackage` Product Application теперь:

- показывает требуемые документы ИД из exact `WorkRequirementMatrix` с раздельными authority layers, основаниями, gaps и conflicts;
- формирует immutable `PackageVersion` и `VolumeBookVersion` с ordered `DocumentMembershipVersion`;
- помещает формируемый из фактического состава реестр первым документом книги (`ordinal=1`), не используя независимый список состава;
- показывает АОСР, исполнительную схему, документы качества и приложения как разные package memberships с честными состояниями;
- разрешает материальные поля только из confirmed `FactVersion` + `EvidenceLink` + `SourceLocator`; missing/conflict не подставляются;
- запускает fresh, idempotent `GenerationRun` через общий durable-job engine;
- после worker processing создаёт новый immutable package/book/membership version, пересобирает реестр и сохраняет старую версию;
- позволяет открыть и скачать generated DOCX candidate через существующий FastAPI → generated OpenAPI client → React Product Spine;
- показывает источник каждого поля, причины incomplete/blocked и состояние generation job;
- сохраняет workspace isolation: другой owner/workspace не получает package, job или artifact.

Первый template family — `support.aosr`. Найденный legacy DOCX допускается только как
`development_candidate`: его authority не подтверждена, поэтому результат не становится
`FinalizedDocument`, а readiness содержит `TEMPLATE_NOT_PRODUCTION_QUALIFIED`.

## Targeted gap audit

| Chain link | До slice | Реализовано в slice | Остаточный gap |
|---|---|---|---|
| WorkRequirementMatrix → ID requirements | Canonical harness и PostgreSQL projection | Typed application query, source layer, RuleTrace/evidence/gaps | Полнота зависит от verified/active normative coverage |
| Template selection | WP-13 contract, legacy inventory | Version-pinned template/source/schema/mapping/artifact contract | Official AОСР template authority не квалифицирована |
| Field resolution | WP-13 synthetic foundation | Confirmed fact/evidence/locator binding; fail-closed material fields | Нужны дополнительные production field schemas |
| Generation | Synthetic OOXML qualification mechanics | Fresh deterministic template-backed DOCX candidate + durable job | Production renderer/layout qualification не пройдена |
| Package assembly | `id_package_versions` audit foundation | Package/book/ordered membership versions | Signature/handover lifecycle вне bounded slice |
| Register | Architecture contract only | Derived structured register candidate from exact membership version | Qualified register TemplateVersion отсутствует |
| Preview/export | Product Spine gap | Browser details, evidence, durable status, Range-capable download | Package ZIP/PDF export и final signing не реализованы |

Существующие `RequiredIDDocument`, `DocumentRequirement`, `IDPackage`, support generation
и application job tables сохранены. Альтернативный `DocumentObligation` или второй job engine
не создавались.

## Domain and persistence

`migrations/versions/0025_support_production_id.py` добавляет:

- `platform.template_artifacts`;
- `platform.template_field_definitions`;
- `platform.required_document_type_templates`;
- `workspace.id_package_volume_book_versions`;
- `workspace.id_package_document_membership_versions`;
- `workspace.support_register_candidates`;
- `workspace.id_package_readiness_evaluations`;
- `workspace.support_generation_job_bindings`;
- durable job kind `ID_DOCUMENT_GENERATION`.

`id_package_versions.rule_set_version_id` допускает `NULL` только для честного candidate
package с blocker `RULE_SET_VERSION_UNRESOLVED`; authoritative transition при этом запрещён.
Все новые workspace tables имеют RLS/default-deny, material write fence и immutable version
guards. Product application и document worker получили минимальные scoped policies к уже
существующим WP-13 tables.

## Package and register invariants

- register membership относится к той же package/book version и всегда имеет ordinal 1;
- ordinal уникален, membership order непрерывен;
- register manifest содержит только фактические non-register memberships данной версии;
- copies берутся из membership requirement;
- completed generation создаёт новую package version, не изменяя старую;
- register новой версии воспроизводимо пересобирается из нового состава;
- executive scheme без confirmed geometry остаётся required/missing, выдуманная геометрия не создаётся.

## Template platform and selective legacy reuse

Legacy evidence: `/Users/oleg/mac_asd/library/templates/acts/344pr/3_AOSR.docx` и связанная
семантика АОСР из inventory. Decision: `REUSE_AFTER_HARDENING` только для form intent,
field semantics и regression evidence; legacy stack/state не переносится.

Modern implementation:

- immutable `TemplateSource`/`TemplateVersion`/artifact digest;
- versioned `FieldSchema` and binding plan;
- fresh stateless render for every run;
- exact template digest verification;
- no VBA/external-link parts;
- deterministic ZIP metadata and semantic fingerprint;
- unresolved material field blocks render;
- candidate template cannot produce finalized/authoritative output.

No generated document becomes a template, and no prior-run values can accumulate.

## Application API and UI

Added operations:

- `GET /api/v1/workspaces/{workspace_id}/support/id-production`;
- `POST /api/v1/workspaces/{workspace_id}/support/id-packages`;
- `POST /api/v1/workspaces/{workspace_id}/support/generation-runs`;
- `GET /api/v1/workspaces/{workspace_id}/support/generated-candidates/{candidate_id}/content`.

The Product Spine route `Support / ID Package` shows requirement authority/evidence,
package/readiness, ordered memberships, register, field sources, gaps, durable job state and
candidate download. OpenAPI remains the source of the generated TypeScript client.

## Durable execution and recovery

One page/job engine is not duplicated. `ID_DOCUMENT_GENERATION` uses the existing lease,
attempt, retry, idempotency and terminal receipt model. Same idempotency key plus same semantic
input returns the original job; different input is a conflict. Interactive document generation
has higher scheduling priority than background document inventory. The worker can recover an
already-created candidate and complete the package-version projection without duplicating it.

## Acceptance evidence

The synthetic product scenario contains one work package and four non-register requirements:

1. AОСР candidate;
2. executive scheme required but geometry/output missing;
3. material quality documentation missing;
4. methodological control attachment blocked as non-normative guidance.

Together with the register this yields five ordered memberships. PostgreSQL integration proves:

- package version 1 formation;
- register ordinal 1;
- same-key generation replay;
- expired running generation lease recovery by a new worker;
- worker processing and generated candidate;
- package version 2 and regenerated register;
- confirmed field evidence;
- template qualification blocker;
- cross-workspace denial.

Current focused results:

- domain/support unit tests: `4 passed`;
- support + migration + production integration: `9 passed`;
- all unit tests: `403 passed`;
- authenticated API view and Range download: passed;
- full Python suite: `474 passed`;
- full integration suite: `71 passed`;
- Ruff: passed;
- strict mypy (`src/asd_kontur`): passed;
- `uv lock --check`: passed;
- frontend format/typecheck/lint/tests/build: passed (`2` files / `3` tests);
- OpenAPI client generation: passed;
- live Support browser path: passed against disposable PostgreSQL, object plane and generated
  DOCX candidate; the broader Playwright suite retains one opt-in NTD test skip when its seed
  flag is absent.

## Remaining blockers and readiness

- official authority/provenance of the first AОСР template is unresolved;
- production DOCX layout/print profile is not qualified;
- no legal/professional finalization or signature evidence is fabricated;
- executive scheme renderer remains blocked by missing confirmed geometry/CAD capability;
- normative coverage and active RuleSet coverage remain incomplete;
- package export beyond individual generated candidate is not yet qualified.

Therefore:

- `SUPPORT-PRODUCTION-ID-01 = PARTIAL`;
- `ProductApplicationReady = PARTIAL`;
- `TrialReady = false`;
- `OKSReady = false`;
- `ProductReady = false`.

No real ОКС data, TM-35 logic, Android client, mass NTD recovery or mass Polza processing is
part of this slice.
