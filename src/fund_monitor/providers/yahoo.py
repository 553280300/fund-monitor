"""Yahoo chart adapter for global index observations."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx

from fund_monitor.domain import Asset, AssetKind, Observation, ProviderError, ProviderErrorKind, ProviderResult
from fund_monitor.providers.base import HttpProvider


class YahooProvider(HttpProvider):
    name = "yahoo"
    supported_kinds = {AssetKind.GLOBAL_INDEX}
    _headers = {"User-Agent": "FundMonitor/0.1 (+local desktop application)"}

    async def fetch(self, asset: Asset) -> ProviderResult:
        ticker = asset.identifiers.get(self.name)
        if not ticker:
            return self._error(ProviderErrorKind.UNSUPPORTED, "Yahoo identifier is not configured")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}?range=1d&interval=1m"
        try:
            response = await self._get(url, headers=self._headers)
            response.raise_for_status()
            return self.parse(asset, response.json())
        except httpx.HTTPStatusError:
            return self._error(ProviderErrorKind.UNAVAILABLE, "Yahoo data source returned an error")
        except ValueError:
            return self._error(ProviderErrorKind.PARSE, "Yahoo data could not be parsed")
        except Exception as error:
            return self._network_error(error)

    @classmethod
    def parse(cls, asset: Asset, payload: dict) -> ProviderResult:
        try:
            meta = payload["chart"]["result"][0]["meta"]
            current = Decimal(str(meta["regularMarketPrice"]))
            previous_close = Decimal(str(meta["chartPreviousClose"]))
            if current <= 0 or previous_close <= 0:
                raise ValueError("market price is invalid")
            change = ((current - previous_close) / previous_close * Decimal("100")).quantize(Decimal("0.01"))
            return ProviderResult(
                source=cls.name,
                observation=Observation(
                    asset_id=asset.id or 0,
                    source=cls.name,
                    observed_at=datetime.now(timezone.utc),
                    value=current,
                    change_percent=change,
                    confirmed=True,
                    label=meta.get("shortName") or asset.name,
                ),
            )
        except (InvalidOperation, KeyError, IndexError, TypeError, ValueError):
            return ProviderResult(
                source=cls.name,
                error=ProviderError(
                    source=cls.name,
                    kind=ProviderErrorKind.PARSE,
                    message="Yahoo chart data could not be parsed",
                    occurred_at=datetime.now(timezone.utc),
                ),
            )
