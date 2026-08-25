"""Idempotently remove the exact disposable database recorded by browser E2E."""

from __future__ import annotations

import json
import os
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import make_url


def main() -> None:
    state_path = Path(os.environ["ASD_E2E_STATE_PATH"])
    if not state_path.is_absolute() or not state_path.is_file():
        return
    state = json.loads(state_path.read_text(encoding="utf-8"))
    database_name = str(state["database_name"])
    roles = tuple(str(value) for value in state["roles"])
    if not database_name.startswith("asd_spine_e2e_") or not all(
        role.startswith("asd_spine_e2e_") and role.replace("_", "").isalnum() for role in roles
    ):
        raise RuntimeError("refusing unrecognized E2E cleanup identities")
    admin_url = make_url(os.environ["ASD_TEST_DATABASE_URL"]).set(database="postgres")
    engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:database AND pid <> pg_backend_pid()"
                ),
                {"database": database_name},
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')
            for role in roles:
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
    finally:
        engine.dispose()
        state_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
