# SUPPORT-PRODUCTION-ID-02

Status: `BOUNDED PASS — qualified official AOSR template and finalized package lifecycle`

## Что теперь умеет АСД-КОНТУР как продукт

Для evidence-bound работы в synthetic acceptance workspace АСД-КОНТУР теперь может:

- выбрать официальный рекомендуемый образец АОСР из exact source edition приказа Минстроя
  России от 16.05.2023 № 344/пр;
- заполнить immutable `TemplateVersion` только подтверждёнными `FactVersion`, сохраняя
  `EvidenceLink`, `SourceLocator`, normalized и display value каждого материального поля;
- создать PDF `GeneratedDocumentCandidate` через общий durable job, проверить структуру,
  печатную геометрию и layout и показать immutable validation receipt;
- отделить routine generation от professional review и independent finalization;
- создать `FinalizedDocument`, заменить candidate-membership новой immutable package version,
  пересобрать реестр из фактического ordered состава и сохранить все прошлые версии;
- показать через существующий Product Spine template authority, print/review/finalization state,
  package membership, текущий реестр, field provenance и честно отсутствующие документы;
- скачать как candidate, так и finalized PDF через scoped Range-capable API;
- пережить потерю generation worker, физический PostgreSQL backup/restore и workspace reset,
  не потеряв platform `TemplateSource`/`TemplateVersion` и не открыв данные другому workspace.

Комплект намеренно остаётся incomplete: исполнительная схема и документы качества не
фабрикуются. После финализации АОСР readiness имеет `required=4`, `finalized=1`, `missing=2`,
`blocked=1`; methodological attachment остаётся advisory blocker, а не нормативной
обязанностью.

## Template authority result

Первый production-qualified template family: `support.aosr`.

- authority: приказ Минстроя России от 16.05.2023 № 344/пр;
- exact official artifact: Minstroy PDF, 29 pages;
- official source URL: `https://minstroyrf.gov.ru/upload/iblock/e22/l0ve6l2xl4ibupz7nlnn6wl7oxeab12i/%D0%BF%D1%80%D0%B8%D0%BA%D0%B0%D0%B7%20344%D0%BF%D1%80%20%D0%9C%D0%B8%D0%BD%D1%8E%D1%81%D1%82.pdf`;
- official source SHA-256:
  `sha256:973f13dda66cddab398d7ee4f969a2e4bbfb600d37c76b7687580a89904de500`;
- exact form pages: source pages 13–16, four A4 pages;
- source edition: `ru:minstroy:order:2023-05-16:344-pr:initial-edition`;
- immutable qualified form subset digest:
  `sha256:7b6ef66cc34c76d49c9fa83faf9ef2d3e6ac3b35a009cbe2011777620e40267f`;
- deterministic `TemplateSource`: `fe8eaab4-0bec-5c8a-bfdc-0ea2d5db4c78`;
- deterministic `TemplateVersion`: `a9b35377-866d-5cc0-ace8-74c57e4304d5`,
  version `344pr-2023@1.0.0`;
- qualification receipt:
  `sha256:46146d22afd3dd4cc3745e0a3d6f72f17b1b6b65d9fd208924cea740c6b296a7`;
- qualification state: `active / production / verified / qualified`.

The official source bytes and generated documents remain in controlled object storage outside
Git. The checked-in JSON profile contains only versioned page selection and binding geometry.
Order 369/pr dated 23.06.2025 was reconciled as an amendment to procedure point 5; it does not
replace Appendix 3's recommended AOSR form. The legacy DOCX remains an unverified development
candidate and is not used as authoritative template bytes.

## Template, rendering and print qualification

The general pipeline is data-driven:

`TemplateSource → TemplateVersion → FieldSchema → BindingPlan → renderer profile → validator profile`.

The PDF renderer has no branch for AOSR. The versioned profile supplies 28 required/optional
bindings, exact pages, regions, typography and material-field semantics. Every render starts
from fresh immutable template bytes and an exact font asset. Missing, candidate or conflicted
material values fail closed; generated output cannot become a template.

Qualification and print validation prove:

