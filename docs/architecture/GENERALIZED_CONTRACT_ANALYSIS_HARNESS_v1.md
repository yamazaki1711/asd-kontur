# Generalized Contract Analysis Harness v1

## Product result

When a Tender workspace contains a semantically identified contract, ASD-KONTUR
must autonomously extract its clauses, assess practical contractor exposure,
propose safer wording where justified, and prepare an editable disagreement
protocol. An absent contract is reported as a missing input. It is not reported
as a process that an operator forgot to start.

## Authority boundary

The autonomous result is a workspace-scoped commercial-risk draft. It is not a
verified legal conclusion, an approved disagreement protocol, or a signed
contract. Existing canonical Tender tables and professional decisions retain
that final authority. The analysis engine writes only immutable candidate
results; promotion/finalization remains an explicit qualified action.

## Runtime stages

1. The generic document-role classifier identifies a `contract` source from
   bounded content and source metadata.
2. The supervised project orchestrator reads durable active-source state and
   creates missing `CONTRACT_ANALYSIS` batches idempotently.
3. Exact native-layout locators form bounded contexts (at most 12 locators and
   12,000 normalized characters per batch).
4. The existing persistent local Qwen service returns strict clause and risk
   JSON. It does not perform arithmetic or alter global knowledge.
5. Deterministic validation rejects unknown locators, invented source text,
   invalid enums, missing risk explanations, and disagreement proposals without
   concrete replacement wording. Every risk must identify both its exact
   triggering wording and the exact wording that creates the adverse Contractor
   effect, obligation, dependency or measure. One bounded schema repair is
   permitted.
6. Immutable result manifests are stored in the workspace and projected into
   clauses, contractor risks, proposed changes, an editable disagreement
   protocol, and a candidate clause-replacement schedule.

## Qwen and deterministic responsibilities

Qwen classifies clause meaning, extracts obligations, interprets practical
contractor risk, and drafts Russian professional explanations and safer wording.
Deterministic code owns exact source text, locator identity, batching,
idempotency, persistence, numeric/date arithmetic, result assembly, access
control, and version history.

## Generalization and false-positive policy

The prompt contains risk questions and a reusable taxonomy, never project
names, known clauses, expected quantities, or expected findings. A balanced
clause is allowed to produce no risk. Customer-favorable wording is not by
itself a disagreement. Legal citations are not fabricated; without qualified
current authority, the output remains a practical commercial-risk conclusion.

## Autonomy and recovery

Scheduling occurs inside the existing supervised project reconciliation sweep,
not a developer tool. Stable idempotency is derived from source version,
analysis profile, and exact locator-set digest. Worker/API/orchestrator restarts
therefore do not duplicate accepted output. Temporary Qwen unavailability uses
the durable worker retry policy. Invalid model output receives one bounded repair
and otherwise terminates with a typed failure visible in the project state.

## Deliverable boundary

The harness generates an editable disagreement protocol and an explicit
candidate schedule of revised clauses. For one admitted DOCX contract, the
application may also generate a format-preserving revised-contract candidate
when every proposed replacement maps to exactly one source fragment inside one
paragraph. Missing or ambiguous matches fail closed and remain a clause
schedule. Untouched package members and untouched paragraphs remain unchanged;
source namespace declarations used by Word compatibility metadata are
preserved. Generated protocol/report packages must pass OOXML validation, and
visual qualification remains a separate release gate. Every artifact remains a
candidate for professional legal review rather than an approved or signed
contract.
