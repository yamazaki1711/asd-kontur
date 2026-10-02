# MAC_ASD to ASD-KONTUR Functional Regression Register

- Date: 2026-10-02
- Perspective: professional tasks available to a construction contractor
- Legacy evidence point: `/Users/oleg/mac_asd`, branch
  `feature/core-under-version-control`, commit
  `84099c3bc46c74bff13067c0b9e680e737baa7e0`
- Current evidence point: ASD-KONTUR branch
  `implementation/ntd-canonical-memory-build-01`, inspected through commit
  `0aaf22580045f44534d10f80a3410a41274f1063`
- Reuse policy: the accepted
  `docs/architecture/LEGACY_COMPONENT_DECISION_MATRIX_v1.md`
- Scope: direct Tender and construction-professional results. This is a
  capability audit, not a proposal to restore the MAC_ASD architecture.

## Executive user-result finding

The clearest regression is contract review.

**Before:** a MAC_ASD user could submit contract text or a contract file to an
executable analysis service, receive contractor-facing risks and proposed
wording, and generate an editable protocol of disagreements.

**Now:** ASD-KONTUR has substantially better workspace isolation, durable
lineage, typed contract records, exports and a Russian contract-analysis screen.
However, the ordinary autonomous Tender path does not start the canonical
contract process or create its clauses, issues, proposed wording, protocol
items or revised clauses. With an uploaded contract but no separately created
process, the screen returns `not_started`. This is a
`PROJECTION_WITHOUT_ENGINE` and therefore a user-visible
`FUNCTIONAL_REGRESSION`.

The same pattern appears in several other areas: the current system has safer
and more reusable data contracts, but some direct professional results that
legacy code attempted to produce are absent or remain partial. Conversely,
several legacy claims were demo-grade, synthetic, jurisdictionally stale, or
unsafe and must not be restored as-is.

### Restoration checkpoint — 2026-10-02 14:49 +12

The P0 contract row is no longer a projection without an engine. The current
autonomous Tender path identifies admitted contract documents by content,
creates bounded local-Qwen clause/risk jobs, persists exact-source candidates,
and progressively exposes contractor risks and proposed wording. The live blind
contract has independently produced two source-bound risk/change proposals, and
the partial editable disagreement protocol contains them. Completion remains
`PRESERVED_BUT_INCOMPLETE` until the effective real-contract batch set
converges, the complete protocol and revised-contract candidate pass content
acceptance, and the signed-in browser flow is verified. The historical
classification below is retained as the audit baseline rather than rewritten.

## Method and evidence boundary

The audit inspected the legacy source, tests and product documents named in the
programme directive, plus the current Product Goal, Capability Registry,
Implementation Plan, Tender application, persistence, generalized analysis
harness and current tests.

The audit distinguishes three evidence levels:

1. **Executable legacy behavior:** a callable implementation and
   characterization tests exist.
2. **Legacy design claim:** documentation describes behavior, but the inspected
   path does not prove a reliable production result.
3. **Current product behavior:** a normal user/application path exists, not
   merely a schema, test fixture, manual service method or renderer.

No legacy test count is treated as proof of professional correctness. No
current schema or projection is treated as proof that an analysis engine exists.

## Classification key

- `A PRESERVED_AND_BETTER`: the same practical result exists and the current
  product is materially safer or more useful.
- `B PRESERVED_BUT_INCOMPLETE`: useful behavior exists, but important parts of
  the user result were lost or remain unavailable.
- `C PROJECTION_WITHOUT_ENGINE`: result schemas/UI/export exist, but ordinary
  processing does not autonomously produce the result.
- `D FUNCTIONAL_REGRESSION`: MAC_ASD could perform the task and ASD-KONTUR
  currently cannot provide an equivalent user result.
- `E OBSOLETE_OR_UNSAFE`: the legacy behavior must not be restored as-is.
- `F NOT_RELEVANT_TO_CURRENT_PRODUCT`: deliberately outside the current product
  objective.

## Functional regression register

