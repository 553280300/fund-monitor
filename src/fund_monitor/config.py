"""Runtime paths and safe local-service settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    database: Path
    logs: Path
    exports: Path

    def ensure_directories(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.exports.mkdir(parents=True, exist_ok=True)


def runtime_paths() -> RuntimePaths:
    configured_root = os.environ.get("FUND_MONITOR_DATA_DIR")
    if configured_root:
        root = Path(configured_root).expanduser()
    else:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        root = local_app_data / "FundMonitor"
    return RuntimePaths(
        root=root,
        database=root / "fund_monitor.db",
        logs=root / "logs",
        exports=root / "exports",
    )


class AppSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8420, ge=1024, le=65535)
    allow_remote_access: bool = False
    polling_interval_seconds: int = Field(default=900, ge=60, le=86400)
    default_timezone: str = "Asia/Shanghai"
    schedule_times: list[str] = Field(
        default_factory=lambda: ["02:00", "06:00", "10:00", "14:00"],
        description="Trading-day monitoring nodes, HH:MM in default_timezone.",
    )

    @model_validator(mode="after")
    def schedule_times_are_hhmm(self) -> AppSettings:
        for slot in self.schedule_times:
            parts = slot.split(":")
            if len(parts) != 2:
                raise ValueError(f"schedule time must be HH:MM, got {slot!r}")
            hour, minute = parts
            if not (hour.isdigit() and minute.isdigit()):
                raise ValueError(f"schedule time must be HH:MM, got {slot!r}")
            if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                raise ValueError(f"schedule time out of range: {slot!r}")
        return self

    @model_validator(mode="after")
    def remote_access_requires_explicit_opt_in(self) -> AppSettings:
        if self.host not in {"127.0.0.1", "localhost", "::1"} and not self.allow_remote_access:
            raise ValueError("non-loopback binding requires allow_remote_access=True")
        return self
