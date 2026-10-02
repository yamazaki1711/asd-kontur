# Generalized Contract Analysis 01

## Baseline defect

ASD-KONTUR exposed contract-analysis tables, API projection, UI, CSV, and DOCX,
but ordinary Tender processing never created the process or populated the
result. The screen therefore stopped at “process not formed.” MAC_ASD had a
direct user flow from contract input to contractor risks, proposed wording, and
a disagreement protocol. This was a functional regression, not a presentation
gap.

The cross-repository user-result audit is recorded in
`docs/reports/MAC_ASD_TO_ASD_KONTUR_FUNCTIONAL_REGRESSION_2026-10-02.md`.

## Implemented engine

- Added the durable `CONTRACT_ANALYSIS` job kind and included it in scarce-model
  fairness and project status.
- Added autonomous, role-driven, bounded contract batching to the supervised
  project reconciliation sweep.
- Corrected the generic semantic role contract after a live blind read showed
  that procurement application instructions had been labelled `contract` while
  the actual draft agreement had not. Profile v3 now distinguishes a document
  containing negotiable party obligations from procurement instructions and
  price calculations. Existing sources are autonomously reclassified under the
  versioned profile; no filename or project-specific exception was added.
- The real blind DOCX then exposed a second generic classification defect: its
  single logical native page contained a long commercial table before the
  contract clauses, while the classifier saw only the first 800 characters and
  returned `local_estimate`. Profile v4 uses a bounded stratified sample across
  the beginning, middle, and end of long logical pages (and across long
  multi-page documents). The prompt treats price tables as possible appendices
  but still requires explicit party obligations for the `contract` role. No
  filename, clause, project name, or expected blind finding is encoded.
- Added strict local-Qwen clause/risk analysis with exact locator and source-text
  validation, reusable risk categories, benign-clause support, and one bounded
  JSON repair.
- Added immutable workspace-scoped candidate persistence without granting the
  document worker access to finalized legal/Tender tables.
- Added a candidate projection for clauses, contractor risks, recommended
  action, proposed contractor wording, disagreement-protocol rows, and revised
  clause candidates.
- Changed the UI blocker from an internal “process not formed” state to either
  automatic analysis progress or the professional missing-input message
  “Проект договора не найден среди загруженных документов.”
- Extended the editable DOCX so the protocol includes the exact customer clause,
  proposed contractor wording, source, practical consequence, and uncertainty.
- Added a separate format-aware revised-contract candidate for admitted DOCX
  contracts. It copies the source package and replaces only an exact, uniquely
  matched full clause paragraph. Missing, partial, duplicate, multi-source, or
  unsupported-format matches fail closed and leave the clause-change schedule
  available; untouched package members and contract paragraphs remain unchanged.
- Added the verified exact-source revised contract to the standard editable
  Tender archive beside the disagreement protocol. If exact replacement fails
  closed, the report, schedules, and clause-change protocol remain downloadable.
- Corrected a third generic long-document defect before blind contract analysis:
  office extraction may represent a complete contract as one native layout
  element. The real blind source contains one 89,087-character element, while
  the analysis contract permits at most 12,000 normalized characters. Contract
  profile v3 deterministically divides any oversized element into exact,
  contiguous source ranges (10,000 characters maximum, preferring paragraph or
  sentence boundaries), records those ranges in each durable job, and reconstructs
  only the selected range for Qwen. Qwen still cites the original locator, and
  no text, clause, or project answer is synthesized by the splitter.
- Contract profile v3 also scales the strict-JSON response budget with bounded
  source length (1,800 to 5,000 tokens). A single long source range no longer
  receives the same output allowance as one short clause; the limit remains
  finite and is reused for the one permitted schema-repair attempt.
- Contract profile v4 preserves native table rows as atomic semantic inputs.
  The blind contract exposed a commercial row whose quantity and price columns
  had previously been separated from its work description by generic layout
  batching. The corrected context now keeps the full admitted row together;
  no document name, work name, quantity, or expected finding is encoded.
- Contract profile v5 accepts a risk only when it cites an explicit continuous
  trigger from the admitted clause text. A bounded fragment's failure to mention
  a price-adjustment or change mechanism is no longer treated as proof that the
  complete contract omits it. Typographic quote/dash substitutions may be
  resolved back to the exact admitted source slice; lexical changes and
  paraphrases still fail closed.
- Output-exhausted contract batches are recursively divided into smaller
  source-preserving groups and their structured results are merged
  deterministically. Duplicate local clause labels remain distinct during the
  merge. Model arithmetic and unbounded output are not introduced.
- The candidate projection now selects the newest immutable attempt for each
  exact input digest. Historical retry-exhausted receipts remain queryable but
  cannot permanently block a successful autonomous replacement. Proposed
  Contractor wording appears progressively as a clearly marked partial draft;
  the revised-contract file remains unavailable until all effective current
  batches are terminal-successful.
