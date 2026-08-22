# АСД-КОНТУР — G-06 Workspace Lifecycle Foundation v0.1

- **Статус:** `Implementation complete; G-06 candidate PASS pending canonical PostgreSQL 18 CI`
- **Владелец:** Олег Щербаков
- **Дата:** 2026-08-23
- **Gate:** `G-06 Workspace Lifecycle Foundation`
- **Work package:** `WP-08`
- **Основание:** прямое разрешение владельца на реализацию G-06 и принятые
  `RD-01…RD-05`, ADR-0001…ADR-0010, LDM, Contract Pack и G-04/G-05.

## 1. Назначение и граница

G-06 реализует единый управляемый lifecycle workspace ОКС для `Tender`,
`Support`, `Audit` и `Restoration`. Реализация не содержит режимных workflows,
не формирует продуктовые результаты и не объявляет `ProductReady`.

Доказательная область ограничена synthetic data, disposable PostgreSQL и
явными временными/test storage adapters. Реальные S3/VPS, backup/PITR,
production credentials, production retention/basis/authority instances и
документы ОКС не использовались.

## 2. Реализованный автомат

```text
PROVISIONING → ACTIVE
ACTIVE → FREEZING → FROZEN
FROZEN → FINALIZING → FINALIZED
FINALIZED → EXPORTING → EXPORTED
EXPORTED → ARCHIVING → ARCHIVED → CLOSED
CLOSED → REOPENING → ACTIVE
CLOSED → RESET_PLANNING → RESET_AUTHORIZED
RESET_AUTHORIZED → PURGING → VERIFYING_RESET → RESET_VERIFIED
RESET_VERIFIED → DESTROYING → DESTROYED

RECOVERY_REQUIRED ↔ controlled retry/quarantine
QUARANTINED → authorized recovery only
LEGAL_HOLD = overlay, not a replacement state
```

`LifecycleStateMachine` declares the transition graph and per-target capability.
PostgreSQL independently enforces the same graph in
`workspace.transition_lifecycle`. Unknown transitions, stale
`expected_version`, missing evidence and legal hold fail before state mutation.

Each accepted transition atomically creates:

- a new `lifecycle_version`;
- immutable `lifecycle_transition_history`;
- a content-minimal domain event in transactional outbox;
- an idempotent command outcome.

A duplicate operation key with the same digest returns the original outcome;
the same key with different semantics is an idempotency conflict.

## 3. Physical model

Migration `0003_g06_workspace_lifecycle` follows `0001_g04 → 0002_g05` and
adds only forward G-06 structures.

### 3.1 Platform policy registries

| Relation | Purpose | Mutability |
|---|---|---|
| `platform.retention_profile_versions` | Exact RetentionProfile, environment, completeness and approval state | Immutable |
| `platform.basis_registry_versions` | Versioned basis code and evidence | Immutable |
| `platform.storage_adapter_registry_versions` | Exact adapter-registry release | Immutable |
| `platform.storage_adapter_registry_entries` | Required capabilities and health per adapter | Immutable |

Synthetic `development` profiles may be complete for disposable tests. They
cannot produce a production assurance claim. Unknown/incomplete production
values remain fail-closed.

### 3.2 Workspace canonical/history relations

| Family | Relations |
|---|---|
| Aggregate | extended `workspace.workspaces`; `workspace_revisions`; `mode_executions` |
| Transition | `lifecycle_commands`; append-only `lifecycle_transition_history` |
| Freeze/finalize | `freeze_manifests`; `finalization_reports` |
| Export/archive | `export_operations/items`; `archive_packages/items/verifications/imports` |
| Authority/hold | `legal_holds`; `deletion_plans`; immutable `destructive_authorizations` and append-only invalidations |
| Execution/recovery | `adapter_receipts`; `recovery_checkpoints`; `residual_verifications` |
| Surviving evidence | `destruction_attestations` with content-free payload |

Every relation is composite-scoped by `(organization_id, workspace_id)` and
references the same workspace. There is no nullable universal `scope_id`.
Workspace relations have RLS and `FORCE RLS`; lifecycle, verifier and
destruction roles receive separate minimum privileges.

## 4. Roles and guards

