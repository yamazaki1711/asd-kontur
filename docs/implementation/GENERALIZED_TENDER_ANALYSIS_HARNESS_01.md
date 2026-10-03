# Generalized Tender Analysis Harness 01

## Baseline and previous defects

The accepted runtime forensic report established that Qwen performed real OCR,
classification, engineering extraction, and work reconciliation, but Codex had
manually advanced retries and successor scheduling. The real Tender workspace
remained at 393 succeeded jobs with 120 dependency-blocked jobs and zero
claimable work during the Codex-absent observation.

Release `ce3d8ee94096245c06ef538d6bc1684459918383` added a supervised durable
project orchestrator. Without manual refill or successor commands, the same
workspace advanced from 393 to at least 407 succeeded jobs, created replacement
and successor work, invoked the existing Qwen service, and refreshed project
reconciliation. Release `de0a60a1e0bd74b49585988744fdb62e048e7a65` adds the
professional processing-status API/UI but has not yet replaced the deployed
public component release recorded above.

The semantic harness nevertheless remained shallow and corpus-shaped:

- quantity review distinguished work quantities from dimensions but did not
  persist semantic scope or total/component relationships;
- cross-document comparison could compare different measurement dimensions as
  if they were a discrepancy;
- a PostgreSQL source-context projection recognized only three L5 sheet-pile
  spellings;
- the project model contained exact retaining-wall title exclusions and a long
  corpus-derived section heading;
- pit helper/UI wording and consultant validation over-centered KNS/LOS and
  exact L5 variants;
- the editable Tender report emitted a fixed section sequence even when source
  roles were absent.

## Corpus-specific rule audit

| Rule | Classification | Disposition |
| --- | --- | --- |
| Exact retaining-wall project title exclusion | Corpus-specific heuristic | Removed; replaced by a generic project-title shape using construction/reconstruction/repair plus a location marker. |
| Exact Far North utility-network heading | Corpus-specific heuristic | Removed; replaced by generic internal/external network heading treatment. |
| SQL L5/L5-10/L5UM recognition | Hardcoded project vocabulary | Generalized to bounded sheet-pile profile syntax; no specific profile is a decision. |
| Split `UM from steel` OCR repair | General algorithm with corpus example | Generalized to use the suffix of whichever profile is present in page context. |
| Consultant required-term L5 regex | Corpus-specific validation | Generalized to arbitrary L-number profiles and common concrete durability classes. |
| Exact 30SH2/35SH2 waling profiles and C255 steel extraction | Hardcoded project vocabulary | Generalized to bounded Russian rolled-section and structural-steel grade syntax. |
| KNS/LOS designation parser | Domain-specific recognizer | Retained as a specialized deterministic signal, not a required ontology. Generic Qwen structure extraction remains the primary project-independent path. |
| Consultant facility intent limited to KNS/LOS codes | Corpus-specific routing | Replaced by matching persisted project-facility labels and a bounded generic construction-location route. |
| Explicit pit association limited to KNS/LOS | Corpus-specific restriction | Generalized to an explicit named/code facility followed by a designation number; semantic pit decisions remain available for other forms. |
| Always-visible pit and sheet-pile Tender panels | Corpus-shaped UI behavior | Made conditional on the current project model. Projects without pits or sheet piling now lead with their actual facilities, structures, works, quantities, and materials. |
| Construction work family vocabulary | General construction rule | Retained. Unknown concepts remain unclassified rather than forced. |
| OZERO quantities, profiles and facility labels in assistant/project-model tests | General algorithms with project-derived cases | Retained only in isolated tests of structured-fact preservation and display. A runtime-code scan found none of these exact values, workspace IDs or project titles in `src`, `frontend` or migrations. Independent bridge, pipeline and reservoir cases exercise the mechanisms with changed terminology and values. |

No production rule containing the destroyed OZERO workspace ID or the active
blind-project workspace ID was found in the audited runtime paths.

## Changes implemented in this checkpoint

1. Added a project-independent `TenderAnalysisTask` contract and bounded
   structured payload builder for the required semantic task families.
2. Advanced work reconciliation to profile v9. Qwen quantity decisions now
   include semantic scope, quantity type, explicit relationship, related input
   identities, and scope compatibility. The parser rejects invented identities,
   self-relations, malformed enums, and implicit relations without operands.
3. Added generic `QuantityStatement`, relationship and scope-compatibility
   contracts. Deterministic arithmetic evaluates only explicit, unit-compatible,
   entity-compatible `TOTAL_FOR` relationships.
4. Integrated accepted quantity semantics into the shared project model and
   professional comparison/finding path. Old v5-v8 results remain readable;
   they do not acquire fabricated relationships.
5. Corrected role comparison so multiple legitimate dimensions for one work
   (for example count and volume) are compared independently. Different units
   alone no longer create a discrepancy.
6. Generalized sheet-pile profiles, rolled-beam profiles, steel grades, and
   split-OCR handling described above.
7. Made the editable Tender report adaptive: it now emits only sections backed
   by the current project model and builds the main quantity schedule across
   all work families rather than treating sheet piling as the universal case.
8. Added migration 0077 so immutable v9 semantic results can be persisted while
   retaining v3-v8 compatibility; downgrade is fail-closed when v9 rows exist.
9. Advanced Qwen engineering extraction to profile v16 with reusable, explicit
   project-participant, commercial, schedule, procurement, and contract field
   keys. The shared model and adaptive report expose those sections only when
   the uploaded package supplies them.
10. Extended quantity relationship analysis across separate work/schedule rows
    in the same bounded Qwen batch. The model may identify the semantic graph;
    deterministic code still rejects invented identities, cross-role or
    cross-facility arithmetic, incompatible units, and conflicting revisions.
11. Advanced content-based document classification to profile v2 and added
    reusable procurement-notice, technical-specification, construction-schedule,
    engineering-survey, and design-calculation roles. Filenames remain supporting
    context rather than a project-specific decision table.
12. Added a compact project-independent professional finding vocabulary while
    preserving Russian construction-language titles and explanations in the UI
    and report. Quantity, component-total, material, duration, scope, NTD, and
    missing-information findings now carry stable machine-readable kinds.
13. Advanced work reconciliation to profile v10 and added bounded
    cross-document semantic batches. Rows enter such a batch only when the same
    exact facility and generic work family occur on both design and commercial
    document sides. Qwen, not the batch builder, decides whether their
    engineering scopes are the same, composite, alternative, revision-related,
    or incomparable. Parameterized bridge, pipeline, and reservoir cases prove
    that neither project names nor retaining-wall vocabulary drive the
    mechanism.
14. Corrected the document-side boundary to recognize both internal role keys
    and the professional Russian role labels supplied by the live preparation
    path. Before this correction, the intended cross-document review remained
    unreachable even when compatible design and commercial rows existed.
15. Added migration 0078 for immutable v10 results while retaining v3-v9 read
    compatibility. Downgrade remains fail-closed if v10 results exist.
16. Corrected progressive profile selection after live observation showed the
    user model dropping from 341 work scopes / 185 material rows to 241 / 124
    while a newer semantic profile was only partly processed. Accepted batches
    remain visible for a source with no completed profile, but a profile upgrade
    now keeps serving the last terminal source result until the replacement
    stage is terminal. Against the same live durable state, the corrected read
    path retained 348 work scopes and 235 material rows instead of exposing the
    partial replacement. This changes read selection only; no candidate or
    immutable result is overwritten.
17. Completed the project-independent semantic task inventory and added one
    shared strict result validator for input identity, decisions, confidence,
    source references, normalized interpretation, relationships and explicit
    ambiguity. This closes the contract gap without creating a monolithic
    project-analysis prompt.
18. Added typed deterministic component/total outcomes: exact match, rounding
    match, mismatch, incomplete component set and incompatible scope. Rounding
    matches remain comparisons but no longer become Tender issues; incomplete
    and incompatible sets never produce arithmetic findings.
19. Completed the reusable professional-finding envelope with comparison data,
    document/source references, confidence, uncertainty, practical consequence
    and recommended action while keeping deterministic values authoritative.
20. Added an independent Qwen status plane. The HTTP service now reports model
    loading, ready/idle, generating and error states while a generation is in
    flight, but retains one heavy-model generation lock. The assistant worker
    treats a generating model as healthy but not claimable, avoiding competing
    requests without misreporting process death.
21. Corrected the user-facing job denominator so immutable historical
    dependency-terminal descendants do not keep an active project permanently
    below completion. Their history is retained and remains available to
    technical diagnostics.

## Autonomous runtime

The orchestrator is a low-frequency supervised safety net over durable state.
It does not interpret documents. It repairs terminal dependency gaps, schedules
bounded replacements for known transient Qwen failures, ensures project model
stages, and refills project-work reconciliation idempotently. The document/Qwen
worker performs content processing through the persistent local model endpoint.

During a later read-only checkpoint, with no manual refill, retry, successor,
or reconciliation command, the real workspace had advanced from the forensic
baseline of 393 succeeded jobs to 454. It contained 104 successful Qwen work-
reconciliation results (up from 102 in the forensic report), 23 queued jobs,
one live project-definition job, and 719 project fields, 590 structures, 1,060
work observations, 663 quantities, and 314 materials. The supervised release
was still `ce3d8ee`; the worktree changes in this record had not been deployed.
Controlled service restart tests and a later blind snapshot are still required
before this record can set `AutonomousProjectProcessing=true` for the completed
release candidate.

At 2026-09-30 13:12 +12:00, the same supervised runtime had reached 106
successful work-reconciliation jobs and was continuing a 54-batch semantic
project-definition job (27 accepted batches) through the persistent Qwen
service. One lease left by an earlier worker restart remained expired and was
available to the existing recovery path; it was not edited or retried by a
developer command. This is progression evidence, not yet final Codex-absent
acceptance for the v10 release.

## General quantity acceptance

Parameterized controlled cases cover different terminology and measures:

- concrete volume: `100 + 25` against stated `90 m3`;
- structural steel: `5.2 + 3.1` against stated `7.0 t`;
- pipeline length: `120 + 80` against stated `150 m`.

The same deterministic implementation reports the arithmetic difference only
after an explicit `COMPONENT_VS_TOTAL` relationship. The relationship may join
separate schedule rows; incompatible units, different facilities, different
document roles, or an `INCOMPARABLE_TO` decision produce no numeric finding.
An invented cross-row identity is rejected and the source value remains visible
as unresolved. These are mechanism tests, not expected values for a real
project.

Typed acceptance additionally covers reported-precision rounding, an incomplete
component set, monolithic versus precast concrete, different revisions and the
same work name in different facilities. These cases prove that the engine
prefers `INCOMPATIBLE_SCOPE` or an unresolved result over a false discrepancy.

## Backlog convergence audit

A read-only live audit found 103 queued jobs at the observation point: 21
project-definition, 38 structure-reconciliation, 38 project-understanding,
three work-reconciliation and three work/quantity/material extraction jobs.
All queued jobs had unique input digests and idempotency keys. Dependencies
were grouped as 17 already satisfied, 38 legitimately pending and 48 direct
stage jobs without a predecessor edge; there was no duplicate refill storm.

The 120 `reconciliation_required` rows were immutable historical
`dependency_terminal_failure` descendants: two document aggregation, one page
classification, 19 evidence-index, one native-layout, one OCR, one OCR-routing,
one page-health, one project-definition, 19 structure-reconciliation, 19
project-understanding, 19 requirement-matrix, 19 work-package and 17
work/quantity/material rows. Forty-three terminal failures were separately
accounted for: 37 transient Qwen-unavailable histories, four invalid locators,
one OCR failure and one unsupported format. No row was patched or deleted.
The autonomous orchestrator owns eligible replacements; immutable historical
rows are excluded only from the professional progress denominator, not from
diagnostic history.

## Blind-project and unseen-corpus status

The active real project remains a blind validation corpus. No owner-known
finding has been added to prompts, fixtures, catalogs, or runtime data. The
durable snapshot captured at 2026-09-30 15:07 +12:00 is stored outside Git at
`~/.asd-kontur/qualification/generalized-tender-20260930/01a0eba7-70ba-7770-9601-1a713dd359cf/`.
Its model SHA-256 is
`bd5d15383f37baeda54654f4ce320c8cd5a03928861b4fd72f1eeb1abf6c7679`;
the editable report SHA-256 is
`1f0817bedd1323f403ab6d7387f30ded20486653704aad6e06ca806f39716364`;
and the analysis archive SHA-256 is
`7ab214c0ede52d719fbf2e1b2e80435f3a0f04bff14114597a0ebfd4bc14553d`.
The snapshot identifies the retaining-wall capital-repair project, six current
facility/structure groups, 179 consolidated works, 142 materials, 18
participants and six commercial conditions. It has no defensible quantity
comparison or professional finding yet, so the report remains explicitly
partial.

An independent controlled bridge corpus now runs through the unchanged shared
project-model path. It uses a bridge facility, bored-pile work, different
document names and roles, and `36` design piles against `30` commercial piles.
The pipeline creates the bridge facility/work schedule and deterministically
reports a six-pile quantity difference from strict v9 semantic scope decisions.
The separate component-total tests vary concrete volume, structural-steel mass,
and pipeline length. This proves portability of the implemented mechanism, not
completion of every harness stage.

## Performance observations

The initial autonomous run eliminated the previous zero-claimable queue gap and
fed multiple work-reconciliation jobs to the already-loaded Qwen service. Exact
time-to-first-summary, queue idle gaps, per-task durations, retries, and
time-to-first-finding remain to be captured from the current candidate release.

## Migration and verification checkpoint

