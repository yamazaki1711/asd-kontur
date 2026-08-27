# INDUSTRIAL-DOCUMENT-UNDERSTANDING-01 implementation record

- Status: `IN PROGRESS — bounded architecture and synthetic vertical slice`
- Base: `81961379366a42475367c42652bef9d0dbf27d7d`
- Contract Pack: `2.3.0`
- Readiness: `TrialReady=false`, `OKSReady=false`, `ProductReady=false`

The branch implements the source-first workspace pipeline and extends the one
existing NTD Authority for PD/RD applicability. It does not claim normative or
industrial acceptance. The exact-25 seed remediation now has official bytes for
15 identities. Deterministic exact-source replay has published 1,293 native
provisions from four exact editions; a bounded external-recovery canary has
published one raster provision from a fifth edition. One Practice↔NTD alignment
is available through the Knowledge Gateway and Product Spine UI. Edition
activation/applicability is not yet qualified and no operational RuleVersion
exists. PP No. 87 and the wider SPDS corpus remain separate unresolved
acquisition gaps described below.

## Current NTD seed remediation checkpoint

This section supersedes the earlier acquisition snapshot in this implementation
record without changing any historical decision or receipt.

- Recovery denominator: 130 artifacts excluding six unrelated/misclassified
  files; 104 unique legacy NTD byte objects are physically materialized on the
  MBP. The immutable recovery v0.9 semantic fingerprint is
  `sha256:8b01dd99f17c8240d6d51b7a3a29bb14dfabc70a649040fe000144778339a00d`;
  the content-addressed staging fingerprint is
  `sha256:d1d0fdc1f61fcb3d2a078860236877cfee9f30cf4735e576c5a7b6d0088e57d5`.
- Twelve recovered GESN artifacts remain
  `NORMATIVE_COST_ESTIMATION_AUTHORITY_CANDIDATE`; they are not published into
  the SP/GOST/order/instruction authority layer. Six unrelated files remain
  excluded.
- The exact guide denominator remains 37 mentions and 25 stable identities with
  logical fingerprint
  `sha256:071960850be497aa6cff032a64375f9cacacadc9fed1a36b136fddfb862ca4b6`.
  Current canonical state is 25 registered identities, 22 resolved official
  records and 15 official artifacts. The fifteenth artifact is the recovered
  SP 70.13330.2012 whose bytes exactly match the Minstroy artifact digest; the
  original 14 Minstroy artifacts were not downloaded again.
- Page inventory is 1,638/1,638: 551 native-complete and 1,087 routed to bounded
  external recovery. Native extraction produced 1,576 structural fragments and
  1,350 provision candidates. The original import recorded all 1,350 as
  `insufficient` because its verifier used an unconditional document-wide
  pending gate. That historical outcome is preserved. Deterministic exact-source
  replay now additionally supports 1,293 independent native provisions from
  four documents. It verifies only candidates whose exact SourceVersion,
  edition, locator, verbatim source fragment and terminal page outcome are
  complete; it does not require unrelated raster pages to finish. One external
  candidate from `СП 71.13330.2017` passed the same local verification contract,
  bringing the published total to 1,294 provisions across five editions. One
  exact Practice↔NTD alignment is published with `edition_warning`;
  qualified/active rules remain zero.
  The 57 native candidates not replayed remain explicitly blocked: 56 by
  `NTD_NATIVE_SOURCE_PAGE_NOT_TERMINAL` and one by
  `NTD_NATIVE_ARTIFACT_NOT_SUPPORTED`.
- The bounded Polza qualification produced five successful candidate receipts
  for representative full-page/crop calls and published the one verified raster
  provision above. Confirmed successful-call usage is 5.35571402 RUB with zero
  retries. The production batch profile did not qualify: one attempted full
  page has outcome-unknown `POLZA_TIMEOUT`, another returned
  `POLZA_REGION_INVALID`, and a targeted text-region diagnostic also timed out.
  The 817 never-attempted queued jobs were therefore terminally cancelled with
  `POLZA_BATCH_PROFILE_NOT_QUALIFIED`; one duplicate page-version job remains
  `reconciliation_required`. No mass 1,087-page run was performed and no failed
  call was converted into an empty successful extraction. Provider-reported cost
  for the timeout/schema-failure calls is unavailable, so it is not guessed.