- A supervised-worker circuit breaker pauses further model claims after a local
  Qwen runtime outage instead of consuming retry budgets across the queue. The
  autonomous orchestrator creates bounded replacement attempts for historical
  runtime outages, exact-source typography failures, and output exhaustion; it
  never rewrites the failed attempt.
- Joined candidate contract risks and proposed Contractor wording into the
  primary Tender findings schedule, report, and analysis archive. The join is
  transient and workspace-scoped; it does not promote model output into the
  finalized legal tables.
- Joined typed project-wide duration, procurement, revision, and contract-risk
  findings into the contract-analysis result even when the conflicting project
  and procurement sources are not the draft-contract file itself. The Russian
  UI and editable contract-analysis DOCX now show key contract/procurement
  conditions and the practical project-to-contract consistency schedule before
  the disagreement rows. Unrelated engineering findings remain in the main
  Tender analysis instead of polluting the contract review.
- Kept party identities tied to admitted contract sources while expanding the
  professional contract view to all source-grounded project price, schedule,
  procurement and acceptance conditions. This prevents NMCK or a POS versus
  procurement duration conflict from disappearing merely because it is stated
  outside the draft-contract file.
- Limited the contract-view time schedule to explicit contract-source terms and
  project time facts that participate in a typed contract/project finding. Raw
  date-like observations that are unrelated to an established comparison no
  longer appear as key contract conditions.
- Corrected the read projection to use only the current versioned semantic-role
  profile. A superseded historical `contract` label can no longer keep a false
  contract source active after reclassification.

## Safety and reuse decision

Legacy MAC_ASD prompt/service/RKB code was used as capability evidence only.
No legacy component was reused as-is. In particular, ASD-KONTUR does not restore
approved-on-model-failure behavior, placeholder parties, blanket statutory
citations, whole-contract unbounded prompts, keyword-only authority, or stale
legal conclusions. The old RKB remains a review backlog until each pattern is
classified for current, generic use. The source-level audit now classifies all
100 legacy identifiers exactly once (30 `SAFE_GENERIC_PATTERN`, 34
`NEEDS_REWORDING`, 27 `NEEDS_CURRENT_LEGAL_VERIFICATION`, 8
`PROJECT_SPECIFIC`, and 1 `INCORRECT`) in the functional regression register.
This is a reuse decision record, not a runtime import: no legacy citation,
threshold, severity, recommendation or proposed wording has been promoted.

## Live validation state

The pure structured-output validator has changed, project-independent tests for
a genuine contractor dependency risk, a benign payment clause, invented source
text rejection, mandatory replacement wording, primary-report integration, and
exact source-locator preservation. Exact-SHA CI passed for
`41848b9b89f1481afb474c7ebf7f8bb20770db1d` in run `36943782110`, including
PostgreSQL integration and browser E2E.

The same autonomous engine completed a live changed control contract in
workspace `01a0f54f-10b8-7d51-8a9a-ef6fdefc0f2c` without a manual queue or
model command. Qwen classified `W95_private_bid_terms.pdf` as `contract` under
the current v3 role profile, extracted six exact clauses, and recorded three
contractor risks with three proposed disagreement rows. The ordinary 24-month
warranty and 4% performance-security clauses were extracted but not flagged.
This supplies a live benign-clause false-positive control.

The generated control-project DOCX passed ZIP/package integrity and macOS text
extraction. The local machine does not currently provide LibreOffice, Pandoc or
the lxml dependency used by the optional skill validator, so page-image visual
qualification remains explicitly not performed.

Release `9ac03000411f9be1cd8f2b05605c46b3be34a12c` is active for API,
project worker, assistant worker, and project orchestrator at migration
`0097_autonomous_contract_analysis`. Exact-SHA CI run `36948272996` passed.
The persistent Qwen process and independent NTD worker were preserved. After
the project-worker restart at an idle model boundary, v4 document-role work
continued without a developer progression command.

On the real blind workspace, the actual `Проект_контракта.docx` was identified
autonomously as a contract and scheduled as 50 bounded v5 analysis inputs. At
the 2026-10-02 14:49 +12 observation, the effective current lineage contained
8 succeeded inputs, 1 running input and 41 queued inputs, with no effective
failed input. The ledger still retains the superseded outage failures. Qwen had
persisted 16 exact clause candidates and two explicit contractor-risk
candidates without a manual queue or model command:

1. clause 2.5 makes payment conditional on budget limits made available to the
   Customer, creating a payment/cash-flow exposure if those limits are absent
   or insufficient;
2. clause 2.5.2 uses “in full or the missing part” for advance repayment after
   partial performance, without an explicit link to the value of work already
   performed and accepted.

Both findings carry the exact source clause, trigger text, consequence,
recommended action and proposed Contractor wording. The current Russian DOCX
projection re-opened successfully through macOS text extraction and contains
both rows, while marking the protocol `partial_draft` and the revised contract
as a clause-change schedule. ZIP/package integrity passed. Visual page
rendering remains unverified because LibreOffice is not installed and the
available Quick Look preview did not complete.

