# ASD-KONTUR Product Reality Gap — OZERO

**Observation time:** 2026-09-25 11:45–12:05 UTC+12  
**Public application:** `https://app.asd-kontur.ru/`  
**Workspace:** `ОЗЕРО`, `01a088aa-0491-7bdd-9127-8359fe927a27`  
**Candidate feature HEAD inspected:** `fc951f42607550ad00c2acd2a15e0a38d4ac108d`  
**Audit kind:** user-visible product-gap audit; no deployment, migration, retry, data mutation, or product implementation was performed.

## Verdict

**The owner's finding is substantiated.** ASD-KONTUR currently gives an OZERO user a durable document registry, processing coverage, source locators, large candidate tables, a limited candidate inventory, downloadable candidate schedules, and an assistant that can answer some narrowly bounded questions. It does **not** yet give the user a coherent construction model or a professional Tender result.

The first end-to-end chain breaks after extraction and before engineering reconciliation:

`source observations → reconciled facility/structure identity → canonical work type → scope-correct work package → consolidated quantities/materials → applicable requirements → professional Tender finding`

The deployed system completed the first term and parts of the second. It did not complete the remaining transformations. The evidence is not merely an empty UI: 133,407/133,407 semantic fragments are recorded as covered, yet all 6,396 work observations remain canonically unmapped, 5,310/5,564 work packages have no demonstrated facility association, the requirement matrix has no OZERO normative editions or rules, and all 1,662 displayed “defects” are extraction/reconciliation ambiguities rather than design, quantity, scope, constructability, cost, or contract findings.

**Proposed single critical-path milestone (renamed by the 2026-09-25 owner product correction):** **OZERO PROJECT UNDERSTANDING AND TENDER ENGINEERING ANALYSIS v1**. It must turn the already processed documentation into an understandable construction project, real cross-document comparisons, practical engineering findings, contractor risks and customer actions. Internal traceability supports those results and is not the milestone name or user deliverable. It is defined precisely in section 12.

### Evidence notation

- **[V] Verified current fact:** observed from the unchanged public release, its served frontend, the deployed application repository projection, or scoped persisted OZERO records.
- **[I] Inference:** conclusion derived from verified facts; the derivation is stated.
- **[U] Unavailable evidence:** could not be verified in this audit.

### Important inspection limitation

**[U]** The in-app browser service reported that no browser or extension session was available (`browsers = []`). Therefore an authenticated visual click-through and screenshots could not be performed without fabricating a session or using a prohibited substitute browser. The audit instead used the unchanged public health/OpenAPI endpoints, exact served frontend build/source, the deployed application repository with the authorized OZERO owner/workspace scope, and read-only database inspection. Click-only visual behavior is marked **not visually verified**; no UI result is claimed solely from feature-branch code.

## 1. ORIGINAL PRODUCT EXPECTATION

**[V]** The authoritative denominator is the product contract, not the most recent implementation receipt:

- an object-independent system with Tender, Support, Audit, and Restoration;
- the shared professional chain from PD/RD, contract, VOR/estimate, customer regulations, NTD, and confirmed facts through OKS structure, works/resources, control/evidence, ID documents, presented quantities, and payment;
- three enduring professional results: contractor-protective contract review, PD/RD omissions/collisions/risks, and executive drawings based on confirmed design and actual geometry;
- complete executive-document packages, register first, with acts, journals, schemes, attachments, and missing-fact handling;
- evidence, provenance, workspace isolation, recovery, and authority boundaries as product qualities, not substitutes for professional outputs.

**[V]** The base Contract Pack registry contains 142 capabilities; the additive field-client decision makes the composed denominator 143. Current product documents record `TrialReady=false`, `OKSReady=false`, and `ProductReady=false`. No current accepted four-mode terminal decision was found.

**[V]** For OZERO specifically, the preserved mission contract requires a reconciled inventory of local areas, LOS, KNS, pits and structures; scope-correct works, quantities and materials; Tender findings; evidence navigation; and grounded consultation. It explicitly says that OCR, isolated candidates, and a document chatbot are insufficient.

## 2. WHAT THE USER ACTUALLY SEES

### Deployed topology and version boundary

