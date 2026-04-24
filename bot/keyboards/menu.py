"""Inline keyboards used by the bot."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.tariffs import iter_tariffs

BUY_CB_PREFIX = "buy"
PAID_CB_PREFIX = "paid"


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Купить VPN", callback_data="menu:buy")
    builder.button(text="👤 Мой VPN", callback_data="menu:profile")
    builder.button(text="❓ Помощь", callback_data="menu:help")
    builder.adjust(1)
    return builder.as_markup()


def tariffs_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tariff in iter_tariffs():
        builder.button(
            text=tariff.menu_label,
            callback_data=f"{BUY_CB_PREFIX}:{tariff.code}",
        )
    builder.button(text="⬅️ Назад", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def payment_menu(payment_url: str, transaction_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оплатить", url=payment_url))
    builder.row(
        InlineKeyboardButton(
            text="🔄 Я оплатил — проверить",
            callback_data=f"{PAID_CB_PREFIX}:{transaction_id}",
        )
    )
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В меню", callback_data="menu:main")
    return builder.as_markup()
