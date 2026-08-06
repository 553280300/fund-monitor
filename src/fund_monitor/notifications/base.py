"""Notification adapter contracts and isolated dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Protocol

from fund_monitor.domain import ChannelType, NotificationMessage


class DeliveryStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True)
class DeliveryResult:
    channel_id: int
    channel_type: ChannelType
    channel_name: str
    status: DeliveryStatus
    attempted_at: datetime
    detail: str | None = None


class NotificationChannel(Protocol):
    channel_id: int
    channel_type: ChannelType
    name: str

    async def send(self, message: NotificationMessage) -> None: ...


class NotificationDispatcher:
    def __init__(self, channels: Iterable[NotificationChannel]) -> None:
        self._channels = list(channels)

    async def dispatch(
        self, message: NotificationMessage, *, channel_ids: tuple[int, ...] = ()
    ) -> list[DeliveryResult]:
        selected = self._channels
        if channel_ids:
            selected = [channel for channel in self._channels if channel.channel_id in channel_ids]
        results: list[DeliveryResult] = []
        for channel in selected:
            attempted_at = datetime.now(timezone.utc)
            try:
                await channel.send(message)
            except Exception:
                results.append(
                    DeliveryResult(
                        channel_id=channel.channel_id,
                        channel_type=channel.channel_type,
                        channel_name=channel.name,
                        status=DeliveryStatus.FAILED,
                        attempted_at=attempted_at,
                        detail="Delivery failed. Check this channel's configuration and status.",
                    )
                )
            else:
                results.append(
                    DeliveryResult(
                        channel_id=channel.channel_id,
                        channel_type=channel.channel_type,
                        channel_name=channel.name,
                        status=DeliveryStatus.SENT,
                        attempted_at=attempted_at,
                    )
                )
        return results
