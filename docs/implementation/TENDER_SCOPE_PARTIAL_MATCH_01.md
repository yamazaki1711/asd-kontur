# Tender scope partial-match correction

Date: 2026-10-08. This is one generic Tender result slice, not Tender-mode or
product readiness.

## Observed defect

The real workspace's current project model had 363 design/commercial scope
comparisons: 43 `MATCH` and 320 `UNRESOLVED_SCOPE_MATCH`. Qwen's accepted
work-reconciliation receipts contained reciprocal exact-candidate decisions.
Some grouped work scopes had both a reviewed `SAME_SCOPE` sub-operation and a
different or unreviewed sub-operation. The former model treated the whole
group as generically unresolved, losing useful partial coverage. Separately,
one combined design/commercial schedule row could be marked `MATCH` solely
because a facility identifier existed; location alone is not operation
equivalence.

## Generic correction

Model v85 emits `PARTIAL_SCOPE_MATCH` only when a reciprocal exact-candidate
`SAME_SCOPE` assertion exists but the grouped scope is not wholly matched.
The complete-match rule remains unchanged; a shared facility no longer
authorizes it by itself. A partial match is not an omitted-work finding.
Each comparison now carries its owning work-scope identity and, where one
unambiguous peer exists, the paired identity. Partial matches retain both
source-locator sets and appear as unresolved coverage in the primary report.
No new Qwen task, corpus-specific string, quantity, facility or expected
finding was introduced.

## Read-only real-project qualification

The same persisted Qwen decisions, without changing project rows or scheduling
new inference, produced 43 full matches, 12 partial matches and 308 unresolved
comparisons out of 363. All 12 partial results carried source locators from
both sides; all 363 comparisons carried work-scope IDs. The professional
finding count remained three, proving that partial coverage did not become a
fabricated discrepancy. The editable preliminary Tender report included the
partial-coverage count. Its 19 rendered A4 pages were nonempty, with no
detected out-of-page text or text within six points of an edge; the first and
last pages were visually inspected. The temporary owner-content export was
removed after inspection.

A combined design/commercial schedule row with an internal exact-candidate
match remains unresolved: the current merged row does not prove the document
role of each candidate in that assertion. A partial result is deliberately
withheld there until a source-role-aware candidate link is available.

Focused generic tests cover mixed exact-pair decisions, location-only
false-positive rejection and report disclosure. They do not prove the 307
remaining scopes are comparable or that Tender mode is complete.
