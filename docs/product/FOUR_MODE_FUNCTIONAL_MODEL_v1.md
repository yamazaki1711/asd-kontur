# Four-mode Functional Model v1

## Common spine

Every mode operates inside one workspace and uses the same version-pinned:

`Source/Evidence Ledger → ProjectDefinition → ConstructionWorkPackage`
`→ WorkRequirementMatrix → Context Assembly → professional mode result`.

Platform Practice Intelligence explains professional practice. Verified NTD
provides normative authority. Qualified RuleVersion provides deterministic
behavior. Workspace facts provide OKS-specific evidence. No layer substitutes
for another and no model confirms facts or applicability.

## Tender

Inputs: tender PD/RD, VOR/estimate, draft contract, appendices, customer
regulation and exact available NTD. The user journey admits and inventories the
package, resolves ProjectDefinition/work/quantity/material structure, compares
project against commercial documents, analyzes contract contradictions and
constructability, then produces:

- package completeness and evidence gaps;
- omitted work/material and quantity deltas;
- obsolete/unresolved NTD references;
- evidence-bound time/cost feasibility and risk conclusion;
- contractor-protective protocol of disagreements;
- revised contract candidate for professional approval/export.

No conclusion is allowed without calculation and locators.

## Support

The same work matrix drives planning, MTR batches and incoming control, hold
points, field evidence, laboratory/geodesy, ID dependencies, AOSR, journals,
executive schemes, presented quantities and KS/payment readiness. The earlier
[Support model v0.1](../mvp/FUNCTIONAL_MODEL_v0.1.md), including its 14 screen
contours and offline requirements, remains a design input—not the whole product
and not evidence that Support is implemented.

## Audit

Expected requirements from the shared matrix are compared with admitted actual
documents. Outcomes distinguish present, missing, incomplete, invalid, wrong
edition/form, unsupported, duplicate, contradictory and evidence gap. The
operator can navigate every finding to source and export a reproducible audit
report.

## Restoration

Restoration starts from gaps in the same matrix and preserved facts. It
classifies recoverable and non-recoverable documents, evidence sufficiency,
restoration order and blockers. Generated documents remain candidates; the
system never invents dates, signatures, measurements, attendance, tests or
geometry. A dedicated workflow is currently not implemented.

## Cross-mode invariants

- one ProjectDefinition and WorkRequirementMatrix identity per selected version;
- hard workspace isolation and default deny;
- base EvidencePack before every substantial AI/VLM operation;
- direct model SQL prohibited;
- customer regulation is additive only;
- gaps remain gaps and block only claims requiring missing authority;
- any contradiction in extraction/knowledge/rules is a
  `KnowledgeConsistencyDefect`, not a silent authority choice;
- every result includes source, locator, authority, uncertainty, blocker and
  version identity;
- all long work is a durable job with recovery and reconciliation;
- exports require explicit finalization and lifecycle receipts.

Current readiness for all four modes is below `MODE_READY`.
