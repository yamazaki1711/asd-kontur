from __future__ import annotations

import os
from argparse import Namespace
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.engine import URL, make_url

from asd_kontur.persistence import create_database_engine
from asd_kontur.settings import DatabaseSettings


@dataclass(frozen=True, slots=True)
class PostgreSQLEnvironment:
    cluster_admin_url: URL
    database_name: str
    application_role: str
    application_engine: Engine
    owner_engine: Engine


def run_migration(repository_root: str, database_url: URL, revision: str) -> None:
    configuration = Config(os.path.join(repository_root, "alembic.ini"))
    configuration.cmd_opts = Namespace(
        x=[f"database_url={database_url.render_as_string(hide_password=False)}"]
    )
    command.upgrade(configuration, revision) if revision == "head" else command.downgrade(
        configuration, revision
    )


def create_database(engine: Engine, database_name: str) -> None:
    assert database_name.startswith("asd_g04_test_")
    with engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')


def drop_database(engine: Engine, database_name: str) -> None:
    assert database_name.startswith("asd_g04_test_")
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (database_name,),
        )
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')


@pytest.fixture(scope="session")
def postgres_environment(repository_root: object) -> Iterator[PostgreSQLEnvironment]:
    explicit_url = os.environ.get("ASD_TEST_DATABASE_URL")
    if not explicit_url:
        pytest.skip(
            "ASD_TEST_DATABASE_URL is not set to an explicitly disposable PostgreSQL cluster"
        )
    base_url = make_url(explicit_url)
    if base_url.get_backend_name() != "postgresql":
        pytest.fail("ASD_TEST_DATABASE_URL must use PostgreSQL")
    run_id = str(os.getpid())
    database_name = f"asd_g04_test_{run_id}"
    application_role = f"asd_g04_test_app_{run_id}"
    password = "synthetic-g04-test-only"
    cluster_admin_url = base_url.set(database="postgres")
    cluster_engine = sa.create_engine(cluster_admin_url, isolation_level="AUTOCOMMIT")
    create_database(cluster_engine, database_name)
    owner_url = base_url.set(database=database_name)
    owner_engine = sa.create_engine(owner_url)
    try:
        run_migration(str(repository_root), owner_url, "head")
        assert application_role.replace("_", "").isalnum()
        with cluster_engine.begin() as connection:
            connection.exec_driver_sql(
                f'CREATE ROLE "{application_role}" LOGIN NOSUPERUSER NOCREATEDB '
                f"NOCREATEROLE INHERIT PASSWORD '{password}'"
            )
            connection.exec_driver_sql(f'GRANT asd_app TO "{application_role}"')
        application_url = owner_url.set(username=application_role, password=password)
        application_engine = create_database_engine(
            DatabaseSettings(
                url=application_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        yield PostgreSQLEnvironment(
            cluster_admin_url=cluster_admin_url,
            database_name=database_name,
            application_role=application_role,
            application_engine=application_engine,
            owner_engine=owner_engine,
        )
        application_engine.dispose()
    finally:
        owner_engine.dispose()
        drop_database(cluster_engine, database_name)
        with cluster_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{application_role}"')
        cluster_engine.dispose()
