# KG-ID-01 ID Practice Guide Knowledge Ingestion v0.1

**Status:** `PARTIAL` (2026-08-25). Extraction, bounded recovery, reconciliation,
permanent publication, restore and projection-rebuild gates are complete, but
fresh-session Knowledge Gateway acceptance finished at 24/25 systemic and 7/7
adversarial scenarios. The fixed threshold was not met. **ProductReady:**
`false`.

## 1. Scope and authority boundary

KG-ID-01 implements native-first, evidence-backed construction of permanent,
model-independent ID Practice Intelligence from the primary methodological
practice guide. Pass A/B are bounded extraction/verification instruments, not
a qualification corpus, benchmark or product objective. The source type is
`MethodologicalPracticeGuide`; its authority layer is
`methodological_practice`. It is neither NTD, legislation, a customer
regulation, a workspace document, an active `RuleVersion`, nor evidence of an
OKS fact.

The immutable boundary is:

```text
local Qwen ProviderExecutionResult
→ GuidanceCandidateVersion
→ deterministic validation
→ independent Qwen verification
→ qualified human publication decision
→ canonical typed ID Practice Intelligence
→ deterministic Context Assembly
→ Knowledge Gateway
→ any authorized VLM
```

Qwen cannot publish, activate a rule, resolve a normative conflict, confirm a
workspace fact, or broaden applicability. Potential rule material remains a
candidate for the existing Promotion/Rule Gate.

## 2. Exact source provenance

The verified source was copied with ordinary OpenSSH from
`ms-7e26:/home/oleg/Desktop/Пособие по ИД.pdf` to an external, non-Git staging
area. Remote and staged bytes are identical:

- SHA-256:
  `469b9fbe001cc87de5235f14615875b5adc11cdeea041f0d7733f5ed32fa297c`;
- size: `19,044,364` bytes;
- MIME: `application/pdf`;
- PDF: version 1.7, OnlyOffice 9.4 creator metadata, unencrypted;
- physical page count: `425`.

The pre-existing local library copy has SHA-256
`f1bc2a2be9a3c912779299854cc3d6d406babe85784ea247971ab0ba825e2dd9`
and was rejected because it is not byte-identical to the verified Desktop
source. Neither PDF is stored in Git.

Exact acquisition paths, both digests, source metadata, the custody outcome and
the PageManifest digest are retained in the local immutable edition provenance.
Git contains only the digest and safe source classification needed to review
the implementation.

## 3. Native-first PageManifest and renders

The deterministic PageManifest has exactly 425 ordered, one-based rows and
records page-content digest, box, rotation, native-text character count, image
count, technical composition, render requirement and previous/next lineage.
Observed technical composition is:

- 422 mixed text/image pages;
- 1 raster-only page;
- 1 native-text-only page;
- 1 blank/technical page;
- 424 pages requiring a render;
- 8 rotated pages;
- 92 deterministic `possible_form_or_template_example` flags;
- 107 deterministic `possible_diagram` flags.

These flags are preflight candidates, not semantic conclusions. Every page
needed for visual semantics is rendered independently at the pinned 144 DPI
Poppler profile and shown to Qwen together with exact native text. The PDF is
never sent as one prompt. Renders, job manifests and raw model receipts stay in
external restricted staging and are excluded from Git.

## 4. Exact Qwen profile and qualification

The original full-pass local profile is:

- provider: `local.mlx`;
- model: `Qwen3.8-27B`;
- cached model revision:
  `241ebb5f1d60b122fd653da658836a55feb9e2b0`;
- immutable component-manifest digest:
  `sha256:a8c3cb163bef0c5b87812b4ce2d8ce2b6b497cb7daeb9f2e0f4f6ebb58c7cc41`;
- quantization: exact 8-bit profile; no 4-bit model;
- runtime: MLX 0.32.1, mlx-vlm 0.6.15, transformers 5.15.1;
- deterministic decoding (`temperature=0`);
- Poppler 26.08.0, 144 DPI;
- schema/contract: 1.5.0.

