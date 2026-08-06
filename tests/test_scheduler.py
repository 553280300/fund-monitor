import asyncio

import pytest

from fund_monitor.scheduler import MonitorScheduler


class FakeMonitor:
    def __init__(self) -> None:
        self.run_count = 0
        self.fail_next = False

    async def run_once(self, *, period: str | None = None):
        del period
        self.run_count += 1
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("provider failure")


@pytest.mark.asyncio
async def test_scheduler_runs_immediately_then_stops(fake_monitor=None) -> None:
    monitor = fake_monitor or FakeMonitor()
    scheduler = MonitorScheduler(monitor, interval_seconds=60)

    await scheduler.start()
    await asyncio.sleep(0)
    await scheduler.stop()

    assert monitor.run_count == 1
    assert scheduler.status().running is False


@pytest.mark.asyncio
async def test_scheduler_records_error_and_continues_after_failed_run() -> None:
    monitor = FakeMonitor()
    monitor.fail_next = True
    scheduler = MonitorScheduler(monitor, interval_seconds=60)

    await scheduler.run_cycle()
    await scheduler.run_cycle()

    assert monitor.run_count == 2
    assert scheduler.status().last_error is None
