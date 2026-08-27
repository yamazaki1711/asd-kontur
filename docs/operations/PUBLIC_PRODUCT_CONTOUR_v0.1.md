# Public Product Contour v0.1

## Domain map

| Surface | Active responsibility |
| --- | --- |
| `asd-kontur.ru` | static public company website |
| `app.asd-kontur.ru` | Product Application frontend, API, SSE and PDF responses |
| `bi.asd-kontur.ru` | isolated Levashovo BI and archived intake-control UI |
| `tm.asd-kontur.ru` | independent TM-35 pilot; no changes in this deployment |

The public website must not link to object BI/pilot surfaces. The Product
Application must not read a Levashovo/TM-35 database or object store.

## Authority topology

The MBP remains the only authoritative primary. PostgreSQL, Knowledge Gateway,
workspace facts, durable jobs, package/finalization state and object bytes stay
on the MBP. The VPS terminates TLS, serves the static website and proxies the
single-origin application traffic over a supervised ingress channel. No domain
database or object-plane replica is created on the VPS.

## Runtime identities

- `ru.asd-kontur.spine.api`: FastAPI + built React frontend;
- `ru.asd-kontur.spine.worker`: durable document/generation worker;
- deployment ingress identity: recorded only after the VPS route is active;
- migration head: `0027_public_deployment`.

Launchd configuration is generated outside Git with
`asd-kontur-spine render-launchd`. It pins database roles, object roots, build
digests, exact source commit and migration head. The generated files are
deployment artifacts, not repository source.

## Cutover invariants

1. Capture exact legacy nginx source, upstream, process and database binding.
2. Create the archival branch in the repository that actually owns the legacy
   application; never import its object data or dumps.
3. Prove the `bi` subpath before removing the root legacy route.
4. Prove `app` login/API/SSE/PDF Range through TLS before linking the website.
5. Deploy the website, then verify forbidden legacy markers are absent.
6. Keep exact previous nginx configuration and service identity as rollback
   target.
7. Do not change `tm.asd-kontur.ru`.

## Failure behaviour

If the MBP or ingress is unavailable, `app.asd-kontur.ru` returns a typed 503
surface. Nginx must not fall back to the legacy application or synthetic static
API responses. The company website remains independently available.

## Acceptance command

External browser acceptance uses the separately configured Playwright profile:

```text
npm --prefix frontend run e2e:external
```

It requires explicit website/application URLs, demo credentials and the pinned
finalized PDF digest in runtime environment. It does not start or substitute a
localhost server.
