"""Thin wrapper around the official Remnawave Python SDK."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from remnawave import RemnawaveSDK
from remnawave.models import (
    CreateUserRequestDto,
    UpdateUserRequestDto,
    UserResponseDto,
)

from bot.config import Settings

logger = logging.getLogger(__name__)


class RemnawaveService:
    """High-level operations on Remnawave panel used by the bot."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        kwargs: dict = {
            "base_url": settings.remnawave_base_url.rstrip("/"),
            "token": settings.remnawave_token,
        }
        if settings.remnawave_caddy_token:
            kwargs["caddy_token"] = settings.remnawave_caddy_token
        self.sdk = RemnawaveSDK(**kwargs)

    # ---- helpers ---------------------------------------------------------

    def _traffic_limit_bytes(self) -> int | None:
        gb = self._settings.remnawave_traffic_limit_gb
        if gb <= 0:
            return None
        return gb * 1024 * 1024 * 1024

    async def _resolve_squads(self) -> list[UUID]:
        configured = self._settings.remnawave_squad_uuids
        if configured:
            return [UUID(value) for value in configured]
        # No squads specified — try to attach the single available one.
        try:
            response = await self.sdk.internal_squads.get_internal_squads()
        except Exception:  # pragma: no cover - network / SDK issues
            logger.exception("Could not fetch internal squads from Remnawave")
            return []
        squads = (
            getattr(response, "internal_squads", None) or getattr(response, "squads", None) or []
        )
        uuids: list[UUID] = []
        for squad in squads:
            uuid = getattr(squad, "uuid", None)
            if uuid is not None:
                uuids.append(UUID(str(uuid)))
        return uuids

    @staticmethod
    def _make_username(telegram_id: int) -> str:
        return f"tg_{telegram_id}"

    # ---- public API ------------------------------------------------------

    async def find_user_by_telegram_id(self, telegram_id: int) -> UserResponseDto | None:
        """Return the first Remnawave user linked to a given Telegram ID, if any."""
        try:
            response = await self.sdk.users.get_users_by_telegram_id(str(telegram_id))
        except Exception:
            logger.exception("get_users_by_telegram_id failed for %s", telegram_id)
            return None
        users = getattr(response, "root", None) or list(response or [])
        return users[0] if users else None

    async def get_user_by_uuid(self, uuid: str) -> UserResponseDto | None:
        try:
            response = await self.sdk.users.get_user_by_uuid(uuid)
        except Exception:
            logger.exception("get_user_by_uuid failed for %s", uuid)
            return None
        return getattr(response, "response", None) or response  # type: ignore[return-value]

    async def create_or_extend(
        self,
        telegram_id: int,
        days: int,
        existing_uuid: str | None = None,
        existing_expire_at: datetime | None = None,
    ) -> UserResponseDto:
        """Create a new Remnawave user or extend an existing one by *days*.

        Returns the up-to-date :class:`UserResponseDto` from the panel.
        """
        now = datetime.now(UTC)

        if existing_uuid:
            base_expire = (
                existing_expire_at if (existing_expire_at and existing_expire_at > now) else now
            )
            new_expire = base_expire + timedelta(days=days)
            payload = UpdateUserRequestDto(
                uuid=UUID(existing_uuid),
                expire_at=new_expire,
                status="ACTIVE",  # type: ignore[arg-type]
            )
            logger.info(
                "Extending Remnawave user %s until %s", existing_uuid, new_expire.isoformat()
            )
            response = await self.sdk.users.update_user(payload)
            return getattr(response, "response", None) or response  # type: ignore[return-value]

        # Look up in case the user was created manually or by a previous run.
        existing = await self.find_user_by_telegram_id(telegram_id)
        if existing is not None:
            return await self.create_or_extend(
                telegram_id=telegram_id,
                days=days,
                existing_uuid=str(existing.uuid),
                existing_expire_at=getattr(existing, "expire_at", None),
            )

        username = self._make_username(telegram_id)
        squads = await self._resolve_squads()
        payload = CreateUserRequestDto(
            username=username,
            expire_at=now + timedelta(days=days),
            telegram_id=telegram_id,
            active_internal_squads=squads or None,
            traffic_limit_bytes=self._traffic_limit_bytes(),
        )
        logger.info("Creating Remnawave user %s for tg %s", username, telegram_id)
        response = await self.sdk.users.create_user(payload)
        return getattr(response, "response", None) or response  # type: ignore[return-value]

    async def disable(self, uuid: str) -> None:
        try:
            await self.sdk.users.disable_user(uuid)
        except Exception:
            logger.exception("disable_user failed for %s", uuid)
