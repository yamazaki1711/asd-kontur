# Role-aware Tender work coverage

Date: 2026-10-08. This is a generic continuation of the partial-scope
comparison slice, not Tender-mode acceptance.

## Failure and correction

The work schedule grouped observations by location, family and operation but
discarded each candidate's source-document role. A reciprocal local-Qwen
`SAME_SCOPE` decision inside a combined design/commercial row could not then
be used safely. The older complete-match predicate also treated one reviewed
pair as proof that every candidate in the row matched.

The schedule now retains `candidate_document_roles`. A combined row is a full
match on reviewed assertions only when every design and commercial candidate
has a reciprocal exact-candidate, cross-role match and the matches are
one-to-one. A reviewed subset becomes `PARTIAL_SCOPE_MATCH`; a same-role pair
cannot authorize commercial coverage. Numeric quantities are not summed or
compared by this rule. Missing or contradictory evidence remains unresolved.
No project-specific name, quantity, document title or expected finding is
encoded.

## Bounded evidence

On unchanged persisted owner-workspace data, a read-only v86 model returned
363 scope comparisons: 40 full matches, 16 partial matches and 307 unresolved.
The previous deployed v85 model had 43, 12 and 308 respectively. Thus three
overstated full matches were demoted while four previously hidden reviewed
subsets became visible. Professional issues remained three; no discrepancy
was fabricated. A controlled source-only test with changed facility names,
operations and candidate IDs covers complete one-to-one coverage, uncovered
candidates, one-to-many commercial ambiguity and same-role false positives.

FFC-02 remains `PARTIAL`, and ProductReady remains false. Authenticated owner
UI and full professional Tender acceptance are still required.

## Controlled release

The source change is deployed as exact application SHA
`962ae7f7ec6a40643c9d135ad0bc6bf27de757a2` on unchanged migration
`0142_audit_id_document_interpretation`. The API, worker, assistant worker and
project orchestrator all reported that SHA after controlled cutover; API
readiness passed and the frontend returned HTTP 200. The existing frontend
build was carried forward unchanged. Qwen and NTD worker process identities
were unchanged. The live durable queue was empty before cutover. Focused
Tender tests passed 216/216; ruff and diff checks passed. Authenticated
browser acceptance was not performed, and this release is not a Tender-mode
PASS.
