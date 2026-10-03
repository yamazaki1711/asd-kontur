# Four-mode Functional Model v1

## Common spine

Every mode uses the same practical construction model:

`project → area/facility → structure/pit → work → quantity/material`
`→ requirement → issue/risk → action → document`.

Versioned sources, locators, candidate lifecycles, rules, jobs, authorization,
and immutable history support this model internally. They must not become the
main professional navigation or be mistaken for the product result. Platform
Practice Intelligence explains construction practice. Verified NTD provides
normative authority. Qualified deterministic rules evaluate conditions where
their inputs are available. Models may interpret and propose; they do not
invent execution facts, signatures, geometry, legal approval, or normative
applicability.

## Tender

Inputs may include PD/RD, specifications, VOR/estimate, draft contract,
appendices, customer requirements and applicable NTD. The user must be able to
understand what is being built, navigate facilities and structures, see the
required works, quantities and materials, compare design and commercial
sources, and receive practical conclusions:

- project engineering overview and facility/structure inventory;
- work, quantity, and material schedules;
- omissions, quantity/material/revision discrepancies, and missing inputs;
- constructability, geometric, sequencing, cost, schedule, and contractor
  risks where the supplied data support those conclusions;
- applicable NTD issues and concrete customer clarification questions;
- contractor-protective disagreement protocol and revised contract candidate
  when a contract is present.

Every material conclusion retains a document/page source and calculation where
applicable, but the conclusion—not the locator—is the user result.

## Support

The same project/work model tells PTO and site staff what ID documents are
required for each performed work, what is ready, what is missing, and which
known data can safely populate AOSR, journals, registers and executive schemes.
It manages material quality records, laboratory/geodesy information,
attachments, package consistency, presented quantities, and KS/payment
preparation. The register is the first document of an ID package. Missing
dates, measurements, tests, geometry, signatures, or external certificates are
named precisely and never fabricated.

## Audit

For an admitted ID/document folder, the system determines the performed works,
the documents that should exist, what actually exists, and what is missing,
incomplete, in the wrong form/revision, duplicated, contradictory, or
quantity-inconsistent. It produces a concrete correction schedule and usable
audit report; source navigation supports each finding.

## Restoration

Restoration determines what can be reconstructed from available PD/RD,
journals, laboratory records, schemes and other known facts. It fills and
generates the recoverable documents, orders the work, and states exactly what
still requires human input. It never invents dates, signatures, measurements,
attendance, tests, or geometry. A dedicated workflow is currently not
implemented.

## User-interface and acceptance principles

- Project-first professional information is primary; processing and diagnostics
  are secondary.
- A user sees construction terms and actions, not UUID-heavy lifecycle or
  model-processing concepts.
- A capability is materially accepted only when its professional result is
  obtainable through the application on representative project data.
- A valid uncertainty is written in professional language and identifies its
  consequence and the needed clarification. Internal flags are not a user
  answer.

## Cross-mode invariants

- one ProjectDefinition and WorkRequirementMatrix identity per selected version;
- hard workspace isolation and default deny;
- bounded source and knowledge context before every substantial AI/VLM
  operation;
- direct model SQL prohibited;
- customer regulation is additive only;
- gaps remain gaps and block only claims requiring missing authority;
- any contradiction in extraction/knowledge/rules is a
  `KnowledgeConsistencyDefect`, not a silent authority choice;
- every material result can be traced to source/version and clearly separates
  fact, calculation, interpretation and unresolved input;
- all long work is a durable job with recovery and reconciliation;
- exports require explicit finalization and lifecycle receipts.

Current readiness for all four modes is below `MODE_READY`.
