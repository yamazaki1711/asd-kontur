# OZERO Tender delivery changes

## 2026-09-18 — readable preliminary Tender findings

- `38f637b` replaces the raw defect object on the Russian “Расхождения и пробелы”
  surface with readable preliminary Tender observations. Each card carries the affected
  candidate identities, its open/candidate state, and links only to its persisted exact
  source locators. It does not convert an unresolved comparison into a confirmed
  omission, noncompliance, or professional decision.
- The API/frontend launchd binding was corrected from a stale release tree to the
  controlled current worktree. Loopback readiness and the served asset identity were
  verified after restart; browser-authenticated acceptance remains unverified.

## 2026-09-12 — current processing coverage versus historical retries

- 4f41617 calculates accepted and failed fragment identities separately, then exposes
  unresolved failed coverage only where no accepted successor exists. It avoids
  misrepresenting a recoverable historical retry as the current document state.
- The change was validated with 22 focused spine tests, frontend format/type/lint
  checks, and execution of the scoped coverage query on OZERO. It is a staged release,
  not proof of browser rendering or complete project analysis.

## 2026-09-12 — bounded malformed-leaf recovery candidate

- `a898ca3` keeps Qwen schema and evidence validation strict. A failed terminal
  single-fragment repair is persisted as typed unresolved coverage rather than
  accepted data, while the remaining batches of the source can complete. This prevents
  one pathological model response from rolling back independent accepted evidence or
  starving other eligible documents.
- The change is not deployed. The worker is deliberately kept on its current release
  until its active Qwen request reaches a terminal boundary.

## 2026-09-11 — exact-evidence graph navigation

- `6739b20` adds graph components composed only of source-scoped relationship endpoints
  that have an exact same-evidence resolution. The API and Russian project-model UI
  expose the component separately from source-scoped dossiers; cross-document names are
  never auto-merged and components remain `candidate_only` evidence.
- Live verification at migration `0047` found 32 such components in the existing OZERO
  candidate graph. This helps navigate partial evidence but does not deliver a
  reconciled project inventory, a pit count, or Tender acceptance.

## 2026-09-11 — source-scoped structural dossiers

- `43244db` exposes every existing facility, local-area, excavation, structure, and
  zone observation as an evidence-linked **candidate dossier** in the existing project
  model UI/API. Relationships are included only on exact source-scoped endpoint
  resolution; same-name items across documents remain separate and unresolved.
- The API/frontend release is live and readiness remains healthy at migration `0047`.
  This improves inspection of partial evidence; it does not establish a reconciled
  object model, comprehensive coverage, or Tender acceptance.

## 2026-09-11 — deployed worker progress transition

- The document worker now runs pinned release `22142e2` after a controlled safe-boundary
  transition. The local Qwen runtime remained in place.
- Real job `01a08f4e-3b5b-7851-9f3d-fcaf3e84c096` persisted the first two accepted
  `engineering.semantic_batch_progress` events (`1/497`, `2/497`). This is operational
  evidence for the worker path, whereas prior validation was disposable PostgreSQL only.
- The live static frontend artifact is `22142e2`; it presents only this specific event
  category as Russian semantic-batch progress. API code remains `f533d5c`, compatible at
  database migration `0047`.

## 2026-09-11 — current semantic job progress

- `c98db6a` appends an idempotently deduplicated, content-free event after each
  completed base semantic batch, locking only the durable job row while writing the
  event. It does not retain document text or alter candidate persistence.
- `4406e23` adds the latest event to both effective and history job responses and shows
  Russian current/total progress in the jobs table. Its integration regression covers a
  running retry beyond 205 historical rows.
- `f533d5c` makes the frontend tolerate a prior API response while services transition.
  The API/frontend half is live. The worker half remains deliberately deferred until
  active job `01a08f4e-3b54-7dd6-8114-39b798d51740` becomes terminal; hence a real worker
  event is not yet claimed.

## 2026-09-11 — profile-scoped candidate release activated

- `b0b80a8`, `3c42300`, and `c29e8e3` form the profile-scoped persistence change;
  `e28da91` is the exact deployed release record. It adds migration
  `0047_profile_scoped_engineering_candidates` and makes a completed semantic-stage
  receipt plus exact semantic and persistence profile provenance necessary before
  scheduling is suppressed. This prevents generic historical candidates from being
  silently mixed with later Qwen profile results.
- The controlled database backup was created and checked before the additive schema
  transition. API, document worker, and assistant worker now import the exact e28da91
  release and the API readiness contract expects 0047.
- Calling the existing project-understanding command scheduled 22 source-scoped,
  profile-aware semantic successors and one reconciliation job. Existing compatible
  accepted batch manifests are reused; no OCR was requested. POS’s successor has
  explicit `engineering_semantic_profile` and `candidate_persistence_profile` v15
  provenance.

Known limitation: processing and candidate persistence are active; cross-document
facility reconciliation, NTD checks, Tender findings, source-link browser acceptance,
and consultant acceptance remain open.

## Pending controlled release — 2026-09-12

## API/frontend activation — 2026-09-12

- API and frontend release `6194eb31fd82630b136dd0f404252b532a8cae44` is active at
  database migration `0048_incremental_reconciliation_claim_priority`. A direct
  loopback readiness call established PostgreSQL reachability and exact migration
  compatibility. The document and assistant workers were intentionally not restarted.
- The release activates already-qualified accepted-batch candidate publication. It
  makes exact-locator fields, structures, relationships, and works from accepted v15
  receipts visible while a source remains in progress; it does not create quantities
  or materials before cross-batch work identity can be resolved.
