+# Correction — OZERO RLS scope and capability-ledger reconciliation
+
+Captured 2026-09-10T16:48:00+12:00. This correction preserves, rather than alters, the original diagnostic handoff files.
+
+## Revised claim: workspace visibility
+
+The original `REPORT_RU.md` statement that OZERO was absent from all local databases is **revised**. Its direct read used role `asd_public_app` with empty `asd.organization_id` and `asd.workspace_id`. The relevant workspace tables use `FORCE ROW LEVEL SECURITY`; the role inherits `asd_app`, has no `BYPASSRLS`, and its `workspace.workspaces` policy predicates on both settings. Zero rows in that unscoped transaction were therefore expected filtered visibility, not evidence of physical absence.
+
+Using the existing `application.resolve_workspace_scope(owner, workspace)` SECURITY DEFINER function with an already-present authorized owner, then setting the resolved organization and requested workspace inside one read-only transaction, returned:
+
+* workspace `01a088aa-0491-7bdd-9127-8359fe927a27`, state `ACTIVE`, revision `1`, not write-fenced;
+* 22 documents and 22 source versions;
+* 2,529 pages, 135,883 source locators, 133,354 native-layout elements, and 2,529 page-health records;
+* 38 completed Qwen OCR page results, plus 550 historical Apple-Vision results;
+* 574 role candidates and 524 role decisions;
+* zero structured project fields/work/quantity/material candidates, ProjectDefinitions, structures, work packages, matrices and reconciliations.
+
+The owning live database is `asd_kontur_public_demo` on the local PostgreSQL server, migration `0038_consultant_request_id`. The API readiness route is `/api/v1/health/ready`, which returned `ready` and PostgreSQL reachable. The prior `/api/v1/health` 404 was an incorrect assumed path.
+
+## Original assistant turn
+
+Within the same scope, turn `01a088c6-a7a0-7fb4-8a64-732bac76b362` exists and completed as `succeeded` on 2026-09-10 12:45:34 UTC+12. It used Tender, `professional-assistant@1.0.0` and `qwen3.8-27b-mlx-8bit@1.0.0`. It has 10 source events but **zero `assistant_tool_receipts`**. Its historical answer is therefore not reproducible as a tool-grounded retrieval trace.
+
+## Effective processing state
+
+Native extraction and page health completed for all 22 documents. OCR has 11 effective failed document jobs and 11 effective successful document jobs; failures include historical `none_available`/Apple schema errors and current Qwen malformed/schema/runtime-unavailable outcomes. The completed Qwen pages belong to the IОС1 source; their parent OCR job terminally failed after page 38. Downstream classification is complete for 12 documents; all aggregation, candidate extraction, assembly, evidence index and reconciliation jobs remain `reconciliation_required`.
+
+The immediate code defect is established: a manual retry runs every actionable page again and does not reuse successful Qwen page results. The active repair adds adapter-specific completed-page lookup and skips only the same-adapter completed pages; it does not promote historical Apple output to Qwen provenance.
+
+## Capability ledger correction
+
+The original CSV applied v2.4/v2.5 deltas directly to the v2.0 registry and omitted the v2.1 Product Application Spine delta. The corrected `documented_readiness` is composed in this order: v2.0 base → v2.1 spine delta → v2.2 accepted current-state record → v2.3 addition → v2.4 delta → v2.5 Industrial Intake/Project Understanding delta. Its resulting documented distribution is exactly:
+
+| State | Count |
+|---|---:|
+| CAPABILITY_READY | 16 |
+| PARTIAL | 45 |
+| FOUNDATION_ONLY | 36 |
+| CONTRACT_ONLY | 39 |
+| NOT_IMPLEMENTED | 7 |
+| Total | 143 |
+
+This is historical/documented readiness, not current OZERO production acceptance. Incident-specific deployment evidence remains separately marked in the CSV.
+
+## Remaining unverified / next action
+
+The API, assistant worker and frontend execute `b67bcd6`; document worker executes `120006d`, while its launchd definition still names `b26eb59`. No authenticated browser binding is available in this Codex session, so public UI-to-API session correlation remains unverified. Next action: qualify and deploy the completed-page retry repair to the document worker, use one supported derived retry for the partially completed IОС1 OCR job, prove durable Qwen page processing and propagate only its affected dependencies.
+
