# OZERO Tender delivery — current checkpoint

## 2026-09-11 19:12 UTC+12 — profile-scoped release live; complete corpus pass active

The controlled OZERO release is now pinned to `e28da91a57879602f727faedf74acbd9e8fe7adb`
for API, document worker, and assistant worker. The API readiness route is `ready` at
database head `0047_profile_scoped_engineering_candidates`. The exact pre-0047
database backup was successfully created and verified in the restricted operational
store before the additive migration; its path and digest are deliberately not copied
into Git.

The POS source version `01a088ac-81c2-7033-8f75-8160ffeb2cb2` completed its original
v15 run as durable historical evidence: 443 accepted batches cover its complete
5,252-fragment manifest. Five rejected attempts cover 60 attempt fragments, with
accepted bounded recovery children present in the same immutable ledger. The old
worker wrote a complete generic persistence stage and source-backed candidates
(299 fields, 494 structural nodes, 148 raw relationship observations, 478 work
candidates, 94 quantities, and 45 materials). These are candidates under the old
profile, not reconciled facilities, Tender facts, or an exhaustive pit inventory.

The live profile-aware `start_project_understanding` command has scheduled one
version-aware semantic successor for each of the 22 active source versions plus one
workspace reconciliation job. It neither re-runs OCR nor mutates historical attempts.
POS successor `01a08f4e-3b70-76ff-8245-15626d8da266` is queued with explicit v15
semantic and candidate-persistence provenance and will reuse compatible POS batches.
The single supervised document worker is currently processing
`Раздел ПД №12.5 005.2-2025-СМ5_ПИР_pdf.pdf`; 21 successors remain queued. This is
full-package processing in progress, not semantic coverage completion or Tender
acceptance.

The frontend artifact from `de98eaf4f1f535692c6af7d7c712767aa65fdae0` is also live
with the compatible e28 API: the Russian structural-candidate panel now supports a
name/kind search and incremental display of every returned structure and relationship
candidate. It no longer silently stops after 200 rows. This makes partial evidence
inspectable; it does not reconcile aliases or convert candidates into confirmed facts.

Updated: 2026-09-11 16:41 UTC+12

The live API is pinned to `8e0c2f5c68ff2c36a4b428dba9e8ec70b18338da`, the scoped
document worker to `18c6893fdbee5186b351bdddaab2920c8f7eda3d`, and the assistant
worker to `a9a693a854f4dd4120de6e8f16451923d82fe4ab`, all at database migration
`0045_bounded_dep_recovery`. The API readiness check reports PostgreSQL reachable.

PZU (source version `01a088ac-8125-7031-8659-a57bd97ff1c6`, 56 pages) reached its
entire v12 semantic input denominator: 5,021 accepted fragment inputs. Five rejected
model attempts remain immutable historical attempts. Their bounded recovery children
are the accepted evidence; this is not a claim that every engineering interpretation is
complete or confirmed.

The current project view is partial. It exposes source-backed candidate collections and
coverage separately from reconciled facts. Workspace totals at this checkpoint are 109
field candidates, 429 work candidates, 121 quantity candidates, 41 material candidates,
188 structural candidates, and five excavation-pit candidates. Those pit candidates are
not an established count: cross-document identity, revision, and coverage reconciliation
are still required.

KR1 (source version `01a088ac-8084-7c59-8b1a-c9bda7ad8208`) is the active next
structural source. Its sole replacement job is `01a08eac-9094-73c6-b936-3ca9bc2a0044`.
It has accepted 2,442 of its 2,960 deterministic semantic fragment inputs at this
snapshot. One immutable failed child receipt covers 12 inputs and remains a visible
unresolved model attempt; it is not relabelled as success. Do not create another
replacement while that job runs.