| Capability | What useful task was possible before? | What happens now? | Class | Root cause and safe path | Priority |
|---|---|---|---|---|---|
| Contractor-facing contract analysis | Submit contract text/file; run Qwen review over the whole contract or bounded chunks; receive clause references, risks, consequences and recommendations. | Document-role classification can identify `contract`; generic task names `CONTRACT_SUMMARY` and `CONTRACT_RISK_REVIEW` exist; canonical contract tables and UI exist. No ordinary worker creates the process, clauses or risk review. | C + D | The re-architecture built the authority/persistence/output boundary but did not connect a semantic engine to autonomous Tender orchestration. Reimplement bounded clause extraction and risk review through current Qwen jobs. | P0 |
| Protocol of disagreements | Generate an editable DOCX from contract findings with clause, customer wording, contractor wording and basis. | Current code can render a much better source-linked DOCX/CSV when canonical disagreement items already exist. Ordinary processing creates no items. | B + C + D | Preserve current renderer and canonical lineage. Generate only from actual clause findings; never insert placeholder parties or invented requisites. | P0 |
| Revised contract candidate | Legacy findings carried `contractor_edit`; document services could form contractor wording, though exact untouched-clause preservation was not reliably demonstrated. | Typed revised-contract and revised-clause versions, UI projection and exports exist, but no engine populates them. | C + D | Reimplement from semantics: exact source clause text plus explicit replacement decisions; preserve untouched clauses byte/text-exactly where extraction supports it. | P0 |
| Contract party and key-term extraction | Extract or accept customer/contractor information and reuse it in legal documents. | General project participant/commercial extraction exists, but it is not connected to a clause-level contract process or protocol metadata. | B | Reuse the semantic task, not the legacy cache. Persist workspace-scoped participants with source locators and leave absent requisites blank. | P0 |
| Contractor risk-pattern review | Search a library of payment, penalty, acceptance, scope, warranty, subcontract, liability, termination and insurance traps, then ask the model to interpret them against contract text. | Practice Intelligence and Knowledge Gateway exist, but there is no reviewed contractor-risk catalog feeding autonomous contract review. | D | Audit and rewrite generic commercial patterns as practice knowledge. Verify legal authority separately. Never make keyword matches findings by themselves. | P0 |
| Project-to-contract consistency | Legacy architecture described contract checks, but the legal service mainly reviewed contract text in isolation. | ASD-KONTUR has a structured project model and generalized duration/commercial comparisons, but no clause engine connects contract obligations to unresolved quantities, omissions, POS duration or Customer-controlled inputs. | B; current architecture can become better | Add structured links from contract clauses to project facts and deterministic dates/amounts. This is a current-architecture advantage, not legacy code reuse. | P0 |
| PD/RD/VOR quantity comparison | Legacy `PTO_VorCheck` compared normalized/fuzzy work labels, units and volumes and surfaced missing/extra rows. | ASD-KONTUR has source-scoped work/quantity/material models, semantic scope matching, Decimal arithmetic and professional findings. Live real-project coverage is still incomplete, but the mechanism is safer than label-only matching. | B, with parts A | Continue the generalized Tender harness. Do not restore fuzzy label matching as authority; preserve only changed-name test scenarios. | P1 |
| VOR-to-estimate delta | Legacy skills compared VOR and estimate positions and described volume/price deltas. | Current extraction and project-engineering code support VOR/estimate roles and some compatible-scope comparisons, but a project-wide user result is not yet consistently produced. | B | Use current scope compatibility and unit model. Add price arithmetic only where real rate/price inputs exist. | P1 |
| Estimate calculation / local estimate generation | Legacy `SmetaCalc` and `SmetaEngine` could calculate direct costs, overhead, profit, VAT and output estimate artifacts from supplied rates. | ASD-KONTUR does not provide an equivalent general estimate-calculation workflow. | D for the direct user task; E for reuse as-is | Legacy tests embed historical methods, rates, regional zones and tax assumptions. A future engine needs versioned price bases, territory/date, calculation method and qualified output. Do not put it on the contract P0 path. | P2 |
| NMCK and profitability analysis | Legacy Tender helpers extracted NMCK, compared it with a calculated cost and produced participate/do-not-participate signals. | Current generalized commercial extraction can represent NMCK and conditions, but there is no qualified profitability calculation or dependable Tender decision based on current prices. | D; legacy implementation partly E | Reimplement only after a qualified cost basis exists. Reject hardcoded VAT, rates, regional coefficients and company thresholds. | P2 |
| Procurement requirements summary | Legacy helpers extracted procurement intake, profile/experience constraints, deadline and conditions. | Generic `PROCUREMENT_SUMMARY`, participant and commercial-condition tasks exist; the primary report can display facts, but real-corpus coverage is incomplete. | B | Complete structured extraction with document role and source scope. Do not assume 44-FZ/223-FZ when the corpus is private procurement. | P1 |
| Tender decision support | Legacy helpers aggregated NMCK, conditions, contract risks and company profile into a verdict. | Current product exposes issues/questions/risks but not a dependable contractor bid decision supported by complete cost, contract and engineering inputs. | D; old verdict logic E as-is | Build an explainable decision only from qualified sub-results. Missing cost/contract inputs must be explicit, not silently defaulted. | P2 |
| Omitted-work detection | Legacy VOR/PD comparison emitted unmatched rows, including false-positive-prone fuzzy results. | Current scope-aware design/commercial comparison and omission finding types exist and are safer; real-project semantic consolidation remains incomplete. | B, with mechanism A | Keep current evidence and scope guard. Reuse only the user journey and controlled missing-work scenarios. | P1 |
| Construction Tender report | Legacy documents described an executive result assembled by agents and helpers; reliability varied. | Current ASD-KONTUR automatically produces an adaptive project-first Tender report from the structured model, but contract sections remain empty without the missing engine. | B | Feed canonical contract findings into the existing primary report; do not create a second report stack. | P0/P1 |
| Editable professional document generation | Legacy generated DOCX protocols, claims, lawsuits, acts, letters and estimate files. | ASD-KONTUR has deterministic DOCX/CSV/ZIP exports, source-linked Tender reports and package manifests. Contract exports are present but data-empty without the engine. | A for generic export infrastructure; B/C for contract results | Retain current export infrastructure. Characterize only the useful table/layout semantics from legacy assets, subject to license and render checks. | P0 |
| Pre-trial claim and lawsuit generation | Legacy exposed tools for claims and arbitration pleadings with automatic monetary/legal text. | Not a current permanent result or required Tender workflow. | F, and E as automatic legal output | Do not restore in this programme. It carries high legal-authority and stale-rate risk. | Deferred |
| EIS Tender search/scraping | Legacy docs explicitly mark the scraper deferred/simulated. | Users upload a selected package. | E/F | Do not restore simulated discovery as a production capability. | None |
| Supplier price-list and purchasing tools | Legacy exposed parsing and supplier/procurement helpers. | Not part of the active generalized Tender/contract regression slice. | F for this programme | Reassess only against a future explicit purchasing capability. | Deferred |

