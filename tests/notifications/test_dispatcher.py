import pytest

from fund_monitor.domain import ChannelType, NotificationMessage
from fund_monitor.notifications.base import DeliveryStatus, NotificationDispatcher


class FailingChannel:
    channel_id = 1
    channel_type = ChannelType.WEBHOOK
    name = "failing"

    async def send(self, message: NotificationMessage):
        raise RuntimeError("network failed")


class SuccessfulChannel:
    channel_id = 2
    channel_type = ChannelType.DESKTOP
    name = "successful"

    async def send(self, message: NotificationMessage):
        return None


@pytest.mark.asyncio
async def test_one_failed_channel_does_not_stop_another() -> None:
    dispatcher = NotificationDispatcher([FailingChannel(), SuccessfulChannel()])
    results = await dispatcher.dispatch(NotificationMessage(title="Alert", body="Message"))

    assert [result.status for result in results] == [DeliveryStatus.FAILED, DeliveryStatus.SENT]
    assert "network failed" not in (results[0].detail or "")
