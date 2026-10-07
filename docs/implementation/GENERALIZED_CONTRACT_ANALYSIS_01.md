# Generalized Contract Analysis 01

## 2026-10-07 editable execution-condition register

The current, human-confirmed Support contract conditions can now be downloaded
as an editable CSV register. It includes clause, category, responsible party,
required action, condition, source document/page/version/locator and review
time. Execution status and evidence columns are deliberately blank. Rejected,
unreviewed, stale and source-less candidates are excluded; spreadsheet formula
prefixes in source text are neutralized. The export uses the owner-scoped
Support read model and does not assert performance, acceptance or legal
agreement. An isolated unit check covers exclusion, source retention and
formula safety; the browser check covers the visible download route. The
declared OpenAPI route matches the runtime-generated schema, 81/81 paths.

Release `c24a9e3531ad4ff77711905b7fdeb13588661863` is pinned at
`~/.asd-kontur/public-demo/releases/20261007-c24a9e3-contract-condition-register-v1`.
The four application launchd roles report that SHA; API readiness and the
built frontend asset returned HTTP 200. The new export rejects unauthenticated
requests with HTTP 401. The public database remains at migration
`0130_contract_obligation_review` and there were zero queued/running jobs at
cutover. Qwen/NTD were not restarted. The previous plists are saved at
`~/.asd-kontur/public-demo/launchd-backups/20261007-pre-c24a9e3-contract-condition-register/`.
The project orchestrator needed roughly 20 seconds to drain after bootout;
bootstrap attempted during its `SIGTERMed` state returned launchd error 5.
Waiting for full service disappearance and then bootstrapping succeeded.
Release health does not prove an authenticated owner download; no real owner
obligation was confirmed merely for qualification. `ProductReady=false`.

The reusable source-side deployment guard
`tools/wait_launchd_service_stopped.py` now observes a selected application
role until launchd has fully removed it, with a bounded timeout. Use it after
`launchctl bootout` and before `launchctl bootstrap`; a `SIGTERMed` state does
not count as stopped. It does not stop/start services or inspect secret
environment values. A deterministic test covers the observed 18-second drain
and timeout. This guard is not a substitute for the release preflight, queue
drain, backup, readiness checks or rollback procedure.

Read-only qualification through the pinned owner-scoped service found 307
extracted contract clauses, seven issues, five disagreement items, five
proposed revisions and 34 referenced-attachment statements in the current
contract projection. The application-generated protocol DOCX opened in
LibreOffice and rendered to a nonempty three-page PDF. The revised-source ZIP
contained two DOCX files that opened and rendered to 30 and seven pages. This
used an isolated temporary directory that was removed at the end of the
check; no owner project row or source was changed. It establishes file
openability and basic pagination, not legal approval, full-page visual quality
or correctness of each proposed revision.

## 2026-10-07 confirmed execution-conditions schedule

The Support production view now separates reviewed contract candidates from
execution conditions. Only a source-linked candidate with a current human
`confirmed` decision enters the execution-conditions schedule. Unreviewed,
rejected and stale candidates remain visible for review but are excluded from
that schedule. The candidate's semantic category, party, clause, condition and
source locator remain available; a changed candidate invalidates its prior
confirmation. This is a planning handover, not an automatic construction-work
block, legal approval, negotiated amendment or field-work confirmation.

The Support UI shows the confirmed schedule with source links. Unit checks
cover empty and confirmed schedules plus stale-decision exclusion. The isolated
browser check confirms that review refreshes the schedule and both displayed
source links resolve to the same admitted document locator. No owner-project
decision is inserted for qualification.

Release `2dc743c438a38cbbb2f045960ebd933d65055dba` is pinned at
`~/.asd-kontur/public-demo/releases/20261007-2dc743c-contract-execution-conditions-v1`.
The public database remains at `0130_contract_obligation_review`; no migration
or owner-project review decision was added for this release. The application
queue had zero queued/running jobs at cutover. The four application launchd
roles now report the exact pinned SHA; API readiness and the built frontend
asset returned HTTP 200. Qwen and NTD were not restarted. The previous four
plists remain recoverable at
`~/.asd-kontur/public-demo/launchd-backups/20261007-pre-2dc743c-contract-execution-conditions/`.
The first bulk bootstrap hit a launchd removal/registration timing race. The
previous roles were restored, then the pinned roles were started with a drain
interval and verified individually. This deployment verifies service and UI
artifact health; it does not constitute an authenticated owner-browser review
or confirmation of any real clause. `ProductReady=false`.

## 2026-10-07 durable contract-obligation review (source checkpoint)

The Support contract handover now has a human confirmation/rejection command.
Its contract is source-bound: the Qwen candidate retains clause, party,
condition and locator; a reviewer supplies a reason; the decision is appended
to the existing workspace-owned candidate-review history. A digest covers the
exact obligation, source clause and locator. If the model/source candidate
changes, the old decision appears as stale rather than confirming new text.
An idempotency key prevents duplicate decisions, and a workspace write or
Support-review grant is required. Nothing here approves a negotiated contract,
creates a field fact, or silently blocks construction work.

Migration `0130_contract_obligation_review` adds one candidate kind to an
existing RLS-protected, deletion-scoped table; it does not modify global NTD
or platform memory. Disposable PostgreSQL acceptance checked append-only
recording, replay, stale input rejection, idempotency conflict and cross-
workspace/read-only denial. An isolated browser scenario exercised the
confirm action and refreshed review state. Before public deployment the
database backup/restore/upgrade path still needs qualification. This is a
source checkpoint, not a deployed product claim.

