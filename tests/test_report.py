"""Report generation from run results, in structured and user-facing text forms."""

from datetime import datetime, timezone
from decimal import Decimal

from fund_monitor.monitoring import AssetResult, RuleCheck, RunResult
from fund_monitor.report import build_report, render_text


def _run(
    assets: list[AssetResult],
    *,
    period: str | None = "02:00",
    alerts_created: int = 0,
    errors: int = 0,
) -> RunResult:
    return RunResult(
        ran_at=datetime(2026, 8, 6, 2, 0, tzinfo=timezone.utc),
        period=period,
        assets=tuple(assets),
        alerts_created=alerts_created,
        errors=errors,
    )


def _asset(
    *,
    change: str = "+5.43",
    previous: str | None = "+5.05",
    thresholds: list[tuple[str, str, bool]] | None = None,
    error: str | None = None,
) -> AssetResult:
    checks = tuple(
        RuleCheck(rule_id=index, kind=kind, threshold=Decimal(threshold), triggered=triggered)
        for index, (kind, threshold, triggered) in enumerate(thresholds or [], start=1)
    )
    return AssetResult(
        asset_id=1,
        name="科创100",
        code="019860",
        kind="fund",
        source="eastmoney",
        value=Decimal("1781.02") if error is None else None,
        change_percent=Decimal(change) if error is None else None,
        observed_at=datetime(2026, 8, 6, 2, 0, tzinfo=timezone.utc) if error is None else None,
        previous_change_percent=Decimal(previous) if previous and error is None else None,
        alerts_created=0,
        error=error,
        rule_checks=checks,
    )


def test_report_contains_all_sections() -> None:
    report = build_report(
        _run([_asset(thresholds=[("percent_change", "-1.5", False)])]),
        schedule_times=["02:00", "06:00", "10:00", "14:00"],
    )

    assert report["title"].startswith("基金监控 — 2026-08-06")
    assert report["period"] == "02:00"
    assert report["results"][0]["name"] == "科创100"
    assert report["results"][0]["change_percent"] == "+5.43%"
    assert report["results"][0]["previous_change_percent"] == "+5.05%"
    assert report["results"][0]["delta_percent"] == "+0.38%"
    assert report["results"][0]["rule_checks"][0]["triggered"] is False
    assert [node["time"] for node in report["nodes"]] == ["02:00", "06:00", "10:00", "14:00"]
    assert report["nodes"][0]["current"] is True


def test_text_report_first_run_notes_no_history() -> None:
    text = render_text(
        build_report(
            _run([_asset(previous=None)], period="02:00"),
            schedule_times=["02:00"],
        )
    )

    assert "基金监控" in text
    assert "本次为首次监控，无历史数据对比。" in text
    assert "科创100" in text
    assert "当前价: 1781.02" in text


def test_text_report_lists_threshold_review() -> None:
    text = render_text(
        build_report(
            _run([_asset(thresholds=[("percent_change", "-1.5", False)])]),
            schedule_times=["02:00"],
        )
    )

    assert "触发信号" in text
    assert "无触发信号" in text
    assert "≤ -1.50%" in text


def test_report_marks_suppressed_threshold_as_triggered_but_no_alert() -> None:
    # A threshold may be logically crossed while the cooldown/quiet-hours gate
    # suppresses the alert; the report should still show the crossing signal.
    report = build_report(
        _run(
            [_asset(change="-2.00", thresholds=[("percent_change", "-1.5", True)])],
            alerts_created=0,
        ),
        schedule_times=["02:00"],
    )

    assert report["signals"][0]["triggered"] is True
    assert report["results"][0]["alerts_created"] == 0


def test_report_shows_source_error_without_crashing() -> None:
    report = build_report(
        _run([_asset(error="Data source request failed")], errors=1),
        schedule_times=["02:00"],
    )

    assert report["results"][0]["status"] == "error"
    assert "异常" in render_text(report)
