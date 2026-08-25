# Architecture Blueprint v1

## Product topology

ASD-KONTUR is a local-first modular monolith with explicit process boundaries:

1. **Product Interaction Plane** — typed React/TypeScript workbench;
2. **Application Plane** — authenticated commands/queries, durable jobs and
   progress streams;
3. **Industrial Intake Plane** — content-addressed admission and native-first
   extraction for thousands of files;
4. **Domain/Knowledge Kernel** — the existing Python/PostgreSQL harness;
5. **Output Plane** — evidence-bound document/CAD candidates, rendering,
   professional finalization and export;
6. **Field/Offline Plane** — bounded device ledger and conflict-aware sync;
7. **Operations Plane** — launchd services, PostgreSQL/object plane, model
   broker, observability, backup and signed release/rollback.

Browser and model runtime never access PostgreSQL or object storage directly.
The Application Plane establishes identity, workspace, authorization,
idempotency and contract version before calling domain ports. The same
ProjectDefinition/WorkRequirementMatrix and Gateway serve all four modes.

## Data authority

- canonical platform memory: PostgreSQL platform schema plus immutable source
  objects; survives workspace lifecycle;
- workspace canon: OKS sources, candidates, verified facts, matrices, jobs and
  results isolated by composite scope and RLS;
- rebuildable projections: exact/FTS/vector/graph/tiles and UI read models;
- runtime context: bounded, version-pinned ContextPack assembled per operation;
- AI/VLM output: Candidate only;
- professional output: finalization decision plus evidence and export receipt.

## Deployment boundary

MBP remains authoritative primary. Static frontend, Python application,
document worker and local model broker run without mandatory Docker and are
supervised by launchd. PostgreSQL is the authoritative metadata plane and the
object plane stores source/output bytes. king25/Ubuntu may access only the
protected typed application boundary; it is not a second primary. VPS and
external providers remain controlled optional profiles.

## Legacy boundary

mac_asd is subject to the [Legacy Component Decision Gate](LEGACY_COMPONENT_DECISION_MATRIX_v1.md).
Its scenarios and characterized algorithms can inform the new components, but
its routes/templates/in-memory state/agent topology are not architecture.

## Readiness

Every plane and capability is counted in Contract Pack v2.0. Foundation tests
do not advance capability readiness. See [ADR-0013](decisions/0013-platform-kernel-to-product-application.md)
and [ADR-0014](decisions/0014-product-application-technology-baseline.md).
