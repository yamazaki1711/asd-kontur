# ASD-KONTUR agent instructions

Before work, read [Product Goal](docs/product/PRODUCT_GOAL_AND_CAPABILITY_MAP_v1.md),
[Capability Registry](contracts/v2.0/fixtures/valid/product-capability-registry.json)
and the current [Implementation Plan](docs/architecture/IMPLEMENTATION_PLAN_v1.md).

- Build the whole object-independent product: four modes and three permanent
  results. The Qwen domain/knowledge harness is necessary, not sufficient.
- UI, Application, Industrial Intake, Output, Field and Operations are
  first-class product planes. Foundation/tests are not capability readiness.
- Do not propose a real OKS before an accepted `TrialReadinessDecision`.
- Use native/deterministic processing before AI. Qwen3.8 receives bounded
  context through Knowledge Gateway; numeric-critical drawings use BF16.
- Codex may implement and operate application code, tests, migrations and
  recovery.  Bulk model-based document OCR/VLM and semantic extraction must
  run through the approved local Qwen3.8 pipeline with durable provenance;
  do not substitute Apple Vision, Tesseract, cloud models or Codex inference.
  Keep deterministic hashing, native extraction, rendering, parsing,
  validation and indexing outside model inference.
- Preserve hard workspace isolation, RLS/default deny, evidence, provenance,
  immutable history and Candidate-before-Fact authority.
- For NTD discovery start with Minstroy, then `docs.cntd.ru`, then
  `meganorm.ru`. The latter two are discovery/reference sources only: canonical
  NTD Authority still requires an exact official SourceVersion.
- Work on one active delivery slice. Every PASS states an exact denominator and
  evidence. `ProductReady=false` until the formal terminal condition.
- Treat any real workspace, including OZERO, as a validation corpus rather
  than the product boundary: implement reusable four-mode capabilities against
  controlled inputs first, then state precisely what a selected real-document
  check proves. A blocked corpus job never blocks independently testable
  product work.
- Use mac_asd through **selective engineering reuse**: preserve proven best
  ideas, algorithms, assets and tests; improve and integrate them into the
  modern architecture. Mechanical copy-paste or automatic adoption of its
  stack is forbidden. Apply the
  [Legacy Component Decision Gate](docs/architecture/LEGACY_COMPONENT_DECISION_MATRIX_v1.md)
  before reuse; do not repeat a broad audit without a specific evidence gap.
