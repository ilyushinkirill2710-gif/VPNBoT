"""aiogram middleware: open a DB session per update and inject services."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.config import Settings
from bot.db.session import Database
from bot.services.subscriptions import SubscriptionsService


class DependenciesMiddleware(BaseMiddleware):
    """Provide ``db_session``, ``settings`` and ``subscriptions`` to handlers."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        subscriptions: SubscriptionsService,
    ) -> None:
        self._database = database
        self._settings = settings
        self._subscriptions = subscriptions

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._database.session() as session:
            data["db_session"] = session
            data["settings"] = self._settings
            data["subscriptions"] = self._subscriptions
            try:
                return await handler(event, data)
            except Exception:
                await session.rollback()
                raise
