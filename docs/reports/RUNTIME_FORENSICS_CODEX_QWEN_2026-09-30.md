# ASD-KONTUR runtime forensics: Codex and local Qwen

Observed: 2026-09-30 10:13–10:19 +12 (Asia/Kamchatka)  
Repository: `/Users/oleg/.asd-kontur/worktrees/product-continuation-20260921`  
Branch: `codex/product-continuation-20260921`  
Local and remote feature HEAD: `c7661acd7233d4f98ce1f8706644aec7f62974dc`  
Deployed API/frontend/assistant/document-worker release: `fea13f55255d2df3f92ae8ec67e31d783b70d5ee`  
Supervised Qwen service release: `145c81939bf2ece15e22099fa52637da3c890a2f`  
Supervised NTD worker release: `7277c637011cf5426b9f81495bd0d20a7f245008`  
Database migration: `0075_workspace_job_fence_predicate`

Labels used below:

- **VERIFIED** — directly observed in the database, process supervisor, source, or Codex transcript.
- **INFERENCE** — conclusion from multiple verified observations.
- **UNKNOWN** — the runtime does not persist enough information to establish the claim.

No code, database row, queue, or service was changed for this audit. The only new file is this report. Two pre-existing, unrelated worktree modifications in `src/asd_kontur/tender/project_engineering.py` and `tests/unit/test_tender_project_engineering.py` were preserved unchanged.

## A. EXECUTIVE CONCLUSION

### Did Qwen actually analyze project documentation?

**Yes — VERIFIED.** Local Qwen3.8-27B produced persisted output for this workspace:

- 36 completed page OCR/VLM records using `qwen3.8-27b-local-vision` / `qwen-vision-ocr-v3`;
- 19 completed document page-classification jobs using `document-page-role-v0.1`, including 21 persisted candidates marked `qwen-document-semantic-v1`;
- 583 accepted and 100 failed bounded engineering-extraction batches using `qwen-engineering-extraction-v15` across 20 source versions;
- 102 completed project-work reconciliation jobs using `qwen-project-work-reconciliation-v8`; their manifests record exactly 324 inference calls.

The exact total HTTP request count is **UNKNOWN** because the Qwen server does not keep a request ledger. There are at least 962 successful result-producing model calls or call-equivalents (36 OCR + 19 classifications + 583 accepted extraction batches + 324 explicitly counted reconciliation calls). This is a lower bound, not an exact request total: repairs, split retries, failed requests, and accepted-result reuse are not represented by one uniform counter.

### Did Codex manually advance the processing pipeline?

**Yes — VERIFIED.** Codex manually:

- created 20 derived retry jobs (19 page-classification retries and one OCR retry);
- invoked `start_project_understanding` repeatedly, creating the three command-level project-understanding jobs and a 20-job semantic-recovery set;
- invoked `start_project_work_reconciliation` repeatedly, including the initial four reconciliation jobs and later bounded batches;
- deployed/restarted workers and, once, deliberately stopped and restarted the document worker around a bounded job;
- inspected project-derived rows and changed generic interpretation/classification code based on observed gaps.

After the first project-work reconciliation jobs existed, the deployed worker did automatically refill that one job family. This does not make the whole project pipeline autonomous.

### Is Codex currently required for project processing to continue?

**Yes, for the current stalled state — VERIFIED.** Intake automatically created the original durable DAG, and the worker automatically claims runnable jobs. However, the runtime has no general project planner/reconciler that repairs failed semantic roots and reconstructs all missing successors. At observation time:

- 120 jobs were queued;
- all 120 were blocked by unsatisfied durable dependencies;
- zero queued jobs were claimable;
- 23 terminal failed jobs had no successful recovery lineage;
- no job had run or completed since 2026-09-30 08:08:51 +12.

Without a manual retry/recovery command or a new autonomous planner, the workspace does not advance.

### Did Codex directly create any engineering conclusions?

**No direct project-fact insertion was found; partial indirect authorship is VERIFIED.** The audit found no Codex SQL insert/update of a project fact, no manually authored Qwen response, and no owner-provided expected discrepancy encoded in production data. Runtime observations originate from native extraction and persisted Qwen output.

