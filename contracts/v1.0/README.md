# G-06 lifecycle contract release v1.0

This immutable, deliberately narrow release supersedes only
`lifecycle.destruction-attestation@0.1.0`. The accepted v0.1 Contract Pack
remains unchanged for every other contract.

The major version is required because G-06 needs two persisted distinctions
that v0.1 cannot represent without a breaking change:

- assurance class `development/disposable` versus `production`;
- terminal outcome `quarantined` in addition to verified/incomplete/failed.

The schema is Draft 2020-12, uses a stable URN, is resolved locally, rejects
unknown fields, and contains only the RD-03 content-free allowlist.
