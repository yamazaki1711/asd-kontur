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
