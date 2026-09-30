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
| Explicit pit association limited to KNS/LOS | Corpus-specific restriction | Generalized to an explicit named/code facility followed by a designation number; semantic pit decisions remain available for other forms. |
| Construction work family vocabulary | General construction rule | Retained. Unknown concepts remain unclassified rather than forced. |

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

## General quantity acceptance

Parameterized controlled cases cover different terminology and measures:

- concrete volume: `100 + 25` against stated `90 m3`;
- structural steel: `5.2 + 3.1` against stated `7.0 t`;
- pipeline length: `120 + 80` against stated `150 m`.

The same deterministic implementation reports the arithmetic difference only
after an explicit `COMPONENT_VS_TOTAL` relationship. Incompatible units,
different facilities, or an `INCOMPARABLE_TO` decision produce no numeric
finding. These are mechanism tests, not expected values for a real project.

## Blind-project and unseen-corpus status

The active real project remains a blind validation corpus. No owner-known
finding has been added to prompts, fixtures, catalogs, or runtime data. A durable
blind Tender snapshot and its fingerprint have not yet been produced for this
checkpoint.

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

## Remaining implementation work

- persist and schedule the remaining generalized semantic tasks beyond work and
  quantity reconciliation;
- complete restart acceptance for worker, orchestrator, Qwen, and API;
- run the blind real project to a fingerprinted preliminary report;
- run the independent unseen controlled corpus without code changes;
- deploy the unified candidate, run browser acceptance, and obtain exact-SHA CI.

Current status: `GeneralizedTenderHarness=false`,
`AutonomousProjectProcessing=false`, `ProductReady=false`.
