"""Aggregator for aiogram routers."""

from __future__ import annotations

from aiogram import Router

from bot.handlers import admin, buy, profile, start
from bot.handlers import help as help_handlers


def build_router() -> Router:
    router = Router(name="root")
    router.include_router(start.router)
    router.include_router(buy.router)
    router.include_router(profile.router)
    router.include_router(help_handlers.router)
    router.include_router(admin.router)
    return router