| Component | Verified deployed state | User consequence |
|---|---|---|
| Frontend/API | **[V]** commit `006d3be49d97544a4dfd9c9ef15043b9c0fb1088`; frontend digest `sha256:c75d42c2e96c2dd6e06aefe35937b8cc94c78b82b468cf6d83127e7dca5f2a91`; served asset `index-BhZW4lyZ.js` | The real application is materially behind candidate `fc951f4`; feature-branch Support qualifications are not public behavior. |
| Document worker | **[V]** commit `e78773c2a6e1d5529ba8b29eafa0f2a22bca972f` | This worker produced the current OZERO analysis lineage. |
| Assistant worker | **[V]** commit `006d3be49d97544a4dfd9c9ef15043b9c0fb1088` | Persisted OZERO turns use the current structured tools plus retrieval, with inconsistent outcomes described below. |
| NTD worker | **[V]** commit `7277c637011cf5426b9f81495bd0d20a7f245008`; supervised PID 98263 | Queue is exhausted, but OZERO does not consume its verified provisions because work identity/applicability is unresolved. |
| Database | **[V]** `asd_kontur_public_demo`, migration `0064_pit_observation_disposition_receipts` | Public data predates candidate migration 0065+ Support work. |
| Qwen runtime | **[V]** local `Qwen3.8-27B-MLX-8bit`, PID 741, loopback endpoint | Model infrastructure exists; this does not itself establish useful engineering reconciliation. |

**[V]** Public liveness and readiness endpoints return 200; PostgreSQL is reachable and at the expected migration. This establishes operational availability, not product usefulness.

### OZERO as exposed by the application projection

**[V]** The current materialization is `partial`, reconciliation version 1, recorded 2026-09-21 19:14:25 UTC+12:

| Observable item | Current value | Practical meaning |
|---|---:|---|
| Active source versions | 22 | Complete imported package denominator. |
| Pages | 2,529 | Page inventory denominator. |
| Semantic coverage | 133,407 / 133,407 expected fragments | The current v15 manifests report no unresolved fragments. This is extraction coverage, not engineering completeness. |
| Document extraction label | 13 `complete`; 9 `partial_with_capability_gap` | Historical OCR/capability limitations remain visible for nine sources despite recovered semantic fragment coverage. |
| Project-field candidates | 8,086 | Mostly unreviewed candidate observations; the verified-facts project definition still has no fields. |
| Structure nodes | 7,629, all `candidate` | No authoritative object hierarchy. |
| Cross-document identity candidates/components | 256 / 251, all candidate | Minimal consolidation: 256 candidate groups reduce to 251 components. |
| Work observations | 6,396, all `unresolved` | No candidate has a canonical work-type binding. |
| Work packages | 5,564 | Near observation-level packages, not a consolidated construction schedule. |
| Quantity candidates | 2,718 | Source-backed values exist but are not reliably consolidated by facility/work/revision. |
| Material candidates | 962 | Source-backed values exist but are not reliably consolidated by facility/work/revision. |
| Facility/work groups | 166 candidate groups | 127 packages share an exact locator with an identity, 39 use a unique label, 88 are ambiguous, and 5,310 remain unassociated. |
| Displayed defects | 1,662, all `ambiguous_source_match` and open | These are extraction-link problems such as unresolved work references or missing units—not Tender contradictions or professional risks. |
| Human review decisions | 1 | The application is not producing a usable result by requiring all candidates to be confirmed. |

**[V]** The project definition itself says `purpose=unresolved`, `object_class=unresolved`, has an empty verified `fields` map, and is incomplete. At the same time a candidate contains the plausible project name `Система ливневой канализации бассейна оз. Култучное Петропавловск-Камчатского городского округа`. The user therefore sees evidence that the system found the name but did not turn it into a coherent project definition.

**[V]** The current frontend provides tabs titled `Общие сведения`, `Структура объекта`, `Виды и объёмы работ`, `Материалы и изделия`, `Пакеты работ`, `Матрица требований`, and `Расхождения и пробелы`. The principal content is candidate counts, candidate review tables, raw work observations, incomplete matrix rows, and extraction defects. It does not present a navigable engineering hierarchy.

**[V]** Evidence routes exist and persisted candidate rows carry source-version and locator IDs. The served frontend provides `Открыть исходный фрагмент` links. **[U]** Actual click/open behavior in the owner's signed-in browser could not be visually rechecked in this audit.

### Four-mode reality