Migration 0078 was tested against a separately restored physical backup before
the public database was upgraded. The backup is
`pre-0078-cross-document-20260930T1310/public-before-0078.dump` with SHA-256
`700e691a1acfddc402ce4a98acd84857c84f9d1ba2627a1e503c85005004b398`.
The explicit downgrade/upgrade integration gate passed on database
`asd_kontur_restore_0078_20260930`. The platform-memory fingerprint was exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`
in both the public source and restored candidate, and remained identical after
the public migration.

Focused backend verification passed 278 tests across batching, semantic
validation, project modeling, findings and exports. The broader local run
passed 997 tests with 109 skipped; its sole reported failure was the deliberate
full-migration guard when `ASD_TEST_DATABASE_URL` was omitted, while that same
test passed separately with the restored database URL. Frontend typecheck,
lint, formatting, five component tests, dependency audit and production build
passed. Exact-SHA CI remains a separate release gate.

## Final release verification

Release `3cdfd0669c779432a08309d7f6c1e1f2c17ef3d0` and migration
`0078_cross_document_scope_reconciliation` are active for API, worker,
assistant worker and project orchestrator. Exact-SHA CI run 36657643792 passed.
After a controlled Qwen restart, project-definition job
`01a0efc7-4194-7802-8f93-be1635fd787b` completed and the supervised services
automatically claimed successor `01a0efc7-4196-7422-9991-14c001a1fbb5`.
Without a manual retry, refill, successor or reconciliation command, succeeded
jobs rose from 473 to 477 and the successor reached two of five accepted
semantic batches while continuing to heartbeat. API, worker, orchestrator and
Qwen restart recovery are therefore demonstrated for the active real project.
Mac sleep/wake was not tested.

The Qwen service uses an older launchd release label, but its loaded
`qwen_server.py` was byte-identical to release `3cdfd066`. The subsequent
candidate replaces the single-threaded health limitation with a lightweight
threaded status plane while retaining a single generation lock. Deployment and
live loading/generating/idle verification remain release gates for that
candidate.

The independent bridge corpus and parameterized quantity tests prove the
shared mechanisms across different names, work types, units and values without
a code change. They do not execute a second complete live Qwen project, so the
full unseen-project acceptance remains open.

Release `5679343aec519b347b1199492afa8709859c4263` subsequently activated the
typed component/total outcomes, shared semantic-task result envelope,
professional-finding completion, corrected professional progress denominator,
and the independent Qwen status plane. Exact-SHA CI run 36667568869 passed;
migration remains `0078_cross_document_scope_reconciliation`.

The first status-plane candidate (`79961d8`) correctly exposed health but ran
MLX generation in HTTP request threads. Live activation caused repeatable MLX
segmentation faults. Qwen alone was immediately rolled back to the prior stable
runtime; no accepted project fact was lost. The corrected release gives one
dedicated thread exclusive ownership of both model loading and inference, while
HTTP threads only transport bounded requests/results and serve health. During
the corrected live run the same Qwen PID remained at one launchd run, health
answered `QWEN_GENERATING`, and five real project requests completed with no
runtime error while the bounded semantic recovery continued.

Across the controlled restart, supervised services advanced the real workspace
from 495 to 533 succeeded jobs without a manual retry, refill, successor, or
reconciliation command. The platform-memory fingerprint remained exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`.
At the release-receipt observation the active work-reconciliation job was still
at 0/12 accepted batches after five completed model requests; this is recorded
as a semantic-output/recovery performance limitation, not claimed as a new
professional result.

The same job later completed autonomously after 13 Qwen requests and its result
became durable; the worker immediately claimed the next project job. Historical
receipts quantified the cause: 72 of 78 twelve-row work-reconciliation batches
needed recursive repair, averaging 3.72 calls, while observed batches of up to
nine rows normally completed in one call. The next candidate therefore reduces
future default batches to eight rows. Existing queued jobs and accepted history
are unchanged; the change applies only to subsequent idempotent refills.

That optimization is active in application release
`c9a251ac986a34314fe1180dd8a0886a24c3882e`; exact-SHA CI run 36669285326
passed. Qwen remains pinned to byte-compatible inference release `5679343` so
the already-loaded model was not restarted merely for an application batching
constant. By the compact post-release observation the workspace had reached
549 succeeded jobs, two new work-reconciliation results had become terminal,
and the corrected Qwen status plane had observed 37 completed requests with one
heavy process and no manual progression command.

## Real-result checkpoint — 2026-09-30

The blind retaining-wall workspace now produces a professional result from the
shared model rather than a zero-result mechanism demonstration. Snapshot
`BLIND_TENDER_ANALYSIS_SNAPSHOT_v2` was frozen before any owner-known finding
comparison at:

`~/.asd-kontur/qualification/generalized-tender-20260930/01a0eba7-70ba-7770-9601-1a713dd359cf/v2/`

Its manifest SHA-256 is
`84900760e5c7881aeec98f4af6db40a53c6523e0e1af1dd45d385c5a45bf9432`.
The snapshot records model `project-engineering-model-v55` with fingerprint
`sha256:dda94895f8db4b214c5b673274c23e91df586d6d9bbf9341b84a1e0070619c43`.
At the freeze it contained six facility/structure groups, 209 consolidated work
scopes, 259 reviewed quantity observations, 233 accepted work quantities, four
quantity/condition comparisons, four material comparisons, two professional
findings, two customer questions and two contractor risks.

The established construction comparisons are a `219 m` PD/VOR match for the
metal enclosure and a `65.4 m3` VOR/estimate match for crushed-stone foundation
preparation. The professional mismatches are estimate VAT `20%` versus contract
VAT `22%`, and project/POS duration `2.2 months` versus procurement duration
`4 months`. Both mismatches carry source locators, a Russian professional
explanation, a customer clarification action and a contractor consequence.
Four material matches connect project and commercial documents for crushed
stone, sand and geotextile. No owner-provided discrepancy was used.

The quantity matrix contains 328 interpreted rows. Its blocker accounting is:
four comparisons established, 185 missing sufficiently grounded structure
links, 76 unresolved semantic scopes, 54 true non-comparable values and nine
unit-incompatible values. This makes the remaining bridge explicit rather than
reporting only a zero comparison count. A previously emitted `772.5 m3` versus
`115.9 m3` component-total mismatch was removed: Qwen established that the
known component set was incomplete, and deterministic arithmetic now refuses
the false discrepancy.

The editable DOCX is structurally valid and its extracted text contains the
project, participants, commercial conditions, schedule, works, comparisons,
findings, questions and risks. No compatible office renderer is installed on
the deployment host, so visual pagination was not claimed and no alternative
renderer experiment was substituted.

Profile v15 terminal receipts provide the current eight-row measurement. Across
15 successful jobs it averaged eight rows, 404.8 seconds, 2.60 inference calls,
0.80 recovery codes per job and 71.1 accepted rows/hour. The older v8 profile
averaged 10.17 rows, 359.2 seconds, 3.13 calls and 1.16 recovery codes per job.
The v15 contract performs additional scope and component-completeness work, so
raw throughput is not directly comparable; the eight-row boundary is retained
because it lowers calls and repair pressure while preserving the stricter
output. It is not claimed as a throughput improvement.

Live operation exposed two generic starvation defects. Migration
`0084_new_project_time_to_first_result` prioritized only a workspace with zero
processed documents, so a new project lost priority after its first document.
Migration `0085_incomplete_project_time_to_first_result` keeps priority while a
latest document state is actively incomplete. A second observation showed that
completed intake could still lose all capacity to an older workspace's deep
semantic queue. Migration `0086_workspace_fair_job_claim` therefore orders
eligible workspaces by least recent service before applying job priority within
the selected workspace. It does not inspect a project name, document role,
work family or expected result.