The public database was backed up to the private local archive
`~/.asd-kontur/public-demo/backups/20261007-pre-0130-contract-obligation-review.dump`
(72 MiB, SHA-256 `02c96d0f040c59a7d3c57302aa422afec880ab2f74a9529319a14a2387e83c46`).
It restored without error in an isolated PostgreSQL cluster after the
application role names were recreated there. Migration `0129 -> 0130`,
disposable downgrade `0130 -> 0129`, and re-upgrade passed on the restored
copy. The public application queue was empty before the controlled cutover.
The four application roles now run exact code SHA
`f57276e9df70400a52017cae62a4aae9e52b2f01` from
`~/.asd-kontur/public-demo/releases/20261007-f57276e-contract-obligation-review-v1`;
API readiness and the new frontend asset returned HTTP 200. Qwen and NTD
workers were not restarted. The previous application plists are at
`~/.asd-kontur/public-demo/launchd-backups/20261007-pre-f57276e-contract-obligation-review/`.
The pinned read path showed 274 source-linked obligations and zero human
confirmations in the owner's workspace; the unauthenticated review command
returned HTTP 401. No owner candidate was confirmed merely to test the API.

A raw whole-file `pg_dump` hash changed between invocations because dump
metadata is not a stable data fingerprint. Exact per-table COPY-section
digests matched for all 170 platform tables between the restored pre-migration
backup and the migrated public database (aggregate SHA-256
`9723d28216e88cf6d7540f40cc96b5df8f80664a74c84054868fc95614cf2e70`).
The checked NTD counters remained 15 documents, 15 editions, 1,669 semantic
rows, and zero in the three inspected embedding/graph/search tables. The
isolated restored cluster and diagnostic dumps were stopped and moved to
Trash; the secured pre-migration backup remains for rollback. This validates
platform data preservation for this cutover, not full NTD operational
readiness or four-mode product readiness.

## 2026-10-07 reviewer-selected draft revisions (source checkpoint)

The Tender contract page now lets a reviewer choose which Qwen-proposed
revisions to include in the downloadable editable contract-source package.
The selection is bound to a fingerprint of the exact current proposal text,
original clause text and source identities. Unknown, duplicate, empty or
stale selections fail closed; the client cannot submit replacement wording
through this endpoint. Unselected admitted DOCX sources remain byte-for-byte
unchanged in the ZIP. The default server export remains the existing all-
proposal draft for compatibility. This selection is an export preference,
not a durable legal acceptance, signature or Customer agreement.

Changed-source tests exercised stale rejection and an actual two-DOCX ZIP in
which only one chosen clause changed. An isolated browser scenario verified
checkbox selection and the fingerprinted export link. A durable human review
decision and legal-authority gate remain necessary before a contract can be
called accepted. This checkpoint is source-only until a controlled release.

The checkpoint was deployed as exact release
`ef34c48ff7eb85e457d411a10f7cad10a7b85de7` at
`~/.asd-kontur/public-demo/releases/20261007-ef34c48-contract-selection-v1`.
All four application launchd roles run that SHA after a 4/4 staging
preflight. The API and new frontend asset returned HTTP 200 after startup;
the selected-export route returned HTTP 401 without authentication. The
database remains at `0129_contract_reference_review`; no migration was
introduced and no public queue job was active at cutover. Qwen and NTD were
left running. Previous plists are at
`~/.asd-kontur/public-demo/launchd-backups/20261007-pre-ef34c48-contract-selection/`.
An authenticated browser download and all-page layout inspection remain
unverified, so neither contract readiness nor ProductReady is claimed.

## 2026-10-07 source-linked Support handover candidate

The Support production view now carries the same workspace's Qwen-extracted
Customer and Contractor obligations with clause, condition and exact source
locator. The browser presents them as a review list before execution. This is
read-only: extraction does not silently become an accepted obligation,
mandatory work prerequisite, approved contract change or field fact. Clauses
without a source locator or obligation do not enter the handover. The
underlying Tender projection remains the single source; no project data is
copied into platform knowledge.

Changed synthetic-party tests verified party/source preservation, duplicate
suppression and same-owner/same-workspace access. An isolated PostgreSQL
browser scenario displayed the new Support table and source navigation. The
human review/acceptance command, scoped transfer into actual Support process
rules and full contract legal-authority qualification remain open. This slice
alone does not establish Support or contract readiness.

Release `dc54b172bbc8005eb6e49124462f6a11f58a11a6` was pinned at
`~/.asd-kontur/public-demo/releases/20261007-dc54b17-support-contract-handover-v1`.
The four application launchd roles passed the exact-argument/SHA/migration
preflight and were restarted from this release. API readiness and the new
frontend asset returned HTTP 200; public migration remained
`0129_contract_reference_review`. The public queue had zero queued/running
jobs before cutover, so no active project inference was interrupted. Qwen and
NTD workers were not restarted. A read-only call through the pinned service
against the owner workspace returned 274 sourced candidates: 63 Customer and
211 Contractor. This verifies the backend handover data, not an authenticated
owner-browser session or human acceptance. Previous plists are recoverable at
`~/.asd-kontur/public-demo/launchd-backups/20261007-pre-dc54b17-support-contract-handover/`.

## 2026-10-07 source-linked obligations result

The existing Qwen clause output already separated Customer and Contractor
obligations and their conditions, but the professional result hid those fields
in the clause payload. Tender contract analysis now presents them in a party,
obligation, condition and source table in the browser and editable Word
report. Clauses without an extracted obligation do not produce a fabricated
row. The source clause remains accessible for review; these are extracted
candidate duties, not accepted legal conclusions or a Support handover yet.
Changed-name/changed-term Word qualification and the isolated browser scenario
passed. The Support obligation-transfer and human decision workflow remain
open before contract capability readiness.

