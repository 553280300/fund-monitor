"""Search, manual-run, run-history, and scheduler-status API endpoints."""

from datetime import datetime, timezone
from fastapi.testclient import TestClient

from fund_monitor.api import create_app
from fund_monitor.domain import AssetCandidate, AssetKind
from fund_monitor.monitoring import RunResult
from fund_monitor.scheduler import MonitorScheduler
from fund_monitor.secrets import SecretStore
from fund_monitor.storage import initialize_database


class FakeSearch:
    async def search(self, query: str) -> list[AssetCandidate]:
        return [
            AssetCandidate(name="科创100联接C", code="019860", kind=AssetKind.FUND, source="eastmoney")
        ]


class FakeMonitor:
    async def run_once(self, *, period: str | None = None):
        return RunResult(
            ran_at=datetime(2026, 8, 6, 2, 0, tzinfo=timezone.utc),
            period=period or "02:00",
            assets=(),
            alerts_created=0,
            errors=0,
        )


def _client(tmp_path, *, scheduler=None, monitor=None):
    database = initialize_database(tmp_path / "state.db")
    app = create_app(
        database,
        monitor=monitor or FakeMonitor(),
        scheduler=scheduler,
        secret_store=SecretStore(),
        search=FakeSearch(),
        schedule_times=["02:00", "06:00"],
    )
    return TestClient(app), database


def test_search_returns_candidates(tmp_path) -> None:
    client, database = _client(tmp_path)
    with client:
        response = client.get("/api/v1/search", params={"q": "科创100"})

    assert response.status_code == 200
    assert response.json()[0]["code"] == "019860"
    assert response.json()[0]["kind"] == "fund"
    database.close()


def test_manual_run_returns_and_persists_report(tmp_path) -> None:
    client, database = _client(tmp_path)
    with client:
        response = client.post("/api/v1/monitor/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["report"]["title"].startswith("基金监控")
    assert "基金监控" in payload["text"]
    runs = database.runs.recent()
    assert len(runs) == 1
    assert "基金监控" in runs[0]["report_json"]
    database.close()


def test_run_history_lists_saved_reports(tmp_path) -> None:
    client, database = _client(tmp_path)
    with client:
        client.post("/api/v1/monitor/run")
        history = client.get("/api/v1/monitor/runs").json()

    assert len(history) == 1
    assert history[0]["period"] == "02:00"
    database.close()


def test_monitor_status_reflects_scheduler(tmp_path) -> None:
    scheduler = MonitorScheduler(FakeMonitor(), schedule_times=["02:00", "06:00"])
    client, database = _client(tmp_path, scheduler=scheduler)
    # Avoid the lifespan context so the scheduler stays stopped.
    status = client.get("/api/v1/monitor/status").json()

    assert status["running"] is False
    assert status["schedule_times"] == ["02:00", "06:00"]
    database.close()


def test_manual_run_without_monitor_is_503(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    app = create_app(database, secret_store=SecretStore(), search=FakeSearch())
    with TestClient(app) as client:
        response = client.post("/api/v1/monitor/run")

    assert response.status_code == 503
    database.close()
