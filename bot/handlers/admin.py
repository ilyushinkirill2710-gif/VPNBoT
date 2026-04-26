"""Minimal admin commands: /stats, /grant."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db.models import Payment, User
from bot.services.subscriptions import SubscriptionsService

router = Router(name="admin")
logger = logging.getLogger(__name__)


@router.message(Command("stats"))
async def on_stats(message: Message, db_session: AsyncSession, settings: Settings) -> None:
    if message.from_user is None or not settings.is_admin(message.from_user.id):
        return

    total_users = (await db_session.execute(select(func.count(User.id)))).scalar_one()
    active_users = (
        await db_session.execute(
            select(func.count(User.id)).where(User.expire_at > datetime.now(UTC))
        )
    ).scalar_one()
    confirmed_payments = (
        await db_session.execute(
            select(func.count(Payment.id)).where(Payment.status == Payment.STATUS_CONFIRMED)
        )
    ).scalar_one()
    revenue = (
        await db_session.execute(
            select(func.coalesce(func.sum(Payment.amount_rub), 0)).where(
                Payment.status == Payment.STATUS_CONFIRMED
            )
        )
    ).scalar_one()

    await message.answer(
        (
            f"<b>📊 Статистика</b>\n\n"
            f"Всего пользователей: <b>{total_users}</b>\n"
            f"С активной подпиской: <b>{active_users}</b>\n"
            f"Успешных платежей: <b>{confirmed_payments}</b>\n"
            f"Выручка: <b>{revenue}\u202f₽</b>"
        ),
        parse_mode="HTML",
    )


@router.message(Command("grant"))
async def on_grant(
    message: Message,
    command: CommandObject,
    db_session: AsyncSession,
    settings: Settings,
    subscriptions: SubscriptionsService,
) -> None:
    """Manually grant `/grant <telegram_id> <days>` an active subscription."""
    if message.from_user is None or not settings.is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer(
            "Использование: /grant &lt;telegram_id&gt; &lt;days&gt;", parse_mode="HTML"
        )
        return
    parts = command.args.split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await message.answer(
            "Использование: /grant &lt;telegram_id&gt; &lt;days&gt;", parse_mode="HTML"
        )
        return
    telegram_id = int(parts[0])
    days = int(parts[1])

    user = await subscriptions.get_or_create_user(
        db_session, telegram_id=telegram_id, username=None, language_code=None
    )
    remnawave_user = await subscriptions.remnawave.create_or_extend(
        telegram_id=telegram_id,
        days=days,
        existing_uuid=user.remnawave_uuid,
        existing_expire_at=user.expire_at,
    )
    user.remnawave_uuid = str(remnawave_user.uuid)
    user.remnawave_username = remnawave_user.username
    user.subscription_url = getattr(remnawave_user, "subscription_url", None)
    user.expire_at = getattr(remnawave_user, "expire_at", None)
    await db_session.commit()

    await message.answer(
        f"✅ Пользователю <code>{telegram_id}</code> выдано {days} дн. до <b>{user.expire_at}</b>.",
        parse_mode="HTML",
    )