The exact `f952863e2fbded996f9f7d12e9d462b3850ea677` code-only release is
now pinned under all four supervised application roles. The deployment kept
database migration `0129_contract_reference_review`; API readiness and the new
frontend asset both returned HTTP 200. Qwen and NTD were not restarted, and no
public project job was queued or running at cutover. Read-only qualification
of the retained owner contract projection found 307 source-linked clauses,
with 63 extracted Customer obligations and 211 Contractor obligations; the
editable Word report rendered as a nonempty 27,434-byte package. The count is
an observation of candidate clauses, not an accepted obligation register.
The previous launchd plists are recoverable from
`/Users/oleg/.asd-kontur/public-demo/launchd-backups/20261007-pre-f952863-contract-obligations/`.

## 2026-10-07 contract-only live integration qualification

An opt-in isolated PostgreSQL acceptance now uploads one changed-party synthetic
construction contract DOCX without PD/RD, runs the application's ordinary
orchestrator and document worker against the persistent local Qwen process, and
requires a grounded payment-risk disagreement, no risk on an ordinary defect
warranty, an editable protocol DOCX, and a valid revised-contract ZIP. It
creates no workspace in the owner's public database and does not insert
precomputed Qwen conclusions or manually create successor jobs.

The second bounded run passed in 160.27 seconds: the ordinary pipeline
completed contract analysis, the API returned both artifacts, and the ZIP
integrity check passed. The persistent Qwen completion counter rose from 878
to 881 during the run. The first diagnostic run was interrupted at 189.66
seconds after accepted semantic output appeared but before the artifact
condition had been observed; no owner workload was interrupted. The test now
terminates early if the isolated job queue becomes quiescent without the
deliverables, while retaining a 900-second ceiling. Command:
`ASD_RUN_LIVE_CONTRACT_ONLY=1 ASD_TEST_DATABASE_URL=<isolated PostgreSQL admin URL> .venv/bin/pytest -q tests/integration/test_contract_only_live.py`.

A stricter follow-up on a fresh isolated database passed in 83.11 seconds. It
checked the actual revised DOCX text: the selected Qwen proposal was applied,
the unrelated ordinary warranty clause remained, and both DOCX and ZIP
containers reopened without corrupt members. This run stopped on the direct
editable revised-contract candidate, so a one-source contract does not wait
for a redundant multi-source package UI state.

This establishes one controlled contract-only professional path, not a full
contract-capability or four-mode acceptance. The qualification is source-code
only at this checkpoint; the deployed release remains `18bf2a2`. The public
database, NTD worker, and owner project were not mutated for this test.

## 2026-10-07 bounded live-model and progressive-view checkpoint

The reusable contract-analysis task was exercised against the existing,
persistent local Qwen service with two changed synthetic clauses. Its strict
validator accepted one exact-source customer-controlled payment risk and left
an ordinary 24-month defect warranty unflagged. The model completed two
requests (counter 873 to 875); elapsed times were 31.368 and 12.856 seconds.
The fingerprinted qualification receipt is
`sha256:54d280d23627ef2bd75a82f5959104dec36f6af941f19e5241875a6959d3805e`.
The repeatable command is `tools/qualify_contract_analysis_live.py`; it never
creates a workspace or advances the production queue.

The contract-analysis UI now refreshes its structured result every 30 seconds
while open. An isolated browser test observed the initial extraction message
change to a source-linked clause without a page reload or a manual job action.
The exact `18bf2a2b57f84c3c8a478f65603d0bb15c926eff` release was then
installed under the four supervised application roles with migration
`0129_contract_reference_review` unchanged. The candidate passed the 4/4
launchd topology preflight, the post-cutover API readiness check returned
HTTP 200, and the new frontend asset returned HTTP 200. No project jobs were
queued or running at cutover; Qwen and the NTD worker were not restarted.
Rollback plists are in
`/Users/oleg/.asd-kontur/public-demo/launchd-backups/20261007-pre-18bf2a2-contract-progress/`.
This closes a progressive-display defect, **not** the contract-only autonomous
application acceptance. Full legal-authority review, source-preserving
multi-page visual qualification, authenticated live download, and all four
mode terminal acceptance remain open. `ProductReady=false`.

## 2026-10-07 exact-span Word formatting correction

The revised-contract renderer previously placed an entire edited paragraph in
its first Word text run. A source clause split across bold, plain and italic
runs therefore lost the styling of untouched text outside the change. The
renderer now edits only text nodes intersecting the exact validated source
span, preserving unrelated runs and package members. A changed-name synthetic
contract test covers a clause crossing two runs with separately styled prefix
and suffix. All 14 focused revised-contract tests and Ruff pass. This is a
source-code checkpoint, **not** a deployed or multi-page visually qualified
contract result. Full contract-only, legal-authority, attachment-reference and
four-mode acceptance remain open; `ProductReady=false`.

Read-only application generation from the retained real contract projection
also produced an 86,479-byte revised candidate (SHA-256
`73c3dbddb2ebe3bb5b8e75174dc86797388eb96b890402ea7a3c496f0d3714b7`).
Its 18-member OOXML package has no corrupt ZIP member and contains
`word/document.xml`. This did not schedule Qwen work or mutate the workspace.
The host still lacks LibreOffice, so this check does not establish complete
visual layout acceptance.

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

