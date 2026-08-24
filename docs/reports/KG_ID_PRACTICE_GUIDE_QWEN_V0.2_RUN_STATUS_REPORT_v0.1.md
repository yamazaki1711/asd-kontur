# KG-ID-01 Qwen v0.2 run status report v0.1

Status: qualification `PASS`, full Pass A v0.2 run `COMPLETE` (425/425 page
terminal receipts). This report is a new artifact; it does not edit
`docs/handoffs/QWEN_ID_PRACTICE_GUIDE_HANDOFF_v0.1.md` retroactively. KG-ID-01
overall gate status is unchanged: Pass B verification, deterministic
reconciliation, canonical publication and fresh-session Knowledge Gateway
memory acceptance have not been performed and remain required before
`ProductReady`.

## Preflight (all verified before any Qwen invocation)

- Canonical worktree `/Users/oleg/asd-kontur-rebaseline`, branch
  `implementation/kg-id-practice-guide-v0.1`, HEAD
  `9857801bf968d1a7897add4efe1d679f3c46d964` — matches handoff exactly.
- Staged source SHA-256
  `469b9fbe001cc87de5235f14615875b5adc11cdeea041f0d7733f5ed32fa297c`,
  19,044,364 bytes — matches handoff's verified remote/staged digest exactly.
- No `qwen_session_runner.py` / PID `66275` process was running. Only the
  unrelated, pre-existing `mlx_vlm.server` (PID 48212) was present; it was not
  touched, stopped, or treated as a checkpoint.
- No stale lock file at `qwen-heavy-session.lock`; no v0.2 qualification
  receipt ledger existed yet (fresh start, as the handoff stated).
- SHA-256 verified byte-for-byte against the handoff table for: source
  provenance, page manifest, qualification-pass-a-v0.2-jobs.json,
  full-pass-a-v0.2-jobs.json, qwen-8bit-profile-v0.2.json,
  qualification-decision-v0.2.json, qualification-pass-b-batched-jobs.json,
  the superseded v0.1 jobs/receipts (left untouched), the runner source
  (`qwen_session_runner.py`), the prompt builder (`pipeline.py`), and the
  contract schema. All matched.

## Qualification v0.2 (7 stratified pages: 1, 23, 84, 110, 211, 362, 425)

Command run exactly as specified in the handoff, no parameter, prompt, schema
or request-file changes:

```sh
cd /Users/oleg/asd-kontur-rebaseline && /Users/oleg/mlx/runtime/.venv/bin/python src/asd_kontur/practice_guidance/qwen_session_runner.py --model /Users/oleg/mlx/models/Qwen3.8-27B-MLX-8bit --request /Users/oleg/asd-kg-id-practice-guide.tABE4W/qualification-pass-a-v0.2-jobs.json --receipts /Users/oleg/asd-kg-id-practice-guide.tABE4W/qualification-pass-a-v0.2-receipts.jsonl --max-tokens 3500 --max-battery-celsius 45 --max-job-seconds 900 --lock-file /Users/oleg/asd-kg-id-practice-guide.tABE4W/qwen-heavy-session.lock
```

Observed live (self-monitored, not delegated): 7/7 jobs `completed`, 0
`failed`, durations 4.9s–114.0s (well under the 900s per-job limit), battery
30.42–30.63°C (well under the 45°C guard), no thermal warning at any point.

### Acceptance criteria and evidence

The KG-ID-01 implementation doc (`docs/implementation/KG_ID_PRACTICE_GUIDE_INGESTION_v0.1.md`,
§5/§10) and `validation.py`/`commands.py evaluate-pass-a` define the
deterministic middle-layer gate. It was run unmodified
(`asd_kontur.practice_guidance.commands evaluate-pass-a`) against the fresh
v0.2 receipts:

| Criterion | Result | Evidence |
|---|---|---|
| All 7 receipts present, strict JSON, schema-valid | PASS | `expected_receipts=7`, `valid_receipts=7`, `integrity_errors=[]` in `qualification-pass-a-v0.2-evaluation.json` |
| No printed-page/PDF-page locator mismatch (the earlier page-211 failure mode) | PASS | page 211 parsed and validated cleanly; no `LOCATOR_INVALID`/`LOCATOR_OUTSIDE_SCOPE` |
| No truncation / malformed JSON | PASS | 0 integrity errors, 0 parse failures |
| No duplicate candidates | PASS | `duplicate_failures=0` |
| Deterministic schema/native-text-grounding/form-field checks | PASS | `validation_failures=0` on every one of the 7 pages, including the 3 pages with candidates (110: 7, 211: 3, 362: 6 candidates; 16 total) |
| Russian semantic-field grounding (the exact v0.1 defect being corrected) | PASS | `NATIVE_TEXT_MISMATCH=0` occurrences despite substantial native text (594/467/1362 chars on pages 110/211/362); manually inspected candidate `section`/`topic`/`instruction` text on all three pages — entirely in Russian, e.g. "Наименование организации, которая производит замоноличивание стыков (подрядчик)." |
| No two heavy Metal sessions / lock respected | PASS | single `flock` acquired, released on exit, unrelated `mlx_vlm.server` untouched |
| `temperature=0` | PASS | hardcoded in `qwen_session_runner.py:166` (`temperature=0.0`), read from source, not inferred |

