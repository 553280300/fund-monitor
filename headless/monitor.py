"""Single-run fund/index monitor for GitHub Actions.

Reads a YAML config, fetches live quotes from Tencent, evaluates threshold
rules, persists the latest observations to `state.json` (committed by the
workflow) so the next run can show a history comparison, and pushes the full
report to PushPlus (WeChat) when configured.

Report layout follows the established standard:
    title / per-asset status / history comparison table / daily nodes /
    threshold reference / alert block.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import yaml

TENCENT_QUOTE_URL = "https://web.sqt.gtimg.cn/q={ticker}"
PUSHPLUS_URL = "https://www.pushplus.plus/send"
DEFAULT_SCHEDULE = ["02:00", "06:00", "10:00", "14:00"]

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
    else:
        if len(fields) < 8:
            raise ValueError(f"{ticker}: 基金行情不完整")
        current = Decimal(fields[5])
        change = Decimal(fields[7])
    return current, change


def fmt_value(value: Decimal | None) -> str:
    if value is None:
        return "-"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def fmt_change(value: Decimal | None) -> str:
    if value is None:
        return "-"
    number = float(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}%"


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_report(
    rows: list[dict],
    *,
    title: str,
    period: str,
    schedule: list[str],
) -> str:
    bar = "━" * 27
    lines: list[str] = [f"📊 {title}", "", bar, ""]

    # ① 各标的状态
    for row in rows:
        if row["error"]:
            lines.append(f"🔍 {row['name']} ({row['code']})")
            lines.append(f"   状态: ⚠️ 数据源异常 — {row['error']}")
            lines.append("")
            continue
        lines.append(f"🔍 {row['name']} ({row['code']})")
        lines.append(f"   当前: {row['value_text']}  |  涨跌幅: {row['change_text']}")
        state_icon = "🔔" if row["triggered"] else "✅"
        lines.append(f"   状态: {state_icon} {row['status_text']}")
        lines.append("")
    if not rows:
        lines.append("（暂无监控资产）")
        lines.append("")

    # ② 历史对比（vs 上次）
    lines.append(bar)
    lines.append("")
    lines.append("📆 历史对比（vs 上次）")
    lines.append("| 标的 | 上次 | 本次 | 变化 |")
    lines.append("|------|------|------|:----:|")
    for row in rows:
        if row["previous_change_text"] == "-":
            lines.append(f"| {row['name']} | — | {row['change_text']} | — |")
            continue
        lines.append(
            f"| {row['name']} | {row['previous_change_text']} | {row['change_text']} | {row['delta_icon']} |"
        )
    lines.append("")

    # ③ 今日监控节点
    lines.append(bar)
    lines.append("")
    lines.append("⏰ 今日监控节点")
    for slot in schedule:
        if slot == period:
            lines.append(f"   ✅ {slot} ← 本次")
        elif slot < period:
            lines.append(f"   ✅ {slot} — 已完成")
        else:
            lines.append(f"   ⏳ {slot} — 待执行")
    lines.append("")

    # ④ 阈值参考
    lines.append(bar)
    lines.append("")
    lines.append("📏 阈值参考：")
    for row in rows:
        if row["threshold"] is None:
            continue
        action = f" → {row['action']}" if row.get("action") else ""
        lines.append(f"- {row['name']} ≤ {row['threshold']}%{action}")
    lines.append("")

    # ⑤ 结论（触发 / 装死）
    triggered = [row for row in rows if row["triggered"]]
    if triggered:
        lines.append(f"🚨 共 {len(triggered)} 个信号触发！")
        for row in triggered:
            action = f"（{row['action']}）" if row.get("action") else ""
            lines.append(f"- {row['name']} {row['change_text']} 已达阈值 ≤ {row['threshold']}%{action}")
        lines.append("")
        lines.append("建议按上述操作执行，注意风险，理性投资。")
    else:
        lines.append("结论：所有标的涨跌均未达阈值。装死🙈 无操作。")
    lines.append("")
    return "\n".join(lines)


def push_pushplus(token: str, title: str, content: str) -> None:
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


def push_safe(token: str, title: str, content: str) -> bool:
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
    parser.add_argument("--state", default="state.json", help="Path to state file")
    parser.add_argument("--output", default=None, help="Write report text to a file")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    timezone_name = config.get("timezone", "Asia/Shanghai")
    tz = resolve_timezone(timezone_name)
    now = datetime.now(tz)
    if now.weekday() >= 5:
        print("非交易日（周末），跳过本次监控。")
        return 0

    schedule = [str(slot) for slot in config.get("schedule", DEFAULT_SCHEDULE)]
    now_time = now.strftime("%H:%M")
    reached = [slot for slot in schedule if slot <= now_time]
    period = reached[-1] if reached else (schedule[0] if schedule else now_time)

    assets = config.get("assets", [])
    if not assets:
        print("配置中没有资产，跳过。")
        return 0

    state_path = Path(args.state)
    state = load_state(state_path)
    history = state.get("history", {})  # code -> last known observation

    title = f"基金监控 {now.strftime('%Y-%m-%d %H:%M')}（交易日）"
    rows: list[dict] = []
    alerts: list[dict] = []

    with httpx.Client(timeout=15, headers={"User-Agent": "FundMonitorHeadless/0.1"}) as client:
        for asset in assets:
            row: dict = {
                "name": asset["name"],
                "code": asset["code"],
                "kind": asset.get("kind", "fund"),
                "threshold": asset.get("threshold"),
                "action": asset.get("action"),
                "value": None,
                "value_text": "-",
                "change": None,
                "change_text": "-",
                "previous_change_text": "-",
                "delta_icon": "—",
                "triggered": False,
                "error": None,
            }
            previous = history.get(asset["code"])
            try:
                value, change = fetch_quote(client, asset["code"], row["kind"])
                row["value"] = value
                row["value_text"] = fmt_value(value)
                row["change"] = change
                row["change_text"] = fmt_change(change)
                if previous is not None:
                    row["previous_change_text"] = fmt_change(Decimal(str(previous["change"])))
                    delta = float(change) - float(previous["change"])
                    row["delta_icon"] = "↑" if delta > 0.005 else ("↓" if delta < -0.005 else "→")
                threshold = row["threshold"]
                if threshold is not None:
                    row["triggered"] = change <= Decimal(str(threshold))
                    row["status_text"] = "正常（未触发）" if not row["triggered"] else "触发阈值！"
                    if row["triggered"]:
                        alerts.append(row)
                else:
                    row["status_text"] = "正常"
                # Persist this observation for the next run's comparison.
                history[asset["code"]] = {"change": float(change), "value": str(value), "period": period}
            except Exception as error:
                row["error"] = str(error)
                row["status_text"] = "异常"
            rows.append(row)

    report = build_report(rows, title=title, period=period, schedule=schedule)

    state["history"] = history
    state["updated_at"] = now.isoformat()
    save_state(state_path, state)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")

    print(report)

    summary = "；".join(
        f"{row['name']}: {row['change_text'] or '-'}（{'触发' if row['triggered'] else '正常' if not row['error'] else '异常'}）"
        for row in rows
    )
    print("\n--- 汇总 ---")
    print(summary)

    pushplus_token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not pushplus_token:
        print("\n[未配置 PUSHPLUS_TOKEN，跳过推送]")
        return 0

    sent = False
    if alerts:
        alert_title = f"🚨 {len(alerts)} 项触发预警 {now.strftime('%H:%M')}"
        alert_lines = ["🚨 触发信号："]
        for row in alerts:
            action = f"（{row['action']}）" if row.get("action") else ""
            alert_lines.append(f"- **{row['name']}** {row['change_text']} 已达阈值 ≤ {row['threshold']}%{action}")
        sent = push_safe(pushplus_token, alert_title, "\n".join(alert_lines))
        if sent:
            print(f"[已推送告警：{alert_title}]")
    if push_safe(pushplus_token, f"📊 {title}", report):
        print("[已推送报告到微信(PushPlus)]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
