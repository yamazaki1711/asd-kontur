# NTD-SEED-01 — bounded official NTD platform memory v0.1

**Status:** PARTIAL — official endpoint access blocked, all seed identities terminal
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

Manifest fingerprint:
`sha256:071960850be497aa6cff032a64375f9cacacadc9fed1a36b136fddfb862ca4b6`.
The 25 exact stable identities are:

1. `ru:minstroy:order:344-pr` — Приказ Минстроя № 344/пр;
2. `ru:minstroy:order:1026-pr` — Приказ Минстроя № 1026/пр;
3. `ru:sp:543.1325800` — СП 543.1325800.2024;
4. `ru:sp:68.13330` — СП 68.13330.2017;
5. `ru:gost-r:51872` — ГОСТ Р 51872-2024;
6. `ru:sp:70.13330` — СП 70.13330.2012;
7. `ru:sp:48.13330` — СП 48.13330.2019;
8. `ru:sp:45.13330` — СП 45.13330.2017;
9. `ru:sp:71.13330` — СП 71.13330.2017;
10. `ru:instruction:1.13-07` — И 1.13-07;
11. `ru:sp:77.13330` — СП 77.13330.2016;
12. `ru:sp:73.13330` — СП 73.13330.2016;
13. `ru:sp:347.1325800` — СП 347.1325800.2017;
14. `ru:sp:129.13330` — СП 129.13330.2019;
15. `ru:sp:74.13330` — СП 74.13330.2023;
16. `ru:sp:392.1325800` — СП 392.1325800.2018;
17. `ru:sp:341.1325800` — СП 341.1325800.2017;
18. `ru:sp:361.1325800` — СП 361.1325800.2017;
19. `ru:sp:42-101` — СП 42-101-2003;
20. `ru:gost:32755` — ГОСТ 32755-2014;
21. `ru:gost:32756` — ГОСТ 32756-2014;
22. `ru:gost-r:59492` — ГОСТ Р 59492-2021;
23. `ru:gost-r:70108` — ГОСТ Р 70108-2025;
24. `ru:gost-r:58973` — ГОСТ Р 58973, printed year absent;
25. `ru:gost:31937` — ГОСТ 31937-2024.

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

## Bounded official resolution result

The official-only client made exactly one sequential request per stable
identity (`concurrency=1`, one attempt, eight-second timeout) against the
allowlisted Minstroy `/docs/` endpoint. DNS resolved, but every TLS connection
timed out in the execution environment. Search snippets and third-party copies
were not accepted and the batch was not retried.

| Outcome | Identities | Published editions | Artifacts | Verified provisions |
| --- | ---: | ---: | ---: | ---: |
| `official_access_blocked` | 25 | 0 | 0 | 0 |

Every identity has an immutable query receipt, terminal outcome and open
`NormativeGap`; all 37 guide mentions have immutable resolution decisions.
There are no catalog IDs, official artifact URLs, edition timelines,
amendment/supersession relationships or practice/NTD alignments to claim from
this run. Report fingerprint:
`sha256:1392964228c5732f69c74026011b554768eacf2cce85a73abbfdac1133302386`.

## Persistence, Gateway and durability evidence

- additive migration `0016_ntd_seed` introduces immutable official acquisition,
  edition relationship, provision candidate/version, activation/applicability,
  guide reference, outcome/gap/conflict, backup and projection contracts;
- application/workspace roles cannot mutate NTD; dedicated ingestion and
  read-only Gateway roles are separate;
- Contract Pack `v1.7` pins exact NTD requests/responses and rejects mutable
  `latest` and verified provision without official evidence;
- Knowledge Gateway returns `knowledge_gap` for all 25 identities and exposes
  the exact guide reference lineage without converting it to normative
  evidence;
- workspace purge deletes its execution records while the platform NTD
  semantic fingerprint remains unchanged;
- PostgreSQL dump/restore reproduced canonical semantic fingerprint
  `sha256:7d1a23d43da874371d3de8e819964d28e96c5cba272132729a8ffa4b06470acd`;
- deletion/rebuild of the empty lexical projection produced the same version
  identity and zero entries, which is correct because no provision is verified;
- the canonical guide SourceVersion object passed byte/digest verification;
- changing the model/provider actor leaves the same Gateway response and
  canonical fingerprint.

## Fresh-session acceptance

One new isolated Qwen3.8-27B BF16 session (`temperature=0`, no PDF or full
source text, no competing heavy process) received only a typed Gateway gap for
СП 543.1325800.2024. Deterministic validation passed: strict JSON, exact guide
edition/SourceVersion/reference locators, `insufficient/knowledge_gap`, and no
fabricated NormativeDocument, NormativeEdition, provision, applicability or
RuleVersion. This is a new NTD non-fabrication decision; it does not modify the
historical KG-ID acceptance.

## Historical boundary

KG-ID-01 remains `PARTIAL` with its immutable historical 24/25 systemic and 7/7
adversarial decision. NTD-SEED-01 may add a new cross-layer acceptance decision,
but never rewrites KG-ID candidates, receipts, publication or acceptance.
`ProductReady=false`.

NTD-SEED-01 therefore remains honestly `PARTIAL`: bounded reconciliation and
fail-closed permanent-memory behavior are implemented, but zero official
editions can be published until the official endpoint is reachable and exact
records/artifacts are acquired in a new immutable attempt.
