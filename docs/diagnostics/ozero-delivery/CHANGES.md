# OZERO Tender delivery changes

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
