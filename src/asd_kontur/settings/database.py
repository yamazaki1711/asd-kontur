"""Database configuration with explicit construction."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Connection parameters supplied by a caller-owned configuration boundary."""

    url: str
    pool_size: int = 5
    max_overflow: int = 0
    pool_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.url.startswith(("postgresql+psycopg://", "postgresql://")):
            raise ValueError("ASD-KONTUR persistence requires a PostgreSQL psycopg URL")
        if self.pool_size < 1:
            raise ValueError("pool_size must be positive")
        if self.max_overflow < 0:
            raise ValueError("max_overflow cannot be negative")