However, Codex read selected project-derived content and then authored/deployed deterministic rules that classify document roles, facilities, work families, units, project purpose, and quantity comparisons. Those rules materially shape current engineering outputs. Project-specific values and filenames also appear in qualification tests. Therefore it would be inaccurate to claim that every current conclusion was independently discovered by an untouched production system. The semantic source facts are Qwen/native; part of their interpretation into user-facing conclusions is Codex-authored code informed by this corpus.

## B. CURRENT NEW PROJECT STATE

### Workspace and corpus

| Item | Current fact |
|---|---|
| Workspace | `01a0eba7-70ba-7770-9601-1a713dd359cf` |
| Display name | `Реконструкция Подпорной Стены` |
| Organization | `25b7d36d-7118-5d1e-8cf0-3d03ceed9f88` |
| Lifecycle | ACTIVE |
| Uploaded package | 21 accepted documents plus one rejected upload |
| Registered pages | 218 `workspace.document_pages` rows |
| Document extraction state | 13 `complete`; 8 `partial_with_capability_gap` |
| Full durable-stage completion | 2 documents reached `EVIDENCE_INDEX_UPDATE`; 19 did not |
| Last meaningful project progress | 2026-09-30 08:08:51.163745 +12 |

The UI-level “about half processed” state describes document extraction status, not completion of the full project-analysis DAG. **VERIFIED:** only two documents completed all pre-created downstream stages.

### Current project-understanding materialization

The latest read model available during the audit reports:

- project name: capital repair of retaining walls at Okeanskaya 63/1 and 65/1;
- purpose: missing;
- 13 facility cards;
- no established pit inventory (11 pit-like rows remain in the model and must not be read as 11 established pits);
- 417 work scopes;
- 1,032 source observations: 737 construction-scope observations, 696 classified, 41 unclassified, and 295 excluded as non-work;
- 205 facility-associated observations;
- 482 quantity-review rows, including 374 accepted work quantities and 12 ambiguous quantities;
- 7 quantity comparisons and 400 scope-comparison rows;
- 228 material rows, but no material comparison;
- one issue, one risk, and one customer question.

These are **VERIFIED persisted outputs**, not a statement that their engineering quality has been professionally accepted.

### Durable jobs

| State | Count |
|---|---:|
| succeeded | 393 |
| failed | 42 |
| cancelled | 1 |
| queued | 120 |
| running / leased | 0 |

| Job kind | Succeeded | Failed | Queued | Current interpretation |
|---|---:|---:|---:|---|
| document admission | 21 | 0 | 0 | complete |
| document hash | 21 | 0 | 0 | complete |
| PDF inventory | 21 | 0 | 0 | complete |
| format inventory | 20 | 1 | 0 | XML crypt container unsupported |
| native text extraction | 21 | 0 | 0 | complete |
| native layout extraction | 20 | 0 | 1 | queued job dependency-blocked |
| page health | 20 | 0 | 1 | queued job dependency-blocked |
| OCR routing | 20 | 0 | 1 | queued job dependency-blocked |
| OCR extraction | 20 | 1 | 1 | original failure was recovered, but another queued chain remains blocked |
| page classification | 19 | 21 | 1 | 18 runtime failures were manually retried successfully; three invalid-locator roots remain unrecovered |
| document aggregation | 19 | 0 | 2 | blocked by upstream failures |
| project definition | 24 job successes / 22 complete stage results | 15 | 1 | manual semantic recovery produced results, but did not reconnect every original dependency chain |
| work/quantity/material extraction | 2 | 2 | 17 | two runtime failures have no automatic retry; queued jobs are blocked |
| work-package assembly | 2 | 0 | 19 | blocked |
| requirement matrix | 2 | 0 | 19 | blocked |
| project-understanding reconciliation | 32 job successes / 28 complete stage results | 0 | 19 | useful incremental views exist; original downstream jobs remain blocked |
| structure reconciliation | 5 jobs / 4 complete stage results | 0 | 19 | partial; queued jobs blocked |
| evidence index | 2 | 0 | 19 | blocked |
| project-work reconciliation | 102 | 2 | 0 | bounded work queue drained; two failed inputs are terminal |

### Every incomplete document