- exact official source and edition pinning;
- exact four-page sequence and A4 geometry;
- bounded, non-overlapping field boxes;
- complete required bindings and confirmed material fields;
- preserved template text, page geometry and pagination;
- extractable rendered values and embedded renderer font;
- bounded multiline layout without clipping/overflow;
- no unresolved placeholder syntax or stale prior-run data;
- no PDF JavaScript, embedded active content or external URI dependency.

The final deterministic acceptance render produced:

- candidate digest:
  `sha256:f4e7308c71ea37e2f69e3e86fefe3bf16a76b62166396c893977899eb9a2c84b`;
- semantic fingerprint:
  `sha256:0db965d2345fbe94e27163a6c022df2d723e4baccd2fab883c6a534429472170`;
- print/layout receipt:
  `sha256:a258026d3a1a278750bafe7f73092935307797e64246abf572999853c2165914`;
- result: `print_ready`.

The PostgreSQL acceptance path separately confirmed all 28 profile fields from synthetic
candidate evidence into 28 exact `FactVersion` records before starting the official-template
generation run. The resulting official-profile PDF then traversed the same durable candidate,
review, finalization, package and register path; it was not substituted with the development
DOCX or a reduced one-field template.

Rendered pages were rasterized and inspected during qualification. Two detected binding defects
(materials and appendices) were corrected in the versioned profile before the final receipt.
The result is qualified for the bounded AOSR profile; no wider pixel-perfect claim is made for
other forms or viewers.

## Generation and finalization

`ID_DOCUMENT_GENERATION` continues to use the existing Product Spine durable-job engine. Same
idempotency key plus identical semantic input returns the original job; changed input creates a
new run/version. A lost lease is recovered by another worker without duplicating the canonical
candidate.

Finalization is a separate material transition:

1. qualified template and `print_ready` receipt;
2. explicit `support.document.review` professional grant and immutable approved review decision;
3. a different identity with `support.deliverable.finalize` grant;
4. immutable `FinalizedDocument` tied to candidate, validation, review, template and source
   lineage.

Synthetic grants are used only inside disposable acceptance tests and are never represented as
production personnel qualification. Unqualified legacy candidates remain downloadable drafts
but cannot be reviewed/finalized through this path.

## Package and register evolution

The acceptance lifecycle creates four immutable package/book/register versions:

1. formed package: AOSR missing;
2. legacy development candidate: generated but template-blocked;
3. qualified PDF candidate: `generated_candidate`, `print_ready`;
4. approved finalization: AOSR membership points to exact `FinalizedDocument`.

Each transition creates a new `PackageVersion`, `VolumeBookVersion` and membership set. Register
ordinal 1 is derived from that exact set and lists only body documents from ordinal 2 onward.
Candidate→finalized, reorder, copy/stage change and removal all produce a new register; old
registers remain immutable. Duplicate ordinals, self-listing and a listed/actual composition
divergence fail closed. The acceptance database contains 4 package versions, 4 books, 20
membership versions and 4 register versions.

Package readiness excludes the register itself from the required-document denominator while
still retaining register blockers. It distinguishes generated, finalized, missing, blocked,
conflict, indeterminate and not-applicable states rather than hiding them in a percentage.

## Product Application and API

The existing FastAPI → generated OpenAPI client → React Product Spine was extended, not forked.
The Support surface shows:

- candidate versus finalized state;
- exact template/version and authority qualification;
- structural and print validation outcome;
- review and finalization state;
- field values with evidence links;
- package membership and current register fingerprint;
- incomplete/missing/blocked package members;
- candidate and finalized download.

Added typed commands/queries include candidate review, candidate finalization, finalized content
streaming and package backup manifest creation. Transport contains no SQL. OpenAPI regeneration
is byte-reproducible; generated TypeScript SHA-256 remained
`71d9a30fa7382b6ea2f9ecc4ab2f1576c0a7485f415fdd03858ce87ad2c62f44`.

Live Playwright, seeded with the exact official source bytes and the 28-field profile, proves
login → Support package → register ordinal 1 → finalized AOSR status → template/print/review
provenance → exact evidence link → finalized PDF download. The separate live test still proves
worker kill/recovery and isolated workspace reset.

## Lifecycle: backup, restore and reset

