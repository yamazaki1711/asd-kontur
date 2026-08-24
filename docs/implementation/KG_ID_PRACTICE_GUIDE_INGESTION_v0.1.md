# KG-ID-01 ID Practice Guide Knowledge Ingestion v0.1

**Status:** `IN PROGRESS`. The gate remains open until real local Qwen
processing and reconciliation cover all 425 source pages, verified guidance is
published to the local platform instance, and a fresh Qwen session passes the
Knowledge Gateway memory acceptance. **ProductReady:** `false`.

## 1. Scope and authority boundary

KG-ID-01 implements native-first, two-pass ingestion of one methodological
practice guide into a permanent platform knowledge layer. The source type is
`MethodologicalPracticeGuide`; its authority layer is
`methodological_guidance`. It is neither NTD, legislation, a customer
regulation, a workspace document, an active `RuleVersion`, nor evidence of an
OKS fact.

The immutable boundary is:

```text
local Qwen ProviderExecutionResult
→ GuidanceCandidateVersion
→ deterministic validation
→ independent Qwen verification
→ qualified human publication decision
→ canonical PracticeGuidanceUnit
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

The local profile is:

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

Final measured Pass-A, Pass-B, CandidateVersion and terminal-page counts will
replace this paragraph only after the real 425-page reconciliation finishes.

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
an explicit qualified human `methodological_guidance.publish` capability;
conflict recording has a separate human capability.

## 7. Knowledge Gateway

Contract Pack v1.5 adds exact, allowlisted tools:

- `knowledge.get_id_guidance`;
- `knowledge.get_form_guidance`;
- `knowledge.get_field_guidance`;
- `knowledge.trace_guidance`;
- `knowledge.explain_guidance_conflict`.

Every successful response carries `authority_layer=methodological_guidance`,
the exact source version and page-region EvidencePack. Missing query/index,
missing guidance, an unavailable projection and an unknown conflict return
typed gaps/statuses rather than empty success. The model receives no SQL and
the external-provider boundary receives no Gateway capability. Exact/FTS
retrieval is implemented; no vector qualification claim is made.

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

Final measured independent-session task counts will replace this paragraph
after the fresh-session run finishes.

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
and PostgreSQL tests, clean `0001→0009`, disposable `0009→0008→0009`, non-owner
role evidence, workspace/reset survival, Markdown/link/whitespace checks and
publication-safety scans. Test count is supporting evidence only.

KG-ID-01 can become `PASS` only after:

1. all 425 pages have exact terminal receipts;
2. real local Qwen processed text and required visuals in Pass A and Pass B;
3. supported, deterministically valid units were published to the permanent
   local platform instance;
4. a fresh Qwen session passed at least 25 exact-citation Gateway tasks and the
   adversarial boundary suite;
5. canonical CI passed without publishing source content.

Until all five are measured, the honest status remains `IN PROGRESS` rather
than a partial success claim.
