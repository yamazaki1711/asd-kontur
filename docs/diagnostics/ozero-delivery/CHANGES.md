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

The deployed release set is `18c6893fdbee5186b351bdddaab2920c8f7eda3d` for API and
document worker. It is compatible with migration `0045_bounded_dep_recovery`; no
migration was required for these changes.

Known limitation: this release provides durable, source-backed partial candidates.
It does not yet provide complete multi-document facility reconciliation, a verified
pit total, complete Tender findings, project-specific normative checks, or accepted
consultant/browser workflows.
