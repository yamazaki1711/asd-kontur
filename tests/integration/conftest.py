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
    curator_engine: Engine
    projection_engine: Engine
    lifecycle_engine: Engine
    destruction_engine: Engine
    verifier_engine: Engine
    harness_engine: Engine
    kernel_engine: Engine
    tender_engine: Engine
    support_engine: Engine
    audit_engine: Engine
    guidance_ingestion_engine: Engine
    guidance_gateway_engine: Engine
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
    curator_role = f"asd_g05_test_curator_{run_id}"
    projection_role = f"asd_g05_test_projection_{run_id}"
    lifecycle_role = f"asd_g06_test_lifecycle_{run_id}"
    destruction_role = f"asd_g06_test_destruction_{run_id}"
    verifier_role = f"asd_g06_test_verifier_{run_id}"
    harness_role = f"asd_g07_test_harness_{run_id}"
    kernel_role = f"asd_wp11_test_kernel_{run_id}"
    tender_role = f"asd_wp12_test_tender_{run_id}"
    support_role = f"asd_wp13_test_support_{run_id}"
    audit_role = f"asd_wp14_test_audit_{run_id}"
    guidance_ingestion_role = f"asd_kgid_test_ingestion_{run_id}"
    guidance_gateway_role = f"asd_kgid_test_gateway_{run_id}"
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
            for role in (
                application_role,
                curator_role,
                projection_role,
                lifecycle_role,
                destruction_role,
                verifier_role,
                harness_role,
                kernel_role,
                tender_role,
                support_role,
                audit_role,
                guidance_ingestion_role,
                guidance_gateway_role,
            ):
                assert role.replace("_", "").isalnum()
                connection.exec_driver_sql(
                    f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOCREATEDB '
                    f"NOCREATEROLE INHERIT PASSWORD '{password}'"
                )
            connection.exec_driver_sql(f'GRANT asd_app TO "{application_role}"')
            connection.exec_driver_sql(f'GRANT asd_platform_curator TO "{curator_role}"')
            connection.exec_driver_sql(f'GRANT asd_projection_builder TO "{projection_role}"')
            connection.exec_driver_sql(f'GRANT asd_lifecycle_service TO "{lifecycle_role}"')
            connection.exec_driver_sql(f'GRANT asd_destruction_executor TO "{destruction_role}"')
            connection.exec_driver_sql(f'GRANT asd_lifecycle_verifier TO "{verifier_role}"')
            connection.exec_driver_sql(f'GRANT asd_harness_service TO "{harness_role}"')
            connection.exec_driver_sql(f'GRANT asd_kernel_service TO "{kernel_role}"')
            connection.exec_driver_sql(f'GRANT asd_tender_service TO "{tender_role}"')
            connection.exec_driver_sql(f'GRANT asd_support_service TO "{support_role}"')
            connection.exec_driver_sql(f'GRANT asd_audit_service TO "{audit_role}"')
            connection.exec_driver_sql(
                f'GRANT asd_guidance_ingestion_service TO "{guidance_ingestion_role}"'
            )
            connection.exec_driver_sql(
                f'GRANT asd_guidance_gateway_service TO "{guidance_gateway_role}"'
            )
        application_url = owner_url.set(username=application_role, password=password)
        curator_url = owner_url.set(username=curator_role, password=password)
        projection_url = owner_url.set(username=projection_role, password=password)
        lifecycle_url = owner_url.set(username=lifecycle_role, password=password)
        destruction_url = owner_url.set(username=destruction_role, password=password)
        verifier_url = owner_url.set(username=verifier_role, password=password)
        harness_url = owner_url.set(username=harness_role, password=password)
        kernel_url = owner_url.set(username=kernel_role, password=password)
        tender_url = owner_url.set(username=tender_role, password=password)
        support_url = owner_url.set(username=support_role, password=password)
        audit_url = owner_url.set(username=audit_role, password=password)
        guidance_ingestion_url = owner_url.set(username=guidance_ingestion_role, password=password)
        guidance_gateway_url = owner_url.set(username=guidance_gateway_role, password=password)
        application_engine = create_database_engine(
            DatabaseSettings(
                url=application_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        curator_engine = create_database_engine(
            DatabaseSettings(
                url=curator_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        projection_engine = create_database_engine(
            DatabaseSettings(
                url=projection_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        lifecycle_engine = create_database_engine(
            DatabaseSettings(
                url=lifecycle_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        destruction_engine = create_database_engine(
            DatabaseSettings(
                url=destruction_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        verifier_engine = create_database_engine(
            DatabaseSettings(
                url=verifier_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        harness_engine = create_database_engine(
            DatabaseSettings(
                url=harness_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        kernel_engine = create_database_engine(
            DatabaseSettings(
                url=kernel_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        tender_engine = create_database_engine(
            DatabaseSettings(
                url=tender_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        support_engine = create_database_engine(
            DatabaseSettings(
                url=support_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        audit_engine = create_database_engine(
            DatabaseSettings(
                url=audit_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        guidance_ingestion_engine = create_database_engine(
            DatabaseSettings(
                url=guidance_ingestion_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        guidance_gateway_engine = create_database_engine(
            DatabaseSettings(
                url=guidance_gateway_url.render_as_string(hide_password=False),
                pool_size=1,
                max_overflow=0,
            )
        )
        yield PostgreSQLEnvironment(
            cluster_admin_url=cluster_admin_url,
            database_name=database_name,
            application_role=application_role,
            application_engine=application_engine,
            curator_engine=curator_engine,
            projection_engine=projection_engine,
            lifecycle_engine=lifecycle_engine,
            destruction_engine=destruction_engine,
            verifier_engine=verifier_engine,
            harness_engine=harness_engine,
            kernel_engine=kernel_engine,
            tender_engine=tender_engine,
            support_engine=support_engine,
            audit_engine=audit_engine,
            guidance_ingestion_engine=guidance_ingestion_engine,
            guidance_gateway_engine=guidance_gateway_engine,
            owner_engine=owner_engine,
        )
        application_engine.dispose()
        curator_engine.dispose()
        projection_engine.dispose()
        lifecycle_engine.dispose()
        destruction_engine.dispose()
        verifier_engine.dispose()
        harness_engine.dispose()
        kernel_engine.dispose()
        tender_engine.dispose()
        support_engine.dispose()
        audit_engine.dispose()
        guidance_ingestion_engine.dispose()
        guidance_gateway_engine.dispose()
    finally:
        owner_engine.dispose()
        drop_database(cluster_engine, database_name)
        with cluster_engine.begin() as connection:
            for role in (
                application_role,
                curator_role,
                projection_role,
                lifecycle_role,
                destruction_role,
                verifier_role,
                harness_role,
                kernel_role,
                tender_role,
                support_role,
                audit_role,
                guidance_ingestion_role,
                guidance_gateway_role,
            ):
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
        cluster_engine.dispose()
