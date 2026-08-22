# ASD-KONTUR Contract Schemas v0.1

Status: **Accepted architecture baseline**

Owner: Oleg Shcherbakov

Decision date: 2026-08-22

This directory is the minimum machine-readable kernel of the G-03 Contract Pack.
It is normative for contract boundaries, not an application implementation and
not a transport API.

## Layout

- `registry.json` — contract registry, family passports, schema identities and
  compatibility rules;
- `schemas/` — JSON Schema Draft 2020-12 resources with stable URN identifiers;
- `fixtures/manifest.json` — fixture-to-schema mapping and expected outcome;
- `fixtures/valid/` — anonymized positive examples;
- `fixtures/invalid/` — schema-negative and semantic-negative examples.

The authoritative human-readable semantics are in
[`CONTRACT_PACK_v0.1.md`](../../docs/architecture/CONTRACT_PACK_v0.1.md).
The JSON Schemas intentionally do not encode transport, database or provider
choices.

## Resolution and validation

Resolve `$ref` by exact `$id`; no network retrieval is required or permitted.
The namespace `urn:asd-kontur:contracts:v0.1:*` is an identifier namespace, not
a claim that a schema registry service is deployed.

Each fixture manifest entry identifies an exact schema fragment. `schema`
negative cases must be rejected by Draft 2020-12 validation. `semantic`
negative cases are contract-test vectors for invariants that require comparing
multiple records, policy state or authoritative canonical state.

Persisted messages and results pin exact contract and schema versions. The
mutable token `latest` is forbidden. Digests prove byte equality; they do not
grant access or establish logical identity.