The live professional projection also demonstrated that accepted clauses could
exist while the `Ключевые условия` summary remained empty whenever the broader
project model had not yet supplied contract facts. A staged generic projection
now selects bounded headline conditions from accepted Qwen clause categories
and their exact source text. It admits actual numeric clause references, rejects
schedule/table identifiers such as `item_*`, prefers primary two-part clauses
over subordinate obligations and keeps existing project facts first. It does
not infer contract meaning from keywords or replace missing participant/project
facts. Changed-name tests prove the fallback and source navigation. This change
is not deployed into the active v8 run; it is staged for the next controlled
release after the current immutable checkpoint reaches terminal state.

Quick Look visual inspection of both editable Word outputs found that the
general analysis artifact was incorrectly titled as though it were the
standalone disagreement protocol, and its dense tables used default body
typography. The staged renderer now calls the general artifact
`Договорный анализ и предложения Подрядчика`, preserves the separate
`ПРОТОКОЛ РАЗНОГЛАСИЙ` title, and uses compact table text in the existing A4
landscape layout. Re-rendered source/proposed-wording tables are materially more
readable without removing source references or professional-review warnings.

## 2026-10-03 v8 terminal professional result

The real blind workspace reached a terminal v8 state without developer runtime
progression. All 78 effective `qwen-contract-analysis-v8` jobs succeeded; none
remained queued, running, failed or reconciliation-required. The autonomous run
started recording results at `2026-10-02 23:09:09 +12` and recorded its last
result at `2026-10-03 00:46:44 +12`. It persisted 307 clause units and nine raw
risk candidates. The current commercial-authority and controller-grounding
policies retain seven professional risks, five grounded disagreement items and
five proposed clause revisions.

Two raw candidates were rejected by generic post-model controls. An ordinary
cure/expert-cost clause was not allowed to become an asymmetric-termination
risk, and a contract-bounded cure obligation was not allowed to become an
unbounded-scope risk. The controls require the adverse mechanism asserted by
the finding; they do not contain the project name, document name, clause number
or wording from the blind corpus.

The accepted revisions belong to two admitted DOCX sources. Three revisions
belong to the governing contract; two belong to its technical description. A
full-document candidate previously failed closed because it required every
revision to have the same source. The generic source selector now uses the
accepted clause semantics instead of filenames: a governing contract must have
materially broader payment, acceptance, liability, warranty, security,
termination and change-procedure coverage than a competing revised attachment.
A close or weak result remains unresolved. The exact candidate applies only the
three revisions belonging to the selected governing contract. Both attachment
revisions remain in the five-item protocol and clause schedule, and the
projection records their exclusion explicitly.

Read-only staged generation against the live immutable v8 results produced:

- a contract analysis report with 307 clauses and seven retained risks,
  SHA-256 `cae2c7bf995f84d2b6bfb7cd627052059f175e0524bb0de32e629ba82f77c6f7`;
- a five-item editable disagreement protocol, SHA-256
  `240700e37fbe31b42d9b4307012db5750c5e3c2b5fe5f8fe37de3eca1b06893c`;
- an exact-format revised governing-contract candidate containing its three
  applicable revisions, SHA-256
  `7f0bb076a1a27c9ae0288b0a2d037f257e182776170539da4632a11af8d0468e`.

All three packages opened as valid OOXML. Quick Look rendered their first pages
without clipping or corrupt glyphs. The analysis and protocol retain source
navigation for all five revisions; the revised contract preserves the admitted
source layout and does not inject the two attachment-specific proposals into
the contract body. Full multi-page visual qualification remains a release gate
because the configured environment does not currently provide the bundled
LibreOffice renderer required by `render_docx.py`.

## 2026-10-03 changed-contract recovery defect and v9 design

The autonomous changed-contract acceptance reached all four v8 analysis
batches without a developer progression command. Three batches succeeded; the
batch containing the remaining liability/change clauses became terminal with
`qwen_contract_risk_controller_not_grounded`. The immutable pre-oracle blind
snapshot has SHA-256
`d33d4bc12dc7379bec099dd60fa1c8f536de3834531a8d2407a8d393815877b3`.
It contained nine accepted clauses and one grounded payment-dependency risk,
but no publishable revision because the proposed wording introduced an
unsupported numeric deadline. The external control manifest was inspected
only after that snapshot.

The failure was systemic rather than corpus-specific: one risk rejected by the
deterministic commercial-risk controller caused the parser to reject the
entire repaired batch, including exact-source clauses and any other grounded
risks. Recursive splitting reduced the context but could not make the invalid
candidate valid. Profile v9 keeps strict validation as the first path and
retains the existing bounded repair call. Only when the repaired response still
fails specifically on controller grounding does a narrow recovery pass discard
the rejected risk while preserving validated clauses and grounded sibling
risks. Invalid JSON, malformed risk structure, invented source text and invalid
contract revisions remain terminal. The accepted result records the discarded
risk count and a typed analysis warning.

Migration `0106_contract_partial_risk_recovery` admits v9 results. The read
projection retains complete v8 output until the autonomous v9 run reaches its
effective terminal boundary, so deployment cannot temporarily replace a useful
contract result with a partial new profile. Generalized changed-contract
acceptance remains open until v9 is deployed and independently produces a
grounded revision while leaving the declared benign clauses unflagged.

## 2026-10-03 autonomous v9 control result and directed-change gap