- Ten identities have no official bytes. Seven have exact Rosstandart cards:
  five viewer manifests are empty and two return the same invalid access
  placeholder instead of the declared pages. The remaining exact blockers are
  `И 1.13-07`, the base `СП 129.13330.2019`, and `СП 42-101-2003` after bounded
  Minstroy enumeration. The printed `ГОСТ Р 58973` remains edition-ambiguous and
  is not silently bound to 2020.
- The current canonical remediation-memory root is
  `sha256:6895f32532d5108363fd61a6bc239ba72ff7a8cf6144c2826868b7f7a06eaafa`.
  Physical PostgreSQL backup/restore into a disposable database reproduced it
  exactly; projection deletion/rebuild reproduced projection identity
  `7d4065fc-48a5-5229-ab32-962c99034d19` and 1,294/1,294 entries. Earlier roots
  remain historical evidence of their bounded pre-publication states.

## Source-first workspace pipeline

Additive migration `0021_document_understanding` stores immutable, workspace-
scoped attempts and derived candidates for format inventory, page health,
native layout, OCR routing/extraction, page/document roles, ProjectDefinition
fields, work types, quantities, materials, estimate positions, source links,
reconciliation defects and projection entries. It extends the existing
PostgreSQL durable queue with these twelve ordered stages:

1. `DOCUMENT_FORMAT_INVENTORY`;
2. `PDF_PAGE_HEALTH_ANALYSIS`;
3. `NATIVE_LAYOUT_EXTRACTION`;
4. `OCR_ROUTING`;
5. `OCR_EXTRACTION`;
6. `DOCUMENT_PAGE_CLASSIFICATION`;
7. `DOCUMENT_AGGREGATION`;
8. `PROJECT_DEFINITION_EXTRACTION`;
9. `WORK_QUANTITY_MATERIAL_EXTRACTION`;
10. `WORK_PACKAGE_ASSEMBLY`;
11. `REQUIREMENT_MATRIX_ASSEMBLY`;
12. `PROJECT_UNDERSTANDING_RECONCILIATION`.

PDF, PNG/JPEG/TIFF, DOCX, XLSX and CSV have declared native/intake boundaries.
Unsupported proprietary CAD and estimate formats return typed gaps. Raw text
and numeric strings remain separate from normalized candidates; exact
SourceVersion and page/region/cell locators are retained. Empty evidence does
not become successful classification. Drawing-derived quantities remain
blocked by `DRAWING_INTELLIGENCE_REQUIRED`.

The browser Project Understanding surface displays extracted fields, work
packages, quantities/materials, the shared WorkRequirementMatrix preview and
gaps. Exact locator links open an Evidence panel and then the workspace source
page. All four modes read that same Matrix; its existence raises their bounded
view from `FOUNDATION_ONLY` to `PARTIAL`, never to `MODE_READY`.

## Official PD/RD normative acquisition

Additive migration `0022_pd_rd_normative_authority` adds provider health
receipts, versioned corpus manifests/members, applicability predicates,
RuleVersion-to-provision evidence and workspace-scoped immutable
`ApplicablePdRdNormativeProfile` rows. It reuses `NormativeDocument`,
`NormativeEdition`, `NormativeArtifact`, SourceVersion, provisions and the Rule
Registry; it does not create a second normative subsystem.

