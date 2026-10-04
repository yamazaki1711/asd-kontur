# ASD-KONTUR project runtime forensic — 2026-10-05

## Executive verdict

The owner-visible long-running workspace is not blocked at document intake. All 21
documents are processed. The reported `30.7%` (described by the owner as roughly
`35%`) is a defective projection calculated from historical durable-job outcomes,
including thousands of cancelled and superseded jobs.

Local Qwen is doing real semantic work, but the useful-work ratio is poor. The main
causes are repeated semantic-profile passes over compatible inputs, 28 validation
workspaces left ACTIVE in the same autonomous production scheduler, and bounded
jobs that can occupy the single model for multiple 900-second inference/repair
windows. Codex is not currently issuing normal queue-progression commands, but
Codex-authored profile revisions have repeatedly caused large semantic replays.

No source code, database state, queue state, worker state, or Qwen state was changed
during this forensic phase.

## Project identity

No active workspace, source package, or current project definition identifies a
residential-building demolition project. The only real uploaded owner workspace is:

| Field | Value |
|---|---|
| Workspace | `01a0eba7-70ba-7770-9601-1a713dd359cf` |
| Construction object | `01a0eba7-70ba-7e9f-a959-961a288e3805` |
| Display name | `Реконструкция Подпорной Стены` |
| Created | `2026-09-29 17:33:34+12` |
| Document records / source versions | `21 / 21` |
| Persisted PDF pages | `218` |
| Uploaded bytes | `32,853,480` |
| Document-processing completion | `21 / 21` |

The package contains demolition work, but the durable project identity is retaining-
wall reconstruction. This report does not silently reinterpret it as another OKS.

## Current professional state

The live `project-engineering-model-v80` projection contains:

- 3 facility cards;
- 324 consolidated works;
- 73 unclassified works;
- 7 quantity comparisons;
- 5 material comparisons;
- 322 cross-document scope comparisons;
- 3 professional issues;
- 3 customer questions;
- 3 contractor risks.

The latest accepted work-reconciliation result was recorded at
`2026-10-05 10:49:49+12`. The latest immutable project-understanding reconciliation
was recorded at `2026-10-03 15:10:54+12`; the interactive projection rebuilds the
engineering model from newer accepted work resolutions at read time.

## Why the dashboard reports approximately 35 percent

The backend method `SpinePostgresRepository.project_processing_status` computes:

`progress_percent = succeeded effective jobs / all effective jobs`

The frontend reads that number unchanged from
`/api/v1/workspaces/{workspace_id}/processing-status`.

At the forensic checkpoint the effective denominator was:

| State included in denominator | Count |
|---|---:|
| succeeded | 1,186 |
| cancelled | 2,357 |
| failed | 254 |
| reconciliation required | 54 |
| queued/running effective jobs | 9 |
| total | 3,860 |

Therefore `1,186 / 3,860 = 30.7%`. This is neither document completion nor
professional Tender completion. Profile changes can add or cancel jobs and move the
percentage independently of useful project progress.

## Qwen work by job family

The workspace has existed for six days, so the requested 14-day interval is the
entire project lifetime. Persisted Qwen-bearing job totals are:

| Job family | Jobs | Succeeded | Failed | Reconciliation required | Distinct input digests | Started-to-terminal minutes |
|---|---:|---:|---:|---:|---:|---:|
| OCR extraction | 22 | 20 | 1 | 1 | 21 | 63.6 |
| page classification | 100 | 77 | 22 | 1 | 63 | 12.7 |
| project-definition extraction | 1,437 | 1,398 | 15 | 23 | 130 | 1,960.5 |
| structure reconciliation | 1,402 | 55 | 0 | 19 | 1,402 | 19.1 |
| work/quantity/material extraction | 38 | 19 | 2 | 17 | 21 | 0.9 |
| project-work reconciliation | 976 | 875 | 57 | 16 | 964 | 3,416.0 |
| contract analysis | 568 | 250 | 228 | 54 | 477 | 770.0 |

Cancelled jobs are not shown as successful model work. Started-to-terminal time is a
job-level interval and is not exact GPU time: retries, process downtime and repair
calls are not represented uniformly. The server does not persist per-request token
or duration telemetry, so exact Metal-runtime attribution is not reconstructible.

During the last 24 hours the target workspace produced 266 successful
project-work reconciliation jobs. Job-count and started-to-terminal-time proxies
both assign approximately 70% of Qwen work to the real workspace during that
window. During the final observed hour only one target job started, while Qwen
rotated across validation workspaces; the target share fell to approximately 1–7%,
depending on proxy.

There were zero assistant turns and zero NTD jobs in the last 24 hours. The NTD
ledger remains exactly 319 succeeded jobs and was last changed on 2026-09-24.
OZERO contributed no active workload.

## Repeated and low-value inference

The principal repeat mechanisms are verified:

- 1,437 project-definition jobs contain only 130 distinct exact input digests;
- 568 contract-analysis jobs contain 477 distinct exact input digests;
- project-work reconciliation used 22 profile versions from v8 through v40;
- 875 accepted project-work results record 1,788 inference calls and 3,802 output
  observations;
- 2,248 unique candidate identities produced 1,554 repeated candidate outputs;
- individual candidates were emitted as many as 51 times across profile/scope
  combinations;
