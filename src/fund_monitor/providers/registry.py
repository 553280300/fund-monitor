"""Capability-based provider selection and fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from fund_monitor.domain import Asset, ProviderError, ProviderErrorKind, ProviderResult
from fund_monitor.providers.base import MarketProvider


class ProviderRegistry:
    def __init__(self, providers: Iterable[MarketProvider]) -> None:
        self._providers = list(providers)

    def for_asset(self, asset: Asset) -> list[MarketProvider]:
        return [provider for provider in self._providers if asset.kind in provider.supported_kinds]

    async def fetch_with_fallback(self, asset: Asset) -> ProviderResult:
        compatible = self.for_asset(asset)
        if not compatible:
            return ProviderResult(
                source="registry",
                error=ProviderError(
                    source="registry",
                    kind=ProviderErrorKind.UNSUPPORTED,
                    message=f"No provider supports asset kind {asset.kind.value}",
                    occurred_at=datetime.now(timezone.utc),
                ),
            )

        failures: list[str] = []
        for provider in compatible:
            result = await provider.fetch(asset)
            if result.observation is not None or result.events:
                return result
            if result.error is not None:
                failures.append(result.error.message)

        return ProviderResult(
            source="registry",
            error=ProviderError(
                source="registry",
                kind=ProviderErrorKind.UNAVAILABLE,
                message="; ".join(failures) or "All compatible providers failed",
                occurred_at=datetime.now(timezone.utc),
            ),
        )