| Role | Allowed purpose | Explicitly not allowed |
|---|---|---|
| `asd_app` | Normal scoped workspace operations while writable | Direct lifecycle-state mutation; destructive execution |
| `asd_lifecycle_service` | Exact transition function and lifecycle evidence writes | Arbitrary platform writes; destructive storage delete |
| `asd_destruction_executor` | Delete exact allowlisted scoped relation/adaptor items | Authorization, platform writes, schema drop/truncate |
| `asd_lifecycle_verifier` | Read scoped plans/receipts/scans and verify | Execute purge or mutate evidence |

Direct `UPDATE lifecycle_state` by the application role is denied. Material
tables have a DB trigger that admits writes only in `PROVISIONING`/`ACTIVE`,
except the restricted deletion identity executing an authorized plan. Thus a
late job/retry cannot write after `FREEZING`.

## 5. Provisioning and ModeExecution

`ProvisioningGuard` requires exact policy/authority references and a complete
RetentionProfile. A production profile without approved values is rejected;
the complete test profile is explicitly `development`.

All four modes use one `ModeExecutionConfiguration` and one workspace
lifecycle. Each mode pins exact ProcessDefinition, RuleSet, policy, authority,
input contract and output contract versions. Multiple executions are allowed
only with unique identities and the shared composite workspace scope. A
terminal ModeExecution status never sets `ProductReady`.

## 6. Freeze and finalization

Freeze is two-phase:

1. `ACTIVE → FREEZING` establishes the DB write fence;
2. a verified immutable `FreezeManifest` proves zero writers and accounts for
   active/cancelled/checkpointed jobs;
3. only then may `FREEZING → FROZEN` commit.

`FinalizationGuard` requires complete retention policy and terminal governed
mode statuses. `FinalizationReport` records blockers and uncertainties and
hard-codes `production_ready_claim=false`. The lifecycle transition to
`FINALIZED` requires a verified report; it does not assert professional or
product result readiness.

## 7. Export and portable archive

`PortableArchiveService` produces a deterministic, traversal-safe ZIP with:

- canonical JSON manifest;
- exact logical paths and source-version references;
- SHA-256 and size for each object;
- exact contract/policy/RuleSet versions;
- `new_workspace_only` import semantics.

Verification rejects missing, extra, duplicate, changed, unreadable or unsafe
items. Staging alone is not success. A verified archive is sealed read-only.
The PostgreSQL transition to `ARCHIVED` requires both a verified package and a
verified readability/integrity receipt.

Portable archive and recovery backup remain separate adapter classes. A
successful synthetic backup receipt cannot satisfy the archive guard.

## 8. Reopen and verified import

Reopen is allowed only from `CLOSED`, before any purge, with policy authority.
`REOPENING → ACTIVE` creates a new immutable WorkspaceRevision while preserving
the frozen/finalized history.

`ArchiveImportGuard` is not reopen. It requires exact archive verification,
schema compatibility and fresh authority, and always creates a different
workspace UUID and revision 1. It carries no old authorization, project index,
embedding or graph projection; imported Candidates require confirmation under
the new workspace policies. Destroyed or corrupt archives are rejected or
quarantined.

## 9. Storage Adapter Registry

The provider-neutral registry records adapter key/version, storage/data plane,
scope, required flag, inventory/purge/residue/destroy capabilities, receipt
schema and health. `verified` is impossible when a required adapter is absent,
unavailable or unable to scan residues.

The acceptance registry covers:

1. PostgreSQL workspace relations;
2. workspace object store;
3. project FTS;
4. project vector projection;
5. project typed graph projection;
6. cache;
7. inbox;
8. outbox;
9. idempotency ledger;
10. jobs;
11. checkpoints;
12. process/events;
13. audit;
14. staging/temp;
15. portable archive;
16. recovery backup/snapshot;
17. external/provider residue placeholder.

Only the PostgreSQL and local filesystem behaviours are real local adapters;
the remaining adapters are explicit deterministic test doubles. No external
system is silently treated as empty.

`ContainedFilesystemAdapter` requires a pre-existing explicit test root,
rejects broad roots, absolute/traversal paths and symlink escape, and deletes
only manifest-listed regular files. It never recursively deletes a directory.

