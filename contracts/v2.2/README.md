# Contract Pack v2.2 — Memory Integrity Fix

This additive pack defines the evidence-bound Practice Intelligence identity, explicit release
activation, fail-closed platform-memory fingerprint scope, unambiguous counters, and the canonical
post-Spine capability current state. It preserves all earlier packs and historical releases.

The semantic identity includes the exact PracticeGuideEdition, SourceVersion, page/region locator,
fragment digest, typed meaning, applicability, modality, units, exclusions, and authority layer.
Candidate, build, release, runtime, and processing-order identities are excluded. Default retrieval
uses only the explicitly activated release; historical releases require an exact pin.

`READY_FOR_INTEGRITY_CYCLE` means participation in the integrity harness, not production readiness.
The empty Rule Registry remains `infrastructure_ready=true` and
`operational_rule_coverage=false`. ProductApplicationReady remains `PARTIAL`; TrialReady,
OKSReady, and ProductReady remain false.
