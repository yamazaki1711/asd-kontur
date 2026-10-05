#!/usr/bin/env python3
"""Build the consultant NTD search index from existing local artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import create_engine

from asd_kontur.ntd.search_corpus import build_ntd_search_corpus


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--object-store-root", required=True, type=Path)
    parser.add_argument("--reference-manifest", type=Path)
    parser.add_argument("--apple-vision-executable", type=Path)
    parser.add_argument("--ocr-workers", type=int, default=4)
    arguments = parser.parse_args()
    engine = create_engine(arguments.database_url)
    try:
        result = build_ntd_search_corpus(
            engine,
            object_store_root=arguments.object_store_root.resolve(),
            reference_manifest=(
                arguments.reference_manifest.resolve() if arguments.reference_manifest else None
            ),
            apple_vision_executable=(
                arguments.apple_vision_executable.resolve()
                if arguments.apple_vision_executable
                else None
            ),
            ocr_workers=arguments.ocr_workers,
        )
    finally:
        engine.dispose()
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