| Mode | Current OZERO records | User-visible reality |
|---|---:|---|
| Tender | **[V]** 0 Tender processes, scopes, issues, deliverables, protocols, or revised contracts. One historical `pilot_mode_result` says `draft_with_open_questions` and advertises export names, but no corresponding Tender artifacts are persisted. | Candidate schedules and a generic editable “Tender findings” export exist under Project Understanding; no professional Tender process result exists. |
| Support | **[V]** 0 OZERO Support scopes, processes, matrices, generation requests, documents, packages, grants, or final outcomes. | The controlled `concrete.slab.install` slice is synthetic qualification evidence on candidate code, not an OZERO or public Support result. |
| Audit | **[V]** 0 OZERO Audit processes, packages, deltas, findings, reports, or action requests. | Route/screen contracts exist, but OZERO has no audit result. |
| Restoration | **[V]** 0 OZERO restoration recovery plans. | Route/screen contract exists, but OZERO has no restoration result. |

## 3. OZERO QUESTION-BY-QUESTION ACCEPTANCE

These outcomes use the required status vocabulary. “Actual answer/UI state” refers to persisted assistant output and the deployed application projection; visual layout remains subject to the browser limitation above.

| # | Professional question | Status | Actual current answer/UI state |
|---:|---|---|---|
| 1 | What is this construction project? | **PARTIAL** | **[V]** Workspace name and candidate project name exist, but the assembled project definition has empty verified fields, unresolved purpose and unresolved object class. |
| 2 | What facilities / local areas / LOS / KNS exist? | **PARTIAL** | **[V]** Candidate identities include LOS/KNS labels, but also noisy/misclassified places and objects; 256 identity candidates remain unconfirmed and are not organized into a reliable facility inventory. |
| 3 | How many excavation pits are in the project? | **PARTIAL** | **[V]** Inventory exposes 10 candidate entries from 259 pit-like observations, with 245 unresolved observations and `exact_total_supported=false`. Earlier assistant answers alternated between no answer, a four-item subset, and a ten-item subset. No exact total is established. |
| 4 | What structures belong to each facility? | **FAIL** | **[V]** Candidate dossiers/relationships exist, but there is no reconciled containment hierarchy. Example classifications include `Скв.897` as an excavation-pit identity and project/system/place labels as structures or zones. |
| 5 | What work types exist? | **PARTIAL** | **[V]** The UI can list 6,396 raw work labels. Every one has `mapping_status` unresolved and no canonical work type. This is a mention inventory, not a usable work taxonomy. |
| 6 | Which works belong to which facility/pit/structure? | **PARTIAL** | **[V]** 166 candidate association groups are exposed. Only 127/5,564 packages share an exact locator with an identity, 39 use an explicit unique label, 88 are ambiguous, and 5,310 are unassociated. All remain candidates. |
| 7 | What quantities are specified for each work? | **PARTIAL** | **[V]** 2,718 quantity candidates include normalized values/units and evidence, but conflicts and unresolved work references prevent scope-correct totals. The UI explicitly avoids aggregation. |
| 8 | What materials are specified? | **PARTIAL** | **[V]** 962 material candidates are inspectable; they are not consolidated by canonical work/facility/revision and many lack quantities. |
| 9 | What evidence/source/page supports each result? | **PARTIAL** | **[V]** Candidate rows, assistant sources, and locator routes exist. There is no coherent final result whose complete evidence can be traversed; some assistant turns cite 2–9 sources, while failed/guarded turns cite none. |
| 10 | Which project documents contradict one another? | **FAIL** | **[V]** The 1,662 displayed defects are all extraction/reconciliation `ambiguous_source_match` records. No persisted cross-document contradiction finding was found. |
| 11 | Which quantities differ between PD/RD and VOR/estimate? | **FAIL** | **[V]** Intake recognizes 15 quantity/estimate sources and 22 design sources, but there are no comparison results or Tender issue records. `QUANTITY_OBSERVATIONS_CONFLICT` is a global gap, not a resolved comparison schedule. |
| 12 | Which works/materials appear omitted from commercial documents? | **FAIL** | **[V]** No explicit design-to-commercial scope comparison or omission finding is persisted. The application cannot safely call omissions while work identity and scope remain unresolved. |
| 13 | Which project data are missing or unresolved? | **PARTIAL** | **[V]** The UI accurately exposes processing/materialization gaps and unresolved candidate counts. It does not yet convert them into a prioritized professional missing-information schedule by facility/work/consequence. |
| 14 | Which applicable NTD requirements affect the identified works? | **FAIL** | **[V]** OZERO normative profile has zero edition IDs, zero rule IDs, no required PD/RD sets, missing applicability date, and `completeness_status=blocked`. Matrix rows only repeat generic blocker codes. |
| 15 | What constructability/geometric conflicts are identified? | **NOT AVAILABLE** | **[V]** No OZERO geometry inputs, geometry comparison results, or constructability findings were found. Extraction-link defects are not geometric conflicts. |
| 16 | What cost/time/Tender risks are identified? | **FAIL** | **[V]** No OZERO professional risk register exists. Candidate ambiguities do not state construction/cost/schedule consequence or required decision. |
| 17 | Can the system produce a useful Tender findings report? | **FAIL** | **[V]** CSV/DOCX/ZIP endpoints exist, but their current data are candidate observations and 1,662 ambiguous-source defects. They do not constitute a professional Tender findings report. |
| 18 | Can it produce a disagreement protocol? | **NOT AVAILABLE** | **[V]** No Tender protocol/process records exist. A historical pilot payload advertises an export name only; there is no persisted usable protocol and no contract source was detected. |
| 19 | Can it produce a revised contract candidate? | **NOT AVAILABLE** | **[V]** No revised-contract records exist, and the intake assessment found no draft contract. The absence should limit contract analysis without blocking PD analysis. |
| 20 | Can the assistant answer the above from structured OZERO evidence? | **PARTIAL** | **[V]** 19 persisted turns succeeded and 3 failed. Some later answers use structured inventory/work-package tools and sources; pit answers changed from “no data” to four candidates to ten candidates, and LOS8.1 answers still cannot produce an authoritative work schedule. No broad 20/30-case OZERO acceptance exists. |