## 10. DeletionPlan and dual authorization

`DeletionPlan` is immutable and RFC 8785/SHA-256 fingerprinted. It pins:

- organization/workspace and lifecycle revision/version;
- exact RetentionProfile and Basis Registry versions/code/evidence;
- fresh hold check and expiry;
- full adapter registry and inventory digest;
- exact adapter items and expected residue classes;
- requester and completed dry-run.

Authorization re-inventories the workspace and rejects changed inventory,
expired basis/authority, missing evidence, legal hold or incomplete policy.
Requester, human confirmer, service executor and independent human verifier
must be four distinct identities. A fresh plan/inventory/hold check is required
before destructive execution.

## 11. Purge, recovery and quarantine

`DestructionCoordinator` executes only immutable plan items. Each adapter/item
has a stable operation key and receipt with before/after count and one of:
`deleted`, `already_absent`, `failed`, `incomplete`, `residue_detected`.

There is no `DROP`, `TRUNCATE`, whole-schema reset, digest-only delete, path
glob or heuristic graph traversal. The PostgreSQL adapter has a compile-time
allowlist of composite-scoped relation slices. Partial adapter failure produces
an incomplete result and creates an immutable checkpoint bound to the exact
plan/operation; it never becomes verified success.

`RECOVERY_REQUIRED` permits only retry of the same plan, explicit compensation
or a superseding plan after re-inventory. `QUARANTINED` is used for foreign
workspace residue, unknown ownership, archive mismatch or adapter-contract
violation and blocks ordinary retrieval/import/promotion/purge continuation.

## 12. Residual verification

Every required adapter is scanned read-only using applicable methods:
workspace UUID, composite scope, known IDs, known digests and known fragments.
The test adapters additionally represent negative FTS/vector/graph/cache/job
lookups. Empty/stale/unavailable is not interpreted as a clean result.

The real PostgreSQL A/B test and complete synthetic adapter matrix prove:

- scoped operational rows and each planned adapter item for A are removed;
- B retains its rows and all adapter items and cannot see A through RLS;
- exact archive/backup residues for A survive reset only when explicitly
  retained by the pinned profile and remain destroy targets;
- a delayed write after freeze is rejected;
- direct state update is rejected for both application and lifecycle roles;
- quarantined material is hidden from ordinary application retrieval;
- platform integrity fingerprint is unchanged before/after reset.

The second scoped purge/checkpoint removes lifecycle outbox records created
between purge start and residual verification; at-least-once semantics remain
bounded by operation/idempotency keys. No full event replay is used.

## 13. DestructionAttestation

The v0.1 lifecycle schema could not express G-06 assurance class or the
`quarantined` outcome. It was not mutated. A narrow immutable major release was
added at `contracts/v1.0/` for
`lifecycle.destruction-attestation@1.0.0`, superseding only the v0.1
attestation contract.

The attestation includes exact plan/policy/basis/adapter versions, independent
identities, receipt/scan IDs, aggregate counts, residue classes, platform
integrity result, timestamp, assurance class and outcome. JSON Schema rejects
unknown fields. The database additionally rejects a production claim using
contract v0.1 and rejects verified status with forbidden residues or changed
platform memory; exact retained residue classes remain explicit.

After reset the allowlist contains only workspace UUID, decision/operation
codes, authority identities, timestamps, aggregate counts, adapter/scan status
and attestation identity. Filenames, project text/fragments/hashes, payloads,
prompts/responses, embeddings, graph content and human-readable ОКС identifiers
are forbidden.

`development/disposable=verified` is evidence only for this test foundation;
it is not a production DestructionAttestation.

## 14. Legal hold and destroy

Legal hold is a versioned overlay with basis/evidence, authority, effective
interval, suspended state and release decision. Placement atomically sets the
workspace hold flag and appends authorization invalidation records without
mutating immutable authorizations.
Destructive transitions then fail closed. Release never resumes an old plan;
fresh inventory, plan and authorization are required.

Destroy reuses a separate immutable plan with `operation_kind=destroy`, a
fresh hold/retention check and new authorization. It targets retained archive,
backup/snapshot and external-residue adapters. `DESTROYED` requires a verified
destroy attestation. Platform NTD, rules, published Evidence Capsules and
platform audit are outside both reset and destroy plans.