The first stratified qualification used physical PDF pages 1, 23, 84, 110,
211, 362 and 425, covering raster, mixed, native-text, form/table/visual and
technical content. The first bounded output exposed truncation and an internal
printed-page/PDF-page mismatch; both failed closed. A targeted retry of page
211 and a targeted Pass-B retry repaired only affected attempts. The qualified
development evidence reconciled 34/34 original Pass-B jobs with no remaining
integrity error. It does not qualify production inference, BF16, another model
revision, another prompt, or another runtime.

The bounded page-batched Pass-B prompt was separately qualified before the full
verification pass. Batch transport does not make evaluation page-atomic: every
syntactically valid disposition is reconciled independently by exact
CandidateVersion identity. Unknown and duplicate IDs are typed failures and
are never matched heuristically; malformed JSON is never repaired.

After PID 48212 disappeared, the stale
`deferred_existing_heavy_metal_session` decision was explicitly superseded.
The exact BF16 recovery profile (`Qwen3.8-27B-bf16`, model digest
`sha256:8ab2241982b33afd5ab176cc4e5069afee866323a8fcc52df6345149b3f0d766`)
qualified 5/5 known integrity failures at `temperature=0`. The reopened
manifest contains 129 exact CandidateVersion identities, fingerprint
`sha256:2015f08c881773844d7dd78753681ac8adda216238fc29cfbd6027f366884b6a`.
One sequential BF16 process produced 129/129 first-attempt strict-JSON
receipts; deterministic validation yielded 55 supported, 57 contradicted and
17 insufficient outcomes, with no model failure. A second bounded queue
reverified only 18 native-row candidates whose earlier response integrity had
failed, yielding 17 supported and one deterministic insufficient outcome.

## 5. Two-pass processing and reconciliation

Pass A receives one exact page image and its native text and emits strict typed
JSON only. Markdown fences, malformed/truncated JSON, printed-page substitution,
out-of-scope locators, no-content/candidate contradictions and unknown kinds are
typed failures. The deterministic middle layer checks schema, source/page
scope, normalized region bounds, native-text grounding, form/field consistency,
duplicates and provider integrity.

Pass B is an independent prompt over the same exact page plus CandidateVersion
and deterministic failure codes. Its terminal candidate outcomes are
`supported`, `contradicted`, `insufficient` or `model_failed`. A correction
creates immutable CandidateVersion `n+1` with parent lineage and a blocking
revalidation requirement; it is not silently accepted in the same response.
One invalid disposition or correction cannot discard valid siblings. A page
receipt records `complete`, `partial`, `unresolved` or `model_failed`, while a
page-level `no_content=true` cannot erase an existing CandidateVersion.

The measured full Pass A has 419 valid page results and six typed failures
(pages 16, 17, 111, 269, 380 and 394). The measured full Pass B completed all
419 eligible page jobs. Candidate-granular salvage of only the seven integrity
pages accepted 15 exact dispositions (10 newly recovered beyond the earlier
page-atomic evaluation) and left 23 exact CandidateVersion identities for
targeted verification. These are intermediate recovery facts, not a completion
claim.

Pages 16-17 use a dedicated native-first continued-table recovery. Poppler PDF
layout supplies deterministic word/line boxes; page 15 is context for the same
table, not another document. The three printed columns are reconstructed into
22 independent `GuideSourceRow` records. Qwen receives one complete source row
at a time for `GuideNtdRelevanceAssertion` semantics and never receives or
returns coordinates. Exact printed NTD identifiers and titles remain source
fields. A canonical NTD link can be appended only after exact designation and
edition resolution; absent or ambiguous editions remain an explicit
`NormativeReferenceCandidate` uncertainty.

The exact resolver is a separate deterministic stage pinned to an explicit
`as_of_date`. It neither normalizes the printed designation nor retains a
partial document-only link when edition resolution fails. The immutable result
is `resolved`, `not_found` or `ambiguous`; inference cannot choose or repair an
edition.

Pages 111, 269, 380 and 394 all passed the native-layout sufficiency classifier.
Their five invalid locator candidates were re-located by deterministic source
phrase alignment and created as CandidateVersion `v2` with exact parent
lineage; no bbox clamping or VLM region recovery was used. Page 380 contains
non-text control glyphs for visual icons, recorded explicitly while preserving
the usable native text geometry.

