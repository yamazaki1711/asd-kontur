# Autonomous Project Processing 01

Status: implementation in progress

Forensic baseline: `docs/reports/RUNTIME_FORENSICS_CODEX_QWEN_2026-09-30.md`

Baseline report SHA-256: `79be6b4ea700f659e5b94ba011987abc33ebac228570fdff8249a26c55d6fa43`

## 1. Forensic baseline and root cause

The real Tender workspace `01a0eba7-70ba-7770-9601-1a713dd359cf` stopped at 393
succeeded, 42 failed, 1 cancelled and 120 queued jobs. None of the queued jobs
was claimable. Local Qwen remained loaded but correctly received no request.

The failure had two systemic causes:

1. the document worker translated transient local-Qwen outages into
   `DeterministicJobFailure`, terminalled those attempts, and therefore left the
   strict pre-created downstream dependency chain unsatisfied;
2. autonomous idle refill covered only project-work reconciliation. Initial
   project-understanding scheduling, terminal dependency repair, semantic
   recovery and retries were still invoked by developer commands.

The accepted forensic report is immutable history. This implementation does
not reclassify past operator actions as autonomous operation.

## 2. Manual operations mapped to runtime ownership

| Prior manual action | Why it was needed | Runtime owner | Durable trigger and idempotency | Failure policy |
|---|---|---|---|---|
| Create successor | terminal prerequisite left a queued dependent unclaimable | document worker normal completion hook; orchestrator safety sweep | accepted terminal receipt plus predecessor/replacement lineage | preserve old attempt; create one causally linked replacement |
| Semantic recovery | missing/failed semantic result was not planned after intake | project orchestrator | active source version, profile and semantic input digest | bounded local-Qwen retry; invalid content stays typed and terminal |
| Retry scheduling | transient Qwen outage was classified as deterministic | document worker | same durable job while attempt budget remains | exponential bounded delay; no infinite retry |
| Project-understanding command | no persistent planner owned initial/current materialization | project orchestrator | source/review/classification/semantic fingerprint | idempotent existing job reuse |
| Structure/work reconciliation command | downstream semantic stages depended on an operator seed | worker completion hooks plus orchestrator sweep | exact model/result/profile fingerprint | bounded batches and compatible-result reuse |
| Queue refill | only a developer command noticed an empty semantic queue | project orchestrator; existing work-refill contract | unresolved candidate/version/profile identity | enqueue only unprocessed compatible rows |
| Dependency repair | queued descendants retained terminal prerequisites | orchestrator safety sweep | failed job identity and accepted causal successor | mark explicit dependency failure, then rewire to accepted replacement |
| Resume after partial/failure | no durable component reevaluated eligibility | orchestrator safety sweep | active workspace and current durable state | retry transient infrastructure failures; retain content blockers |

## 3. The 120 blocked jobs

The fixed baseline denominator is 120 queued jobs:

- 100 were directly behind another queued job in the same blocked chain;
- 17 were directly behind terminal `qwen_semantic_runtime_unavailable` attempts;
- 1 was behind `job_cancelled_before_effect`;
- 1 was behind `qwen_semantic_response_invalid_locator`;
- 1 was behind permanent `document_format_not_supported`.

By immediate dependent kind, the chain contained 19 evidence-index updates, 19
structure reconciliations, 19 project-understanding reconciliations, 19
requirement matrices, 19 work packages, 17 quantity/material extractions and 8
other document stages. The repair is lineage-based; it does not update these
120 rows individually.

Transient Qwen failures receive immutable, causally linked replacement jobs.
Queued descendants are first marked `dependency_terminal_failure`; a successful
equivalent replacement then causes the existing bounded recovery contract to
create and rewire the direct successor. Cancellation, invalid locator content
and unsupported formats are not blindly retried.

## 4. Runtime architecture after this change

The application has six distinct supervised roles:

- API: user requests only;
- document/project worker: deterministic stages and calls to the persistent
  local-Qwen service;
- project orchestrator: low-frequency durable eligibility reconciliation;
- assistant worker: foreground consultant requests;
- Qwen service: one persistent heavy MLX model;
- NTD worker: independent platform-knowledge processing.

The project orchestrator does not interpret documents. Every sweep asks which
active workspace has missing eligible work, repairs transient terminal
lineages, ensures the idempotent project model, and refills bounded work
reconciliation. Worker terminal-success hooks remain the normal event-driven
path. The 30-second sweep is the missed-event safety net, not a busy loop.

## 5. Durable state, retries and stalls

The durable job graph remains the project state machine. Job identity combines
workspace, job kind, idempotency key and semantic input digest. Accepted output
is never overwritten. Current worker attempts treat local-Qwen semantic, work
reconciliation and vision-runtime unavailability as retryable. Historical
attempts terminalled by older releases receive at most two autonomous
replacement generations, each retaining the existing per-job attempt budget.

