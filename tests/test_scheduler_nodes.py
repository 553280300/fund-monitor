"""Trading-day node scheduling behavior."""

from datetime import datetime, timedelta, timezone

from fund_monitor.scheduler import MonitorScheduler

CN = timezone(timedelta(hours=8), name="UTC+08:00")


class StubMonitor:
    def __init__(self) -> None:
        self.periods = []

    async def run_once(self, *, period: str | None = None):
        self.periods.append(period)


def _scheduler(*, times: list[str] | None = None, interval: int | None = None):
    return MonitorScheduler(
        StubMonitor(),
        schedule_times=times,
        interval_seconds=interval,
        timezone_name="Asia/Shanghai",
    )


def test_requires_either_mode() -> None:
    try:
        MonitorScheduler(StubMonitor())
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when neither mode is configured")


def test_rejects_both_modes() -> None:
    try:
        MonitorScheduler(StubMonitor(), interval_seconds=60, schedule_times=["10:00"])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when both modes are configured")


def test_next_node_is_later_today() -> None:
    scheduler = _scheduler(times=["02:00", "06:00", "10:00"])
    # 2026-08-06 is a Thursday; 03:00 local time.
    now = datetime(2026, 8, 6, 3, 0, tzinfo=CN)
    assert scheduler._seconds_until_next_node(now) == 3 * 3600  # 06:00 - 03:00


def test_next_node_skips_weekend() -> None:
    scheduler = _scheduler(times=["10:00"])
    # 2026-08-07 is a Friday at 12:00 -> next node Monday 2026-08-10 10:00.
    now = datetime(2026, 8, 7, 12, 0, tzinfo=CN)
    assert scheduler._seconds_until_next_node(now) == (2 * 24 + 22) * 3600


def test_next_node_rolls_to_next_day_after_last_slot() -> None:
    scheduler = _scheduler(times=["02:00", "06:00"])
    now = datetime(2026, 8, 6, 20, 0, tzinfo=CN)  # Thursday evening
    assert scheduler._seconds_until_next_node(now) == 6 * 3600  # Friday 02:00


def test_weekend_has_no_node_until_monday() -> None:
    scheduler = _scheduler(times=["02:00", "06:00"])
    now = datetime(2026, 8, 8, 12, 0, tzinfo=CN)  # Saturday
    assert scheduler._seconds_until_next_node(now) == (1 * 24 + 14) * 3600  # Monday 02:00


def test_current_node_label_picks_reached_slot() -> None:
    scheduler = _scheduler(times=["02:00", "06:00", "10:00"])
    now = datetime(2026, 8, 6, 6, 1, tzinfo=CN)
    assert scheduler._current_node_label(now) == "06:00"


def test_status_exposes_schedule_times() -> None:
    scheduler = _scheduler(times=["02:00", "14:00"])
    assert scheduler.status().schedule_times == ("02:00", "14:00")
