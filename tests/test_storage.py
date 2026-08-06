from pathlib import Path

from fund_monitor.domain import Asset, AssetKind, ChannelConfig, ChannelType
from fund_monitor.storage import initialize_database


def test_alert_fingerprint_is_unique_after_reopening_database(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    first = initialize_database(db_path)
    assert first.alerts.record_if_new("fund:1:percent:2026-08-05") is True
    first.close()

    second = initialize_database(db_path)
    assert second.alerts.record_if_new("fund:1:percent:2026-08-05") is False
    second.close()


def test_assets_round_trip_through_repository(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "state.db")
    asset = database.assets.create(
        Asset(
            name="Example fund",
            kind=AssetKind.FUND,
            identifiers={"eastmoney": "019860"},
        )
    )

    assert asset.id is not None
    assert database.assets.get(asset.id) == asset
    database.close()


def test_channel_metadata_round_trips_without_a_secret(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "state.db")
    channel = database.channels.create(
        ChannelConfig(name="Telegram", channel_type=ChannelType.TELEGRAM, settings={"chat_id": "123"})
    )

    assert channel.id is not None
    assert database.channels.list() == [channel]
    assert "token" not in str(channel.settings).lower()
    database.close()


def test_health_list_prefers_the_latest_status_for_legacy_duplicate_records(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "state.db")
    database.connection.execute("DROP TABLE component_health")
    database.connection.execute(
        """CREATE TABLE component_health (
            component_type TEXT NOT NULL, component_name TEXT NOT NULL, status TEXT NOT NULL,
            detail TEXT, checked_at TEXT NOT NULL
        )"""
    )
    database.connection.executemany(
        "INSERT INTO component_health VALUES (?, ?, ?, ?, ?)",
        [
            ("provider", "registry", "error", "old error", "2026-08-05T00:00:00+00:00"),
            ("provider", "registry", "healthy", None, "2026-08-05T00:01:00+00:00"),
        ],
    )
    database.connection.commit()

    assert database.health.list() == [{
        "component_type": "provider", "component_name": "registry", "status": "healthy",
        "detail": None, "checked_at": "2026-08-05T00:01:00+00:00",
    }]
    database.close()