- The rollout used a preserved launchd plist and isolated process qualification. The
  ordinary launchd registration path failed and was recovered; forced reload activated
  the same qualified API configuration. This operational incident did not mutate OZERO
  source versions, durable jobs, or accepted receipts.

Known limitation: API partial publication is live, but the document worker remains on
the prior pinned release until its active Qwen extraction reaches a terminal receipt.
Therefore full-package coverage, facility reconciliation, Tender findings, and
consultant acceptance remain open.

- `53cafdf` makes accepted v15 engineering-batch receipts materialize their exact,
  source-backed fields, structures, relationships, and work observations immediately.
  This is explicitly a partial candidate view: cross-batch quantities and materials
  remain in the receipt until complete-source work identity reconciliation can safely
  attach them.
- The API profile selection includes accepted batch receipts, so a partial source is
  no longer hidden solely because its terminal source stage is still running. Exact
  receipt digests, source locators, candidate status, and RLS scope remain unchanged.
- `2b48e05` records a dense policy only for an otherwise unstarted source. Existing
  v15 accepted manifests stay byte-identical and resume without duplicate model calls.

The pinned candidate release is `436cba06a24d88345af6dc9ca77f6f67b09a6803`; it has
not been deployed while document worker `5939` owns the active Qwen request. Focused
format/check, strict mypy, 53 document-understanding tests, and a scoped read through
the staged application repository passed. None of these checks establishes complete
OZERO semantic coverage, a reconciled facility inventory, Tender acceptance, browser
source navigation, or a grounded consultant answer.

## 2026-09-11 — full structural-candidate inspection

- `de98eaf` replaces the silent first-200 truncation in the Russian project-model
  structure panel with local search plus explicit incremental display for structures
  and relationship observations. The built frontend artifact is served by the
  compatible e28 API release. Frontend Prettier, ESLint, TypeScript, and production
  build passed. The change is presentation-only: it neither updates candidates nor
  asserts a reconciled entity inventory.

## 2026-09-11 checkpoint

- `4de2561` derives project-definition, work-package, requirement-matrix, and
  reconciliation state from actual evaluated gaps. It removes the unconditional
  `WORK_TYPE_CATALOG_UNAVAILABLE` placeholder without forcing a completed state.
- `74f9ce4` makes the Russian project-model UI surface source-backed candidate
  counts for fields, structures, works, quantities, and materials while the model
  remains partial.
- `18c6893` reuses accepted bounded child manifests after a failed parent batch;
  dependent stages no longer repeat that parent Qwen request when exact validated
  child evidence already exists.

The initial deployed release set was `18c6893fdbee5186b351bdddaab2920c8f7eda3d` for
API and document worker. It was compatible with migration `0045_bounded_dep_recovery`;
no migration was required for these changes.

- `a9a693a` prevents metadata-only workspace tools from satisfying a question that
  requires project-document content (for example, an exhaustive pit inventory).
- `8e0c2f5` presents structural candidates as Russian-labelled, source-linked cards
  instead of raw schema-shaped JSON in the project model UI.

The live release set is now API `8e0c2f5`, document worker `18c6893`, and assistant
worker `a9a693a`, all compatible with migration `0045_bounded_dep_recovery`.

Known limitation: this release provides durable, source-backed partial candidates.
It does not yet provide complete multi-document facility reconciliation, a verified
pit total, complete Tender findings, project-specific normative checks, or accepted
consultant/browser workflows.

## Pending controlled release

- `c460131` adds the initial relationship-candidate ledger. The final pending profile is v15. Qwen may
  emit an exact-locator relation (`contains`, `located_in`, `serves`, `connects_to`, or
  `depends_on`) between named observations. Persistence deliberately retains raw,
  evidence-bound endpoints and does not turn same-name matches into canonical links.
  The project-model UI/API displays them as source-linked candidates. Migration
  `0046_structure_relationship_candidates` is required before this release.
- `e4b2083` corrects the semantic-coverage query so the project view includes active
  source versions with no accepted batch as `not_started`. It was exercised through a
  scoped OZERO application-repository read: 22 documents, 1 complete, 2 partial, and
  19 not started. The previous surface only listed already accepted sources and could
  understate incomplete package coverage.
- `742357b` prevents profile v14 from reusing earlier engineering manifests: those
  manifests never requested relationship observations and therefore cannot establish a
  valid empty v14 relation set. Existing candidates remain preserved; relationship
  coverage needs a separately versioned local-Qwen pass.
- `a36ee21` adds source-scoped endpoint resolution to the relationship API response.
  It resolves an endpoint only where the same evidence locator has exactly one matching
  structure candidate; cross-document or same-name ambiguity remains explicit.

## 2026-09-11: semantic role-gate and status corrections

- `1f1575a` makes semantic coverage select the latest activity profile, including a
  profile with only failed attempts. The UI calls failed entries historical attempts;
  accepted coverage and immutable failed receipts are no longer conflated.
- `ce9cd3b` permits project/work semantic extraction to use evidence-bearing native
  elements when deterministic page classification is unavailable. Missing native
  elements still fail with `structured_extraction_evidence_unavailable`; the change
  does not create a fallback extractor. It also preserves Qwen
  `structure_relationships` in the persisted project bundle. A focused regression
  covers a role-less source whose Qwen structure and facility-to-pit relationship
  candidates persist with exact evidence.

`ce9cd3b` is prepared as a complete API/document-worker/assistant-worker release
with additive migration `0046_structure_relationship_candidates`. It is not live:
the current public application database role cannot make the required full recovery
backup. No services were restarted and no schema change was attempted after that
backup gate failed.