Exact-SHA CI run `37014230765` passed for commit
`aa1704d145b8199abaf7af4a6862367bff225b13`. Backup, separate restore,
`0105 -> 0106`, disposable downgrade and re-upgrade all passed with platform
fingerprint
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`
and 319 succeeded NTD jobs unchanged. Release
`20261003-aa1704d-contract-v9` activated API, document worker, orchestrator and
assistant worker without restarting Qwen or the NTD worker.

The supervised orchestrator created all v9 work without a developer queue
command. The changed control contract reached four of four succeeded batches,
retained 14 clauses and one grounded payment-dependency risk, and discarded
one controller-ungrounded candidate without losing its five-clause batch. None
of the declared benign control clauses became a professional issue. Workspace
fairness was also observed: the worker served the changed control workspace
while the larger blind contract still had more than 60 queued v9 batches.

The control still produced no protocol item. The remaining source clause
describes work carried out on the Customer's written direction before a
contract change is formalized and then expressly denies payment. Qwen selected
it as a risk, but the controller's `unpaid_change` guard recognized only an
explicit “additional/changed work” phrase. That is a generic contract-analysis
gap: the same commercial mechanism is often expressed as instructed work
pending a change order or addendum.

Profile v10 extends the generic guard only when the exact full clause jointly
contains all four semantic controls: work scope, Customer direction, contract
change formalization, and explicit payment denial. The rule contains no
project name, clause number, party name, document name or expected value.
Changed-name tests prove the mechanism, while existing false-positive tests
continue to reject overpayment restitution, ordinary cure costs and Customer
mentions that do not confer control. Migration
`0107_contract_directed_change_risk` admits the new profile. Live v10
acceptance remains required before the generalized contract gate can pass.

The same live transition exposed avoidable model work: after a newer contract
profile was admitted, unclaimed batches for the prior profile remained queued
even though the atomic read projection would never select their eventual
output. The v10 scheduler now terminally cancels only queued older-profile
contract jobs when it has eligible sources for the current profile. Every such
job receives a cancellation request, terminal receipt, typed reason and event.
Running jobs and all completed immutable results are preserved. A PostgreSQL
integration test proves that an older queued job is cancelled while a queued
current-profile job remains runnable. This is runtime convergence, not manual
queue cleanup.

## 2026-10-03 v10 release and changed-contract acceptance

Commit `702551bd8c5c2bea08d4f749570c7bb783982a0f` passed exact-SHA CI run
`37017462813` and was activated as release
`20261003-702551b-contract-v10` at migration
`0107_contract_directed_change_risk`. The pre-release database backup has
SHA-256 `2fbb8cdcd74c259c303a3c9f5ce91daf13acc84107916896b488dfb23254f57d`.
Separate restore, upgrade, downgrade and re-upgrade checks passed before the
controlled public database was migrated.

The activation restarted only the API, document worker, project orchestrator
and assistant worker. Qwen and the NTD worker were not restarted. The canonical
platform-memory fingerprint remained exactly
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`,
and the NTD job ledger remained at 319 succeeded jobs.

The supervised runtime created and completed all four v10 batches for the
changed contract without a developer queue, retry or successor command. The
effective professional result contains 14 clauses and two contractor risks:

- clause 4.8 makes payment depend on receipt of investor financing. The risk is
  retained, but the proposed wording is not published because Qwen introduced
  an unsupported numeric payment deadline;
- clause 6.7 denies payment for work performed on the Customer's written
  direction before formal execution of the contract amendment. Its exact-source
  grounded revision is retained as one disagreement item and one revised clause.

None of the declared benign control clauses was projected as a professional
issue. This proves that the system can retain a real contractor risk without
turning every Customer-favourable or ordinary clause into a disagreement.

In-memory application generation produced three valid OOXML packages:

- analysis report: 5,488 bytes, SHA-256
  `2c6b279d18332ebdf798eb581d2a2950d2005e073e3b8e61c9cb59cfe6298154`;
- disagreement protocol: 3,460 bytes, SHA-256
  `20478bac36939860f09649b8674682795e8903ddf20a19614a25333fe655e05d`;
- exact-source revised contract: 38,323 bytes, SHA-256
  `92447fda9fcb7109d897e80493a11dadfbb325318d4d9cc5fa78f76000a13b5d`.

The real blind contract had already reached a terminal autonomous v8 result
with 307 clauses, seven retained risks and five disagreement items. The changed
contract v10 result provides the independent generalization and false-positive
control. Full multi-page visual qualification of generated Word documents
remains an output-release limitation because the configured environment lacks
the required LibreOffice renderer; OOXML structure, application generation,
source-preserving revision and browser export routes are qualified.

The v10 transition also converged obsolete queued work without manual row
patching: 36 queued older-profile jobs were cancelled with durable supersession
receipts, while jobs already terminal remain immutable history. A further 24
old-profile claims failed fast with the typed supersession outcome rather than
consuming Qwen inference. Current-profile work continued autonomously.

## 2026-10-03 editable real-contract artifact checkpoint

The current real blind-contract projection remains `drafted` with a complete
assessment. It identifies `Проект_контракта.docx` and
`Описание объекта закупки.docx` as its contract sources and exposes 307
clauses, seven structured contractor issues, five disagreement items and five
proposed revisions. The exact-source revised-contract candidate applies three
revisions that belong to the governing contract. Two proposals grounded in an
attachment remain in the protocol and are deliberately excluded from the
contract body under the explicit limitation
`REVISED_CONTRACT_EXCLUDES_NON_PRIMARY_SOURCE_REVISIONS`.

The application-generated qualification set is stored at
`~/.asd-kontur/qualification/contract-analysis-20261003/01a0eba7-70ba-7770-9601-1a713dd359cf/v10`:

