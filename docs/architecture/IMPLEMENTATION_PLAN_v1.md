# Implementation Plan v1

## Delivery policy

One active delivery slice advances the complete Product Capability Registry.
Infrastructure micro-gates cannot displace the product path. Every capability
stream ends in a visible professional result with source/evidence, blockers,
recovery and export—not a test-count claim.

## Active product-led delivery policy — 2026-09-19

**Programme objective:** production-quality ASD-KONTUR for Tender, Support,
Audit and Restoration, including evidence-backed analysis and complete,
editable executive-documentation (ID) packages. The 143-capability registry
remains the readiness denominator.

**Delivery unit:** one reusable product capability with a visible application
output. A source receipt, page counter, candidate store, or test suite is
supporting evidence, never the output by itself.

**OZERO:** the preserved OZERO workspace is one real validation corpus. It is
not the product boundary, a required fact source for all development, or a
reason to postpone an independently testable capability. OZERO checks are
recorded with the precise subset they exercise; controlled inputs with known
outcomes establish reusable behaviour first.

The current product path is deliberately two connected increments:

| Capability | Modes | User-visible output | Implementation gap | Acceptance | OZERO role |
| --- | --- | --- | --- | --- | --- |
| Evidence-bound Tender comparison and findings schedule | Tender | Editable schedule of source-backed quantity/material comparisons, risks, consequences and exact missing inputs | Work packages currently mirror raw observations and generic reconciliation cards cannot distinguish a real comparison from unavailable comparison input | Controlled revisions, repeated names, distinct scopes, quantity discrepancy and missing-input cases; persistence, evidence navigation and isolation | Validate a selected available design/estimate subset only; no project-wide claim until coverage supports it |
| Supported ID package formation and export | Support; reusable data prepared in Tender | Register-first editable ID package, generated supported forms, attachments/missing-field manifest and export | Existing package formation needs a scope-aware, deduplicated work package and a production-facing completeness/report boundary | Controlled known work type with composition, missing fields, revisions, export/render/edit/reload/isolation | Optional regression check only; OZERO does not supply execution dates, measurements, signatures or a Support transition |

### Product-led delivery evidence — 2026-09-19

The two initial increments are implemented on feature releases `98b7363` and
`fca2198` (the controlled API release set must still be verified per runtime):

* Tender now consolidates work observations only within an explicit source and
  scope, retains conflicting quantities rather than summing them, exposes a
  source-backed editable findings schedule, and states when estimate or
  contract input is unavailable instead of emitting an unsupported omission or
  generic contract-review conclusion. The Tender result now also publishes the
  same source-scoped work/quantity/material schedule to its application view
  and exports: same-named work in different scopes remains separate, values
  are observations rather than a project total, and each row retains locator
  references and reconciliation limits.
  The editable CSV and DOCX finding exports now resolve a finding to a work
  package only through exact candidate-observation membership. They show the
  source-scoped work name and scope where that membership exists; a matching
  label in another scope cannot be selected. This makes a discrepancy usable
  for bid preparation without promoting it to a confirmed omission or
  collapsing repeated work names.
* Support can export the exact formed package as a deterministic editable ZIP:
  its register is the first entry, available generated/finalized documents are
  included, and missing/blocked positions are an explicit separate schedule.
  The archive also carries a deterministic field-evidence and missing-input
  schedule.  It coalesces multiple evidence bindings for one field, retains
  candidate/confirmed/missing state, and names the exact locator identifiers.
  A generated candidate therefore cannot make a missing material input appear
  completed.  This is independently covered by a disposable PostgreSQL
  Support-package test.  The Support UI presents the same field states and
  linked source locators in a deduplicated table rather than labelling the
  section as completed fields.  OZERO is not used for this acceptance.

