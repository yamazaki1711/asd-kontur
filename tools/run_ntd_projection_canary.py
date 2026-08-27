"""Build and reproducibly rebuild the exact verified-provision NTD projection."""

from __future__ import annotations

import argparse
import json

import sqlalchemy as sa

from asd_kontur.ntd.durability import (
    NtdProjectionBuilder,
    build_backup_manifest,
    persist_backup_manifest,
    verify_restored_memory,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--seed-manifest-fingerprint", required=True)
    parser.add_argument("--delete-rebuild", action="store_true")
    arguments = parser.parse_args()
    engine = sa.create_engine(arguments.database_url)
    try:
        manifest = build_backup_manifest(
            engine, seed_manifest_fingerprint=arguments.seed_manifest_fingerprint
        )
        manifest_reused = persist_backup_manifest(engine, manifest)
        verify_restored_memory(engine, manifest)
        builder = NtdProjectionBuilder(engine)
        first_id, first_count = builder.rebuild(manifest.canonical_semantic_fingerprint)
        second_id, second_count = first_id, first_count
        if arguments.delete_rebuild:
            builder.delete_rebuildable_plane()
            second_id, second_count = builder.rebuild(manifest.canonical_semantic_fingerprint)
        if (first_id, first_count) != (second_id, second_count):
            raise ValueError("NTD_PROJECTION_REBUILD_MISMATCH")
        print(
            json.dumps(
                {
                    "schema": "ntd-projection-canary-v1",
                    "canonical_semantic_fingerprint": manifest.canonical_semantic_fingerprint,
                    "verified_provision_count": len(manifest.provision_fingerprints),
                    "projection_id": str(first_id),
                    "projection_entry_count": first_count,
                    "delete_rebuild": arguments.delete_rebuild,
                    "backup_manifest_reused": manifest_reused,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