**[I]** The system is more than a document browser, but less than an engineering analysis system. Its useful OZERO outcome today is “inspect source-backed candidates and limitations,” not “understand the project and prepare a bid.”

## 4. PROJECT UNDERSTANDING GAP

### Where the chain breaks

| Transformation | Verified current state | Missing transformation |
|---|---|---|
| Source bytes/pages → semantic observations | **[V]** 22 sources, 2,529 pages, 133,407/133,407 semantic fragments covered under v15 | Extraction coverage is established for the current manifests. Quality is not independently complete, but this is no longer the primary product blocker. |
| Observations → facility/local-area identity | **[V]** 7,629 candidate nodes; 256 identity candidates; 251 components; all candidate | Entity-type correction, alias/revision reconciliation, authoritative project composition, and stable facility IDs. Current groups are noisy and barely consolidate. |
| Facility → structure/pit hierarchy | **[V]** 2,325 candidate relationships and 251 candidate dossiers; no confirmed hierarchy | Typed containment/location/function relationships, conflict handling, and explicit unresolved alternatives. |
| Raw work label → canonical work type | **[V]** 6,396/6,396 unresolved; no catalog binding in any package | Reusable canonical work taxonomy mapping with evidence, scope, confidence, and unresolved queue. |
| Canonical work → scope-correct work package | **[V]** 5,564 packages, typically observation/page scoped; 5,310 unassociated | Cross-document consolidation by facility/structure/work/revision without merging same-name work in different scopes. |
| Work package → quantity/material schedule | **[V]** 2,718 quantity and 962 material candidates; 1,662 link/unit defects | Deterministic unit normalization, relationship resolution, duplicate/revision policy, and explicit conflicting values rather than silent aggregation. |
| Work → requirements | **[V]** every matrix row incomplete; no OZERO editions/rules | Applicability inputs, canonical work binding, Gateway retrieval, edition/applicability assessment, and persisted requirement evaluation. |
| Project model → Tender finding | **[V]** displayed defects are extraction ambiguities only | Comparison operators across design/specification/estimate/revision; professional consequence, confidence, question, and source set. |

**[I]** This proves the owner's hypothesis. Thousands of observations do not produce value because the system stores extraction candidates and then constructs near-observation-level “packages,” while the identity, taxonomy, scope, revision, consolidation, and comparison layers remain candidate-only or absent.

