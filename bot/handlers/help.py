"""Help / FAQ screen."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.keyboards.menu import back_to_menu

router = Router(name="help")


def _text(settings: Settings) -> str:
    return (
        "<b>❓ Помощь</b>\n\n"
        "• <b>Купить VPN</b> — выбрать тариф и оплатить.\n"
        "• <b>Мой VPN</b> — получить ссылку для клиента и срок действия.\n\n"
        "После оплаты подписка подключается автоматически в течение 1–2 минут.\n"
        "Если что-то пошло не так — напишите в поддержку: "
        f"{settings.support_username}."
    )


@router.message(Command("help"))
async def on_help_cmd(message: Message, settings: Settings) -> None:
    await message.answer(_text(settings), reply_markup=back_to_menu(), parse_mode="HTML")


@router.callback_query(F.data == "menu:help")
async def on_help_cb(callback: CallbackQuery, settings: Settings) -> None:
    if callback.message:
        await callback.message.edit_text(
            _text(settings), reply_markup=back_to_menu(), parse_mode="HTML"
        )
    await callback.answer()
