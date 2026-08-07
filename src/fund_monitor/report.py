"""Structured and text monitoring reports rendered from a run result."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fund_monitor.monitoring import RunResult


def resolve_timezone(timezone_name: str) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=8), name="UTC+08:00")


def _fmt_value(value: Decimal | None) -> str:
    if value is None:
        return "-"
    text = format(value, "f")
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".") if "." in text.rstrip("0") else text.split(".")[0]


def _fmt_change(value: Decimal | None) -> str:
    if value is None:
        return "-"
    number = float(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}%"


def _fmt_threshold(threshold: Decimal | None) -> str:
    if threshold is None:
        return "-"
    return f"\u2264 {_fmt_change(threshold)}"


def _delta_change(current: Decimal | None, previous: Decimal | None) -> str | None:
    if current is None or previous is None:
        return None
    delta = float(current) - float(previous)
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.2f}%"


def build_report(
    run: RunResult,
    *,
    schedule_times: list[str],
    timezone_name: str = "Asia/Shanghai",
) -> dict[str, Any]:
    """Convert a run into a structured report ready for text rendering or the panel."""
    local = run.ran_at.astimezone(resolve_timezone(timezone_name))
    period = run.period or local.strftime("%H:%M")

    results: list[dict[str, Any]] = []
    for asset in run.assets:
        status = asset.status
        if status == "normal":
            status_label = "正常"
        elif status == "alert":
            status_label = "异动"
        else:
            status_label = "异常"
        results.append(
            {
                "name": asset.name,
                "code": asset.code,
                "value": _fmt_value(asset.value),
                "change_percent": _fmt_change(asset.change_percent),
                "status": status,
                "status_label": status_label,
                "error": asset.error,
                "previous_change_percent": _fmt_change(asset.previous_change_percent),
                "delta_percent": _delta_change(asset.change_percent, asset.previous_change_percent),
                "alerts_created": asset.alerts_created,
                "rule_checks": [
                    {
                        "kind": check.kind,
                        "threshold": _fmt_threshold(check.threshold),
                        "triggered": check.triggered,
                    }
                    for check in asset.rule_checks
                    if check.threshold is not None
                ],
            }
        )

    nodes: list[dict[str, str]] = []
    for slot in schedule_times:
        nodes.append(
            {
                "time": slot,
                "state": "done" if slot == period else "pending",
                "current": slot == period,
            }
        )

    signals: list[dict[str, Any]] = []
    for asset in results:
        for check in asset["rule_checks"]:
            signals.append(
                {
                    "name": asset["name"],
                    "threshold": check["threshold"],
                    "current": asset["change_percent"],
                    "triggered": check["triggered"],
                }
            )

    title = f"基金监控 — {local.strftime('%Y-%m-%d %H:%M')}"
    return {
        "title": title,
        "ran_at": run.ran_at.isoformat(),
        "period": period,
        "date": local.strftime("%Y-%m-%d"),
        "results": results,
        "signals": signals,
        "nodes": nodes,
        "alerts_created": run.alerts_created,
        "errors": run.errors,
    }


def render_text(report: dict[str, Any]) -> str:
    """Render the structured report in the plain-text format users see today."""
    lines: list[str] = []
    lines.append(f"📊 {report['title']}")
    lines.append("")

    lines.append(f"🔹 本次结果（{report['period']} 时段）")
    for asset in report["results"]:
        if asset["error"]:
            lines.append(f"{asset['name']} ({asset['code']})")
            lines.append(f"• 状态: ⚠️ 数据源异常 — {asset['error']}")
            lines.append("")
            continue
        lines.append(f"{asset['name']} ({asset['code']})")
        lines.append(f"• 当前价: {asset['value']}")
        arrow = "↑" if asset["change_percent"].startswith("+") and asset["change_percent"] != "+0.00%" else "↓" if asset["change_percent"].startswith("-") else ""
        lines.append(f"• 涨跌幅: {asset['change_percent']} {arrow}".rstrip())
        lines.append(f"• 状态: {'✅ ' if asset['status'] == 'normal' else '🔔 '}{asset['status_label']}")
        lines.append("")
    if not report["results"]:
        lines.append("暂无监控资产。")
        lines.append("")

    lines.append("🔹 历史对比")
    any_history = any(asset["previous_change_percent"] != "-" for asset in report["results"])
    if not any_history:
        lines.append("本次为首次监控，无历史数据对比。")
    else:
        for asset in report["results"]:
            if asset["previous_change_percent"] == "-":
                continue
            lines.append(f"{asset['name']} ({asset['code']})")
            lines.append(f"• 上次涨跌幅: {asset['previous_change_percent']}")
            lines.append(f"• 本次涨跌幅: {asset['change_percent']}")
            delta = asset["delta_percent"] or ""
            lines.append(f"• 变化: {delta}")
            lines.append("")
    lines.append("")

    lines.append("🔹 触发信号")
    triggered = [signal for signal in report["signals"] if signal["triggered"]]
    if not triggered:
        lines.append("✅ 无触发信号，保持观望。")
        for signal in report["signals"]:
            lines.append(f"- {signal['name']} {signal['current']} → 未到 {signal['threshold']} 阈值 ❌")
    else:
        for signal in triggered:
            lines.append(f"- {signal['name']} {signal['current']} → 达到 {signal['threshold']} 阈值 ⚠️")
    lines.append("")

    lines.append("🔹 监控时间节点")
    for node in report["nodes"]:
        marker = "✅" if node["state"] == "done" else "⬜"
        suffix = " ⬅ 本次" if node["current"] else ""
        lines.append(f"{marker} {node['time']}{suffix}")
    lines.append("")

    if report["errors"]:
        lines.append(f"⚠️ {report['errors']} 个数据源异常，请检查数据源状态。")
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    """WeChat-friendly Markdown variant of the report (bold headings + lists)."""
    lines: list[str] = []
    lines.append(f"📊 **{report['title']}**")
    lines.append("")

    lines.append("🔹 **本次结果**")
    for asset in report["results"]:
        if asset["error"]:
            lines.append(f"🔍 **{asset['name']}** ({asset['code']})")
            lines.append(f"状态: ⚠️ 数据源异常 — {asset['error']}")
            lines.append("")
            continue
        lines.append(f"🔍 **{asset['name']}** ({asset['code']})")
        lines.append(f"当前: {asset['value']} ｜ 涨跌幅: {asset['change_percent']}")
        icon = "🔔" if asset["status"] == "alert" else "✅"
        lines.append(f"状态: {icon} {asset['status_label']}")
        lines.append("")
    if not report["results"]:
        lines.append("（暂无监控资产）")
        lines.append("")

    lines.append("🔹 **历史对比（vs 上次）**")
    any_history = any(asset["previous_change_percent"] != "-" for asset in report["results"])
    if not any_history:
        lines.append("本次为首次监控，无历史数据对比。")
    else:
        for asset in report["results"]:
            if asset["previous_change_percent"] == "-":
                lines.append(f"- {asset['name']}: — → {asset['change_percent']}（首次）")
                continue
            lines.append(
                f"- {asset['name']}: {asset['previous_change_percent']} → {asset['change_percent']}（{asset['delta_percent']}）"
            )
    lines.append("")

    lines.append("🔹 **触发信号**")
    triggered = [signal for signal in report["signals"] if signal["triggered"]]
    if not triggered:
        lines.append("✅ 无触发信号，保持观望。")
        for signal in report["signals"]:
            lines.append(f"- {signal['name']}: {signal['current']} 未到 {signal['threshold']} ❌")
    else:
        lines.append(f"🚨 共 {len(triggered)} 个信号触发！")
        for signal in triggered:
            lines.append(f"- {signal['name']}: {signal['current']} 已达 {signal['threshold']} ⚠️")
    lines.append("")

    lines.append("🔹 **监控时间节点**")
    for node in report["nodes"]:
        marker = "✅" if node["state"] == "done" else "⬜"
        suffix = " ← 本次" if node["current"] else ""
        lines.append(f"- {marker} {node['time']}{suffix}")
    lines.append("")

    if report["errors"]:
        lines.append(f"⚠️ {report['errors']} 个数据源异常，请检查。")
    return "\n".join(lines)


def render_html(report: dict[str, Any]) -> str:
    """Render the structured report as safe HTML for the local panel."""
    def esc(value: Any) -> str:
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    parts: list[str] = [f"<h3>{esc(report['title'])}</h3>"]

    parts.append("<h4>本次结果</h4>")
    for asset in report["results"]:
        if asset["error"]:
            parts.append(
                f"<div class='report-asset'><strong>{esc(asset['name'])}</strong> "
                f"<span class='badge badge-error'>数据源异常</span><div>{esc(asset['error'])}</div></div>"
            )
            continue
        badge_class = "badge-ok" if asset["status"] == "normal" else "badge-alert"
        parts.append(
            f"<div class='report-asset'><strong>{esc(asset['name'])}</strong> "
            f"<span class='badge {badge_class}'>{esc(asset['status_label'])}</span>"
            f"<div>当前价: <b>{esc(asset['value'])}</b> &nbsp; 涨跌幅: <b>{esc(asset['change_percent'])}</b></div></div>"
        )
    if not report["results"]:
        parts.append("<p class='empty'>暂无监控资产。</p>")

    parts.append("<h4>历史对比</h4>")
    any_history = any(asset["previous_change_percent"] != "-" for asset in report["results"])
    if not any_history:
        parts.append("<p>本次为首次监控，无历史数据对比。</p>")
    else:
        for asset in report["results"]:
            if asset["previous_change_percent"] == "-":
                continue
            parts.append(
                f"<div class='report-asset'><strong>{esc(asset['name'])}</strong>"
                f"<div>上次 {esc(asset['previous_change_percent'])} → 本次 {esc(asset['change_percent'])}"
                f" <b>{esc(asset['delta_percent'])}</b></div></div>"
            )

    parts.append("<h4>触发信号</h4>")
    if not report["signals"]:
        parts.append("<p>✅ 无触发信号。</p>")
    else:
        for signal in report["signals"]:
            mark = "⚠️" if signal["triggered"] else "✅"
            parts.append(
                f"<div class='report-asset'>{mark} <strong>{esc(signal['name'])}</strong> "
                f"当前 {esc(signal['current'])}，阈值 {esc(signal['threshold'])}</div>"
            )

    parts.append("<h4>监控时间节点</h4>")
    parts.append("<div class='nodes'>" + " ".join(
        f"<span class='node {'node-done' if node['state'] == 'done' else ''}'>{'✅' if node['state'] == 'done' else '⬜'} {esc(node['time'])}{' ⬅ 本次' if node['current'] else ''}</span>"
        for node in report["nodes"]
    ) + "</div>")

    return "".join(parts)
