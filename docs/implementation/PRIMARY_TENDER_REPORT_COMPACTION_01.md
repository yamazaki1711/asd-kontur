# Primary Tender Report Compaction 01

## Decision-first follow-up — deployed checkpoint

The rendered primary report was readable after compaction but still placed raw
participant, price, time and procurement tables before the professional
participation decision and key findings. The report now places the existing
decision and source-derived key conclusions immediately after the object
summary. The underlying facts, calculations and findings do not change;
context tables follow the conclusion and the full schedules remain in the
archive. A changed-party test verifies section order. The focused report suite
passed 16/16. Exact source `b8a85df54fb019284b0f3c29cca05a9fe77d77dd`
was built and deployed as
`~/.asd-kontur/public-demo/releases/20261008-b8a85df-tender-decision-first`.
The API, document worker, assistant worker and project orchestrator all run
from that release. Exact-release focused checks passed 88/88; isolated
PostgreSQL checks passed 3/3; frontend typecheck, lint and build passed.
The API returned ready at migration `0141_contract_reference_partial_package`
and the frontend returned HTTP 200. The Qwen and NTD services were not
restarted. The platform-only data fingerprint remained
`9941ef97d43749ffc396287f008fef03e3fb2e56804e5972f13a3bd68e158627`.
Owner-authenticated browser acceptance remains unavailable.

## Observed product defect

The live owner workspace has a useful structured Tender model and an editable
export, but the primary Word report rendered to 44 A4 pages. Large work,
quantity and material schedules were embedded in the report even though the
same archive already contained complete editable CSV schedules. This delays
the professional first review and makes significant findings harder to find.
Visual QA also showed that repeated extracted procurement and timing
statements can appear adjacent without semantic reconciliation. The latter is
an unresolved harness-quality gap; this slice does not infer which statement
governs.

## Reusable correction

The primary report now shows at most 30 location/work groups, 30 distinct
reviewed quantity rows, 25 material observations and eight names per facility
card list. It keeps all professional comparisons, issues, questions, risks
and uncertainty sections. Overflow is explicitly counted. The full work and
material schedules remain unchanged in the editable Tender archive; no
observation is deleted or promoted to a fact by this presentation rule.
Limits are project-independent and do not use any owner-project name, quantity
or expected finding.

On a read-only render of the same live project model, the primary Word report
fell from 44 to 28 A4 pages. Both full schedule members retained their
previous uncompressed byte counts (470,906 and 462,111). A changed-name
controlled test verifies that omitted main-report rows remain in the complete
CSV schedules. Exact release `9cb02f7d8e9db4596a422af96ca91266aae116cd`
is pinned to the API, document worker, assistant worker and project
orchestrator under
`~/.asd-kontur/public-demo/releases/20261008-9cb02f7-tender-summary`. The
public migration remains `0141_contract_reference_partial_package`. API
readiness and frontend HTTP 200 passed; the Qwen and NTD worker processes
were not restarted. The platform-only data fingerprint remained
`9941ef97d43749ffc396287f008fef03e3fb2e56804e5972f13a3bd68e158627`.
The exact release passed 87/87 focused unit and 3/3 isolated PostgreSQL
checks plus frontend typecheck, lint and build. Owner-authenticated browser
acceptance is not claimed; the in-app browser backend was unavailable.
Temporary owner-report QA files were removed after visual inspection. The
previous application plists are private under
`~/.asd-kontur/public-demo/launchd-backups/20261008-pre-9cb02f7-tender-summary/`.

## Remaining professional limit

The report still needs a generic Qwen-backed relationship review for
apparently conflicting procurement, commercial and time conditions, with
source roles and revisions kept separate. Deterministic display compaction
must not choose between those statements. Full four-mode product readiness
remains unaccepted.
