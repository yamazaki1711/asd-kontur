# Contract Pack v2.0 — Product Goal and Readiness

Additive Contract Pack v2.0 fixes the complete product capability denominator
and fail-closed readiness ladder for ASD-KONTUR. It preserves v0.1–v1.9.

It defines `ProductGoal`, `ProductCapability` and dependency projection,
`ProductInteractionSurface`, the PostgreSQL-authoritative `DurableJob`
state/command contract, 1k/5k/10k `ScaleQualificationProfile`, mode/trial/
product readiness decisions and superseding lineage. The independent
`required-capabilities.json` list prevents an omitted plane or capability from
shrinking the denominator.

`product-capability-registry.json` describes the current canonical-main state.
It deliberately contains no `CAPABILITY_READY`, `MODE_READY`, `TRIAL_READY`
or `PRODUCT_READY` claim. Backend foundations and bounded fixtures do not imply
a user-operable capability.

Validation has two layers:

1. JSON Schema validates shape, closed enums and required evidence fields.
2. `asd_kontur.product_readiness.validate_capability_registry` validates the
   independent mandatory denominator, dependencies and readiness transitions.

The current terminal status is `TrialReady=false`, `OKSReady=false` and
`ProductReady=false`.

`READY_FOR_INTEGRITY_CYCLE` in v1.9 remains a bounded harness-participation
status; it is not readiness. Rule Registry with zero RuleVersion means
`infrastructure_ready=true` and `operational_rule_coverage=false`.
