# OZERO overnight Tender mission — factual outcome

## Scope and versions

- **Window:** `2026-09-10T17:12:09+12:00` to the preserved deadline
  `2026-09-11T08:12:09+12:00`.  It expired before this report; no new mission window was started.
- **Recorded active work:** Qwen OCR and recovery activity is recorded from approximately 17:12 to 17:55
  +12 in the durable mission journal.  The supplied logs do not provide a complete per-minute timeline;
  intervals outside those records are **unknown**.
- **Local/pushed HEAD:** `9c98c2fd995a19b6cf65e2daedcf19028d3eaf8e`.
- **Running processes observed after the window:** API `3ac8a33`, assistant worker `b67bcd6`, document
  worker `9c98c2f`, Qwen server source `e7dfba4`.  They are mixed, compatible development releases;
  the API/UI does not contain the later project-view changes.  No deployment was performed for this report.
- **Unrelated local changes preserved:** `frontend/e2e/product-spine-live.spec.ts`,
  `tools/run_product_spine_e2e_server.py`, `frontend/pnpm-lock.yaml`, `.orig` evidence files and the
  listed untracked retrieval/assistant files in `git status`.  They are not part of this outcome.

## Direct result

The mission did **not** deliver usable OZERO Tender.  The scoped database contains 22 active source
versions and 2,529 pages, but zero persisted project fields, structure nodes, work types, quantities or
materials.  Thus `dependency_terminal_failure` in the model is a real missing materialization, not a
"zero findings" result.

The only source whose Qwen-derived processing completed is IОС1.  Its `57/60` pages were routed to and
persisted by local Qwen vision.  It also has one persisted Qwen role candidate.  This is a **single
document/page-routing denominator**, not the uploaded package and not engineering analysis.

## Effective corpus state at report time

All documents remain effective-blocked for Tender materialization.  For 21 documents there is no Qwen
OCR output or Qwen semantic candidate.  For IОС1, downstream project-definition extraction succeeded
but persisted no fields or structure candidates; its deterministic work extraction therefore also has no
candidate result.  `fields/structures/works/quantities/materials` below are all `0`.

| Source document | Source version | Pages | Qwen OCR pages | Qwen semantic roles | First unresolved dependency |
|---|---|---:|---:|---:|---|
| ТБЭ | `01a088ac-8013-7e32-acef-3f68c3276955` | 53 | 0 | 0 | OCR/recovery not completed |
| СМ1 ПЗ | `01a088ac-7ff8-728b-981c-22151bce4cb2` | 10 | 0 | 0 | OCR/recovery not completed |
| СМ1 ССР | `01a088ac-7f59-7a03-b342-fd7187e8d472` | 5 | 0 | 0 | semantic/project extraction not run |
| СМ2 | `01a088ac-7fdb-7b12-be33-e3a325af8edf` | 123 | 0 | 0 | semantic/project extraction not run |
| СМ3 | `01a088ac-7f97-761a-b857-f5d3b4c5be8b` | 121 | 0 | 0 | OCR/recovery not completed |
| СМ4 | `01a088ac-7f77-76da-84a9-5621e128e3d4` | 52 | 0 | 0 | semantic/project extraction not run |
| СМ5 ПИР | `01a088ac-7f16-73ef-9d2c-3957b2393f66` | 22 | 0 | 0 | OCR/recovery not completed |
| СМ5 | `01a088ac-7fbd-71be-9b35-8fd1d1b4821b` | 50 | 0 | 0 | semantic/project extraction not run |
| ПРЗ | `01a088ac-80e6-7166-a78f-b4f8b5f147b1` | 38 | 0 | 0 | OCR/recovery not completed |
| СОЭ | `01a088ac-80c8-74f4-b29a-21fe6985b976` | 48 | 0 | 0 | semantic/project extraction not run |
| ИРД | `01a088ac-80a5-778d-8215-a09eb037b53d` | 14 | 0 | 0 | semantic/project extraction not run |
| ПЗУ | `01a088ac-8125-7031-8659-a57bd97ff1c6` | 56 | 0 | 0 | semantic/project extraction not run |
| КР1 | `01a088ac-8084-7c59-8b1a-c9bda7ad8208` | 29 | 0 | 0 | semantic/project extraction not run |
| КР2 | `01a088ac-8065-7088-9fe9-298e3848e7ae` | 21 | 0 | 0 | semantic/project extraction not run |
| ИОС1 | `01a088ac-8181-727a-987f-5a5519421c77` | 60 | **57** | **1** | no engineering candidates persisted |
| ИОС3 | `01a088ac-8105-70a5-a875-265eed420c3a` | 114 | 0 | 0 | OCR/recovery not completed |
| ТХ | `01a088ac-81a0-7840-8e74-1aecc704d1fc` | 412 | 0 | 0 | OCR/recovery not completed |
| ПОС | `01a088ac-81c2-7033-8f75-8160ffeb2cb2` | 165 | 0 | 0 | OCR/recovery not completed |
| ООС | `01a088ac-8143-7e00-a6ef-ca9a52ef84be` | 1,002 | 0 | 0 | OCR/recovery not completed |
| ПБ | `01a088ac-8163-72d9-992e-4eabbb3576fc` | 28 | 0 | 0 | OCR/recovery not completed |
| КР1.РР | `01a088ac-8042-723d-9c64-02f1629c50af` | 44 | 0 | 0 | semantic/project extraction not run |
| КР2.РР | `01a088ac-802d-71b2-ad73-cd30b625fead` | 62 | 0 | 0 | semantic/project extraction not run |

