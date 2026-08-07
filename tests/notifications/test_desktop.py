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
    assert "127.0.0.1:8420" in received["script"]  # click opens the panel


@pytest.mark.asyncio
async def test_desktop_channel_truncates_long_bodies_and_hints_panel() -> None:
    received = {}
    def runner(script): received["script"] = script
    channel = DesktopChannel(channel_id=9, name="Desktop", runner=runner)

    long_body = "字" * 500
    await channel.send(NotificationMessage(title="长报告", body=long_body))

    assert "点击通知打开完整报告" in received["script"]
    assert "字" * 500 not in received["script"]
