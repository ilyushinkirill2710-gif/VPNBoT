"""Core business logic: buy/fulfill subscription flow."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Payment, User
from bot.services.platega import PlategaClient
from bot.services.remnawave import RemnawaveService
from bot.services.tariffs import Tariff, get_tariff

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CreatedPayment:
    payment: Payment
    payment_url: str


class SubscriptionsService:
    def __init__(
        self,
        remnawave: RemnawaveService,
        platega: PlategaClient,
    ) -> None:
        self.remnawave = remnawave
        self.platega = platega

    # ---- users ----------------------------------------------------------

    async def get_or_create_user(
        self,
        session: AsyncSession,
        telegram_id: int,
        username: str | None,
        language_code: str | None,
    ) -> User:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                language_code=language_code,
            )
            session.add(user)
            await session.flush()
            logger.info("Registered new user %s (tg=%s)", user.id, telegram_id)
        else:
            changed = False
            if username and user.username != username:
                user.username = username
                changed = True
            if language_code and user.language_code != language_code:
                user.language_code = language_code
                changed = True
            if changed:
                await session.flush()
        return user

    # ---- payments -------------------------------------------------------

    async def create_payment(
        self,
        session: AsyncSession,
        *,
        user: User,
        tariff: Tariff,
    ) -> CreatedPayment:
        description = f"VPN {tariff.title} — TgId:{user.telegram_id} UserId:{user.id}"
        transaction = await self.platega.create_transaction(
            amount=float(tariff.price_rub),
            description=description,
            payload=f"uid={user.id};tariff={tariff.code}",
        )

        payment = Payment(
            user_id=user.id,
            tariff_code=tariff.code,
            tariff_days=tariff.days,
            amount_rub=tariff.price_rub,
            transaction_id=transaction.transaction_id,
            payment_method=int(self.platega._settings.platega_payment_method),
            payment_url=transaction.redirect,
            status=transaction.status or Payment.STATUS_PENDING,
        )
        session.add(payment)
        await session.flush()
        logger.info(
            "Created payment id=%s tx=%s tariff=%s user=%s",
            payment.id,
            payment.transaction_id,
            tariff.code,
            user.id,
        )
        return CreatedPayment(payment=payment, payment_url=transaction.redirect)

    async def mark_payment(
        self,
        session: AsyncSession,
        *,
        transaction_id: str,
        status: str,
    ) -> Payment | None:
        result = await session.execute(
            select(Payment).where(Payment.transaction_id == transaction_id)
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            logger.warning("Callback for unknown transaction %s", transaction_id)
            return None
        payment.status = status
        await session.flush()
        return payment

    async def fulfill_payment(
        self,
        session: AsyncSession,
        payment: Payment,
    ) -> User:
        """Apply a CONFIRMED payment: create or extend the VPN subscription."""
        if payment.processed:
            logger.info("Payment %s already processed, skipping", payment.id)
            result = await session.execute(select(User).where(User.id == payment.user_id))
            return result.scalar_one()

        tariff = get_tariff(payment.tariff_code)
        if tariff is None:
            raise ValueError(f"Unknown tariff code: {payment.tariff_code}")

        result = await session.execute(select(User).where(User.id == payment.user_id))
        user = result.scalar_one()

        remnawave_user = await self.remnawave.create_or_extend(
            telegram_id=user.telegram_id,
            days=tariff.days,
            existing_uuid=user.remnawave_uuid,
            existing_expire_at=user.expire_at,
        )

        user.remnawave_uuid = str(remnawave_user.uuid)
        user.remnawave_username = remnawave_user.username
        user.subscription_url = getattr(remnawave_user, "subscription_url", None)
        user.expire_at = getattr(remnawave_user, "expire_at", None)

        payment.processed = True
        await session.flush()

        logger.info(
            "Fulfilled payment %s: user %s now expires at %s",
            payment.id,
            user.id,
            user.expire_at,
        )
        return user
