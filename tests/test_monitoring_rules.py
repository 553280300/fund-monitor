"""Rule-evaluation behavior: NAV changes, provider events, cooldown, quiet hours, channel routing."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from fund_monitor.domain import (
    AlertKind,
    AlertRule,
    Asset,
    AssetKind,
    ChannelType,
    Observation,
    ProviderEvent,
    ProviderResult,
)
from fund_monitor.monitoring import MonitoringService
from fund_monitor.notifications.base import NotificationDispatcher
from fund_monitor.storage import initialize_database


class SequenceProvider:
    name = "sequence"
    supported_kinds = {AssetKind.FUND}

    def __init__(
        self,
        changes: list[Decimal],
        *,
        observed_ats: list[datetime] | None = None,
        events: list[ProviderEvent] | None = None,
    ) -> None:
        self._changes = iter(changes)
        self._ats = iter(observed_ats or [])
        self._events = events or []

    async def fetch(self, asset: Asset) -> ProviderResult:
        observed_at = next(self._ats, None) or datetime.now(timezone.utc)
        return ProviderResult(
            source=self.name,
            observation=Observation(
                asset_id=asset.id or 0,
                source=self.name,
                observed_at=observed_at,
                value=Decimal("1.0000"),
                change_percent=next(self._changes),
            ),
            events=tuple(self._events),
        )


class RecordingChannel:
    channel_id = 1
    channel_type = ChannelType.DESKTOP
    name = "recording"

    def __init__(self) -> None:
        self.messages = []

    async def send(self, message) -> None:
        self.messages.append(message)


def _asset(database, name: str = "Fund") -> Asset:
    return database.assets.create(Asset(name=name, kind=AssetKind.FUND, identifiers={"sequence": "1"}))


def _utc(year: int, month: int, day: int, hour: int = 10) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _seed_alert(database, rule_id: int, asset_id: int, *, created_at: str) -> None:
    """Insert an alert as if the rule fired at a known time (bypasses the real clock)."""
    database.connection.execute(
        """INSERT INTO alerts (fingerprint, asset_id, rule_id, kind, title, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (f"asset:{asset_id}:rule:{rule_id}:kind:nav_change:date:seed", asset_id, rule_id,
         "nav_change", "seed", None, created_at),
    )
    database.connection.commit()


