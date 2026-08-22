# ASD-KONTUR G-07 Contract Extension v1.1

Status: **Accepted implementation contract extension**

Owner: Oleg Shcherbakov

Date: 2026-08-23

This immutable additive release supplements, and does not mutate, Contract Pack
v0.1 or the v1.0 destruction attestation. It formalizes four records that cross
the G-07 process boundary: rendering lineage, batch manifest, qualification
decision, and raw-artifact retention reference. References to the v0.1 common
schema are resolved from the local repository bundle only; network resolution is
forbidden.

Fixtures under `fixtures/valid` must validate. Fixtures under `fixtures/invalid`
must fail for the reason recorded in `fixtures/manifest.json`. Hostile fields are
rejected by `additionalProperties: false` and never become routing commands.