The semantic coverage query now enumerates all active sources rather than only sources
which already have accepted batches: 22 active documents, 1 complete, 2 partial, and
19 not started. KR2 has exactly one queued successor
`01a08ec5-b223-7f78-8c1c-893ca2bb8eff`, which will follow KR1 without concurrent heavy
Qwen execution.

Pushed but un-deployed commits `c460131`, `e4b2083`, `742357b`, `a36ee21`, and `e1c3908` add profile v15 and an additive
relationship-candidate ledger. The ledger retains evidence-bound raw endpoints and does
not perform a name-only facility merge. Its migration is
`0046_structure_relationship_candidates`; release waits for the active v13 job to
become terminal.

KR1 v13 has now completed its 2,960 accepted fragment-input denominator. The immutable
failed child receipt remains separate. Its accepted candidate evidence has reached the
partial live project view: 231 field candidates, 486 work candidates, 142 quantity
candidates, 68 material candidates and 274 structure candidates across the workspace.
Examples visible through source links include KNS observations in IOS1 pages 10, 12–13,
and 52. They are not yet reconciled facility dossiers, nor evidence of an exhaustive KNS
or excavation inventory.

Next active work: materialize KR1 through the durable dependency chain; then run KR2
and POS. Assemble facility/area relationships, complete the source manifest, perform
cross-document Tender reconciliation and normative evaluation, and verify the project
consultant through the user-facing application.

## 2026-09-11 17:11 UTC+12 — current correction and release gate

KR1 and KR2 are no longer active: their v13 semantic manifests have respectively
accepted 2,960/2,960 and 1,525/1,525 fragment inputs. Failed input counts (12 and
24) are immutable historical attempt records; they do not reduce accepted coverage.
The source-scoped KR2 downstream chain completed. Package completion, facility
reconciliation, and Tender acceptance remain open.

The one permitted POS replacement failed immediately as
`structured_extraction_evidence_unavailable`. Its receipt demonstrated that the
deployed worker gates Qwen semantic extraction on deterministic role decisions.
Commit `ce9cd3b` removes that incorrect gate for evidence-bearing native elements
and retains Qwen relationship candidates; it is fully qualified but **not
deployed**.

Deployment is blocked solely by the required current full-backup gate. The existing
application role can access scoped OZERO records but `pg_dump` fails on a platform
table permission check. No migration, service reload, or source mutation was made.
The next active work is locating the already-authorized full-backup/migration path;
then deploy exact `ce9cd3b` with additive migration 0046 and retry only the POS
failure lineage.

## 2026-09-11 18:23 UTC+12 — profile-isolation release prepared

The active POS v15 semantic job remains `running` under the existing pinned worker;
at this observation it had 308 accepted durable batch receipts (3,672 fragment inputs)
and two immutable failed parent receipts whose recovery children are accepted. It has
not yet reached candidate persistence, project materialization, or Tender acceptance.

Release candidate `c29e8e3` (including
`b0b80a8275519e569b0faf38ffa1f6e50a359a24`) is pushed but **not deployed**.
It adds additive migration `0047_profile_scoped_engineering_candidates` and keeps
Qwen engineering observations, structural nodes, relationships, and extraction defects
scoped to the exact semantic profile that produced them. The active project view and
reconciliation will select only the completed profile for each active source; legacy
generic candidates remain immutable historical evidence rather than being mixed into a
newer Qwen pass. A profile-aware successor can reuse compatible accepted v15 manifests
to persist the corrected candidate identities without rerunning OCR or duplicating Qwen
inference.

Focused unit, PostgreSQL integration, format, lint, and strict type checks passed for
this release. A job is reusable only when its exact profile provenance and immutable
`PROJECT_DEFINITION_EXTRACTION` stage receipt both exist; a terminal state alone cannot
silently suppress recovery. Activation waits for the current POS worker job to become terminal so its
accepted batches and lease are preserved. The next executable action is to verify that
terminal receipt, apply the additive migration through the existing recoverable release
procedure, and schedule the profile-aware persistence successor exactly once.
