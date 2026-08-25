# ADR-0014: Product Application technology baseline

- Status: Accepted with qualification gates
- Owner: Oleg Shcherbakov
- Date researched: 2026-08-26
- Scope: target architecture, not implementation or dependency approval

## Drivers

The application is local-first, processes thousands of files and large PDF/CAD
artifacts, supports offline field work, strict typing, evidence navigation,
workspace isolation and crash recovery, and must remain maintainable by one
owner. The mandatory MBP runtime may not depend on Docker or an external cloud.
The domain harness remains independent of every UI/provider choice. One heavy
MLX process is allowed at a time.

## Comparative decisions

| Concern | Candidates considered | Decision and reason | Gate / rejected assumption |
|---|---|---|---|
| Frontend | React/TypeScript SPA/PWA; Vue/TypeScript SPA/PWA; Jinja2+HTMX server-driven | **React + TypeScript SPA/PWA**. Its component ecosystem fits synchronized PDF/CAD panes, virtualized matrices and offline states. Vue is credible but offers no measured project advantage. HTMX remains a control/admin option, not the primary workbench. | No React Server Components or SSR by default; prove any need. Legacy Jinja/HTMX routes are reference semantics only. |
| Build | Vite client build; Next integrated build; Nuxt integrated build | **Vite**. It produces a static client bundle with a narrow tool boundary and does not impose a second server runtime. Integrated metaframeworks add SSR/server conventions not justified for this desktop-like local app. | Pin and supply-chain review in Product Application Spine; frontend static assets served by the Python application. |
| Application API | FastAPI; Litestar; Django REST Framework | **FastAPI as the preferred implementation candidate**, selected for fit with the existing typed Python kernel and direct OpenAPI generation, not legacy precedent. Litestar remains a benchmark; DRF carries a larger ORM/application framework than needed. | Final dependency/version acceptance occurs in Spine with auth, upload streaming and OpenAPI conformance characterization. Domain code never imports the web framework. |
| API protocols | REST/OpenAPI; GraphQL; gRPC | **REST/OpenAPI for commands and queries**, plus SSE for durable progress. WebSocket is reserved for proven bidirectional latency needs. GraphQL/gRPC would add client/server and browser complexity without a current domain benefit. | No endpoint may expose direct SQL or bypass command/auth/workspace boundaries. |
| Typed client | OpenAPI Generator `typescript-fetch`; openapi-typescript/openapi-fetch; handwritten client | **Generated client from the pinned OpenAPI artifact**; qualify both generators on unions, UUID/date handling and runtime validation before choosing the tool. Handwritten domain clients are rejected. | CI fails on generated diff or contract incompatibility. Runtime responses remain schema-validated. |
| Durable jobs | PostgreSQL queue with outbox/inbox, leases and `SKIP LOCKED`; Temporal; Celery + broker | **PostgreSQL-backed durable jobs** inside the modular monolith. The canonical DB already exists and can provide atomic admission, lease, idempotency and reconciliation. Temporal is an escalation option for measured cross-service workflow complexity; Celery adds a broker and has retry semantics that still require product idempotency. | Load/crash qualification at 1k/5k/10k; no in-memory authoritative queue. |
| PDF workbench | PDF.js custom viewer; MuPDF/WASM; server-side raster-only viewer | **PDF.js rendering engine with an ASD-KONTUR viewer layer** for exact locators, overlays, synchronized navigation, native/OCR text and page virtualization. MuPDF requires separate license/security evaluation. Raster-only loses native structure. | Characterize large-document memory, rotations, crop boxes and locator round trips. Do not embed the stock viewer unchanged. |
| Large drawing view | OpenSeadragon tile pyramid; custom Canvas/WebGL; full CAD browser engine | **OpenSeadragon for large raster/tiled drawings**, with project-owned evidence overlays. Vector/CAD interaction is a separate adapter contract. | Prove tile generation, coordinate transforms and 10k-page/large-sheet navigation. A viewer is not geometric authority. |
| CAD | Python `ezdxf`; LibreDWG/ODA-class translators; model-generated geometry | **Deterministic native/DXF adapter boundary; qualify `ezdxf` first** because it is typed, MIT and supports large-file iteration, while documenting its rendering/3D limitations. DWG translators require license/format qualification. Model-generated numbers are candidates only. | Representative CAD corpus, license provenance and geometry round-trip tests precede selection. BF16 is the numeric-critical VLM profile, never final geometry authority. |
| Server state | TanStack Query; RTK Query; custom Redux store | **TanStack Query for server state**; local React state for view state; XState only for genuinely complex UI workflows. Do not mirror canonical domain state into a browser store. | Offline mutations use an explicit sync ledger, not cache persistence masquerading as authority. |
| Offline field | PWA + Service Worker + IndexedDB; native Android/iOS; Capacitor hybrid | **PWA first, hybrid escalation gate**. It maximizes reuse and local deployment while Service Worker/IndexedDB enable bounded offline queues. Capacitor is preferred if camera/filesystem/background constraints fail PWA acceptance. Existing Android code is prototype/reference, not selected client. | Device, background sync, large media, secure storage and conflict tests decide escalation. |
| Authentication/session | server-side opaque session cookie; OIDC Authorization Code; browser-held bearer/JWT | **Opaque server-side sessions** for the single-owner/local deployment, Secure/HttpOnly/SameSite cookies, CSRF protection and session rotation. Add an OIDC adapter for multi-user/remote deployment. Browser storage bearer tokens are rejected. | Authorization and workspace RLS remain server-side; king25 access uses the protected network and the same session/API boundary. |
| Observability | structured local logs/metrics; OpenTelemetry; full external monitoring stack | **Structured content-minimal logs plus OpenTelemetry-compatible traces/metrics**, export optional. A mandatory external backend is rejected. | Never emit project text, prompts, secrets or evidence payloads; test correlation and redaction. |
| macOS runtime | launchd-managed modular-monolith services; packaged native wrapper; Docker/VM | **launchd-managed API, document worker and model broker**, with static web client. A signed wrapper may later install/observe services. Docker is optional development tooling, never required runtime. | Qualification covers restart, permissions, local-network privacy, logs, backups and uninstall. Packaging tool chosen after signed-bundle spike. |
| Model orchestration | application spawns MLX; dedicated local broker with DB lease; external workflow scheduler | **Dedicated model broker with a PostgreSQL lease/fence and process-group cleanup**. It enforces one heavy MLX process and immutable attempts while preserving provider neutrality. | App cannot spawn an ungoverned heavy model. Crash/thermal/cancel/reconciliation tests required. |
| Update/rollback | signed immutable release manifest; Sparkle app updater; package-manager/manual install | **Signed immutable release bundles with staged activation and retained rollback**, borrowing TUF rollback/freeze protections. Sparkle becomes eligible only if a native app wrapper is accepted. | Never self-update from an unsigned branch/artifact; DB compatibility, backup and rollback drill are release gates. |

