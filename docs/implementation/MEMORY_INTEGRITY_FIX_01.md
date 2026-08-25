# MEMORY-INTEGRITY-FIX-01

Status: `IN PROGRESS`  
Owner: Олег Щербаков  
Date: 2026-08-26  
ProductReady: `false`

This bounded correction supersedes the semantic decision of
SYSTEM-INTEGRITY-CYCLE-01 without deleting its three physical-reproducibility
cycles. The immutable decision is
`docs/verification/MEMORY_INTEGRITY_SUPERSEDING_DECISION_01.json`.

## Corrected canonical model

`PracticeIntelligenceIdentity` is computed from guide identity, typed kind,
canonical subject/predicate/object, unit/dimension, modality, applicability,
qualifiers, exclusions and authority layer. It excludes CoverageManifest,
construction/release identity, evidence occurrence UUIDs, timestamps and input
order. `PracticeIntelligenceVersion` pins the exact guide edition, construction
profile and canonical payload. Each occurrence is retained as an immutable
`PracticeIntelligenceEvidenceLink`; releases only select exact versions.

The eight proven duplicate groups (NRS 240/241, form QR 308/322, two page-309
candidates and form QR 357/396, each in two typed kinds) are regression fixtures.
The construction validator computes the denominator; it does not hard-code
`7113 - 8`.

## Integrity semantics

Contract Pack v2.0 names identities, version rows, active release membership,
history, logical gaps, gap snapshots, conflicts and quarantined candidates
separately. The fingerprint implementation validates actual
`context_assembly_policies` and `practice_intelligence_releases` relations and
fails closed if required schema, release selection, edition selection, policy or
projection binding is absent.

Three fingerprints are independent:

1. all-history platform memory;
2. selected active-release semantics and evidence;
3. active ContextPack release/edition/policy/projection binding.

`READY_FOR_INTEGRITY_CYCLE` is not production readiness. With zero
`RuleVersion`, Rule Registry infrastructure is present but operational rule
coverage is absent.

## Qualification gate

Focused migration, deduplication, release, Gateway, durability and security
checks precede a fresh BF16 acceptance. Because canonical memory and fingerprint
scope changed, completion requires a new series of three consecutive clean-room
cycles C1–C3. Any failure resets that series. Historical KG-ID acceptance remains
24/25 systemic and 7/7 adversarial unless a genuinely new run reaches 25/25 and
7/7; expected answers and thresholds are not weakened.
