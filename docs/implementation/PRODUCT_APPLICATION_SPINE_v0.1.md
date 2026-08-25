# PRODUCT-APPLICATION-SPINE-01 implementation record

- Status: PASS — bounded implementation slice (not Mode/Trial/OKS/Product readiness)
- Base: `79876bf2cec1a4baee8578cc39c73136b198505f`
- Product issue: [#19](https://github.com/yamazaki1711/asd-kontur/issues/19)
- Contract Pack: `2.1.0`
- Readiness: `TrialReady=false`, `OKSReady=false`, `ProductReady=false`

## Result and boundary

The slice adds a real local browser/application path over the existing Domain/Knowledge Harness:
opaque owner sessions, isolated workspaces, streamed document admission, PostgreSQL durable jobs,
document/PDF registry, evidence locators, four honest mode shells, platform-knowledge status, and a
controlled local reset. It neither changes canonical Practice/NTD memory nor invokes Qwen/MLX.
At the time of this historical bounded PASS, `MEMORY_DATA_DEFECT` remained an
explicit platform blocker. Its current state is derived from the latest
immutable platform-memory qualification decision; it is never hardcoded by the
application. MEMORY-INTEGRITY-FIX-01 later superseded that blocker with a PASS
qualification; this historical Spine status is not rewritten.

The frontend is reimplemented from accepted user-journey semantics. No routes, templates,
`app_state`, fallback records, or demo domain data were copied from `mac_asd`.

## Qualified dependencies

| Boundary | Exact selection | Qualification result |
|---|---|---|
| API | FastAPI `0.139.2`, Pydantic `2.13.4`, Uvicorn `0.52.4` | Python 3.12 imports/typechecks; deterministic OpenAPI; multipart streams to a spooled file and then chunked object storage; SSE, lifespan, typed handlers and TestClient exercised. FastAPI is MIT. `0.141.1` was evaluated but rejected because the upstream repository documents an unresolved long-lived-process callable-cache regression across `0.140.0`–`0.141.1`; `0.139.2` is the explicit upstream-recommended workaround until a fixed release is qualified. |
| Passwords/sessions | argon2-cffi `25.1.0` | Argon2id profile: time 3, memory 64 MiB, parallelism 4; only hashes/digests persist. |
| Frontend | React `19.2.8`, TypeScript `5.9.3`, Vite `8.2.2` | Strict typecheck, ESLint, Vitest and static production build. No SSR/RSC/CDN/runtime Node. |
| Server state/navigation | TanStack Query `5.102.3`, React Router `7.18.2` | Canonical state stays on the server; only query/view state is held in the browser. |
| PDF | pdfjs-dist `6.2.108` | Local bundled worker, custom navigation/text/overlay layer, normalized locator round-trip tests. Viewer is not CAD/geometric authority. |
| Browser E2E | Playwright `1.62.1` | A contract journey and a live-stack journey cover owner login, A/B creation, multipage PDF.js/evidence navigation, all mode shells, honest knowledge blockers, reset, logout and unauthorized denial. The live journey uses a fresh migrated PostgreSQL database, kills a claimed worker process, waits for lease expiry and drains all five jobs through a new process. Synthetic data only. |

FastAPI evidence was checked on 2026-08-26 against the official
[release list](https://github.com/fastapi/fastapi/releases) and upstream
[callable-cache regression report](https://github.com/fastapi/fastapi/discussions/16020).

### Generated client decision

`openapi-typescript@7.13.0` + `openapi-fetch@0.17.0` was selected over OpenAPI Generator
`typescript-fetch`. Both represent UUID/datetime as strings and preserve enums/nullability from the
same OpenAPI document. The selected pair produced a smaller deterministic checked-in diff, no Java
runtime, and a narrow fetch adapter. SSE remains an explicitly typed bootstrap endpoint because
OpenAPI describes the HTTP handshake, not the event-stream runtime. A handwritten domain client is
not present. CI regenerates OpenAPI and the client and fails on a diff. The selected usage matches
the official [openapi-fetch type-safety contract](https://openapi-ts.dev/openapi-fetch/).

## Security and application flow

Every operation follows authentication → authorization → workspace scope → typed command/query →
application service → persistence/domain port → typed response. Endpoints contain no SQL. The
browser cannot reach PostgreSQL, object storage, Knowledge Gateway, or MLX.

The local profile still requires login. Sessions are opaque server-side records with rotation,
inactivity/absolute expiry, revocation, HttpOnly/SameSite cookies, CSRF on mutations and bounded
login rate limiting. The protected-network profile requires an explicit non-wildcard address and
Secure cookies. Passwords, session tokens, source text and document payloads are excluded from
operational metadata.

## Durable jobs and intake

State machine:

`queued → leased → running → succeeded | failed | cancelled | reconciliation_required`

Claiming uses PostgreSQL `FOR UPDATE SKIP LOCKED`, deterministic priority/creation ordering, a finite
lease, generation fencing, heartbeat and stale-lease reconciliation. A terminal state requires an
immutable receipt. Duplicate document admission is content-addressed and idempotent. Retry is finite;
schema/content failures are not silently retried. Cancellation is observed at safe page boundaries.

Initial kinds are `DOCUMENT_ADMISSION`, `DOCUMENT_HASH`, `PDF_INVENTORY`,
`NATIVE_TEXT_EXTRACTION`, `EVIDENCE_INDEX_UPDATE`, and reset reconciliation contract support. OCR/VLM
is deliberately absent: raster pages receive `OCR_REQUIRED`/`OCR_OR_VLM_REQUIRED`, never empty
success.

Intake distrusts extension, client MIME/path/digest/workspace. It sanitizes names, rejects traversal,
validates content signature, hashes in chunks, enforces per-file/batch limits and commits bytes to the
workspace object plane outside Git. PostgreSQL stores identities, versions, manifests and receipts.

## Lifecycle reset assurance

The browser uses an exact, expiring target challenge. The workflow fences writes, terminalizes
remaining jobs, finalizes the bounded modes with blockers, creates and verifies a streamed portable
archive, then uses the existing lifecycle state machine and storage adapters for immutable reset and
destroy plans, authorization, receipts, residual scans and attestations. Workspace B and platform
fingerprints are compared before/after.

The first deployment has one owner, so this ceremony is explicitly
`development_single_owner_confirmation`; it is not a production independent-person attestation.
Production assurance still requires separately qualified requester/confirmer/executor/verifier
identities under the canonical lifecycle contract.

## API and UI surfaces

The `/api/v1` groups cover session, capabilities, workspaces/lifecycle, documents, jobs/events,
evidence, mode views, platform knowledge and live/ready health. The React shell exposes Workspaces,
Documents, Jobs, Evidence, Work Matrix, Tender, Support, Audit, Restoration, Platform Knowledge and
Operations. Four modes read the same bounded kernel and expose missing capabilities; Restoration is
not presented as implemented.

PDF.js receives authenticated Range responses. Evidence navigation preserves exact SourceVersion,
one-based page, normalized region, source page geometry, extraction method and digest. Missing
evidence remains a visible gap.

## Operational profile

`asd-kontur-spine` supplies owner bootstrap, database preflight/migrate, frontend build, foreground
API/worker, health/status, exact-label stop, bounded log reading and launchd/newsyslog generation.
API, lifecycle, worker and destruction use separate PostgreSQL roles. Loopback is default;
protected-network binding is explicit. Node is a build dependency only. Docker and sudo are not
runtime requirements. The model broker is not started and appears as an unavailable capability
rather than a fallback.

## Synthetic scale qualification

Content-minimal synthetic files were generated in disposable directories outside Git and admitted
to fresh disposable PostgreSQL databases. Each file produced the five initial durable jobs. A
worker-process boundary was crossed, every document identity was enumerated through stable cursor
pagination, and exact job totals were reconciled. These are measurements, not accepted SLA values:

| Profile | Accepted / rejected | Durable jobs / lost | Admission | First registry page | Peak RSS |
|---|---:|---:|---:|---:|---:|
| 1k | 1,000 / 0 | 5,000 / 0 | 4.352 s | 0.0737 s (cold) | 162.5 MiB |
| 5k | 5,000 / 0 | 25,000 / 0 | 19.910 s | 0.0040 s | 163.5 MiB |
| 10k | 10,000 / 0 | 50,000 / 0 | 40.823 s | 0.0072 s | 162.6 MiB |

The first 1k qualification exposed a full-scan registry path (14.9 s). The universal fix added
covering indexes and an active-version/latest-state LATERAL lookup; the final measured results above
are from the corrected path. Numeric acceptance thresholds remain `UNSET`, so `intake.scale-1k`,
`intake.scale-5k` and `intake.scale-10k` remain `PARTIAL`.

## Qualification evidence

- Python: 386 tests passed with PostgreSQL enabled; no skips, deselections or xfails. This includes
  clean migration `0018`, downgrade to `0017`, repeat upgrade/schema fingerprint, RLS/default-deny,
  session/CSRF/rate-limit, duplicate admission, lease fencing, process-loss recovery,
  cancellation/retry exhaustion, lifecycle reset and Contract Pack validation.
- Frontend: strict TypeScript and ESLint pass; 3 Vitest assertions pass; deterministic Vite bundle
  and generated OpenAPI client are stable; two Playwright browser journeys pass, including one
  end-to-end against live FastAPI, PostgreSQL, static assets and restartable worker processes.
- Supply chain: `pip-audit` and `npm audit` report zero known vulnerabilities; dependency-license
  inventory contains no incompatible dependency. The repository's own private-project license is
  not inferred by `licensecheck` and is not treated as third-party dependency evidence.
- Hygiene: JSON/YAML syntax, local Markdown links, whitespace, secrets and forbidden PDF/model/raw
  artifact scans pass. Full synthetic scale receipts remain outside Git.

## Readiness

This slice can establish evidence for individual Product Application capabilities only after its
full gates. It does not make any mode `MODE_READY`; official verified NTD and active RuleVersion
counts remain zero, MEMORY semantic identity remains defective, numeric scale thresholds are UNSET,
and the three product results are not accepted. Consequently:

- `PlatformKernelReady=PARTIAL`;
- `ProductApplicationReady=PARTIAL` (bounded Spine, not complete product application);
- `TrialReady=false`;
- `OKSReady=false`;
- `ProductReady=false`.