* Support package formation now requires an existing scoped Support process.
  The Product Application exposes its immutable scope/process context and, if
  it is absent, explains that an authorised professional must configure the
  Support scope before an ID package can be formed. This prevents an apparent
  package from being created against a raw Tender observation without a
  declared deliverable scope, policy set, and rule-set version. It does not
  promote Tender candidates, bypass a professional grant, or require routine
  manual review of every observation. Controlled PostgreSQL acceptance proves
  both the configured process success path and the no-process API rejection;
  the generated OpenAPI client and Russian UI distinguish the two states.
  OZERO is not used.

The reusable Support configuration command is now implemented behind an
explicit role-separated connection.  The owner-scoped Product Application
connection resolves workspace access and verifies the exact Support mode plus
an admitted intake manifest; only a configured `asd_support_service` connection
can append the Support process and scope versions.  The existing Support writer
then re-verifies the active human `support.scope.configure` grant in the same
transaction as the append-only process records.  Semantic idempotency excludes
newly allocated command/process IDs, so a retry returns the original process
while a changed request under the same key is rejected.  Disposable PostgreSQL
acceptance proves the successful path, replay, semantic conflict, invalid
manifest rejection, cross-owner default deny, and visibility through the
existing ID-production projection. OZERO is not used.

The Support ID screen now also discovers that command's prerequisites through
an owner-scoped readiness projection instead of asking a user to copy opaque
database identifiers. It derives the active Support execution, exact active
rule set, workspace contract registry, admitted intake manifest, policy and
authority profile versions, and the authenticated owner's unexpired
`support.scope.configure` grant. The UI offers one bounded action for the
currently supported `id_package` scope only when every prerequisite and the
dedicated writer service are available; otherwise it names the exact missing
prerequisite in Russian. The command independently revalidates the entire
derived contract and rejects client tampering before the role-separated write.
Controlled PostgreSQL acceptance proves discovery, tamper rejection,
idempotent configuration, cross-owner default deny, and continuity into the
existing register-first package generator. OZERO is not used.

The live Product Application runtime still has no
`ASD_SUPPORT_COMMAND_DATABASE_URL`, so this writer capability remains disabled
there and no privileged connection was added to the running process. Production
acceptance still requires an approved Support-service credential assignment,
an actual professional grant, deployment/recovery evidence, and an authorised
live UI run through scope configuration, package formation, generation and
export. This is an
operational/authority dependency, not an OZERO-processing blocker.

* The platform construction consultant now projects Gateway evidence into a
  bounded structural prompt before local-Qwen generation. Every selected
  source retains its source-version identity, locator, authority layer, and
  access reference; only optional excerpts and non-evidence result fields are
  bounded. This prevents long metadata from removing later evidence or leaving
  a malformed JSON fragment in the model context. The full Gateway receipt and
  persisted message source records remain the audit boundary. A controlled
  unit case exercises two sources separated by 50,000 characters of irrelevant
  metadata, and a bounded loopback request confirms the configured local Qwen
  generation contract. OZERO is not read or changed. This advances a reusable
  evidence-bound analytical consultation surface; it does not establish its
  full professional quality matrix, browser E2E, or a mode-ready decision.

* The same consultant UI now retains one request identity for a retry of an
  unchanged question in the same conversation. If a response is lost after
  persistence, retrying uses the existing idempotency contract instead of
  silently creating another pair of messages. Changing either the conversation
  or question deliberately starts a new request. A compact frontend unit test,
  lint, typecheck, and production build cover that reusable interaction;
  OZERO is not used. Browser E2E remains an explicit separate check because
  no authenticated browser binding is available in this session.

* Tender now exposes a read-only Russian application view of the canonical
  contract-analysis process: its corpus assessment, extracted clause records
  with exact locator navigation, registered issues and typed deliverables.  An
  absent process is presented as `not started`, not as a successful review or
  a finding that no risks exist.  The view cannot write clauses, issues,
  professional grants or legal conclusions; those remain in the separately
  authorised Tender-service flow.  Disposable PostgreSQL application-boundary
  acceptance proves the owner can read the honest empty state and another
  owner receives no workspace data.  OZERO is not used: this capability is
  exercised through controlled scoped data and can later project an authorised
  OZERO Tender process without a project-specific branch.

