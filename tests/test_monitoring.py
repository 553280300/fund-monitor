from datetime import datetime, timezone
from decimal import Decimal

import pytest

from fund_monitor.domain import AlertKind, AlertRule, Asset, AssetKind, ChannelType, Observation, ProviderResult
from fund_monitor.monitoring import MonitoringService
from fund_monitor.notifications.base import NotificationDispatcher
from fund_monitor.storage import initialize_database


class SequenceProvider:
    name = "sequence"
    supported_kinds = {AssetKind.FUND}

    def __init__(self, changes: list[Decimal]) -> None:
        self._changes = iter(changes)

    async def fetch(self, asset: Asset) -> ProviderResult:
        return ProviderResult(
            source=self.name,
            observation=Observation(
                asset_id=asset.id or 0,
                source=self.name,
                observed_at=datetime.now(timezone.utc),
                value=Decimal("1.0000"),
                change_percent=next(self._changes),
            ),
        )


class RecordingChannel:
    channel_id = 1
    channel_type = ChannelType.DESKTOP
    name = "recording"

    def __init__(self) -> None:
        self.messages = []

    async def send(self, message) -> None:
        self.messages.append(message)


@pytest.mark.asyncio
async def test_percent_rule_triggers_once_on_threshold_crossing(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    asset = database.assets.create(
        Asset(name="Fund", kind=AssetKind.FUND, identifiers={"sequence": "1"})
    )
    database.rules.create(
        AlertRule(
            asset_id=asset.id or 0,
            kind=AlertKind.PERCENT_CHANGE,
            threshold=Decimal("-1.0"),
            cooldown_minutes=30,
        )
    )
    service = MonitoringService(database, [SequenceProvider([
        Decimal("-0.9"), Decimal("-1.2"), Decimal("-1.3")
    ])])

    assert (await service.run_once()).alerts_created == 0
    assert (await service.run_once()).alerts_created == 1
    assert (await service.run_once()).alerts_created == 0
    assert len(database.alerts.recent()) == 1
    database.close()


@pytest.mark.asyncio
async def test_new_alert_is_dispatched_once_and_delivery_is_persisted(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    asset = database.assets.create(Asset(name="Fund", kind=AssetKind.FUND, identifiers={"sequence": "1"}))
    database.rules.create(AlertRule(asset_id=asset.id or 0, kind=AlertKind.PERCENT_CHANGE, threshold=Decimal("-1.0"), cooldown_minutes=30))
    channel = RecordingChannel()
    service = MonitoringService(
        database,
        [SequenceProvider([Decimal("-0.9"), Decimal("-1.2"), Decimal("-1.3")])],
        dispatcher=NotificationDispatcher([channel]),
    )

    await service.run_once()
    await service.run_once()
    await service.run_once()

    assert len(channel.messages) == 1
    assert database.deliveries.recent()[0]["status"] == "sent"
    database.close()
