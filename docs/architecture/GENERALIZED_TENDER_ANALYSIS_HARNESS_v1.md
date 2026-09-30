# Generalized Tender Analysis Harness v1

## Product boundary

The harness turns a previously unseen construction document package into a
progressively improving preliminary Tender analysis. A project corpus validates
the harness; it never defines the harness. Production code and prompts must not
contain a workspace identifier, project name, expected facility, expected
quantity, or expected discrepancy.

The user-facing model is:

`Project -> Facility/Area -> Structure/Element -> Work -> Quantity/Material`
`-> Requirement -> Issue/Risk -> Action -> Document`.

Source locations, candidate versions, receipts, confidence, and queue state are
supporting safeguards. They are not the primary professional result.

## Responsibility split

### Deterministic application code

Deterministic code owns admission, hashes, page and source identities, durable
jobs, retries, validation, persistence, revisions, exact identifier matching,
unit normalization, arithmetic, duplicate control, schedules, comparison after
scope compatibility is established, and reproducible report assembly.

### Local Qwen

Qwen owns bounded semantic interpretation: document role, project purpose,
entities, construction meaning, work normalization proposals, quantity scope,
total/component relationships, ambiguous identity, document-scope matching,
engineering contradictions, commercial completeness, procurement/contract
meaning, and NTD applicability. Its output is strict JSON with input identities,
decision, normalized interpretation, relationships, confidence, ambiguity, and
source references. Malformed output receives a bounded repair/retry and then a
typed failure; it is never silently accepted.

### Permanent knowledge

Global NTD, Practice Intelligence, generic work concepts, comparison policies,
and templates remain outside workspaces. Project entities, aliases, quantities,
materials, findings, interpretations, and conversations remain workspace
scoped. A project may propose an unknown work concept, but cannot promote it to
the global catalog.

## Staged analysis

1. **Document package understanding** classifies roles from title pages,
   headings, stamps, tables, contents, and filename support signals. The
   reusable vocabulary includes project/working documentation, drawings,
   specifications, estimates, procurement notices, technical specifications,
   schedules, calculations, surveys, contracts, customer requirements, and
   administrative correspondence; it does not depend on a project filename
   table.
2. **Project understanding** identifies purpose, location, participants,
   facilities, structures, areas, and functional relationships.
3. **Engineering entity extraction** emits typed, source-located entities.
4. **Work/quantity/material understanding** gives each numeric value an
   engineering scope and retains unknown work concepts without forcing a match.
5. **Scope reconciliation** resolves supported identities and records localized
   ambiguity.
6. **Cross-document comparison** compares only compatible engineering scopes
   across design, drawing, calculation, specification, commercial, contract,
   and schedule roles.
7. **Professional findings** explain the conflict, consequence, uncertainty,
   and action in construction language.
8. **NTD checks** retrieve from structured project/work context, resolve edition
   where possible, and keep uncertain applicability local to that check.
9. **Adaptive Tender report** publishes available professional sections and
   omits unavailable ceremonial sections.
10. **Consultant access** retrieves compact task-specific slices of the same
    persisted project model; it does not rediscover the project from raw text.

The task vocabulary is defined by `TenderAnalysisTask`: document role, project
entity, work, quantity scope and relationship, material relationship, structure
identity, document scope, contradiction, commercial completeness, procurement,
contract, and NTD applicability tasks.

## Quantity semantics

A `QuantityStatement` contains identity, decimal value, normalized unit,
semantic scope, quantity type, entity/work/material context, source role, and
revision. Supported semantic relationships are `COMPONENT_OF`, `SUBTOTAL_OF`,
`TOTAL_FOR`, `ALTERNATIVE_TO`, `DUPLICATE_OF`, `REVISION_OF`, and
`INCOMPARABLE_TO`.

Qwen may establish the semantic relationship from bounded text. Deterministic
code validates that all referenced identities exist, the subject is not its own
component, units and document roles match, entities and revisions do not
conflict, and only then performs arithmetic. A relationship may connect
separate schedule rows from the same bounded semantic batch, because project
totals and their components are commonly printed on different rows. Numeric
similarity never creates a relationship.

Scope compatibility is explicit: `SAME_SCOPE`, `OVERLAPPING_SCOPE`,
`COMPONENT_VS_TOTAL`, `DIFFERENT_SCOPE`, `ALTERNATIVE_DESIGN`,
`REVISION_DIFFERENCE`, or `INSUFFICIENT_INFORMATION`. Automatic numeric
discrepancies require `SAME_SCOPE` or a valid `COMPONENT_VS_TOTAL` relationship.

## Finding model

The professional finding vocabulary is small and reusable: quantity or
component-total mismatch, material/grade/profile mismatch, geometry or duration
mismatch, revision conflict, design work missing commercially, commercial work
without design basis, missing project information, NTD issue, contract or
procurement risk, constructability risk, and other engineering conflict.

Every finding states what, where, compared documents/conditions, interpretation,
practical consequence, recommended action, and uncertainty. A missing document
is not proof of omitted work; an ambiguous scope is not a discrepancy.

## Autonomous orchestration

Supervised ASD-KONTUR services, not Codex, own ordinary progression. Terminal job
events produce direct successors where implemented. The low-frequency project
orchestrator reconstructs active workspace state, repairs missing successors,
queues bounded retry replacements, ensures project-understanding stages, refills
semantic reconciliation, and records unrecoverable blockers. Stable semantic
digests and idempotency keys prevent duplicate work after worker, API,
orchestrator, Qwen, or machine-session recovery.

Progressive milestones are primary project facts, engineering structure,
quantity analysis, commercial comparison, partial Tender analysis, and complete
to current capability. Report regeneration reads the same versioned model, so
new accepted analysis improves the application without reprocessing unrelated
documents.

## Project-independent guarantees

- No project identifier, filename, facility, quantity, or expected answer is a
  production decision rule.
- Domain vocabulary is allowed; exact corpus answers are not.
- Unknown work concepts remain visible and workspace scoped.
- Qwen interprets meaning; deterministic code performs arithmetic and state
  transitions.
- A browser, terminal, or Codex session is not required for background progress.
- The same unchanged code must pass a controlled corpus with different names,
  structures, works, documents, values, and units before the harness can be
  declared generalized.
