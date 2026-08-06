"""Windows desktop notification channel using built-in Windows Forms."""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Callable

from fund_monitor.domain import ChannelType, NotificationMessage


class DesktopChannel:
    channel_type = ChannelType.DESKTOP

    def __init__(self, *, channel_id: int = 0, name: str = "Desktop", runner: Callable[[str], None] | None = None) -> None:
        self.channel_id, self.name = channel_id, name
        self._runner = runner or self._run_powershell

    async def send(self, message: NotificationMessage) -> None:
        title = message.title.replace("'", "''")
        body = message.body.replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$n=New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon=[System.Drawing.SystemIcons]::Information; $n.Visible=$true; "
            f"$n.BalloonTipTitle='{title}'; $n.BalloonTipText='{body}'; "
            "$n.ShowBalloonTip(5000); Start-Sleep -Seconds 6; $n.Dispose()"
        )
        await asyncio.to_thread(self._runner, script)

    @staticmethod
    def _run_powershell(script: str) -> None:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Windows desktop notification failed")