“Job exists” below refers to the original automatically created intake DAG. Those queued jobs exist but are not claimable because their `success_required` dependency is unsatisfied.

| Document | Pages | Current stage | Next required stage | Job exists? | Who creates/repairs it today? |
|---|---:|---|---|---|---|
| `ТРЕБОВАНИЯ ... К ЗАЯВКЕ ... .docx` | 0 | recovered project definition and incremental model | work/quantity/material | yes, blocked | intake created it automatically; only manual recovery currently repairs the broken lineage |
| `Описание объекта закупки.docx` | 0 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `Проект сметы контракта.docx` | 0 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `Ведомость объемов работ.pdf` | 5 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `ССРСС на 3 кв. 2026 г.pdf` | 1 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `Обоснование НМЦК.pdf` | 6 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `ЛСР 01-01-01 (на 3 кв.2022 г.).pdf` | 3 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `ЛСР 01-01-01.pdf` | 3 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `ЛСР 01-01-02.pdf` | 8 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `ЛСР 02-01-01.pdf` | 8 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `ЛСР 07-01-01.pdf` | 3 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `ЛСР 07-01-02.pdf` | 3 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `ЛСР 07-01-03.pdf` | 2 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `Проект_контракта.docx` | 0 | recovered project definition and work reconciliation | work/quantity/material | yes, blocked | same |
| `Криптоконтейнер_41-1-1-2-024120-2023.xml` | 0 | format inventory failed: unsupported format | supported crypt-container handling or explicit terminal blocker | downstream jobs exist, all blocked | no automatic supported adapter; repeated retry would not be appropriate |
| `22.467 - ПЗ, ООС, ПБ.pdf` | 19 | project definition and work reconciliation complete | retry work/quantity/material | no active replacement; downstream jobs blocked | currently requires manual retry/recovery |
| `22.467 - ПЗУ, КР, НВ.pdf` | 46 | project definition and extensive work reconciliation | work/quantity/material | yes, blocked | intake created it; original failed project-definition lineage was not reconnected automatically |
| `22.467 - ПОС.pdf` | 39 | work reconciliation exists; page classification failed locator validation | bounded page-classification locator recovery, then aggregation | queued descendants exist, blocked | currently requires a manual/versioned recovery command |
| `22.467-СМ.Изм7.pdf` | 70 | project definition and work reconciliation complete | retry work/quantity/material | no active replacement; downstream jobs blocked | currently requires manual retry/recovery |

The two one-page approval/correspondence PDFs (`30.07.26 - №3908.26 ...` and `70 от 30.07.26г..pdf`) completed through evidence indexing.

## C. QWEN PROJECT-DOCUMENT WORK

### Runtime and profiles

| Item | Verified value |
|---|---|
| Model | Qwen3.8-27B |
| Model path / precision | `Qwen3.8-27B-MLX-8bit` |
| Endpoint | loopback `127.0.0.1:8790` (`/generate`, `/vision`) |
| Supervised process | `ru.asd-kontur.spine.qwen`, PID 36812 |
| Project submitter | supervised document workers, not a Codex HTTP client |
| Document worker identities in attempts | `document-worker:66143`, `document-worker:76656`, `document-worker:77096`, `document-worker:79070` |

Project-document profiles and persisted scope:

| Profile | Persisted result | Time range (+12) |
|---|---|---|
| `qwen-vision-ocr-v3` | 36 completed page OCR/VLM records | 2026-09-29 17:39:59–18:42:22 |
| `document-page-role-v0.1` / `qwen-document-semantic-v1` | 19 completed document-classification jobs; 21 Qwen role candidates | 2026-09-29 18:42:31–18:45:00 |
| `qwen-engineering-extraction-v15` | 583 accepted and 100 failed batches across 20 source versions; 22 complete project-definition stage results | 2026-09-29 18:45:21–2026-09-30 05:21:16 |
| `qwen-project-work-reconciliation-v8` | 102 completed jobs; exactly 324 inference calls in result manifests | 2026-09-29 20:12:11–2026-09-30 08:08:51 |

Persisted job-level average durations are available, but they are not reliable per-call latency because `started_at` can span manual retry/recovery lineage. For example, successful work-reconciliation jobs average 366.6 seconds, while the maximum is 11,679.9 seconds. No uniform per-inference duration or token accounting exists.