- `contract-analysis.docx`, SHA-256
  `4cb4f396cbc468855d3cb0490ba5053474493ae78c8d270012758665ddc8af69`;
- `disagreement-protocol.docx`, SHA-256
  `432eaf8ba780a3285dc5f09a30ab7a38dbec03fe6ad63ddf9ac8d08f33d6135d`;
- `revised-contract-candidate.docx`, SHA-256
  `7f0bb076a1a27c9ae0288b0a2d037f257e182776170539da4632a11af8d0468e`.

The manifest SHA-256 is
`4fba33a4142463231c8c0c0fb07d222c332976fec8c75a62e8f723c9ce108813`.
ZIP-package integrity and macOS text extraction passed for all three files.
Quick Look thumbnails of the first page were visually inspected: both analysis
tables are readable and the revised candidate preserves the admitted source
layout. A complete multi-page render and XSD validation are not claimed in
this checkpoint because the available environment lacks LibreOffice and the
validator environment lacks `lxml`.

## 2026-10-07 contract-only comparison coverage correction

The source implementation now distinguishes an absent project comparison input
from a completed comparison with no finding. The contract projection reports
whether design-scope, commercial-scope and schedule source roles are represented
in the current project model. The contract screen and editable analysis report
name missing inputs and explicitly warn that no finding is not proof of no
contradiction. This is a conservative availability indicator, not proof that a
cross-check ran or that the supplied documents are complete. Document roles,
not filenames or project-specific names, drive it. Contract-only input remains
an independent valid analysis path, with project cross-check limitations shown.

This checkpoint is source-only pending a controlled release. It neither changes
the live contract projection nor establishes full contract or product readiness.
The editable CSV export now carries the same per-input coverage states as the
screen and Word report, so a spreadsheet consumer does not silently interpret
an empty findings table as a completed project-to-contract comparison.

The OCR route was checked before altering scheduling: persisted Qwen OCR elements
enter `native_layout_element_versions` with source locators; the supervised
reconciler counts readable persisted elements and can queue role classification
and contract analysis for that source. The `native_locator_count` field is
misleadingly named, but it does not exclude OCR output. No OCR scheduler change
was justified by this inspection.

Comparison coverage semantics were also tightened. Presence of a document role
is now reported as `source_role_present`, not `input_available`; it does not
claim that a comparison has run. Where no project-contract finding is
published, the UI and Word report state that comparison completeness is not
confirmed. These are truthful source-only presentation boundaries, not a
substitute for the still-missing exhaustive project/contract comparison engine.

The candidate contract projection previously called the corpus assessment
`complete` whenever all *existing* effective jobs were terminal. That was
insufficient: an admitted contract source could have no job, or one of its
bounded source segments could have no accepted result. The projection now
checks successful result segments against the readable layout denominator for
every current contract source. Incomplete source names are disclosed in the
screen, Word report and CSV; protocol/revised-contract readiness remains
partial until coverage is complete. The planner's readable-locator count was
aligned with the same raw-or-normalized text rule used to form contract batches.
This prevents a normalized-only source from being silently excluded at the
scheduling gate. The change has no database migration and has not been
deployed or exercised on a live contract in this checkpoint.

An isolated PostgreSQL API qualification now covers the actual normalized-only
case: one admitted `text/plain` contract source with blank `raw_text`, readable
`normalized_text`, and a current Qwen contract-role decision. Before Qwen runs,
the API reports one incomplete contract source rather than a complete corpus;
the project-understanding scheduler creates one current-profile
`CONTRACT_ANALYSIS` job from that same source. The test database is created as
`asd_g04_test_*` and removed by the integration fixture. This establishes the
application/SQL boundary for this case, not a live model result or full
contract-only journey.

## 2026-10-07 exact-source release candidate and read-only check

Commit `46aab7680633d0e93cda7b552bca8b04e4c84f41` was archived into a
non-active qualification release at
`~/.asd-kontur/qualification/contract-release-46aab76.7Wcuie`.
Its isolated Python environment installs from the frozen lock; frontend
`npm ci`, production build and TypeScript check pass. The transitive
`source-map-js` lock was raised from 1.2.1 to patched 1.2.2 after the
[reviewed advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q);
`npm audit` reports zero known vulnerabilities for the candidate.

The staged read projection was exercised without writes against the existing
real contract workspace. It returned a drafted assessment with two of two
current contract sources complete and no uncovered sources; one revised-contract
candidate remained eligible. An independent SQL aggregate found all 576 of 576
readable current-source locators covered by accepted v10 result segments. This
checks that the new gate does not demote an already-covered corpus. It does not
validate the substantive legal findings or activate the staged code.

All-page Word rendering remains unqualified. The installed ONLYOFFICE `x2t`
converter returned its `open` error for both an existing generated report and
a trivial synthetic DOCX, so that invocation is not evidence that the report
is malformed. LibreOffice 26.8.0 was installed as a local QA tool, not an
ASD-KONTUR runtime dependency. Its first headless conversion produced no PDF;
the `soffice` wrapper remained at `_dyld_start` with no rendering child, and
even `soffice --version` did not return. Both bounded attempts were stopped.
Existing ZIP/XML integrity and first-page Quick Look checks do not satisfy
all-page visual acceptance. The owner-facing launchd services were not
restarted or repointed during this qualification.

## 2026-10-07 autonomous contract-reference review (source candidate)

The prior clause analyzer worked on bounded pieces of each contract document.
It could identify explicit clause risks but had no corpus-level account of
documents referenced by those clauses. An absent attachment could therefore
be invisible to the user even when its reference was readable. The new
`CONTRACT_REFERENCE_REVIEW` stage is a separate, workspace-owned Qwen task:

