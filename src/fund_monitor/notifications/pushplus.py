"""PushPlus channel for WeChat push notifications (~200 free messages/day)."""

from __future__ import annotations

import httpx

from fund_monitor.domain import ChannelType, NotificationMessage

_PUSHPLUS_URL = "https://www.pushplus.plus/send"


class PushPlusChannel:
    channel_type = ChannelType.PUSHPLUS

    def __init__(
        self,
        *,
        channel_id: int,
        name: str,
        token: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token:
            raise ValueError("PushPlus token 不能为空")
        self.channel_id = channel_id
        self.name = name
        self._token = token
        self._client = client

    async def send(self, message: NotificationMessage) -> None:
        params = {
            "token": self._token,
            "title": message.title,
            "content": message.body,
            "template": "markdown",
        }
        if self._client is not None:
            response = await self._client.get(_PUSHPLUS_URL, params=params, timeout=15)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(_PUSHPLUS_URL, params=params)
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError(f"PushPlus 返回异常：{response.text[:200]}")
        if result.get("code") != 200:
            raise RuntimeError(result.get("msg") or "PushPlus 推送失败")