* The same owner-scoped Tender projection now includes the exact current
  disagreement-protocol items and revised-contract clauses already written by
  the separately authorised Tender service. The Russian UI links each proposed
  revision back to its source clause locator, and an editable CSV retains the
  clause, source-version, locator, evidence, consequence, proposal, revised
  wording, uncertainty, and deliverable state. A missing process exports an
  explicit `not started` row instead of an empty risk schedule. Controlled
  PostgreSQL 17 acceptance proves canonical lineage and cross-owner default
  deny; a separate changed-identifier fixture proves the export is reusable and
  neutralizes spreadsheet formulas. OZERO is not used. This advances the
  contractor-protective R1 output but does not create legal findings, qualify a
  reviewer, deploy the release, or establish Tender mode readiness.

  Exact release `0250683c12c6992d0444339c62d05e1e2a9d7fb1` is now active for
  the public API/frontend against migration `0059_scoped_worker_job_claims`.
  Readiness, the versioned OpenAPI route, the exact built frontend asset, and
  the public TLS ingress were verified after activation; document and assistant
  workers and local Qwen were not restarted.  The reusable behavior is proven
  independently of OZERO by PostgreSQL 17 application-boundary tests with
  canonical lineage and cross-owner default deny, plus a changed-identifier
  export fixture.  OZERO was not used because no authorized contract-analysis
  process has been established for that validation corpus.  An authenticated
  browser run remains unverified because no browser binding or external-E2E
  credential set was available in the execution session.  Tender mode still
  requires an authorized legal-analysis flow, professional review authority,
  real-corpus validation where applicable, and its remaining mode gates.

  The same canonical projection now renders an editable Russian Word report
  for contractor review.  It pairs each disagreement item with the exact
  revised clause where available, retains source-version, locator and evidence
  identities, lists risks and deliverable blockers, and states that the file is
  not a legal opinion, approval or signed contract.  A controlled changed-ID
  fixture proves the report is not project-specific; the full PostgreSQL
  Tender flow proves canonical content and exact source lineage; the owner API
  test proves honest `not started` output and cross-owner default deny.
  `textutil` successfully re-opened the generated OOXML and retained Russian
  text and source references.  OZERO is not used because this is reusable
  contract-output behavior and its workspace has no authorized contract-
  analysis process.  Professional approval and a real contract corpus remain
  separate production-acceptance gates.

* Audit preflight now emits an editable, scope-and-version-bound correction
  schedule.  For every required document it records the practical consequence
  and the bounded next action (form a package, attach source-backed evidence,
  resolve a conflict, or perform an independent audit).  It deliberately does
  not classify any item as audit-satisfied: candidate presence and finalization
  remain distinct from independent content audit.  Disposable PostgreSQL API
  acceptance exercises generated and missing document cases; OZERO is not
  needed.

* Tender work/resource schedules retain a stated zero quantity as an
  observation.  Zero is distinct from absent data and remains source-scoped;
  no project total is inferred.  Controlled exporter and disposable
  project-understanding API tests cover this behaviour without OZERO.

* Tender reconciliation now performs an automatic quantity comparison only
  for one exact normalized work observation and one estimate-position
  observation.  Repeated work names in different scopes or repeated estimate
  positions remain an evidence-backed ambiguous match; neither side is
  silently attached to the other or reported as unsupported.  Because the
  current estimate input contract contains no material/resource positions, a
  project material produces an explicit missing-comparison-input observation
  rather than the unsupported conclusion that it is absent from the estimate.
  Controlled fixtures cover same-named LOS/KNS work, a one-to-one quantity
  delta, and a material row; OZERO is not used.  The next extension for an
  actual material-omission comparison is a versioned estimate-resource input,
  not a looser name match.

