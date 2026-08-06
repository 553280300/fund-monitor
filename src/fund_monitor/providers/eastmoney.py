"""Eastmoney adapter for confirmed fund NAV history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from fund_monitor.domain import Asset, AssetKind, Observation, ProviderError, ProviderErrorKind, ProviderResult
from fund_monitor.providers.base import HttpProvider


class EastmoneyProvider(HttpProvider):
    name = "eastmoney"
    supported_kinds = {AssetKind.FUND, AssetKind.ETF}
    _headers = {
        "User-Agent": "FundMonitor/0.1 (+local desktop application)",
        "Referer": "https://fundf10.eastmoney.com/",
    }

    async def fetch(self, asset: Asset) -> ProviderResult:
        code = asset.identifiers.get(self.name)
        if not code:
            return self._error(ProviderErrorKind.UNSUPPORTED, "Eastmoney identifier is not configured")
        url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex=1&pageSize=1"
        try:
            response = await self._get(url, headers=self._headers)
            response.raise_for_status()
            payload = self._decode_jsonp(response.text)
            return self.parse_history(asset, payload)
        except httpx.HTTPStatusError:
            return self._error(ProviderErrorKind.UNAVAILABLE, "Eastmoney data source returned an error")
        except (json.JSONDecodeError, ValueError):
            return self._error(ProviderErrorKind.PARSE, "Eastmoney data could not be parsed")
        except Exception as error:
            return self._network_error(error)

    @classmethod
    def parse_history(cls, asset: Asset, payload: dict) -> ProviderResult:
        try:
            data = payload.get("Data", {})
            rows = data.get("LSJZList", []) if isinstance(data, dict) else []
            if not rows:
                raise ValueError("NAV history is empty")
            latest = rows[0]
            observed_at = datetime.fromisoformat(latest["FSRQ"]).replace(tzinfo=timezone.utc)
            return ProviderResult(
                source=cls.name,
                observation=Observation(
                    asset_id=asset.id or 0,
                    source=cls.name,
                    observed_at=observed_at,
                    value=Decimal(latest["DWJZ"]),
                    change_percent=Decimal(latest.get("JZZZL") or "0"),
                    confirmed=True,
                    label=asset.name,
                ),
            )
        except (InvalidOperation, KeyError, TypeError, ValueError):
            return ProviderResult(
                source=cls.name,
                error=ProviderError(
                    source=cls.name,
                    kind=ProviderErrorKind.PARSE,
                    message="Eastmoney NAV data could not be parsed",
                    occurred_at=datetime.now(timezone.utc),
                ),
            )

    @staticmethod
    def _decode_jsonp(text: str) -> dict:
        text = text.strip()
        if text.startswith("{"):
            return json.loads(text)
        start = text.index("(") + 1
        end = text.rindex(")")
        return json.loads(text[start:end])