### What Qwen did

**VERIFIED:** Qwen supplied page roles, bounded engineering fields, structures, structure relationships, works, quantities, materials, unresolved quantity/material candidates, and semantic work reconciliation/classification. Qwen also supplied OCR/VLM text for 36 routed pages.

**VERIFIED:** deterministic validation rejected malformed locators and invalid output rather than accepting them silently.

**UNKNOWN:** exact prompt tokens, completion tokens, total HTTP calls, and per-call latency. The server suppresses normal HTTP request logging and returns no usage record. `workspace.project_work_reconciliation_results` is the only examined result family with an explicit `inference_call_count`.

## D. QWEN OTHER WORK

### Consultant

**VERIFIED:** this workspace has zero assistant turns and zero assistant quality receipts. No consultant Qwen call has been persisted for the new project.

### NTD

**VERIFIED and separate from project processing:** `ru.asd-kontur.spine.ntd-worker` was running as PID 98263. Its queue contains 319 succeeded `provision_extraction` jobs, zero queued/running/failed jobs, 1,669 provision-semantic rows, and last completed at 2026-09-24 18:36:15 +12. This NTD work did not advance the new workspace during the observed interval.

### Developer-worker / code assistance

**UNKNOWN in the absolute sense; no persisted project evidence was found.** The project database contains no developer-worker attribution. The inspected Codex transcript does not establish a direct developer-worker Qwen call that wrote project facts for this workspace. The local project-document requests were submitted by document-worker identities. Qwen’s HTTP server does not persist requester identity, so a complete negative proof is unavailable.

## E. CODEX RUNTIME INTERVENTIONS

### Proven manual operations

| Operation | Automatic ASD-KONTUR? | Manually executed by Codex? | Required for observed progress? | Should exist in production? |
|---|---|---|---|---|
| create intake DAG at document admission | yes | no | yes | yes |
| claim an already-runnable job | yes | no | yes | yes |
| submit Qwen request for a claimed semantic job | yes | no direct Codex submission found | yes | yes |
| create retry after transient semantic runtime failure | no in this failure path | yes | yes | yes, bounded and typed |
| retry 19 page-classification failures | no | yes (`manual-retry:*`) | yes for 18 recovered documents | yes, automatically for transient failures; invalid output needs bounded recovery |
| retry failed OCR job | no | yes | yes for that page chain | yes, when failure is transient/recoverable |
| create semantic-recovery project-definition jobs | only through an explicit command | yes, via `start_project_understanding` | yes for current model population | yes, planner-owned and idempotent |
| create first project-work reconciliation batches | explicit command required initially | yes, via `start_project_work_reconciliation` | yes | yes, planner-owned |
| refill project-work reconciliation after a successful batch | yes, for this one job family | Codex also invoked the command several times | yes | yes; current narrow implementation is insufficient |
| schedule incremental project-understanding after successful definition/classification | yes | no | yes | yes |
| schedule post-structure model refresh | yes | no | yes | yes |
| detect a workspace with blocked DAG and missing recovery successor | no general service | Codex diagnosed it manually | yes | yes |
| deploy/restart API/worker components | no | yes | not ordinary content processing, but changed which code ran | remains controlled operations, not runtime scheduling |
| direct project-table SQL inserts/updates | no evidence found | no evidence found; inspected SQL was read-only | no | no |
| manually insert project facts/conclusions | no evidence found | no evidence found | no | no |

Database evidence for manual interventions:

- 18 page-classification retry jobs were created together at 2026-09-29 18:30:51 +12 and succeeded.
- one OCR retry was created at 18:31:20 and succeeded.
- one further page-classification retry was created at 18:44:47 and failed locator validation.
- three command-level project-understanding jobs were created at 20:31:43, 20:31:53, and 21:05:48; the first command created 20 semantic-recovery project-definition jobs.
- the first four work-reconciliation jobs were created at 19:33:41 immediately after a Codex command. Later groups at 20:56:38 and 21:02:29 also align with Codex invocations. From 23:56 onward the worker’s deployed bounded idle/completion refill created additional groups automatically until 08:04:44.

