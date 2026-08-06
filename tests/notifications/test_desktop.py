import pytest

from fund_monitor.domain import ChannelType, NotificationMessage
from fund_monitor.notifications.desktop import DesktopChannel


@pytest.mark.asyncio
async def test_desktop_channel_invokes_windows_notification_script() -> None:
    received = {}
    def runner(script): received["script"] = script
    channel = DesktopChannel(channel_id=9, name="Desktop", runner=runner)

    await channel.send(NotificationMessage(title="Alert", body="Changed"))

    assert channel.channel_type == ChannelType.DESKTOP
    assert "ShowBalloonTip" in received["script"]
    assert "Alert" in received["script"]