- the current active semantic queue contains 31 jobs whose candidate pair was
  already processed by a compatible earlier profile and 15 genuinely new pair
  jobs.

The last 24 hours consumed 266 successful target reconciliation jobs while the
professional projection remained broadly at 7 quantity comparisons, 5 material
comparisons and 3 findings. Qwen inference therefore produced real accepted
semantic rows but disproportionately little new professional state.

## Shared runtime and current long-running job

Twenty-eight controlled `Unseen Control` workspaces remain ACTIVE beside the real
workspace. At the checkpoint, 65 semantic jobs were queued globally and one was
running. The running job was not for the real project:

| Field | Value |
|---|---|
| Workspace | `01a0f605-1608-7c9a-8b8a-f13e83a11920` |
| Name | `Post-v20 Unseen Control - Steel Gallery SG-314` |
| Job | `01a108f3-4fce-72ad-a141-6019308b145e` |
| Kind | `PROJECT_WORK_RECONCILIATION` |
| Input | two steel-gallery cross-document scope rows |
| Attempt | 2 |
| Started | `2026-10-05 10:16:32+12` |

It exceeded 47 minutes while the v40 completed-job median was 87 seconds and p95
was 217 seconds. It continued to heartbeat and the Qwen process consumed CPU, so it
was anomalously slow rather than abandoned. The 900-second request timeout plus
bounded repair/retry permits one logical job to occupy the single model for multiple
timeout windows.

The Qwen launchd process loaded once in its current process lifetime, beginning at
`2026-10-05 10:46:23+12`. Source inspection confirms one model load per supervised
server process, not per job. Historical exact load count is unknown because it is
not persisted; old shutdown warnings are not a reliable load ledger.

## Queue and dependency state

The real workspace physically had 20 queued jobs:

| Job family | Count | Explicit dependency state |
|---|---:|---|
| project-work reconciliation | 3 | no explicit prerequisite |
| requirement-matrix assembly | 5 | succeeded |
| project-understanding reconciliation | 12 | succeeded |

No target job had a stale running lease. The 17 downstream jobs are claimable by
their explicit durable dependency edges. Their `causation_id` points at older
historical rows in some cases, but causation is not the claim prerequisite; the
separate `durable_job_dependencies` rows all point to succeeded prerequisites.

The governing claim function performs workspace fairness before priority. This
prevents one workspace from monopolising Qwen, but because 28 test workspaces are
ACTIVE it also gives them production turns. A workspace can receive new work after
its previous current-profile queue drains, so the real project's bounded completion
time cannot be proven from the present queue snapshot.

## Codex production dependency

The accepted 2026-09-30 forensic report remains authoritative for the historical
failure: Codex manually created page-classification/OCR retries, semantic recovery,
initial project-understanding work and initial/refill reconciliation batches before
the autonomous orchestrator existed.

For the recent period, no manual queue refill, retry, successor, priority mutation,
project-fact insert, Qwen prompt, or SQL data repair was found. The supervised
orchestrator and worker now create and claim successors. Release deployment and
service restart are developer operations, not ordinary production progression.

However, Codex-authored semantic profile revisions caused broad production replay.
The scheduler created the individual jobs autonomously, but changing v8 through v40
re-opened already interpreted candidate/pair work. This is a runtime-efficiency
defect caused by insufficient semantic-decision compatibility, not evidence that
Codex directly inserted project conclusions.

## Seven owner questions

1. **What did Qwen do?** Real OCR/classification/extraction/reconciliation and
   contract analysis, plus extensive repeated compatible-profile work.
2. **Why approximately 35%?** The percentage is a historical job-outcome ratio;
   2,357 cancelled jobs dominate its denominator although documents are 21/21.
3. **What share belonged to the project?** Exact GPU share is unavailable; two
   persisted 24-hour proxies are approximately 70%, while the final hour was only
   approximately 1–7% because control workspaces had the model.
4. **What was wasteful?** Profile-wide replays, repeated project-definition and
   contract passes, repeated candidate-pair reconciliation, and anomalously long
   repair/timeout jobs.
5. **What did Codex do?** Historically, manual progression; recently, no queue
   progression, but repeated developer profile releases amplified autonomous work.
6. **Can it finish today with Codex closed?** Autonomous turns continue, but a
   bounded terminal result is not currently provable because 28 validation
   workspaces share/refill the scheduler and professional terminal state is not the
   progress denominator.
7. **What exactly changes in 24 hours without Codex?** Supervised workers and Qwen
   continue. A specific target-project professional change cannot be guaranteed by
   the current graph; zero guaranteed professional-state change is the defensible
   answer until workload isolation and convergence are corrected.

## Minimal correction scope

The evidence supports four focused corrections:

1. persist/reuse compatible semantic pair decisions so a profile revision does not
   replay already accepted scope pairs without an explicit versioned invalidation;
2. isolate controlled validation workloads from ordinary production scheduling;
3. bound and expose current Qwen request/repair duration and useful output;
4. compute user progress from current effective stages/work, excluding superseded,
   cancelled and replaced historical attempts.

Autonomy must be reaccepted only when GPU inference changes professional project
state without a Codex runtime command.
