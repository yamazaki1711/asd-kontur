# Contract Pack v1.4 — acquisition, corpus and Audit

This additive Draft 2020-12 release defines the shared object-independent
collection/preflight/processing/reconciliation records and the WP-14 Audit
outputs. It does not alter persisted v0.1–v1.3 semantics.

The contract distinguishes physical objects, page-addressable processing,
validated logical-document boundaries and an evidence-rated `CorpusSnapshot`.
Audit then emits three separately scoped and fingerprinted deltas: document,
causal readiness, and package/signing/handover. No record asserts corpus-wide
ОКС completeness, model authority, restoration, or `ProductReady`.