Production retention triggers, archive stores, backup/PITR and provider
residue APIs remain blocked policy/adapter instances.

## 15. Migration and rollback

- clean install: `0001_g04 → 0002_g05 → 0003_g06`;
- accepted prior migrations are not rewritten;
- migration has no network or mutable production-policy dependency;
- production destructive downgrade fails unless
  `ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1`;
- the override is tested only in a disposable database;
- production rollback is forward repair or verified restore, never automatic
  destructive downgrade.

## 16. Legacy preserve / modernize / reject

| Legacy evidence | Decision | G-06 result |
|---|---|---|
| `lifecycle/completion.py` write guard | Preserve principle | DB write fence + exact state/version guard |
| `lifecycle/reset.py` dry-run, explicit confirmation, restricted role | Preserve/modernize | immutable plan, four-way authority separation, scoped adapters |
| `lifecycle/reset.py` whole-schema `TRUNCATE … CASCADE` | Reject | no drop/truncate/cascade reset |
| archive manifest/hash/readability checks | Preserve principle | deterministic ZIP, exact inventory, no extras, hash/readability receipt |
| legacy archive paths/metadata | Reject as contract | object-agnostic logical paths and new-workspace import |
| `project_lifecycle.py` best-effort exception suppression | Reject | typed incomplete/recovery/quarantine outcomes |
| local object layout | Modernize | provider-neutral exact-item adapter with containment/symlink guard |

No legacy code was copied.

## 17. Test evidence

Local evidence on 2026-08-23:

| Check | Result |
|---|---|
| Python / PostgreSQL | Python 3.12; disposable PostgreSQL 17.10; pgvector 0.8.6 |
| Full pytest with real PostgreSQL | `98 passed` |
| Lifecycle unit/contract tests | state graph, reset/destroy authority gates, archive, adapters, v1 schema |
| G-06 PostgreSQL tests | roles/RLS, transitions/outbox, direct-update denial, freeze fence, A/B purge, fresh-scope import, versioned legal hold/release, full reset, downgrade/upgrade |
| Migration | clean head and disposable `0003→0002→0003` pass |
| Ruff / mypy | format and lint clean; strict mypy clean for 34 source files |
| PostgreSQL 18 + pgvector canonical CI | pending; required before final `G-06=PASS` |

Test counts are inventory, not readiness evidence. The material evidence is the
behavioural isolation, failure and attestation assertions above.

## 18. Production blockers

The following remain `BLOCKED` and are not masked by G-06:

- G-02B production RetentionProfile and Basis Registry values;
- production authority/qualification assignments;
- real S3/VPS/object/archive/backup/provider adapters and residue receipts;
- backup/PITR/WAL/snapshot deletion evidence;
- production assurance signing/keys;
- external custody and provider retention/deletion terms;
- real restore/failover drills;
- all four mode/result E2E acceptance suites.

## 19. Gate self-check

| Criterion | Evidence | State |
|---|---|---|
| Provisioning / ModeExecution | shared guards and exact version fields | PASS local |
| Freeze/finalize | DB fence + immutable manifests/reports | PASS local |
| Export/archive | deterministic package + transition guards | PASS local |
| Reopen/import | new revision/new workspace fail-closed guards | PASS local |
| Plan/authorization | immutable fingerprint + four identities + hold | PASS local |
| Purge/reset/destroy foundation | scoped adapters, receipts, attestations | PASS local |
| Recovery/quarantine | explicit states/checkpoints/outcomes | PASS local |
| Full adapter inventory | 17 synthetic/disposable classes | PASS local |
| A/B isolation | real non-owner PostgreSQL test | PASS local |
| Platform survives reset | before/after integrity assertion | PASS local |
| PostgreSQL 18 canonical CI | required workflow run | PENDING |

Until the canonical PostgreSQL 18 workflow is green, overall gate state is
`candidate PASS / IN_PROGRESS`. After that evidence is recorded and status
documents are synchronized, `G-06=PASS` means only an accepted synthetic
foundation, not production destruction readiness or product readiness.
