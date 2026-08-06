"""Single-run fund/index monitor for GitHub Actions.

Reads a YAML config, fetches live quotes from Tencent (real-time), evaluates
threshold rules, and pushes alerts/report to PushPlus (WeChat) when configured.

Designed to run as a scheduled GitHub Actions job; also works locally:
    python monitor.py --config config.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import yaml

TENCENT_QUOTE_URL = "https://web.sqt.gtimg.cn/q={ticker}"
PUSHPLUS_URL = "https://www.pushplus.plus/send"


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def resolve_timezone(name: str) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=8), name="UTC+08:00")


def fetch_quote(client: httpx.Client, ticker: str, kind: str) -> tuple[Decimal, Decimal]:
    """Return (current, change_percent) from the Tencent quote endpoint."""
    response = client.get(TENCENT_QUOTE_URL.format(ticker=ticker), timeout=15)
    response.raise_for_status()
    match = re.search(r'="(.+)"', response.content.decode("gbk", errors="replace"))
    if match is None:
        raise ValueError(f"{ticker}: 无法解析行情响应")
    fields = match.group(1).split("~")
    if kind == "cn_index":
        if len(fields) < 5:
            raise ValueError(f"{ticker}: 指数行情不完整")
        current = Decimal(fields[3])
        previous_close = Decimal(fields[4])
        if previous_close <= 0:
            raise ValueError(f"{ticker}: 无效的昨收")
        change = (current - previous_close) / previous_close * Decimal("100")
    elif kind == "etf":
        if len(fields) < 33:
            raise ValueError(f"{ticker}: ETF 行情不完整")
        current = Decimal(fields[3])
        change = Decimal(fields[32])
    else:  # fund (open-end, jj prefix)
        if len(fields) < 8:
            raise ValueError(f"{ticker}: 基金行情不完整")
        current = Decimal(fields[5])
        change = Decimal(fields[7])
    return current, change


def fmt_value(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def fmt_change(value: Decimal) -> str:
    number = float(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}%"


def build_report(rows: list[dict], *, title: str) -> str:
    lines = [f"## {title}", ""]
    for row in rows:
        lines.append(f"**{row['name']}** ({row['code']})")
        if row["error"]:
            lines.append(f"- 状态: ⚠️ {row['error']}")
        else:
            arrow = "↑" if row["change"] > 0 else "↓" if row["change"] < 0 else ""
            lines.append(f"- 当前价: {row['value_text']}")
            lines.append(f"- 涨跌幅: {row['change_text']} {arrow}".rstrip())
            if row["threshold"] is not None:
                mark = "⚠️ 已触发" if row["triggered"] else "✅ 未触发"
                lines.append(f"- 阈值: ≤ {row['threshold']}% → {mark}")
        lines.append("")
    return "\n".join(lines)


def push_pushplus(token: str, title: str, content: str) -> None:
    """PushPlus (WeChat push, free ~200/day). Content is Markdown."""
    with httpx.Client(timeout=15) as client:
        response = client.get(
            PUSHPLUS_URL,
            params={"token": token, "title": title, "content": content, "template": "markdown"},
        )
    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(f"PushPlus 返回异常：{response.text[:200]}")
    if result.get("code") != 200:
        raise RuntimeError(result.get("msg") or "PushPlus 推送失败")


def push_pushplus_safe(token: str, title: str, content: str) -> bool:
    """Push to PushPlus; failures are isolated and reported, never fatal."""
    if not token:
        return False
    try:
        push_pushplus(token, title, content)
        return True
    except Exception as error:
        print(f"[PushPlus推送失败] {error}", file=sys.stderr)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fund/index monitor (headless)")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    timezone_name = config.get("timezone", "Asia/Shanghai")
    tz = resolve_timezone(timezone_name)
    now = datetime.now(tz)
    if now.weekday() >= 5:
        print("非交易日（周末），跳过本次监控。")
        return 0

    assets = config.get("assets", [])
    if not assets:
        print("配置中没有资产，跳过。")
        return 0

    title = f"基金监控 {now.strftime('%Y-%m-%d %H:%M')}（交易日）"
    rows: list[dict] = []
    alerts: list[dict] = []
    errors = 0

    with httpx.Client(timeout=15, headers={"User-Agent": "FundMonitorHeadless/0.1"}) as client:
        for asset in assets:
            row: dict = {
                "name": asset["name"],
                "code": asset["code"],
                "kind": asset.get("kind", "fund"),
                "threshold": asset.get("threshold"),
                "value": None,
                "value_text": "-",
                "change": None,
                "change_text": "-",
                "triggered": False,
                "error": None,
            }
            try:
                value, change = fetch_quote(client, asset["code"], row["kind"])
                row["value"] = value
                row["value_text"] = fmt_value(value)
                row["change"] = change
                row["change_text"] = fmt_change(change)
                threshold = row["threshold"]
                if threshold is not None:
                    row["triggered"] = change <= Decimal(str(threshold))
                    if row["triggered"]:
                        alerts.append(row)
            except Exception as error:  # Isolate per-asset failures.
                row["error"] = str(error)
                errors += 1
            rows.append(row)

    report = build_report(rows, title=title)
    print(report)

    summary = []
    for row in rows:
        state = "触发" if row["triggered"] else "正常" if not row["error"] else "异常"
        summary.append(f"{row['name']}: {row['change_text'] or '-'}（{state}）")
    print("\n--- 汇总 ---")
    print("；".join(summary))
    if errors:
        print(f"{errors} 个资产获取失败")

    pushplus_token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not pushplus_token:
        print("\n[未配置 PUSHPLUS_TOKEN，跳过推送]")
        return 0

    sent = False
    if alerts:
        alert_title = f"⚠️ {len(alerts)} 项触发预警 {now.strftime('%H:%M')}"
        alert_desp = "\n".join(
            f"- **{a['name']}** {a['change_text']}（阈值 ≤ {a['threshold']}%）" for a in alerts
        )
        sent = push_pushplus_safe(pushplus_token, alert_title, alert_desp)
        if sent:
            print(f"[已推送告警：{alert_title}]")
    if push_pushplus_safe(pushplus_token, f"📊 {title}", report):
        print("[已推送报告到微信(PushPlus)]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
