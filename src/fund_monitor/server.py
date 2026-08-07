"""Local application construction and development server entry point."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from fund_monitor.api import create_app
from fund_monitor.config import AppSettings, runtime_paths
from fund_monitor.domain import NotificationMessage
from fund_monitor.monitoring import MonitoringService, RunResult
from fund_monitor.providers.eastmoney import EastmoneyProvider
from fund_monitor.providers.tencent import TencentProvider
from fund_monitor.providers.yahoo import YahooProvider
from fund_monitor.providers.search import EastmoneySearchProvider
from fund_monitor.report import build_report, render_markdown, render_text
from fund_monitor.scheduler import MonitorScheduler
from fund_monitor.notifications.configured import ConfiguredDispatcher
from fund_monitor.secrets import SecretStore
from fund_monitor.storage import Database, initialize_database


class ReportPusher:
    """Push the rendered monitoring report to all enabled channels."""

    def __init__(
        self,
        database: Database,
        dispatcher: ConfiguredDispatcher,
        *,
        schedule_times: list[str],
        timezone_name: str,
    ) -> None:
        self._database = database
        self._dispatcher = dispatcher
        self._schedule_times = schedule_times
        self._timezone_name = timezone_name

    async def push(self, run: RunResult) -> None:
        report = build_report(run, schedule_times=self._schedule_times, timezone_name=self._timezone_name)
        # Push the WeChat-friendly Markdown variant to channels.
        message = NotificationMessage(title=report["title"], body=render_markdown(report))
        # Report delivery failures are isolated per channel and never block monitoring.
        try:
            await self._dispatcher.dispatch(message)
        except Exception:
            pass


class ReportingMonitor:
    """Wraps the monitoring service to push a report after every full run."""

    def __init__(self, monitor: MonitoringService, pusher: ReportPusher | None = None) -> None:
        self._monitor = monitor
        self._pusher = pusher

    async def run_once(self, *, period: str | None = None) -> RunResult:
        run = await self._monitor.run_once(period=period)
        if self._pusher is not None:
            try:
                await self._pusher.push(run)
            except Exception:
                pass  # A failed report push must not fail the monitoring cycle.
        return run

    async def check_asset(self, asset):
        return await self._monitor.check_asset(asset)


def build_application(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or AppSettings()
    paths = runtime_paths()
    paths.ensure_directories()
    database = initialize_database(paths.database)
    secrets = SecretStore()
    monitor = MonitoringService(
        database,
        [TencentProvider(), EastmoneyProvider(), YahooProvider()],
        dispatcher=ConfiguredDispatcher(database, secrets=secrets),
        timezone_name=settings.default_timezone,
    )
    dispatcher = ConfiguredDispatcher(database, secrets=secrets)
    pusher = ReportPusher(
        database,
        dispatcher,
        schedule_times=settings.schedule_times,
        timezone_name=settings.default_timezone,
    )
    reporting = ReportingMonitor(monitor, pusher)
    scheduler = MonitorScheduler(
        reporting,
        schedule_times=settings.schedule_times,
        timezone_name=settings.default_timezone,
    )
    app = create_app(
        database,
        monitor=reporting,
        scheduler=scheduler,
        secret_store=secrets,
        search=EastmoneySearchProvider(),
        schedule_times=settings.schedule_times,
        timezone_name=settings.default_timezone,
    )
    app.state.database = database
    app.state.monitor = reporting
    app.state.scheduler = scheduler
    return app


def run_local_server(settings: AppSettings | None = None) -> int:
    settings = settings or AppSettings()
    uvicorn.run(build_application(settings), host=settings.host, port=settings.port, log_level="info")
    return 0
