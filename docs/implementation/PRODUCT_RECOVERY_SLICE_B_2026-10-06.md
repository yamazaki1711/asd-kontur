# Product recovery: workspace removal, bounded slice B

This source-only checkpoint addresses one verified lifecycle defect. It is not an attestation of complete OKS erasure and does not authorize deletion of the currently admitted project.

## Defect and correction

The existing reset `prepare` operation creates a project ZIP under the local archive root. Its deletion coordinator previously inventoried PostgreSQL and the workspace object store, but not that ZIP. A successful `execute` therefore left a restorable project copy behind.

The deletion registry now contains an exact workspace-scoped reset-archive adapter. It inventories every direct file under the organization/workspace archive directory, rejects links and unexpected nested entries, removes only planned files, and reports any remaining file as residue. The normal reset plan, execution and verification consequently cover archives created by `prepare` as well as older files in that same exact workspace directory. An unrelated workspace directory is not touched. A separately requested user export remains outside this adapter.

## Evidence and limits

Disposable tests demonstrate exact-scope archive removal, other-workspace preservation, symlink rejection and empty residue. Static checks and type checking pass. The database-backed reset test is skipped here because `ASD_TEST_DATABASE_URL` is not configured for an explicitly disposable cluster. No real workspace was reset and this change is not deployed.

The older lifecycle still creates a temporary ZIP during `prepare`. If preparation aborts before a deletion plan exists, or a challenge expires without `execute`, the temporary ZIP can remain. That path requires a separate resumable cleanup policy before claiming complete lifecycle acceptance. Browser/client state, logs containing project payloads, remote backups, development artifacts and retained identifying metadata are also not yet covered by this adapter. `ProductReady=false`.
