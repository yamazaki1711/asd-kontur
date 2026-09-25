# SUPPORT-REUSABILITY-03

Status: `CANDIDATE — multi-work-type software qualification; production authority blocked`

## Delivery boundary

This increment generalizes the accepted `concrete.slab.install` vertical without
re-qualifying its official AOSR PDF. It proves that one Support application
boundary can persist, reopen, select, and export packages for materially
different work types and document compositions. It does not approve any work
type, requirement matrix, template, specialist, or execution fact for production.

The selected additional qualification work types already exist in the controlled
construction-harness data:

- `earthworks` — earthworks/excavation category;
- `reinforced-concrete` — reinforced-concrete works;
- `pipeline-installation` — pipeline installation.

They are not represented as production catalog entries. Their requirement
matrices are controlled qualification inputs whose expected compositions are
specified independently of generation. This is why their packages remain
candidate/incomplete and list missing documents instead of fabricating them.

## Bounded reusability audit

| Stage | Class | Result |
|---|---|---|
| admitted source and evidence | A | Existing workspace-scoped intake and evidence locators are reused unchanged. |
| source interpretation | A/B | Existing local-Qwen candidate path is generic; no new inference was required because this increment tests package orchestration from controlled, already structured inputs. |
| Support work scope | A/B | Canonical `work_type_key` and immutable `work_package_id` drive scope; package selection no longer falls back to the most recent workspace package. |
| AOSR field requirements | B/C | Common versioned `support.aosr-field-map@2.0.0` is selected only after the matrix requires `support.aosr`; the former `concrete.slab.install` routing guard was removed. |
| evidence and missing inputs | A | Candidate, confirmed, conflict, missing, and unsupported states retain exact work and source scope. |
| NTD/professional resolution | B/F | Knowledge remains Gateway/catalog/rule data. The three added profiles have no production-approved requirement matrix and remain blocked. |
| document requirements | B | `WorkRequirementMatrix` controls composition; three different controlled compositions are accepted by the same code. |
| rendering | C/F | Qualified AOSR PDF and candidate editable DOCX remain the only qualified/candidate renderer pair. Other roles are explicitly missing/blocked. |
| package/register generation | A | One package engine derives register ordinal 1 and manifest/membership from the selected matrix row. |
| persistence/reload/export | A | Each work package has an independently selectable immutable package history and ZIP export. |
| UI | A | Russian Support UI lists available packages by work scope and downloads the selected package. |
| qualification identities/data | E | Synthetic owner, grants, sources, matrices, and values exist only in disposable acceptance databases. |
| public activation | F | Support writer login/URL, production catalog approval, and real `support.scope.configure` grant remain absent. |

No production source file contains a `concrete.slab.install` branch after this
increment. `support.aosr` branches remain document-family behavior, which is the
intended template boundary rather than work-type routing.

## Application behavior proved independently of OZERO

One authenticated disposable application session forms three packages, selects
each by `work_package_id`, reloads one package, downloads each archive, verifies
the register is first, compares the manifest roles with the independently
specified matrix, and denies a second owner. The tested compositions are:

| Work type | Required body roles |
|---|---|
| `earthworks` | `support.executive-scheme` |
| `reinforced-concrete` | `support.aosr`, `support.material-quality` |
| `pipeline-installation` | `support.aosr`, `support.material-quality`, `support.control-attachment` |

Because the controlled inputs deliberately contain no execution evidence, the
exports contain the editable register plus manifest, consistency, evidence, status,
and blocked-item schedules. They do not contain invented acts, schemes, certificates,
dates, measurements, or signatures. The accepted concrete slab qualification remains
the evidence that a sufficiently supported `support.aosr` member produces the
qualified PDF and editable DOCX candidate through this same engine.

OZERO is not used by this increment.

## Deterministic coverage and release readiness

`GET /api/v1/admin/support-release-readiness?workspace_id=<uuid>` reads current
database authority and repository qualification profiles. It reports separately:

- active canonical work-type denominator;
- verified production catalog entries;
- catalog entries carrying a non-synthetic professional approval reference;
- resolved field and document-requirement profiles;
- qualified template document types;
- package-capable, isolated-qualified, and browser-E2E work types;
- workspace scope gaps;
- Support command-writer configuration and role membership.

The endpoint is authenticated and workspace-scoped. Missing or invalid
`ASD_SUPPORT_COMMAND_DATABASE_URL` never falls back to the application/owner
connection. At application startup the command service is constructed only when
the configured login is a member of `asd_support_service`; otherwise Support scope
commands remain unavailable and readiness reports the exact reason. Migration 0066
grants the application role only the two additional read projections needed to
count canonical work types.

The deterministic provisioning check is:

1. provision the `asd_support_service` login using the established secret-bearing
   operator channel (never Git or command receipts);
2. grant only the existing service role and configure
   `ASD_SUPPORT_COMMAND_DATABASE_URL` in the service manager;
3. restart the candidate application under the controlled release procedure;
4. call the readiness endpoint as an authorized owner;
5. require `command_writer.role_valid=true` and inspect every remaining blocker;
6. do not activate public Support until production catalog approval and a real
   professional scope grant are also present.

## Evidence

- PostgreSQL application qualification:
  `tests/integration/test_support_production_id.py::test_support_package_pipeline_persists_distinct_work_type_compositions`.
- Writer/readiness qualification:
  `tests/integration/test_industrial_document_understanding.py::test_authorized_support_scope_configuration_is_idempotent_and_owner_scoped`.
- Common AOSR mapping tests: `tests/unit/test_support_field_mapping.py`.
- Coverage manifest validation: `tests/unit/test_support_release_readiness.py`.
- Controlled archive directory:
  `/Users/oleg/.asd-kontur/qualification/support-reusability-20260925/`.
- `earthworks.zip`:
  `sha256:d9a56ff63d4c8fb26e50835882429cf899bba642b07a5017ff89e7da22882b5e`.
- `reinforced-concrete.zip`:
  `sha256:998f5623d5834d4a5bc8e214bfdd731b3d4344793cb62b7134517d48c5d5024b`.
- `pipeline-installation.zip`:
  `sha256:d19dbb7261eb0a3619114841d9e199a59d65437131139eca19d87acbd7c6e002`.

## Remaining acceptance

- professional approval of production work-type catalog entries and matrices;
- additional exact, applicable template families for non-AOSR roles;
- isolated browser journeys for the three additional work types;
- a least-privilege production Support writer credential and real specialist grant;
- controlled migration/release activation and public runtime verification;
- broader canonical catalog qualification before Support ModeReady.

`ProductReady=false`.
