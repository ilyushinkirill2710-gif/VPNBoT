"""Client for the platega.io Payment API.

Documentation: https://docs.platega.io/
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from bot.config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CreatedTransaction:
    transaction_id: str
    redirect: str
    status: str
    raw: dict[str, Any]


class PlategaError(RuntimeError):
    """Raised when platega.io returns a non-2xx response."""


class PlategaClient:
    """Async client for platega.io. Uses ``X-MerchantId`` / ``X-Secret`` auth."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.platega_base_url.rstrip("/"),
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "X-MerchantId": settings.platega_merchant_id,
                "X-Secret": settings.platega_secret,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_transaction(
        self,
        *,
        amount: float,
        description: str,
        payload: str | None = None,
        payment_method: int | None = None,
        currency: str = "RUB",
    ) -> CreatedTransaction:
        """Create a payment and return redirect URL + transaction id."""
        body: dict[str, Any] = {
            "paymentMethod": payment_method or self._settings.platega_payment_method,
            "paymentDetails": {"amount": amount, "currency": currency},
            "description": description,
        }
        if self._settings.platega_return_url:
            body["return"] = self._settings.platega_return_url
        if self._settings.platega_fail_url:
            body["failedUrl"] = self._settings.platega_fail_url
        if payload:
            body["payload"] = payload

        response = await self._client.post("/transaction/process", content=json.dumps(body))
        if response.status_code >= 400:
            logger.error(
                "platega.io create failed: %s %s", response.status_code, response.text[:500]
            )
            raise PlategaError(f"platega.io returned {response.status_code}: {response.text[:200]}")
        data = response.json()
        return CreatedTransaction(
            transaction_id=str(data["transactionId"]),
            redirect=str(data.get("redirect") or data.get("return") or ""),
            status=str(data.get("status", "PENDING")),
            raw=data,
        )

    async def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        """Fetch current status of a transaction."""
        response = await self._client.get(f"/transaction/{transaction_id}")
        if response.status_code >= 400:
            raise PlategaError(
                f"platega.io status request returned {response.status_code}: {response.text[:200]}"
            )
        return response.json()

    def verify_callback(self, headers: dict[str, str]) -> bool:
        """Check the ``X-MerchantId`` / ``X-Secret`` sent in a callback."""
        # Headers are case-insensitive; httpx / aiohttp normalise them.
        merchant = headers.get("X-MerchantId") or headers.get("x-merchantid")
        secret = headers.get("X-Secret") or headers.get("x-secret")
        return (
            merchant == self._settings.platega_merchant_id
            and secret == self._settings.platega_secret
        )
