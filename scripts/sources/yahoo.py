"""数据源模块 — Yahoo Finance

Yahoo Finance API 提供海外指数实时数据（标普500、纳斯达克等）。
"""

import json
import ssl
import urllib.request
from typing import Optional


def fetch_sp500() -> Optional[dict]:
    """获取标普500实时数据"""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/^GSPC?range=1d&interval=1m"
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            d = json.loads(resp.read())
            result = d.get('chart', {}).get('result', [{}])[0]
            meta = result.get('meta', {})
            price = meta.get('regularMarketPrice', 0)
            prev = meta.get('chartPreviousClose', 1)
            if prev > 0 and price > 0:
                change_pct = round(((price - prev) / prev) * 100, 2)
                return {
                    "name": meta.get('shortName', 'S&P 500'),
                    "current": price,
                    "prev_close": prev,
                    "change_pct": change_pct,
                }
    except Exception as e:
        print(f"[WARN] Yahoo Finance 获取标普500失败: {e}")
    return None


def fetch(ticker: str) -> Optional[dict]:
    """
    获取 Yahoo Finance 数据
    
    Args:
        ticker: 支持 "sp500" / "^GSPC" 等
    """
    if ticker in ("sp500", "^GSPC"):
        return fetch_sp500()
    return None