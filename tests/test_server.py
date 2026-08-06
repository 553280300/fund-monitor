from fastapi.testclient import TestClient

from fund_monitor.server import build_application


def test_server_builds_a_local_application(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FUND_MONITOR_DATA_DIR", str(tmp_path))
    app = build_application()

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
