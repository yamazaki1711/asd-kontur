"""Generate the deterministic Product Spine OpenAPI build artifact without a live database."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import sqlalchemy as sa

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.web_app import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="asd-openapi-") as temporary:
        (Path(temporary) / "archives").mkdir()
        settings = SpineSettings(
            database_url="postgresql+psycopg://invalid:invalid@127.0.0.1/explicit",
            lifecycle_database_url=("postgresql+psycopg://invalid:invalid@127.0.0.1/explicit"),
            worker_database_url="postgresql+psycopg://invalid:invalid@127.0.0.1/explicit",
            destruction_database_url="postgresql+psycopg://invalid:invalid@127.0.0.1/explicit",
            object_store_root=Path(temporary),
            archive_store_root=Path(temporary) / "archives",
            session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
            audit_pepper="openapi-generation-content-minimal-value",
        )
        engine = sa.create_engine(settings.database_url)
        document = create_app(engine=engine, settings=settings).openapi()
        engine.dispose()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