Every physical page must finish with exactly one terminal receipt: `verified`,
`partial_with_gaps`, `no_methodological_content`, `unresolved`,
`insufficient_evidence`, `model_failed` or `technically_blocked`.
`expected_pages=425` is reconciled against exact receipt identities; partial or
failed processing cannot become `complete` or `ok_empty`. Checkpoint/resume
skips completed jobs, retains immutable attempt receipts and uses targeted
candidate manifests only.

Final reconciliation version 2 accounts for all 425 pages and 2,891 immutable
CandidateVersions. Candidate terminal counts are: 2,463 supported, 124
contradicted, 277 insufficient, 27 superseded and zero model-failed. Page
terminal counts are: 281 verified, 109 partial-with-gaps, 20
no-methodological-content and 15 insufficient-evidence; model-failed,
technically-blocked and unresolved are all zero. The 15 fully insufficient
pages and gaps on 109 partial pages are evidence limitations, not
inference/process failures. Reconciliation
fingerprint:
`sha256:8afdaf4c2be412432cc32f9ee9e12d4fcab967956e3746bdbebb35d93f83c90a`.

## 6. Platform physical model

Alembic revision `0009_kg_id` follows `0008_wp14` and extends the platform
source kind allowlist with `methodological_practice_guide`. It adds physically
platform-scoped, immutable relations for:

- PracticeGuide, edition, structural units and PageManifest;
- exact local model/execution profile and ingestion run state history;
- CandidateVersion, deterministic failures and Qwen verification receipts;
- deterministic GuideSourceRow geometry, NTD relevance assertions, exact
  printed reference candidates and separate edition-resolution receipts;
- per-page terminal receipts and ingestion reconciliation;
- canonical guidance units, EvidenceLinks, conflicts and uncertainties;
- immutable CoverageManifest, searchable GuidanceGap and recovery lineage;
- rebuildable Russian FTS projection versions and entries.

No relation in this family contains `workspace_id`. Canonical guidance evidence
points to the platform `SourceVersion` and exact `page:N:region:…` locator. The
original PDF is retained in a provider-neutral local platform object-store
adapter outside Git. A workspace reset has no deletion target capable of
reaching the guide, its source version, guidance units or platform projection
definition.

The non-owner `asd_guidance_ingestion_service` and
`asd_guidance_gateway_service` roles have narrow platform/projection/audit
grants. Candidate, verification, receipt, reconciliation, publication,
conflict and uncertainty records are append-only. Canonical publication needs
an explicit qualified human `methodological_practice.publish` capability;
conflict recording has a separate human capability.

Additive revisions `0010`–`0015` preserve the published `0009` history and add
candidate-granular recovery compatibility, typed Practice Intelligence,
permanent-memory releases/backup contracts, immutable edition activation,
versioned superseding verification/page/reconciliation decisions and the
complete typed playbook member-role set. A repeated SourceVersion resolves to
the same edition; changed bytes create a retained new edition. There is no
mutable `latest`: release, backup and Gateway runtime bind an exact activation
decision and edition.

Revision `0015` preserves pre-ADR `methodological_guidance` rows as immutable
legacy provenance, but permits and requires every new source-guidance
publication to use `methodological_practice`. Runtime Context Packs and the
active Practice Intelligence release expose only the accepted authority layer.

`persist-verified-guidance` consumes only the final bounded reconciliation
artifacts: CoverageManifest, GuidanceGap register and publication manifest with
exact verification lineage. It does not reread the original page-atomic Pass A
or Pass B outputs to make publication decisions. Thus an original supported
version that was superseded, a corrected version without its own supported
verification, or a quarantined conflict cannot enter authoritative retrieval.

