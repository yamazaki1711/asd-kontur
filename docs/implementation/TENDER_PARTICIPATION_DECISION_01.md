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

## Quality-gate follow-up release

The first full local Python suite exposed two outdated test expectations for
already-existing contract revision review fields and the project-material
export. It reported 1,487 passed, two failed and two skipped. The expected
contract-review fields and material CSV were added to those tests; the
production behavior was not weakened. A full mypy run exposed a Decimal
special-value exponent typing case in the new decision validator and a variable
name collision in the report renderer. Both were fixed. Repository-wide Ruff
formatting also identified three files; only mechanical formatting changed in
the two pre-existing files.

Follow-up SHA `dcf66131e2980a7d7b2297b3691c194660f49cc6` passed full local
Python acceptance: 1,489 passed, two skipped, one dependency deprecation
warning. Full mypy, Ruff format/lint and frontend format/typecheck/lint/unit
checks also passed. GitHub Actions does not trigger for this feature branch;
no exact-SHA hosted CI result is claimed.

The follow-up release is pinned at
`~/.asd-kontur/public-demo/releases/20261007-dcf6613-tender-participation-gate-v2`
on the same migration 0132. During launchd cutover, bootstrap initially
returned error 5 because the prior orchestrator was still in `SIGTERMed` and
retained its label. The API, worker and assistant worker restarted; after the
orchestrator exited cleanly, it bootstrapped from the pinned v2 release. All
four process command paths and staged/installed plists were verified against
the exact SHA. The API is ready, Qwen and NTD remained running, and the
platform-memory fingerprint is unchanged. No project job was running at either
cutover boundary. This incident shows the release procedure must wait for
launchd label removal before attempting bootstrap.

## Contractor cost build-up checkpoint (7 October 2026)

Release `199a6b15c54697f087e407a2706299d3f5915852` adds optional,
workspace-scoped contractor cost lines to the participation assessment. Each
line records a category, described resource/work, quantity, unit, RUB unit
rate, and human-supplied basis. Decimal code calculates each amount and the
subtotal. A contractor-entered required-profit amount yields a minimum viable
price only after the contractor explicitly confirms that the cost scope is
complete. A partial schedule remains visible but cannot trigger the
price-below-cost gate; conflicting manual and calculated minimum prices are
rejected. The existing separate confirmation of comparable VAT/scope/price
bases remains required. No market rates, quantities, company fit, or profit
were inferred from the owner's project.

The Tender screen now accepts and reopens these inputs, displays the
calculation, and the editable primary report includes each cost basis and
states when a partial total is not decision-grade. An isolated PostgreSQL API
test exercised persistence, exact arithmetic and replay; changed-value unit
cases exercised a complete and incomplete schedule. The local Python unit
gate passed 1,386 tests, frontend typecheck/lint/build passed, and four-role
launchd preflight passed. The exact-SHA release was installed and all four
application roles relaunched. API readiness reports migration
`0133_contract_coherence_review`; Qwen and NTD processes were not restarted.
The owner's real workspace still has no contractor-supplied cost assessment,
so its decision correctly remains `INSUFFICIENT_INPUT`. An authenticated
browser submission has not been claimed. Full Tender and ProductReady remain
unaccepted.