`support_package_backup_manifests` records the full canonical package history, memberships,
registers, runs, candidates, finalized documents and exact object digests. Repeating the command
is idempotent.

A populated physical PostgreSQL `pg_dump`/`pg_restore`, paired with the copied object plane,
reproduced the exact canonical payload:

- database fingerprint:
  `sha256:6bec009cac82cc92686f077c346a908a9d3c22478256e3812e4c7efcf3cf78e0`;
- package backup manifest fingerprint:
  `sha256:a3f8235404c2d5ceef1247476e47577dab6226976edc4e7b1e05471c8378c309`;
- object digest references: 2; restored object files: 6;
- dump digest:
  `sha256:39f1e19c935dbd372d208afc7e9ff09bfbb83f61a0c9cbdb9a48a1816bed7e70`.

Support package state is canonical rather than a disposable read projection, so application view
reconstruction reads the same immutable tables; no second package projection or rebuild engine
was introduced. Existing rebuildable knowledge projections remain independent.

Workspace reset with populated state deletes package/book/membership/register history,
generation plans/runs/receipts, candidates, reviews, finalized documents, backup manifests and
workspace objects. A residual scan returns zero. Platform template source/version/qualification
and renderer assets survive; workspace B is unchanged. The lifecycle deletion order was fixed
generically for job bindings, package→matrix and matrix→ProjectDefinition foreign keys.

## Selective legacy reuse

Legacy evidence remains
`/Users/oleg/mac_asd/library/templates/acts/344pr/3_AOSR.docx` and the recorded AOSR field/form
semantics. Decision remains selective `REUSE_AFTER_HARDENING` for semantic and regression intent
only. The legacy DOCX bytes, mutable generator state, filename identities and hidden fallbacks
were not reused.

Modern implementation uses the official Minstroy PDF, immutable source/edition identities,
data-only binding plan, stateless rendering, evidence-bound fields, deterministic receipts,
workspace isolation and Product Application access. This is not a copy of the legacy generator.

## Verification

- `uv lock --check`: passed;
- Ruff format/lint: passed (`369` files formatted/check-clean);
- strict mypy: passed (`153` source files);
- full Python suite with PostgreSQL: `476 passed`, one upstream Starlette deprecation warning;
- migration head: `0026_support_id_finalize`;
- clean disposable downgrade/upgrade round trips: passed as part of the full suite;
- RLS/default-deny, immutable write fences and cross-workspace denial: passed;
- populated package logical backup, physical backup/restore and residual reset: passed;
- frontend format/typecheck/lint/tests/build: passed (`2` test files, `3` tests);
- Playwright live suite: `3 passed`, `1` explicitly opt-in NTD test skipped because no NTD seed
  was requested; both Support finalization and worker-loss/reset live journeys passed;
- OpenAPI/generated client reproducibility: passed;
- Python dependency audit: no known vulnerabilities; license inventory accepted, including
  ReportLab BSD;
- frontend dependency audit: zero vulnerabilities at `high` threshold;
- forbidden PDF/model/dump/key/environment and credential scans: passed; official/source/output
  bytes remain outside Git;
- `git diff --check`: passed.

## Remaining blockers and readiness

- the package remains intentionally incomplete until real executive-scheme geometry and quality
  documents/evidence exist;
- qualified electronic signing, handover and legally significant signature evidence are outside
  this bounded slice;
- a second production-qualified template family was not added: no second exact official
  authority was established in scope, and an unqualified form was not promoted for quantity;
- the official AOSR form is a recommended sample; applicability and required-document basis
  still depend on exact active rule/contract/project context for each real ОКС;
- no real ОКС, TM-35-specific behavior, CAD generation, Android work, mass NTD acquisition or
  mass Polza processing was introduced.

Therefore:

- `SUPPORT-PRODUCTION-ID-02 = BOUNDED PASS` for the first qualified template/finalization and
  package-lifecycle vertical;
- `SUPPORT-PRODUCTION-ID-01 = PARTIAL` remains its historical checkpoint;
- `ProductApplicationReady = PARTIAL`;
- `TrialReady = false`;
- `OKSReady = false`;
- `ProductReady = false`.
