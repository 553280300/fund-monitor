import json

import httpx
import pytest

from fund_monitor.domain import ChannelType, NotificationMessage
from fund_monitor.notifications.webhook import WebhookChannel


@pytest.mark.asyncio
async def test_webhook_posts_a_minimal_alert_payload() -> None:
    received = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["body"] = json.loads(request.content)
        received["auth"] = request.headers.get("Authorization")
        return httpx.Response(204)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = WebhookChannel(
        channel_id=3,
        name="Webhook",
        url="https://example.test/hook",
        secret="secret",
        client=client,
    )

    await channel.send(NotificationMessage(title="Alert", body="Changed", alert_id=7))

    assert channel.channel_type == ChannelType.WEBHOOK
    assert received["body"] == {"title": "Alert", "body": "Changed", "alert_id": 7}
    assert received["auth"] == "Bearer secret"
    await client.aclose()
