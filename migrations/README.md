# G-04 PostgreSQL migrations

Migrations are deterministic and PostgreSQL-specific. Supply the database URL
explicitly with `alembic -x database_url=... upgrade head`.

Production schema evolution is forward-only. Downgrade exists solely for a
disposable development/test database and is refused unless
`ASD_ALLOW_DESTRUCTIVE_DOWNGRADE=1` is set explicitly.

Migration execution reads neither application settings nor network policy and
does not import application runtime modules.
