# Product Interaction Architecture v1

## Information architecture

Global shell: authentication, workspace selector, health/capability status and
administration. Every domain screen is bound to exactly one workspace.

Workspace shell navigation:

1. Overview and blockers;
2. Documents and intake jobs;
3. Project Definition / OKS structure;
4. Work Requirement Matrix;
5. Tender;
6. Support;
7. Audit;
8. Restoration;
9. Generation/export;
10. Evidence/provenance;
11. Platform Knowledge status (read-only).

The document workbench is a resizable multi-pane layout: registry/tree,
PDF/image/CAD viewer, evidence side panel and task/finding panel. Selecting any
claim synchronizes source version, page/region or geometry locator, authority,
uncertainty, gap and blocker. Complex interaction works deterministically
without an LLM.

## API boundaries

- commands mutate through idempotent authorized endpoints and return job or
  decision identities;
- queries return typed workspace projections with version/freshness metadata;
- SSE emits recoverable progress sequence numbers;
- binary bytes use authorized bounded streaming endpoints;
- browser never receives database/object/model credentials;
- no demo/fallback domain data is permitted.

Destructive archive/reset/destroy actions require separate confirmation,
previewed scope and immutable receipt. Every long job supports restored
progress, pause/resume/cancel where safe, retry policy and reconciliation.

## Acceptance contracts

Keyboard/accessibility, large-table virtualization, exact locator round trips,
reload recovery, cross-workspace negative tests, no-result/gap states and
destructive confirmations are capability E2E requirements. Visual polish alone
does not satisfy them.