@pytest.mark.asyncio
async def test_nav_change_rule_fires_when_daily_change_exceeds_threshold(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    asset = _asset(database)
    database.rules.create(
        AlertRule(asset_id=asset.id or 0, kind=AlertKind.NAV_CHANGE, threshold=Decimal("0.5"), cooldown_minutes=30)
    )
    service = MonitoringService(database, [SequenceProvider([Decimal("0.4"), Decimal("0.6")])])

    assert (await service.run_once()).alerts_created == 0
    assert (await service.run_once()).alerts_created == 1
    assert len(database.alerts.recent()) == 1
    database.close()


@pytest.mark.asyncio
async def test_dividend_event_creates_alert_once_and_dispatches(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    asset = _asset(database)
    database.rules.create(
        AlertRule(asset_id=asset.id or 0, kind=AlertKind.DIVIDEND, cooldown_minutes=30)
    )
    event = ProviderEvent(
        asset_id=asset.id or 0,
        source="sequence",
        kind=AlertKind.DIVIDEND,
        occurred_at=_utc(2026, 8, 1),
        title="分红公告",
        detail="每份 0.05 元",
        external_id="div-2026-08",
    )
    channel = RecordingChannel()
    service = MonitoringService(
        database,
        [SequenceProvider([Decimal("0.1"), Decimal("0.1")], events=[event])],
        dispatcher=NotificationDispatcher([channel]),
    )

    first = await service.run_once()
    second = await service.run_once()

    assert first.alerts_created == 1
    assert second.alerts_created == 0  # Same external event must not alert twice.
    assert len(channel.messages) == 1
    assert database.deliveries.recent()[0]["status"] == "sent"
    database.close()


@pytest.mark.asyncio
async def test_cooldown_suppresses_repeat_alert_across_days(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    asset = _asset(database)
    rule = database.rules.create(
        AlertRule(asset_id=asset.id or 0, kind=AlertKind.NAV_CHANGE, threshold=Decimal("0.5"), cooldown_minutes=10080)
    )
    _seed_alert(database, rule.id or 0, asset.id or 0, created_at="2026-08-01T10:00:00+00:00")
    service = MonitoringService(
        database,
        [SequenceProvider([Decimal("0.6")], observed_ats=[_utc(2026, 8, 2)])],
    )

    assert (await service.run_once()).alerts_created == 0  # Still inside the weekly cooldown.
    assert len(database.alerts.recent()) == 1
    database.close()


@pytest.mark.asyncio
async def test_short_cooldown_allows_alert_on_the_next_day(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    asset = _asset(database)
    rule = database.rules.create(
        AlertRule(asset_id=asset.id or 0, kind=AlertKind.NAV_CHANGE, threshold=Decimal("0.5"), cooldown_minutes=30)
    )
    _seed_alert(database, rule.id or 0, asset.id or 0, created_at="2026-08-01T10:00:00+00:00")
    service = MonitoringService(
        database,
        [SequenceProvider([Decimal("0.6")], observed_ats=[_utc(2026, 8, 2)])],
    )

    assert (await service.run_once()).alerts_created == 1  # 24h later, cooldown expired.
    assert len(database.alerts.recent()) == 2
    database.close()


@pytest.mark.asyncio
async def test_quiet_hours_suppress_alert(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    asset = _asset(database)
    database.rules.create(
        AlertRule(
            asset_id=asset.id or 0,
            kind=AlertKind.NAV_CHANGE,
            threshold=Decimal("0.5"),
            cooldown_minutes=30,
            quiet_hours=("18:00", "20:00"),
        )
    )
    # UTC 10:00 == Asia/Shanghai 18:00, inside quiet hours.
    service = MonitoringService(
        database,
        [SequenceProvider([Decimal("0.6")], observed_ats=[_utc(2026, 8, 1)])],
    )

    assert (await service.run_once()).alerts_created == 0
    assert len(database.alerts.recent()) == 0
    database.close()


@pytest.mark.asyncio
async def test_quiet_hours_allow_outside_window(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    asset = _asset(database)
    database.rules.create(
        AlertRule(
            asset_id=asset.id or 0,
            kind=AlertKind.NAV_CHANGE,
            threshold=Decimal("0.5"),
            cooldown_minutes=30,
            quiet_hours=("18:00", "20:00"),
        )
    )
    # UTC 00:00 == Asia/Shanghai 08:00, outside quiet hours.
    service = MonitoringService(
        database,
        [SequenceProvider([Decimal("0.6")], observed_ats=[_utc(2026, 8, 1, 0)])],
    )

    assert (await service.run_once()).alerts_created == 1
    database.close()


@pytest.mark.asyncio
async def test_rule_restricts_dispatch_to_selected_channels(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    asset = _asset(database)
    database.rules.create(
        AlertRule(
            asset_id=asset.id or 0,
            kind=AlertKind.PERCENT_CHANGE,
            threshold=Decimal("-1.0"),
            cooldown_minutes=30,
            channel_ids=(2,),
        )
    )
    first_channel = RecordingChannel()
    second_channel = RecordingChannel()
    second_channel.channel_id = 2
    service = MonitoringService(
        database,
        [SequenceProvider([Decimal("-0.9"), Decimal("-1.2")])],
        dispatcher=NotificationDispatcher([first_channel, second_channel]),
    )

    await service.run_once()
    await service.run_once()

    assert len(first_channel.messages) == 0
    assert len(second_channel.messages) == 1
    database.close()