## Primary-source evidence

The comparison uses official project/specification documentation, observed on
2026-08-26:

- frontend/build: [React](https://react.dev/learn),
  [Vue TypeScript](https://vuejs.org/guide/typescript/overview),
  [htmx](https://htmx.org/docs/), [Vite](https://vite.dev/guide/),
  [Nuxt](https://nuxt.com/docs/4.x/getting-started/installation);
- API/client: [FastAPI OpenAPI](https://fastapi.tiangolo.com/tutorial/first-steps/),
  [Litestar OpenAPI](https://docs.litestar.dev/main/usage/openapi/index.html),
  [Django REST Framework](https://www.django-rest-framework.org/),
  [OpenAPI Specification](https://spec.openapis.org/oas/latest.html),
  [OpenAPI Generator TypeScript Fetch](https://openapi-generator.tech/docs/generators/typescript-fetch/);
- jobs/events: [PostgreSQL locking and `SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html),
  [Temporal workflows](https://docs.temporal.io/workflows),
  [Celery tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html),
  [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events);
- documents/CAD: [PDF.js API](https://mozilla.github.io/pdf.js/api/),
  [PDF.js examples](https://mozilla.github.io/pdf.js/examples/),
  [OpenSeadragon](https://openseadragon.github.io/),
  [ezdxf](https://ezdxf.readthedocs.io/en/stable/),
  [ezdxf drawing limitations](https://ezdxf.readthedocs.io/en/stable/addons/drawing.html);
- state/offline: [TanStack Query](https://tanstack.com/query/latest/docs/framework/react/overview),
  [RTK Query](https://redux-toolkit.js.org/rtk-query/overview),
  [XState](https://stately.ai/docs),
  [PWA](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps),
  [Service Worker](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API),
  [IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API),
  [Capacitor](https://capacitorjs.com/docs);
- security/operations: [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
  [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0-18.html),
  [OpenTelemetry](https://opentelemetry.io/docs/what-is-opentelemetry/),
  [Apple Service Management](https://developer.apple.com/documentation/servicemanagement),
  [Apple launchd](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html),
  [Sparkle security](https://sparkle-project.org/documentation/),
  [The Update Framework](https://theupdateframework.io/docs/overview/),
  [MLX](https://github.com/ml-explore/mlx).

## Consequences

No code is copied from mac_asd by this ADR. Product Application Spine may
introduce the selected packages only after pinning, license/security review,
characterization and E2E acceptance. The Domain/Knowledge Harness remains a
Python package behind typed application ports and Knowledge Gateway.
