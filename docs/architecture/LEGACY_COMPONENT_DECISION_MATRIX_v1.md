# Legacy Component Decision Matrix v1

- Status: Accepted gate baseline
- Legacy evidence point: `/Users/oleg/mac_asd`, branch
  `feature/core-under-version-control`, commit
  `84099c3bc46c74bff13067c0b9e680e737baa7e0`
- Scope: targeted components relevant to Product Application Rebaseline
- Method: existing ASD-KONTUR legacy reports plus bounded source/test inspection;
  not a new broad audit

## Gate

Use **selective engineering reuse**: preserve demonstrably best semantics,
algorithms, assets and tests from mac_asd, improve them and integrate them into
the modern architecture. Mechanical copy-paste and declaring the legacy stack
the target without a new evidence-backed decision are prohibited.

Before code moves, all of the following must be true: the capability is in the
Product Registry; behavior has characterization evidence; no demo/fallback or
in-memory authority exists; workspace/provenance/Knowledge Gateway boundaries
hold; strict typing and current dependency/license/security review pass;
performance matches its scale profile; and hardened integration tests pass.
Failure of any critical condition changes the decision to
`REIMPLEMENT_FROM_SEMANTICS` or `USE_AS_REFERENCE_ONLY`.

## Decisions

| Legacy component/path | Capability and proven useful behavior | Tests/evidence | Defects, debt and risk | Decision and exact reason | Modernization target / preserved regression assets |
|---|---|---|---|---|---|
| `src/core/segmentation/container_splitter.py` | container/page segmentation concepts and bounded parts | source digest `7f0accbd…`; [legacy pdfpipeline report](../reports/LEGACY_PDFPIPELINE_AUDIT_EXPERIENCE_v0.1.md) records sliding windows, partial failures and duplicate attempts | legacy identity/persistence/provider assumptions; scale and typing not accepted | `REIMPLEMENT_FROM_SEMANTICS`: behavior is valuable but must use CorpusSnapshot, immutable shards and reconciliation | preserve split/overlap/no-empty-success cases as anonymized characterization fixtures |
| legacy pdfpipeline geometry and manifests described in `LEGACY_PDFPIPELINE_AUDIT_EXPERIENCE_v0.1.md` | page/region mapping, source/render digests, resume lessons | fully traced report and external evidence ledger | object-specific implementation and inaccessible volumes; not a reusable library | `USE_AS_REFERENCE_ONLY` | exact one-based locators, crop/rotation transforms and retry receipts become new intake/viewer tests |
| `src/core/hybrid_classifier.py`, `src/core/vlm_classifier.py` | native/deterministic-first classification fallback semantics | `tests/test_document_classifier.py`, `tests/test_multi_classifier.py`; source digest `b4b15886…` | demo/fallback matches; provider and authority mixed; result may be treated too strongly | `REIMPLEMENT_FROM_SEMANTICS` | classifier Candidate contract behind corpus pipeline; same fixture cases, strict provenance and terminal outcomes |
| `src/core/evidence_graph.py` | useful relation vocabulary and evidence-navigation expectations | `tests/test_evidence_graph.py`; source digest `9b6ef070…` | confidence helpers and mutable graph can imply authority; no canonical RLS/workspace boundary | `USE_AS_REFERENCE_ONLY` | map reviewed relation semantics to canonical SQL identities and rebuildable typed-graph projection; graph never SoR |
| `src/core/hitl_system.py` | prioritized operator questions, missing-evidence workflow | source digest `12e4a1e…`; UI templates `src/web/templates/hitl*.html` | in-memory sessions, hard-coded potentially fabricated normative statements, UUID/time state | `REIMPLEMENT_FROM_SEMANTICS` | durable ActionRequest/HITL queue with evidence, authority, workspace, lifecycle and answer receipts; preserve question journeys only |
| `src/core/lessons_service.py`, `src/db/seed_lessons.py` | Domain Traps/Lessons Learned concepts | legacy report confirms lessons such as attempt-before-side-effect and no empty success | seed content lacks Promotion Gate provenance; fallback paths; possible global mutable memory | `USE_AS_REFERENCE_ONLY` | ingest candidates only through Domain Trap/Lesson Promotion Gate; preserve proven lessons as review corpus |
| `library/templates/**`, `data/knowledge/templates/**` | forms, template structures and document-generation test cases | [Legacy ID Generator Asset Inventory](../reports/LEGACY_ID_GENERATOR_ASSET_INVENTORY_v0.1.md), `tests/test_*template*` | authority/edition/license, duplicate/generated assets and completeness are mixed | `REUSE_AFTER_HARDENING` per exact asset, never directory-wide | content-addressed TemplateAssetVersion with official authority, license, malware/content scan and render/print golden tests |
| `src/core/services/is_generator/{dxf_parser,dxf_builder,dxf_annotator,pdf_overlay_builder,spatial_calc_adapter}.py` | parsing/building/overlay algorithms and geometry workflows | digests recorded above; `tests/test_is_generator*.py`, `tests/test_parametric_templates.py` | numeric/CRS/units authority and CAD fidelity need qualification; dependencies and lineage not integrated | `REUSE_AFTER_HARDENING` for isolated pure algorithms that pass characterization; otherwise reimplement | typed GeometryEvidence, CRS/unit/precision lineage, deterministic DXF adapter, render/round-trip corpus; preserve control-example scenarios, not project files |
| `src/core/services/is_generator/is_generator.py`, `batch_generator.py` | generation stages, completeness gate and batch scenarios | `tests/test_is_generator*.py`, `tests/test_gap5_is_generator_integration.py` | legacy service boundary and state do not satisfy Candidate/finalization/Rule/Gateway contracts | `REIMPLEMENT_FROM_SEMANTICS` | GeneratedDocumentCandidate workflow using current domain harness; preserve state-transition assertions |
| `src/mobile/sync_engine.py`, `mobile/android/**` | offline work plan, confirmations, conflict and queue concepts | digest `b0e2944b…`; Android DAO/sync/security/ViewModel tests | SQLite schema in module, PIN identity, mutable last-write notions, old API and prototype UX; security/scale not accepted | `USE_AS_REFERENCE_ONLY`; target `REIMPLEMENT_FROM_SEMANTICS` | Preserve planned-work/confirmation/conflict scenarios as regression evidence. Select no client, identity, MDM or sync technology before the separate FIELD-ANDROID architecture/security ADR and threat model. |
| `src/web/app.py`, `src/web/templates/**` | dashboard, projects, documents, reports, four mode journeys and evidence/HITL surfaces | source digest `36e22836…`; historical working UI is owner-accepted product evidence | in-memory `app_state`, demo/fallback data, untyped routes, Jinja/HTMX constraints for complex workbench | `REIMPLEMENT_FROM_SEMANTICS` | React/TypeScript workbench over typed OpenAPI; preserve screen/journey acceptance scenarios and wording where professionally valid |
| `scripts/audit_pdf_*.py`, `scripts/audit_pipeline.py`, legacy batch ingestion | batch admission, health checks, operator progress and audit sequencing | `docs/adr/ADR-001-audit-pipeline-sequence.md`, audit scripts and reports | script-local state, no durable jobs/RLS/reconciliation; project-specific outputs | `USE_AS_REFERENCE_ONLY` | Product Application durable job workflow; preserve failure sequences, page-health and progress scenarios |
| mode helpers/templates: `src/agents/{tender_helpers,construction_helpers,restoration_helpers}.py`, `src/web/templates/modes/**` | mode-specific user journeys and professional result vocabulary | tender/construction tests and four legacy screens | tied to agent architecture and weak legacy authority; Restoration is not complete | `USE_AS_REFERENCE_ONLY` | four views over one ProjectDefinition/WorkRequirementMatrix; preserve scenario fixtures, reject eight-agent topology |
| `tests/**` and anonymizable qualification cases | regression corpus for classifiers, templates, evidence, modes and offline | tracked tests at the evidence commit | many tests assert legacy internals/demo behavior or embed project content | `REUSE_AFTER_HARDENING` selectively | copy only anonymized, licensed characterization semantics with trace to legacy path/commit; rewrite expectations to current authority/isolation contracts |

## Rejected categories

- `REUSE_AS_IS`: no inspected component met every gate.
- in-memory `app_state`, demo/fallback domain data, confidence-as-authority,
  direct browser/agent database access and eight-agent topology: `REJECT`.
- third-party dashboard/template boilerplates: `REJECT` unless license,
  dependency, security, accessibility and document/CAD workflow reviews pass.

Every future reuse PR must cite a matrix row, exact legacy commit/path/digest,
characterization tests, license evidence and a new integration decision.