Provider adapters are host allow-listed, TLS-verifying, rate-limited and have
bounded retries for the official [Government portal](https://government.ru/),
[official legal-publication portal](https://publication.pravo.gov.ru/),
[Rosstandart fund](https://protect.gost.ru/) and the existing
[Minstroy catalogue](https://minstroyrf.gov.ru/docs/). A health/access outcome
belongs to one provider and transport profile and cannot block another
provider by inference.

The owner-approved NTD search order is Minstroy first, then
`https://docs.cntd.ru/`, then `https://meganorm.ru/`. Minstroy is checked as an
official authority candidate. CNTD and Meganorm are discovery/reference-only:
they may identify a designation or edition to resolve, but their bytes cannot
be admitted as canonical NTD Authority or qualify a RuleVersion.

The bounded 2026-08-26 health probe produced separate outcomes. Python
`urllib.getproxies()` inherited the configured HTTP/HTTPS proxy at
`127.0.0.1:10809` and SOCKS route at `127.0.0.1:10808`; no credentials were
present or logged. The proxy accepted HTTP CONNECT but did not complete the
upstream TLS handshake. Direct routing remained provider-specific:

| Provider | Direct | configured environment proxy |
|---|---|---|
| Government portal | TCP connect timeout / `OFFICIAL_NETWORK_TIMEOUT` | CONNECT 200 then TLS timeout / `OFFICIAL_PROXY_ROUTE_FAILED` |
| official legal-publication portal | TCP connect timeout / `OFFICIAL_NETWORK_TIMEOUT` | CONNECT 200 then TLS timeout / `OFFICIAL_PROXY_ROUTE_FAILED` |
| Rosstandart fund | HTTP 200, TLS chain verified | CONNECT 200 then TLS timeout / `OFFICIAL_PROXY_ROUTE_FAILED` |
| Minstroy catalogue | HTTP 200, TLS chain verified | CONNECT 200 then TLS timeout / `OFFICIAL_PROXY_ROUTE_FAILED` |

### PP No. 87

The exact stable identifier contract is
`ru:government:resolution:16.02.2008:87`; authority, act kind, date and number
are mandatory. `ПП 87` is rejected as ambiguous. Minstroy was searched first
using the exact designation and title: four bounded HTTP-200 search responses
returned no exact record. CNTD and Meganorm expose discovery copies and an
amendment list, but are not official authority bytes. The official consolidated
record remains identified at
[government.ru/docs/all/63014](https://government.ru/docs/all/63014/), but both
direct TCP and configured-proxy TLS acquisition are blocked in this MBP
network environment. Consequently:

- official artifacts acquired: **0**;
- immutable materialized editions: **0**;
- verified provisions: **0**;
- qualified rules: **0**;
- amendment/current/as-of chain: `OFFICIAL_ACCESS_BLOCKED` and unresolved.

The URL is discovery evidence only. It is not a SourceVersion or authority text.

### Official SPDS manifest

The exact official Rosstandart search for “Система проектной документации для
строительства” reconciled **109** distinct catalog records. The search manifest
fingerprint is
`sha256:29785779c5fd311a6ce5b6e4937fcf865f6f51e0b43c0633fdbdde5a7fdea7d5`;
the all-card metadata manifest fingerprint is
`sha256:62c62a25d8a092214c5ebc6f8a7b03297792387131e940a0ac9771d12008019a`.

| Official catalog state | Count |
|---|---:|
| active | 54 |
| replaced | 37 |
| cancelled | 8 |
| not effective in the Russian Federation | 10 |
| unknown | 0 |
| **denominator** | **109** |

The former ten `unknown` rows all carried the exact official status «Утратил
силу в РФ» and now resolve to the separate terminal catalog state
`not_effective_in_rf`. Effective dates were parsed for 109, replacement targets
for 37, replaced designations for 42, and official scope metadata for 101.
Metadata-only rows are quarantined from provision and rule publication.

The priority gate was executed, not inferred: exact Minstroy searches for each
of the 54 active SPDS designations returned `no_exact_result` for all 54. The
resolver therefore proceeded to the official Rosstandart fund per identity;
Minstroy press/news material was not treated as the bytes of a standard.

Two mandatory identities are resolved at catalog level:

| Identity | Official catalog ID | Card digest | Page-view manifest |
|---|---|---|---|
| ГОСТ Р 21.001-2021 | `88e90567-2700-420a-92fe-d23d8a7bb2ee` | `sha256:943dad512527a770d6fe01f6d82370997d6d2167ef12984497d3f34597d3a61b` | 8 page identities; semantic `sha256:64f22aef4199638c6e088aa8f1882a4ae6b8aed07363a6f3e34beef9d295f51b` |
| ГОСТ Р 21.101-2026 | `17bc12e8-6579-4145-b141-56855e772e7f` | `sha256:462821e803293c879cc85afa203a7635abcf5cfb95ddd9fb5460b7ee255c2138` | 70 page identities; semantic `sha256:f3aea2947663d4fbd363f181ee1e9bfba5ed9f46df892d911edf27995b70d5bf` |

The protected official viewer was not bypassed. All 54 active records received
an individual bounded viewer outcome:

| Active artifact outcome | Documents | Declared page identities |
|---|---:|---:|
| `authentication_required` | 48 | 1,250 |
| `official_artifact_unavailable` (valid JSON, empty page list) | 6 | 0 |
| acquired official content | 0 | 0 |

For the 48 records, pages 1 and 2 returned the same 1,802,234-byte PNG access
placeholder (`sha256:e3a0159f7880cfaaa86820693af818b40db4b4230b641e1585cdfd26449e7057`),
declared as `image/jpeg`, with geometry `1536x1024` instead of the page-manifest
geometry. Strict PNG decoding, CRCs, stream length and absence of trailing
payload all pass. The MIME mismatch is therefore retained as a validation
observation; authentication is proven by repeated placeholder bytes and page
geometry mismatch. Placeholder bytes are not a `NormativeArtifact`.

The six exact `official_artifact_unavailable` identities are ГОСТ 21.201-2011,
ГОСТ 21.205-2016, ГОСТ 21.513-2024, ГОСТ Р 21.1709-2001,
ГОСТ Р 21.514-2025 and ГОСТ Р 21.706-2024. Registered official source
artifacts, exact editions and verified provisions therefore remain zero. The
109-record denominator is reproducible official metadata, not proof that the
contents have been acquired.

## Applicability, rules and Gateway

The version-pinned profile accepts verified ProjectDefinition dimensions and
returns proven requirements, unresolved inputs, exact provision/rule traces and
corpus denominator/gaps. Knowledge Gateway v2.3 has typed operations for PD
sections, section contents, applicable SPDS profile, expected RD marks/sets,
completeness, exact/as-of edition, explanation and normative gaps.

One canonical deterministic evaluator is shared by the document worker and the
Gateway-facing profile service. The exact SPDS manifest denominator is stored in
the immutable profile, included in its semantic fingerprint and shown in the UI;
different row order cannot change the result, while a denominator change must.

Publication fails closed unless the full chain exists:

`RuleVersion → verified NormativeProvisionVersion → NormativeEdition`
`→ official SourceVersion → exact locator`.

Synthetic integration evidence proves this architectural chain, RLS, exact pin
and deterministic response shape only. It is not official normative content.
The PP No. 87/SPDS profile subset in this separate acquisition scope remains
empty. Matrix therefore retains its PD/RD profile and Rule coverage gaps and
cannot be complete. This does not erase the bounded exact-25 provision subset.

## Qualification evidence and open gates

- Python/PostgreSQL suite: **469 passed**, with no skips/deselects/xfails; one
  upstream FastAPI/Starlette deprecation warning remains visible.
- Browser E2E: **2 passed** against a fresh migrated PostgreSQL database. The
  live journey admits a two-page PDF and VOR CSV, survives a killed worker,
  reaches exact workspace evidence, shows four `PARTIAL` mode views and resets
  workspace A without changing B. It also proves that the Platform Knowledge UI
  exposes the exact-25 denominator and immutable logical manifest fingerprint.
- Metadata-only registration is idempotent and does not publish provisions.
- A live disposable clone of the current NTD database passed a targeted browser
  E2E showing 534 provisions for the selected native edition, the one
  Practice↔NTD alignment, the exact `7.1.13` page-23 evidence locator, the
  separately verified raster provision with page-1 evidence and honest
  `not_activated` edition status.
- A fresh Qwen3.8-27B BF16 session received only bounded Gateway packs and passed
  2/2 systemic plus 1/1 adversarial exact-response gates. It preserved the
  Practice/NTD authority distinction, returned an honest unsupported-AOSR gap
  and did not use an unresolved locator. Model digest was
  `sha256:8ab2241982b33afd5ab176cc4e5069afee866323a8fcc52df6345149b3f0d766`.
  The accepted session digest is
  `sha256:a506c24e76fbb7d44d52d4f0019a79e6bdc1fb2e357cd2a13533bea759ac4883`.

Content-minimal control-plane profiles were generated outside Git. Every input
created the exact 17-stage durable graph; a two-worker restart boundary
terminalized two jobs and left every remaining job durably queued. These are
measurements with `threshold_status=UNSET_MEASURED_ONLY`, not semantic or scale
readiness:

| Files accepted/rejected | durable rows / missing | admission | first registry page | peak RSS |
|---:|---:|---:|---:|---:|
| 1,000 / 0 | 17,000 / 0 | 16.765 s | 0.0922 s | 166.8 MiB |
| 5,000 / 0 | 85,000 / 0 | 103.394 s | 0.0064 s | 167.2 MiB |
| 10,000 / 0 | 170,000 / 0 | 151.260 s | 0.0059 s | 167.3 MiB |

A bounded local OCR comparison used five generated Russian construction pages
(ordinary text, table, stamp, low contrast and 90° rotation) outside Git.
Language correction was disabled for Apple Vision; Tesseract used `rus+eng` and
TSV coordinates. Mean measurements were:

| Adapter | CER | WER | numeric/symbol/unit exact | mean/page | peak RSS on normal page |
|---|---:|---:|---:|---:|---:|
| Apple Vision accurate | 0.1527 | 0.3105 | 0.7639 | 0.458 s | 297.0 MiB |
| Tesseract 5.5.3 | 0.3369 | 0.9007 | 0.5091 | 0.127 s | 68.8 MiB |

Apple Vision is the bounded upright-page primary candidate and Tesseract the
fallback candidate, matching the implemented routing order. Both failed the
rotated-page numeric gate (Apple exact-token score 0.60; Tesseract 0.00), so the
OCR qualification is **not accepted** until rotation normalization and the full
mixed born-digital/scan corpus pass. All returned boxes were normalized and
bounded, but exact ground-truth bbox fidelity remains unqualified.

The following mandatory terminal gates are not satisfied: a qualified external
batch profile and remaining 1,086-page recovery, exact official bytes for ten
identities, full-document page completion/publication, official PP No. 87
bytes/amendment chain, official SPDS artifacts/provisions, authoritative edition
activation and independent human rule approval, accepted OCR qualification,
three clean-room semantic cycles and accepted
scale/semantic corpus results. No commit, PR or merge is permitted as a PASS
while these remain.

## Rule Activation Vertical Slice checkpoint

The pre-existing Rule Registry supplied immutable RuleVersion, evidence,
review, approval and activation lifecycle tables, a fail-closed declarative
runtime and three-person human separation for review/approval. The NTD layer
already supplied verified provision lineage, applicability predicates,
edition-activation decisions and Practice↔NTD alignment. The missing contract
was an evidence-bound pre-RuleVersion `RuleCandidate`, deterministic
qualification gates, an explicit activation outcome and a Gateway/UI join over
those layers.

Migration `0024_rule_activation_vertical` adds immutable canonical relations
for candidates, qualification decisions and activation outcomes. Candidate
identity is derived from exact document, edition, SourceVersion, provision,
locator, verbatim digest and interpreted semantics. Essential semantic fields
must each quote text present verbatim in the source. Qualification verifies the
provision state, edition, SourceVersion, locator, exact text, deontic evidence,
applicability contract and pinned test manifest. Qualification does not review,
approve or activate a rule.

The versioned selection manifest
`contracts/v2.3/fixtures/valid/rule-activation-vertical-slice.json` selected four
heterogeneous verified provisions without branching in domain code:

| Edition / provision | Semantics | Canonical outcome |
|---|---|---|
| СП 347.1325800.2017, 10.8 | direct prohibition | qualified; RuleVersion `candidate`; not activated |
| СП 361.1325800.2017, 9.2.2.6 | numeric prohibition, 1.5 m | qualified; RuleVersion `candidate`; not activated |
| СП 361.1325800.2017, 7.1.4 | conditional report-content obligation | qualified; RuleVersion `candidate`; not activated |
| СП 543.1325800.2024, 7.1.13 | documentation obligation and existing Practice alignment | qualified; RuleVersion `candidate`; not activated |

Counts are **4 candidates / 4 qualified / 0 active**. All four compiled
RuleVersions are evidence-attached and in lifecycle `candidate`. Their stable
activation reason is `NORMATIVE_EDITION_NOT_ACTIVATED`: no official
`NormativeActivationDecision` is present. The implementation deliberately did
not fabricate edition authority or independent human reviewers. A disposable
browser clone used the service author plus distinct synthetic human reviewer
and approver identities and a synthetic edition decision to prove the separate
active path; that state was destroyed after E2E and never entered canonical
memory.

The existing СП 543 clause 7.1.13 alignment remains one exact Practice↔NTD
alignment. Gateway evidence packs now expose candidate semantics, qualification
gates, activation status/reason, RuleVersion lifecycle, exact edition,
SourceVersion, locator and verbatim evidence. The Product Spine renders both
`qualified → not_activated` and, in disposable acceptance,
`qualified → active`, including the reason and exact source page/region.

Rule candidate, qualification and activation fingerprints are included in both
the NTD remediation root and the permanent platform-memory inventory. The new
NTD root is
`sha256:d82e4c4016516476b1c16fcf0f8b87bed4d0d496f3fcedf77e53dbb53a4b1402`;
the platform-memory fingerprint is
`sha256:645f00d196fb1ad0bbd1e86df676d8865ee337ea7cde04a0dc10c4e6067b03d0`.
Physical dump/restore reproduced both fingerprints. Backup manifest semantic
fingerprint is
`sha256:55ca21c1c8dd3aa7fdf6bb1c402813452d62fef02bcc7de5c545f7350b9b6ec7`;
projection delete/rebuild reproduced 1,294 entries under projection
`d05923ae-5c72-5ad3-a916-8bdac5afc38f`.

Quality evidence: 469 Python/PostgreSQL tests pass; strict mypy covers 170
source files; Ruff and `uv lock --check` pass; migration clean install and
0024→0023→0024 round-trip pass; frontend format/typecheck/lint, 3 component
tests and production build pass; versioned OpenAPI and generated TypeScript
client regenerate byte-identically; live Playwright proves exact evidence,
qualified/non-active and disposable active outcomes. The stage remains
**PARTIAL** because canonical active count is zero and the independent official
edition/human activation gates are intentionally unresolved. `TrialReady`,
`OKSReady` and `ProductReady` remain false.

## Separate field-client debt

[`FIELD-ANDROID-CLIENT-01`](FIELD_ANDROID_CLIENT_01.md) is tracked by
[GitHub issue #24](https://github.com/yamazaki1711/asd-kontur/issues/24) and by
`field.secure-android-client@2.3.0`. Its status is `NOT_IMPLEMENTED`, legacy
decision is `USE_AS_REFERENCE_ONLY`, target implementation is
`REIMPLEMENT_FROM_SEMANTICS`, and authentication architecture is `UNDECIDED`.
No APK code, UI, backend stub or selected Android/MDM/authentication technology
is part of this slice.