The 0085/0086 chain passed upgrade, fail-closed downgrade and re-upgrade on the
separately restored database `asd_kontur_restore_0085_20260930`. The source
backup is
`~/.asd-kontur/public-demo/backups/pre-0085-incomplete-project-priority-20260930T2215/public-before-0085.dump`
with SHA-256
`d51242850a7317f640f30bd7aa6bdde2551cd77ebc8929564ea18a15fb21b764`.
The platform-memory fingerprint remained exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`.
The roof development control exposed one further generic scheduler defect.
The autonomous refill returned no work when a workspace had never previously
had a `PROJECT_WORK_RECONCILIATION` job. Thus the first semantic batch still
depended on an operator-created predecessor even though later batches were
autonomous. Release `d0641e95ce0bc678828f213bf1873178960c4e50` fixes that
bootstrap by deriving the durable owner identity from the latest workspace job
when no earlier work-reconciliation job exists. The idempotency key and batch
eligibility remain unchanged. The roof corpus is therefore development
evidence, not the strict final unseen acceptance corpus.

The deployed API, worker, assistant worker and orchestrator use release
`d0641e95ce0bc678828f213bf1873178960c4e50` and migration
`0086_workspace_fair_job_claim`. The persistent Qwen process was not restarted;
its server module is byte-compatible. After activation the supervised
orchestrator independently created four initial work-reconciliation batches
for the roof control and additional batches for the earlier heat and culvert
controls. No manual successor, retry, refill or reconciliation command was
issued.

The strict final unseen control was introduced only after that source release:

- workspace: `01a0f229-8537-79fa-9c20-44844689b10f`;
- display name: `Final Unseen Control — Firewater D-6`;
- corpus root:
  `~/.asd-kontur/qualification/generalized-tender-20260930/final-unseen-control-firewater-v1`;
- external corpus manifest SHA-256:
  `e2cf9c555b5459f3b5c618c526481a72a9386b17d7ccc0b9d23a01fcea0251d4`;
- three stable selectable-text PDF inputs with different names, facilities,
  work types, quantities and units from the real blind project.

The external oracle is not uploaded to the workspace or included in Qwen
context. It defines a `120 m + 80 m` component/total relationship, a stated
`230 m` total, a `200 m` commercial scope, and a false-positive trap consisting
of `6` wells versus `6 m3` concrete preparation. No production source change is
permitted after this corpus introduction. At the first live checkpoint the
workspace advanced autonomously from admission to 17 succeeded jobs; the
orchestrator created document-classification and project-semantic successors,
and Qwen began `PROJECT_DEFINITION_EXTRACTION` at
`2026-10-01T00:22:47+12:00` without any Codex runtime progression command.

Focused verification for the bootstrap change passed 51 unit tests and the
targeted PostgreSQL integration test. Backend lint passed. The full
PostgreSQL-backed suite passed 1,138 tests with one skip and two failures: the
native DOCX/CSV project-understanding fixture exceeded its eight-second drain
window with one final job still queued, and the ZIP intake fixture observed a
`reconciliation_required` terminal result where it expected every job to
succeed. Both failures reproduced individually and remain release limitations;
they are not hidden as successful acceptance. Frontend typecheck, lint,
formatting, five component tests and production build passed.

## Exact-release continuation — 2026-10-01

Release `5fdb1b04ddc8b8a04d7cf34754802841f500cdef` makes one previously
unprocessed engineering source batch the maximum work of one durable semantic
job. Accepted batches from the same semantic profile remain reusable under the
dense batching policy, so yielding does not reprocess accepted content. The
autonomous planner schedules another idempotent recovery only while accepted
fragment coverage increases and stops after a no-progress recovery. This is a
scheduling boundary; it does not change project facts or Qwen's semantic
contract.

The focused backend gate passed 160 tests. The broad local gate passed 1,040
tests with 110 skips; its only unavailable check was the database migration
round trip because that invocation intentionally had no `ASD_TEST_DATABASE_URL`.
Exact-SHA GitHub Actions run `36751000961` passed, including PostgreSQL
integration, browser E2E and security jobs. API, document worker, assistant
worker and project orchestrator run from the pinned exact-release directory;
migration remains `0086_workspace_fair_job_claim`.

The current blind-project snapshot remains independent of owner-known answers.
Its 328-row quantity matrix records four established comparisons and classifies
the remaining blockers as 185 missing structure links, 76 unresolved semantic
scopes, 54 true non-comparable values and nine incompatible units. The accepted
professional result includes:

- a `219 m` PD/VOR match for the metal enclosure;
- a `65.4 m3` VOR/estimate match for crushed-stone foundation preparation;
- estimate VAT `20%` versus contract VAT `22%`;
- project/POS duration `2.2 months` versus procurement duration `4 months`;
- matching sand, crushed-stone and geotextile material scopes;
- two source-linked customer questions and two contractor risks derived from
  the VAT and duration conflicts.

The frozen `BLIND_TENDER_ANALYSIS_SNAPSHOT_v2` manifest is
`sha256:84900760e5c7881aeec98f4af6db40a53c6523e0e1af1dd45d385c5a45bf9432`;
its editable report is
`sha256:70de51a20a6a520106152a01c6b69054e99447d8a02d940383d50950458b431f`.
No office-compatible renderer is installed on the host, so DOCX structure and
extracted content were verified but visual pagination is not claimed.

Actual terminal v15 receipts reject the earlier eight-row assumption. Four-row
batches measured 15 jobs (14 succeeded, one failed), 2.13 model calls, 0.60
repair codes, 177.4 seconds and 75.9 accepted rows/hour on average. Eight-row
batches measured 29 jobs (28 succeeded, one failed), 3.17 calls, 1.28 repairs,
402.3 seconds and 69.9 accepted rows/hour. The deployed four-row policy is
therefore retained.

A strict unseen PDF control was created only after source release `5fdb1b0`:

- workspace `01a0f378-45b8-77d2-8a54-a6efbb22183d`;
- display name `Post-release Unseen PDF Control - School Roof S17`;
- four one-page selectable-text PDF inputs with manifest SHA-256
  `f0f65033bdc04fdd31518255a3a347710265ba1d4d92ccd8e40a68a31e465e87`;
- an external, non-uploaded acceptance oracle with SHA-256
  `d6d6cb4472b43cd19378644015ebaf10a8e21edc9d5f426b976075a07bed9a81`.

The corpus changes project name, participants, filenames, structures, work
families, quantities and commercial terms. It contains a component/total
relationship, a cross-document quantity mismatch, a material-thickness
mismatch, an explicitly absent commercial demolition position and two false-
comparison traps. Production code contains none of these expected values.

At admission the workspace had 16 succeeded jobs, zero accepted semantic
fragments and no project result. Supervised services independently advanced it
to a usable early report: `Капитальный ремонт кровли`, the customer and
designer, VAT and payment terms, private-tender basis, performance security,
warranty and both project/tender duration statements. The harness correctly
kept `45 working days` and `3 calendar months` as non-comparable duration
scopes. The early editable report and archive were generated from the shared
project model; the DOCX ZIP/XML structure and extracted Russian content passed
verification.

The long-lived Qwen process was then restarted once under launchd so it loaded
the already-tested pinned threaded status-plane implementation. Its PID changed
from `26466` to `90242`; the document worker and orchestrator were not
restarted. The loopback `/health` endpoint remained responsive during
generation, and durable processing resumed automatically without a retry,
refill or successor command. The status plane must be queried without the host
SOCKS proxy (`NO_PROXY`/equivalent loopback bypass).

The strict unseen run remains in progress at this record point. It is not yet
accepted as the full unseen-project gate until the working schedule and
commercial sheet produce a quantity relationship, a valid comparison, a
professional finding, false-positive rejection and the final preliminary
report under the unchanged source release.

## Complete-context and document-role correction — 2026-10-01

Release `96ef4569db48f8f1915351fa1fda72f21386f471` corrected a second
generic relationship-review failure. A complete three/four-row
`QUANTITY_RELATIONSHIP_ANALYSIS` response could exhaust its compact first-pass
output budget and then lose cross-row authority when generic recovery split the
batch. Profile `qwen-project-work-reconciliation-v19`, admitted by migration
`0092_relationship_review_budget_v19`, retries the same bounded context once
with the established 5,000-token ceiling before the existing split fallback.
The fallback remains bounded, and no project value or work family is encoded in
the policy. A parameterized test uses a changed `825 + 550 = 1375` steel-mass
relationship to prove the mechanism.

The physical pre-migration backup is:

`~/.asd-kontur/public-demo/backups/pre-0092-relationship-budget-20261001T151853/public-before-0092.dump`

Its SHA-256 is
`34e88488e7ba012bc47a075017d2eea10f2667bbb877f6428e2ac856944dc3f4`.
Upgrade, fail-closed downgrade and re-upgrade passed on the separately restored
database `asd_kontur_restore_0092_20261001`. The 26 platform-global table
counts and fingerprints remained exactly equal before and after migration;
NTD processing remained `319 succeeded`. The full local PostgreSQL-backed
suite passed 1,160 tests with one skip. Exact-SHA CI run `36809799636` passed.

The post-release warehouse-yard control then exposed a distinct generic bridge
defect. Durable page-role decisions correctly classified its design,
specification and commercial documents as `РД`, `Спецификация` and `ВОР`, but
the engineering read model trusted a fragment-local Qwen role and rendered the
work observations as `ПД`. After three of four documents had complete semantic
coverage, the workspace had eight pending quantities and zero comparisons.
This control is preserved as a failed unseen attempt; it is not retroactively
claimed as a pass.

Release `5ec6d23555782bc0460b7dad343b430997d9ab8a` carries the generic
correction. Source context now includes the latest page-scoped role-decision
set. The professional read model prefers an established non-unknown page role
over a fragment-local broad role, while retaining separate roles for different
pages of a mixed document. A read-only evaluation against the already
persisted warehouse data changed the same rows from `ПД` to `РД`,
`Спецификация` and `ВОР` without re-extraction or project-specific rules. The
focused gate passed 157 tests. Exact-SHA CI run `36813132587` passed, including
PostgreSQL integration, migration round-trip, browser E2E and security checks.

The API, document worker, assistant worker and autonomous orchestrator now run
from the pinned `5ec6d23` release. Qwen PID `90242` and NTD worker PID `98263`
were not restarted. API readiness reports migration `0092`. A post-deployment
snapshot again matched all 26 platform table counts/fingerprints and the `319`
terminal NTD jobs exactly; its SHA-256 is
`505711eecafc45438311ebdeee8a8f7c0bb334d20266a5975ff606c83f6c09a0`.

A new independent drainage-network control was generated and visually checked
only after source `5ec6d23` was frozen. It changes project purpose,
participants, filenames, structures, work families, quantities, materials and
commercial conditions. Its workspace is
`01a0f5a9-7ed2-7343-9710-5ec208920750`, and its runtime admission digest is
`sha256:d297d6ce95b253d3c0dabea675839b7d4a10aaea4eb0ae3b50880d12fcf46f47`.
The external oracle is not uploaded. Admission created the normal durable graph
with `manual_progression_commands=0`; production source remains frozen for the
acceptance run.

That frozen drainage-network run completed semantic coverage for all four
documents without a queue, retry or successor command from Codex. The page-role
bridge correctly exposed `A17` as `РД`, `B28` as `Спецификация` and `C39` as
`ВОР`. The shared model established the project purpose, customer, designer,
private-request procurement method, monthly payment basis, three-percent
performance security, twenty-month warranty and distinct `28 working days`
versus `6 calendar weeks` time scopes. It classified all ten construction
observations, accepted nine of ten reviewed quantities and produced:

- an exact `6 piece` RD/VOR well-count match;
- a real `150 m` RD versus `145 m` VOR sand-base quantity discrepancy;
- a source-linked professional finding, customer question and contractor risk
  for the unpriced `5 m` difference;
- a sand material match;
- no false comparison between wells and weeks, sand volume and warranty months,
  or working-day and calendar-week durations.

The run remains a partial unseen acceptance, not a pass. Although Qwen's
professional reason correctly described the two pipeline segments as components
of the stated pipeline total, strict output validation rejected the complete
relationship response because `component_set_complete` had an invalid shape.
The subsequent split recovery safely preserved the quantities but necessarily
lost cross-row authority. The stated total therefore remained ambiguous and no
component/total arithmetic result was published. The pipe `SDR17` and `SDR21`
properties were preserved but did not yet become a material comparison because
the unresolved pipeline work scopes were not consolidated.

Release `74bff1abfc537bd62ab708c1e45679099c89d11f` addresses the generic
complete-context failure as profile `qwen-project-work-reconciliation-v20`.
One bounded schema-repair pass now receives the same complete group and the
typed validation failure before recursive split fallback. A harmless model
variation (`component_set_complete=false` on a non-total row) is normalized to
`null`; no semantic relation or arithmetic result is inferred by the parser.
Parameterized cable-length and structural-steel tests change names, quantities,
units and work families. Migration `0093_relationship_schema_repair_v20`
admits the versioned profile. The focused gate passed 240 tests.

Before public migration, the physical backup
`~/.asd-kontur/public-demo/backups/pre-0093-relationship-schema-20261001T173500/public-before-0093.dump`
was created with SHA-256
`1bed4d1f9023ea90978fac42308369a6ca638d03a134fe968a3f0a6a39c29a8c`.
The separately restored database `asd_kontur_restore_0093_20261001` passed
upgrade, fail-closed downgrade and re-upgrade. All 26 platform-table counts and
fingerprints plus the `319 succeeded` NTD state remained exactly equal; the
pre-migration platform snapshot SHA-256 is
`505711eecafc45438311ebdeee8a8f7c0bb334d20266a5975ff606c83f6c09a0`.

Exact-SHA CI run `36820305995` passed for `74bff1a`, including PostgreSQL
integration and migration round-trip, frontend checks, browser E2E, security
checks and the production-contamination guard. The production database then
advanced to `0093_relationship_schema_repair_v20`. Its post-migration platform
snapshot has SHA-256
`cab90bcc35ea566fc758737b5391edb2f6cac10c727f30430f8523e1bbd3958a`;
all 26 platform-table counts/fingerprints and the `319 succeeded` NTD state
remain exactly equal to the pre-migration snapshot. API, document worker,
assistant worker and project orchestrator now run from the pinned release
`~/.asd-kontur/public-demo/releases/20261001-74bff1a-relationship-schema-v20`.
The persistent Qwen and NTD worker processes were not restarted.

A new independent steel-gallery control was generated only after that release
and migration were frozen. Its four visually checked one-page PDF inputs use a
new project purpose, participants, filenames, structures, structural-steel
work, quantities, material grades and private commercial conditions. The
external acceptance oracle is stored outside the input directory and was not
uploaded or included in model context. The normal application admission
created workspace `01a0f605-1608-7c9a-8b8a-f13e83a11920`, display name
`Post-v20 Unseen Control - Steel Gallery SG-314`, with manifest digest
`sha256:c1f308eeba8ac67027865b0af444401992651cb582bd99dc3beb5264a856df52`.
Admission used release `74bff1a` and records zero manual progression commands.
The supervised orchestrator independently created and completed the initial
project-model stages. No queue refill, retry, successor, reconciliation or
priority command was issued after admission.

That admission also exposed a generic time-to-first-result scheduler defect.
Model-slot fairness was evaluated before semantic completion, so a newly
admitted project with only one of four source documents semantically complete
shared the single model with historical deep-reconciliation work. The system
remained autonomous but could take hours to deliver the next primary project
fact. Migration `0094_intake_before_fairness` changes only durable claim
ordering: active workspaces with incomplete project-definition semantics are
ranked first, then by the fraction of active documents already semantically
complete, and only then by model-slot fairness. The policy is independent of
project name, document name, work family and expected result.

The migration was tested against the physical pre-migration backup at
`~/.asd-kontur/public-demo/backups/pre-0094-intake-priority-20261001T183300/`
(dump SHA-256
`289e7522d45fbbe958a41a3685e65389b8d1c5eee427c8321d65e82bf3edb27e`).
The separately restored database passed upgrade, downgrade and re-upgrade.
Its first transactional model claim changed from a historical workspace to the
incomplete steel-gallery workspace without any row patch. All 26 platform
knowledge table counts/fingerprints and the `319 succeeded` NTD state remained
exactly equal; the corrected post-upgrade snapshot SHA-256 is
`c132cf6c3f39751c82ef6ebc81eb2103113db0ba3b19d1496e9dce406da28a93`.

Production observation refined that policy. Ordering incomplete projects by
their completion ratio allowed an older 25%-complete control workspace to
monopolize the worker even while newer incomplete projects had dependency-free
semantic jobs. The fresh waterproofing control reached two of four semantic
documents and then waited while the worker completed historical deterministic
jobs. It is retained as a failed scheduling acceptance, not counted as the
strict unseen pass.

Migration `0095_incomplete_semantic_fairness` removes only that ratio
tie-breaker. The resulting order is: semantically incomplete workspaces before
fully interpreted historical work, then model-slot fair sharing between the
incomplete workspaces. This keeps the product-value tier while ensuring that a
single incomplete workspace cannot monopolize Qwen. Upgrade, fail-closed
downgrade and re-upgrade passed on the disposable restored database, together
with the focused 243-test orchestration/analysis gate and the full migration
round-trip test.

Release `f0476a8d837c63a072e129e25c2a5e57812b4c00` deploys that policy as
migration `0095_incomplete_semantic_fairness`. The physical pre-migration
backup is
`~/.asd-kontur/public-demo/backups/pre-0095-incomplete-fairness-20261001T190500/public-before-0095.dump`;
its SHA-256 is
`cf42cc39ef3019884219d3c71a010b5736f3a8fc6ee256735781d8d1c26904b2`.
Upgrade, fail-closed downgrade and re-upgrade passed on the disposable restore.
The post-migration platform snapshot is stored beside that backup as
`platform-after-0095.json` with SHA-256
`f621263072480d7822c7844b0be270bc4714aebd6f247673850257fc1760a2e0`.
Its 26 platform-table counts/fingerprints, Knowledge Gateway status and NTD
worker state are exactly equal to the pre-migration snapshot; the only whole-
file difference is the expected migration-head metadata. NTD remains at 319
succeeded jobs. Exact-SHA CI run `36828257227` passed:
<https://github.com/yamazaki1711/asd-kontur/actions/runs/36828257227>.

API, document worker, assistant worker and autonomous project orchestrator now
run from the pinned release
`~/.asd-kontur/public-demo/releases/20261001-f0476a8-incomplete-project-fairness`.
Qwen PID `90242` and NTD worker PID `98263` were not restarted. During the
first launchd update, generated candidate plists briefly referenced a missing
release-local `.venv`, so the four application services failed to start. The
preserved plist topology was restored immediately with the correct pinned
environment. Qwen and the NTD worker were unaffected. Readiness then returned
HTTP 200 on migration `0095`.

The immutable terminal receipts also provide a direct batching measurement.
The current `qwen-project-work-reconciliation-v20` profile has 17 completed
jobs and 31 Qwen calls (1.82 calls/job); six jobs used bounded repair (35.3%).
The original `v8` workload recorded 106 completed jobs and 332 calls (3.13
calls/job), with 79 jobs using repair (74.5%). The current four-row production
batch therefore reduces observed calls and repair incidence. It does not yet
solve coarse job latency: individual reconciliation jobs may still contain
multiple sequential calls before model-slot fairness can move to another
workspace.

A final independent service-wing waterproofing control was generated and
visually checked only after source and migration `0095` were frozen. The input
PDF SHA-256 values are:

- `N15_service_wing_design.pdf`:
  `b18fcff84c44e151a80943144ed35cc19907eb06db3071c27944f667c7efd8ba`;
- `P27_material_register.pdf`:
  `c7759c623c393e06d26c20e9c0fdb94a89e53fffe611188dd4b5f8ffe82e1266`;
- `Q39_commercial_schedule.pdf`:
  `94112a5064c3077ac61d62396eb9dbf1542c48e51d90f28ee1de63efa976e5b9`;
- `R51_request_terms.pdf`:
  `9986b6d1855d230753a131c59ff25647c4ec4837e94e3c3f3f99ee90dbbd7e67`.

The external oracle remains outside the uploaded input. Normal application
admission created workspace `01a0f64d-728e-718e-bb0a-49bf73738e42` with
manifest digest
`sha256:f04a582bd6f62af37fc4394fa7981f842ca51862ff6a1a2963147bf3b3550dae`
and records zero manual progression commands. Supervised services independently
admitted and interpreted all four documents (31 of 31 semantic fragments,
zero failed fragments), classified the design, specification and commercial
roles, and extracted the project name, customer, designer, private request-for-
proposals method, payment basis, six-percent security, 30-month warranty and
the distinct 22-working-day and seven-calendar-week duration statements.
At this record point its quantity-relationship and final Tender-analysis jobs
remain queued behind previously admitted incomplete controls. The strict unseen
gate is therefore still open; no comparison with the external oracle has been
made.

Migration `0096_first_fact_fairness` corrects the remaining intake starvation
without privileging any project name, document name, construction family or
expected result. A workspace receives the highest claim tier only until its
first accepted `PROJECT_DEFINITION_EXTRACTION` result exists; deeper semantic
work then returns to the existing model-slot fair-share order. The migration
changes only `workspace.claim_next_durable_job` and does not mutate project or
platform knowledge rows.

Exact-SHA CI run `36930821157` passed for release
`0aaf22580045f44534d10f80a3410a41274f1063`, including PostgreSQL integration,
migration round-trip, browser E2E, dependency security and license checks. The
public database advanced from `0095_incomplete_semantic_fairness` to
`0096_first_fact_fairness` after the existing physical backup and disposable
upgrade/downgrade/re-upgrade test. A byte-for-byte `platform` schema data dump
around the production migration remained exactly
`b5bc08de8c258a5829003644671d936785c57cd3a6c5b1e5d557c51df854dc82`;
the NTD job state remained exactly `319 succeeded`.

API, assistant worker and project orchestrator were switched first to the
pinned release
`~/.asd-kontur/public-demo/releases/20261002-0aaf225-first-fact-fairness`.
The document worker's existing Qwen reconciliation was not interrupted: its
graceful stop handler completed job
`01a0f619-f716-7583-8dee-5f7a0f06203c` successfully at
`2026-10-02T10:52:00+12:00`, exited at the safe boundary, and relaunched from
the same pinned release. Readiness then returned HTTP 200 on migration `0096`.
Persistent Qwen PID `90242` and NTD worker PID `98263` were not restarted. The
new worker immediately completed additional project-definition jobs under the
new ordering and continued autonomous reconciliation without a manual queue or
successor command.

## Remaining implementation work

- complete and fingerprint the final post-`0095` service-wing control, then
  compare its frozen result with the external oracle;
- improve project entity consolidation, especially the 185 blind-project
  quantities without a sufficiently grounded structure link;
- reduce strict-output repair without weakening semantic validation;
- run signed-in visual browser acceptance when an in-app browser session is
  available, and test the supported Mac sleep/wake boundary.

Current status: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Commercial comparison recovery checkpoint — release 9c57aa6

The next regression-register slice repaired three generic bridges that were
preventing accepted project facts from becoming a professional commercial
result:

1. `Смета контракта` now participates in the same centralized commercial-role
   policy as VOR and estimate sources for quantities, materials and work scope.
2. An explicit reviewed Qwen `SAME_SCOPE` relationship between source quantity
   identities can establish the comparison boundary even when an unlocated
   work group contains several observations. Labels and numeric similarity do
   not establish this authority.
3. A facility-bound commercial work scope without an established design basis
   now becomes a professional issue, customer question and contractor risk.
   Material differences without an established location are deliberately
   qualified as possible differences and require location confirmation first.

No project name, project code, document filename, known blind-project value or
expected finding was added to runtime code. Generic regression cases vary
project names, structures, source roles and values. A production-code search
found no OZERO or current blind-project identifiers in `src`, `frontend`,
`contracts` or `migrations`.

On the frozen blind project, model `project-engineering-model-v58` now contains
four quantity comparisons (three construction quantities and one duration),
15 material comparisons and four professional issues/questions/risks. The
independent `BLIND_TENDER_ANALYSIS_SNAPSHOT_v3` was persisted before any owner
comparison with model fingerprint
`sha256:3731259a4fc3f1e3344dae474017fa286dd3a489535c1e21394424ee166f5c56`
and manifest SHA-256
`be09ee67613a3ff48d232ef5372f18ad13090899d14af51164c3ebfb92df86e4`.
The snapshot includes the structured model and editable primary Tender and
contract-analysis DOCX artifacts; both DOCX packages passed OOXML validation
and the primary report passed macOS Quick Look rendering.

Exact-SHA CI run `37022885723` passed for
`9c57aa60deaa3bd23976b2d156f8d46c2d408073`. API, document worker, project
orchestrator and assistant worker run from the immutable release
`~/.asd-kontur/public-demo/releases/20261003-9c57aa6-tender-commercial` on
migration `0107_contract_directed_change_risk`. Qwen PID `93554` and NTD worker
PID `98263` were not restarted; the NTD job ledger remains exactly
`319 succeeded`. Autonomous blind-project progress increased from 1,191 to
1,204 effective succeeded jobs across the release window and Qwen immediately
continued receiving work from the supervised runtime.

The in-app browser connector had no available browser instance at this
checkpoint, so a signed-in visual pass is not claimed. Readiness, live service
projection, structured project result, artifact generation and autonomous
continuation were verified directly. The P1 capability remains incomplete
because 904 source work descriptions remain unclassified and facility
association is still sparse.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Exact pair authority — read-side release 84b72a5

Engineering model v77 closes a comparison-authority defect without changing
the semantic queue or restarting the local model. For the current v32 semantic
profile, a top-level `SAME_SCOPE` value no longer authorizes an arbitrary
design/commercial pair: the two exact quantity candidates must carry reciprocal
pair-specific `scope_assertions` with `SAME_SCOPE`. Historical accepted profiles
retain their compatibility path.

The blind workspace continues to expose 10 quantity comparisons, 4 material
comparisons and 2 professional issues under v77; the stricter rule removed no
currently accepted result. API and assistant projections run from immutable
release
`~/.asd-kontur/public-demo/releases/20261004-84b72a5-pair-authority-v72`.
The document/project worker and autonomous orchestrator remain on v71 while
their pre-existing bounded v32 queue drains, so the active Qwen generation was
not interrupted. Qwen PID `85702` and NTD worker PID `98263` were preserved.

Exact-SHA CI run `37128256620` passed. Migration head remains
`0119_pair_specific_quantity_scope_profile`. The release receipt SHA-256 is
`912ec45934c1eda466487b6f2ad82f17e239c13957680fd2ee70397887f449ea`.
The all-history platform-memory and canonical NTD fingerprints remain
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`
and
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
the NTD ledger remains exactly 319 succeeded jobs. No manual queue, retry,
successor, priority or Qwen command was issued.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Pair-specific quantity scope and live persistence repair — release 0c6f880

