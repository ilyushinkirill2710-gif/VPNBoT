"""Entrypoint: run the Telegram bot + webhook server in one process."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import get_settings
from bot.db.session import make_database
from bot.handlers import build_router
from bot.middlewares import DependenciesMiddleware
from bot.services.platega import PlategaClient
from bot.services.remnawave import RemnawaveService
from bot.services.subscriptions import SubscriptionsService
from bot.utils.logger import setup_logging
from bot.webhook.server import run_webhook

logger = logging.getLogger(__name__)


async def _run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    database = make_database(settings)
    await database.init_models()

    remnawave = RemnawaveService(settings)
    platega = PlategaClient(settings)
    subscriptions = SubscriptionsService(remnawave=remnawave, platega=platega)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.update.middleware(DependenciesMiddleware(database, settings, subscriptions))
    dp.include_router(build_router())

    runner = await run_webhook(
        settings=settings, database=database, subscriptions=subscriptions, bot=bot
    )

    logger.info("Starting Telegram polling…")
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, handle_signals=True)
    finally:
        await runner.cleanup()
        await platega.aclose()
        await database.close()
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(_run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown requested")


if __name__ == "__main__":
    main()