## What Qwen actually did

Historical Qwen calls cannot be promoted to package processing.  The recoverable IОС1 OCR retry produced
57 complete `qwen3.8-27b-local-vision` page outputs.  The first three semantic-classification replacements
failed with `qwen_semantic_response_invalid_json`; after commits `e7dfba4` (disable thinking) and
`9c98c2f` (six pages / 4,800 characters), the fourth replacement persisted one exact-locator role
candidate.  No Qwen structure candidate, project field, work, quantity or material was persisted.

## Code findings confirmed at deployed/local heads

The independent-review findings remain true at `9c98c2f`:

1. `qwen_semantic._sample_pages` takes only the first six pages, maximum 800 characters per page
   (`src/asd_kontur/document_understanding/qwen_semantic.py:28,143-160`).  This is classification/structure
   discovery, not full-document semantic extraction.
2. `IndustrialDocumentUnderstandingPipeline._work_values` calls deterministic
   `extract_structured_candidates`; it does not invoke `QwenDocumentSemanticAdapter`
   (`pipeline.py:287-304`).
3. `_project_fields` invokes deterministic `extract_structured_candidates`; the Qwen call is limited to
   `extract_structures` (`pipeline.py:268-285`).
4. `_aggregation` returns role-decision counts/fingerprint and creates no engineering aggregate
   (`pipeline.py:253-266`).

No local uncommitted fix exists for these limitations.  The visible project-model API is still the older
`3ac8a33` process, so even candidate-display commits are not user-visible.

## Trace of useful-information loss

IОС1 source `01a088ac-8181-727a-987f-5a5519421c77` is the only complete live trace:

`source bytes → native pages → 57 Qwen vision outputs → one Qwen role candidate → DOCUMENT_AGGREGATION → PROJECT_DEFINITION_EXTRACTION`

Validation accepted the OCR outputs and the role candidate.  The next deterministic project-field/table
extractors produced zero candidates; aggregation only recorded role metadata.  As a result no source-backed
engineering content reached reconciliation, the API, UI or consultant.  This establishes the loss point:
the pipeline has no full-document semantic extraction/aggregation contract, rather than evidence that the
document contains no project facts.

## Root job state

Workspace durable jobs at report time: 205 `succeeded`, 41 `failed`, 237 `reconciliation_required`, no
queued/running jobs.  The historical IОС1 OCR root and replacement lineage ends in successful OCR; its
classification lineage has three preserved JSON failures followed by the successful fourth replacement.
The inherited root project jobs remain `dependency_terminal_failure` because manual replacements do not
reconnect the original DAG automatically.  The current model block is therefore not cleared by a leaf
success.

## Tender capabilities still missing

Not merely job-blocked: full-document semantic evidence extraction; cross-document engineering
reconciliation; project structure/works/quantities/materials materialization; project evidence retrieval;
Tender discrepancy/risk/scope outputs; and grounded consultant answers.  Thus excavation-pit inventory,
sheet-pile scope and Tender analysis are not established.

## Smallest complete engineering change

Introduce one versioned **full-document semantic extraction** stage after validated native/Qwen OCR:
paginate every eligible page/region into bounded Qwen requests, validate each output against exact source
locators, persist typed project/entity/work/quantity/material candidates, and aggregate all active source
versions through a versioned reconciliation manifest.  Its completion must enqueue/reconcile dependent
packages, matrix, evidence index and project-understanding view.  The Jobs API must expose effective
lineage and cursor pagination separately from historical attempts.  Only then can the existing UI and
consultant consume evidence-backed model data.
