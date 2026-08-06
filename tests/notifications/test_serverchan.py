"""Server酱 (ServerChan Turbo) notification channel."""

from urllib.parse import parse_qs

import httpx
import pytest

from fund_monitor.domain import ChannelType, NotificationMessage
from fund_monitor.notifications.serverchan import ServerChanChannel


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.sent.append((str(request.url), parse_qs(request.content.decode())))
        return httpx.Response(200, json={"code": 0, "message": "success"})


@pytest.mark.asyncio
async def test_serverchan_posts_title_and_body() -> None:
    transport = FakeTransport()
    client = httpx.AsyncClient(transport=transport)
    channel = ServerChanChannel(
        channel_id=1,
        name="微信推送",
        send_key="SCT_TEST_KEY",
        client=client,
    )

    await channel.send(NotificationMessage(title="基金异动", body="科创100 +5.07%"))

    assert len(transport.sent) == 1
    url, params = transport.sent[0]
    assert url == "https://sctapi.ftqq.com/SCT_TEST_KEY.send"
    assert params["title"] == ["基金异动"]
    assert params["desp"] == ["科创100 +5.07%"]
    await client.aclose()


class FakeErrorTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": 40001, "message": "错误的Key"})


@pytest.mark.asyncio
async def test_serverchan_rejects_invalid_key() -> None:
    client = httpx.AsyncClient(transport=FakeErrorTransport())
    channel = ServerChanChannel(channel_id=1, name="微信推送", send_key="BAD", client=client)

    with pytest.raises(Exception):
        await channel.send(NotificationMessage(title="t", body="b"))
    await client.aclose()


def test_serverchan_requires_send_key() -> None:
    try:
        ServerChanChannel(channel_id=1, name="微信推送", send_key="")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when send_key is empty")


def test_channel_type_is_serverchan() -> None:
    assert ServerChanChannel.channel_type == ChannelType.SERVERCHAN
