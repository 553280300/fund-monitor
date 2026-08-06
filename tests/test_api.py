from fastapi.testclient import TestClient

from fund_monitor.api import create_app
from fund_monitor.secrets import SecretStore
from fund_monitor.storage import initialize_database


def test_health_reports_local_service_status(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    with TestClient(create_app(database)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    database.close()


def test_assets_can_be_created_and_listed(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    with TestClient(create_app(database)) as client:
        created = client.post(
            "/api/v1/assets",
            json={
                "name": "Example fund",
                "kind": "fund",
                "identifiers": {"eastmoney": "019860"},
            },
        )
        listed = client.get("/api/v1/assets")

    assert created.status_code == 201
    assert listed.json()[0]["name"] == "Example fund"
    database.close()


def test_assets_overview_includes_latest_observation(tmp_path) -> None:
    from datetime import datetime, timezone
    from decimal import Decimal

    from fund_monitor.domain import Asset, AssetKind, Observation

    database = initialize_database(tmp_path / "state.db")
    asset = database.assets.create(
        Asset(name="科创50", kind=AssetKind.CN_INDEX, identifiers={"tencent": "sh000688"})
    )
    database.observations.add(
        Observation(
            asset_id=asset.id or 0,
            source="tencent",
            observed_at=datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc),
            value=Decimal("1701.29"),
            change_percent=Decimal("0.45"),
            confirmed=True,
        )
    )
    with TestClient(create_app(database)) as client:
        overview = client.get("/api/v1/assets/overview")

    assert overview.status_code == 200
    row = overview.json()[0]
    assert row["name"] == "科创50"
    assert row["value"] == "1701.29"
    assert row["change_percent"] == "0.45"
    assert row["source"] == "tencent"
    database.close()


def test_panel_is_served_from_local_root(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    with TestClient(create_app(database)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "基金监控" in response.text
    database.close()


def test_rules_are_created_for_an_existing_asset_only(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    with TestClient(create_app(database)) as client:
        asset = client.post(
            "/api/v1/assets",
            json={"name": "Fund", "kind": "fund", "identifiers": {"eastmoney": "019860"}},
        ).json()
        created = client.post(
            "/api/v1/assets/{}/rules".format(asset["id"]),
            json={"asset_id": asset["id"], "kind": "percent_change", "threshold": "-1.5", "cooldown_minutes": 30},
        )
        missing = client.post(
            "/api/v1/assets/999/rules",
            json={"asset_id": 999, "kind": "percent_change", "threshold": "-1.5", "cooldown_minutes": 30},
        )

    assert created.status_code == 201
    assert created.json()["threshold"] == "-1.5"
    assert missing.status_code == 404
    database.close()


def test_channel_api_exposes_metadata_only(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    with TestClient(create_app(database)) as client:
        created = client.post(
            "/api/v1/channels",
            json={"name": "Telegram", "channel_type": "telegram", "settings": {"chat_id": "123"}},
        )
        listed = client.get("/api/v1/channels")

    assert created.status_code == 201
    assert listed.json()[0]["settings"] == {"chat_id": "123"}
    assert "token" not in str(listed.json()).lower()
    database.close()


def test_channel_secret_is_written_to_secret_store_not_api_response(tmp_path) -> None:
    class FakeKeyring:
        values = {}
        def set_password(self, service, username, value): self.values[(service, username)] = value
        def get_password(self, service, username): return self.values.get((service, username))
        def delete_password(self, service, username): self.values.pop((service, username), None)

    database = initialize_database(tmp_path / "state.db")
    secrets = SecretStore(backend=FakeKeyring())
    with TestClient(create_app(database, secret_store=secrets)) as client:
        channel = client.post("/api/v1/channels", json={"name": "Telegram", "channel_type": "telegram", "settings": {"chat_id": "123"}}).json()
        response = client.put(f"/api/v1/channels/{channel['id']}/secret", json={"secret": "bot-token"})

    assert response.status_code == 204
    assert "bot-token" not in response.text
    assert secrets.get(f"channel:{channel['id']}") == "bot-token"
    database.close()


def test_configuration_export_contains_no_channel_secret(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    with TestClient(create_app(database)) as client:
        client.post("/api/v1/channels", json={"name": "Hook", "channel_type": "webhook", "settings": {"url": "https://example.test"}})
        exported = client.get("/api/v1/config/export")

    assert exported.status_code == 200
    assert exported.json()["channels"][0]["settings"] == {"url": "https://example.test"}
    assert "secret" not in str(exported.json()).lower()
    database.close()