1. the supervised project reconciler selects active sources with a current
   Qwen `contract` role and routes likely cross-reference text; its lexical
   gate does not decide whether an attachment exists;
2. every job identifies exact source segments and the complete active admitted
   source inventory in its idempotency digest;
3. the same persistent local Qwen endpoint interprets the reference and may
   match an admitted source, or returns `unresolved` with an exact source quote;
4. validation rejects invented quotes, unknown source identities, malformed
   decisions and unsupported output; one output-budget failure splits the
   bounded task instead of retrying an identical oversized prompt;
5. accepted results are stored with model/profile identity in the existing
   workspace-owned contract result store, exposed in the contract screen,
   editable Word/CSV analysis and consultant context. An unmatched reference
   is a request to verify package composition, not proof that an attachment
   is missing.

The read model invalidates old reference matches when the admitted document
inventory changes. Unclaimed jobs tied to a superseded inventory are
terminally cancelled rather than spending the model slot on stale work. The
new job kind shares the existing single-heavy-model claim policy and is
handled by the supervised document worker; Codex is not its dispatcher.
Migration `0129_contract_reference_review` adds the job kind and result
profile without adding a new project-data store. Workspace destruction already
owns the result table. A disposable PostgreSQL database passed full upgrade,
clean downgrade and re-upgrade. Isolated API qualification exercised automatic
orchestrator scheduling, exact-source Qwen-response validation and persistence,
unresolved-reference publication, and invalidation/requeue after a later source
admission. Unit tests use changed synthetic contract names and do not encode
the real owner's project findings.

This is a **source candidate, not a deployed capability**. The live API/worker
remain on the older pinned release. No real-project reference result or live
Qwen output from this new stage is claimed. The v1 routing gate can miss an
unusual implicit document reference; inventories above 64 active sources are
explicitly marked outside its current comparison bound. The separate legacy
Tender-process read path now merges this workspace-scoped autonomous reference
projection when a canonical process already exists; a disposable PostgreSQL
integration check covers the merge alongside the autonomous candidate path.
Substantive all-page Word rendering, live contract-only acceptance and legal
review remain open. A local Pages automation attempt on a trivial DOCX did
not return a PDF; it was stopped. LibreOffice still stalls before its main
code despite verified signing and a targeted quarantine-attribute removal.
The local bundled ONLYOFFICE x2t converter also returned an `open` error on
a trivial synthetic DOCX, so its failure is not evidence that the generated
contract file is malformed. All-page visual qualification remains open.
macOS Quick Look rendered the first page of the real revised-contract candidate
locally; the title, body text and first two sections are legible in that
thumbnail. This is first-page evidence only, not an all-page layout pass.

The DOCX skill's independent OOXML/XSD validator passed the generated revised
candidate with 566 paragraphs. As a bounded local content-continuity check,
macOS `textutil` converted that DOCX to HTML and headless Chromium printed the
HTML to a 13-page A4 PDF; all 13 surrogate pages were rendered and inspected
as a contact sheet. The retained DOCX metadata declares 30 pages, and HTML
conversion changes pagination and styling. Therefore this is **not** an
all-page visual qualification of the editable DOCX; that release gate stays
open until a working direct Word-compatible renderer is available.

The repeatable `tools/qualify_contract_references_live.py` command exercised
the same validated reference task against the already loaded local Qwen model
using three changed synthetic inputs, without a live workspace or queue write.
Unresolved reference, matched attachment and no-reference control all passed
(3/3); model completed requests increased from 846 to 849, and the measured
case durations were 8.211, 6.620 and 0.953 seconds. The fingerprinted local
qualification receipt is
`~/.asd-kontur/qualification/contract-reference-live.bJqApc/report.json`
(`sha256:f9419de0bef33af2f33ca8bec4dcfdfec0cbaed8ecf984b2ef04ae9d6c362ff1`).
This is real Qwen task acceptance on synthetic context, not an autonomous
project run or a real-contract conclusion.

## 2026-10-07 controlled public contract-reference release

The exact code release `b973ec392bce41aeed8054220cb1b7fd46894eeb` is
pinned at `~/.asd-kontur/public-demo/releases/20261007-b973ec3-contract-reference-v1`.
The four application roles (API, document worker, project orchestrator and
assistant worker) were switched together; Qwen, NTD and ingress were not
restarted. The public database advanced from `0128_destroyed_object_redaction`
to `0129_contract_reference_review` after a consistent 71 MB custom-format
backup at
`~/.asd-kontur/public-demo/backups/pre-0129-contract-reference.KM8h8J/public-before-0129.dump`
(SHA-256 `381119936141cb2535859f8ed1e8584837aa5c87c145b07e4c65918b346fecb8`).
A separate restored copy passed upgrade, explicit disposable downgrade and
re-upgrade. The restored pre/post workspace counts were exactly 44 workspaces,
22 source versions, 7,060 durable jobs, 261 contract result rows and 10,939
native layout elements. Both disposable restored databases were then removed;
the public rollback backup remains. A deterministic platform-data dump with
fixed PostgreSQL restrict key retained SHA-256
`1742758f99279a4f4114a693bc1cd0addf36747ae3751d3b8d611ee79eaa31a1`
before and after rehearsal and public migration.