**[V]** The excavation-pit case is representative. There are 259 pit-like observations: 125 marked non-pit, 115 generic mentions, 14 distinct-instance candidates, and 5 ambiguous. The UI returns ten candidate labels, including plural work descriptions and a generic `котлован`, while the sole older identity candidate is mislabelled `Скв.897`. The inventory correctly refuses an exact total, but it has not reconciled facility pits, trench/work descriptions, well pits, and plural quantity rows into project entities.

## 5. TENDER GAP

**[V]** The package contains the inputs needed to begin real comparisons: design/working documentation (22 sources), quantity/estimate material (15), and specifications (2). A contract and customer regulation were not detected.

**[V]** No OZERO Tender process, scope, issue, evidence set, deliverable, disagreement item, protocol, revised clause, or revised contract exists in the mode tables.

**[V]** Current exports are useful only as engineering workbench artifacts:

- document coverage schedule;
- raw/candidate work-resource schedule;
- candidate facility/work associations;
- candidate identity groups;
- a “findings” export built from extraction ambiguity defects.

**[I]** They cannot currently answer the contractor's core bid questions: which scope is at each facility, which quantities disagree, what is absent from the estimate, what requires clarification, and what the practical consequence is.

**[V]** Missing contract documents legitimately block the disagreement protocol and revised contract for OZERO. They do **not** explain the absence of independent PD/estimate analysis.

## 6. SUPPORT GAP

**[V]** Controlled qualification proves that later candidate code can create a register-first package for `concrete.slab.install` with an editable AOSR draft and fail-closed missing items. That is category **C: synthetic qualification**, not public or OZERO usability.

**[V]** In the public OZERO database there are no work-type catalog versions or entries, and OZERO has no Support scope, process, requirement matrix, generation request, generated document, register, package, professional grant, or terminal outcome.

**[V]** No real OZERO package can be selected as an approved canonical work because all 6,396 observations are unmapped. Consequently no real approved WorkRequirementMatrix or required ID composition can be derived from OZERO evidence.

**[I]** The three Support authorization blockers remain valid fail-closed release issues, but they are downstream of this project-understanding gap and do not explain Tender failure.

## 7. AUDIT GAP

**[V]** Audit contracts, routes, and frontend screens exist. OZERO has zero audit processes, package denominators, classifications, deltas, causal paths, action requests, projections, or reports.

**[I]** Current status is **F: capability absent for the real workspace**, even though foundations and synthetic tests exist. A professional cannot submit or inspect an OZERO ID-package audit result today.

## 8. RESTORATION GAP

**[V]** Restoration contracts, route, and frontend screen exist. OZERO has zero recovery-plan versions and no restored document output.

**[I]** Current status is **F: capability absent for the real workspace**. There is no user-visible composition gap analysis or non-fabricating restoration plan for OZERO.

## 9. NTD / PROFESSIONAL KNOWLEDGE GAP

**[V]** The shared platform has real knowledge infrastructure:

- 15 normative editions;
- 1,669 provision candidates/semantics;
- 1,294 persisted verified provision versions;
- 2 active deterministic rule versions;
- 319/319 NTD processing jobs succeeded; no queued/running/failed eligible job remains under that queue.

**[V]** OZERO's normative profile nevertheless contains no normative edition IDs and no rule version IDs. It lacks an applicability date and a canonical work binding. Every requirement row is incomplete and lists generic missing-evidence codes.

**[I]** Therefore the completed NTD queue is category **A: infrastructure without an OZERO user result**. The missing product connection is:

`OZERO observation → canonical work/facility condition → applicable edition/provision → evaluated requirement → practical finding`

No new NTD extraction campaign is justified by this audit. The immediate gap is identity/applicability/evaluation integration, not GPU utilization.

## 10. UI / INFORMATION ARCHITECTURE GAP

**[V]** The UI has sensible top-level mode names and a Project Model screen with seven professional-sounding tabs. It also clearly labels candidates and incomplete processing, which prevents some false confidence.

**[V]** The primary content remains implementation-shaped:

- thousands of candidate rows and counts;
- “Qwen groups,” reconciliation progress, internal status/gap codes, and raw matrix JSON;
- one work package per source observation/page in many cases;
- manual candidate review controls without a resolved project hierarchy;
- evidence navigation by locator rather than by a stable facility/work dossier.