The permanent source bytes reside outside Git in the platform object plane
with mode `0600`; its byte digest equals the exact SourceVersion digest. The
canonical edition, selected verification lineage, guidance, intelligence,
playbooks, gaps, conflicts, policy and releases reside in the PostgreSQL
`platform` schema. Exact/FTS/vector/sparse/typed-graph state is a rebuildable
`projection` plane. The immutable backup manifest pins the object digest,
edition activation, CoverageManifest, construction, policy and semantic
fingerprints. A real `pg_dump` restore into a disposable database reproduced
revision `0015_practice_authority`, the edition, 7,113 active units, 1,644
active playbooks, 395 active-version gaps, conflict count 138 and the same
semantic fingerprint. The external backup digest is
`sha256:d1a2da32e87c50118fd27667403b4b4851697872c53c4c0293be86c916cb3b71`.
The disposable restore database was removed after verification. Deleting all
8,757 FTS entries and rebuilding from canonical rows reproduced the same count
and fingerprint.

## 7. Knowledge Gateway

Contract Pack v1.5 retains the immutable source-guidance extraction contracts.
The additive v1.6 Practice Intelligence contract keeps the original tools and
adds exact, allowlisted task/playbook retrieval:

- `knowledge.get_id_guidance`;
- `knowledge.get_form_guidance`;
- `knowledge.get_field_guidance`;
- `knowledge.trace_guidance`;
- `knowledge.explain_guidance_conflict`;
- `knowledge.get_id_task_guidance`;
- `knowledge.get_practice_playbook`.

Every successful response carries `authority_layer=methodological_practice`,
the exact source version and page-region EvidencePack. Missing query/index,
missing guidance, an unavailable projection and an unknown conflict return
typed gaps/statuses rather than empty success. The model receives no SQL and
the external-provider boundary receives no Gateway capability. Exact/FTS
retrieval is implemented; no vector qualification claim is made.

Publication of source assertions is not the completion condition. Verified
source guidance must be transformed into versioned principles, workflow steps,
form/field completion instructions, attention points, allowed variants,
rationale, common failure patterns, verification/completeness/journal
checklists, document dependencies, signer guidance, visual examples and
playbooks. Each unit retains exact SourceVersion/page/region, fragment digest,
applicability, relations, printed NTD candidates, uncertainty/conflict and
construction lineage.

Every ID-related operation must run a pinned deterministic
`ContextAssemblyPolicy` before VLM execution. The selected
`IDPracticeContextPack` separates normative requirements, practice advice,
workspace facts and missing information. `knowledge_incomplete`,
`guidance_normative_conflict` and `edition_mismatch` are terminal typed
retrieval outcomes, not empty context.

CoverageManifest version 2 published 2,410 non-quarantined canonical guidance
units and retained 395 searchable gaps. Fifty-three supported candidate
identities participating in 138 directed conflict records are quarantined and
excluded from ordinary practice retrieval. Deterministic construction produced
7,113 typed intelligence units and 1,644 playbooks; the exact/FTS plane contains
8,757 rebuildable entries. Canonical semantic fingerprint:
`sha256:a7164aa7488c29fbc9cc6e84387add243e519c0e6fb6a9cf199bc33e5bedac43`.

## 8. Independent-session memory acceptance

After canonical publication, a new Qwen process is loaded without the PDF,
page images or book text. A local trusted layer discovers and traces at least 25
distinct canonical guidance units only through the Knowledge Gateway, then
passes the resulting minimized EvidencePacks to Qwen. Each answer must use the
methodological authority layer, contain an exact allowed page-region citation
and remain grounded in the retrieved instruction.

Additional adversarial tasks cover an invented field, absent guidance/page,
visual example promoted to a norm, unsupported NTD conflict resolution,
missing evidence and attempted RuleVersion activation. Invented citations,
authority escalation or a positive answer without evidence fail the gate.

The historical independent-session run produced 28/28 terminal receipts but
only 7/25 systemic and 3/3 adversarial passes: 15 responses had integrity
failures and three systemic tasks were not answered. Those receipts remain
immutable evidence. Universal fixes then bounded response size, tightened the
schema and parser, refreshed deterministic grounding terms, and preserved the
same expected-answer and threshold contracts.

A new stateless BF16 session (`temperature=0`) completed all 28 original jobs.
It reached 21/25 systemic and 3/3 original adversarial passes. Exactly four
systemic identities remained invalid: journal selection, failure detection,
field-level instructions and preflight checking. One final bounded session ran
only those four identities plus four newly required adversarial identities
(invented field, absent page, cross-workspace knowledge and quarantined
conflict). It completed 8/8 terminal receipts with no competing heavy process
and a safe initial thermal reading.

