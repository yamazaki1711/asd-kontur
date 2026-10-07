# Bounded review of unlocated commercial/design work

Date: 2026-10-08. This is a generic Tender progression correction, not a
professional discrepancy or Tender-mode acceptance.

## Observed scheduling gap

The real workspace had 363 design/commercial work-scope comparisons, 307 of
them unresolved in model v86. Of those unresolved rows, 107 were design-only
and 197 commercial-only. Sixty-two design rows had a same-family commercial
peer under a loose location screen; 40 of those had no work-scope assertion.
Across grouped exact candidates there were 1,076 unattempted plausible pairs,
but only 32 pairs had both candidates eligible for the existing scope-review
policy. Every one of those 32 had a facility hint on exactly one side. The
batch selector allowed two located sides or two unlocated sides, so the
autonomous queue had no route for this case. These are *candidate contexts*,
not 1,076 proven comparable works or jobs that should all be run.

## Generic correction

The source-context prefilter and batch selector now admit a bounded lane for
one located and one unlocated design/commercial candidate in the same work
family when their source wording shares a distinguishing term. Strict
same-location contexts retain priority. The lane forms an exact two-candidate
Qwen task and records attempted pairs, so accepted decisions are not replayed.
It cannot connect two different explicit facilities or declare a scope match
by itself. Qwen must establish semantic compatibility; downstream deterministic
guards continue to reject unsupported quantity comparisons and findings.

The complete-match predicate for separate grouped design/commercial rows now
requires every candidate on both sides to participate in one-to-one reciprocal
reviewed matches. One reviewed sub-operation is partial coverage, not proof
that a whole grouped work scope is commercially covered. This is the same
anti-overstatement rule already applied inside combined-source schedule rows.

## Qualification before release

On unchanged persisted project facts, a read-only v87 model returned 28 full,
33 partial and 302 unresolved comparisons out of 363; professional issues
remained three. This is a correction of comparison authority, not a claim that
new discrepancies were found. Changed-name synthetic tests cover the
one-unlocated lane, unrelated wording rejection, attempted-pair idempotency,
complete coverage and incomplete grouped coverage. Focused tests passed
334/334; ruff and format checks passed. Live Qwen autonomy and useful-result
acceptance must be verified after controlled deployment.

FFC-02 and ProductReady remain incomplete.

## Controlled application release and autonomous observation

The exact application release is
`a2175552b3516d7d2b57bddafa3fee75c277bd06` on unchanged migration
`0142_audit_id_document_interpretation`. API, project worker, assistant worker
and project orchestrator all reported that SHA after cutover; API readiness
passed. The persistent Qwen and NTD services were not restarted. No durable
job was active immediately before release.

Without a manual queue command, the supervised runtime created four exact
two-row `CROSS_DOCUMENT_SCOPE_MATCHING` jobs. Qwen received those tasks;
four jobs succeeded with persisted results, and the orchestrator created
another four while the first batch was finishing. The first four accepted
results used seven model requests and included reciprocal `SAME_SCOPE` and
`DIFFERENT_SCOPE` decisions, plus bounded repair receipts. The read-only
deployed project model moved from 28/33/302 to 28/37/296 full/partial/
unresolved work-scope comparisons while professional issues stayed at three.
The total scope-row count also changed from 363 to 361 as accepted Qwen work
reconsolidated rows; no quantity mismatch or omission is inferred from that
count change. This demonstrates useful autonomous semantic progress, not a
complete Tender analysis or terminal project result. Further queued work is
owned by the supervised runtime, not by Codex.
