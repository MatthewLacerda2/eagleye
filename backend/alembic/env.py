"""Alembic environment: async engine on the app's DATABASE_URL, models' metadata.

`init_db()` runs `upgrade head` in a worker thread at startup, so `asyncio.run`
below never nests inside the application's event loop.
"""

import asyncio

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import models  # noqa: F401  (registers every table on Base.metadata)
from alembic import context
from core.config import get_settings
from core.database import normalize_database_url
from models.base import Base

target_metadata = Base.metadata


def _url() -> str:
    return normalize_database_url(get_settings().DATABASE_URL)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it."""
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async())
