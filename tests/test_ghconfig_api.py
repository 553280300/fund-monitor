"""GitHub token management API endpoints."""

from fastapi.testclient import TestClient

from fund_monitor.api import create_app
from fund_monitor.secrets import SecretStore
from fund_monitor.storage import initialize_database


class FakeKeyring:
    def __init__(self) -> None:
        self.values = {}

    def set_password(self, service, username, value):
        self.values[(service, username)] = value

    def get_password(self, service, username):
        return self.values.get((service, username))

    def delete_password(self, service, username):
        self.values.pop((service, username), None)


def test_gh_token_is_stored_in_secret_store(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    secrets = SecretStore(backend=FakeKeyring())
    with TestClient(create_app(database, secret_store=secrets)) as client:
        response = client.put("/api/v1/ghconfig/token", json={"secret": "ghp_abc"})

    assert response.status_code == 204
    assert secrets.get("github:token") == "ghp_abc"
    database.close()


def test_gh_token_can_be_cleared(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    secrets = SecretStore(backend=FakeKeyring())
    secrets.set("github:token", "ghp_abc")
    with TestClient(create_app(database, secret_store=secrets)) as client:
        response = client.delete("/api/v1/ghconfig/token")

    assert response.status_code == 204
    assert secrets.get("github:token") is None
    database.close()


def test_sync_uses_stored_token(monkeypatch, tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    secrets = SecretStore(backend=FakeKeyring())
    secrets.set("github:token", "ghp_stored")

    calls = {}

    def fake_sync(content, repo, token):
        calls["token"] = token
        calls["repo"] = repo
        return f"已同步到 {repo}"

    monkeypatch.setattr("fund_monitor.api.ghconfig.sync_config", fake_sync)
    with TestClient(create_app(database, secret_store=secrets)) as client:
        response = client.post("/api/v1/ghconfig/sync", json={"repo": "me/repo"})

    assert response.status_code == 200
    assert calls["token"] == "ghp_stored"
    assert calls["repo"] == "me/repo"
    assert response.json()["ok"] is True
    database.close()


def test_ghconfig_reports_default_repo(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    with TestClient(create_app(database, secret_store=SecretStore(backend=FakeKeyring()))) as client:
        response = client.get("/api/v1/ghconfig")

    assert response.status_code == 200
    assert response.json()["repo"] == "Frog755/fund-monitor"
    database.close()
