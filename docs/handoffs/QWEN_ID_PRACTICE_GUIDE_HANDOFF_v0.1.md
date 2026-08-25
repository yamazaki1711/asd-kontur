# Qwen ID Practice Guide handoff v0.1

Status: **PAUSED**. KG-ID-01 is not complete and must not be reported as complete.
No Qwen process was restarted while preparing this handoff.

## Repository state

- Canonical working tree: `/Users/oleg/asd-kontur-rebaseline`.
- Branch: `implementation/kg-id-practice-guide-v0.1`.
- HEAD: `9857801bf968d1a7897add4efe1d679f3c46d964`.
- The branch contains uncommitted KG-ID-01 work and pre-existing modifications listed by
  `git status --short`; no commit was created for this handoff.
- The user-provided handoff context names `/Users/oleg/asd-kontur`, but that is the old
  dirty tree. The actual feature branch and KG-ID-01 changes are in the canonical tree
  above. The old tree was not modified.

## Source provenance

The `LOCAL_CANDIDATE_UNVERIFIED` statement in the latest handoff request is stale for
the source that was actually processed. Earlier in this run, the ordinary office-LAN
OpenSSH endpoint `192.168.0.110:22` was available, and the remote Desktop bytes were
hashed and copied. The remote and staged digests are identical.

| Role | Path | SHA-256 | Size | Status |
|---|---|---|---:|---|
| verified remote source | `/home/oleg/Desktop/Пособие по ИД.pdf` on host alias `oleg-ms-7e26` | `469b9fbe001cc87de5235f14615875b5adc11cdeea041f0d7733f5ed32fa297c` | 19,044,364 bytes | remote digest verified |
| exact staged source | `/Users/oleg/asd-kg-id-practice-guide.tABE4W/Пособие по ИД.pdf` | `469b9fbe001cc87de5235f14615875b5adc11cdeea041f0d7733f5ed32fa297c` | 19,044,364 bytes | admitted processing source |
| older local candidate | `/Users/oleg/MAC_ASD/library/sources/Пособие по ИД.pdf` | `f1bc2a2be9a3c912779299854cc3d6d406babe85784ea247971ab0ba825e2dd9` | 19,365,416 bytes | rejected: bytes differ |

The exact staged source is MIME `application/pdf`, PDF 1.7, unencrypted, and has 425
pages. Its source class is `MethodologicalPracticeGuide`, not NTD and not workspace
evidence. The full machine-readable provenance is in
`/Users/oleg/asd-kg-id-practice-guide.tABE4W/source-provenance.json`, SHA-256
`f3d06f6c6304ca58fe7ae5fe67acf3295d891ad116c3aa873d55a1bb51445972`.

## Model and execution profile

- Model: `/Users/oleg/mlx/models/Qwen3.8-27B-MLX-8bit`.
- Model identity: Qwen3.8-27B, cached revision
  `241ebb5f1d60b122fd653da658836a55feb9e2b0`.
- Model component-manifest digest:
  `sha256:a8c3cb163bef0c5b87812b4ce2d8ce2b6b497cb7daeb9f2e0f4f6ebb58c7cc41`.
- Runtime: `/Users/oleg/mlx/runtime/.venv/bin/python`;
  MLX 0.32.1, mlx-vlm 0.6.15, transformers 5.15.1.
- Backend/profile: local MLX/Metal, 8-bit, deterministic decoding,
  `temperature=0`, one heavy model session, sequential bounded jobs.
- Current intended execution profile:
  `/Users/oleg/asd-kg-id-practice-guide.tABE4W/qwen-8bit-profile-v0.2.json`,
  SHA-256 `6e92ed386df35cae71a36ba59375883571e98af2bf91cc6349f5a259a3dcfe10`.
- Semantic contract/schema: `practice-guide.ingestion/1.5.0` and
  `contracts/v1.5/schemas/practice-guidance.schema.json`, schema SHA-256
  `8cb6cd31304b03450982fe63b5ded14af578a26f1be74634ea15270c51569c07`.
- Runner transport contract: `practice-guide-runner/0.1.0`.
- Runner source:
  `src/asd_kontur/practice_guidance/qwen_session_runner.py`, SHA-256
  `117ebf56cf5d0d657ca38e0954c163c165bfff8384c94b848a209613421e403d`.
- Prompt-builder source: `src/asd_kontur/practice_guidance/pipeline.py`, SHA-256
  `058675c7bcba251a08ba0d10d44c73354d9d123843edc53ae5483e56182e25fb`.

## Paused process

The actual batch process was PID `66275`, launched from
`/Users/oleg/asd-kontur-rebaseline` with:

