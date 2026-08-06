"""Generic JSON webhook notification channel."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from fund_monitor.domain import ChannelType, NotificationMessage


class WebhookChannel:
    channel_type = ChannelType.WEBHOOK

    def __init__(
        self,
        *,
        channel_id: int,
        name: str,
        url: str,
        secret: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("Webhook URL must be an absolute HTTP(S) URL")
        self.channel_id = channel_id
        self.name = name
        self._url = url
        self._secret = secret
        self._client = client

    async def send(self, message: NotificationMessage) -> None:
        headers = {"Content-Type": "application/json"}
        if self._secret:
            headers["Authorization"] = f"Bearer {self._secret}"
        payload = {"title": message.title, "body": message.body, "alert_id": message.alert_id}
        if self._client is not None:
            response = await self._client.post(self._url, json=payload, headers=headers, timeout=15)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(self._url, json=payload, headers=headers)
        response.raise_for_status()
