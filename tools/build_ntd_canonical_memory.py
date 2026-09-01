#!/usr/bin/env python3
"""Build canonical NTD memory from the accepted immutable audit."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import create_engine

from asd_kontur.ntd.canonical_memory import HttpEmbeddingClient, build_canonical_ntd_memory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--audit-json", required=True, type=Path)
    parser.add_argument("--object-store-root", required=True, type=Path)
    parser.add_argument("--embedding-profile", required=True, type=Path)
    parser.add_argument("--qualified-retrieval-receipt", required=True, type=Path)
    parser.add_argument("--embedding-endpoint", default="http://127.0.0.1:8791")
    parser.add_argument("--ocr-executable", type=Path)
    parser.add_argument("--actor", default="ntd-canonical-memory-builder")
    parser.add_argument("--canary-designation")
    parser.add_argument("--embedding-batch-size", default=32, type=int)
    args = parser.parse_args()
    profile = json.loads(args.embedding_profile.read_bytes())
    embedding = HttpEmbeddingClient(endpoint=args.embedding_endpoint, profile=profile)
    engine = create_engine(args.database_url)
    try:
        result = build_canonical_ntd_memory(
            engine,
            audit_json=args.audit_json.resolve(strict=True),
            object_store_root=args.object_store_root.resolve(strict=True),
            actor_identity_id=args.actor,
            embedding=embedding,
            retrieval_qualification_receipt=args.qualified_retrieval_receipt.resolve(strict=True),
            ocr_executable=(
                args.ocr_executable.resolve(strict=True) if args.ocr_executable else None
            ),
            canary_designation=args.canary_designation,
            embedding_batch_size=args.embedding_batch_size,
        )
    finally:
        engine.dispose()
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