All criteria measured, none by impression. Qualification decision: **PASS**.
No `qualification-decision-v0.2.json`-style artifact was overwritten; a new
evaluation output was written instead (`qualification-pass-a-v0.2-evaluation.json`
and `qualification-pass-a-v0.2-derived-pass-b-jobs.json`) so the handoff's
listed prior-development-qualification artifact stays intact and undisturbed.

## Full Pass A v0.2 run (425/425 pages)

Qualification passed, so the full run was started immediately, command exactly
as specified in the handoff:

```sh
cd /Users/oleg/asd-kontur-rebaseline && /Users/oleg/mlx/runtime/.venv/bin/python src/asd_kontur/practice_guidance/qwen_session_runner.py --model /Users/oleg/mlx/models/Qwen3.8-27B-MLX-8bit --request /Users/oleg/asd-kg-id-practice-guide.tABE4W/full-pass-a-v0.2-jobs.json --receipts /Users/oleg/asd-kg-id-practice-guide.tABE4W/full-pass-a-v0.2-receipts.jsonl --max-tokens 3500 --max-battery-celsius 45 --max-job-seconds 900 --lock-file /Users/oleg/asd-kg-id-practice-guide.tABE4W/qwen-heavy-session.lock
```

Result, self-monitored continuously to completion:

- 425/425 unique job IDs in `full-pass-a-v0.2-receipts.jsonl`, all
  `state="completed"`, 0 `failed`, 0 duplicate receipt lines, 0 job IDs
  missing against `full-pass-a-v0.2-jobs.json`, 0 extra/unknown job IDs.
- Receipt ledger SHA-256:
  `efc12fea68cd4db260b7e012979182e7e01e6e767803d0c71ee88dfe58e5b978`.
- Per-job duration: min 4.56s, max 206.59s — every job finished well inside
  the 900s `--max-job-seconds` bound; no timeout fired.
- Battery: max observed 30.75°C (guard threshold 45°C); `thermal_warning`
  never observed `True` across all 425 attempts.
- Total measured Qwen generation time across all pages: ≈805 minutes (≈13.4
  hours), sequential, single model load, single heavy Metal session.
- Process exited cleanly (no exception propagated); the exclusive lock file
  was released.

This is the **corrected v0.2 Pass A ledger only**. It is not Pass B
verification, not deterministic reconciliation, not the platform publication,
and not the fresh-session Knowledge Gateway memory acceptance — those stages
of KG-ID-01 (`docs/implementation/KG_ID_PRACTICE_GUIDE_INGESTION_v0.1.md` §10,
items 2–4) were explicitly out of scope for this run and were not started.
Every `GuidanceCandidateVersion` produced here remains a candidate: it has not
been Pass-B-verified, deterministically validated at full-corpus scale, or
published, and none of it may be treated as approved guidance, an active
`RuleVersion`, NTD, or a workspace fact.

## Errors and uncertainties

- None. No job failed, no integrity error, no thermal guard trip, no lock
  contention, no truncation, no locator mismatch across qualification or the
  full 425-page run.
- The pre-existing `qualification-decision-v0.2.json` in the staging area
  (timestamped 17:51, before the final v0.2 prompt/profile artifacts at
  19:21–19:28) is stale relative to this run and was not relied on for the
  PASS decision above; a fresh evaluation was produced instead. It was not
  deleted or overwritten.

## Git status and diff summary

Unchanged from the state recorded in
`docs/handoffs/QWEN_ID_PRACTICE_GUIDE_HANDOFF_v0.1.md` at the start of this
session — no tracked file was modified or committed during this run (all
Qwen I/O stayed in the external, non-Git staging area
`/Users/oleg/asd-kg-id-practice-guide.tABE4W/`). `git status --short` still
shows only the same pre-existing modified/untracked KG-ID-01 files listed in
the handoff, plus this new report file. No commit was created.

## Next action

The next KG-ID-01 stage is Pass B independent verification and deterministic
reconciliation of the 425 v0.2 candidates, followed by the qualified human
publication decision — none of which Qwen or this run is authorized to
perform unattended. There is no pending resume command for Pass A: it is
complete and reconciled 425/425. If Pass A ever needs to be re-run for a typed
repair, the same full command above is safe to reuse as-is — the runner skips
job IDs already present in `full-pass-a-v0.2-receipts.jsonl`.