```text
/Users/oleg/mlx/runtime/.venv/bin/python src/asd_kontur/practice_guidance/qwen_session_runner.py --model /Users/oleg/mlx/models/Qwen3.8-27B-MLX-8bit --request /Users/oleg/asd-kg-id-practice-guide.tABE4W/full-pass-a-jobs.json --receipts /Users/oleg/asd-kg-id-practice-guide.tABE4W/full-pass-a-receipts.jsonl --max-tokens 3500 --max-battery-celsius 45
```

It was stopped with `SIGINT`, not `SIGKILL`. PID `66275` no longer exists, and no
`qwen_session_runner.py`/`full-pass-a-jobs` process remains. The final atomic receipt
for page 54 is present and parses successfully, so the durable observed checkpoint is
54 completed page jobs, not 53. Stdout/stderr existed only in Codex unified-exec
session `76073`; no persistent log file was configured. The JSONL receipt ledger is
the durable checkpoint and execution-result record.

An unrelated long-lived `mlx_vlm.server` process exists on the machine. It was not the
KG-ID-01 batch process and must not be treated as its checkpoint, stopped, or reused
without a separate authorization and identity check.

## Durable artifacts and progress

| Artifact | Path | SHA-256 / evidence |
|---|---|---|
| source provenance | `/Users/oleg/asd-kg-id-practice-guide.tABE4W/source-provenance.json` | `f3d06f6c6304ca58fe7ae5fe67acf3295d891ad116c3aa873d55a1bb51445972` |
| page manifest | `/Users/oleg/asd-kg-id-practice-guide.tABE4W/page-manifest.json` | `6907988b0c04bdb255a4a08b7f75b63fcdd8d7107cea6cf4bc33c930bd21f5f6` |
| superseded Pass A v0.1 jobs | `/Users/oleg/asd-kg-id-practice-guide.tABE4W/full-pass-a-jobs.json` | `a9f807b03a1965ec3aade712ab36c872548ea65284808dfde489949ed0f52a8e` |
| superseded Pass A v0.1 checkpoint/results | `/Users/oleg/asd-kg-id-practice-guide.tABE4W/full-pass-a-receipts.jsonl` | `36d50f21e227df5bc0ccd11865302c0d249acf86ca948129b43870397c88958c` |
| Pass A v0.2 qualification jobs | `/Users/oleg/asd-kg-id-practice-guide.tABE4W/qualification-pass-a-v0.2-jobs.json` | `52b99a69feb585d2f0f8512c8fbba008c1038e7e21af3f93da7fe910c9befb4d` |
| Pass A v0.2 full jobs | `/Users/oleg/asd-kg-id-practice-guide.tABE4W/full-pass-a-v0.2-jobs.json` | `1da1e8c4c9413e85be932588c74eb69537b81d94c866c259bc21c82b9e5afcbd` |
| prior development qualification decision | `/Users/oleg/asd-kg-id-practice-guide.tABE4W/qualification-decision-v0.2.json` | `8be1aa1b0e57dd02c7026e8c050df58e59be6714d8987580780b781c5ebf12ac` |
| batched Pass B qualification input | `/Users/oleg/asd-kg-id-practice-guide.tABE4W/qualification-pass-b-batched-jobs.json` | `6be512cf56c0b08e0400949367a1d217bcd7b8c693d203ee8dad51885674bffd` |
| rendered pages | `/Users/oleg/asd-kg-id-practice-guide.tABE4W/full-renders/` | 425 PNG files; aggregate SHA-256 of the sorted per-file SHA-256 listing: `0fcbf2560f834d1ce9bf496035c2c74684137b7858ea91c2b62053af4e7259ba` |

The page manifest reconciles 425 pages: 422 mixed, one raster-image, one native-text,
one blank/technical; 424 require rendering and eight have non-zero rotation.

The superseded v0.1 checkpoint has 54 unique completed jobs for pages 1 through 54;
all 54 receipt envelopes and embedded response JSON objects are readable. It has 371
pages not attempted. However, v0.1 used a prompt that allowed English semantic fields
for a Russian source. This produced a measured deterministic native-text grounding
defect. Preserve these 54 receipts as immutable evidence of a superseded attempt; do
not append to them or publish their candidates as the final run.

The corrected v0.2 prompt requires Russian semantic fields and preserves Russian
source terminology for deterministic grounding. Its job manifests contain 7/7
qualification jobs and 425/425 full-run jobs. No v0.2 Qwen receipt exists yet, so the
authoritative corrected run has 0 completed and 425 remaining.

