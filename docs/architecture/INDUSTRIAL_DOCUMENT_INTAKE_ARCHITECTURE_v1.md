# Industrial Document Intake Architecture v1

## Pipeline

`folder/batch admission → streamed hash → MIME/signature validation → archive`
`inventory → deduplication → object registration → PDF/page inventory → native`
`extraction → OCR only where needed → bounded VLM route → Candidate → validators`
`→ quarantine/publication → reconciliation`.

Each file/page/shard has stable workspace identity, SourceVersion, digest,
attempts and terminal outcome. Native/deterministic processing precedes AI.
Overlap is context only and never creates duplicate logical results. Partial or
all-request failure cannot become ready or empty success.

## Durable execution

Admission and processing are PostgreSQL-backed jobs with outbox/inbox, leases,
backpressure, idempotency and restart recovery. The object plane receives bytes
before publication; transaction failure leaves no visible partial document.
Quarantined content is excluded from ordinary retrieval.

## Scale profiles

Profiles `intake.scale-1k`, `intake.scale-5k` and `intake.scale-10k` specify
exact representative corpus, memory/thermal/disk envelopes, throughput,
failure injection, restart and reconciliation acceptance. All are currently
`CONTRACT_ONLY`; no scale claim is accepted from a small fixture.
