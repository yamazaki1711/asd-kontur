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
classified for current, generic use.

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