* The existing material-candidate contract now also supports a bounded,
  evidence-safe material comparison: an estimate resource is eligible only
  when its parent estimate work has the same exact source locator and
  normalized work description as the estimate position.  With such a resource
  row, a missing project material is a candidate Tender difference; without
  one, the output remains an explicit missing comparison input.  Controlled
  fixtures prove both the exact-locator match and the no-resource boundary;
  this has no OZERO dependency and requires no schema migration.

* When that exact material-resource link contains usable quantities and units
  on both sides, Tender now emits a source-bound material quantity difference
  or incompatible-unit observation.  If either source does not state a usable
  value, the output names the missing comparison input instead.  Controlled
  fixtures exercise both equal and different quantities; OZERO is not used.
  Deployment to the document worker and a selected real-document regression
  remain distinct acceptance steps.

* The supported ID-package export now makes its first, editable register
  readable in Russian: qualified document roles and member states use display
  labels while their stable role IDs remain in parentheses.  The adjacent CSV
  remains the machine-friendly projection.  A controlled archive check opens
  the OOXML register and the disposable PostgreSQL Support workflow verifies
  the same export after forming a package and generating its supported
  candidate.  OZERO is not used.  This improves one reusable package surface;
  it does not qualify an official form template or establish Support mode
  readiness.

The same export now contains a deterministic delivery manifest after the
register and generated documents. It records the exact package version,
membership/version state, template qualification boundary, evidence references,
blockers, and SHA-256 digest of each included document. Missing and blocked
members are recorded without a fabricated file. This lets an editable package
be checked after download or handoff without treating a generated candidate as
a signed or executed document. A controlled archive test verifies ordering,
digest binding, candidate/missing preservation, and the PostgreSQL Support
workflow verifies the downloadable package. OZERO is not used; it has no
field-execution authority or actual Support transition.

Release `98b7363` replaces the CSV-only first register projection with a
Russian editable DOCX register candidate as the first archive document,
retaining the CSV as a tabular projection and the missing-items schedule as a
separate truthful boundary. It is tested from controlled package data with a
valid OOXML structure and a persisted application export. It does not claim
official register-template authority, completed field records, or visual
renderer qualification; OZERO is not required for this change.

Tender now also has the editable Russian report described above. It exposes the
current materialization state, coverage gaps, candidate finding, practical
consequence, exact missing input, and source/revision/locator reference.
Controlled project-model data tests its candidate boundary and document
validity; an OZERO check is limited to rendering its already-persisted findings
and never implies full-corpus Tender acceptance.

The exact-membership context change is covered by controlled same-name/different-
scope fixtures, CSV/DOCX structural output checks, scoped application-service
tests, and the PostgreSQL-backed project-understanding API suite. OZERO was not
read or changed: it remains a later real-document validation of this reusable
output, not its acceptance oracle.

Tender delivery now also includes an editable **document-processing coverage
schedule**.  It has one row per active source version and preserves admission,
native-extraction, semantic-profile, expected/accepted/failed fragment, and
unresolved-failure states separately.  The schedule is included in the
deterministic Tender archive and can be downloaded directly from the Tender
view.  Consequently a readable document or a completed OCR stage cannot be
presented as completed engineering analysis.  Controlled PostgreSQL API
acceptance covers active-source scope, the direct download, archive membership,
and a native-complete/semantic-partial case.  OZERO is not used; a later
real-document validation can only establish the status of the selected active
OZERO sources, not universal package coverage.

The Tender result labels the persisted source-and-scope groups as **work
observations**, not work packages.  The current persistence boundary safely
retains raw candidate observations but does not yet establish cross-document
facility identity or an awarded commercial scope.  Reusing its raw count as a
work-package total would therefore inflate the user-visible result.  Controlled
same-name/different-scope fixtures verify the changed label and count; OZERO
is not needed.  A future reusable facility/scope reconciliation capability is
required before these observations can become a deduplicated package basis for
Support.

