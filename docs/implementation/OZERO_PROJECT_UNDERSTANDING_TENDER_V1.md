# OZERO Project Understanding and Tender Engineering Analysis v1

## Product result

This delivery turns the persisted project-understanding records into a construction-facing read
model used by the Tender UI, editable exports, and assistant context. The main application result
is now the project, facilities, pits, works, quantities, materials, comparisons, engineering
issues, contractor risks, and customer actions. Processing diagnostics remain available in a
secondary disclosure.

The implementation is object-independent. OZERO supplies the real validation data but no OZERO
workspace ID, facility name, expected pit count, or expected conclusion is encoded in the model.

## Model contract

- Contract version: `project-engineering-model-v1`.
- Inputs: current project definition, active-source engineering observations, structure identity
  components, pit dispositions, requirement matrix, professional reconciliation defects, and
  scoped source labels.
- Stable identity: facility and work-scope IDs include the workspace and their deterministic
  construction identity inputs.
- Recalculation: the fingerprint changes when an input observation, association, source version,
  role, quantity, material, requirement, or model contract changes. No document extraction is
  repeated to rebuild this read model.
- Authority: supported project results are immediately usable; ambiguity is expressed in ordinary
  construction language. This does not promote model extraction into a signed field fact or a
  professionally approved normative rule.
- Sources: document/version/page links remain available from each result but are supporting
  information, not the main product hierarchy.

## Automatic reconciliation policy

1. LOS/KNS facilities require a repeated explicit design mark, not a product/capacity string.
2. Work-to-facility association uses an explicit facility mark, an exact shared source locator, or
   a single unambiguous facility on the same source page. The association basis is shown.
3. Work mentions are deduplicated within the same source locator and grouped by facility, work
   family, and operation. Installation and removal remain separate operations.
4. Quantities are compared only when both roles have one unambiguous value in compatible normalized
   units. Conflicting values remain unresolved and are never averaged.
5. Technical extraction-link failures do not appear as construction defects. A professional issue
   is created only from a demonstrated comparison or a practical commercial-scope limitation.

## Current OZERO result before public activation

The read-only application-path check against the authorized OZERO scope established:

- project: `Система ливневой канализации бассейна оз. Култучное Петропавловск-Камчатского
  городского округа`;
- 12 repeated explicit facility designations in the current model;
- 4 individually established facility-linked pits and 6 unresolved designation groups, so a final
  project-wide pit total is not yet justified;
- a KNS-4 sheet-pile enclosure in structural calculations;
- sheet-pile installation, extraction, profile/material, and waling-beam observations in design
  and estimate sources, with facility allocation incomplete;
- six reproducible PD-to-estimate comparisons whose currently comparable values agree;
- one Tender issue: commercial sheet-pile quantities are not allocated to facilities, preventing a
  reproducible facility price/completeness check;
- one corresponding customer clarification and contractor-risk entry.

The current result is useful but partial. It does not claim that four is the final pit count, that
all 5,232 unmatched work descriptions have been classified, that sheet-pile quantities are fully
assigned by facility, or that applicable NTD rules have been established for OZERO.

## User-visible outputs

- project-first Tender model screen with facility and pit navigation;
- work/quantity/material schedule with an explicit unclassified section;
- role-aware quantity comparison view;
- professional issues, risks, and customer actions;
- editable Tender engineering report (`DOCX`);
- editable work/resource and findings schedules (`CSV`);
- register-style Tender analysis archive with the engineering report first;
- assistant context and pit-inventory tool driven by this same read model.

`ProductReady=false`: this delivery does not complete the remaining OZERO identity/quantity work,
contract analysis, geometry checks, Support authority, Audit, Restoration, or the product-wide
acceptance gates.
