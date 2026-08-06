"""Typed domain models shared by the monitoring core and local API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssetKind(str, Enum):
    FUND = "fund"
    ETF = "etf"
    CN_INDEX = "cn_index"
    GLOBAL_INDEX = "global_index"


class AlertKind(str, Enum):
    PERCENT_CHANGE = "percent_change"
    NAV_CHANGE = "nav_change"
    DIVIDEND = "dividend"
    MANAGER_CHANGE = "manager_change"


class ChannelType(str, Enum):
    DESKTOP = "desktop"
    EMAIL = "email"
    TELEGRAM = "telegram"
    WEBHOOK = "webhook"
    HERMES = "hermes"
    SERVERCHAN = "serverchan"
    PUSHPLUS = "pushplus"


class ProviderErrorKind(str, Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    PARSE = "parse"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


class Asset(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    kind: AssetKind
    identifiers: dict[str, str] = Field(min_length=1)
    enabled: bool = True


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_id: int
    source: str
    observed_at: datetime
    value: Decimal | None = None
    change_percent: Decimal | None = None
    confirmed: bool = False
    label: str | None = None


class ProviderEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_id: int
    source: str
    kind: AlertKind
    occurred_at: datetime
    title: str = Field(min_length=1, max_length=240)
    external_id: str | None = None
    detail: str | None = None


class ProviderError(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    kind: ProviderErrorKind
    message: str = Field(min_length=1, max_length=500)
    occurred_at: datetime


class ProviderResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    observation: Observation | None = None
    events: tuple[ProviderEvent, ...] = ()
    error: ProviderError | None = None

    @model_validator(mode="after")
    def has_data_or_error(self) -> ProviderResult:
        if self.observation is None and not self.events and self.error is None:
            raise ValueError("provider result must contain an observation, event, or error")
        return self


class AlertRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None = None
    asset_id: int = Field(gt=0)
    kind: AlertKind
    threshold: Decimal | None = None
    enabled: bool = True
    cooldown_minutes: int = Field(gt=0, le=10080)
    quiet_hours: tuple[str, str] | None = None
    channel_ids: tuple[int, ...] = ()

    @model_validator(mode="after")
    def threshold_matches_rule_kind(self) -> AlertRule:
        threshold_rules = {AlertKind.PERCENT_CHANGE, AlertKind.NAV_CHANGE}
        if self.kind in threshold_rules and self.threshold is None:
            raise ValueError("threshold is required for numeric alert rules")
        if self.kind not in threshold_rules and self.threshold is not None:
            raise ValueError("threshold is only valid for numeric alert rules")
        return self


class NotificationMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    alert_id: int | None = None


class ChannelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None = None
    name: str = Field(min_length=1, max_length=80)
    channel_type: ChannelType
    enabled: bool = True
    settings: dict[str, str] = Field(default_factory=dict)


class AssetCandidate(BaseModel):
    """A search result offered when a user adds an asset by name or code."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=40)
    kind: AssetKind
    source: str = "eastmoney"
    description: str | None = None
    market: str | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    ticker_hints: list[str] = Field(default_factory=list)

    def to_identifiers(self) -> dict[str, str]:
        if self.kind == AssetKind.CN_INDEX:
            prefix = self.market or ("sz" if self.code.startswith("399") else "sh")
            return {"tencent": f"{prefix}{self.code}"}
        if self.kind == AssetKind.ETF:
            prefix = self.market or ("sz" if self.code.startswith("1") else "sh")
            return {"eastmoney": self.code, "tencent": f"{prefix}{self.code}"}
        if self.kind == AssetKind.FUND:
            return {self.source: self.code, "tencent": f"jj{self.code}"}
        return {self.source: self.code}