**[V]** The desired hierarchy is not present as the primary navigation:

`PROJECT → AREA/FACILITY → STRUCTURE/PIT → WORK → QUANTITY/MATERIAL/REQUIREMENT/EVIDENCE/ID/FINDINGS`

**[I]** This is not mainly a cosmetic redesign problem. The frontend cannot render the hierarchy until backend reconciliation produces stable identities and typed relationships. Redesigning cards before that would hide, not solve, the product gap.

## 11. INFRASTRUCTURE THAT IS ALREADY GOOD AND SHOULD NOT BE REWRITTEN

| Foundation | Evidence and preservation decision |
|---|---|
| Workspace isolation and scoped repositories | **[V]** OZERO data are visible under the exact owner/organization/workspace scope; the public API remains authenticated and unauthenticated `/session` is denied. Preserve RLS/default deny. |
| Source/version preservation | **[V]** 22 source versions, filenames, hashes, pages, and immutable history are retained. Do not reimport OZERO. |
| Durable jobs and lineage | **[V]** historical attempts, replacements, receipts, states, and failures remain available. Do not reset or replay the corpus. |
| Local Qwen processing boundary | **[V]** current semantic results identify the local Qwen profile and exact locators. Preserve deterministic/Qwen responsibility separation. |
| Evidence locators/viewer contracts | **[V]** candidate rows and assistant messages carry source IDs; frontend routes can open source fragments. Extend, do not replace. |
| Candidate-before-Fact authority | **[V]** current UI avoids silently promoting extracted observations. Preserve the authority boundary while reducing unnecessary manual review through deterministic reconciliation. |
| Processing/materialization honesty | **[V]** current UI distinguishes partial materialization and explicitly says pit candidates are not the project total. Preserve this behavior. |
| Persistent assistant history/tools | **[V]** turns, tool receipts, sources, model identity, and failures are persisted. Improve inputs and inventory tools; do not rebuild conversation storage. |
| Shared normative memory | **[V]** editions, verified provisions, rules, and processing receipts exist independently of workspaces. Connect them through the Gateway; do not copy NTD text into project-specific code. |

## 12. CRITICAL PATH TO FIRST GENUINELY USEFUL PRODUCT

### Single next milestone: OZERO PROJECT UNDERSTANDING AND TENDER ENGINEERING ANALYSIS v1

**Why this milestone:** **[I]** It is the smallest reusable increment that lets a construction professional understand the project, compare technical/commercial scope, identify practical problems, and decide what to clarify or protect in the bid. Support package expansion, additional synthetic work types, more NTD extraction, and unrelated UI polish remain downstream or orthogonal.

### Required reusable behavior

1. **Project composition.** Establish the project purpose and practical inventory of local areas, LOS/KNS/facilities, structures, pits and their relationships from project composition, plans, schedules and cross-references. Retain unresolved alternatives.
2. **Stable construction identities.** Produce stable identities for project, local area, LOS/KNS/facility, structure, pit and relevant component. Preserve aliases, revisions and conflicts internally without making candidate terminology the primary UI.
3. **Canonical work reconciliation.** Map raw work observations to a reusable canonical taxonomy where evidence supports it; retain unmatched labels explicitly. Never merge by name alone.
4. **Scope-aware packages.** Assign work to facility/structure/pit and revision; consolidate duplicate mentions while keeping same-name work in different scopes separate.
5. **Resource reconciliation.** Attach quantities/materials to the correct work and entity, normalize units deterministically, and expose stated, derived, conflicting, and missing values separately.
6. **Professional comparisons.** Compare design/specification/estimate/VOR observations by entity/work/resource and create findings with the actual values, practical consequence, and a clarification/action question.
7. **Project-first application.** Expose a navigable project/facility/structure/work dossier, differences, risks and actions before technical processing tables.
8. **Project consultant.** Answer inventory, facility, work and comparison questions from the shared project model and relevant source context; do not infer totals from keyword hits.

### OZERO acceptance for this milestone

The milestone passes only through the real OZERO application when an authenticated user can:

- open a project overview showing the supported formal project identity and an explicit unresolved remainder;
- navigate every established LOS/KNS/local-area candidate to structures and pits, with aliases and source pages;
- ask `Сколько всего котлованов в этом проекте?` and receive either the established total or a professional explanation of the confirmed inventory and exact ambiguous designations—without calling extracted rows a total;
- request `Покажи все шпунтовые работы и где они выполняются` and receive a scope-aware schedule by facility/structure with source links and a clear statement of any incomplete scope;
- select a facility and see its documents, structures, works, quantities, materials, findings, and missing information;
- compare PD/RD against available VOR/estimate data and obtain at least one real matched comparison plus explicit unmatched sets; no fabricated omission;
- open every cited evidence link and reload without losing the result;
- receive the same model through the assistant, with missing processing/retrieval clearly separated from missing source information.

**[U]** The exact OZERO pit total is intentionally not an acceptance fixture. The reconciled source evidence must determine it.

## 13. ORDERED IMPLEMENTATION BACKLOG

1. **Project Inventory/Reconciliation contract.** Define stable typed identities, aliases/revisions, containment/location/function relations, inventory coverage, and unresolved alternatives using current candidate/evidence stores.
2. **OZERO inventory reconciler.** Reconcile facility/local-area/LOS/KNS/structure/pit observations using deterministic evidence rules plus bounded local Qwen adjudication only for ambiguous semantic cases; preserve all provenance.
3. **Canonical work mapping and scope resolver.** Connect project work observations to the reusable catalog; create an explicit unmatched-work queue and stop generating authoritative-looking observation-per-package totals.
4. **Quantity/material consolidation.** Resolve relationships across batches/documents/revisions, normalize units, retain conflicts, and calculate only from recorded operands.
5. **Tender comparison engine.** Match design/specification/estimate/VOR sets; generate typed discrepancy, omission-candidate, missing-input, and ambiguity findings with practical consequence.
6. **Project-first API/UI projection.** Add project → facility → structure/pit → work/resource/requirement/evidence/findings navigation; keep raw candidates as a diagnostic secondary surface.
7. **Grounded assistant inventory tools.** Serve exhaustive structured inventories and comparison results with coverage; retain source retrieval for supporting detail.
8. **Knowledge Gateway applicability integration.** After canonical work/conditions exist, bind verified editions/provisions/rules and persist evaluated requirements; do not wait for unrelated corpus completion.
9. **Real OZERO Tender report.** Export the reconciled inventory, comparisons, risks, gaps, and clarification schedule; keep contract outputs blocked when the contract is absent.
10. **Then resume downstream modes.** Bind real project work packages into Support; separately deliver Audit and Restoration user workflows. Do not use synthetic qualification as the mode acceptance denominator.

## Product-contract comparison matrix

Category codes: **A** infrastructure without useful result; **B** data not reconciled; **C** synthetic-only; **D** works incompletely on OZERO; **E** end-to-end on OZERO; **F** absent.

| Expected professional result | Current user-visible result | State | Gap/root cause | Required capability | Product acceptance |
|---|---|---|---|---|---|
| Project identity and composition | Candidate name plus empty verified project definition | **B/D** | Candidate fields not reconciled into project authority | Project definition reconciliation | Supported identity/purpose/composition with conflicts and evidence |
| Facility/local-area inventory | 256 noisy candidate identities | **B/D** | Weak type/alias/revision reconciliation | Typed project inventory | Facility list independently reconciles with source composition |
| Structures/pits per facility | Ten pit candidate rows; exact total unsupported | **B/D** | No complete typed containment/identity graph | Entity relationship reconciliation | Navigable facility dossiers and bounded pit inventory |
| Work schedule | 6,396 raw labels; all unmapped | **B** | Canonical work taxonomy disconnected | Canonical work mapping | Scope-aware canonical works plus explicit unmatched set |
| Quantity/material schedule | 2,718/962 candidates | **B/D** | Relationship, scope, duplicate, and revision ambiguity | Resource consolidation | Correct units and totals by work/facility with conflicts retained |
| Applicable requirements | Generic blocked matrix | **A/B** | No work binding, applicability date, or edition/rule selection | Gateway applicability/evaluation | Exact provision and implication per evaluated work |
| Tender discrepancies/omissions | Extraction ambiguity cards | **A/B** | No cross-document comparison semantics | Tender comparison/findings | Actual matched differences and unmatched sets with evidence |
| Tender risk/questions report | Candidate export endpoints | **D** | No professional consequence or prioritized question model | Tender report composition | Editable, useful report verified against OZERO evidence |
| Disagreement protocol/revised contract | No artifact; contract absent | **F** | No contract input/process | Contract-analysis workflow | Remains explicitly unavailable until a contract is supplied |
| Support ID package on real project | Synthetic controlled qualification only | **C** | No OZERO canonical work/matrix/scope | Real project-to-Support binding | Real authorized work can form incomplete/complete package without invented facts |
| Audit report | No OZERO process or result | **F** | Workflow not exercised/delivered | Audit mode E2E | Package denominator, findings, corrections, export |
| Restoration plan/output | No OZERO plan or result | **F** | Workflow not exercised/delivered | Restoration mode E2E | Missing-document/fact plan and non-fabricated drafts |
| Grounded consultant | Some structured answers, unstable inventory outcomes | **D** | Structured source remains incomplete/unreconciled; no exhaustive inventory proof | Inventory-aware assistant | Broad question matrix passes against independently checked evidence |
| Source inspection | Candidate evidence links/routes | **D/E** | Visual click path not verified in this audit; final results absent | Preserve viewer; bind reconciled results | Every material result opens correct source revision/page |