Codex transcript evidence is in `/Users/oleg/.codex/sessions/2026/08/25/rollout-2026-08-25T10-41-42-01a035ef-c8d6-7833-803d-5ee40b6e4423.jsonl`. Relevant calls include `start_project_work_reconciliation` at 2026-09-29 07:33:41Z, 08:14:50Z, 08:56:37Z, 09:01:36Z, 09:02:29Z, and 09:23:47Z, and `start_project_understanding` at 07:58:18Z, 08:31:43Z/53Z, and 09:05:47Z. Duplicate transcript lines can be the tool call and its recorded execution and must not be counted as separate operator actions.

## F. AUTONOMY GAP

### Exact cause of the stop

The stop is the combination of three verified defects:

1. **Transient semantic errors become terminal failures.** In `DocumentWorker._execute`, every `UnderstandingStageFailure`, `NativeExtractionFailure`, and `OcrFailure` is translated to `DeterministicJobFailure`. `run_once` immediately terminals a `DeterministicJobFailure` as `FAILED`. Therefore `qwen_semantic_runtime_unavailable` does not enter the existing `RetryableJobFailure` / `retry_job` path even though the job has attempts remaining.
2. **The intake DAG is pre-created with strict success dependencies.** `_enqueue_document_jobs` creates all normal stages and links each to the prior stage with `success_required`. When an upstream job becomes terminal `FAILED`, all downstream rows remain queued but unclaimable.
3. **There is no general autonomous planner.** The worker contains completion hooks for incremental project-understanding refresh, post-structure refresh, and project-work-reconciliation refill. It does not periodically derive every missing eligible recovery/successor from durable workspace state. No separate orchestrator/reconciler launchd service exists.

At 10:13–10:19 +12 the dependency predicate found **zero claimable queued jobs**. Every one of the 120 queued jobs was dependency-blocked. The 23 unrecovered failure roots were:

- one unsupported format-inventory job;
- three page-classification invalid-locator jobs;
- 15 project-definition jobs, primarily `qwen_semantic_runtime_unavailable`;
- two work/quantity/material jobs with `qwen_semantic_runtime_unavailable`;
- two project-work reconciliation jobs with runtime-unavailable failures.

The system has useful recovered stage outputs for several of these documents, but the recovery jobs were not connected as successful replacements for every original dependency. Thus persisted semantic data and the original durable DAG disagree about effective completion.

### What continues if Codex exits now

**Continues automatically:**

- supervised API, document worker, assistant worker, Qwen process, and NTD worker remain running under launchd;
- the document worker will claim a newly claimable existing job;
- stale leases can be recovered by the claim function;
- a successfully completed project-definition/classification job schedules an incremental model refresh;
- a successfully completed structure reconciliation schedules a post-structure refresh;
- a successfully completed project-work reconciliation can refill that same bounded job family;
- foreground assistant work would be claimed if a user created it.

**Stops in the current state:**

- document semantic recovery for the 15 failed project-definition roots;
- work/quantity/material recovery for the two failed roots;
- locator recovery for the three invalid classification roots;
- reconnection of recovered semantic results to the old dependency DAG;
- downstream work-package, matrix, structure, evidence-index, and final analysis stages for 19 documents;
- project-wide determination that incomplete eligible work exists but no runnable job exists;
- terminal project-completion calculation.

### Why Qwen is idle

The Qwen process is loaded (PID 36812, approximately 25% resident memory, 0.1% CPU at 10:18:44) but there is no claimable project job to submit. The process was not observed receiving a new request. Its `/health` request returned an empty response and logged a `BrokenPipeError`, so endpoint readiness itself was **not verified**; process existence and loaded memory are not treated as proof of health.

Qwen is therefore idle primarily because ASD-KONTUR has not produced a runnable semantic job, not because a queued runnable job is waiting unclaimed. Whether the current Qwen endpoint would successfully execute a new request is separately unverified by this non-mutating audit.

## G. DATA ORIGIN AUDIT