The user-visible result is that one quantity may now participate in several
independent engineering comparisons without a later review erasing an earlier
valid decision. For example, a commercial total can remain comparable with the
matching estimate scope while being explicitly non-comparable with an unrelated
design component. The model stores scope compatibility on the exact quantity
pair and requires reciprocal Qwen assertions. Deterministic comparison consumes
that pair ledger and continues to perform all arithmetic itself.

Commit `19c729081832194cd6b4fe5b81803c21eaa5557d` introduced semantic profile
`qwen-project-work-reconciliation-v32` and engineering model
`project-engineering-model-v76`. Its first public activation exposed a release
defect before acceptance: the database profile constraint still ended at v31,
so valid v32 manifests reached Qwen but failed persistence with a PostgreSQL
check violation. Those immutable failures remain recorded as
`reconciliation_required`; they are not counted as accepted semantic results.

Commit `0c6f880fc310eaf6f484409c9943e45a95079a0c` adds migration
`0119_pair_specific_quantity_scope_profile`. The public database was backed up
to
`~/.asd-kontur/public-demo/backups/asd_kontur_public_demo_pre_0119_20261004T013300.dump`
(SHA-256
`bd3b19ed6fe6c379bb4f937fbcaed35c13180d24536d90cb0984f4260ef931b2`),
restored separately as `asd_kontur_restore_0119_20261004`, and exercised through
`0118 -> 0119 -> 0118 -> 0119` before controlled public migration. The migration
changes only the accepted reconciliation-profile allowlist; it does not rewrite
project or platform knowledge.

The first result executed entirely after the migration boundary, job
`01a101f3-1776-76b6-bb1b-15d407f8cc01`, succeeded autonomously. Its validated
manifest contains reciprocal `DIFFERENT_SCOPE` assertions for a pipeline-branch
component and a commercial total whose pipe profiles differ. This is a live
false-positive rejection from the independent control corpus, not a hardcoded
expected answer. The blind workspace is already materialized as
`project-engineering-model-v76` with fingerprint
`sha256:45edbda2b402ab9837cf14d8747fed686df0f63fc6c7e5f329ab9e92ecfaf7b4`;
its four targeted v32 reviews remain in the fair autonomous queue at this
observation, so no new blind-project pair decision is claimed yet.

The active immutable release is
`~/.asd-kontur/public-demo/releases/20261004-0c6f880-pair-scope-v71` with
release profile `tender-pair-scope-v71-model-v76`. Exact-SHA CI run
`37126829569` passed; 1,235 local unit tests and the isolated migration
round-trip passed. Qwen PID `85702` and NTD worker PID `98263` were preserved.
The release-receipt SHA-256 is
`eb22589d7ad1fab6d274bbaefe9605f148e17c6247ec3264c50c11efa3e49e36`.

The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the canonical NTD fingerprint remains exactly
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains exactly 319 succeeded jobs. No developer queue,
retry, successor, priority or Qwen command was issued.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Current-profile comparison authority — engineering model v77

Engineering model v77 closes the remaining deterministic fallback behind the
pair-specific v32 semantic contract. A quantity interpreted by the current
profile can authorize design/commercial or VOR/estimate arithmetic only when
the two exact quantity identities carry one reciprocal `SAME_SCOPE` assertion.
The legacy top-level compatibility field describes the last bounded model
context and can no longer stand in for that exact pair. Historical accepted
profiles retain their existing compatibility behavior; this change neither
rewrites their output nor schedules inference.

The first blind v32 result was inspected before this correction. It properly
kept asphalt-cover demolition distinct from block-wall demolition and therefore
did not need a pair assertion. The defect was the latent fallback for a future
current-profile row that reused identical scope text without identifying its
peer. A changed pipeline fixture now proves that such an unasserted pair is
rejected, while reciprocal current-profile assertions remain comparable and
unit-normalized arithmetic remains deterministic.

At the 2026-10-04 02:00 +12 observation boundary, the supervised v32 refresh
had 13 successes, one actively generating job with a fresh heartbeat, 40
queued jobs, and ten historical pre-migration reconciliation-required attempts.
The blind workspace had one completed and three queued targeted reviews. The
runtime was left autonomous: no manual queue, retry, successor, or priority
command was issued.

## Component/total and material-scope safety — release e6c561a

The blind project now contains a defensible quantity graph for tree removal:
the design identifies 37 trees in the 14.1–18 cm band and 24 trees over 20 cm,
while the commercial scope states a total of 61 trees. Qwen established the
`COMPONENT_OF` / `TOTAL_FOR` relationships; deterministic Decimal arithmetic
calculated `37 + 24 = 61` and returned `MATCH`. The model did not perform the
arithmetic.

The same live workload exposed three generic false-positive paths. Release
`e6c561aa34b8c0b925a0682578276f7d592f002f` now rejects a direct
component-to-total comparison unless an explicit quantity graph exists,
prevents natural subjects of work (such as felled trees) from becoming
construction materials, and requires item identity before comparing unresolved
utility materials. The latter prevents unrelated pipe or drainage items from
being compared merely because they share a broad material family. Controlled
structural-steel synonyms and explicit component/total graphs remain usable.

The active blind projection is `project-engineering-model-v75`, fingerprint
`sha256:d9b91040d8cacda20492909d01fa7ee8ad2a7f62c89ecc50c954f9c010c2b05d`.
It reports 550 of 789 construction observations classified (69.7%), 330
accepted work quantities, ten quantity comparisons, four material comparisons
and two professional findings. The remaining findings are the 2.2-month versus
4-month duration difference and the commercial soil-loading scope that is not
yet linked to design. The false tree-material and unresolved utility-material
findings are absent.

The immutable public release is
`~/.asd-kontur/public-demo/releases/20261004-e6c561a-scope-safety-v69`.
Exact-SHA CI run `37123195390` passed, as did the 1,231-test local unit suite.
A controlled worker restart was followed by an autonomously claimed
cross-document job; no developer queue, retry, successor, priority or Qwen
command was issued. Qwen PID `85702` and NTD worker PID `98263` were preserved.
The release receipt SHA-256 is
`be344b7aeb9b06a8f5e959ab7c3ea24a83f6e1d10c1cd1d7277740b24820983b`.

The platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the canonical NTD fingerprint remains exactly
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains 319 succeeded jobs.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Commercial work denominator cleanup — release c00a938

Release `c00a938f6acf9ca0e2989776ac7398874051daa7` separates construction
operations from estimate accounting/resource rows before work-scope comparison.
The generic filter recognizes coded estimate resources, labour/FOT/reserve
rows, material-only rows, LSR/LRS/table headings and project/structure headings.
It preserves every raw observation and keeps source-grounded materials in the
material schedule. A validated Qwen `MATCHED` construction decision takes
precedence, so a row is not removed merely because it also names a material.
No project name, document filename, facility, quantity or expected omission is
encoded in the rule.

