# Evidence index — OZERO diagnostic snapshot

Captured 2026-09-10T16:06:16+12:00 through 2026-09-10T16:09:01+12:00. Commands were read-only except for writing this diagnostic directory. Secrets, source contents, and connection strings are omitted.

| Ref | Observation / command class | Result |
|---|---|---|
| E-01 | `git status --short`, `git rev-parse HEAD`, `git branch --show-current` | Branch `implementation/ntd-canonical-memory-build-01`, HEAD `120006d`; pre-existing unrelated dirty/untracked paths preserved. |
| E-02 | `ps`, `lsof` | API PID 29697 and Qwen PID 36891 listen only on `127.0.0.1` ports 8765 and 8790; assistant PID 29715; document-worker PID 37287. |
| E-03 | Process environment parsed without recording credentials | API/assistant use `b67bcd6` and `asd_kontur_public_demo`; document worker executes `120006d`, while its launchd plist still declares `b26eb59`. |
| E-04 | `psql` metadata query to API database | Database revision `0038_consultant_request_id`; its `workspace.workspaces` table has zero rows and no requested OZERO ID. |
| E-05 | Read-only scan of local PostgreSQL databases that contain `workspace.workspaces` | No local database contains requested workspace ID. |
| E-06 | `curl --noproxy '*' http://127.0.0.1:8790/health` | Qwen runtime replied `ready`, model `Qwen3.8-27B`; this proves a ready server only, not an OZERO document-job call. |
| E-07 | `curl --noproxy '*' http://127.0.0.1:8765/api/v1/health` | HTTP 404. There is no accepted health endpoint at this path. |
| E-08 | Read launchd ingress plist and its log metadata | Reverse tunnel configured from VPS loopback port 18765 to MBP 8765. Last ingress log write is historical (2026-08-30), so it cannot prove current public routing. |
| E-09 | Read repository controller/repository/UI source | `project_understanding_view` returns an empty 200 view if there is no reconciliation; UI maps empty collections to the four zero counters. POST button calls `start_project_understanding`; its behavior requires database evidence from the actual workspace. |
| E-10 | Read current worker/pipeline/semantic source and commits | Current document-worker source contains Qwen vision OCR integration (`120006d`); deterministic phrase classification and structured candidate extraction remain non-Qwen paths. |
| E-11 | Read product goal, implementation plan, ADR-0006 and ADR-0007; parse registry/deltas | Registry has 142 IDs plus the v2.3 Android addition = composed denominator 143; readiness requirements recorded in report. |
| E-12 | Browser-control availability | No controlled browser binding is available in this session; no authenticated UI/API reproduction was possible through browser state. |

## Limits

The exact user-visible OZERO database, original turn, current job history, and uploaded source objects were not reachable from the API/worker configuration that is currently supervised on this MBP. The report deliberately labels statements derived from earlier mission notes as historical and unverified. No source files, job rows, status flags, caches, or deployment configuration were changed.

