"""Generate headless/config.yaml from asset names/codes via Eastmoney search.

Used by the `update-config` GitHub Actions workflow (Run workflow form):
    python headless/generate_config.py --assets "科创50, 019860: -1.5"

Each item may be a plain name/code, or "name:threshold" to attach a rule.
"""

from __future__ import annotations

import argparse

import httpx
import yaml

SUGGEST_URL = "https://searchapi.eastmoney.com/api/suggest/get"
SUGGEST_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"
CONFIG_PATH = "headless/config.yaml"
_MARKET_PREFIX = {1: "sh", 0: "sz"}
_IGNORED_TYPES = {"沪A", "深A", "沪B", "深B", "三板", "北交", "债券", "可转债", "港股", "美股", "期货", "期权", "新股", "开放式基金"}


def search(query: str) -> list[dict]:
    with httpx.Client(timeout=15) as client:
        response = client.get(
            SUGGEST_URL,
            params={"input": query, "type": "14", "count": "5", "token": SUGGEST_TOKEN},
        )
        payload = response.json()
    items = (payload.get("QuotationCodeTable") or {}).get("Data") or []
    return [candidate for item in items if (candidate := _parse(item))]


def _parse(item: dict) -> dict | None:
    code = str(item.get("Code") or "")
    name = str(item.get("Name") or "")
    security_type = str(item.get("SecurityTypeName") or "")
    if not code or not name:
        return None
    if security_type == "指数":
        kind = "cn_index"
    elif security_type in _IGNORED_TYPES or security_type != "基金":
        return None
    elif "ETF联接" in name.upper() or ("ETF" not in name.upper() and not code.startswith(("5", "1"))):
        kind = "fund"
    else:
        kind = "etf"

    market_number = item.get("MktNum")
    market = _MARKET_PREFIX.get(int(market_number)) if market_number is not None else None
    if kind == "cn_index":
        prefix = market or ("sz" if code.startswith("399") else "sh")
    elif kind == "etf":
        # Exchange-traded funds use the exchange prefix (sh/sz + code).
        prefix = market or ("sz" if code.startswith("1") else "sh")
    else:
        # Open-end funds use the jj prefix.
        prefix = "jj"
    ticker = f"{prefix}{code}"
    return {"name": name, "code": ticker, "kind": kind}


def build_config(entries: list[str]) -> str:
    assets: list[dict] = []
    warnings: list[str] = []
    with httpx.Client(timeout=15) as client:
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            threshold: str | None = None
            if ":" in entry:
                entry, _, threshold = entry.partition(":")
                entry = entry.strip()
                threshold = threshold.strip() or None
            matches = search(entry)
            if not matches:
                warnings.append(f"未找到「{entry}」")
                continue
            asset = matches[0]
            if len(matches) > 1:
                print(f"「{entry}」匹配多个，已选用第一个：{asset['name']}（{asset['code']}）")
            if threshold is not None:
                asset = {**asset, "threshold": float(threshold)}
            assets.append(asset)

    config = {
        "timezone": "Asia/Shanghai",
        "assets": assets,
        "channels": {"pushplus": {"token_env": "PUSHPLUS_TOKEN"}},
    }
    text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    if warnings:
        text = "# 以下未找到匹配，请检查名称/代码：\n" + "\n".join(f"# - {w}" for w in warnings) + "\n" + text
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate headless config from asset names/codes")
    parser.add_argument("--assets", required=True, help="Comma-separated names/codes, optional ':threshold' each")
    parser.add_argument("--output", default=CONFIG_PATH, help="Output YAML path")
    args = parser.parse_args(argv)

    entries = [part.strip() for part in args.assets.split(",")]
    content = build_config(entries)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(content)
    print(f"\n[已写入 {args.output}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
