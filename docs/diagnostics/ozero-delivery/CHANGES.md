# OZERO Tender delivery changes

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

- `c460131` adds profile v14 and an additive relationship-candidate ledger. Qwen may
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
