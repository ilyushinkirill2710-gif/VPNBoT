"""«Мой VPN»: show current subscription status."""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.keyboards.menu import back_to_menu, main_menu
from bot.services.subscriptions import SubscriptionsService

router = Router(name="profile")


async def _render(
    db_session: AsyncSession,
    subscriptions: SubscriptionsService,
    telegram_id: int,
    username: str | None,
    language_code: str | None,
) -> str:
    await subscriptions.get_or_create_user(
        db_session,
        telegram_id=telegram_id,
        username=username,
        language_code=language_code,
    )
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one()

    if not user.subscription_url:
        return (
            "<b>👤 Мой VPN</b>\n\n"
            "У вас пока нет активной подписки.\n"
            "Нажмите «🛒 Купить VPN», чтобы оформить её."
        )

    now = datetime.now(UTC)
    if user.expire_at and user.expire_at > now:
        delta = user.expire_at - now
        days = delta.days
        hours = delta.seconds // 3600
        expire_line = f"Действует до: <b>{user.expire_at.strftime('%Y-%m-%d %H:%M UTC')}</b>"
        left_line = f"Осталось: <b>{days} дн. {hours} ч.</b>"
    else:
        expire_line = "Подписка истекла"
        left_line = "Продлите доступ в меню «🛒 Купить VPN»."

    return (
        "<b>👤 Мой VPN</b>\n\n"
        f"{expire_line}\n{left_line}\n\n"
        "🔗 <b>Ссылка для клиента</b> (вставьте в v2rayNG / Hiddify / Happ):\n"
        f"<code>{user.subscription_url}</code>"
    )


@router.message(Command("profile"))
async def on_profile_cmd(
    message: Message,
    db_session: AsyncSession,
    subscriptions: SubscriptionsService,
) -> None:
    assert message.from_user is not None
    text = await _render(
        db_session,
        subscriptions,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        language_code=message.from_user.language_code,
    )
    await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")


@router.callback_query(F.data == "menu:profile")
async def on_profile_cb(
    callback: CallbackQuery,
    db_session: AsyncSession,
    subscriptions: SubscriptionsService,
) -> None:
    assert callback.from_user is not None
    text = await _render(
        db_session,
        subscriptions,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        language_code=callback.from_user.language_code,
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=back_to_menu(), parse_mode="HTML", disable_web_page_preview=True
        )
    await callback.answer()
