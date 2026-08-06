import httpx
import pytest

from fund_monitor.domain import NotificationMessage
from fund_monitor.notifications.telegram import TelegramChannel


@pytest.mark.asyncio
async def test_telegram_uses_send_message_endpoint_and_chat_id() -> None:
    received = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["url"] = str(request.url)
        received["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = TelegramChannel(channel_id=1, name="Telegram", chat_id="99", token="bot-token", client=client)

    await channel.send(NotificationMessage(title="Alert", body="Changed"))

    assert received["url"].endswith("/botbot-token/sendMessage")
    assert received["json"] == {"chat_id": "99", "text": "Alert\n\nChanged"}
    await client.aclose()