## Priority-one contract regression in current code

### Useful current assets

ASD-KONTUR already has reusable, safer assets:

- document roles include `contract`, `procurement_notice` and Tender source
  classes;
- autonomous project scheduling and persistent local-Qwen execution;
- generic task identifiers `CONTRACT_SUMMARY` and `CONTRACT_RISK_REVIEW`;
- canonical Tender process, clause, issue, disagreement-protocol and
  revised-contract tables;
- RLS/default-deny workspace isolation and immutable source versions;
- source locator navigation;
- read-only Russian UI and DOCX/CSV renderers;
- a project model suitable for contract-to-engineering checks.

### Missing middle

No production call site outside tests invokes the current Tender writer to
start a process and append clauses, issues, disagreement items or revised
clauses. The visible screen therefore has this behavior:

`uploaded contract -> role/input assessment -> no canonical contract process -> not_started`

The required behavior is:

`uploaded contract -> clause extraction -> contractor-risk review -> project/contract checks -> proposed wording -> protocol -> revised-contract candidate`.

The missing engine, not the renderer, is the P0 task.

## Legacy contract capability characterization

At the inspected commit, MAC_ASD provided:

- `asd_analyze_contract`, which accepted document text, file path or persisted
  document identity and called `LegalService.analyze`;
- whole-document quick review with a Map/Reduce fallback;
- model-generated finding fields including clause reference, issue,
  recommendation and proposed contractor edit;
