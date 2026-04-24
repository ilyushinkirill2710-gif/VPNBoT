"""Smoke tests: every module must import and tariffs must be well-formed."""

from __future__ import annotations

import importlib
import os

import pytest


def _set_env() -> None:
    os.environ.setdefault("BOT_TOKEN", "123:TEST")
    os.environ.setdefault("REMNAWAVE_BASE_URL", "https://example.com")
    os.environ.setdefault("REMNAWAVE_TOKEN", "test-token")
    os.environ.setdefault("PLATEGA_MERCHANT_ID", "00000000-0000-0000-0000-000000000000")
    os.environ.setdefault("PLATEGA_SECRET", "secret")
    os.environ.setdefault("PLATEGA_CALLBACK_URL", "https://example.com/platega/callback")


@pytest.mark.parametrize(
    "module",
    [
        "bot",
        "bot.config",
        "bot.db.models",
        "bot.db.session",
        "bot.handlers",
        "bot.handlers.admin",
        "bot.handlers.buy",
        "bot.handlers.help",
        "bot.handlers.profile",
        "bot.handlers.start",
        "bot.keyboards.menu",
        "bot.middlewares",
        "bot.services.platega",
        "bot.services.remnawave",
        "bot.services.subscriptions",
        "bot.services.tariffs",
        "bot.webhook.server",
    ],
)
def test_import(module: str) -> None:
    _set_env()
    importlib.import_module(module)


def test_tariffs_are_well_formed() -> None:
    _set_env()
    from bot.services.tariffs import TARIFFS, get_tariff

    assert TARIFFS, "TARIFFS must not be empty"
    codes = [t.code for t in TARIFFS]
    assert len(codes) == len(set(codes)), "tariff codes must be unique"
    for tariff in TARIFFS:
        assert tariff.days > 0
        assert tariff.price_rub > 0
        assert get_tariff(tariff.code) is tariff


def test_settings_loads() -> None:
    _set_env()
    from bot.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    settings = get_settings()
    assert settings.bot_token == "123:TEST"
    assert settings.platega_payment_method == 2
