"""Async SQLAlchemy engine / session factory."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import Settings
from bot.db.models import Base

logger = logging.getLogger(__name__)


class Database:
    """Wraps the SQLAlchemy engine + sessionmaker."""

    def __init__(self, url: str) -> None:
        self._ensure_sqlite_dir(url)
        self.engine = create_async_engine(url, pool_pre_ping=True, future=True)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    @staticmethod
    def _ensure_sqlite_dir(url: str) -> None:
        if not url.startswith("sqlite"):
            return
        # sqlite+aiosqlite:///./data/vpnbot.sqlite3
        path = urlsplit(url).path.lstrip("/")
        if not path or path == ":memory:":
            return
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    async def init_models(self) -> None:
        """Create tables if they do not exist yet."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema is ready")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()


def make_database(settings: Settings) -> Database:
    return Database(settings.database_url)