## Evidence appendix

### Authoritative product sources

- `README.md`
- `docs/product/PRODUCT_GOAL_AND_CAPABILITY_MAP_v1.md`
- `docs/product/FOUR_MODE_FUNCTIONAL_MODEL_v1.md`
- `docs/product/PRODUCT_SCOPE.md`
- `docs/product/TRIAL_READINESS_SPECIFICATION_v1.md`
- `docs/missions/OZERO_COMPREHENSIVE_TENDER_GOAL.md`
- `contracts/v2.0/fixtures/valid/product-capability-registry.json`

### Current runtime evidence

- Launchd service definitions: `/Users/oleg/Library/LaunchAgents/ru.asd-kontur.spine.{api,worker,assistant-worker,ntd-worker}.plist`
- Public API/frontend release: `/Users/oleg/.asd-kontur/public-demo/releases/20260923-006d3be-facility-consultant`
- Public document-worker release: `/Users/oleg/.asd-kontur/public-demo/releases/20260923-e78773c-bounded-project-analysis`
- NTD worker receipt: `/Users/oleg/.asd-kontur/public-demo/releases/20260924-7277c63-ntd-worker/release-receipt.json`
- Public logs (read-only inspection): `/Users/oleg/.asd-kontur/public-demo/logs/`
- Database/application projection: deployed `SpinePostgresRepository.project_understanding_view(...)` with owner `owner:07e0deae70cc3b80462746bf` and exact OZERO workspace scope.
- Health: `GET /api/v1/health/live`, `GET /api/v1/health/ready`; both returned 200 at observation time.
- Persisted assistant evidence: `workspace.assistant_turns`, `assistant_messages`, `assistant_tool_receipts`, including original turn `01a088c6-a7a0-7fb4-8a64-732bac76b362`.

### Representative persisted evidence

- Reconciliation: `f2692346-4c3b-53d8-bd8c-9ef5e1a5fa77`, version 1, `terminal_status=partial`.
- Project definition: `f35447ad-b76b-53d7-b92e-3e96e3e82836`, version 1, empty verified fields.
- Requirement matrix: `d9574282-1e40-54d5-a419-cef516498b58`, version 1, all inspected rows incomplete.
- Original failed product answer: turn `01a088c6-a7a0-7fb4-8a64-732bac76b362` said the context lacked project text despite the uploaded sources.
- Later candidate answers: four-item subset on 2026-09-21; ten-item subset on 2026-09-23; current inventory says `exact_total_supported=false`.

### Non-mutation statement

No public code, database record, job, service, source object, model process, migration, or deployment was changed. This report is the only new file and remains uncommitted for owner review.

## Final decision

**First genuinely useful product milestone:** OZERO PROJECT UNDERSTANDING AND TENDER ENGINEERING ANALYSIS v1.  
**OZERO Tender readiness:** NOT ACCEPTED.  
**Support on OZERO:** NOT AVAILABLE.  
**Audit on OZERO:** NOT AVAILABLE.  
**Restoration on OZERO:** NOT AVAILABLE.  
**TrialReadinessDecision:** NOT ESTABLISHED / current recorded `TrialReady=false`.  
**ProductReady=false.**