| Major output/fact family | Primary origin | Codex influence | Finding |
|---|---|---|---|
| file identity, bytes, hashes, media type, page inventory | deterministic intake/native code | operational deployment only | VERIFIED deterministic |
| native text/layout | deterministic parsers | implementation only | VERIFIED deterministic |
| 36 routed OCR pages | local Qwen vision, deterministically validated | no direct content authored by Codex found | VERIFIED Qwen |
| document roles | Qwen role candidates plus deterministic role rules | Codex added filename/content role heuristics after inspecting this corpus | mixed Qwen + deterministic; partially corpus-informed code |
| project fields and project name | Qwen extraction plus deterministic consolidation | Codex added generic project-purpose/name and corroboration rules | mixed Qwen + deterministic |
| facilities/structures | Qwen structure candidates plus deterministic identity/location consolidation | Codex added generic location/address/facility-root rules after inspecting rows | mixed; no manual fact insert found |
| work observations | Qwen engineering extraction | Codex did not author raw observations | VERIFIED Qwen source |
| normalized work families | Qwen reconciliation plus deterministic classifiers | Codex authored many classifiers during this project | mixed; current labels are not purely independent Qwen findings |
| facility/work association | Qwen suggestions plus explicit headings/location rules | Codex authored VOR/facility association rules during this project | mixed |
| quantities/materials | Qwen extraction and native rows; deterministic unit normalization/arithmetic | Codex authored unit and role normalization | mixed; arithmetic deterministic |
| quantity comparisons | deterministic matching/arithmetic over extracted data | Codex authored and revised comparison policy after inspecting this corpus | deterministic, corpus-informed implementation |
| issue/risk/customer question | deterministic Tender materialization from current model | Codex-authored generic rules shape the only current rows | no manual DB insert, but not purely Qwen-authored conclusions |
| assistant conclusions | none for this workspace | none persisted | NOT AVAILABLE |
| owner-provided expected errors | none supplied | none found in production code/data | VERIFIED absent from inspected inputs |

Targeted production-code search found no hardcoded workspace ID or display name. Tests do contain the Okeanskaya address, retaining-wall names, and exact filenames. Those tests validate generic behavior with values copied from the real corpus; they do not encode an owner-known discrepancy, but they weaken the claim that validation is fully blind.

The relevant commit sequence includes corpus-driven generic changes such as `9d7bdf8` (project hierarchy roots), `696f564` (location association), `5739d68` (Russian units), `e39ce45` (project overview), `6c3a3ec` (address-specific structures), `61e02f2` (facility aliases), `e2cd947`/`c7661ac` (work-family classification), `f6d2e3a`/`ac46097` (commercial role/scope), and `85697c7` (project purpose). These are code improvements, but they are also evidence that Codex directly influenced how this corpus became an engineering model.

## H. TOKEN-USAGE INTERPRETATION

### Codex

An isolated Codex token total for only the new-project interval is **UNKNOWN**. The available transcript is a long-running, compacted session whose token counters include prior tasks and repeatedly cached context. It does not attribute tokens by activity.

The transcript establishes that Codex tokens were spent on:

- source-code inspection, implementation, tests, CI, deployment, and debugging;
- database and runtime inspection;
- queue/retry/reconciliation commands;
- selected project-derived rows, filenames, facility names, quantities, and model outputs used to design generic rules.

Therefore the observed Codex usage is **not consistent with code/orchestration only** in the strict sense: Codex did read selected document-derived content and used it when writing deterministic interpretation code. It did not read the entire corpus in context, and no direct insertion of a manually written project fact was found.

### Qwen

Prompt and completion tokens are **UNKNOWN**. The Qwen server does not persist usage, and stage/job tables do not contain token columns. Persisted batches and the 324 reconciliation inference count prove substantial model work, but token consumption cannot be reconstructed from them.

Token volume alone cannot distinguish “Qwen processed the document” from “Codex read the document.” The persisted Qwen batch outputs prove the former happened. The Codex transcript proves selected content inspection and corpus-informed rule authoring also happened. Both are true.

## I. CODEX-ABSENT OBSERVATION

Observation procedure:

1. No queue refill, successor, retry, SQL mutation, service restart, or Qwen generation command was issued.
2. Only launchd-supervised services were left running.
3. Job state was read at 10:13 and again at 10:19 +12.
4. Qwen/document/NTD processes and Qwen CPU/memory were observed read-only.

