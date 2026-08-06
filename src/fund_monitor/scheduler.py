"""Single-task, cancellation-safe local monitoring scheduler.

Two modes:
- trading-day node mode: run at configured clock times (e.g. 02:00/06:00/10:00/14:00)
  on weekdays;
- fixed-interval mode: run every N seconds (used in development and tests).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class MonitorRunner(Protocol):
    async def run_once(self, *, period: str | None = None) -> object: ...


@dataclass(frozen=True)
class SchedulerStatus:
    running: bool
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_error: str | None
    next_due_at: datetime | None
    schedule_times: tuple[str, ...] | None = None


class MonitorScheduler:
    def __init__(
        self,
        monitor: MonitorRunner,
        *,
        interval_seconds: int | None = None,
        schedule_times: list[str] | None = None,
        timezone_name: str = "Asia/Shanghai",
    ) -> None:
        if interval_seconds is None and not schedule_times:
            raise ValueError("interval_seconds or schedule_times is required")
        if interval_seconds is not None and schedule_times:
            raise ValueError("choose either interval_seconds or schedule_times, not both")
        self._monitor = monitor
        self._interval_seconds = interval_seconds
        self._schedule_times = tuple(schedule_times or ())
        self._timezone = MonitorScheduler._resolve_timezone(timezone_name)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._run_lock = asyncio.Lock()
        self._last_started_at: datetime | None = None
        self._last_finished_at: datetime | None = None
        self._last_error: str | None = None
        self._next_due_at: datetime | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._loop(), name="fund-monitor-scheduler")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
        self._task = None
        self._next_due_at = None

    async def run_cycle(self, *, period: str | None = None) -> None:
        if self._run_lock.locked():
            return
        async with self._run_lock:
            self._last_started_at = datetime.now(timezone.utc)
            try:
                await self._monitor.run_once(period=period)
            except Exception as error:  # Scheduler isolation: next interval must still run.
                self._last_error = str(error)
            else:
                self._last_error = None
            finally:
                self._last_finished_at = datetime.now(timezone.utc)

    def status(self) -> SchedulerStatus:
        return SchedulerStatus(
            running=self._task is not None and not self._task.done(),
            last_started_at=self._last_started_at,
            last_finished_at=self._last_finished_at,
            last_error=self._last_error,
            next_due_at=self._next_due_at,
            schedule_times=self._schedule_times or None,
        )

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            if self._schedule_times:
                wait_seconds = self._seconds_until_next_node()
                self._next_due_at = datetime.now(timezone.utc) + timedelta(seconds=wait_seconds)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=wait_seconds)
                except TimeoutError:
                    pass
                if self._stop_event.is_set():
                    break
                await self.run_cycle(period=self._current_node_label())
            else:
                await self.run_cycle()
                self._next_due_at = datetime.now(timezone.utc)
                self._next_due_at = self._next_due_at.replace(microsecond=0) + timedelta(
                    seconds=self._interval_seconds or 0
                )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
                except TimeoutError:
                    continue

    def _seconds_until_next_node(self, now: datetime | None = None) -> float:
        """Seconds until the next trading-day node; weekdays only for now."""
        now = now or datetime.now(self._timezone)
        for offset in range(8):
            day = now.date() + timedelta(days=offset)
            if day.weekday() >= 5:  # Saturday / Sunday
                continue
            for slot in self._schedule_times:
                hour, minute = (int(part) for part in slot.split(":"))
                candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=now.tzinfo)
                if candidate > now:
                    return (candidate - now).total_seconds()
        return 7 * 24 * 3600

    def _current_node_label(self, now: datetime | None = None) -> str:
        """The slot that just fired: the latest node at or before the given time."""
        now = now or datetime.now(self._timezone)
        now_time = now.strftime("%H:%M")
        reached = [slot for slot in self._schedule_times if slot <= now_time]
        if reached:
            return reached[-1]
        return self._schedule_times[0] if self._schedule_times else ""

    @staticmethod
    def _resolve_timezone(timezone_name: str) -> timezone | ZoneInfo:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return timezone(timedelta(hours=8), name="UTC+08:00")
