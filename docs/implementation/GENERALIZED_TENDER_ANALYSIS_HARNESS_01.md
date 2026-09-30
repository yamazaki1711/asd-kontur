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
`qwen_server.py` is byte-identical to the candidate implementation
(`sha256:4c0b429e63fd6daddc0c9517b62802f7a7b4c21cba6c437cca67ab9cd7346d30`).
Its single-threaded health endpoint cannot answer while a long generation owns
the request loop; process/connection/heartbeat evidence distinguishes that
observable condition from service death. This remains an operational
observability limitation.

The independent bridge corpus and parameterized quantity tests prove the
shared mechanisms across different names, work types, units and values without
a code change. They do not execute a second complete live Qwen project, so the
full unseen-project acceptance remains open.

## Remaining implementation work

- persist and schedule the remaining generalized semantic tasks beyond work and
  quantity reconciliation;
- complete a live autonomous unseen-project run without code changes;
- improve project entity consolidation and produce defensible quantity,
  comparison and finding results for the blind project;
- make Qwen health/availability observable while its one heavy request is in
  progress;
- run signed-in visual browser acceptance when an in-app browser session is
  available, and test the supported Mac sleep/wake boundary.

Current status: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=true`, `ProductReady=false`.