API release `67264392fbcdc8369dcb655cf452903885e51773` exposes the progressive
projection. Project worker, assistant worker and project orchestrator release
`32a1e2402e4b06c00ec94d2edbcffcab24a876cf` performs bounded recovery and
continued live v5 processing without restarting Qwen or the NTD worker.
Exact-SHA CI run `36956436183` passed for the worker/orchestrator release;
the progressive API release CI was still running at this observation.

The remaining acceptance work is:

1. allow all effective v5 batches to converge and inspect the remaining
   independently generated blind-project findings;
2. generate and inspect the complete disagreement protocol and exact-source
   revised-contract candidate after convergence;
3. perform a visual page qualification of the generated protocol when an
   approved local renderer is available;
4. qualify the format-aware revised-contract candidate against the real blind
   DOCX contract; a controlled changed-project fixture already proves exact
   replacement, untouched-paragraph preservation, and ambiguous-match refusal.

Until those runtime gates pass:

- `ContractAnalysisOperational=false` until the autonomous real blind-project
  result is inspected and accepted (the control-corpus engine path passes)
- `ProtocolOfDisagreementsOperational=false` until the real blind-project
  protocol passes content acceptance (the editable control artifact passes)
- `GeneralizedTenderHarness=false`
- `AutonomousProjectProcessing=true`
- `ProductReady=false`

## 2026-10-02 contract/project context and standalone protocol checkpoint

The contract projection now joins source-grounded project commercial facts and
typed project/contract findings. Contract-source participants remain isolated
to the contract corpus; project-wide price, procurement and schedule facts may
appear when they are established elsewhere in the admitted Tender package.
The time schedule is limited to explicit contract terms and facts participating
in typed project/contract findings, preventing unrelated date-like drawing
references from appearing as contract conditions.

ASD-KONTUR now exposes a separate editable
`tender/disagreement-protocol.docx` product result in addition to the broader
contract-analysis report. Its table contains the exact Customer clause,
Contractor wording, practical basis and source reference. The Russian contract
screen offers this artifact as soon as at least one defensible disagreement is
available. The renderer does not invent parties, signatories or missing
contract details and retains the professional-review boundary.

At the 2026-10-02 16:19 +12 observation, the autonomous v6 blind-project run
had 9 effective successful batches, 1 running batch and 40 queued batches. It
had persisted 24 exact clauses and 6 contractor-risk findings. The running job
had a fresh durable heartbeat and the supervised Qwen status was
`QWEN_GENERATING`; no manual queue or successor command was issued. Historical
failed and reconciliation-required jobs remain immutable ledger entries, while
the product projection selects the newest effective attempt per exact input.

The active API release is
`81834608e76a038a5f9f4df3a0e8338095db629c`. The worker, assistant worker and
project orchestrator remain on
`b6a293e5137389ccbaf4a57c4b21fa318635af4d`; Qwen and the independent NTD
worker were not restarted. Exact-SHA CI run `36963161384` passed for the active
API release. The standalone protocol change is locally qualified but not yet
deployed at this observation.

The first revised-contract attempt against the admitted blind-project DOCX
failed closed because a proposed change identified an exact clause fragment
inside a Word paragraph rather than the whole paragraph. The generic renderer
now permits a replacement only when that exact fragment occurs once in one
paragraph. It preserves the prefix, suffix, all untouched paragraphs and all
unmodified package members; duplicate or missing matches still fail closed.
It also prevents duplicated boundary punctuation when the replacement and
preserved suffix carry the same terminal mark. Re-running the real candidate
produced a valid 86,683-byte DOCX with five exact proposed changes while
retaining the rest of `Проект_контракта.docx`. ZIP integrity and macOS text
extraction passed; visual page qualification remains pending.

## 2026-10-02 adverse-effect qualification checkpoint

The autonomous v6 blind-project run exposed a generic professional-quality
defect that exact source quoting alone does not prevent. Three exact contract
fragments were incorrectly interpreted as Contractor risks:

1. a three-working-day duty imposed on the Customer to transfer the site and
   documents was treated as Contractor deadline exposure based on a hypothetical
   future Customer breach;
2. the Customer's ordinary right to demand a contractual penalty for a proven
   Contractor breach was treated as unlimited liability without text creating
   an unlimited or disproportionate consequence;
3. a duty to send a unilateral control act to the Contractor was treated as an
   acceptance risk even though the bounded fragment stated no adverse effect of
   that act.

These are false positives, not disagreement-protocol rows. The v7 contract
analysis contract therefore requires two independently inspectable exact source
quotes for every proposed risk: the triggering wording and the wording that
establishes the adverse Contractor effect, obligation, dependency or measure.
Both quotes must resolve to admitted clause text. The bounded prompt also
instructs Qwen not to infer Contractor exposure solely from a short Customer
deadline, an ordinary contractual remedy, a control act without a stated
effect, or remediation costs caused only by the Contractor's own breach.

