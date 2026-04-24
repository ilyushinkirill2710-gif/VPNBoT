"""Subscription tariffs catalog.

Edit the :data:`TARIFFS` list below to adjust prices or add new plans.
Each tariff has a stable ``code`` used as a reference in the database
and in payment payloads. Do not change codes after payments exist.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tariff:
    code: str
    title: str
    days: int
    price_rub: int

    @property
    def price_label(self) -> str:
        return f"{self.price_rub}\u202f\u20bd"  # NARROW NO-BREAK SPACE + RUB sign

    @property
    def menu_label(self) -> str:
        return f"{self.title} — {self.price_label}"


TARIFFS: tuple[Tariff, ...] = (
    Tariff(code="1m", title="1 месяц", days=30, price_rub=80),
    # 3 месяца — скидка 20 ₽ относительно трёх одиночных месяцев (80×3 − 20 = 220).
    Tariff(code="3m", title="3 месяца", days=90, price_rub=220),
)


def iter_tariffs() -> Iterable[Tariff]:
    return TARIFFS


def get_tariff(code: str) -> Tariff | None:
    for tariff in TARIFFS:
        if tariff.code == code:
            return tariff
    return None
