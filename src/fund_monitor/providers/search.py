"""Asset search adapter so users can add assets by name or code only.

Uses the Eastmoney combined suggest endpoint, which covers Chinese indices,
funds, and exchange-traded funds. Stocks and other security types are filtered
out because the monitor targets funds, ETFs, and indices.

Queries may carry a market prefix (`sh588900`, `jj019860`, `sz399006`); the
prefix is stripped before searching. Candidates expose their possible Tencent
ticker forms so the panel can show which prefix will be used.
"""

from __future__ import annotations

import re

import httpx

from fund_monitor.domain import AssetCandidate, AssetKind
from fund_monitor.providers.base import HttpProvider

_SUGGEST_URL = "https://searchapi.eastmoney.com/api/suggest/get"
_SUGGEST_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"
_MARKET_PREFIX = {1: "sh", 0: "sz"}
_PREFIX_RE = re.compile(r"^(sh|sz|bj|jj|fu)[_\-]?(\d{6})$")
_IGNORED_SECURITY_TYPES = {
    "沪A",
    "深A",
    "沪B",
    "深B",
    "三板",
    "北交",
    "债券",
    "可转债",
    "港股",
    "美股",
    "期货",
    "期权",
    "新股",
    "开放式基金",
}


class EastmoneySearchProvider(HttpProvider):
    name = "eastmoney-search"
    _headers = {"User-Agent": "FundMonitor/0.1 (+local desktop application)"}

    @staticmethod
    def normalize_query(query: str) -> str:
        """Strip a market prefix (sh/sz/bj/jj/fu) so bare codes search cleanly."""
        query = query.strip()
        match = _PREFIX_RE.fullmatch(query.lower())
        return match.group(2) if match else query

    async def search(self, query: str) -> list[AssetCandidate]:
        query = self.normalize_query(query)
        if not query:
            return []
        response = await self._get(
            _SUGGEST_URL,
            headers=self._headers,
            params={"input": query, "type": "14", "count": "10", "token": _SUGGEST_TOKEN},
        )
        if response.status_code != 200:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        table = payload.get("QuotationCodeTable") or {}
        items = table.get("Data") or []
        candidates: list[AssetCandidate] = []
        for item in items:
            candidate = self._candidate(item)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    @staticmethod
    def _candidate(item: dict) -> AssetCandidate | None:
        code = str(item.get("Code") or "")
        name = str(item.get("Name") or "")
        security_type = str(item.get("SecurityTypeName") or "")
        if not code or not name:
            return None
        kind = EastmoneySearchProvider._kind_for(security_type, code, name)
        if kind is None:
            return None
        market_number = item.get("MktNum")
        market = _MARKET_PREFIX.get(int(market_number)) if market_number is not None else None
        return AssetCandidate(
            name=name,
            code=code,
            kind=kind,
            source="eastmoney" if kind in {AssetKind.FUND, AssetKind.ETF} else "tencent",
            description=security_type,
            market=market,
            ticker_hints=EastmoneySearchProvider._ticker_hints(kind, code, market),
        )

    @staticmethod
    def _ticker_hints(kind: AssetKind, code: str, market: str | None) -> list[str]:
        if kind == AssetKind.CN_INDEX:
            prefix = market or ("sz" if code.startswith("399") else "sh")
            return [f"{prefix}{code}（指数）"]
        hints: list[str] = []
        if code.startswith(("5", "1")):
            prefix = market or ("sz" if code.startswith("1") else "sh")
            hints.append(f"{prefix}{code}（场内）")
        hints.append(f"jj{code}（场外）")
        return hints

    @staticmethod
    def _kind_for(security_type: str, code: str, name: str) -> AssetKind | None:
        if security_type == "指数":
            return AssetKind.CN_INDEX
        if security_type in _IGNORED_SECURITY_TYPES:
            return None
        if security_type != "基金":
            return None  # Unknown security types are not monitored.
        if "ETF联接" in name.upper():
            return AssetKind.FUND
        if "ETF" in name.upper():
            return AssetKind.ETF
        if code.startswith(("5", "1")) and len(code) == 6:
            return AssetKind.ETF
        return AssetKind.FUND