Migration `0104_contract_adverse_effect_text` admits the versioned v7 result
profile without altering historical v1-v6 results. Focused formatting, lint,
typing and 20 contract tests pass. The disposable migration round-trip was not
run in the development shell because `ASD_TEST_DATABASE_URL` was absent; it
remains an exact-SHA CI and controlled pre-deployment gate.

The v7 release is intentionally not deployed while the autonomous v6 run is
active. At 2026-10-02 16:37 +12, v6 had 10 effective successful batches, one
running batch with a fresh heartbeat, and 39 queued batches. It had persisted
33 exact clauses and nine raw risk candidates. Qwen reported
`QWEN_GENERATING`, 397 completed requests and no error. The API reported ready
at migration `0103_contract_risk_mechanism`. No manual queue, retry or successor
command was issued. Exact-SHA CI passed for all four preceding artifact commits,
including `75391ca45c326b4b2f961198e304924e72b242f1`.

Promotion of v7 requires a live changed-contract false-positive acceptance in
addition to schema and parser tests. In particular, benign Customer duties,
ordinary breach remedies and ordinary warranty/security terms must remain
unflagged while an explicit Contractor exposure in the same controlled corpus
must still produce a source-grounded risk and, where justified, a disagreement
row.

The mandatory Word-package validator then exposed defects that ZIP integrity
and macOS text extraction had not detected in the generated contract report and
standalone protocol: the minimal table omitted `tblPr`/`tblGrid`, section
margins omitted required header/footer/gutter attributes, and the document
relationship part used the office-document namespace instead of the package
relationships namespace. The generic renderer now emits schema-valid fixed
layout tables, complete section margins and the correct relationship namespace.
Both a contract report and a standalone disagreement protocol generated after
the fix pass the DOCX XSD/package validator. LibreOffice is not installed, so a
page-image visual qualification remains explicitly outstanding; schema success
does not claim visual acceptance.

The format-preserving revised-contract editor had a separate serializer defect.
Python `xml.etree` retained the `mc:Ignorable` attribute but removed namespace
declarations for extension prefixes used only inside that attribute. The
admitted source contract validates, while the earlier 86,683-byte revised
candidate therefore failed namespace validation despite preserving all 566
paragraphs. The editor now records the admitted source namespace map and
restores only the declarations referenced by `mc:Ignorable`, failing closed if
the admitted package did not define one. Applying the fix to the same real
candidate produced an 86,767-byte document with 566/566 paragraphs and no new
schema/package errors against the original contract. A generic changed-contract
test covers an unused `w15` extension namespace so this behavior is independent
of the blind corpus.

macOS Quick Look is available as a bounded local visual renderer even though
LibreOffice is absent. Visual inspection of the schema-valid controlled
protocol showed that the first minimal table was readable but insufficiently
professional: headings ran together and cells had no visible boundaries. The
generic renderer now emits a narrow ordinal column, fixed table grid, cell
padding, grey borders and a shaded bold header. The restyled controlled
protocol remains schema-valid and its 1600-pixel landscape preview is readable
without overlapping columns. The real blind-project protocol must be
regenerated from the qualified release before its own visual acceptance is
claimed.

## 2026-10-02 v7 pre-deployment database rehearsal

The adverse-effect profile remains staged rather than active while the
autonomous v6 blind-contract run is in progress. A fresh physical backup was
created before any public migration at
`~/.asd-kontur/public-demo/backups/pre-0104-contract-adverse-20261002T1705/public-before-0104.dump`.
Its SHA-256 is
`a16437f17c688c7c83863a22cb01b4a1a651994691bcdb1f3f4a7d68dee89e60`.

The dump restored separately as `asd_kontur_restore_0104_20261002` at migration
`0103_contract_risk_mechanism`. Source and restored databases had the same
all-history platform-memory fingerprint,
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
and the same NTD processing state: 319 succeeded jobs and no other NTD job
state. The disposable restore passed upgrade to
`0104_contract_adverse_effect_text`, fail-closed downgrade without the explicit
disposable-database flag, flagged downgrade to 0103, and re-upgrade to 0104.
The platform-memory fingerprint and NTD job state remained exactly equal after
the round trip. The live database and supervised services were not changed by
this rehearsal.

At 17:02 +12 the v6 run still had 13 successful effective batches, one running
batch, and 36 queued batches. Qwen's completed-request counter advanced from
414 to 419 during observation and it remained in `QWEN_GENERATING`; this is a
productive bounded repair/analysis sequence, not an idle or hung model. No
manual successor, retry, reconciliation, or queue-refill command was issued.

## 2026-10-02 v7 controlled activation

The later v6 observation exposed a second generic bounded-response failure:
`qwen_contract_risk_revision_invalid` after the schema-repair pass. The v7
analyzer now applies its existing recursive context split to that failure as
well as source-quote and output-budget failures. Each child result still has to
pass the complete exact-source, exact adverse-effect and single-revision
validator; a one-locator invalid result still fails closed. A changed-clause
test demonstrates two independent valid child revisions without using the
blind corpus. Exact-SHA CI run `36968115791` passed for
`f42324775dd7079d7f6e22a85ac06571686a0471`.

