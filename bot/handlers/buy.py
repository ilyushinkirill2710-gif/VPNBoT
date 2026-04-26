"""Purchase flow: pick a tariff → create platega payment → verify."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Payment
from bot.keyboards.menu import (
    BUY_CB_PREFIX,
    PAID_CB_PREFIX,
    back_to_menu,
    payment_menu,
    tariffs_menu,
)
from bot.services.platega import PlategaError
from bot.services.subscriptions import SubscriptionsService
from bot.services.tariffs import get_tariff

router = Router(name="buy")
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "menu:buy")
async def on_buy_menu(callback: CallbackQuery) -> None:
    text = "<b>🛒 Выберите тариф:</b>\n\nПосле оплаты подписка подключится автоматически."
    if callback.message:
        await callback.message.edit_text(text, reply_markup=tariffs_menu(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith(f"{BUY_CB_PREFIX}:"))
async def on_buy(
    callback: CallbackQuery,
    db_session: AsyncSession,
    subscriptions: SubscriptionsService,
) -> None:
    assert callback.data is not None
    _, code = callback.data.split(":", 1)
    tariff = get_tariff(code)
    if tariff is None:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    assert callback.from_user is not None
    user = await subscriptions.get_or_create_user(
        db_session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        language_code=callback.from_user.language_code,
    )
    try:
        created = await subscriptions.create_payment(
            db_session,
            user=user,
            tariff=tariff,
        )
    except PlategaError:
        logger.exception("platega create_payment failed")
        await callback.answer("Платёжный шлюз недоступен, попробуйте позже.", show_alert=True)
        await db_session.rollback()
        return

    await db_session.commit()

    text = (
        f"<b>💳 Оплата — {tariff.title}</b>\n\n"
        f"Сумма: <b>{tariff.price_label}</b>\n"
        "Нажмите «💳 Оплатить», после успешной оплаты подписка активируется автоматически.\n\n"
        "Если автообновление не сработало — нажмите «🔄 Я оплатил — проверить»."
    )
    if callback.message:
        await callback.message.edit_text(
            text,
            reply_markup=payment_menu(
                payment_url=created.payment_url,
                transaction_id=created.payment.transaction_id or "",
            ),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{PAID_CB_PREFIX}:"))
async def on_check_paid(
    callback: CallbackQuery,
    db_session: AsyncSession,
    subscriptions: SubscriptionsService,
) -> None:
    assert callback.data is not None
    _, transaction_id = callback.data.split(":", 1)

    try:
        status_data = await subscriptions.platega.get_transaction(transaction_id)
    except PlategaError:
        logger.exception("platega status check failed")
        await callback.answer("Платёжный шлюз недоступен.", show_alert=True)
        return

    status = str(status_data.get("status") or "").upper()

    result = await db_session.execute(
        select(Payment).where(Payment.transaction_id == transaction_id)
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        await callback.answer("Платёж не найден в системе.", show_alert=True)
        return

    payment.status = status or payment.status

    if status == Payment.STATUS_CONFIRMED:
        user = await subscriptions.fulfill_payment(db_session, payment)
        await db_session.commit()
        expires = user.expire_at.strftime("%Y-%m-%d %H:%M UTC") if user.expire_at else "—"
        text = (
            "<b>✅ Оплата прошла успешно!</b>\n\n"
            f"Подписка активна до <b>{expires}</b>.\n\n"
            "🔗 <b>Ссылка для клиента:</b>\n"
            f"<code>{user.subscription_url}</code>"
        )
    elif status == Payment.STATUS_CANCELED:
        await db_session.commit()
        text = "<b>❌ Платёж отменён.</b>\n\nПопробуйте оформить подписку заново в меню."
    else:
        await db_session.commit()
        text = (
            "⏳ Платёж ещё в обработке.\n"
            "Подождите минуту и нажмите «🔄 Я оплатил — проверить» ещё раз."
        )

    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=back_to_menu(), parse_mode="HTML", disable_web_page_preview=True
        )
    await callback.answer()