- a trap/RKB lookup before model review;
- `asd_generate_protocol` and `LegalDocumentGenerator`, which produced a DOCX
  disagreement table;
- schemas for parties, findings, protocol items and verdicts;
- characterization tests for chunking, JSON parsing, finding aggregation and
  DOCX generation.

This proves prior product intent and an executable user path. It does **not**
prove legally qualified output or safe production behavior.

## Legacy defects that must not be restored

1. A model/service failure could fall back to an `approved` result.
2. Invalid model JSON could become a pseudo-finding about parser failure.
3. Unknown enum values silently became the first enum member.
4. Protocol generation defaulted missing contract/party data to underscores,
   `Customer` and `Contractor`, allowing placeholders into a professional file.
5. The protocol tool asserted that every revision rested on a concrete legal
   article, although model output and the RKB did not establish that safely.
6. Legal analysis could consume an entire large contract in one call based on
   model-context assumptions rather than bounded clause contracts.
7. Keyword/fuzzy matching and model confidence could be treated too strongly.
8. Tests largely use authored findings rather than proving discovery on an
   unseen real contract.
9. Legacy estimate/profitability logic contains hardcoded tax, method,
   territory and company-threshold assumptions.
10. The trap catalog is internally inconsistent: documentation refers to
    approximately 61 or 96 traps, while `traps/default_traps.yaml` contains
    100 entries. Several legal citations, court cases, quantitative thresholds
    and assertions require current independent verification.

## Legacy Risk Knowledge Base salvage audit

The 100-entry legacy YAML has the following actual category counts:

| Category | Entries | Initial reuse classification |
|---|---:|---|
| payment | 8 | `NEEDS_REWORDING`; useful generic commercial patterns, legal basis must be checked |
| penalty | 7 | `NEEDS_CURRENT_LEGAL_VERIFICATION` |
| acceptance | 8 | `NEEDS_REWORDING`; retain practical delay/payment patterns |
| scope | 7 | `SAFE_GENERIC_PATTERN` at the problem-pattern level; citations require verification |
| warranty | 6 | `NEEDS_CURRENT_LEGAL_VERIFICATION` |
| subcontractor | 6 | `NEEDS_REWORDING`; contract/procurement context dependent |
| liability | 6 | `SAFE_GENERIC_PATTERN` at the exposure level; proposed caps are not universal |
| corporate_policy | 5 | `PROJECT_SPECIFIC` unless the exact policy is supplied in the workspace |
| termination | 4 | `NEEDS_CURRENT_LEGAL_VERIFICATION` |
| insurance | 3 | `NEEDS_REWORDING`; project and contract dependent |
| legal | 1 | `NEEDS_CURRENT_LEGAL_VERIFICATION` |
| audit_traps | 12 | outside contract P0; review separately for Audit mode |
| restoration_traps | 11 | outside contract P0; review separately for Restoration mode |
| construction_traps | 16 | mixed; not a contract catalog |

No entry is imported automatically. `SAFE_GENERIC_PATTERN` means only that the
commercial exposure is reusable as a question for analysis; it does not
promote the attached legal statement, severity, threshold, court citation or
proposed wording. The modern catalog must version the pattern, jurisdiction,
review status and authority references separately.

## Legacy Component Decision Gate records

