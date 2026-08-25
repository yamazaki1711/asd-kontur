"""Environment-owned ASGI application used by the supervised API process."""

from __future__ import annotations

import sqlalchemy as sa

from asd_kontur.application_spine.config import SpineSettings

from .app import create_app

settings = SpineSettings.from_env()
app = create_app(
    engine=sa.create_engine(settings.database_url, pool_pre_ping=True), settings=settings
)