The merged final evaluation covers 32 exact tasks and finished at **24/25
systemic and 7/7 adversarial**. `practice-intelligence-12-failure_detection`
returned `insufficient` after its one permitted targeted retry and failed the
unchanged deterministic contract with `SYSTEMIC_TASK_NOT_ANSWERED`. Its exact
edition, SourceVersion, selected intelligence/playbook identities and two page
regions remain in the terminal receipt. No third retry is permitted. The final
evaluation fingerprint is
`sha256:630eb9538d415c4c2649d116c2bd1223a79f001f86fc290d31950c4e2617ce1f`.
Accordingly memory acceptance is **failed** and KG-ID-01 is `PARTIAL`, while
the verified subset remains available as explicitly incomplete platform
knowledge.

## 9. Lifecycle and product impact

The platform guide can support Support document generation/checking, Audit
Document/Package Readiness, future Restoration planning and the common ID
Generation field/evidence pipeline. It cannot supply missing OKS facts or cure
missing original evidence. Customer regulations remain workspace sources and
cannot modify the book, NTD or platform rules.

KG-ID-01 does not qualify production model execution, embeddings, BF16,
external providers, print-ready templates, professional ID decisions, G-07B,
G-02B, WP-15 or ProductReady.

## 10. Verification and gate self-check

The implementation gate requires lock, Ruff, strict mypy, full unit/contract
and PostgreSQL tests, clean `0001→0015`, disposable downgrade/upgrade, non-owner
role evidence, workspace/reset survival, Markdown/link/whitespace checks and
publication-safety scans. Test count is supporting evidence only.

KG-ID-01 can become `PASS` only after:

1. all 425 pages have exact terminal receipts;
2. real local Qwen processed text and required visuals in Pass A and Pass B;
3. supported, deterministically valid source knowledge was constructed into
   canonical typed Practice Intelligence and published to the permanent local
   platform instance;
4. mandatory Context Assembly and Gateway serve source-pinned packs
   independently of VLM/provider, survive workspace reset and restore, and
   expose gaps/conflicts/edition mismatches;
5. a fresh VLM session passed at least 25 scenario-based exact-citation tasks
   and the adversarial boundary suite;
6. canonical CI passed without publishing source content.

Items 1–4 are proven locally. Item 5 is measured but failed at 24/25 systemic
with the complete adversarial suite at 7/7; canonical CI for item 6 is recorded
on the pull request rather than predicted here. The acceptance failure already
makes the honest terminal project status `PARTIAL`, not `PASS` or
`PASS WITH EXPLICIT COVERAGE GAPS`.

## 11. ADR-0011 architecture/code gap analysis

Observed at checkpoint `6c0a56e`:

- permanent source/edition, page/candidate receipts, verified guidance,
  conflicts/gaps and lexical projection contracts already exist;
- bounded recovery and final reconciliation are complete, and Practice
  Intelligence construction code/migration is present as an uncommitted
  implementation delta;
- current physical/contract terminology still uses
  `methodological_guidance`, not accepted `methodological_practice`;
- lifecycle has platform/workspace isolation but no explicit
  `permanent_platform_core` retention classification or whole-platform-only
  decommission guard;
- Gateway retrieval exists, but mandatory deterministic Context Assembly is
  not yet enforced for every ID-related invocation;
- backup/restore manifests do not yet pin guide object SHA-256, canonical
  intelligence semantic fingerprints and `ContextAssemblyPolicy` together;
- rebuildable projection recovery and provider-independent EvidencePack
  equality are not yet proven by acceptance tests;
- fresh-session scenario acceptance is measured at 24/25 systemic and 7/7
  adversarial after the bounded retry; its single remaining terminal blocker
  prevents closure even though publication is durable and usable with gaps.

The additive implementation is complete and retains all immutable extraction
and acceptance evidence without rewriting published migration history. The
remaining blocker is the terminal fresh-session failure-detection scenario;
`ProductReady` remains `false`.