Result:

| Measure | Start | End | Delta |
|---|---:|---:|---:|
| succeeded jobs | 393 | 393 | 0 |
| failed jobs | 42 | 42 | 0 |
| queued jobs | 120 | 120 | 0 |
| running jobs | 0 | 0 | 0 |
| last progress | 08:08:51 +12 | 08:08:51 +12 | none |
| claimable queued jobs | 0 | 0 | 0 |

No project job appeared, no Qwen project request was evidenced, no document completed, and the project model did not advance. The short controlled observation is reinforced by the already elapsed idle period of more than two hours since the last durable result.

**Conclusion: current autonomous project processing is false.** Supervision keeps processes alive, but no supervised component repairs this stalled project state.

## J. REQUIRED ARCHITECTURAL FIX

This section is a required fix statement, not an implementation performed by this audit.

1. Add a lightweight supervised project orchestrator/reconciler, or prove equivalent independent lifecycle inside an existing supervised worker. It must derive missing eligible work from durable workspace state, not from an interactive command.
2. Define a durable per-workspace stage state machine and terminal/partial-with-blockers calculation. The planner must compare accepted stage results with DAG lineage and repair missing successors idempotently.
3. Classify failures before terminalization. `qwen_semantic_runtime_unavailable`, transient endpoint/lease/timeouts, and bounded output exhaustion must use bounded retry/recovery. Unsupported formats and schema-invalid permanent content must remain terminal or explicitly blocked.
4. Make recovery results satisfy or supersede the failed prerequisite in the durable dependency model. Do not leave a valid semantic result beside an unclaimable original DAG.
5. Generalize event-driven successor creation beyond the three existing hooks. Add a low-frequency reconciliation sweep as insurance against missed completion events, expired leases, machine sleep/wake, and process restarts.
6. Keep Qwen scheduling sequential and supervised. Foreground work should run at safe job boundaries, after which background project processing resumes without Codex.
7. Persist a Qwen request ledger with model/profile, requester worker identity, source scope, timestamps, duration, terminal outcome, and available token counts. Do not log document bodies or secrets.
8. Add a workspace watchdog condition: active workspace + incomplete eligible stage + no runnable/running job + no explicit blocker. The orchestrator must repair it or persist an operational failure visible to the user.
9. Add `AUTONOMOUS-TENDER-PROCESSING-01`: demonstrate multiple Qwen completions and successor creation with no developer command, then repeat after document-worker, orchestrator, Qwen, and API restarts.

Until those changes are implemented and the real incomplete workspace progresses under supervised services alone:

`AutonomousProjectProcessing=false`

## Evidence appendix

Primary evidence sources:

- durable job state, dependencies, attempts, stage results, OCR records, engineering batches, work-reconciliation results, and assistant tables in the local PostgreSQL runtime (read-only transactions scoped to this workspace);
- launchd services `ru.asd-kontur.spine.api`, `ru.asd-kontur.spine.worker`, `ru.asd-kontur.spine.assistant-worker`, `ru.asd-kontur.spine.qwen`, and `ru.asd-kontur.spine.ntd-worker`;
- Qwen log `/Users/oleg/.asd-kontur/public-demo/logs/qwen.log`;
- Codex transcript `/Users/oleg/.codex/sessions/2026/08/25/rollout-2026-08-25T10-41-42-01a035ef-c8d6-7833-803d-5ee40b6e4423.jsonl`;
- source symbols:
  - `PostgresSpineRepository._enqueue_document_jobs`;
  - `PostgresSpineRepository.manually_retry_job`;
  - `PostgresSpineRepository.start_project_understanding`;
  - `PostgresSpineRepository.start_project_work_reconciliation`;
  - `PostgresSpineRepository.refill_workspace_project_work_reconciliation_if_idle`;
  - `PostgresSpineRepository.schedule_incremental_project_reconciliation`;
  - `DocumentWorker.run_once`, `run_forever`, and `_execute`;
  - `QwenDocumentSemanticAdapter`, `QwenVisionOcrAdapter`, and `QwenProjectWorkReconciler`.

No credentials, prompts, document bodies, or model outputs are reproduced in this report.
