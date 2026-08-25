# NTD-SEED-01 — bounded official NTD platform memory v0.1

**Status:** IN PROGRESS  
**Owner:** Олег Щербаков  
**Date:** 2026-08-25  
**Base:** canonical `main` `a807a783c5b7c84270cd6caf22c70f00783fe7c1`

## Scope and invariants

This implementation admits only the 25 stable identities discovered on exact
PDF pages 15–19 of the canonical ID Practice Guide edition. The guide supplies
discovery evidence, not normative authority. Official content is accepted only
from exact Minstroy catalogue records and artifacts; unavailable or ambiguous
content terminates as a typed gap. No recursive expansion is permitted.

The implementation extends the existing G-05 platform source/evidence ledger
and normative canon. It does not create a parallel knowledge subsystem. Source
bytes and raw acquisition receipts remain outside Git in the platform object
plane. PostgreSQL stores canonical identities, immutable editions, relations,
verified provisions, gaps/conflicts and explicit activation/applicability
decisions. Retrieval projections remain rebuildable.

## Deterministic seed reconciliation

Native Poppler word/line geometry, with no OCR or VLM, produced:

| PDF page | Printed page | Mention count | Method |
| --- | --- | ---: | --- |
| 15 | 14 | 2 | native block geometry |
| 16 | 15 | 11 | native three-column row geometry |
| 17 | 16 | 11 | native three-column row geometry |
| 18 | 17 | 6 | native block geometry |
| 19 | 18 | 7 | native block geometry |

Total: 37 immutable references and 25 deduplicated identities. Repeated
mentions remain separate locators. The exact raw text and contexts are written
only to the external processing ledger; Git records the counts, normalized
identifier set, profile version and manifest fingerprint.

## Gap analysis

- Existing G-05 has `NormativeDocument`, `NormativeEdition`, source versions,
  structural units, assertions, gaps/conflicts and projection tables.
- Missing physical contracts are official catalog query receipts, multiple
  artifacts per edition, typed edition relationships, provision
  candidate/version separation, guide-reference resolution, explicit
  activation/applicability decisions and NTD backup/projection manifests.
- The historical `MinstroyCatalogueClient` supplies useful fail-closed parsing
  evidence but supports only SP identifiers and a legacy mutable-current model.
  It must be modernized into the existing G-05 ledger, not copied as a second
  registry/downloader.
- Knowledge Gateway lacks exact NTD identity/edition/as-of/provision/alignment
  contracts. An additive Contract Pack version is required.

## Historical boundary

KG-ID-01 remains `PARTIAL` with its immutable historical 24/25 systemic and 7/7
adversarial decision. NTD-SEED-01 may add a new cross-layer acceptance decision,
but never rewrites KG-ID candidates, receipts, publication or acceptance.
`ProductReady=false`.

