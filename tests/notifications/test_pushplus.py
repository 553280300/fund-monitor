"""PushPlus (WeChat push) notification channel."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from fund_monitor.domain import ChannelType, NotificationMessage
from fund_monitor.notifications.pushplus import PushPlusChannel


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, payload=None):
        self.sent: list[tuple[str, dict]] = []
        self.payload = payload or {"code": 200, "msg": "ok"}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        self.sent.append((parsed.path, parse_qs(parsed.query)))
        return httpx.Response(200, json=self.payload)


@pytest.mark.asyncio
async def test_pushplus_posts_token_title_and_content() -> None:
    transport = FakeTransport()
    client = httpx.AsyncClient(transport=transport)
    channel = PushPlusChannel(channel_id=1, name="微信推送", token="TOKEN123", client=client)

    await channel.send(NotificationMessage(title="基金监控", body="科创100 +5.07%"))

    assert len(transport.sent) == 1
    path, params = transport.sent[0]
    assert path == "/send"
    assert params["token"] == ["TOKEN123"]
    assert params["title"] == ["基金监控"]
    assert params["content"] == ["科创100 +5.07%"]
    assert params["template"] == ["markdown"]
    await client.aclose()


@pytest.mark.asyncio
async def test_pushplus_rejects_bad_token() -> None:
    transport = FakeTransport(payload={"code": 903, "msg": "无效的用户token"})
    client = httpx.AsyncClient(transport=transport)
    channel = PushPlusChannel(channel_id=1, name="微信推送", token="BAD", client=client)

    with pytest.raises(RuntimeError, match="无效的用户token"):
        await channel.send(NotificationMessage(title="t", body="b"))
    await client.aclose()


def test_pushplus_requires_token() -> None:
    try:
        PushPlusChannel(channel_id=1, name="微信推送", token="")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when token is empty")


def test_channel_type_is_pushplus() -> None:
    assert PushPlusChannel.channel_type == ChannelType.PUSHPLUS
