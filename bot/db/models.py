"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class."""


class User(Base):
    """End-user of the bot."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Remnawave link
    remnawave_uuid: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    remnawave_username: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    subscription_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    payments: Mapped[list[Payment]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Payment(Base):
    """Payment record. Linked to platega.io transaction."""

    __tablename__ = "payments"

    STATUS_PENDING = "PENDING"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_CANCELED = "CANCELED"
    STATUS_CHARGEBACKED = "CHARGEBACKED"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    tariff_code: Mapped[str] = mapped_column(String(16), nullable=False)
    tariff_days: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_rub: Mapped[int] = mapped_column(Integer, nullable=False)

    # platega.io
    transaction_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    payment_method: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), default=STATUS_PENDING, nullable=False, index=True
    )
    processed: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="payments")
