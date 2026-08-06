from datetime import datetime, timezone

import pytest

from fund_monitor.domain import Asset, AssetKind, Observation, ProviderError, ProviderErrorKind, ProviderResult
from fund_monitor.providers.base import MarketProvider
from fund_monitor.providers.registry import ProviderRegistry


class TimeoutProvider:
    name = "timeout"
    supported_kinds = {AssetKind.FUND}

    async def fetch(self, asset: Asset) -> ProviderResult:
        return ProviderResult(
            source=self.name,
            error=ProviderError(
                source=self.name,
                kind=ProviderErrorKind.TIMEOUT,
                message="Timed out",
                occurred_at=datetime.now(timezone.utc),
            ),
        )


class SuccessProvider:
    name = "success"
    supported_kinds = {AssetKind.FUND}

    async def fetch(self, asset: Asset) -> ProviderResult:
        return ProviderResult(
            source=self.name,
            observation=Observation(
                asset_id=asset.id or 0,
                source=self.name,
                observed_at=datetime.now(timezone.utc),
                value=1,
            ),
        )


@pytest.mark.asyncio
async def test_registry_uses_next_provider_after_error() -> None:
    asset = Asset(id=1, name="Fund", kind=AssetKind.FUND, identifiers={"x": "1"})
    registry = ProviderRegistry([TimeoutProvider(), SuccessProvider()])

    result = await registry.fetch_with_fallback(asset)

    assert result.source == "success"
    assert result.observation is not None
