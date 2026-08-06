"""SMTP email notification channel."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage

from fund_monitor.domain import ChannelType, NotificationMessage


Sender = Callable[[str, int, str, str, str, str, str, str], None]


class EmailChannel:
    channel_type = ChannelType.EMAIL

    def __init__(
        self, *, channel_id: int, name: str, host: str, port: int, username: str,
        password: str, sender_address: str, recipient: str, sender: Sender | None = None,
    ) -> None:
        if not all((host, username, password, sender_address, recipient)):
            raise ValueError("SMTP host, credentials, sender and recipient are required")
        self.channel_id, self.name = channel_id, name
        self._host, self._port = host, port
        self._username, self._password = username, password
        self._sender_address, self._recipient = sender_address, recipient
        self._sender = sender or self._send_smtp

    async def send(self, message: NotificationMessage) -> None:
        await asyncio.to_thread(self._sender, self._host, self._port, self._username, self._password,
                                self._sender_address, self._recipient, message.title, message.body)

    @staticmethod
    def _send_smtp(host: str, port: int, username: str, password: str, sender_address: str, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = sender_address, recipient, subject
        message.set_content(body)
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as client:
                client.login(username, password)
                client.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=15) as client:
                client.starttls(context=context)
                client.login(username, password)
                client.send_message(message)