Before public migration the application services were stopped and a fresh
physical backup was created at
`~/.asd-kontur/public-demo/backups/pre-f423247-contract-v7-20261002T1728/public-before-f423247.dump`.
Its SHA-256 is
`5d992e6425d9d22f364f5020c05a63bfa79243debbd470d6b8a2e61fbd212e46`.
The public database then advanced transactionally from 0103 to
`0104_contract_adverse_effect_text`. The platform-memory fingerprint remained
exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
and NTD remained exactly 319 succeeded jobs. Qwen PID 93554 and the independent
NTD worker PID 98263 were not restarted.

The worker's in-process SIGTERM handler did not provide a true launchd drain:
`launchctl bootout` removed the process while it was waiting on batch 22. Qwen
was not killed and completed the bounded request, but the disconnected result
was not persisted. The expired durable lease is recoverable and this behavior
is retained as an operational limitation rather than described as a graceful
drain. No accepted result was lost.

API, worker, assistant worker and project orchestrator now run from the pinned
release
`~/.asd-kontur/public-demo/releases/20261002-f423247-contract-v7` at exact SHA
`f42324775dd7079d7f6e22a85ac06571686a0471`. Readiness returned HTTP 200 with
migration 0104, and the built JavaScript asset returned HTTP 200. Without a
manual queue or model command, the restarted worker terminalled superseded v6
inputs, the orchestrator created 50 immutable v7 inputs for the real blind
contract, and Qwen completed the first three before starting batch 4. Those
three results contained two exact clauses and no risks, which is appropriate
for the opening document context rather than a manufactured finding.

## 2026-10-02 v7 professional-output checkpoint

The autonomous v7 run produced its first risk-bearing result without a manual
queue, retry or model command. Batch 9 contains two defensible contractor
exposures from the admitted `Проект_контракта.docx`:

1. clause 2.5 makes payment conditional on budget limits made available to the
   Customer;
2. clause 2.5.2 permits advance repayment after partial performance without an
   explicit link to the value of work already performed and accepted.

Both results contain exact trigger text, separate exact adverse-effect text,
the practical consequence, recommended action, proposed Contractor wording
and the source clause. The live candidate projection exposed 15 clauses, two
risks, two disagreement rows and two revised-clause candidates. The invalid
batch-8 and batch-10 outputs failed closed on exact-source validation; the
supervised orchestrator independently created bounded replacement work while
the worker continued with the next batch. At the 17:52 +12 observation Qwen
reported 463 completed requests, `QWEN_GENERATING`, and no runtime error.

Visual inspection of the live partial disagreement protocol exposed a separate
product-language defect: the professional `Источник` column included source
version UUIDs, fragment UUIDs and the internal `qwen_contract_candidate`
authority label. The renderer now keeps those identities in structured CSV/API
lineage but shows only the admitted document name and page/sheet in the Word
report and standalone protocol. The same change translates processing status
and known gaps into ordinary Russian professional language and removes the
draft process UUID from the report body. The regenerated live protocol passes
the application DOCX structural validator and Quick Look renders a readable
landscape table with no UUID or candidate terminology.

The document-role run also established a remaining generalized scope issue:
`Описание объекта закупки.docx` is a contract attachment/technical
specification with explicit Contractor obligations, but the current bounded
profile assigns the coarse role `contract`. It is useful to review that source
for Contractor exposure, but a completed product must distinguish the main
agreement from amendable attachments so attachment proposals cannot suppress
or contaminate a revised-main-contract candidate. No project-specific filename
rule has been added; this remains a generic role/output-scope correction after
the current v7 checkpoint completes.

The post-migration Knowledge Gateway canary successfully retrieved the verified
provision `external/page:1/clause:1` from edition
`991a1cff-4967-560f-be70-be902b92b7b0` with `status=ok`. The provision remains
not activated for a workspace and has no verified deterministic rule candidate,
which is reported as a gap rather than promoted into a contract conclusion.

## 2026-10-02 professional UI activation

Exact-SHA CI run `36971548250` passed for
`8a3bd1b47478bc33afc752bdbcce2c09d6d933af`, including PostgreSQL integration,
frontend production build and browser E2E. The API and frontend were activated
from the pinned release
`~/.asd-kontur/public-demo/releases/20261002-8a3bd1b-contract-professional-ui`.
The database remained at migration `0104_contract_adverse_effect_text`.

This was deliberately an API/frontend-only activation. The document/project
worker, autonomous project orchestrator, assistant worker, Qwen service and NTD
worker were not restarted. During the activation the live blind-contract run
advanced from nine to ten successful v7 batches and Qwen remained in
`QWEN_GENERATING`, demonstrating that the deployment did not make Codex the
runtime scheduler. The served JavaScript artifact is `index-B4n-g9mB.js` with
SHA-256
`f3e4a5394a2377107e1932715a0c2bebe370179de6e5318d6918c3358efa235a`.

