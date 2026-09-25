# Contract Pack v2.8

Additive professional-assistant reasoning contract for
`PROFESSIONAL-ASSISTANT-REASONING-01`. It preserves Contract Pack v2.7 and the
143-capability product denominator.

The pack replaces the fixed aggregate retrieval path in the runtime assistant
with fourteen typed, workspace-scoped read tools and a bounded four-step cycle:
plan, retrieve, assess adequacy, synthesize and validate. It fixes no source
quota, preserves exact source navigation, stores immutable tool/quality
receipts and maintains a compact versioned dialogue state.

The user-facing `Construction Consultant` profile calls only `consultant.*`
read tools.  It shares model weights and the physical MLX runtime with the
independent Domain Harness, but never shares prompts, chat history, tool
authority, schemas or readiness.  Existing Harness contracts remain unchanged;
`DomainHarnessReady` is reported separately and cannot be inferred from
consultant quality.

`ConstructionConsultantQualityReady` remains false until the 30-question
professional matrix and the external browser acceptance pass on the exact
deployed merge commit. Owner acceptance is a separate subsequent observation.
