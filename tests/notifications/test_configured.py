import pytest

from fund_monitor.domain import ChannelConfig, ChannelType, NotificationMessage
from fund_monitor.notifications.configured import ConfiguredDispatcher
from fund_monitor.storage import initialize_database


class FakeChannel:
    channel_id = 1
    channel_type = ChannelType.WEBHOOK
    name = "Webhook"
    async def send(self, message):
        self.message = message


@pytest.mark.asyncio
async def test_configured_dispatcher_uses_enabled_channel_metadata(tmp_path) -> None:
    database = initialize_database(tmp_path / "state.db")
    database.channels.create(ChannelConfig(name="Webhook", channel_type=ChannelType.WEBHOOK, settings={"url": "https://example.test"}))
    channel = FakeChannel()
    dispatcher = ConfiguredDispatcher(database, builder=lambda config: channel)

    result = await dispatcher.dispatch(NotificationMessage(title="Alert", body="Changed"))

    assert result[0].status.value == "sent"
    database.close()