The first launchd activation attempt was rejected during immediate service
teardown. The old API was restored and verified healthy before a second
controlled attempt. A later readiness guard initially used a startup window
that was shorter than the service preflight and therefore rolled back safely.
The final activation used an explicit unload wait and a sufficient readiness
window. No background analysis service or project data was affected.

After activation the all-history platform-memory fingerprint remained exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
and the NTD processing state remained exactly 319 succeeded jobs. The release
receipt records the split API/background release boundary explicitly.

## 2026-10-02 counterparty-grounding correction staged

The first four live risk candidates exposed one false-positive mechanism that
the changed-contract controls did not yet cover. Clause 3.1.14 requires a
hidden-work act before subsequent work but, in the extracted clause, does not
identify the Customer as the party controlling signature. The v7 model inferred
Customer delay and proposed deemed acceptance plus a transfer of quality risk.
Those consequences are not grounded in the quoted clause and must not become a
professional disagreement merely because signing an act is required.

The generic v8 contract profile therefore requires an explicit Customer actor
in the exact trigger/adverse-effect wording for
`customer_controlled_payment`, `customer_controlled_acceptance`,
`customer_controlled_deadline` and `contractor_bears_customer_cause`. The prompt
also forbids attributing an act/signature to the Customer or transferring
quality responsibility unless the supplied wording supports that relationship.
A changed hidden-work-act test proves rejection without using the blind-project
text, while the existing changed deadline and payment cases remain accepted.
Migration `0105_contract_controller_grounding` admits the versioned v8 result
profile. This correction is staged only: it will not be activated until the
autonomous v7 checkpoint has completed, so the current worker and Qwen run are
not interrupted.

The read projection is also version-transition safe. While v8 is being built,
it retains the complete v7 professional projection until the effective v8 run
has no active work, then switches profiles atomically. A terminal partial run
switches with an explicit batch-failure gap and cannot enable the exact revised
contract; it does not leave the older profile visible indefinitely. Batch ordinals are
not treated as source-coverage identities because a new profile may change its
context size or table packing. A new project without a prior profile still
appears progressively. The counterparty-grounding and professional-authority
guards are applied to both profiles at read time, so an unsupported historical
inference cannot remain in the UI, report or disagreement schedule during the
transition. This avoids both an empty screen and duplicated/lost clauses while
a safer profile is running.
Until the first v8 job is actually created, the projection also retains the v7
run state, so an actively generating v7 analysis remains `analyzing` rather
than being misreported as a completed draft. Against the live database the
transition projection preserved 35 extracted clauses, removed the unsupported
fourth risk, retained three grounded disagreement candidates and continued to
show `CONTRACT_ANALYSIS_IN_PROGRESS`.

The same live run exposed a performance/availability bottleneck in exact clause
quotation. Four of the first fourteen v7 batches ended with
`qwen_contract_clause_source_not_exact` after approximately 5–11 minutes of
generation and bounded repair. V8 now first resolves an exact quote as before;
when Qwen has selected valid durable locators but makes a small lexical change,
the validator may fall back to the complete exact admitted locator context only
when that context is at most 3,000 characters and token overlap is at least
80%. Low-overlap invented wording remains rejected. Risk `trigger_text` and
`adverse_effect_text` continue to require exact source substrings, so this
throughput correction cannot turn paraphrased model prose into a professional
finding.

At the 18:24 +12 measurement point, the eleven successful v7 jobs averaged
123.5 seconds with a 41.5-second median, while the four exact-source failures
averaged 483.5 seconds with a 487.2-second median. The failed quotation path was
therefore consuming roughly four times the average successful-job duration and
more than eleven times the successful median. This is measured live workload,
not a theoretical optimization target.

V7 batch 15 then labelled a return-of-overpayment clause as `unpaid_change`,
inferred possible internal auditors/SRO actors not present in the source, and
proposed making a court judgment the only basis for recovery. It is retained in
immutable v7 history but is not accepted as a final professional finding. The
v8 task now treats restitution of objectively verified overpayment or
unauthorized material/method as ordinary unless the clause itself creates an
unreviewable unilateral mechanism; it forbids inventing the identity of a
control body and reserves `unpaid_change` for actual additional/changed-work
payment exposure. The correction is a general contract-review rule rather than
a clause-number or corpus-specific exception.

## 2026-10-02 consultant contract-model integration staged

The professional consultant previously received the project-engineering model
but not the contract-analysis projection. It could therefore describe general
Tender engineering risks while omitting contract clauses, Contractor exposure
and proposed wording already available on the contract screen. This was a
product inconsistency rather than a model-capacity issue.

The Knowledge Gateway now projects a bounded contract context alongside the
same workspace engineering model. It contains admitted source document names,
exact issue-linked clause wording, page and locator references, grounded
Contractor risks, practical consequences, recommended actions, proposed
Contractor wording, deliverable state and explicit gaps. Tender process, issue,
clause and job identifiers are excluded from the professional prompt. The
assistant prompt compactor preserves this contract block, and direct contract
questions route to the prepared discrepancy/risk result rather than asking the
model to rediscover the contract from raw search fragments. A deterministic
publication guard appends grounded contract risks and requested protocol
wording if the narrative model omits them.

