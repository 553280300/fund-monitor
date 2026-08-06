"""Channel management API: delete and test-send endpoints."""

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


class OkServerChanChannel:
    channel_id = 1
    channel_type = "serverchan"
    name = "ok"

    async def send(self, message) -> None:
        return None


def test_channel_can_be_deleted_with_its_secret(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    secrets = SecretStore(backend=FakeKeyring())
    with TestClient(create_app(database, secret_store=secrets)) as client:
        channel = client.post(
            "/api/v1/channels",
            json={"name": "微信", "channel_type": "serverchan", "settings": {}},
        ).json()
        client.put(f"/api/v1/channels/{channel['id']}/secret", json={"secret": "SCT-KEY"})
        deleted = client.delete(f"/api/v1/channels/{channel['id']}")
        listed = client.get("/api/v1/channels")

    assert deleted.status_code == 204
    assert listed.json() == []
    assert secrets.get(f"channel:{channel['id']}") is None
    database.close()


def test_channel_test_send_returns_result(tmp_path, monkeypatch) -> None:
    database = initialize_database(tmp_path / "state.db")
    monkeypatch.setattr(
        "fund_monitor.api.ChannelFactory",
        lambda secrets: (lambda config: OkServerChanChannel()),
    )
    with TestClient(create_app(database, secret_store=SecretStore(backend=FakeKeyring()))) as client:
        channel = client.post(
            "/api/v1/channels",
            json={"name": "微信", "channel_type": "serverchan", "settings": {}},
        ).json()
        response = client.post(f"/api/v1/channels/{channel['id']}/test")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    database.close()


def test_channel_test_send_reports_config_errors(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    with TestClient(create_app(database, secret_store=SecretStore(backend=FakeKeyring()))) as client:
        channel = client.post(
            "/api/v1/channels",
            json={"name": "微信", "channel_type": "serverchan", "settings": {}},
        ).json()
        response = client.post(f"/api/v1/channels/{channel['id']}/test")

    assert response.status_code == 200
    assert response.json()["ok"] is False  # Missing send_key -> config error
    database.close()


def test_test_send_for_missing_channel_is_404(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    with TestClient(create_app(database, secret_store=SecretStore(backend=FakeKeyring()))) as client:
        response = client.post("/api/v1/channels/999/test")

    assert response.status_code == 404
    database.close()