| Legacy source | Capability | Ownership/license | Current validity and generality | Security/dependencies | Characterization | Decision |
|---|---|---|---|---|---|---|
| `src/core/services/legal_service.py` (`sha256:8c897046...`) | whole-contract/Map-Reduce semantic review | supplied owner repository; no standalone permissive legacy license was found | useful flow, unsafe fallback and stale authority assumptions | tied to legacy LLM/RAG/DB stack | `tests/test_legal_service.py` | `REFERENCE_ONLY`; reimplement bounded tasks on current Qwen runtime |
| `mcp_servers/asd_core/tools/jurist_tools.py` (`sha256:f85e7872...`) | user-callable analysis and protocol flow | same boundary | proves user workflow; placeholder and blanket legal claims unsafe | legacy MCP and direct file output | legal tool/service tests | `REFERENCE_ONLY` |
| `src/core/services/legal_documents.py` (`sha256:5c06561f...`) | protocol table and legal document formatting | same boundary; third-party assets require separate review | protocol layout useful; claims/lawsuit calculations may be stale | python-docx and legacy filesystem | `tests/test_legal_documents.py` | `ADAPT` only for characterized layout semantics; use current renderer |
| `traps/default_traps.yaml` (`sha256:b2c988fe...`) | contractor-risk pattern corpus | same boundary; embedded external legal/case content needs review | mixed generic, stale, project-specific and unverified content | no runtime code risk, high authority risk | count/category inspection; no unseen-contract qualification | `REFERENCE_ONLY`; individually review and rewrite before promotion |
| `src/agents/skills/pto/vor_check.py` (`sha256:e2616eb7...`) | VOR/PD matching scenarios | same boundary | useful scenarios; fuzzy labels alone are not engineering scope | legacy skill framework | `tests/test_vor_check.py` | `REFERENCE_ONLY`; current scope engine remains authoritative |
| `src/agents/tender_helpers.py` (`sha256:27d4a699...`) | NMCK, procurement, conditions, estimate delta and verdict journeys | same boundary | mixed generic workflow and hardcoded company/regional policy | legacy state/agent stack | tender-helper tests | `REFERENCE_ONLY`; reimplement only qualified sub-capabilities |

No inspected component qualifies for `REUSE_AS_IS`.

## Reimplementation boundary for contract P0

The first implementation slice must deliver one complete professional path:

1. autonomously detect an admitted contract document;
2. persist exact clause units and source locations;
3. ask local Qwen bounded, structured questions about obligations and risks;
4. validate Qwen output and retain uncertainty;
5. deterministically extract dates, percentages and monetary values from the
   structured clause result and perform arithmetic outside Qwen;
6. compare contract terms with project facts where compatible;
7. persist contractor risk, consequence, action and proposed wording;
8. generate an editable protocol of disagreements and revised-contract
   candidate without invented parties or requisites;
9. expose progressive status in the existing UI and feed the main Tender
   report;
10. prove the same code on a changed controlled contract including a benign
    clause that remains unflagged.

Professional review/signing remains a separate authority action. Reading and
editing the analysis result must not require signature authority.

## Ordered backlog after contract P0

1. Complete real VOR/estimate delta and omitted-work results through the
   generalized semantic scope engine.
2. Complete procurement qualification/condition extraction in the primary
   Tender report.
3. Connect contract duration, change-order and Customer-input clauses to the
   project model.
4. Add a qualified contractor Tender decision only after cost, engineering and
   contract sub-results have explicit completeness states.
5. Design a versioned estimate-calculation capability only with current rate,
   method, territory and tax authority; do not resurrect the legacy calculator
   unchanged.

## Audit conclusion

Contract analysis is a confirmed functional regression, not a cosmetic UI gap.
ASD-KONTUR preserved and improved the reliability envelope and output
projection, but the professional task is unavailable until the autonomous
semantic engine populates that projection. The safest recovery strategy is
selective semantic reimplementation using the current durable orchestrator,
local Qwen task harness, project model, canonical Tender store and existing
editable exports.

`ContractAnalysisOperational=false`

`ProtocolOfDisagreementsOperational=false`

`GeneralizedTenderHarness=false`

`AutonomousProjectProcessing=true`

`ProductReady=false`
