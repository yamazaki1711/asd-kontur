# BLIND TENDER ANALYSIS SNAPSHOT v2 — 2026-10-04

## Snapshot authority

- Workspace: `01a0eba7-70ba-7770-9601-1a713dd359cf`
- Observation time: `2026-10-04T04:35:00+12:00`
- Application release: `c204c92230ebf3e952db94de482cf777e5b52a61`
- Engineering model: `project-engineering-model-v78`
- Engineering model fingerprint:
  `sha256:122cb2b48157d33a63e901ab2d32c9310041eff58200ead7fac0ee06e7fb301d`
- Canonical compact snapshot fingerprint:
  `sha256:1669d72cf4395b5684a6586618e2a2c7e0b7d5d8ebd0eff05cfda459ca61b4d3`
- Generated preliminary Tender DOCX: 44,802 bytes,
  `sha256:b0a1543e0932f7effc76a7eac7e2cee4967cc09b95cf83cbbf3787f8c41b286b`
- Blind discipline: no owner-known expected discrepancy was requested, read,
  prompted, encoded or used as a runtime rule before this snapshot.

This record freezes what ASD-KONTUR independently understood at the stated
time. It is not a claim that processing was terminal. Later autonomous results
must receive a new version and fingerprint rather than altering this record.

## Project and participants

ASD-KONTUR identifies the project as capital repair of the retaining walls at
63/1 and 65/1 Okeanskaya Street. It establishes three navigable project
entities:

1. retaining wall at 63/1 Okeanskaya Street;
2. retaining wall at 65/1 Okeanskaya Street;
3. the overall design area.

The current structured participant result identifies the municipal landscaping
service of Petropavlovsk-Kamchatsky as Customer and identifies
`ООО «АЛЬФА-СТРОЙ»` in developer, contractor and designer contexts. These role
assignments remain source-grounded project facts, but the repeated organization
identity across three professional roles should be confirmed before external
use.

## Document package

The package model contains project documentation, embedded work quantity
sheets, estimates, a contract, Customer requirements and procurement material.
No separate RD or specification document has been established. Their absence
limits only comparisons that require those source roles.

## Commercial and procurement facts

The independently extracted commercial result includes:

- NMCK / initial contract price: `41,573,447.08 RUB`;
- price method: base-index method, with both historic 2022 price-basis
  statements and current Q3 2026 price-basis statements retained rather than
  silently collapsed;
- VAT rate stated in the contract: `22%`;
- VAT amount in the NMCK justification: `7,496,851.11 RUB`;
- payment: no more than seven working days after the Customer signs the
  acceptance document;
- performance security: funds or an independent guarantee;
- participant requirements include construction experience and an SRO-related
  condition extracted from the procurement package.

The coexistence of 2022 and 2026 price-basis statements is retained as source
information. This snapshot does not yet promote it to a professional conflict
because the applicable estimate/revision relationship has not been established
for every statement.

## Time requirements

The model retains the following distinct statements:

- procurement/NMCK start: October 2026;
- contract start: from contract conclusion;
- contract completion: 31 July 2027;
- NMCK completion: July 2027;
- POS construction duration: 0.2 month preparatory period plus two months main
  period;
- project work duration: 2.2 months;
- procurement/correspondence work duration: four months.

ASD-KONTUR has established a `DURATION_MISMATCH` between the 2.2-month project
duration and the four-month procurement statement. It does not compare the
active work duration directly with the full calendar contract interval.

## Construction scope

The model contains 286 consolidated work scopes. Of 787 observations retained
as construction scope, 552 are classified (70.1%). It has assigned a facility
to 332 observations. It excludes 1,306 source rows as non-work and retains 235
unclassified descriptions instead of forcing a construction meaning.

The model reports no excavation pit for this project. The pit inventory is
marked final for the currently admitted corpus; this project is not being
forced into the OZERO pit ontology.

## Quantities and comparisons

