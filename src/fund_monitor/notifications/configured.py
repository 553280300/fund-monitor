"""Build enabled notification adapters from local channel configuration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fund_monitor.domain import ChannelConfig, ChannelType, NotificationMessage
from fund_monitor.notifications.base import DeliveryResult, DeliveryStatus, NotificationChannel, NotificationDispatcher
from fund_monitor.notifications.telegram import TelegramChannel
from fund_monitor.notifications.webhook import WebhookChannel
from fund_monitor.notifications.email import EmailChannel
from fund_monitor.notifications.desktop import DesktopChannel
from fund_monitor.notifications.serverchan import ServerChanChannel
from fund_monitor.notifications.pushplus import PushPlusChannel
from fund_monitor.secrets import SecretStore
from fund_monitor.storage import Database


class ChannelFactory:
    def __init__(self, secrets: SecretStore) -> None:
        self._secrets = secrets

    def __call__(self, config: ChannelConfig) -> NotificationChannel:
        secret = self._secrets.get(f"channel:{config.id}")
        if config.channel_type == ChannelType.TELEGRAM:
            return TelegramChannel(channel_id=config.id or 0, name=config.name, chat_id=config.settings["chat_id"], token=secret or "")
        if config.channel_type == ChannelType.WEBHOOK:
            return WebhookChannel(channel_id=config.id or 0, name=config.name, url=config.settings["url"], secret=secret)
        if config.channel_type == ChannelType.EMAIL:
            return EmailChannel(channel_id=config.id or 0, name=config.name, host=config.settings["host"],
                                port=int(config.settings.get("port", "465")), username=config.settings["username"],
                                password=secret or "", sender_address=config.settings["sender_address"],
                                recipient=config.settings["recipient"])
        if config.channel_type == ChannelType.SERVERCHAN:
            return ServerChanChannel(channel_id=config.id or 0, name=config.name, send_key=secret or "")
        if config.channel_type == ChannelType.PUSHPLUS:
            return PushPlusChannel(channel_id=config.id or 0, name=config.name, token=secret or "")
        if config.channel_type == ChannelType.DESKTOP:
            return DesktopChannel(channel_id=config.id or 0, name=config.name)
        raise ValueError(f"Channel type {config.channel_type.value} is not configured")


class ConfiguredDispatcher:
    def __init__(self, database: Database, *, builder: Callable[[ChannelConfig], NotificationChannel] | None = None, secrets: SecretStore | None = None) -> None:
        self._database = database
        self._builder = builder or ChannelFactory(secrets or SecretStore())

    async def dispatch(
        self, message: NotificationMessage, *, channel_ids: tuple[int, ...] = ()
    ) -> list[DeliveryResult]:
        channels: list[NotificationChannel] = []
        failures: list[DeliveryResult] = []
        for config in self._database.channels.list():
            if not config.enabled:
                continue
            if channel_ids and config.id not in channel_ids:
                continue
            try:
                channels.append(self._builder(config))
            except Exception:
                failures.append(DeliveryResult(channel_id=config.id or 0, channel_type=config.channel_type, channel_name=config.name, status=DeliveryStatus.FAILED, attempted_at=datetime.now(timezone.utc), detail="Channel configuration is incomplete or invalid."))
        return failures + await NotificationDispatcher(channels).dispatch(message)
