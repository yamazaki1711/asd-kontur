# Tender participation decision — delivery slice 01

This is one user-result slice of the full four-mode ASD-KONTUR programme, not a
readiness claim. The existing project model can contain a source-linked initial
contract price, but it has no authority to infer the bidder's qualifications,
viable cost, contract tolerance or ability to meet tender conditions. The prior
application therefore could not issue an evidence-bounded participation
recommendation.

The Tender screen now distinguishes source-derived project price from explicit
workspace-scoped Contractor assessment. An immutable assessment version records
profile fit, contract acceptability, feasibility, minimum viable RUB price and
the reviewer's confirmation that price bases are comparable. The four early
negative gates are profile mismatch, unacceptable contract, impossible
conditions and documented price ceiling below confirmed minimum viable price.
Missing inputs yield `INSUFFICIENT_INPUT`, not a neutral or favorable score.
Open professional issues or incomplete project analysis prevent an
unconditional positive recommendation. The editable primary Tender report
states the current decision and missing information in Russian.

The assessment is isolated by workspace RLS, authenticated owner scope and
append-only versions. A database trigger locks and checks the lifecycle row
before accepting a new assessment, preventing a late submission after reset
fences the workspace. The table is registered in the controlled workspace
purge. No global NTD or Practice data is written.

Qualification uses changed-value decision tests, an isolated PostgreSQL API
test for workspace isolation and idempotent replay, and a rendered DOCX sample.
The real owner workspace was inspected read-only: its structured commercial
facts yield one source-linked price ceiling, while project materialization is
partial. No company facts were inserted into that workspace. A complete Tender
participation decision still requires actual bidder profile/cost inputs and a
professional review of contract and site conditions. The other three modes and
the full product remain below ready.

## Controlled public release — 2026-10-07

Code SHA `0a440f5677be00c11954b5125366bf9853fa41ab` is pinned at
`~/.asd-kontur/public-demo/releases/20261007-0a440f5-tender-participation-v1`.
The four supervised application roles run from that release at migration
`0132_tender_participation_assessments`; the Qwen and NTD services were not
restarted. The public API returned `ready`, the frontend returned HTTP 200 and
the unauthenticated new decision endpoint returned HTTP 401.

Before migration, a real public backup was created at
`~/.asd-kontur/public-demo/backups/20261007-pre-0132-tender-participation.dump`
with SHA-256 `33bbc41bc3d8e4f716bdcad991c8eabf7a5aa662412f88e8f87290570c890c3d`.
It restored separately into the disposable database
`asd_integrity_tender0132_20261007`. Upgrade, downgrade and re-upgrade passed
there before the public migration. The platform-memory fingerprint remained
`sha256:e79b8886a5983b42d9c89427b82425702292869805e44fc40184114dfcee0126`
through restore, migration and public release. NTD documents/editions/semantic
rows remained 15/15/1,669; inspected embedding, graph-edge and search-document
counts remained 0/0/0.

The pinned code read the owner workspace without mutation. Its structured
commercial facts yielded an established price with four source locators; no
contractor assessment exists, so the effective recommendation is
`INSUFFICIENT_INPUT`. An authenticated browser form submission on the owner's
project has not been performed because there are no owner-supplied bidder facts
to submit. Isolated PostgreSQL API acceptance covered submission and replay;
the sample DOCX was rendered to PDF and its new first-page decision section was
visually checked. This does not establish full Tender readiness or ProductReady.
