"""HTTP server that receives platega.io payment callbacks."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiohttp import web

from bot.config import Settings
from bot.db.models import Payment
from bot.db.session import Database
from bot.services.subscriptions import SubscriptionsService

logger = logging.getLogger(__name__)


def build_app(
    *,
    settings: Settings,
    database: Database,
    subscriptions: SubscriptionsService,
    bot: Bot,
) -> web.Application:
    app = web.Application()

    async def callback_handler(request: web.Request) -> web.Response:
        if not subscriptions.platega.verify_callback(dict(request.headers)):
            logger.warning("Rejected platega callback with bad credentials")
            return web.Response(status=403, text="forbidden")

        try:
            payload: dict[str, Any] = await request.json()
        except Exception:  # noqa: BLE001
            logger.exception("Malformed platega callback")
            return web.Response(status=400, text="bad request")

        transaction_id = str(payload.get("id") or "")
        status = str(payload.get("status") or "").upper()
        if not transaction_id or not status:
            logger.warning("platega callback missing id/status: %s", payload)
            return web.Response(status=400, text="missing id/status")

        logger.info("platega callback tx=%s status=%s", transaction_id, status)

        async with database.session() as session:
            payment = await subscriptions.mark_payment(
                session, transaction_id=transaction_id, status=status
            )
            if payment is None:
                await session.commit()
                return web.Response(status=200, text="ok")

            if status == Payment.STATUS_CONFIRMED:
                try:
                    user = await subscriptions.fulfill_payment(session, payment)
                    await session.commit()
                except Exception:
                    logger.exception("Failed to fulfill payment %s", payment.id)
                    await session.rollback()
                    return web.Response(status=500, text="fulfill error")

                await _notify_user(bot, user.telegram_id, user)
            else:
                await session.commit()

        return web.Response(status=200, text="ok")

    async def health(_: web.Request) -> web.Response:
        return web.Response(status=200, text="ok")

    # Both paths accept platega.io callbacks — /platega_webhook is kept as an
    # alias for installations whose callback URL was configured with that path.
    app.router.add_post("/platega/callback", callback_handler)
    app.router.add_post("/platega_webhook", callback_handler)
    app.router.add_get("/health", health)
    return app


async def _notify_user(bot: Bot, telegram_id: int, user: Any) -> None:
    expires = user.expire_at.strftime("%Y-%m-%d %H:%M UTC") if user.expire_at else "—"
    text = (
        "<b>✅ Оплата прошла успешно!</b>\n\n"
        f"Подписка активна до <b>{expires}</b>.\n\n"
        "🔗 <b>Ссылка для клиента:</b>\n"
        f"<code>{user.subscription_url}</code>"
    )
    try:
        await bot.send_message(telegram_id, text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to notify user %s about payment", telegram_id)


async def run_webhook(
    *,
    settings: Settings,
    database: Database,
    subscriptions: SubscriptionsService,
    bot: Bot,
) -> web.AppRunner:
    app = build_app(settings=settings, database=database, subscriptions=subscriptions, bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.webhook_host, port=settings.webhook_port)
    await site.start()
    logger.info(
        "Webhook server listening on %s:%s (path /platega/callback)",
        settings.webhook_host,
        settings.webhook_port,
    )
    return runner