The current model contains 386 reviewed quantity observations, 327 accepted
work quantities, six ambiguous quantities and eleven pending quantities. Ten
professional quantity/duration comparisons are visible:

1. crushed-stone base, VOR versus estimate: `65.4 m3` versus `65.4 m3` — match;
2. tree removal internal component/total check: `61 pcs` versus component sum
   `61 pcs` — match;
3. tree removal, VOR versus contract estimate: `61 pcs` versus `61 pcs` — match;
4. project versus procurement duration: `2.2 months` versus `4 months` —
   mismatch;
5. metal fencing at 63/1, PD versus VOR: `219 m` versus `219 m` — match;
6. reinforced-concrete retaining-wall demolition, VOR versus contract estimate:
   `119.83 m3` versus `119.83 m3` — match;
7. earth excavation, VOR versus estimate: `115.9 m3` versus `115.9 m3` — match;
8. topsoil removal, PD versus VOR: `370 m2` versus `370 m2` — match;
9. drainage collector, VOR versus estimate: `219 m` versus `219 m` — match;
10. earth excavation, PD versus contract estimate: `115.9 m3` versus
    `115.9 m3` — match.

The snapshot contains no defensible construction-quantity mismatch. The system
must not invent one to satisfy an acceptance target.

## Materials

Four current material comparisons are matches:

- metal fencing in PD versus VOR;
- metal fencing in PD versus contract estimate;
- cement-sand mortar in project material versus VOR context;
- cement-sand mortar in project material versus contract estimate context.

No material discrepancy is claimed at this boundary. Material comparisons
whose engineering subject or source role remains unresolved are not promoted.

## Professional findings

Two findings are currently established from structured facts:

1. `DURATION_MISMATCH` — project duration 2.2 months versus procurement work
   duration four months. Practical consequence: calendar and execution
   assumptions must be reconciled before tender submission.
2. `COMMERCIAL_SCOPE_WITHOUT_DESIGN_BASIS` — the commercial soil-loading item
   at the 63/1 retaining wall has not yet been connected to a project quantity.
   This remains a moderate-confidence scope question, not proof that the work
   is unnecessary.

## Customer questions and contractor risks

The model produces two source-linked customer questions:

1. confirm the mandatory execution period and reconcile the project and
   procurement calendar conditions;
2. identify the project basis for soil loading at the 63/1 retaining wall, or
   confirm its exclusion from commercial scope.

The corresponding contractor risks are schedule/price-basis uncertainty and an
unclear commercial position whose necessity, boundary and acceptance procedure
are not yet established.

## Contract analysis

The autonomous contract pipeline identifies `Проект_контракта.docx` and
`Описание объекта закупки.docx` as the governing sources. Its current effective
projection contains:

- 307 clauses;
- seven contractor-facing issues;
- five disagreement-protocol items;
- five proposed revised clauses.

The editable contract-analysis report, disagreement protocol and revised
contract candidate are separate qualified artifacts. Contract findings remain
professional candidates for human/legal review and do not claim unverified
statutory authority.

## Primary report

The current adaptive Russian Tender report generated as valid OOXML and
contains the project summary, commercial conditions, time requirements, main
quantities, customer questions and contractor risks. Its hash is recorded in
the snapshot authority section. Processing statistics are not part of its main
professional body.

## Unresolved limits

- 235 construction descriptions remain unclassified.
- A separate RD and specification have not been established in the corpus.
- Facility allocation remains incomplete for part of the commercial scope.
- The v36 exact-pair profile has passed live negative controls but had not yet
  produced a reciprocal live `SAME_SCOPE` result at snapshot time.
- No construction-quantity or material mismatch is independently established
  at this boundary.
- NTD applicability is not claimed for a work unless edition and project scope
  are both established.
- Autonomous processing is continuing; this file must not be edited to absorb
  later results.

Snapshot status:

`GeneralizedTenderHarness=false`

`AutonomousProjectProcessing=true`

`ProductReady=false`
