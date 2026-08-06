"""Telegram Bot API notification channel."""

from __future__ import annotations

import httpx

from fund_monitor.domain import ChannelType, NotificationMessage


class TelegramChannel:
    channel_type = ChannelType.TELEGRAM

    def __init__(
        self,
        *,
        channel_id: int,
        name: str,
        chat_id: str,
        token: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not chat_id or not token:
            raise ValueError("Telegram chat_id and token are required")
        self.channel_id = channel_id
        self.name = name
        self._chat_id = chat_id
        self._token = token
        self._client = client

    async def send(self, message: NotificationMessage) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {"chat_id": self._chat_id, "text": f"{message.title}\n\n{message.body}"}
        if self._client is not None:
            response = await self._client.post(url, json=payload, timeout=15)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(url, json=payload)
        response.raise_for_status()
        if response.json().get("ok") is not True:
            raise RuntimeError("Telegram rejected the message")
