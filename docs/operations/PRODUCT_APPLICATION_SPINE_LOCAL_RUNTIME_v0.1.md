# Product Application Spine local runtime v0.1

Status: bounded single-owner local profile. This profile is not Trial, OKS, Mode, or Product ready.

## Process boundary

The API and document worker are separate supervised processes over one PostgreSQL-backed application
boundary. PostgreSQL is canonical for sessions, workspace scope, documents, jobs and progress; the
workspace object root stores admitted bytes outside Git. Node is required only to build the static
frontend bundle. Qwen/MLX is not started by this slice.

Required environment references:

- `ASD_DATABASE_URL` — `asd_app` connection;
- `ASD_LIFECYCLE_DATABASE_URL` — lifecycle-service connection;
- `ASD_WORKER_DATABASE_URL` — document-worker connection;
- `ASD_DESTRUCTION_DATABASE_URL` — destruction-executor connection;
- `ASD_OBJECT_STORE_ROOT` and `ASD_ARCHIVE_STORE_ROOT` — distinct, pre-created absolute directories;
- `ASD_AUTH_AUDIT_PEPPER` — installation secret of at least 32 characters, supplied outside Git;
- `ASD_FRONTEND_DIST` — absolute path to the built `frontend/dist` directory;
- `ASD_LOG_ROOT` — pre-created absolute directory for content-minimal API/worker logs;
- `ASD_SESSION_PROFILE` — `development_loopback` or `protected_remote`.

The development profile binds only to loopback. A protected-network profile requires an explicit
non-wildcard address and secure session cookies; it does not infer trust from the network.

## Versioned commands

Run from the checked-out release with its locked Python and frontend dependencies:

```text
uv sync --locked --all-groups
asd-kontur-spine database-preflight
asd-kontur-spine migrate
asd-kontur-spine frontend-build
asd-kontur-spine bootstrap-owner --username OWNER --display-name "Owner"
asd-kontur-spine serve-api
asd-kontur-spine run-worker --identity document-worker:local-1
asd-kontur-spine health
asd-kontur-spine stop --service all
asd-kontur-spine logs --service all --lines 100
```

`bootstrap-owner` reads and confirms the password without accepting it on the command line. API and
worker use graceful process termination. Operational logs are content-minimal and must not include
session values, passwords or document text.

`asd-kontur-spine render-launchd --output /absolute/new/directory` emits separate API and worker
property lists plus a `newsyslog` rotation fragment (10 compressed rotations, 10 MiB threshold).
`stop` sends `TERM` only to the exact loaded per-user launchd labels; `logs` performs a bounded read
of the configured content-minimal files. Installation, update and rollback remain an
operator-controlled deployment action; the generator does not invoke `sudo`, install services or
mutate the host automatically. The operator must expose the required environment references to the
per-user launchd service context from an installation-owned secret mechanism; the generated plist
does not serialize database credentials or `ASD_AUTH_AUDIT_PEPPER`.

## Recovery

On worker restart, expired leases are reconciled through PostgreSQL fencing and queued work remains
available. SSE is a resumable notification view, not the source of truth; after event-retention loss
the browser reloads the normal jobs query. Workspace reset uses an exact expiring confirmation,
fences writes, reconciles jobs, creates/verifies an archive and proves platform-memory and peer-
workspace survival.

The first profile has only one human owner. Its destructive confirmation is therefore explicitly
development-level assurance, not independent production authorization or verification.
