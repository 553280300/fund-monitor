"""Tencent quote adapter for fund estimates and Chinese indices."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from fund_monitor.domain import Asset, AssetKind, Observation, ProviderErrorKind, ProviderResult
from fund_monitor.providers.base import HttpProvider


class TencentProvider(HttpProvider):
    name = "tencent"
    supported_kinds = {AssetKind.FUND, AssetKind.ETF, AssetKind.CN_INDEX}
    _headers = {"User-Agent": "FundMonitor/0.1 (+local desktop application)"}

    async def fetch(self, asset: Asset) -> ProviderResult:
        ticker = asset.identifiers.get(self.name)
        if not ticker:
            return self._error(ProviderErrorKind.UNSUPPORTED, "Tencent identifier is not configured")
        try:
            response = await self._get(f"https://web.sqt.gtimg.cn/q={ticker}", headers=self._headers)
            response.raise_for_status()
            return self.parse(asset, response.content.decode("gbk", errors="replace"))
        except httpx.HTTPStatusError:
            return self._error(ProviderErrorKind.UNAVAILABLE, "Tencent data source returned an error")
        except Exception as error:
            return self._network_error(error)

    @classmethod
    def parse(cls, asset: Asset, raw: str) -> ProviderResult:
        try:
            match = re.search(r'="(.+)"', raw)
            if match is None:
                raise ValueError("quote payload does not contain a value")
            fields = match.group(1).split("~")
            if asset.kind == AssetKind.CN_INDEX:
                if len(fields) < 5:
                    raise ValueError("index quote is incomplete")
                current = Decimal(fields[3])
                previous_close = Decimal(fields[4])
                if previous_close <= 0:
                    raise ValueError("index previous close is invalid")
                change = ((current - previous_close) / previous_close * Decimal("100")).quantize(Decimal("0.01"))
                confirmed = True
            elif asset.kind == AssetKind.ETF:
                # Exchange-traded funds use the stock layout: price at 3,
                # change percent at 32 (change amount at 31).
                if len(fields) < 33:
                    raise ValueError("etf quote is incomplete")
                current = Decimal(fields[3])
                change = Decimal(fields[32])
                confirmed = False
            else:
                # Open-end funds use the compact layout: estimate at 5,
                # change percent at 7 when the full payload is present.
                if len(fields) < 7:
                    raise ValueError("fund quote is incomplete")
                value_index = 5 if len(fields) >= 8 else len(fields) - 3
                change_index = 7 if len(fields) >= 8 else len(fields) - 1
                current = Decimal(fields[value_index])
                change = Decimal(fields[change_index])
                confirmed = False
            return ProviderResult(
                source=cls.name,
                observation=Observation(
                    asset_id=asset.id or 0,
                    source=cls.name,
                    observed_at=datetime.now(timezone.utc),
                    value=current,
                    change_percent=change,
                    confirmed=confirmed,
                    label=fields[1] or asset.name,
                ),
            )
        except (InvalidOperation, ValueError, IndexError):
            return ProviderResult(
                source=cls.name,
                error=cls._static_error("Tencent quote could not be parsed"),
            )

    @staticmethod
    def _static_error(message: str):
        from fund_monitor.domain import ProviderError

        return ProviderError(
            source=TencentProvider.name,
            kind=ProviderErrorKind.PARSE,
            message=message,
            occurred_at=datetime.now(timezone.utc),
        )
