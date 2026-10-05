# OZERO pre-deletion inventory

Observed at `2026-09-29T03:03:22.624793Z` (`2026-09-29 15:03:22 +12`). This is the required inventory before the owner-authorized workspace reset. It contains identifiers and counts only; no document bodies, credentials, or model prompts.

## Scope

- Workspace: `01a088aa-0491-7bdd-9127-8359fe927a27` (`ОЗЕРО`).
- Organization: `25b7d36d-7118-5d1e-8cf0-3d03ceed9f88`.
- Lifecycle at observation: `ACTIVE`, lifecycle version `2`, workspace revision `1`.
- The reset archive directory for this exact workspace did not exist before `prepare`; any new archive there is attributable to this reset.

## Workspace database inventory

- 60 non-empty workspace-scoped relations.
- 599,080 rows in the scoped inventory.
- 22 document records, 22 document/source versions, 2,529 pages, and 22 admitted source objects.
- 13,370 engineering extraction batches.
- 8,677 project-field observations, 8,427 structure-node versions, 365 structure identity candidates, and 29 pit disposition receipts.
- 7,379 work observations, 2,958 quantity observations, 1,086 material observations, and 34,786 work-package versions.
- 33 project-understanding reconciliations, 7 requirement-matrix versions, and 1 Tender pilot result.
- 23 assistant conversations, 62 turns, 113 messages, and 1,500 turn events.
- 26,966 durable jobs at the snapshot: 649 succeeded, 69 failed, 10 cancelled, 26,237 historical `reconciliation_required`, and one running bounded reconciliation job. The official prepare operation is responsible for fencing/cancelling any nonterminal job.

The exact per-relation counts are in `OZERO_PRE_DELETION_SNAPSHOT_2026-09-29.json`.

## Object and generated-file inventory

- Workspace object store: 2,414 exact objects, 250,064,393 bytes.
- Object manifest fingerprint: `sha256:ab332fc60a6521a99eab8148943cdb2e7e30e24e0d7c356aaec2278ef4e59130`.
- Existing lifecycle reset archives for this workspace before prepare: zero.
- OZERO-only runtime artifacts found outside the canonical object store include the `ozero-project-tender-v1` and `ozero-project-tender-v2` archive directories, OZERO Tender ZIP/DOCX/CSV files under dated `public-demo/acceptance` directories, and OZERO-labelled pre-operation database dumps. These are inventoried for post-destruction review only. No local file is removed before the workspace reaches verified `DESTROYED`.
- Generic release receipts, release directories, CI evidence, source code, migrations, templates, and mixed historical Git reports are excluded from deletion.

## Platform-memory safety baseline

- Lifecycle reset fingerprint: `sha256:02cb45f341ad56595bbe6ec59abe5fbadac7841914280b165ed99861923e8487`.
- Canonical NTD remediation fingerprint: `sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`.
- NTD worker ledger: 319 succeeded, zero queued/running/failed.
- Canonical NTD: 15 documents, 15 editions, 1,669 provision candidates, 1,669 semantic rows, 1,294 verified provision versions, 3,281 representation pages, 1,577 structural fragments, and 2,677 native chunks.
- Practice Intelligence: one guide/edition, 2,410 guidance units, 7,111 active intelligence units, and 1,644 active playbooks.
- Templates/catalog/rules: two template versions, 29 field definitions, 28 binding versions, one canonical work type/version, and two rule versions.
- Search/graph/embedding projection counts are currently zero and must remain zero; they must not be rebuilt as part of deletion.

The post-destruction check must reproduce the same lifecycle fingerprint, canonical NTD fingerprint, semantic fingerprints, NTD worker ledger, and critical platform counts exactly. Any unexpected delta is a data-integrity incident and stops subsequent artifact cleanup.

## Authorized deletion boundary

The only authorized database deletion path is the existing two-stage workspace lifecycle (`reset/prepare` followed by `reset/execute` using the returned challenge). Direct table deletion or truncation is prohibited. After verified destruction and platform-memory equality, only the newly created reset archive and clearly exclusive OZERO generated artifacts may be removed.