Permanent content failures are not retried merely to create activity. A queued
graph with no claimable work is reconciled into an explicit terminal-dependency
state. If no eligible repair exists, that state remains an operational blocker
rather than silent idleness.

## 6. Qwen scheduling

The document worker remains the only project component that sends document
semantic requests to local Qwen. The orchestrator only publishes durable work.
Foreground consultant activity is checked at safe job boundaries; the worker
yields an untouched lease and resumes background work automatically afterward.
No second heavy Metal process is introduced.

## 7. launchd topology

`asd-kontur-spine render-launchd` now emits
`ru.asd-kontur.spine.project-orchestrator` with the same pinned release,
explicit environment, bounded log and `KeepAlive` policy as the existing API
and workers. The runtime command is `run-project-orchestrator`. It has no
terminal or Codex dependency.

## 8. Corpus-contamination audit

No production source contains either real workspace UUID or the new project
display name. No owner-known blind finding is encoded. Targeted source search
did find three historical corpus-informed areas requiring classification:

- work-family stem matching: general construction algorithm (A/B);
- LOS/KNS designation parsing: reusable utility but domain-narrow, retained as
  an existing supported-project convention rather than a universal facility
  ontology (A/B);
- exact sheet-pile/OCR repair strings and one exact project-title exclusion:
  corpus-specific heuristics (C/D), scheduled for removal/generalization before
  blind-analysis acceptance.

Tests may retain synthetic or licensed wording, but runtime logic must not know
a project answer.

## 9. Acceptance evidence

The final candidate is supervised under launchd with migration
`0078_cross_document_scope_reconciliation`. During the final read-only
observation, no manual refill, retry, successor, reconciliation or SQL write was
issued. The real incomplete workspace increased from 473 to 477 succeeded
jobs. A project-definition job completed after the controlled Qwen restart,
the orchestrator published downstream model jobs, and the worker automatically
claimed the next project-definition job. That successor reached two of five
accepted semantic batches and maintained a current lease and heartbeat.

Worker restart recovered an expired lease without repeating accepted output;
orchestrator restart reconstructed eligible work; API restart did not stop
background processing; and Qwen restart was performed at a zero-running-job
boundary before the worker automatically resumed semantic processing. Mac
sleep/wake was not tested and is not claimed.

## 10. Performance and remaining risks

Baseline queue-refill latency was unbounded because no planner existed. The new
safety bound is one 30-second sweep plus normal claim latency. Actual Qwen idle
gap, request duration, retry rate and semantic-to-project-model latency will be
measured during the real autonomous run.

Known limitations after acceptance:

- cancellation/unsupported/invalid-locator roots intentionally remain partial
  blockers unless a separate supported recovery strategy applies;
- the Qwen server health route is single-threaded and does not answer while a
  long generation occupies the request loop, although process, connection,
  worker heartbeat and accepted-batch evidence remain available;
- the current project model is still semantically shallow and incomplete;
- machine reboot resilience is not claimed; the supported boundary is the
  per-user launchd session until separately tested.

Final operational status for this release:
`AutonomousProjectProcessing=true`. This does not imply
`GeneralizedTenderHarness=true` or `ProductReady=true`.

## 11. Reconciliation queue amplification correction — 2026-10-02

A thermal/load investigation of the real blind Tender workspace found a
healthy active Qwen request but an unhealthy durable backlog. The running
contract job renewed its lease every few seconds and completed successive
batches, while the workspace had accumulated 10,026 time-eligible queued jobs:
5,928 structure reconciliations and 3,867 project-understanding
reconciliations accounted for nearly all of them. One source had 449 completed
and 983 queued project refreshes. This was scheduling amplification, not a
stuck model process.

The event path previously assigned a unique project refresh to every completed
semantic job. Each project refresh could then create a structure refresh and a
post-structure project refresh. In parallel, the 30-second safety sweep
included transient job identities and states in its semantic fingerprint.
Thus all individual actions were durable and idempotent by their own identity,
but the chosen identity was too fine-grained for a workspace materialized
view.

The corrected policy is workspace/stage coalescing:

- one queued refresh absorbs newly accepted workspace state;
- a leased or running refresh is never cancelled or replaced;
- event-driven completion and the periodic sweep serialize their active-job
  decision with a transaction-scoped advisory lock;
- the newest pending project and structure snapshots are retained;
- older queued snapshots receive immutable cancellation and terminal receipts
  with `superseded_project_reconciliation` rather than being deleted;
- a project refresh required by a retained nonterminal structure job is not
  superseded.

Supersession is bounded per workspace and sweep, so a large historical backlog
converges without a single unbounded transaction. Accepted results, running
jobs, source versions, NTD memory and global knowledge are not changed. A
disposable PostgreSQL acceptance creates three project snapshots and three
dependent structure snapshots, retains the newest coherent pair, and verifies
four terminal supersession receipts.
