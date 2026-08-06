"""Provider contracts and shared HTTP error handling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import httpx

from fund_monitor.domain import Asset, AssetKind, ProviderError, ProviderErrorKind, ProviderResult


class MarketProvider(Protocol):
    name: str
    supported_kinds: set[AssetKind]

    async def fetch(self, asset: Asset) -> ProviderResult: ...


class HttpProvider:
    timeout_seconds = 15.0

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.get(url, headers=headers, params=params, timeout=self.timeout_seconds)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await client.get(url, headers=headers, params=params)

    def _error(self, kind: ProviderErrorKind, message: str) -> ProviderResult:
        return ProviderResult(
            source=self.name,
            error=ProviderError(
                source=self.name,
                kind=kind,
                message=message,
                occurred_at=datetime.now(timezone.utc),
            ),
        )

    def _network_error(self, error: Exception) -> ProviderResult:
        if isinstance(error, httpx.TimeoutException):
            return self._error(ProviderErrorKind.TIMEOUT, "Data source request timed out")
        return self._error(ProviderErrorKind.NETWORK, "Data source request failed")
