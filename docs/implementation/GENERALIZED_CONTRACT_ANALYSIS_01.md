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
- Joined candidate contract risks and proposed Contractor wording into the
  primary Tender findings schedule, report, and analysis archive. The join is
  transient and workspace-scoped; it does not promote model output into the
  finalized legal tables.
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

Release `41848b9` is active for API, project worker, assistant worker, and
project orchestrator at migration `0097_autonomous_contract_analysis`. The
persistent Qwen process and independent NTD worker were preserved. After the
project-worker restart at an idle model boundary, Qwen resumed new generations
without a developer progression command.

On the real blind workspace, v3 document-role reclassification is still
running autonomously. No owner-known finding or document-specific rule has
been introduced. The actual draft contract has not yet completed its v3 role
decision at this observation point, so a real blind contract finding cannot
yet be claimed.

The remaining acceptance work is:

1. observe autonomous contract discovery and multiple live Qwen batches on the
   current blind project, with no manual queue command;
2. inspect the independently generated blind-project findings and editable
   DOCX;
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