The staged code was exercised read-only against the live blind workspace. It
returned the active `analyzing` state, both admitted contract-role sources, 70
extracted clauses, eight then-visible v7 risk candidates, eight proposed
revisions and nine source records. These counts document the current partial
v7 projection; they are not final acceptance because v8 is expected to reject
unsupported v7 candidates after autonomous replacement. No runtime job was
created, retried or changed by this check.

The continued v7 run also classified an optional mechanism for accepting and
paying early-completed work by mutual agreement as a restriction on ordinary
payment. The selected wording did not alter payment for work completed on the
normal schedule, so this is not a Contractor risk by itself. V8 now states that
boundary explicitly and validates it deterministically: a
`customer_controlled_payment` result based only on mutual early performance is
rejected unless the exact selected text also denies or conditions ordinary
payment. A changed-clause regression case proves the rule without using the
blind contract wording.

A separate v7 row treated a one-hour Contractor signing obligation as a
`customer_controlled_deadline` merely because the resulting notice is sent to
the Customer. Mentioning the Customer as recipient is not proof that the
Customer controls the deadline. The grounding validator now requires an
explicit Customer action for Customer-controlled acceptance/deadline
mechanisms, including active wording (the Customer sets, approves, changes or
delays) and correctly formed passive wording (set or approved by the Customer).
A changed notice-delivery case proves that a dative recipient reference cannot
pass as Customer control, while the existing unilateral-deadline controls
remain accepted.

The return-of-overpayment false positive is now also blocked by deterministic
source grounding rather than prompt wording alone. A result classified as
`unpaid_change` cannot be accepted from text that only describes restitution
of an overpayment or an amount above measured actual work, unless the same
exact selected text explicitly concerns payment for additional or changed
work. The rule is independent of clause numbering, parties, project identity
and quantities. A changed restitution example is rejected, while a changed
example that explicitly denies payment for additional work remains accepted.

The live candidate wording exposed a separate output-safety gap: two otherwise
useful risks contained proposed revisions with new five-day and thirty-day
deadlines that were absent from the clauses being replaced. V8 now instructs
the model not to introduce new amounts, percentages, durations or other
numeric thresholds. Deterministic validation independently enforces the rule.
If a proposed revision introduces a numeric contract term not present in the
exact replacement source, the risk is retained but the disagreement/revised
clause is withheld and marked
`PROPOSED_WORDING_NUMERIC_TERM_UNGROUNDED`. The same rule is applied at read
time to historical v7 output. Against the current blind projection this keeps
all five grounded risk findings while reducing the negotiation-ready rows from
five to three; no invented numeric term can enter the protocol merely because
it was fluent model output.

Changed-corpus verification also found that a previously identified contract
could temporarily disappear as “contract not found” after the global document
role profile advanced. The current projection deliberately does not reuse an
old role decision as current authority, but it now distinguishes an active
historical contract awaiting current-profile classification from a corpus in
which no contract exists. The user sees analysis/reclassification pending
until autonomous reconciliation produces the current role decision. Combined
with the rotating active-workspace scheduler, this removes the false missing-
input state without accepting a superseded classification as final.

The next live blind batch treated release of contract security as a Customer-
controlled payment risk even though the exact clause requires return within a
term already established by another contract clause. Its adverse scenario was
an assumed future Customer delay, not an adverse condition stated by the
source. V8 now rejects a `customer_input_dependency` based only on a return or
release tied to an established contractual deadline unless the exact wording
also denies or conditions payment. The prompt carries the same general rule.
Read-time filtering removes the historical candidate while retaining the five
other grounded risks and three numerically grounded disagreement rows.

One later v7 batch terminated with `qwen_contract_risk_invalid` after its
bounded repair attempt, discarding any otherwise valid clauses in that batch.
V8 now treats this validator failure like the existing output-exhaustion,
exact-quote and revision-shape failures: a multi-source batch is divided into
smaller source-preserving groups, each group retains the same bounded repair
budget, and results are merged deterministically. A changed two-source test
proves recovery without relaxing risk validation or adding an unbounded retry.

A subsequent candidate used `unpaid_change` for expert-cost reimbursement in
an unilateral-termination cure clause. The clause may warrant review under a
termination/remedy category, but it contains no changed work and must not be
presented as unpaid construction scope. The deterministic taxonomy guard now
requires both explicit additional/changed/excess-work language and explicit
payment denial before accepting `unpaid_change`. Changed examples cover both
rejection of a termination-cost misclassification and preservation of a real
additional-work nonpayment clause. The live read projection consequently
retains five correctly typed risks and three grounded disagreement rows.

## 2026-10-02 measured contract-batch bound staged