Tender now also exports a **cross-document structure identity candidate
schedule**. Each row is one original source observation with its candidate
group, confidence, raw label, locator, and a literal `automatic_merge=false`.
The same schedule is present in the Tender analysis ZIP and downloadable from
the structure view. It makes facility aliases and possible cross-discipline
links usable for review without creating a canonical facility, attaching work
or quantities by name, or requiring a user to confirm unrelated observations.
Controlled two-source alias fixtures and the authenticated PostgreSQL project
understanding flow verify all rows, source links, ZIP order, and workspace
scope. OZERO is not needed; it may later validate only the identity candidates
its processed sources actually produced.

Tender additionally publishes an editable **facility/work observation
association schedule**. It links a raw work observation to one structure or
facility identity candidate only where they share an exact persisted source
locator. A single match is exposed as a candidate association; multiple matches
remain an explicit ambiguity; no match is stated without inventing an
association. It neither canonicalizes facilities nor promotes work observations
to awarded work packages, and it never uses a shared normalized name as an
identity key. Controlled fixtures verify same-named work in separate scopes,
one exact locator match, and a two-candidate ambiguity; scoped PostgreSQL API
coverage verifies authorization and download. OZERO is not needed for this
reusable Tender output. It can later validate only links from its accepted
source evidence.

The same facility/work candidate schedule is also a member of the deterministic
Tender analysis archive (`tender.analysis-delivery@1.3.0`), between identity
candidates and document coverage. Its manifest binds the exact CSV digest and
the status text states the exact-locator and ambiguity boundary. Controlled
archive and PostgreSQL-backed API tests verify member order and workspace scope;
OZERO is not used. This is a packaging improvement, not canonical facility or
work-package reconciliation.

The project-structure view now carries the same bounded association into each
source-scoped facility/area dossier: it lists work observations only when the
work and the structure node share the exact persisted locator, and labels the
link as a source-shared candidate rather than a confirmed assignment. This
provides useful `facility → related work observations` navigation without
merging same-named facilities or work across sources. Controlled unit data
changes both scope and locator while PostgreSQL-backed project-understanding
acceptance verifies the projection, evidence access, and workspace boundary;
OZERO is not needed. A later canonical facility/work reconciliation remains a
separate Support prerequisite.

The project-understanding view now contains a reusable **Tender input
assessment** derived only from active source versions and persisted document
role decisions. It identifies design/working documentation, quantities or
estimates, a draft contract, customer regulation, and specifications as
available, classification-incomplete, or not detected in fully classified
sources. Each unavailable category states the specific limited analysis: for
example, an absent contract limits contract review but does not block design
analysis. Controlled DOCX/CSV workspace acceptance covers availability,
absence, source locators, persistence, and RLS scope; OZERO is not required.
This assessment reports input availability, not the legal sufficiency or
professional completeness of a Tender submission.

The same project-understanding surface also provides a separate editable
work/quantity/material CSV schedule. It has one row per candidate work package,
retains raw and normalized quantity observations, materials, exact locator
references, scope and unresolved conditions, and intentionally does not sum
identical names across locations. Controlled input changes identifiers and
values across two same-named scopes; the authenticated PostgreSQL-backed API
test verifies the download and its candidate boundary. This is a usable Tender
pricing/comparison input, not a confirmed quantity total. OZERO is not needed
to establish the mechanism.

The Tender application additionally exports those three candidate projections
as one deterministic analysis ZIP: editable findings report first, then the
findings and work/resource schedules, followed by an explicit coverage/status
file. The archive does not claim a contract conclusion or a project-wide total.
Its content order, partial-coverage notice, OOXML member and authenticated API
delivery are verified on controlled PostgreSQL-backed project data; OZERO is
not required for this output contract.

