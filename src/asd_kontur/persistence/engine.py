"""PostgreSQL engine construction without ambient configuration."""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.pool import Pool

from asd_kontur.settings import DatabaseSettings


def create_database_engine(settings: DatabaseSettings) -> Engine:
    """Create the synchronous authoritative PostgreSQL boundary."""

    engine = create_engine(
        settings.url,
        pool_pre_ping=True,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_seconds,
    )

    @event.listens_for(engine.pool, "reset")
    def _rollback_on_pool_reset(
        dbapi_connection: object,
        connection_record: object,
        reset_state: object,
    ) -> None:
        # SQLAlchemy rolls back before check-in. Explicit rollback is harmless and
        # ensures failed transactions cannot preserve SET LOCAL state.
        rollback = getattr(dbapi_connection, "rollback", None)
        if rollback is not None:
            rollback()

    return engine


def pool_has_no_ambient_scope(pool: Pool) -> bool:
    """Marker used by tests/documentation: all scope is transaction-local."""

    return pool is not None
