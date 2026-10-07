# Product Goal and Capability Map v1

- Product Goal: `PRODUCT-GOAL-ASD-KONTUR@1.0.0`
- Owner source: [GitHub issue #19](https://github.com/yamazaki1711/asd-kontur/issues/19)
- Machine denominator: [Contract Pack v2.0](../../contracts/v2.0/README.md)
- Current readiness ledger: [Contract Pack v2.7](../../contracts/v2.7/README.md)
- Historical rebaseline: [Product Goal Rebaseline](PRODUCT_GOAL_REBASELINE_DECISION_v1.json)
- Current decision: [Product Current State v1.2](PRODUCT_CURRENT_STATE_DECISION_v1.2.json)

## Goal

ASD-KONTUR is an object-independent, local-first applied construction-
engineering system for thousands of documents. It understands what is being
built, connects facilities and structures to works, quantities and materials,
compares project and commercial sources, applies available requirements, and
produces practical professional conclusions and documents. Its common
professional chain is:

`PD/RD + contract + VOR/estimate + customer regulation + NTD`
`→ project composition → facilities/structures → works/quantities/materials`
`→ comparisons/requirements → issues/risks/actions → professional outputs`.

The three permanent results are:

1. a contractor-protective protocol of disagreements and revised construction
   contract;
2. PD/RD analysis for omitted work/material, constructability/geometric
   collisions, errors, cost and time risk;
3. executive schemes from verified design and as-built geometry only.

Tender, Support, Audit and Restoration are required. They share one domain and
knowledge kernel; a backend slice or UI screen is not a ready mode.

## Product interpretation and acceptance

The primary unit of progress is a solved professional user task, not a
processed document, extracted candidate, receipt, test, migration, capability
counter, or readiness state. Internal provenance, immutable history, workspace
isolation, authorization, model receipts, and source locators remain mandatory
supporting infrastructure for correctness and safety.

The primary application hierarchy is:

`PROJECT → LOCATION/SECTION → ENGINEERING ENTITY → OPERATION/WORK → ATTRIBUTE/QUANTITY/MATERIAL`
`→ REQUIREMENT → ISSUE/RISK → ACTION → DOCUMENT`.

The location and entity levels are extensible and optional where a source-supported
fact has no such association. Pipes, walls, buildings, road sections and pits are
possible entity types, not mandatory ancestors. A project without excavation pits
must not display a universal pit category or require a pit before publishing a
source-supported pipe dimension.

Processing and diagnostic state is secondary. UUIDs, candidate lifecycles,
reconciliation terminology, and model-operation details are not the normal
professional workflow.

A capability is materially useful only when a user can obtain its professional
result through the application on representative project data. Tests, CI,
traceability, and safety checks remain mandatory acceptance evidence, but they
cannot substitute for the result. Source links support an engineering
conclusion; they are not the conclusion itself.

For Tender this means an understandable project, facility and work schedules,
quantity/material comparisons, engineering and NTD issues, contractor risks,
questions, and—when contract inputs exist—contract revisions. For Support it
means knowing what ID is required, ready, missing, and safely generatable. For
Audit it means a concrete list of missing, incomplete, conflicting, or invalid
documents and corrections. For Restoration it means safely generated
recoverable documents plus an exact list of facts that still require people.

## Complete denominator

The immutable v2.0 registry contains **142 mandatory capabilities across 13
planes**. Contract Pack v2.3 additively registers the newly accepted mandatory
`FIELD-ANDROID-CLIENT-01` capability, so the current composed denominator is
**143**. Historical registries and their denominators are not rewritten.

| Plane | Count | Stable capability namespace | Current distribution |
|---|---:|---|---|
| Product Interaction | 13 | `interaction.*` | 12 NOT_IMPLEMENTED, 1 CONTRACT_ONLY |
| Application | 10 | `application.*` | 4 NOT_IMPLEMENTED, 3 CONTRACT_ONLY, 3 FOUNDATION_ONLY |
| Industrial Intake | 17 | `intake.*` | 3 NOT_IMPLEMENTED, 6 CONTRACT_ONLY, 8 FOUNDATION_ONLY |
| Project Understanding | 12 | `project-understanding.*` | 9 CONTRACT_ONLY, 3 FOUNDATION_ONLY |
| Knowledge and Rules | 11 | `knowledge.*` | 2 NOT_IMPLEMENTED, 2 CONTRACT_ONLY, 6 FOUNDATION_ONLY, 1 PARTIAL |
| Engineering Intelligence | 9 | `engineering.*` | 6 CONTRACT_ONLY, 3 FOUNDATION_ONLY |
| Tender | 8 | `tender.*` | 3 CONTRACT_ONLY, 5 FOUNDATION_ONLY |
| Support | 12 | `support.*` | 6 CONTRACT_ONLY, 6 FOUNDATION_ONLY |
| Audit | 8 | `audit.*` | 4 CONTRACT_ONLY, 4 FOUNDATION_ONLY |
| Restoration | 7 | `restoration.*` | 2 CONTRACT_ONLY, 5 FOUNDATION_ONLY |
| Document/CAD Output | 11 | `output.*` | 9 CONTRACT_ONLY, 2 FOUNDATION_ONLY |
| Field/Offline | 10 | `field.*` | 10 CONTRACT_ONLY |
| Operations | 14 | `operations.*` | 9 CONTRACT_ONLY, 5 FOUNDATION_ONLY |
| **Rebaseline total (v2.0)** | **142** | — | **21 NOT_IMPLEMENTED, 70 CONTRACT_ONLY, 50 FOUNDATION_ONLY, 1 PARTIAL** |

The per-plane table above preserves the v2.0 rebaseline. The effective
post-Spine distribution is the additive v2.1 delta reconciled by v2.2; no stable
capability identity was added, removed or renamed.

| Effective readiness after Product Application Spine | Count |
|---|---:|
| `CAPABILITY_READY` | 16 |
| `PARTIAL` | 10 |
| `FOUNDATION_ONLY` | 45 |
| `CONTRACT_ONLY` | 64 |
| `NOT_IMPLEMENTED` | 7 |
| **Denominator** | **142** |

Contract Pack v2.3 adds `field.secure-android-client` to the Field/Offline
plane with `NOT_IMPLEMENTED` readiness and links it to Support, Audit and
Restoration. The current composed distribution is therefore:

| Effective readiness after FIELD-ANDROID-CLIENT-01 registration | Count |
|---|---:|
| `CAPABILITY_READY` | 16 |
| `PARTIAL` | 10 |
| `FOUNDATION_ONLY` | 45 |
| `CONTRACT_ONLY` | 64 |
| `NOT_IMPLEMENTED` | 8 |
| **Composed denominator** | **143** |

Its absence blocks the corresponding field acceptance and `ProductReady`.
Issue and security/offline boundaries are recorded in
[FIELD-ANDROID-CLIENT-01](../implementation/FIELD_ANDROID_CLIENT_01.md).

Contract Pack v2.4 additively records the evidence-backed Support production-ID
and public development-contour delta. Eighteen capabilities move to `PARTIAL`;
none becomes `CAPABILITY_READY`, and no mode or product readiness is promoted.
The composed distribution is 16 `CAPABILITY_READY`, 28 `PARTIAL`, 40
`FOUNDATION_ONLY`, 52 `CONTRACT_ONLY`, and 7 `NOT_IMPLEMENTED` across the same
143-capability denominator.

The complete stable-ID list and per-capability product result, modes, lifecycle,
inputs, outputs, dependencies, canonical/workspace data, surface, evidence,
readiness, gaps, acceptance, scale and next slice are in:

- [required-capabilities.json](../../contracts/v2.0/required-capabilities.json);
- [product-capability-registry.json](../../contracts/v2.0/fixtures/valid/product-capability-registry.json);
- [v2.3 capability extension](../../contracts/v2.3/fixtures/valid/capability-registry-extension.json);
- [v2.4 readiness delta](../../contracts/v2.4/fixtures/valid/capability-readiness-delta.json).
- [v2.5 intake and project-understanding delta](../../contracts/v2.5/fixtures/valid/industrial-intake-project-understanding-delta.json);
- [v2.6 pilot acceptance contract](../../contracts/v2.6/fixtures/valid/pilot-usable-e2e-delta.json).
- [v2.7 professional assistant contract](../../contracts/v2.7/fixtures/valid/professional-assistant-delta.json).

These files are normative and machine-validated; this page is their navigation
view, not a second registry.

## Readiness ladder

| Level | Meaning |
|---|---|
| `NOT_IMPLEMENTED` | No accepted contract or implementation. |
| `CONTRACT_ONLY` | Boundary/schema exists; behavior is not implemented. |
| `FOUNDATION_ONLY` | Services/schema/tests exist without a user/operations process. |
| `PARTIAL` | Some behavior/evidence exists, but terminal criteria are unmet. |
| `CAPABILITY_READY` | Production-shaped interface, real declared formats, professional result and capability E2E pass. |
| `MODE_READY` | One mode passes its complete admission-to-output/export/recovery user workflow. |
| `TRIAL_READY` | Application Spine, UI/API/intake/jobs/viewer, applicable NTD/rules/outputs, operations and scale qualification all pass under an explicit decision. |
| `PRODUCT_READY` | Four MODE_READY decisions, three product results and system-wide operational acceptance all pass. |

Tests are evidence inside a denominator; their count is never a readiness KPI.
No real OKS is proposed before an exact `TrialReadinessDecision`.

## Current truth

- `PlatformKernelReady=PARTIAL`;
- `ProductApplicationReady=PARTIAL`;
- `TrialReady=false`;
- `OKSReady=false`;
- `ProductReady=false`.

SYSTEM-INTEGRITY-CYCLE-01 proves bounded kernel reproducibility only. Its old
semantic claim was superseded by the memory DATA_DEFECT. MEMORY-INTEGRITY-FIX-01
closed that bounded defect through immutable requalification and three fresh
clean-room cycles; this does not promote any product capability or mode.
Rule Registry has infrastructure but zero operational rules.

## Delivery order

The owner-supplied full functional completion directive of 7 October 2026
supersedes the previous Tender-only stopping priority. Work proceeds by
dependency: finish the source-grounded editable contract journey, integrate
the remaining Tender result, then Support, Audit, Restoration, verified
drawings, field/offline and complete lifecycle/scale qualification. Existing
working components and autonomous processing must be preserved. No source
checkpoint or single-mode pass establishes `ProductReady`.

The 143 stable capability identities in the composed registry remain the
machine denominator. The following source-mapped acceptance overlay identifies
the full-product journeys added or sharpened by the 7 October directive. Each
row is `NOT VERIFIED` for whole-journey acceptance unless a tested and
delivered release is named in later evidence. A missing-input/blocked-case
pass does not substitute for a sufficient-input success path.

| Requirement ID | Directive source | User input/action and required professional output | Qwen / deterministic boundary | UI, API and export acceptance | Current whole-journey state |
| --- | --- | --- | --- | --- | --- |
| FFC-01 | Required contract capability | Upload contract alone or with attachments; receive sourced contractor assessment, editable protocol and complete coherent revised contract | Qwen clauses, risks and drafting; code verifies source identity, dates, selection and OOXML assembly | Contract view and DOCX outputs reopen; missing references and conflicting terms reported | PARTIAL: durable human amendment review and editable drafts exist; no owner decision or accepted cross-clause/legal coherence |
| FFC-02 | Required Tender mode | Upload PD/RD, commercial and optional company/logistics inputs; receive scoped quantities, omissions, costs, conditions and reasoned participation decision | Qwen semantic scope; code computes quantities, costs and decision gates | Tender view and editable report on distinct projects | PARTIAL: source-scoped comparisons, a bounded editable report and optional contractor-entered cost build-up exist; real company fit, viable cost and participation decision are not accepted without owner inputs and full Tender qualification |
| FFC-03 | Required Construction Support mode | Confirm real work, materials and inspections; receive required ID, registers, as-built and KS packages with exact blockers | Qwen applicable requirements; code enforces prerequisites and factual authority | Support workflow, reopenable documents and exports | NOT VERIFIED |
| FFC-04 | Required Audit mode | Upload existing ID; receive document inventory, findings, corrective actions and declared unexamined scope | Qwen semantic contradiction review; code checks identity, chronology and completeness | Audit view and editable register/report | NOT VERIFIED |
| FFC-05 | Required Restoration mode | Supply audited ID and confirmed facts; receive prioritized plan, grounded drafts, pre-inspection and final/partial package | Qwen grounded drafting and independent review; code prohibits invented field facts | Restoration workflow and editable package | NOT VERIFIED |
| FFC-06 | Shared documentation and engineering capabilities | Supply confirmed design/as-built geometry; receive usable drawing, or precise missing-measurement request | Qwen interprets source geometry; code validates confirmed values and assembles drawing | Reopen and inspect drawing file and source linkage | NOT VERIFIED |
| FFC-07 | Application and field use | Record planned-work confirmation, quantities and evidence offline; reconnect and resolve conflicts; confirm voice transcript | Qwen only for approved speech/semantic tasks; code owns local queue and conflict safety | Supported field client offline/reconnect and voice-confirmation test | NOT VERIFIED |
| FFC-08 | Shared project lifecycle | Create A, process/export, delete A, then process B without leakage while NTD remains unchanged | Code owns isolation, fence, cleanup and residue checks | Actual application lifecycle and isolated destructive qualification | NOT VERIFIED |
| FFC-09 | Durable autonomy and bounded execution | Admit project and leave Codex disconnected; receive useful outputs and explicit terminal/partial state after restarts | Qwen performs bounded semantic work; supervised runtime owns durable successors/retries | Same release survives worker/API/Qwen restart without manual queue commands | PARTIAL: earlier autonomous Tender progression; full four-mode path unverified |
| FFC-10 | Knowledge and regulatory applicability | Ask for applicable requirements on real scoped works; receive edition-qualified source-linked conclusions | Qwen reasons over Knowledge Gateway context; code checks source/version/applicability | Mode outputs cite exact normative locators without altering global memory | NOT VERIFIED |
| FFC-11 | Delivery and acceptance | Run qualified diverse-corpus, false-negative/positive and representative thousands-of-documents acceptance | Qwen production tasks only; code measures work, replay, failure and time-to-value | Same tested/deployed release exposes all results and files | NOT VERIFIED |
| FFC-12 | Application and field use | Use role-appropriate access and protected device/session data | Code enforces authentication, authorization, attempt limits and local-data controls | API/UI/field security and offline-lock boundary acceptance | NOT VERIFIED |

Current FFC-01 delivery checkpoint: application SHA
`fea2395429b31c3e87c096af970976020d79668c`, migration
`0134_contract_coherence_profile_v2`. The release preserves unchanged readable PDF
contract appendices in the revised-source package, explicitly marks them
non-editable, and rejects attempts to apply DOCX clause revisions to a PDF.
It also includes a source-linked CSV of unresolved referenced documents in
the editable revised-contract ZIP, without asserting that those documents
are absent from the owner's possession.
After completed reference review, an owner can also download that CSV directly
from the contract screen without selecting a clause revision. Incomplete
review returns an explicit blocker rather than a misleading empty register.
The previous public worker repeatedly scanned an idle workspace despite zero
claimable jobs; the supervised orchestrator now owns that safety-net sweep,
and the released worker idles between claims. A changed-party contract-only corpus
passed the isolated live-Qwen result path, and the owner's already-admitted
contract reached 5/5 accepted bounded cross-clause contexts autonomously.
The reviewed editable package and protocol consistency checks are delivered,
but these results do not certify unreviewed clauses, legal authority, owner
negotiation choices or authenticated browser acceptance. FFC-01 stays
`PARTIAL`; the other FFC rows and `ProductReady=false` are unchanged. The
exact lifecycle cleanup of an accidental control workspace was separately
verified without altering the owner workspace or permanent NTD memory.

FFC-01 follow-up: application release
`56300deabcdc9aaa6d1271d9433b5d5c8e945cbe` keeps accepted bounded
contract reviews reusable while scheduling additional local-Qwen reviews for
explicit clause cross-references that previously exceeded the 12-clause
context. Unreviewed explicit links and revisions beyond the bounded cap are
visible as coverage gaps on the contract screen. This advances review
coverage, but it does not certify the entire revised contract, authorize
negotiated wording, or pass an authenticated owner-browser deliverable check.
The FFC-01 whole-journey state remains `PARTIAL`.

FFC-01 remains `PARTIAL` after the 7 October contract output checkpoint. The
delivered application release is
`1be4a7f0d5aad9368c904e17034acfa3f0ce6d31` on migration
`0132_tender_participation_assessments`. A changed-party contract-only corpus
passed the isolated upload-to-editable-output path with live local Qwen and a
benign-clause false-positive control (one scenario, 86.55 seconds). A read-only
render of the owner workspace's persisted Qwen result produced a two-page
editable disagreement protocol whose clause numbers are shown only when
present in exact source wording. The in-app browser connection was unavailable
for authenticated download and visual UI acceptance. Legal/cross-clause
coherence, attachment authority, user selection of revisions, and full
contract-only supervisor-disconnected acceptance remain unverified; no
contract journey PASS or `ProductReady` change follows from these checks.
An additional changed-party contract-only run verified an unprovided referenced
appendix as `unresolved` with an exact source quote and an explicit contract
gap (one scenario, 103.60 seconds, four local-Qwen requests). This closes only
the missing-attachment subcase; it does not promote FFC-01 to PASS.

Release `25b8a6d0b68f7ef16b79582caa932917a60137bc` on migration
`0133_contract_coherence_review` adds an autonomous, source-linked Qwen review
of selected related clauses for each proposed revision. The changed-party
contract-only scenario passed with live Qwen in 121.98 seconds, and the
owner's already-admitted contract advanced without Codex scheduling: five
review jobs succeeded and the application read model reports bounded review
complete. Zero candidate conflicts means only that none was established in
those selected contexts. A complete legal coherence review, authenticated
browser acceptance and the remaining contract obligations are still open;
FFC-01 remains `PARTIAL` and `ProductReady=false`.

Release `3fa4596a4505c080a82bbd9d4fd74d90ab1a5a77` adds a fail-closed
editable-contract output boundary: source DOCX packages must have a valid
Office main-document relationship and content type, and an unresolved
placeholder cannot become a proposed or exported clause. A bounded local-Qwen
repair may replace a placeholder with source-safe non-numeric wording; otherwise
the risk remains without a false completed revision. One isolated changed-party
contract-only run passed the full intake-to-output route in 185.32 seconds;
both resulting one-page DOCX artifacts opened and every page was visually
inspected after PDF rendering. This does not establish contract-wide legal
coherence, negotiated term authority, authenticated owner-browser acceptance,
or FFC-01 PASS.

The FFC-02 partial delivery is pinned to application release
`81af71af3d12a988dbd2100d664233272bc20f09` on migration
`0131_contract_revision_review`. A read-only render of the current real
workspace's unchanged model reduced the main editable report from 1,570 to
314 table rows; all 845 material-observation rows remain available in the
separate source-linked CSV included in the Tender archive. Exact repeated
quantity displays are collapsed only in the overview, never summed, and
unreviewed quantity values are excluded from its principal quantity table.
The DOCX reopened and converted to a 36-page PDF; three sampled pages were
visually inspected. This is not all-page or browser acceptance, a new
engineering conclusion, a participation decision, or a mode PASS.

The 7 October Tender continuation reached release
`85628fda3a1cbb69bde78bcee3b164cefb767b12` without a schema change.
The earlier `199a6b1` checkpoint added an optional contractor-supplied cost
build-up; the live owner's decision remains insufficient-input because no
company/cost assessment was supplied. The later checkpoint corrected a generic
material-scope false-positive path: multiple distinct item-property values on
one side are now an unresolved item-mapping question, not automatically a
single material mismatch. In the owner's read-only projection, one of seven
material comparisons moved to that ambiguity state while one independently
single-valued material mismatch remains. The owner workspace was not reset or
manually reprocessed; Qwen and NTD processes were not restarted. These are
professional-quality improvements, not FFC-02 acceptance.

For each row, the detailed acceptance record must additionally name the
tested release, delivered release, actual observed result and remaining
blocker. Until that evidence exists, implementation or a passing unit test is
not a journey PASS. The historical v16.1 enumeration of 19 audit checks,
nine Support blocking rules and 12 laboratory steps is not asserted from an
unverified count; recover the source definitions or mark the specific
specification gap without weakening known requirements.
