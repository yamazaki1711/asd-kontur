# Trial Readiness Specification v1

## Hard gate

A real OKS may be proposed or admitted only after an immutable accepted
`TrialReadinessDecision` pins the Product Goal, Capability Registry, target
trial profile, code/config/contracts, required rules/NTD, scale evidence,
operations and professional outputs.

## Required denominator

All capabilities marked `required_for_trial=true` must be at least
`CAPABILITY_READY`. In particular the decision must prove:

- Product Application Spine, typed UI/API and authentication/session;
- recursive/batch industrial intake, durable jobs and crash recovery;
- document registry, PDF viewer and evidence navigation;
- Project Understanding from representative real formats;
- applicable verified NTD and qualified RuleVersion coverage for the trial;
- mode-specific complete E2E and production-shaped outputs;
- workspace isolation, lifecycle, backup/restore and projection rebuild;
- 1k/5k/10k profile required by the chosen scale envelope;
- launchd/process/model guard, health, update and rollback;
- explicit gaps, owner authorities, support and recovery procedures.

## Fail-closed conditions

The decision is invalid if UI/application/intake/rules/outputs/scale evidence is
missing; a test PASS lacks denominator; any required capability is only
contract/foundation/partial; a model output substitutes for evidence; or an
unresolved blocker is hidden. `OKSReady` cannot be inferred from TrialReady and
must be a separate bounded admission decision for the selected trial.

Current state: `TrialReady=false`, `OKSReady=false`.