Tender comparison findings now show the exact persisted operands in the
application, editable CSV, and editable Russian DOCX report: the project value,
estimate value, shared unit, and the exact `project_minus_estimate` decimal
difference when both values have a compatible stated unit; otherwise they show
the two incompatible units.  The renderer does not calculate a new total,
convert units, or resolve an ambiguous match.  This makes a source-backed
discrepancy usable for bid preparation while preserving its candidate status.
Controlled quantity-mismatch fixtures and the authenticated PostgreSQL
project-understanding export verify the output; OZERO is not used for this
acceptance.  A real document check can only confirm that a particular
persisted OZERO finding is rendered, not that all project quantities have been
reconciled.

The current reusable output is an **Audit expected-versus-package preflight**.
It is a workspace-scoped application projection of exact
requirement versions and ID-package memberships. It preserves repeated document
names in distinct work scopes, reports missing/generated/finalized-but-not-yet-
audited positions, and never promotes a package member to an independently
audited conclusion. It is intentionally not the immutable canonical Audit
ledger: that ledger remains owned by the separately scoped `asd_audit_service`
role. Controlled support-package data verifies identity/version matching,
candidate boundaries, API authorization, UI rendering, and editable CSV export;
OZERO is not needed for its acceptance. The next Audit increment is the
separately scoped canonical Audit-process service and its immutable evidence
ledger; this preflight must never be relabelled as that service's conclusion.

The canonical Audit service can now issue an immutable, evidence-bound
correction request for one exact snapshot-bound Audit process. Issuing it
transitions that process to `blocked`; it does not manufacture remediation or
grant the Product Application role the Audit-writer role. Disposable
PostgreSQL acceptance verifies request persistence, exact process revision,
and the append-only write fence. The next canonical dependency is versioned
request membership in a final Audit report, followed by a separately scoped
owner-readable projection. OZERO is not needed for this acceptance.

The next Audit increment is now implemented as an **owner-readable immutable
report projection**. Finalizing a canonical Audit report publishes customer and
PTO projections in the same Audit-service transaction, each bound to the exact
report version, snapshot fingerprint, three delta versions, unresolved items,
and versioned correction requests. The Product Application role receives only
scoped `SELECT` on this immutable projection boundary; it receives no Audit
ledger write privilege. The Russian Audit UI shows either the published report
or the truthful absence of a canonical report, without relabelling the package
preflight as an independent audit. Controlled PostgreSQL acceptance verifies
atomic publication, default-deny/scoped visibility, and application-write
rejection; the generated OpenAPI and frontend build verify the application
surface. OZERO is not used. Deployment remains a separate operation because
the live OZERO-compatible database is at an earlier migration head and has no
configured canonical Audit-service runtime.

The owner-readable Audit projection now has an editable CSV export. It retains
the exact report/version, projection fingerprint, delta versions and unresolved
item keys, plus each immutable correction-request version with its evidence and
blocking impacts. A not-published report exports an explicit absence row rather
than a clean conclusion. The Product Application still reads only the immutable
projection boundary and cannot create an Audit decision or remediate an item.
Controlled projection payload tests and PostgreSQL-backed application routing
verify the content, RLS-scoped download, and the not-published boundary; OZERO
is not needed. A qualified canonical Audit-service deployment and a complete
professional Audit workflow remain separate acceptance requirements.

Final Audit reports now bind exact immutable ActionRequest versions through a
separate membership table. Unknown, cross-process, or duplicate request
versions are rejected before finalisation; reclassification is required after
an issued action moves the process to `blocked`. The report remains an Audit
service-owned record and does not yet have an owner-readable application
projection. Controlled Audit tests cover report/request linkage and immutable
membership; OZERO is not used.

