"""Server酱 (ServerChan Turbo) channel for WeChat push notifications."""

from __future__ import annotations

import httpx

from fund_monitor.domain import ChannelType, NotificationMessage


class ServerChanChannel:
    channel_type = ChannelType.SERVERCHAN

    def __init__(
        self,
        *,
        channel_id: int,
        name: str,
        send_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not send_key:
            raise ValueError("Server酱 SendKey 不能为空")
        self.channel_id = channel_id
        self.name = name
        self._send_key = send_key
        self._client = client

    async def send(self, message: NotificationMessage) -> None:
        url = f"https://sctapi.ftqq.com/{self._send_key}.send"
        payload = {"title": message.title, "desp": message.body}
        if self._client is not None:
            response = await self._client.post(url, data=payload, timeout=15)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(url, data=payload)
        if response.status_code != 200:
            detail = ServerChanChannel._error_message(response)
            raise RuntimeError(f"Server酱返回错误：{detail}")
        result = response.json()
        if result.get("code") != 0:
            raise RuntimeError(result.get("message") or "Server酱 rejected the message")

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            return str(payload.get("message") or payload.get("info") or response.text)[:200]
        except ValueError:
            return response.text[:200]