The active local API returned HTTP 200 `ready` at migration `0129`, its exact
built frontend asset returned HTTP 200, and an unauthenticated contract route
returned HTTP 401. The supervised orchestrator autonomously created seven
`CONTRACT_REFERENCE_REVIEW` jobs for the owner project and one for a separate
active workspace; the local Qwen service accepted and completed the first owner
batches without a Codex queue command. The owner-scoped read projection exposed the accepted references
and marked the review in progress. The in-app/external browser was unavailable
to this execution session, so authenticated visual acceptance is not claimed.
No legal approval, full contract-only journey, or direct all-page DOCX visual
acceptance is implied by this incremental release. `ProductReady=false`.

## 2026-10-07 bounded invalid-output recovery candidate

Read-only observation of the autonomous owner run found one six-segment
`CONTRACT_REFERENCE_REVIEW` batch terminally rejected with
`qwen_contract_reference_invalid_item` after the existing one-shot JSON
repair. Accepted earlier batches remained intact. The candidate implementation
now splits a still-invalid multi-locator response into smaller local Qwen
tasks, retaining the exact quote and inventory validators. A single-locator
invalid response remains a typed terminal failure. For an already-failed batch,
the supervised reconciler schedules one idempotent `invalid-output-split-v1`
replacement using the same source/inventory identity; accepted batches are
not replayed. The read projection treats a failed predecessor as recovered
only when its matching batch has a running or accepted replacement. A
disposable-PostgreSQL API test covered one replacement, repeated sweeps,
recovery status and supersession after source-inventory change. This fix is
source-only until a controlled release; the public worker is still running the
earlier pinned code and no live repair result is claimed here.

The repair code was subsequently pinned as
`5f295291d4e3fd703daafc8adfeaf7e01246beef` in
`~/.asd-kontur/public-demo/releases/20261007-5f29529-contract-reference-recovery-v1`.
No database migration was needed. A first launchd cutover used an incorrectly
edited argument array: the four application roles exited before startup with
a Python binary interpreted as a script. The staged and installed plists were
corrected and reloaded; the API, document worker, orchestrator and assistant
worker then ran from the pinned Python path. The API returned HTTP 200 `ready`
at migration `0129`; Qwen and the NTD worker were not restarted. After the
supervised orchestrator's next sweep, exactly two versioned replacement jobs
appeared for the two previously failed owner batches, without a manual queue
operation; the first was claimed and Qwen began generation. This demonstrates
autonomous repair scheduling, not yet successful completion of both batches.

Read-only runtime observation found the first replacement accepted four
source-bound references. The second six-locator replacement was still active
after multiple completed local-Qwen requests with a fresh lease heartbeat.
This measured cost motivated a further source-only refinement: when a
multi-locator response contains an invalid source-bound item, split it
immediately instead of spending one identical broad repair request first.
Malformed JSON still receives one bounded repair; singleton invalidity still
fails closed. The refinement does not interrupt or modify the running job.

The failed launchd cutover also gained a read-only release preflight:
`tools/check_launchd_release.py` verifies the exact four-argument command for
each application role, executable/frontend presence, pinned SHA and migration
head before bootout. A changed synthetic plist test rejects the duplicate
Python argument that caused the outage. No secret environment value is printed.

The two owner-workspace replacement jobs subsequently both succeeded under
supervised workers. The effective review is seven of seven source batches;
the two original failed jobs remain historical terminal receipts. The current
projection contains 34 source-grounded references, 31 with unresolved
admitted-document matches. This is a package-composition question, not proof
that 31 attachments are absent. Qwen's completed-request counter advanced
from 859 to 873 while the two bounded repairs ran, showing that this narrow
task was expensive despite eventual convergence.

The resulting contract view exposed a separate professional gap: three
proposed revisions belonged to the primary admitted DOCX and two to a second
admitted DOCX. The existing single-file candidate correctly disclosed the two
excluded revisions but did not give the user a complete set of edited source
documents. A new source-only package renderer now emits every current admitted
DOCX contract source, applies only exact, source-bound revisions, preserves
unaffected files byte-for-byte, and includes a manifest with per-source hashes
and revision counts. It fails closed on unknown revision sources, ambiguous
clause matches and signed sources whose signature would be invalidated. The
user-facing endpoint and link name this an editable candidate package, not an
approved contract. Read-only in-memory qualification against the actual owner
workspace produced a valid ZIP with two DOCX files, revision counts 3 and 2,
and no corrupt ZIP member (121,083 bytes). This exercised deterministic
assembly from persisted Qwen results and admitted source bytes; it did not
alter the owner's project or prove browser download/all-page visual quality.

## 2026-10-07 multi-source contract package release

Release `6443023bce026b6988044b5e79f4d14bacd5c55c` is pinned at
`~/.asd-kontur/public-demo/releases/20261007-6443023-contract-package-v1`.
The four staged application-role plists passed the new executable/argument,
SHA and migration-head preflight before cutover. The API, document worker,
project orchestrator and assistant worker run from that pinned release; Qwen
and NTD were not restarted. The public database remains at
`0129_contract_reference_review` with no new migration. The local readiness
API returned HTTP 200, the new built frontend asset returned HTTP 200, and
unauthenticated access to the new ZIP endpoint returned HTTP 401.

The deployed owner-scoped service reports 7/7 effective contract-reference
batches complete, 34 references, and 31 unresolved admitted-document matches.
It exposes an `exact_source_package_available` candidate. A read-only
render through the pinned service produced a valid ZIP containing the two
admitted DOCX contract sources with 3 and 2 exact revisions respectively;
the manifest carries the 31 unresolved references and only the remaining
package-relevant gap. This is a draft for human/legal review, not a signed or
agreed contract. The in-app browser was unavailable to this session, so an
authenticated browser download and all-page Word-compatible visual inspection
remain unverified. `ProductReady=false`.
