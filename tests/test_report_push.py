"""Report pushing after each full monitoring run."""

from datetime import datetime, timezone

import pytest

from fund_monitor.domain import NotificationMessage
from fund_monitor.monitoring import RunResult
from fund_monitor.server import ReportPusher, ReportingMonitor


class StubMonitor:
    def __init__(self) -> None:
        self.run_count = 0
        self.checked: list[int] = []
        self.run = RunResult(
            ran_at=datetime(2026, 8, 6, 2, 0, tzinfo=timezone.utc),
            period="02:00",
            assets=(),
            alerts_created=0,
            errors=0,
        )

    async def run_once(self, *, period: str | None = None):
        self.run_count += 1
        return self.run

    async def check_asset(self, asset):
        self.checked.append(asset)
        return None


class StubDispatcher:
    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    async def dispatch(self, message, *, channel_ids=()):
        self.messages.append(message)
        return []


@pytest.mark.asyncio
async def test_reporting_monitor_pushes_report_after_run() -> None:
    monitor = StubMonitor()
    dispatcher = StubDispatcher()
    pusher = ReportPusher(
        object(),
        dispatcher,
        schedule_times=["02:00"],
        timezone_name="Asia/Shanghai",
    )
    reporting = ReportingMonitor(monitor, pusher)

    run = await reporting.run_once(period="02:00")

    assert monitor.run_count == 1
    assert run is monitor.run
    assert len(dispatcher.messages) == 1
    assert "基金监控" in dispatcher.messages[0].title
    assert "基金监控" in dispatcher.messages[0].body


@pytest.mark.asyncio
async def test_failed_report_push_does_not_fail_the_run() -> None:
    class BrokenPusher:
        async def push(self, run):
            raise RuntimeError("push failed")

    monitor = StubMonitor()
    reporting = ReportingMonitor(monitor, BrokenPusher())

    run = await reporting.run_once()

    assert run is monitor.run
    assert monitor.run_count == 1


@pytest.mark.asyncio
async def test_reporting_monitor_forwards_check_asset() -> None:
    monitor = StubMonitor()
    reporting = ReportingMonitor(monitor, None)

    await reporting.check_asset(7)

    assert monitor.checked == [7]
