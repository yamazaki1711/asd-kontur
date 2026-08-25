# Technical Architecture v1

## Component boundaries

`frontend` communicates only with versioned HTTP/OpenAPI commands and queries.
The Python Application Plane maps authenticated workspace context to domain
ports. Domain packages stay framework-neutral. PostgreSQL enforces canonical
transactions, RLS, idempotency, outbox/inbox and durable-job leases. Immutable
object bytes are addressed by SHA-256 and referenced by the Source/Evidence
Ledger.

Long operations are admitted as `DurableJob`: queued → leased → running, with
explicit pause/cancel/retry and terminal success/failure/reconciliation.
Attempts are immutable. A dead worker may lose a lease but cannot convert
partial output to success. Progress is reconstructible after restart and
streamed by SSE; polling remains a recovery path.

## Frontend and viewers

The target is React/TypeScript built by Vite. TanStack Query holds server cache;
view state stays local and complex workflow state may use an explicit state
machine. PDF.js renders pages behind a project-owned virtualized viewer with
page/region overlays and native/OCR layers. OpenSeadragon is the raster-tile
candidate for very large sheets. CAD/native geometry is provided through typed
deterministic adapters, never browser or VLM authority.

## API and security

Preferred API candidate is FastAPI because it fits the typed Python kernel and
OpenAPI generation; it must pass the Product Application Spine qualification.
Clients are generated from a pinned OpenAPI artifact. Opaque server-side
sessions use Secure/HttpOnly/SameSite cookies, CSRF protection and rotation;
OIDC is an adapter for multi-user deployment. Authorization, workspace scope
and RLS are checked server-side on every operation.

## Model boundary

All substantial AI/VLM calls receive an automatically assembled EvidencePack.
The model has no SQL/object credentials. A dedicated broker and PostgreSQL
lease enforce one heavy MLX process; every attempt records model/profile,
prompt/schema/validator versions and digests. Qwen3.8-27B is the primary local
model; BF16 is required for numeric-critical drawing candidates. Canonical
memory and deterministic results do not depend on model/provider.

## Quality and operations

Structured content-minimal telemetry is OpenTelemetry-compatible. Logs exclude
project content, prompts, secrets and raw model responses. Signed immutable
releases have compatibility checks, staged activation and rollback. No
mandatory Docker runtime is introduced. Exact choices and qualifications are
recorded in [ADR-0014](decisions/0014-product-application-technology-baseline.md).
