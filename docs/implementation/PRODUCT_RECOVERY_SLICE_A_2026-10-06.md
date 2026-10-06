# Product recovery: project consultation, slice A

This record describes the inspected running boundary, not four-mode readiness. It contains no project source text or expected project answer.

## Executable baseline

- Inspected source and assistant release: `45a0bad1719a5836fb13663de48a50cd5c7edbc5`, on `codex/product-continuation-20260921`.
- Running API, document worker and orchestrator remained pinned to `9e15d8ab1bd9e7c225eeabc24577cc890e8dd9b0` during this slice. The assistant worker was switched from `e23f06e4bc491280a0a977b5617aa7e924f7885b` to `45a0bad1719a5836fb13663de48a50cd5c7edbc5` without restarting those services or Qwen/NTD. PostgreSQL migration head: `0127_task_scoped_quantity_profile`.
- The two failed assistant turns were retrieved from durable turn, tool and quality receipts. Both retrieved workspace sources and were then rejected by deterministic answer checks. One draft was typed `insufficient_data` without a next question; the other was typed `clarification`, cited sources and omitted a question. The worker published the same generic insufficient-data fallback for both.
- The workspace search returned isolated native-layout cells. A read-only query established that one retrieved pipe-work description had separate adjacent cells for unit and quantity. The old tool result did not present those cells together. This is a retrieval-context defect, not proof that every requested attribute is already extracted or that the documents agree.

## Correction map

| Owner requirement | Running implementation / observed boundary | Reusable correction / acceptance |
| --- | --- | --- |
| Tender: answer entity, operation and property questions | Structure inventory and fragment search exist; search exposed isolated table cells and answer validation collapsed distinct failures. | Provide bounded, source-linked row context to Qwen; preserve supported partial clarification. Real authenticated turn and changed-project tests still required. |
| Support | Same workspace model and mode API exist; live professional output not inspected here. | Use general entity/property retrieval in this mode only after the Tender path is accepted; mode acceptance remains open. |
| Audit | Same shared memory and mode API exist; live professional output not inspected here. | Require a supplied-ID versus required-ID user path; acceptance remains open. |
| Restoration | Product contract says dedicated restoration remains unimplemented. | Recover source-supported editable generation with explicit missing field facts; acceptance remains open. |
| Shared project memory | RLS-scoped project understanding and source locators exist. | Do not require a pit/facility ancestor for a pipe fact; confirm on a controlled second workspace. |
| NTD access | Separate platform knowledge and worker exist; no NTD claim is needed for a PD pipe dimension. | Preserve NTD and do not let unrelated applicability checks veto a source-supported project attribute. |
| Generation | Contract/report generation components exist; four-mode editability is not accepted. | Evaluate each mode's concrete user document separately. |
| Consultant | Qwen planner/synthesis and deterministic validation run in supervised assistant worker. | Context change is deployed; real answer, citation and source conflict checks remain to be run. |
| Lifecycle | The inspected reset implementation creates an internal archive outside its deletion coordinator; current deployed endpoint and stores are not yet inventoried. | Slice B must separate optional export from complete removal; no current project was deleted. |
| Scheduling and restart | API, document worker, orchestrator, assistant worker and Qwen are launchd-supervised. | Assistant restart succeeded. End-to-end autonomous professional-output convergence was not re-proven in this slice. |

## Change and bounded evidence

The workspace search now returns a small envelope from the same source version and page: the same table row when row coordinates exist, otherwise nearby reading-order elements. Every cell keeps its own locator and row/column coordinates. Retrieval does not infer which numeric cell is a diameter or length; Qwen must do that interpretation. A source-grounded partial answer may ask for clarification without being rejected merely because it cites a source.

The assistant prompt projection now serializes primary search matches before optional row context. It removes a duplicate source-fragment index and bounds the context as valid JSON instead of truncating the tool result mid-record. A read-only check on the real workspace showed all ten primary matches, including a design-document match, and the relevant adjacent table cells in the bounded prompt. This is context delivery, not a project conclusion.

Generic planner/synthesis instructions now direct Qwen to distinguish engineering entity, location, existing/proposed state, work operation and table row/column meaning. They do not contain any project-specific value or expected answer.

Focused tests passed, and a read-only live query showed the relevant table row and source identifiers enter the assistant prompt. A different workspace scope returned zero rows. An authenticated external-browser qualification test was added, parameterized by workspace identity and login environment; it has no embedded expected pipe value. This is **not** real user acceptance: the in-app browser was unavailable and no approved API/E2E login credential was available in this engineering session. The live question was not submitted. No project fact was manually inserted or reprocessed.

## Remaining acceptance for slice A

1. Ask the original question through an authenticated application session; inspect Qwen tool/quality receipts and the published answer.
2. Verify each reported existing/replacement pipe attribute against cited document/page and check contradictory/absent values.
3. Run reusable controlled cases with changed values and names, two same-named pipes, another entity, conflicting sources and cross-workspace denial.
4. If structured extraction still lacks a required attribute, add a bounded targeted Qwen task and durable result rather than encoding a project answer.

`ProductReady=false`; Tender, Support, Audit, Restoration and complete lifecycle acceptance remain open.
