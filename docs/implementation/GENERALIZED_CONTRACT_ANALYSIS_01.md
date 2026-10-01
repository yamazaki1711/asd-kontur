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

## Safety and reuse decision

Legacy MAC_ASD prompt/service/RKB code was used as capability evidence only.
No legacy component was reused as-is. In particular, ASD-KONTUR does not restore
approved-on-model-failure behavior, placeholder parties, blanket statutory
citations, whole-contract unbounded prompts, keyword-only authority, or stale
legal conclusions. The old RKB remains a review backlog until each pattern is
classified for current, generic use.

## Validation state

The pure structured-output validator has changed, project-independent tests for
a genuine contractor dependency risk, a benign payment clause, invented source
text rejection, and mandatory replacement wording. Full unit and frontend
checks pass at this checkpoint.

The remaining acceptance work is:

1. migrate a disposable PostgreSQL database through 0097 and verify downgrade /
   upgrade reproducibility;
2. deploy the release without interrupting active Qwen work;
3. observe autonomous contract discovery and multiple live Qwen batches on the
   current blind project, with no manual queue command;
4. inspect the independently generated findings and editable DOCX;
5. run a changed controlled contract with a benign clause and a substantive
   risk, without a production code change;
6. integrate accepted draft contract findings into the primary Tender summary;
7. implement and qualify a format-aware full revised-contract candidate if the
   source format supports exact clause replacement.

Until those runtime gates pass:

- `ContractAnalysisOperational=false`
- `ProtocolOfDisagreementsOperational=false`
- `GeneralizedTenderHarness=false`
- `AutonomousProjectProcessing=true` (preserved baseline, subject to release smoke)
- `ProductReady=false`
