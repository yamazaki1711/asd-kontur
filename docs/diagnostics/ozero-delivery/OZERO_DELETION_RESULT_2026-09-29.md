# OZERO controlled deletion result

Observed through `2026-09-29T03:33:04Z` (`2026-09-29 15:33:04 +12`). This report contains identifiers, counts, and fingerprints only. It contains no document bodies, credentials, model prompts, or extracted confidential text.

## Outcome

- Workspace `01a088aa-0491-7bdd-9127-8359fe927a27` reached `DESTROYED`, lifecycle version `20`.
- Terminal reset receipt: `01a0eb29-4998-75e8-bd93-71c832388b03`, outcome `verified`, completed `2026-09-29T15:15:46.712637+12:00`.
- The owner-authorized workspace list no longer contains OZERO, and scoped workspace access returns `workspace_not_found`.
- Active OZERO project data changed from 599,080 scoped database rows, 22 documents, 2,529 pages, 26,966 jobs, and 2,414 object-store items (250,064,393 bytes) to zero.
- The only remaining workspace-keyed item reported by the destruction adapter is a content-free `messaging.workspace_outbox` lifecycle notification written after destruction. It is control metadata, not active project content, and was not bypass-deleted.

## Job termination

- Requested job `01a0eae4-78ce-7dd6-bde4-d29ba6f00103` had already succeeded.
- Its final recorded successor `01a0eaec-ea33-7df3-9951-a238708d60cc` also succeeded before deletion; no successor was created by this cleanup.
- The lifecycle prepare fenced OZERO and cancelled the remaining active reconciliation work with `workspace_reset_fence`. No active OZERO jobs remain because the workspace job ledger was destroyed with the workspace.

## Platform knowledge integrity

The exact pre-deletion measurements were repeated after destruction:

- Lifecycle platform fingerprint remained `sha256:02cb45f341ad56595bbe6ec59abe5fbadac7841914280b165ed99861923e8487`.
- Canonical NTD root remained `sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`.
- All six recorded platform semantic fingerprints matched exactly.
- Every critical NTD, Practice Intelligence, rule, template, and catalog table count matched the pre-deletion snapshot; mismatch set was empty.
- NTD processing ledger remained exactly 319 `succeeded` jobs with no other state.
- The supervised NTD worker remained running as PID `98263`; the local Qwen server remained PID `36812` with `Qwen3.8-27B-MLX-8bit`.
- Knowledge Gateway inventory and NTD search both returned `ok` from a surviving authorized workspace; the bounded search returned three source results.

The detailed denominator and fingerprints are in `OZERO_PRE_DELETION_SNAPSHOT_2026-09-29.json` and `OZERO_POST_DELETION_VERIFICATION_2026-09-29.json`.

## Artifact cleanup

Only after `DESTROYED` and exact platform equality were established, the reset archive, OZERO Tender v1/v2 archives, dated OZERO acceptance DOCX/CSV/ZIP/preview files, and untracked OZERO handoff copies were removed from active ASD-KONTUR runtime/report roots. The filesystem operation moved the verified exclusive runtime artifacts to the macOS Trash, so they are absent from the active archive/output stores but remain recoverable until Trash is emptied.

Mixed database backups, generic release receipts, CI evidence, reusable source code, migrations, templates, and Git history were preserved.

## Defects found and corrected

The first purge attempt safely stopped after exposing two lifecycle defects:

1. Four newer workspace relations were missing from the immutable PostgreSQL purge order. They are now included before their referenced job/source parents.
2. Worker successor/refill paths could create jobs after a workspace was lifecycle-fenced. All relevant project scheduling/retry paths now check `ACTIVE` plus `write_fenced=false`, and a claimed job from a fenced workspace is cancelled before execution.

The failed attempt did not change platform knowledge. Recovery used the supported immutable checkpoint and lifecycle continuation, not direct table deletion.

## User-facing deletion

The project selector now offers `⋯ → Удалить проект`. The Russian confirmation dialog explains which project data will be removed, requires the displayed project name, calls the existing lifecycle prepare/execute endpoints, clears recent-project pointers, refreshes the project list, and never exposes challenge/reset/attestation terminology. The route-mocked Playwright browser suite verifies deletion, list removal, and preservation of another project.
