# SYSTEM-INTEGRITY-CYCLE-01

**Status:** qualification candidate  
**Owner:** Oleg Shcherbakov  
**Date:** 2026-08-25  
**ProductReady:** `false`

## Purpose and boundary

This verification increment qualifies the integrity and reproducibility of the
implemented ASD-KONTUR kernel on an anonymized multi-work fixture. It does not
run a real OKS, field acceptance, TM-35, NTD acquisition, Drawing Intelligence,
G-07B, or any legacy-computer recovery.

PASS requires three complete consecutive clean-room cycles. A failure creates
an immutable typed receipt outside Git, resets the consecutive count to zero,
and requires a universal root-cause correction plus regression coverage before
a new series starts.

The authoritative readiness inventory for the qualification candidate is the
[Module Readiness Manifest](../../contracts/v1.9/fixtures/valid/module-readiness-manifest.json).
`PARTIAL`, `BLOCKED`, `CONTRACT_ONLY`, and `NOT_IMPLEMENTED` entries remain
visible and do not become ready merely because a module imports or has a table.

## Reproducible runner

`asd_kontur.integrity.runner` implements phases A–J and launches every cycle in
a fresh application process. Each cycle uses:

- a clean schema and separate disposable PostgreSQL databases;
- an exact external NTD-era platform-memory backup, migrated from `0016` to
  current head `0017`;
- exact Practice Guide source-byte verification;
- independent Workspace A/B/C identities;
- the same three-work `ProjectDefinition → ConstructionWorkPackage →
  WorkRequirementMatrix` fixture for Tender, Support, Audit, and Restoration;
- deterministic Gateway/ContextPack checks plus one isolated Qwen3.8-27B BF16
  structural smoke at temperature zero;
- controlled fault injection, backup/restore, physical projection deletion and
  rebuild, a full no-skip pytest suite, and resource reconciliation.

The runner accepts all environment paths explicitly. It does not contain a PDF,
database dump, source text, raw prompt/response, credential, or object-plane
artifact. Full logs and receipts are written with restrictive permissions to an
owner-selected directory outside Git. Repository artifacts are limited to the
runner, schemas, anonymized fixtures, deterministic validators, and this
content-minimal protocol.

## Fingerprint reconciliation

The series gate compares code, lock, schema, Contract Pack, platform semantic,
backup/restore, projection, fixture, WorkRequirementMatrix, four-mode output,
ContextPack, readiness-manifest, and model structural fingerprints. Timestamps,
process IDs, database names, durations, and permitted environment observations
are receipt metadata and are excluded from semantic fingerprints.

The semantic schema fingerprint includes column names/types/defaults/nullability,
constraints, indexes, functions, triggers, RLS flags and policies. PostgreSQL's
internal `attnum`/`information_schema.ordinal_position` is deliberately excluded:
after a valid drop/add round trip PostgreSQL retains a physical dropped-column
slot, although the addressable schema is identical. A regression test compares
the complete semantic inventory before and after the destructive disposable
round trip.

Expected historical partial states are invariants, not failures:

- KG-ID-01 remains `PARTIAL`, with historical acceptance 24/25 systemic and
  7/7 adversarial;
- NTD-SEED-01 remains `PARTIAL`, with 25 `official_access_blocked` gaps and no
  verified official edition or provision;
- Guidance/NTD candidates are never promoted automatically to RuleVersion.

The final three-cycle result is recorded outside Git before PR creation and is
reported with exact cycle IDs and fingerprints. This bounded integrity PASS, if
obtained, does not imply product or field readiness.