The live blind projection now contains 794 construction-scope observations:
545 are classified and 249 remain unclassified, for 68.6% construction-scope
classification. It excludes 1,301 accounting/resource/non-work observations
from the work denominator while retaining 575 material scopes. Only one VOR
operation remains unclassified: `Установка лотков водоотводных`; it remains
eligible for autonomous Qwen classification rather than being suppressed.
The projection retains nine compatible scope matches, one grounded
commercial-only work, nine quantity comparisons, eight material comparisons,
seven professional issues, seven customer questions and seven contractor
risks. No design-work omission is claimed yet because the remaining
design/commercial scope is not sufficiently resolved.

Exact-SHA CI run `37119074830` passed. The active immutable release is
`~/.asd-kontur/public-demo/releases/20261003-c00a938-commercial-scope-v66` at
migration `0118_source_grounded_alternative_profile`. The first activation
check detected that a copied editable virtual environment still pointed at the
v65 source tree. No acceptance claim was made from that process state; the
release-local editable source pointer was corrected, the four application
services were restarted, and the imported module path plus
`project-engineering-model-v74` were then verified. Qwen PID `85702` and NTD
worker PID `98263` were preserved throughout.

After activation the autonomous worker resumed
`PROJECT_WORK_RECONCILIATION`; the observed ledger had 3,083 succeeded jobs,
18 queued jobs and one running job, while Qwen reported 50 completed requests
and `QWEN_GENERATING`. No manual queue, retry, successor or priority command
was issued. Platform memory remained exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
canonical NTD memory remained exactly
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`,
and the NTD ledger remained 319 succeeded jobs. The release receipt is
`~/.asd-kontur/public-demo/releases/20261003-c00a938-commercial-scope-v66/release-receipt.json`
with SHA-256
`41d89abc609defb0936cfcb029ccdb77b482593956094502817673bd7fcfb1e6`.

Current status remains: `ContractAnalysisOperational=true`,
`ProtocolOfDisagreementsOperational=true`, `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Commercial first-pass throughput and multi-relationship quantity safety — release ec4d232

Releases `d8dcd3c` and `679fc38` separated the independent first-pass lane from
the two-row relationship lane. A first-pass batch may now contain four
independent descriptions, and localized VOR roles receive product-value
priority over estimate accounting tails. The first autonomous four-row batch
contained two VOR and two PD descriptions. It classified valve installation,
relocation of a 300 mm steel water pipeline, retaining-wall reinforcement and
construction of a new bored-pile retaining wall in 74.432 seconds with one
inference call and no repair. A second four-row batch retained four
construction operations in 81.581 seconds after bounded validation repair.
No developer queue, retry or priority command was issued.

The same live run exposed a false-positive boundary in the generic quantity
graph. Persisted semantic reviews contained `772.5 m3` as a stated excavation
total, `656.6 m3` as one component and `115.9 m3` as another related measure.
One review listed only the 656.6 component on the total row, while a separate
review related the 115.9 value to the total. A later cross-document pass then
replaced that component relation with a valid `DUPLICATE_OF` relation. The
projection consequently emitted an unsupported `115.9 m3` mismatch.

Commits `7e3fa70` through `ec4d232` correct the generic failure without
encoding any project quantity. Reviewed quantity relationships are now
retained as a set: one statement may be both a component of a design total and
a duplicate of a VOR/estimate statement. Deterministic component/total
arithmetic closes only explicit reviewed reciprocal links. Facility, unit,
revision and engineering-scope compatibility still have to pass. On the live
blind project the current graph does not establish a compatible complete
component set, so model `project-engineering-model-v73` suppresses the false
comparison instead of presenting either a mismatch or a manufactured match.

The blind application now exposes six grounded quantity matches: crushed-stone
base VOR/estimate `65.4 m3`, metal fencing PD/VOR `219 m`, reinforced-concrete
demolition VOR/contract estimate `119.83 m3`, manual excavation VOR/estimate
`115.9 m3`, vegetation-layer removal PD/VOR `370 m2`, and drainage collector
VOR/estimate `219 m`. It also retains the independently established `2.2`
versus `4` month duration mismatch. The projection contains 559 classified
construction observations, 392 unclassified observations, 338
facility-associated observations and 332 accepted work quantities. It does
not yet contain a defensible design-work omission or a price-bearing estimate
delta; those results remain open product work.

Exact-SHA CI run `37117638337` passed for
`ec4d23220872f7ad8417a08185f6da3b211f2ef6`. The immutable active release is
`~/.asd-kontur/public-demo/releases/20261003-ec4d232-quantity-relations-v65`
on unchanged migration `0118_source_grounded_alternative_profile`. API,
document worker, assistant worker and project orchestrator run from that
release. Qwen PID `85702` and NTD worker PID `98263` were preserved. Two jobs
crossing controlled worker activation were reclaimed from expired leases and
completed autonomously with one accepted result row each; no manual recovery
command was used.

The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
the canonical NTD fingerprint remains
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`,
and the NTD ledger remains exactly 319 succeeded jobs. The release receipt
SHA-256 is
`f7d5fb145e0fa72bd5b1b5a7893131579026ddd4e060dd3ba60b2ae524843e5b`.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Guaranteed first-pass semantic progress — release db05be8

The live blind workspace still contained 411 construction descriptions without
any current-profile semantic decision. The previous scheduler nominally
reserved one of four refill slots for ordinary classification, but that slot
was filled from a mixed priority pool and could select a fourth relationship
batch. Quantity and cross-document work could therefore keep first-pass work
starved indefinitely.

Commit `db05be8dcb46b96d993f2377207aa3e1229806a1` makes the reserved lane
structural rather than nominal. Three slots remain available to high-value
relationship and cross-document review. When never-reviewed construction work
exists, the fourth slot is selected only from rows whose
`classification_review_needed` value is true, with the existing source,
duplicate-wording and quantity-context bounds preserved.

The immutable v61 release autonomously created four blind-workspace batches at
`2026-10-03T21:37:43.348518+12:00`: three relationship batches and job
`01a10120-8262-7517-81ba-5b0996e51c65`, containing two never-reviewed rows in
the reserved lane. Qwen completed that job without a developer queue, retry or
priority command. The resulting application model changed as follows:

- classified observations: 547 to 548;
- unclassified observations: 411 to 410;
- facility-assigned observations: 328 to 329;
- accepted work quantities: 323 to 327;
- model fingerprint:
  `sha256:8758837da3de48f8ad331e125133fe19455b7302c88e314b63def42c039e5891`.

The active immutable release is
`~/.asd-kontur/public-demo/releases/20261003-db05be8-first-pass-v61`.
Exact-SHA CI run `37112383798` passed. Migration head remains
`0118_source_grounded_alternative_profile`; Qwen PID `93554` and NTD worker PID
`98263` were preserved. The all-history platform-memory fingerprint remains
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
all 26 critical platform/NTD table counts equal the deletion-safety baseline,
and the NTD ledger remains exactly 319 succeeded jobs. The release-receipt
SHA-256 is
`36aebe9329dacd291e2cae6db35425dfad0e388e18f324d239983c0f81282d46`.

The classification denominator is still materially incomplete, and this
release does not create a new omitted-work claim. The next product step remains
a defensible VOR/estimate delta or omission derived from compatible scopes.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Project-wide VOR/estimate comparison — release 4db8b11

Commit `4db8b114a8c32dc92eb740f76af7e40d7c84152a` advances the next
contractor-facing task: compare established project-wide commercial scopes
without inventing a facility allocation that the source does not contain.
The source-context classifier now recognizes extended official VOR headings,
including headings in which “ведомость объемов” and “работ” are separated by
the described construction content. An explicit project-wide location is an
established comparison scope, while a merely unresolved location remains
ineligible. Already-normalized units and their Russian source forms are reduced
to the same deterministic unit before arithmetic.

The live blind-project model is `project-engineering-model-v70`, fingerprint
`sha256:1d70ffd1ed96397307559df9a95f487ba71119df1552ec40cc47f8d73abbc48b`.
It now presents 143 project-wide commercial work scopes and 115 work scopes
whose location remains unresolved. Four real construction comparisons are
available through the application:

- crushed-stone base: VOR `65.4 m3` and estimate `65.4 m3` — match;
- shrub removal: VOR `8 items` and estimate `8 items` — match;
- metal fence at the established `63/1` structure: design `219 m` and VOR
  `219 m` — match;
- drainage collector: VOR `219 m` and estimate `219 m` — match.

The result is useful even though it contains no new discrepancy: it proves that
the same-scope denominator exists and tells the engineer that these four values
agree. Numeric equality, similar labels and a shared document do not establish
scope. A changed regression case with identical values but different semantic
scope is rejected rather than emitted as a false comparison.

The release was activated only after the document worker reached a boundary
with no leased or running job. API, document/project worker, assistant worker
and project orchestrator now import the immutable release
`~/.asd-kontur/public-demo/releases/20261003-4db8b11-vor-estimate-scope-v58`.
Qwen PID `93554` and NTD worker PID `98263` were preserved. No queue, retry,
successor, priority or Qwen command was issued. Exact-SHA CI run `37107291207`
passed. The release-receipt SHA-256 is
`f71160287786561369da9ab1c8f1598f0eb067a27b4c7b2c271d2127f2454f6a`.

The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the canonical NTD fingerprint remains exactly
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains exactly 319 succeeded jobs.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Commercial estimate scope cleanup — release b8b7a9f

Commit `b8b7a9f945c3ed6b311713a1f554959c9e4e1a9a` closes a generic
commercial-scope defect exposed by the blind project. Estimate accounting
rows—totals, subtotals, direct-cost summaries, payroll/overhead/profit lines
and estimate norm references—were being presented as unclassified
construction work. The deterministic classifier now excludes those rows while
retaining actual construction operations and material positions. This reduced
the blind project's unclassified set from 904 to 411: 493 false work rows
were removed without inventing a work classification.

The commercial-document context parser now recognizes full-form local estimate
headings, not only abbreviated LSR/VOR labels, and retains the nearby project
heading. When a heading explicitly addresses several facilities, the model can
represent one project-wide commercial scope. It does not distribute that scope
or its quantities among individual facilities unless the source does. The live
v69 projection consequently contains 121 project-wide commercial work scopes
and 135 scopes whose location remains unresolved. It produces one
commercial-only comparison, six matches and 265 unresolved scope matches. No
new omitted-work finding is claimed: the commercial documents name both
addressed walls but do not provide a defensible wall-by-wall allocation.

Focused project-engineering validation passed 147 tests, the unit suite passed
1,209 tests, and mypy passed all 235 checked source files. The full local suite
passed 1,210 tests with 113 skips; its only unavailable gate required the
absent `ASD_TEST_DATABASE_URL`. Exact-SHA CI run `37106155942` passed every
backend, frontend, browser, security and migration gate.

The immutable active release is
`~/.asd-kontur/public-demo/releases/20261003-b8b7a9f-estimate-scope-v57`.
Migration head remains `0118_source_grounded_alternative_profile`. API,
document/project worker, assistant worker and project orchestrator all import
the release commit. Qwen PID `93554` and NTD worker PID `98263` were preserved.
The release-receipt SHA-256 is
`3e7095c14982728a95fb1a24fa0d9e163a17ab9c0eabfb8c3a1cd9f55ce089ed`.

The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the canonical NTD fingerprint remains
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains exactly 319 succeeded jobs. No developer queue,
retry, successor, priority or Qwen command was issued.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Explicit project-wide commercial membership — release b2329f4

Commit `b2329f4d9534cdec488661d2015db3932843e0b3` closes a generic scope-linking
gap in the design-to-commercial comparison path. A commercial heading that
explicitly names every established addressed facility is now retained as one
project-wide scope with the exact member facility identities. This membership
can establish that a design operation is present commercially for a named
facility, while the quantity remains project-wide and is not allocated between
facilities without source support.

The live blind-project v71 projection contains 275 consolidated work scopes.
Of these, 142 commercial scopes carry the exact two-facility membership from
their source heading. The scope comparison now contains 10 `MATCH` results,
264 unresolved scope matches and one commercial-only work. In particular, the
design excavation and pipeline-installation scopes for retaining wall 63/1
are now shown as present in the explicit two-facility commercial scope. The
Russian application conclusion states that the commercial quantity has not
been allocated between structures. No omitted-work finding is generated from
the still-incomplete commercial denominator.

This is a direct professional improvement: the user can distinguish “work is
present in the common commercial scope” from both “work is omitted” and “the
commercial quantity is allocated to this facility.” It does not close the
broader VOR/estimate delta regression because 411 work descriptions remain
unclassified and a defensible omitted-work denominator is not yet complete.

Exact-SHA CI run `37110891575` passed. The active immutable release is
`~/.asd-kontur/public-demo/releases/20261003-b2329f4-commercial-members-v60`.
All four application services run the exact commit; Qwen PID `93554` and NTD
worker PID `98263` were preserved. After activation, the supervised worker
autonomously claimed job `01a100f2-f475-7422-87b3-bd65f589e62f`; no developer
queue, retry, successor, priority or Qwen command was issued.

The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`.
All critical NTD/platform counts are exactly equal to the preserved deletion
baseline, including 319 succeeded NTD jobs. The canonical NTD root remains
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`.
The release receipt SHA-256 is
`4aed664951bdee6e221c76a3f0df6de64b95381f7b4bb34def6f76d678560af9`.

Current status remains: `ContractAnalysisOperational=true`,
`ProtocolOfDisagreementsOperational=true`, `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Cross-document scheduling and serialized refill — releases v30–v36

