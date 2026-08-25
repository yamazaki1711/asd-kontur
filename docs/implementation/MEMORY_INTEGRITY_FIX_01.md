# MEMORY-INTEGRITY-FIX-01

Status: `PASS — bounded platform-memory integrity`
Owner: Олег Щербаков
Date: 2026-08-26
ProductReady: `false`

This bounded correction supersedes the semantic decision of
SYSTEM-INTEGRITY-CYCLE-01 without deleting its three physical-reproducibility
cycles. The immutable decision is
`docs/verification/MEMORY_INTEGRITY_SUPERSEDING_DECISION_01.json`. Final
requalification is recorded by
`docs/verification/MEMORY_INTEGRITY_TERMINAL_DECISION_01.json`.

## Corrected canonical model

`PracticeIntelligenceIdentity` is computed from guide and exact edition, typed
kind, canonical subject/predicate/object, unit/dimension, modality,
applicability, qualifiers, exclusions, authority layer, SourceVersion, exact
page/region locator and source-fragment digest. It excludes CoverageManifest,
construction/release identity, Candidate/Guidance occurrence UUIDs, timestamps
and input order. `PracticeIntelligenceVersion` pins the construction profile and
canonical payload. Each occurrence is retained as an immutable
`PracticeIntelligenceEvidenceLink`; releases only select exact versions.

The read-only reconciliation disproved the earlier eight-group assumption. Six
equal-text pairs have different exact locators (pages 240/241, 308/322 and
357/396) and remain separate identities. Two page-309 groups have identical
edition, SourceVersion, locator, fragment and typed meaning; each converges to
one identity with two Candidate/Guidance evidence links. The validator computes
the denominator (`7,111` in the qualified snapshot); it does not hard-code a
subtraction.

## Integrity semantics

Contract Pack v2.2 names identities, version rows, active release membership,
history, logical gaps, gap snapshots, conflicts and quarantined candidates
separately. The fingerprint implementation validates actual
`context_assembly_policies` and `practice_intelligence_releases` relations and
fails closed if required schema, release selection, edition selection, policy or
projection binding is absent.

The all-history specification enumerates every canonical relation and selected
semantic column. It excludes workspace state, processing receipts, wall-clock
metadata and rebuildable projection rows. Projection schema/version binding is
included without projection contents. The qualification decision itself is
excluded from the root to avoid a self-referential fingerprint.

Three fingerprints are independent:

1. all-history platform memory;
2. selected active-release semantics and evidence;
3. active ContextPack release/edition/policy/projection binding.

`READY_FOR_INTEGRITY_CYCLE` is not production readiness. With zero
`RuleVersion`, Rule Registry infrastructure is present but operational rule
coverage is absent.

## Qualification gate

Focused migration, deduplication, release, Gateway, durability and security
checks preceded fresh BF16 acceptance. The full rerun produced 20/25 systemic
and 7/7 adversarial; task 12 remains an honest knowledge gap and four other
systemic responses failed exact identity/evidence validation. Thresholds and
expected answers were not weakened, so historical KG-ID remains PARTIAL.

The final official series is `MEMORY-INTEGRITY-FIX-01-R6`:

- C1, C2 and C3 are three consecutive clean-room PASS;
- active semantic duplicate groups: 0;
- missing fingerprint components: 0;
- all-history fingerprint:
  `sha256:d78a22e94a87fc32b885fb71a338e3416310b95f562246db045091fa1fbce132`;
- active-release fingerprint:
  `sha256:0006d0bd2d09ae4713a7ee9692b55d0afc0c9a830d018bc4e8c342e548de4fe4`;
- ContextPack binding fingerprint:
  `sha256:595a3ea9716bf772d05d7273b5c9ba1ae196bd036513dcce2779a0b8f3161a07`;
- each cycle fingerprint:
  `sha256:e79eb678116ac0fbddc1a1ce765bb401085ed70bf342d267c6a221a20eab4886`.

Additive migration `0020_knowledge_status` makes Platform Knowledge status
report the canonical 138 open conflicts and 53 quarantined candidate identities.
The UI/API derives MEMORY_DATA_DEFECT exclusively from the latest immutable
qualification: it is now false, while NTD and RuleVersion blockers remain.

Restarts before the final series: five. Three were failure resets (R1
environment-owned import, R2 whitespace, R4 order-dependent qualification
assertion); R3 and R5 were successful but were superseded after required
schema/Contract Pack truth-surface changes. All receipts remain outside Git.
ProductApplicationReady stays PARTIAL; TrialReady, OKSReady and ProductReady
remain false.
