# OZERO Tender delivery — current checkpoint

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

Pushed but un-deployed commits `c460131` and `e4b2083` add profile v14 and an additive
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