The blind-project queue exposed two generic barriers between accepted quantity
meaning and an engineering comparison. First, professional source roles were
not consistently reduced to design and commercial comparison sides, and a
commercial filename could be weakened by an earlier generic role. Second,
settled quantity observations were excluded from a later cross-document pass
because their single-source semantic review was mistaken for proof that their
relationship to another source had already been reviewed.

Commits `6c7734e`, `123338a`, `2e3d570`, `65c29d7`, `7b54c18`, `ac05ced` and
`aeb60ce` correct those generic selection rules. The scheduler now recognizes
professional Russian document roles, preserves the stronger commercial role,
reuses settled quantities as bounded semantic context, prioritizes
design-commercial pairs within the same construction family, and keeps Qwen
responsible for deciding whether the two scopes are actually comparable.
Numeric similarity is never a scheduling or compatibility signal.

The first autonomous mixed-source batch under this policy compared a design
drilling count with a commercial Far North percentage. Qwen correctly returned
`DIFFERENT_SCOPE`; no quantity discrepancy was created. A later autonomous
`\u041f\u0414`/`\u0412\u041e\u0420` batch for asphalt-cover demolition established a
`COMPONENT_VS_TOTAL` relationship and identified the transmitted `127.2 m2`
value as a component of the stated `274.7 m2` total while explicitly noting
that the other `147.5 m2` component was absent from the bounded batch.
Deterministic arithmetic remains responsible for any eventual consistency
decision.

Runtime observation also found a scheduler race: the completion hook and the
orchestrator safety sweep could both observe an idle workspace and each create
four jobs. Commit `3a4c205067c67ab83293d7a1bf188e99104e85d8` serializes the
refill decision with the existing transaction-scoped advisory lock and repeats
the idle check inside that lock. Exact-SHA CI run `37077883733` passed.

Release `tender-refill-lock-v36-model-v65` is active from
`~/.asd-kontur/public-demo/releases/20261003-3a4c205-refill-lock-v36` at
migration head `0111_reviewed_quantity_source_value`. The last v35 worker job
was allowed to persist its terminal receipt before the worker switch. The first
and second autonomous v36 refill cycles each created exactly four jobs, rather
than the previous duplicated set of eight; Qwen claimed the jobs without a
developer queue, retry or successor command. The first v36 cross-document
result is job `01a0feff-6a03-7b3d-bfbe-6b9b7b0ed009`, result digest
`sha256:385b6f9303a9d3b5dd7b3d7bed9c40e58d39d74e43d93aa8a6ea88216865882e`.

Qwen PID `93554` and NTD worker PID `98263` were not restarted. The platform
memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
and the NTD ledger remains exactly 319 succeeded jobs. The v36 release receipt
SHA-256 is
`e0a1969f90e1c27216866460eded1cf3237f7c486c40b59c35b6fb1150c51c18`.

This closes the observed refill race and proves autonomous mixed-source scope
review. It does not yet prove a complete generalized Tender result or the
independent unseen-project gate. Current status remains:
`GeneralizedTenderHarness=false`, `AutonomousProjectProcessing=true`,
`ProductReady=false`.

### Deployment verification correction for v36

Post-activation source-path verification found that the v36 virtual
environment had been copied from v29 and its editable package pointer still
resolved `asd_kontur` from the v29 release directory. The launchd executable
and frontend paths named v36, but the Python application source did not.
Consequently, the preceding v36 runtime observations prove autonomous queue
behavior under the older source tree; they do **not** prove that commit
`3a4c205067c67ab83293d7a1bf188e99104e85d8` was active. The original immutable
receipt was preserved, and a separate
`deployment-verification-addendum.json` records
`FAILED_SOURCE_TREE_PIN`. No history or runtime data was rewritten.

The corrective v37 release was built from Git archive commit
`27372c90c841f5f476138a636c5af22290f1c30a` with a fresh locked environment.
After moving the staged release into its final immutable path, the editable
package was explicitly reinstalled there and verified to import from
`~/.asd-kontur/public-demo/releases/20261003-27372c9-relationship-transition-v37/src`.
All four supervised application roles now use that exact release and report
the exact commit. Exact-SHA CI run `37079521270` passed. Qwen PID `93554` and
NTD worker PID `98263` were preserved.

The v37 scheduler then autonomously created four dedicated two-row quantity
relationship batches for the blind project. Every batch carried
`relationship_review_needed=true`; the selected role pairs were two
`ПД`/`ВОР` pairs and two `ПД`/`Смета` pairs. No developer queue, retry,
successor or priority command created those jobs. This is the first valid
runtime evidence for the current-profile transition that makes accepted
single-source quantity meaning eligible for a later cross-document
relationship review. Qwen remains responsible for refusing unrelated scopes;
the scheduler does not infer compatibility from equal units or numeric values.

API readiness passes at migration head
`0111_reviewed_quantity_source_value`. The all-history platform-memory
fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the lifecycle platform fingerprint remains
`sha256:02cb45f341ad56595bbe6ec59abe5fbadac7841914280b165ed99861923e8487`;
the canonical NTD fingerprint remains
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains exactly 319 succeeded jobs. The corrective v37
release receipt SHA-256 is
`f68725a37440135560467bc6184b402b76254bd9cfdffb42502f3f81ea606853`.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Source-grounded alternative decisions — profile v31

Live autonomous acceptance of profile v30 exposed a generic semantic boundary
defect. In the independent steel-gallery control workspace, Qwen correctly
established the design component/total relationship and deterministic Decimal
arithmetic produced a 0.7 t internal mismatch. The same bounded context also
contained a 13.2 t design total and a 12.0 t commercial total, but Qwen called
them alternative designs solely because the values differed. The prompt
already prohibited that inference; the result validator did not enforce it.

Profile v31 adds two deterministic acceptance checks without deciding scope
compatibility itself:

- `ALTERNATIVE_TO` or `ALTERNATIVE_DESIGN` requires explicit source language
  identifying a variant, alternative, or replacement in the bounded source
  context. A numeric difference is never evidence of an alternative.
- rows assigned the same normalized `semantic_scope` and `SAME_SCOPE` must use
  the same normalized construction operation.

Either violation rejects the full bounded response with a typed code and gives
Qwen one full-context repair. The repair may establish `SAME_SCOPE`, preserve
an explicitly documented alternative, or leave the relationship unresolved;
deterministic code does not choose among those outcomes and still performs all
arithmetic only after accepted semantic authority.

The v30-to-v31 scheduling transition is deliberately narrow. Settled v30
quantity and cross-document scope decisions remain compatible. Only rows that
carry `ALTERNATIVE_TO` or `ALTERNATIVE_DESIGN` are eligible for autonomous
re-review, preventing a new full-corpus replay while repairing the exact class
of unsafe decision. Generic tests use changed structures, work descriptions,
values, and units; they also prove that a source which explicitly names an
alternative remains an accepted non-comparable scope.

Commits `3f0218f305d7a69e3fa95d26c9ae3b1f702db4ec` and
`c899b317e57ed4bd074792078d1c9a1a84748805` passed exact-SHA CI run
`37103729010` and are active as immutable release
`~/.asd-kontur/public-demo/releases/20261003-c899b31-alt-evidence-v55`.
Migration `0118_source_grounded_alternative_profile` was exercised as
upgrade/downgrade/upgrade on separate restored database
`asd_kontur_restore_0118_20261003` before public activation. The production
backup SHA-256 is
`a4980634ff8ccff26390ef08d1772fb941bd53d01ea9246e0550db000d26216b`.

The application worker's in-flight v30 lease was recovered automatically
during activation and terminated with the typed supersession outcome. The
supervised orchestrator created the targeted v31 queue without a developer
queue, retry, priority, successor, or Qwen command. At the release receipt,
two v31 jobs had succeeded, one was running and 47 were queued. Qwen PID
`93554` and NTD worker PID `98263` were preserved. The release receipt SHA-256
is `2d42a192e7923fa007d1ed7974e5874cc1bea68912370c1f67045336972f7d70`.

The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the canonical NTD fingerprint remains exactly
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains exactly 319 succeeded jobs. The OP-73 and real blind
target v31 results remain in the fair autonomous queue, so no repaired
cross-document comparison is claimed at this checkpoint.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Quantity relationship closure and first blind discrepancy — release v40

The accepted single-source quantity bridge produced two materially different
professional outcomes on the blind project without owner-provided expected
values. Qwen first established that the project and estimate values for
mechanized excavation describe the same engineering scope. Deterministic
comparison reported a match: `772.5 m3` in both sources. The system therefore
showed agreement instead of manufacturing a Tender defect.

A later autonomous `ПД`/`Смета` review established that the two tray LM-2
lengths describe the same scope. Deterministic arithmetic then found:

- project: `87 m`;
- estimate: `100 m`;
- commercial excess over the project quantity: `13 m`.

The project model generated a typed `QUANTITY_MISMATCH`, explained the
contractor exposure, and proposed asking the Customer either to confirm the
project basis for `100 m` or align the estimate with the `87 m` project value.
The finding retains direct source references to page 11 of
`22.467 - ПЗУ, КР, НВ.pdf` and page 41 of `22.467-СМ.Изм7.pdf`. At the frozen
checkpoint the blind model contained three quantity comparisons, six
professional issues, six customer questions and six contractor risks.

`BLIND_TENDER_ANALYSIS_SNAPSHOT_v6` was persisted before any owner comparison.
The snapshot SHA-256 is
`8f75da8a49ef2eec463f0c0569c10a87ade0212c504240757d71bbbe9a394e06`;
its manifest SHA-256 is
`9cbcba0949a104d07db52f64c17e6e652563109c03f08c39db1f57de8d0e9934`.

The same run exposed a generic scheduling defect: candidate-level relationship
attempt accounting allowed one unrelated rejected pair to suppress a later
comparison with a better counterpart. Commit
`927c4742c2426938b5a5d1118fb897cf3ab4fe0f` changes that ledger to the exact
design/commercial candidate pair. It also ranks bounded Qwen context by
facility, normalized construction wording, previously accepted semantic scope
and physical-unit dimension. Numeric values are deliberately excluded from
pair selection. Weak unassigned pairs with no semantic overlap are skipped;
Qwen still decides whether every selected pair is actually comparable.

Exact-SHA CI run `37082260795` passed. Release
`~/.asd-kontur/public-demo/releases/20261003-927c474-pair-ledger-v40` is active
for all four application roles at migration head
`0111_reviewed_quantity_source_value`. The first autonomous post-activation
Qwen result was RD/VOR structural-steel job
`01a0ff30-23b4-771a-be96-758ade42cfaa`, result digest
`sha256:4765574d48ac88efbf9fe05c749fc761ca7119a347403a11c522a1a39078d633`.
No developer queue, retry, successor or priority command was issued.

Qwen PID `93554` and NTD worker PID `98263` were preserved. API readiness
passes. The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the lifecycle platform fingerprint remains
`sha256:02cb45f341ad56595bbe6ec59abe5fbadac7841914280b165ed99861923e8487`;
the canonical NTD fingerprint remains
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains exactly 319 succeeded jobs. The v40 release receipt
SHA-256 is
`3d0f0d4834e1d4d58b2c9b883b7f94824c1b29a4122af4617b637bb5a72fdd85`.

This closes the zero-real-comparison defect, but it does not yet establish
project-wide design/commercial coverage. Current status remains:
`GeneralizedTenderHarness=false`, `AutonomousProjectProcessing=true`,
`ProductReady=false`.

## Procurement and participant-context checkpoint — release 2d64726

The next P1 slice addresses professional-report contamination that was visible
in the blind result rather than adding a new architecture layer:

- values shaped like personal names from drawing title blocks are no longer
  asserted as customer, designer, developer or contractor organizations;
- formatting aliases within one participant role are consolidated, and
  corroboration counts distinct source documents rather than repeated pages;
- when one participant is corroborated by several documents and competing
  role labels occur only once, the primary table shows the corroborated value
  and the alternatives move to “uncertainties / missing information”;
- schedule dates require a schedule-bearing document role and a complete date,
  month/year or source-relative contract expression, so price-base dates,
  bare years and drawing marks do not become start/completion dates;
- VAT rates written with a percent sign or the word “percent” normalize to one
  rate, numeric VAT amounts remain amounts, and untyped prose is rejected.

The live blind model `project-engineering-model-v59` has fingerprint
`sha256:626cfd8677aa313062c1951f6e2f552049add325a992ee21bb8898ffd45157c6`.
Its primary report now contains four principal participant rows and five
localized participant ambiguities. The independently extracted procurement and
contract facts remain available: price, payment terms, real schedule values,
SRO and experience requirements, execution security and warranty conditions.
The false `8.22`/bare-year schedule values are absent. The independent
`BLIND_TENDER_ANALYSIS_SNAPSHOT_v4` manifest SHA-256 is
`90b45865b162fd5fcc4ecfc737893c1f9d3e028f580d1b426c8dec7b3a2d7352`.

Exact-SHA CI run `37026446815` passed for
`2d64726d96248558b9c543e5fc1aa4d28c5d897a`. API, document worker, project
orchestrator and assistant worker run from
`~/.asd-kontur/public-demo/releases/20261003-2d64726-tender-context` on the
unchanged migration `0107_contract_directed_change_risk`. Qwen PID `93554` and
NTD worker PID `98263` were preserved; the NTD ledger remains exactly
`319 succeeded`. Autonomous blind-project progress reached 1,219 effective
successful jobs immediately after activation, and Qwen continued receiving
work from the supervised runtime.

The v4 primary Tender and contract-analysis DOCX artifacts pass OOXML
validation; the primary report also passes macOS Quick Look rendering. The
browser connector still exposes no available signed-in browser instance, so a
visual authenticated application pass is not claimed.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Professional summary checkpoint — release fab716f