Canonical Audit persistence now has the first reusable lifecycle and ledger
implementation on feature releases `4100b4d`, `009972f`, and `dcf452f`:
an Audit process is pinned to one exact corpus snapshot and rule-set version;
its collection/reconciliation/snapshot/evaluation header states use optimistic
concurrency; document, causal-readiness, and package/signing/handover deltas
are committed atomically with their evaluation transition. Causal paths and
package-to-delta membership are preserved as immutable payloads rather than
being reduced to counters. A disposable PostgreSQL acceptance exercises
scope/RLS, retry, stale-revision, snapshot binding, and all three delta kinds.
This is an implementation foundation, not a public Audit conclusion. The next
feature release persists a final Audit report only when its pinned corpus
snapshot plus the document, causal-readiness, and package/signing/handover
deltas each resolve to one exact immutable evidence version; it finalizes the
process atomically and keeps `product_ready=false`. The PostgreSQL acceptance
covers the success path, an altered delta fingerprint, and action-request
rejection. Versioned ActionRequest persistence and report membership remain an
explicit next dependency: a report carrying bare action-request IDs is rejected
rather than silently binding an arbitrary later action version. User-facing
Audit report/projection output and an authorised, separately configured Audit
service still remain. The public application role must not be granted the
audit-service role merely to expose this work. OZERO is not used for this
acceptance.

Restoration now has a reusable, read-only recovery-plan projection built from
the same exact matrix/package preflight. It distinguishes reviewable generated
candidates from positions that require a real source document, field fact,
test record, measurement, date, signature, or applicable requirement basis.
It does not generate a document in place of missing evidence. Controlled data
tests the non-fabrication boundary and application API; OZERO is not required.
The next Restoration increment is durable recovery-process state plus
evidence-bound document regeneration for a separately declared supported form.

The current Restoration delivery adds an editable CSV handoff of that exact
plan. It keeps recoverable candidates and blocked missing-evidence positions
separate, includes their requirement/version/evidence references and global
blockers, and marks every row as fabrication-prohibited. Controlled plan data
and the authenticated PostgreSQL-backed Support/Audit/Restoration application
flow verify the export; OZERO is not used.

Restoration now also persists a **versioned recovery-assessment snapshot**.
The user can explicitly fix the current expected-versus-package basis, ordered
recoverable actions, blockers, evidence references and non-fabrication boundary
through the application. The snapshot is append-only, RLS-scoped, idempotent
for identical plan content, and shown as current or stale against the live
preflight; it never changes an uploaded source, field fact, package membership,
date, measurement, test record, or signature. A controlled PostgreSQL flow
forms a scope-bound package, captures version 1, proves replay idempotency,
then changes the supported package state and captures version 2. The UI/API
and editable CSV expose the recovery plan; OZERO is not needed. This advances
the reusable Restoration recovery process, but **does not yet regenerate a
document**: the next ID-production dependency is a separately declared,
qualified form whose every material field is evidence-bound.

The compatible controlled API/frontend release is pinned at
`d0696f066848361b76e9a015b8f1709f0448edea` with database migration
`0056_restoration_recovery_plan_versions`; its sanitized local receipt is
`/Users/oleg/.asd-kontur/public-demo/launchd-backups/20260919T041301Z-d0696f0/release-receipt.json`.
The document worker, assistant worker, and local Qwen runtime were deliberately
not restarted. Live browser authentication and a qualified regeneration form
remain unverified, so this is not a Restoration mode acceptance.

Controlled checks cover repeated names in different scopes, contradictory
quantities, missing estimate input, contract-input state, register ordering,
generated/missing documents, persistence, authorization scope, and ZIP
content. These checks establish reusable behavior; they do not establish
OZERO-wide extraction, Tender completeness, a Support field execution, or
full-product readiness. OZERO remains available for a selected real-data
regression only after the relevant live worker path is healthy.

Blocked live processing and the local Qwen slot never block implementation,
controlled verification, or outputs that do not require that live runtime.
No capability is promoted to `CAPABILITY_READY` without its declared
professional output and E2E evidence.

## Completed prerequisite

`MEMORY-INTEGRITY-FIX-01` resolved the two canonical memory defects and passed
three final consecutive clean-room cycles. The historical defect and failed
series receipts remain immutable. This bounded PASS does not change product
readiness.

## Completed bounded slice: PRODUCT-APPLICATION-SPINE-01

