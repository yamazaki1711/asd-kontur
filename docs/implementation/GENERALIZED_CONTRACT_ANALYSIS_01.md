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