The editable primary Tender report now presents a bounded section named
`Ключевые выводы для участия в тендере` before its long engineering schedules.
The section is assembled only from persisted structured engineering issues and
source-bound contract-analysis issues. It includes each issue's location or
contract clause, professional description and recommended action. Exact
duplicate conclusions are suppressed in the synopsis while their detailed
records remain unchanged.

The real blind-project artifact contains four engineering/commercial
conclusions followed by six distinct contractor contract risks. Both editable
DOCX artifacts passed OOXML validation, and the primary report passed macOS
Quick Look rendering. The independent `BLIND_TENDER_ANALYSIS_SNAPSHOT_v5`
manifest SHA-256 is
`974541e21783a262f6c8060afe16d062b75e7987b037e9c8284ba2b73b3fec3e`.

Exact-SHA CI run `37028408423` passed for
`fab716f53a84a5143e9b87917b8c3b95004dd2cc`. API, document worker, project
orchestrator and assistant worker run from the immutable release
`~/.asd-kontur/public-demo/releases/20261003-fab716f-tender-summary` on the
unchanged migration `0107_contract_directed_change_risk`. Qwen PID `93554` and
NTD worker PID `98263` were preserved. No database or platform-knowledge
mutation was part of this release.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Scaled estimate-unit safety and autonomous profile convergence — release 47d4e63

The next blind-project quantity pass exposed a generic estimate-unit defect.
The source estimate expressed waterproofing in `100 m2`, while the extracted
row value was `8.339`. Treating that row as plain square metres produced a
false 825.561 m2 discrepancy against the 833.9 m2 VOR value. The runtime now
allows Qwen to preserve an exact source unit only when that unit occurs in the
bounded source context, validates the dimension and supported scale
deterministically, and performs the multiplication outside model inference.
Legacy semantic reviews cannot authorize a newly introduced unlocated
same-scope comparison. Until current-profile review is available, the model
keeps the quantity visible but suppresses the professional discrepancy.

The first scaled-unit release was rolled back immediately after the false
finding appeared. Release `6ce5959d3ec8b72be7a2c92cc37a2ffc226154ab`
restored the safe boundary. Live model `project-engineering-model-v61` has
fingerprint
`sha256:076b325e7c292de10f22c629a079fe8357b992cb372e3eff862fbefd01a31e3f`
and publishes only two then-defensible comparisons: the 2.2 versus 4 month
duration difference and the matching 219 m metal-fencing scope. It does not
publish the false waterproofing discrepancy.

Autonomous review could not initially reach profile
`qwen-project-work-reconciliation-v21` because nine unclaimed jobs from v8,
v10, v15 and v20 remained queued and were counted as outstanding work. Commit
`47d4e63cf01ca636ef7d4c5797217b4760280d01` adds durable profile supersession
to the normal reconciliation refill path. It cancels only unclaimed queued
older-profile jobs, writes their cancellation records and terminal receipts,
and leaves running and immutable terminal history unchanged.

Exact-SHA CI run `37034912026` passed. After activating the new orchestrator,
the supervised sweep cancelled all nine obsolete queued jobs at
2026-10-03 04:44:49+12 and autonomously created four v21 batches for the real
blind workspace at 04:44:50+12. No developer enqueue, retry, refill or row
patch was used. API readiness passed on migration
`0107_contract_directed_change_risk`; Qwen PID `93554` and NTD worker PID
`98263` were preserved. The document worker was allowed to finish its active
bounded v21 request rather than being interrupted; its launchd definition is
pinned to the new release for the next controlled restart.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Scaled-unit schema admission and productive-runtime checkpoint — release 01aff39

The first autonomous v21 requests exposed a release-boundary defect rather
than a semantic-model defect. Qwen completed the bounded reconciliation work,
but PostgreSQL migration `0107_contract_directed_change_risk` admitted only
profiles v3 through v20 in
`project_work_reconciliation_results_profile_version_check`. Each v21 result
therefore reached a durable `reconciliation_required` terminal state with
SQLSTATE-family failure code `gkpj`. The model was doing real inference, but
the accepted output could not be persisted.

Migration `0108_scaled_quantity_unit_profile` adds only the current v21
profile to that constraint. A physical public-database backup was written to
`~/.asd-kontur/public-demo/backups/pre-0108-scaled-quantity-20261003T0455/`
with SHA-256
`582cece6273b7fe7644333bb28aa43fe241e8b9120e81eb37287c72e98c80a35`.
A separate restore passed upgrade, downgrade and re-upgrade before the live
database was migrated. Exact-SHA CI run `37037048423` passed for commit
`01aff39f56763581d2a5d70862d1200d1021c134`.

The active API, worker, orchestrator and assistant worker now run from the
immutable release
`~/.asd-kontur/public-demo/releases/20261003-01aff39-scaled-unit-schema`.
Qwen PID `93554` and NTD worker PID `98263` were not restarted. The first
post-migration v21 job, `01a0fd71-6381-7dea-961a-acb52e10ad25`, completed at
2026-10-03 05:06:08+12 and persisted result digest
`sha256:2503c030567c44aedb5dc75c4885f965adc9f1f64cb42aab15095559d47e76f0`.
The worker immediately claimed the next eligible semantic job without a
developer queue, retry or successor command.

The all-history platform-memory fingerprint remained exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`.
The NTD ledger remained exactly 319 succeeded jobs, and the independent NTD
worker remained supervised and unchanged. The release receipt SHA-256 is
`98fb45aebb07391042b6b985205cc7211c777411e1770fbc82f8b8273dd3319c`.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Measured quantity-relationship batch policy — release 96be292

Forty successful production receipts from
`qwen-project-work-reconciliation-v21` established that four-row relationship
reviews were keeping the local model busy with structured-output repair rather
than useful new project interpretation. Across those receipts, two-row batches
completed in one call for all nine measured jobs, averaging 58.1 seconds. The
eleven four-row jobs averaged 249.2 seconds and 2.82 calls; only four completed
without repair. Overall, 40 jobs used 67 model calls, including ten output
exhaustions and seven invalid quantity-output recoveries.

The generic scheduling policy is therefore reduced from four observations to
two while retaining a design/commercial pair in one bounded semantic context.
Profile `qwen-project-work-reconciliation-v22` makes that policy change durable
and lets the existing autonomous supersession mechanism retire only unclaimed
queued v21 batches. Migration `0109_bounded_quantity_relationship_batches`
admits v22 persistence. No facility name, document name, project value or
expected blind-corpus conclusion is encoded in the change.

Focused work-reconciliation, document-understanding and application-spine
tests passed (195 tests), project-engineering and generalized-harness tests
passed (116 tests), and the full migration upgrade/downgrade/re-upgrade gate
passed on a disposable PostgreSQL database. Exact-SHA CI run `37048233741`
passed for `96be2927ca2641674cad2a4e066975a5e88f6d75`.

The public database backup is
`~/.asd-kontur/public-demo/backups/pre-0109-quantity-batches-20261003T0640/public-before-0109.dump`
with SHA-256
`1c7a701d8c2692ed98a89c4d77fb0892acab1655f3401187c201328384ea7d13`.
The real backup passed a separate restore, 0108-to-0109 upgrade, downgrade and
re-upgrade before the live database was migrated.

API, worker, orchestrator and assistant worker now run from
`~/.asd-kontur/public-demo/releases/20261003-96be292-quantity-batch-v22` on
migration `0109_bounded_quantity_relationship_batches`. The running worker was
given a graceful stop request and completed its accepted v21 job before the
release boundary. Qwen PID `93554` and NTD worker PID `98263` were not
restarted. The orchestrator automatically superseded three queued v21 jobs and
created 42 two-row v22 jobs across active workspaces, including four for the
blind project. No queue, retry or successor command was issued manually.

The first v22 job, `01a0fdf2-c814-74c2-947c-d3b801de7309`, completed in
68.974828 seconds with one model call, no repair codes and result digest
`sha256:2a678bcd00b960349e624e3da1e1e2cb24cd5d07f6d8b8fae1a3e0293f4cfc15`.
The worker immediately claimed the next autonomous v22 batch. The all-history
platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
and the NTD ledger remains exactly 319 succeeded jobs. The release receipt
SHA-256 is
`182e2cff782719b35668598d2ab591b7957f2be2eb8967c5780fe71b4b247412`.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## OCR-spaced scaled-unit normalization — release 1b329e4

The first blind-workspace v22 quantity review isolated a generic source-
validation defect. The source page contained the unit text `100 ш т`, while
Qwen correctly returned the professional unit `100 шт`. The deterministic
validator compared only globally collapsed whitespace, so it rejected the
model result four times even though the bounded source context supported it.
The quantity therefore remained unresolved and the productive model spent
five calls on a two-observation job.

Release `1b329e47a8852bb84407772e8856b395d8fa18c5` canonicalizes whitespace
inside the compact OCR unit tokens `шт`, `м2` and `м3` before evidence
validation. It also maps the internal `piece` dimension to `шт`, so code—not
Qwen—can evaluate a supported scaled source quantity such as
`0.6 × 100 шт = 60 шт`. The logic contains no workspace, document, facility or
expected project value. Profile `qwen-project-work-reconciliation-v23` and
migration `0110_ocr_spaced_quantity_units` make the new validation contract
durable.

The public database backup is
`~/.asd-kontur/public-demo/backups/pre-0110-ocr-units-20261003T0715/public-before-0110.dump`
with SHA-256
`988511f62b3a7ea06b6e46e190ef1938b8bfca75a4416bd1ede83b9052b1d154`.
The real backup passed a separate restore, upgrade, downgrade and re-upgrade
before live migration. Exact-SHA CI run `37052684072` passed.

The API, worker, project orchestrator and assistant worker now run from the
immutable release
`~/.asd-kontur/public-demo/releases/20261003-1b329e4-ocr-unit-v23`. Qwen PID
`93554` and NTD worker PID `98263` were preserved. The worker completed its
accepted v22 request before stopping; no model request was interrupted. The
autonomous orchestrator superseded the remaining unclaimed v22 work and
created v23 batches without a queue, retry or successor command.

The first durable v23 result,
`01a0fe12-ee6c-7fe3-abca-0982570706f2`, completed in 46.983643 seconds with
one Qwen call, no recovery codes and terminal result digest
`sha256:8d5cf1a6a8c32d35dce1fbad910a99bc6469a22bc013ecf96060668a09c46bbe`.
The worker immediately claimed the next v23 batch. The all-history
platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
and the NTD ledger remains exactly 319 succeeded jobs. The release receipt
SHA-256 is
`33c3141bdb4a7da240400292366198af8e9ae1d1a861731b9be8bc2456e19e6b`.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Reviewed source-value recovery — release 4499d8f

The live estimate corpus exposed a generic column-alignment defect after the
scaled-unit correction. A quantity candidate could retain the unit-column token
as its extracted value while the actual numeric quantity was present in the
same bounded source row. Profile `qwen-project-work-reconciliation-v24` permits
the semantic reviewer to copy one exact numeric token from that bounded source
context. Deterministic validation requires the returned token to occur in the
source and records both the extracted and reviewed values; deterministic code
continues to perform all scaling and arithmetic. The contract does not permit
the model to derive or invent a corrected number.

Commit `4499d8f1d10cc17f755efe9b3f3eea0198f6c034` passed exact-SHA CI run
`37056211705`. The public backup is
`~/.asd-kontur/public-demo/backups/pre-0111-source-value-20261003T0742/public-before-0111.dump`
with SHA-256
`5fc84a8f1691e3ac97e5e7e3d3ec37a9014d6542598abcfb8be704031ad92882`.
The real backup passed a separate restore, upgrade, downgrade and re-upgrade
before the public database advanced to
`0111_reviewed_quantity_source_value`.

API, document worker, project orchestrator and assistant worker now run from
the immutable release
`~/.asd-kontur/public-demo/releases/20261003-4499d8f-source-value-v24`.
Qwen PID `93554` and NTD worker PID `98263` were not restarted. The supervised
orchestrator superseded unclaimed v23 work and created v24 work without a
developer queue, retry or successor command.

The first durable v24 result,
`01a0fe30-df0d-7063-afce-9e31040f8525`, completed in 46.096338 seconds with
one Qwen call, no recovery code and terminal result digest
`sha256:6750768cfc94a3113ba8a763a64fe7012106840cffd25c4d229b37a9bf23fb63`.
It preserved two distinct waterproofing scopes rather than comparing an area
with a count. During the service drain, launchd briefly respawned the v23
worker before bootout completed; its last request finished in Qwen but the
worker was no longer present to persist it. The durable stale claim was then
terminally accounted for by the normal profile-supersession path as
`work_reconciliation_profile_superseded`; Qwen itself was not interrupted.

The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
and the NTD ledger remains exactly 319 succeeded jobs. The release receipt
SHA-256 is
`d5f3b1d71d63a6ba8c8d5f0895550ada60a75251a4d4cf1a1d95fede1c2112be`.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Reviewed physical-unit authority — release 11c927c

The v24 source-value recovery made a second generic bridge defect visible. A
reviewed quantity could carry an exact physical unit from its bounded source
row while the earlier native extractor retained a truncated unit token. The
project model therefore continued to represent an otherwise understood cubic
volume as a linear measure and correctly refused a cross-document comparison.

Commit `11c927c2a31d64eaee1955c9c34fa617de12de8c` changes only the deterministic
project-model projection. It accepts an exact reviewed unscaled physical unit
from the closed set `м`, `мм`, `м2`, `м3`, `т`, `кг`, `шт`; retains the stricter
scaled-unit rules; and rejects percentage or unrelated units. It does not add
project names, document names, expected values or corpus-specific decisions.
Older semantic results that predate the durable `source_unit` field remain
unchanged until the autonomous current-profile reconciliation revisits them.

Exact-SHA CI run `37059213284` passed. This was a code-only release over the
already qualified migration head `0111_reviewed_quantity_source_value`; the
existing pre-0111 backup and restore/downgrade evidence therefore remain the
database recovery basis. API, document worker, project orchestrator and
assistant worker now run from
`~/.asd-kontur/public-demo/releases/20261003-11c927c-reviewed-unit-v25`.
Qwen PID `93554` and NTD worker PID `98263` were not restarted.

The existing v24 semantic queue continued without a manual queue, retry,
successor or priority command. The first post-activation result,
`01a0fe31-5a6f-7afa-928e-95dd2b7fc502`, completed in 61.901934 seconds with one
Qwen call, no recovery code and result digest
`sha256:f8bf461a64d65cd769d0271e69f1bba57f6670ca0c174ed207bea16d4aa5a89d`.
The worker immediately claimed the next existing batch.

The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the lifecycle platform fingerprint remains
`sha256:02cb45f341ad56595bbe6ec59abe5fbadac7841914280b165ed99861923e8487`;
the canonical NTD fingerprint remains
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains exactly 319 succeeded jobs. The release receipt
SHA-256 is
`c454f902fd051237a9b221da22987abed12c0370462a7fae33d6edc4f1770e9e`.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Reviewed scaled-unit source-pair guard — release fac32ca

The first autonomous blind-project result after the reviewed-unit release
exposed a generic numeric safety defect. The semantic review correctly copied
the exact estimate unit `100 m3`, but it did not return an exact source numeric
token. The earlier extractor had retained an unscaled candidate value and unit.
The project projection combined those independently sourced fields and rendered
the value after applying the scale factor. This produced a false tenfold-scale
professional quantity even though the same semantic result correctly marked the
row as not comparable.

Commit `fac32ca4fa01f97d4400a505ea879d470e3d7341` makes the deterministic
projection conservative. A reviewed scaled unit may replace an unscaled
extracted unit only when the review also contains an exact validated source
value. If extraction already captured the identical scaled unit, retaining that
scale remains valid. Reviewed unscaled physical-unit corrections continue to
work, and percentages remain excluded. This policy is independent of project
names, document names and expected values. The engineering model version is
`project-engineering-model-v65`.

The focused projection suite passed 120 tests, the full unit suite passed 1,136
tests, and exact-SHA CI run `37063552877` passed including PostgreSQL integration
and browser E2E. The immutable code-only release is
`~/.asd-kontur/public-demo/releases/20261003-fac32ca-scaled-unit-guard-v26`;
the migration head remains `0111_reviewed_quantity_source_value`.

The same persisted blind-project observation that previously rendered a false
`10000 m3` now renders conservatively as `100 m3`, retains no invented source
value, and remains `DIFFERENT_SCOPE` until a later semantic review establishes a
valid counterpart. The first autonomous post-activation job,
`01a0fe30-e03d-75f3-a6a8-21769d7484e8`, completed in 54.308102 seconds with one
Qwen call, no recovery code, and terminal result digest
`sha256:b5734a0d65f164938eccfd6390cd33760d0da2f2894ca2f5b90e6688bc381108`.
No developer queue, retry, successor or priority command was issued.

Qwen PID `93554` and NTD worker PID `98263` were preserved. API readiness
passes at migration head `0111_reviewed_quantity_source_value`. The all-history
platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the lifecycle platform fingerprint remains
`sha256:02cb45f341ad56595bbe6ec59abe5fbadac7841914280b165ed99861923e8487`;
the canonical NTD fingerprint remains
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains exactly 319 succeeded jobs. The release receipt
SHA-256 is
`26c8169098e423775a71bb06551f056c998b4d44f2554a6bf059b24d4d2e8403`.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Commercial relationship lanes and exact-pair accounting — release b398c41

The autonomous quantity-relation scheduler no longer assumes that every useful
review crosses only a design/commercial boundary. It now assembles bounded
semantic tasks for design-to-design, design-to-commercial, VOR-to-estimate and
same-source component/total contexts. Role recognition accepts both the
Russian professional labels used by the UI and canonical English document-role
labels used by independent corpora. Numeric similarity remains excluded from
pair selection; Qwen must still establish semantic scope compatibility.

Relationship attempts are recorded by every exact candidate pair supplied to
an explicit relationship task. A rejected pair therefore cannot suppress a
different counterpart, while a completed VOR/estimate or design/design review
cannot be replayed indefinitely. Same-role settled context remains excluded
unless it belongs to one of the explicit professional lanes.

The first autonomously created v42 task reviewed two quantities from one VOR.
Qwen retained both as component areas for different roof slopes and declined to
invent a total or same-scope relationship. Job
`01a0ff40-f6d4-782d-b435-17dd744a8318` completed with result digest
`sha256:f3dacba235ff141bbb91fbe1395a57966bf767d6dcd839408ac6b92c3c0b24bc`.
The blind workspace independently completed post-switch PD/VOR job
`01a0ff3f-de9a-70d2-9386-c9dc5efa4120` and continued through the supervised
queue without a developer progression command.

Commit `b398c41f4c992b39b8864f119dc4a5f91ffcd841` passed exact-SHA CI run
`37083308969` and is active as immutable release
`~/.asd-kontur/public-demo/releases/20261003-b398c41-commercial-lanes-v42`.
The migration head remains `0111_reviewed_quantity_source_value`. Qwen PID
`93554` and NTD worker PID `98263` were preserved. API readiness passes, all
four application services import from the v42 release path, the all-history
platform-memory fingerprint remains
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
the lifecycle fingerprint remains
`sha256:02cb45f341ad56595bbe6ec59abe5fbadac7841914280b165ed99861923e8487`,
the canonical NTD fingerprint remains
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`,
and the NTD ledger remains exactly 319 succeeded jobs. The release-receipt
SHA-256 is
`bea063aaf975c59051832f01394a0ae27456740c2dc313510ba9ccfd61e39ac0`.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Cohesive component/total context — release 42aa6ad