## Exact resumption commands

Do not resume the superseded v0.1 ledger. The next action is the corrected v0.2
stratified qualification, using a new receipt ledger:

```sh
cd /Users/oleg/asd-kontur-rebaseline && /Users/oleg/mlx/runtime/.venv/bin/python src/asd_kontur/practice_guidance/qwen_session_runner.py --model /Users/oleg/mlx/models/Qwen3.8-27B-MLX-8bit --request /Users/oleg/asd-kg-id-practice-guide.tABE4W/qualification-pass-a-v0.2-jobs.json --receipts /Users/oleg/asd-kg-id-practice-guide.tABE4W/qualification-pass-a-v0.2-receipts.jsonl --max-tokens 3500 --max-battery-celsius 45 --max-job-seconds 900 --lock-file /Users/oleg/asd-kg-id-practice-guide.tABE4W/qwen-heavy-session.lock
```

Only after that exact profile has passed the qualification/evaluation gate, the full
corrected Pass A command is:

```sh
cd /Users/oleg/asd-kontur-rebaseline && /Users/oleg/mlx/runtime/.venv/bin/python src/asd_kontur/practice_guidance/qwen_session_runner.py --model /Users/oleg/mlx/models/Qwen3.8-27B-MLX-8bit --request /Users/oleg/asd-kg-id-practice-guide.tABE4W/full-pass-a-v0.2-jobs.json --receipts /Users/oleg/asd-kg-id-practice-guide.tABE4W/full-pass-a-v0.2-receipts.jsonl --max-tokens 3500 --max-battery-celsius 45 --max-job-seconds 900 --lock-file /Users/oleg/asd-kg-id-practice-guide.tABE4W/qwen-heavy-session.lock
```

The runner loads the model once, processes sequentially, appends one atomic JSONL
receipt per completed job, and skips job IDs already present in the selected receipt
ledger. Do not point the v0.2 command at `full-pass-a-receipts.jsonl`.

## Errors, uncertainty, and non-repeat instructions

- Do not repeat the remote source acquisition: verified remote/staged provenance already
  exists. Do not use the differing `MAC_ASD/library/sources` candidate.
- Do not resume or overwrite the v0.1 checkpoint; it is a superseded immutable attempt.
- Do not claim the prior v0.1 qualification for the changed Pass A v0.2 prompt tuple.
- Do not start the full 425-page v0.2 run until the exact v0.2 profile passes its
  stratified qualification and deterministic validation.
- Do not start two heavy Metal sessions. Check the exclusive lock and unrelated MLX
  server identity before starting.
- Do not treat a model response, strict JSON, confidence, or agreement between passes
  as acceptance. Each result remains a candidate until deterministic validation,
  independent Pass B verification, reconciliation, and authorized publication.
- Do not declare `ok_empty`, lose pages, or call a partial result complete. Exactly 425
  page terminal receipts must reconcile.
- Do not repeat successful page jobs within the same prompt/profile version unless a
  typed repair or version change requires it.
- The old development qualification was not production qualification. Production
  local-model qualification remains blocked pending the approved corpus and gates.
- No database publication, final reconciliation, or fresh-session Knowledge Gateway
  memory acceptance has been completed.

## Invariants

- Every candidate and later guidance unit retains exact SourceVersion plus one-based
  page and region/chunk locator provenance.
- Qwen produces candidates only. It cannot create WorkspaceFactVersion, approve a
  RuleVersion, activate a rule, resolve a conflict, or confirm NTD.
- `MethodologicalPracticeGuide` guidance stays distinct from NTD and project facts.
- 4-bit profiles, cloud/external providers, Docker, silent fallback, direct model SQL,
  and publishing the PDF, page images, full extracted text, or raw prompts/responses to
  Git are forbidden.
- Platform guidance may be published only after the two-pass and human authority gates;
  it must survive workspace reset without creating live workspace links.

## Safe verification performed for this handoff

- PID `66275` and the KG-ID-01 runner command are absent from the process table.
- All top-level staging `.json` files and every line of every top-level `.jsonl` file
  parse successfully.
- All 54 embedded v0.1 response JSON objects parse successfully and identify exact pages
  1 through 54.
- The corrected full manifest has exactly 425 unique jobs, all with prompt
  `kg-id-guide-pass-a-v0.2.0` and the Russian-grounding instruction.
- The PDF, source provenance, page manifest, profiles, jobs, receipts, qualification
  artifacts, runner, prompt source, and schema listed above exist and were hashed.
- No Qwen inference, database operation, dependency change, cleanup, commit, or cache
  mutation was performed during handoff preparation.