Purpose: establish the minimum user-operable application boundary without
claiming any mode ready.

### Deliverables

1. Python application package with FastAPI candidate qualification, versioned
   OpenAPI, command/query ports and generated TypeScript client.
2. React/TypeScript/Vite shell with authentication, workspace selector,
   four-mode navigation and no demo/fallback domain data.
3. Server-side opaque sessions, CSRF, authorization and workspace/RLS negative
   tests.
4. Workspace lifecycle screens: create/admit, view, archive/export,
   reset/destroy confirmation and receipts.
5. Recursive folder and bounded batch upload with streaming hash, MIME/content
   checks, deduplication, quarantine and document registry.
6. PostgreSQL DurableJob table/worker: leases, outbox/inbox, progress SSE,
   pause/resume/cancel/retry, idempotency and reconciliation.
7. PDF.js document viewer with virtualized pages, source/region navigation and
   evidence side panel.
8. Empty but functional Tender/Support/Audit/Restoration workspaces that show
   honest prerequisites/gaps and never fake results.
9. Read-only Platform Knowledge and operational status surfaces.
10. UI E2E for restart recovery, isolation, no-result, blocker, evidence
    navigation and destructive confirmation.

### Explicit non-goals

No real OKS, product-scale claim, complete mode, new NTD acquisition, CAD
intelligence, G-07B or legacy code copy. Dependencies are pinned only after the
[technology ADR](decisions/0014-product-application-technology-baseline.md) and
[Legacy Gate](LEGACY_COMPONENT_DECISION_MATRIX_v1.md).

### Terminal condition

The Spine ended with selected application/interaction/intake foundations and
their capability E2E. It may advance individual capabilities to
`CAPABILITY_READY`; it cannot set ModeReady, TrialReady or ProductReady.

## Current slice: INDUSTRIAL-DOCUMENT-UNDERSTANDING-01

Purpose: turn admitted ПЗ/ПД/РД/ВОР/estimate documents into an evidence-bound,
visible project model without changing memory integrity or claiming a ready
mode.

`admitted documents → document/page classification → ProjectDefinition → OKS
structure → work/quantity/MTR candidates → ConstructionWorkPackages →
WorkRequirementMatrix → visible evidence-bound UI result`.

This slice starts only after MEMORY-INTEGRITY-FIX-01 is merged. It must use the
existing Product Application Spine, durable jobs, workspace isolation,
Knowledge Gateway and exact locators. Its bounded normative denominator is the
official PP No. 87 edition/amendment chain and the official SPDS family manifest
needed for PD/RD applicability. It does not authorize recursive acquisition of
unrelated NTD, a real OKS, CAD/Drawing Intelligence or external VLM routing.

Current implementation and acquisition status is recorded in
[INDUSTRIAL-DOCUMENT-UNDERSTANDING-01](../implementation/INDUSTRIAL_DOCUMENT_UNDERSTANDING_01.md).

## Subsequent streams

1. Industrial Intake scale and Project Understanding;
2. applicable official NTD, RuleVersion and work-type coverage;
3. Tender professional outputs R1/R2;
4. Support production ID/control/output chain;
5. Audit full operator report workflow;
6. Restoration dedicated non-fabricating workflow;
7. Drawing/CAD/output R3 and field/offline;
8. operations/scale and Trial Readiness;
9. four ModeReady decisions and product acceptance.

Each stream updates the same registry and cannot remove a denominator.

The Field/Offline stream includes the separately registered
[`FIELD-ANDROID-CLIENT-01`](../implementation/FIELD_ANDROID_CLIENT_01.md)
capability ([issue #24](https://github.com/yamazaki1711/asd-kontur/issues/24)).
It remains `NOT_IMPLEMENTED`; an approved threat model and comparative device,
MDM, security, offline-sync and delivery decisions precede any Android project.
Its absence blocks Support/Audit/Restoration field acceptance and final
`ProductReady`, but does not expand the current Industrial Document Understanding
slice.
