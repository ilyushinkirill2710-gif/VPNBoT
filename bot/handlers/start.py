"""`/start` command and main menu."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.menu import main_menu
from bot.services.subscriptions import SubscriptionsService

router = Router(name="start")

WELCOME = "👋 <b>Привет!</b>\n\nЭто бот для покупки VPN-подписки.\nВыберите действие в меню ниже."


@router.message(CommandStart())
async def on_start(
    message: Message,
    db_session: AsyncSession,
    subscriptions: SubscriptionsService,
) -> None:
    assert message.from_user is not None
    await subscriptions.get_or_create_user(
        db_session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        language_code=message.from_user.language_code,
    )
    await db_session.commit()
    await message.answer(WELCOME, reply_markup=main_menu(), parse_mode="HTML")


@router.callback_query(F.data == "menu:main")
async def back_to_main(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.edit_text(WELCOME, reply_markup=main_menu(), parse_mode="HTML")
    await callback.answer()
