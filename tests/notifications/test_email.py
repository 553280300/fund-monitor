import pytest

from fund_monitor.domain import ChannelType, NotificationMessage
from fund_monitor.notifications.email import EmailChannel


@pytest.mark.asyncio
async def test_email_channel_passes_only_alert_content_to_sender() -> None:
    received = {}

    def sender(host, port, username, password, sender_address, recipient, subject, body):
        received.update(locals())

    channel = EmailChannel(
        channel_id=5, name="Email", host="smtp.example.test", port=465,
        username="user", password="secret", sender_address="from@example.test",
        recipient="to@example.test", sender=sender,
    )
    await channel.send(NotificationMessage(title="Alert", body="Changed"))

    assert channel.channel_type == ChannelType.EMAIL
    assert received["subject"] == "Alert"
    assert received["body"] == "Changed"
