"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram
    bot_token: str = Field(..., alias="BOT_TOKEN")
    admin_ids: list[int] = Field(default_factory=list, alias="ADMIN_IDS")
    support_username: str = Field(default="@support", alias="SUPPORT_USERNAME")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/vpnbot.sqlite3",
        alias="DATABASE_URL",
    )

    # Remnawave
    remnawave_base_url: str = Field(..., alias="REMNAWAVE_BASE_URL")
    remnawave_token: str = Field(..., alias="REMNAWAVE_TOKEN")
    remnawave_caddy_token: str | None = Field(default=None, alias="REMNAWAVE_CADDY_TOKEN")
    remnawave_squad_uuids: list[str] = Field(default_factory=list, alias="REMNAWAVE_SQUAD_UUIDS")
    remnawave_traffic_limit_gb: int = Field(default=0, alias="REMNAWAVE_TRAFFIC_LIMIT_GB", ge=0)

    # platega.io
    platega_merchant_id: str = Field(..., alias="PLATEGA_MERCHANT_ID")
    platega_secret: str = Field(..., alias="PLATEGA_SECRET")
    platega_base_url: str = Field(default="https://app.platega.io", alias="PLATEGA_BASE_URL")
    platega_payment_method: int = Field(default=2, alias="PLATEGA_PAYMENT_METHOD")
    platega_callback_url: str = Field(..., alias="PLATEGA_CALLBACK_URL")
    platega_return_url: str | None = Field(default=None, alias="PLATEGA_RETURN_URL")
    platega_fail_url: str | None = Field(default=None, alias="PLATEGA_FAIL_URL")

    # Webhook server
    webhook_host: str = Field(default="0.0.0.0", alias="WEBHOOK_HOST")
    webhook_port: int = Field(default=8080, alias="WEBHOOK_PORT", ge=1, le=65535)

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, str):
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        raise ValueError("ADMIN_IDS must be a comma-separated string or list")

    @field_validator("remnawave_squad_uuids", mode="before")
    @classmethod
    def _parse_squads(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        raise ValueError("REMNAWAVE_SQUAD_UUIDS must be a comma-separated string or list")

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