The autonomous v7 run established that the sustained MBP load was real local
Qwen inference rather than an idle spin, but also exposed avoidable work in the
strict-output path. Across the first 27 original real-contract batches, all
seven terminal failures used the twelve-locator ceiling. Those failures
averaged 528.6 seconds. The seventeen successful twelve-locator batches
averaged 182.8 seconds. Five failures were exact-source quotation failures,
one was an invalid risk structure, and a later exact-source failure completed
after 718.7 seconds. The supervised orchestrator correctly scheduled bounded
lineage replacements, but repeating a large strict-JSON task is an expensive
recovery strategy.

V8 therefore limits a newly scheduled contract-analysis context to eight
source locators. The character ceiling and atomic table-row behavior are
unchanged, and an oversized table row remains explicitly incomplete rather
than being treated as evidence of absence. This is a general throughput and
availability correction derived from terminal receipts; it does not encode a
document name, clause, party, quantity or expected finding. Recursive
source-preserving recovery remains available for an eight-locator batch that
still fails validation. A changed-seventeen-clause unit case proves the
default `8 + 8 + 1` packing behavior.

The autonomous replacement policy is now profile-aware as well. Runtime
unavailability remains retryable for every profile. Exact-source,
controller-grounding and output-budget failures remain eligible for bounded
replacement when they came from an older profile that lacked current
source-preserving recovery. If the current v8 analyzer has already exhausted
its repair and recursive split down to the smallest bounded context, the same
deterministic validation failure is terminally accounted instead of repeating
the entire task twice more. This preserves recovery from transient service
loss while preventing an accepted current recovery strategy from creating a
new expensive retry chain.

The live projection also exposed an authority-boundary defect in otherwise
useful model prose: a source-grounded advance-repayment risk was followed by an
unsupported assertion that the clause contradicted a legal principle. Contract
analysis in this path has `contract_commercial_risk` authority, not verified
legal authority. A generic deterministic publication filter now removes
sentences that assert illegality, invalidity, unenforceability or conflict with
law/legal principles without a separately qualified authority source. It keeps
the practical commercial explanation and action; if no usable commercial text
remains, the risk fails closed. The same filter applies at parse time for v8
and at read time for historical candidates. Against the blind projection it
retained all five grounded commercial risks and three disagreement rows while
removing the unsupported legal sentence.

## 2026-10-02 v7 terminal checkpoint and v8 controlled activation

The real blind workspace completed its autonomous v7 run before activation was
attempted. The terminal set contained 39 successful and 29 failed contract jobs,
with no queued or running v7 work. It persisted 201 exact clause units and 18 raw
risk candidates. The professional read projection retained six grounded risks
and four disagreement/revised-clause candidates; terminal batch failures kept
the exact revised-contract deliverable disabled. Twenty-seven failures were
strict exact-source quotation failures, one was invalid clause evidence and one
was an invalid risk. Original and bounded replacement failures each consumed a
median of roughly 8.5 minutes, confirming the need for the smaller v8 contexts
and current-profile terminal accounting.

The application worker was then disabled and sent `SIGTERM` through launchd.
Its signal handler finished the already leased project-work reconciliation job
`01a0fa68-72d1-7626-9fe2-8397a70b96ee`, recorded successful receipt
`01a0fc47-465b-7d8b-8aa4-007fbccae58f`, and exited without abandoning a lease.
The API, assistant worker and orchestrator were subsequently drained. Qwen and
the independent NTD worker were neither signalled nor restarted.

Before migration, a PostgreSQL custom-format backup was written to
`pre-f6ff30a-contract-v8-20261002T2302/public-before-f6ff30a.dump` with SHA-256
`dbaa126c6772748fa150974c279e64552f29674ee0dfd77ea050db4299b2035a`.
A separate restored database proved `0104 -> 0105`, fail-closed downgrade,
explicit destructive downgrade to `0104`, and re-upgrade to `0105`. The
all-history platform-memory fingerprint remained
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`
and all 319 NTD processing jobs remained succeeded throughout rehearsal and
public migration.

Pinned release `20261002-f6ff30a-contract-v8` now serves commit
`f6ff30a34f080fa11c2601a3d0ed18f2d4cd12c2` on migration
`0105_contract_controller_grounding`. Packaging verification caught and fixed
two release-construction defects before activation: editable-install metadata
and command shebangs still referenced the temporary staging directory. The
final environment was rebuilt in the pinned release path and imports only that
path. Exact-SHA CI run `36981605417` passed before deployment.

After launchd activation, `/api/v1/health/ready` reported `ready`, the expected
frontend asset returned HTTP 200, and the platform-memory/NTD checks remained
exact. Without a developer queue command, the supervised orchestrator created
78 v8 contract-analysis jobs for the blind workspace. A transient Qwen-busy
outcome on the first claim was autonomously requeued; the same job then
succeeded on attempt two, followed by further successful jobs. This is direct
evidence that v8 discovery, scheduling, retry and Qwen dispatch belong to the
runtime rather than to Codex.