Four incremental commits (`ed9a776`, `0a270b2`, `24a48c2`, and `42aa6ad`)
correct the generic relationship context assembled for quantity semantics.
After the strongest professional pair is selected, remaining rows are ranked
by semantic wording, work family, source role and source/page proximity rather
than numeric similarity. A context containing a total and one established
component now reserves room for an unresolved candidate, and the bounded
relationship task may contain three or four rows. Numeric equality is never a
scheduling signal and Qwen still has to establish every semantic relation.

The current release autonomously scheduled four-row job
`01a0ff65-d529-7e45-bde5-b5cdf5d9aa32` for the independent steel-gallery
control workspace `01a0f605-1608-7c9a-8b8a-f13e83a11920`. Qwen identified
10.1 t and 8.3 t as components of the same 18.4 t design total and marked the
component set complete. Deterministic Decimal arithmetic then projected
comparison `sha256:1104de824ab12427c0e56e5b3420e4ac82f364db9d50dd88bb13abbcf22c7795`
as `MATCH` with zero difference. The same semantic context contained a 17.0 t
commercial quantity and a different steel grade; Qwen classified it as an
alternative scope, so deterministic comparison correctly did not manufacture
a cross-document discrepancy without same-scope authority.

Commit `42aa6add4560c37db7e7b8d9e6c96c86241d42b4` passed exact-SHA CI run
`37085807855` and is active as immutable release
`~/.asd-kontur/public-demo/releases/20261003-42aa6ad-component-closure-v47`.
The migration head remains `0111_reviewed_quantity_source_value`. Qwen PID
`93554` and NTD worker PID `98263` were preserved. No developer queue, retry,
successor, priority or Qwen command was issued. The release receipt SHA-256 is
`db5fddc01419dc5669f53ef72af7097223549982905e5bcdb55bf9ece92ac864`.

The real blind workspace continues through its pre-existing autonomous
relationship queue. Its compound measurement case is not yet claimed as
accepted: the current extractor retained a compound area/volume cell and the
system must either establish a singular source measure through generic
semantic review or leave the arithmetic unresolved. No project-specific
quantity rule has been introduced.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Typed compound-source failure — release b21a492

The first generic attempt to recover the real blind-project compound
measurement did not establish a safe scalar source pair. The reviewed source
cell contained more than one measurement, and the semantic result returned the
compound cell rather than one exact value/unit pair. Deterministic validation
rejected that output with the typed recovery code
`qwen_work_reconciliation_quantity_source_value_invalid`; it did not project a
quantity, relation, comparison or professional finding from malformed model
output. This is a negative product result, but it preserves the core invariant
that Qwen establishes meaning while deterministic code controls numeric
authority.

The v52 release receipt is stored at
`~/.asd-kontur/public-demo/releases/20261003-b21a492-typed-quantity-repair-v52/release-receipt.json`
with SHA-256
`20fdfca4c5df621c30509404f68a2db920b1485fa553f727df8249b2fac52d12`.
The failed result was not described as a successful comparison, and the blind
snapshot gate remains closed.

## Exact scalar options for compound source cells — release ebff0c1

Commit `ebff0c1c1d85358f44d5de6c617e95f60d32b428` implements the generic
recovery exposed by the v52 failure. The deterministic harness now splits a
compound source cell into its exact scalar value/unit pairs and supplies those
pairs as a closed `available_source_measures` set. Qwen may select one exact
pair or return no selection; it cannot authorize a value that is absent from
the source set. Arithmetic remains deterministic. The semantic profile is v29
and the engineering model accepts that profile without any project name,
document name, expected value or corpus-specific branch.

Accepted v28 results are preserved except for rows carrying the exact typed
compound-source validation failure. Previously queued or otherwise unprocessed
v28 work is superseded by v29 work through the normal autonomous profile
transition. This means the accepted-result replay is targeted, while the
remaining unfinished validation backlog legitimately continues on the current
profile; it does not mean that only one workspace has unfinished work.

Migration `0116_exact_compound_source_measure_options` records the active
semantic contract. The public database was backed up to
`~/.asd-kontur/public-demo/backups/pre-0116-source-measures-20261003T1715/public-before-0116.dump`
(SHA-256
`95f526c6d88aa299654440a99d60c1f89ddbf7be9b77b2b430a88e76e220bdc5`),
restored separately, upgraded, downgraded and upgraded again before controlled
activation. The application services run from immutable release
`~/.asd-kontur/public-demo/releases/20261003-ebff0c1-compound-source-v53`.
The worker drained its in-flight job to a durable successful receipt before
activation. Qwen PID `93554` and NTD worker PID `98263` were not restarted.

Exact-SHA CI run `37099025674` passed. API readiness reports migration head
`0116_exact_compound_source_measure_options`. After activation the supervised
orchestrator autonomously created blind-workspace v29 job
`01a10034-743e-70e3-8016-349527670153` for the three compound-measure
candidates; no developer queue, retry, successor, priority or Qwen command was
issued. At this checkpoint that job remains queued in the fair shared work
queue, so no component/total success is claimed yet.

The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the lifecycle platform fingerprint remains
`sha256:02cb45f341ad56595bbe6ec59abe5fbadac7841914280b165ed99861923e8487`;
the canonical NTD fingerprint remains
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains exactly 319 succeeded jobs.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.

## Profile v31 live closure and material source scope — release 1e08687

The independent steel-gallery control workspace
`01a0f605-1608-7c9a-8b8a-f13e83a11920` exercised the source-grounded
alternative guard without a developer progression command. Its first Qwen
response incorrectly treated the 18.4 t design total and 17.0 t VOR quantity as
alternatives without source support. Deterministic validation rejected that
decision with `qwen_work_reconciliation_alternative_evidence_missing`. The
bounded repair then established 10.1 t and 8.3 t as design components of 18.4 t
and classified the 17.0 t VOR value as the same commercial scope.
Deterministic Decimal arithmetic produced a 1.4 t design-to-commercial
difference, a professional finding, a customer clarification question and a
contractor-facing consequence. The terminal result digest is
`sha256:ef5db1cbc98c0e063ec59a38c914a0df7eeab8b09731665882a467d2635c9b89`.

Commit `1e08687366d7cb590716768296014b63219417f4` fixes the next generic bridge
failure exposed by the same control corpus. Repeated model assertions of the
same material property on the same source version, document version, page,
location and work scope are now collapsed before comparison. Assertions with a
different property, page, source or engineering scope remain distinct. The
projection also emits one comparison for an exact source-page/property pair,
while preserving independent design-note and specification comparisons against
the commercial source. The engineering model version is
`project-engineering-model-v68`.

The live v68 result contains exactly two material comparisons: RD S355 against
VOR S275 and specification S355 against VOR S275. It contains no duplicate
comparison produced solely by material-kind aliases. Together with the 18.4 t
versus 17.0 t quantity finding, the project view now produces three grounded
professional issues and three corresponding customer questions from structured
facts.

The full local suite passed 1,197 tests with 113 skips; the separately exercised
0118 migration roundtrip passed. Exact-SHA CI run `37104844770` passed every
backend, frontend, browser, security and migration gate. The immutable active
release is
`~/.asd-kontur/public-demo/releases/20261003-1e08687-material-scope-v56`.
No database migration was required beyond 0118. All four application services
import commit `1e08687`; Qwen PID `93554` and NTD worker PID `98263` were
preserved. The release-receipt SHA-256 is
`a26cf95b2c52bbf34b2b75fbb112ac591702bb3391bff1a38d5d3fe52f8de622`.

The all-history platform-memory fingerprint remains exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`;
the canonical NTD fingerprint remains
`sha256:ed99e55b55742af1122f3e64e213fc9c70217921c2fba9a1d0f2295c9e5c6510`;
and the NTD ledger remains exactly 319 succeeded jobs. No developer queue,
retry, successor, priority or Qwen command was issued.

Current status remains: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.
