"""Provider fallback and deterministic alert evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fund_monitor.domain import (
    AlertKind,
    AlertRule,
    Asset,
    NotificationMessage,
    Observation,
    ProviderEvent,
)
from fund_monitor.providers.base import MarketProvider
from fund_monitor.providers.registry import ProviderRegistry
from fund_monitor.notifications.base import NotificationDispatcher
from fund_monitor.storage import Database


@dataclass(frozen=True)
class RuleCheck:
    """Whether a single rule crossed its threshold on the latest observation."""

    rule_id: int
    kind: str
    threshold: Decimal | None
    triggered: bool


@dataclass(frozen=True)
class AssetResult:
    asset_id: int
    name: str
    code: str
    kind: str
    source: str
    value: Decimal | None
    change_percent: Decimal | None
    observed_at: datetime | None
    previous_change_percent: Decimal | None
    alerts_created: int
    error: str | None
    rule_checks: tuple[RuleCheck, ...] = ()

    @property
    def status(self) -> str:
        if self.error is not None:
            return "error"
        return "alert" if self.alerts_created > 0 else "normal"


@dataclass(frozen=True)
class RunResult:
    ran_at: datetime
    period: str | None
    assets: tuple[AssetResult, ...]
    alerts_created: int
    errors: int

    @property
    def assets_checked(self) -> int:
        return len(self.assets)


class MonitoringService:
    def __init__(
        self,
        database: Database,
        providers: list[MarketProvider],
        *,
        dispatcher: NotificationDispatcher | None = None,
        timezone_name: str = "Asia/Shanghai",
    ) -> None:
        self._database = database
        self._providers = ProviderRegistry(providers)
        self._dispatcher = dispatcher
        self._timezone = MonitoringService._resolve_timezone(timezone_name)

    async def run_once(self, *, period: str | None = None) -> RunResult:
        results = [
            await self.check_asset(asset) for asset in self._database.assets.list(enabled_only=True)
        ]
        return RunResult(
            ran_at=datetime.now(timezone.utc),
            period=period,
            assets=tuple(results),
            alerts_created=sum(result.alerts_created for result in results),
            errors=sum(result.error is not None for result in results),
        )

    async def check_asset(self, asset: Asset | int) -> AssetResult:
        if isinstance(asset, int):
            resolved = self._database.assets.get(asset)
            if resolved is None:
                raise KeyError(f"asset {asset} does not exist")
            asset = resolved
        code = next(iter(asset.identifiers.values()), "")
        result = await self._providers.fetch_with_fallback(asset)
        if result.observation is None:
            error = result.error.message if result.error else "Provider returned no observation"
            self._database.health.record("provider", result.source, "error", error)
            return AssetResult(
                asset_id=asset.id or 0,
                name=asset.name,
                code=code,
                kind=asset.kind.value,
                source=result.source,
                value=None,
                change_percent=None,
                observed_at=None,
                previous_change_percent=None,
                alerts_created=0,
                error=error,
            )

        previous = self._database.observations.latest_for_asset(asset.id or 0)
        self._database.observations.add(result.observation)
        self._database.health.record("provider", result.source, "healthy")
        rule_checks, created = await self._evaluate_observation_rules(asset, previous, result.observation)
        created += await self._evaluate_events(asset, result.events)
        return AssetResult(
            asset_id=asset.id or 0,
            name=asset.name,
            code=code,
            kind=asset.kind.value,
            source=result.source,
            value=result.observation.value,
            change_percent=result.observation.change_percent,
            observed_at=result.observation.observed_at,
            previous_change_percent=previous.change_percent if previous else None,
            alerts_created=created,
            error=None,
            rule_checks=rule_checks,
        )

    async def _evaluate_observation_rules(
        self, asset: Asset, previous: Observation | None, current: Observation
    ) -> tuple[tuple[RuleCheck, ...], int]:
        checks: list[RuleCheck] = []
        created = 0
        for rule in self._database.rules.for_asset(asset.id or 0):
            triggered = self._observation_rule_triggered(rule, previous, current)
            checks.append(
                RuleCheck(
                    rule_id=rule.id or 0,
                    kind=rule.kind.value,
                    threshold=rule.threshold,
                    triggered=triggered,
                )
            )
            if not triggered:
                continue
            if not self._allowed_now(rule, current.observed_at):
                continue
            fingerprint = self._observation_fingerprint(rule, current)
            alert_id = self._database.alerts.create_if_new(
                fingerprint,
                asset_id=asset.id,
                rule_id=rule.id,
                kind=rule.kind.value,
                title=f"{asset.name} 异动提醒",
                detail=f"当前涨跌幅：{current.change_percent}%（数据源：{current.source}）",
            )
            if alert_id is not None:
                created += 1
                await self._dispatch(
                    alert_id,
                    rule,
                    NotificationMessage(
                        alert_id=alert_id,
                        title=f"{asset.name} 异动提醒",
                        body=f"当前涨跌幅：{current.change_percent}%（数据源：{current.source}）",
                    ),
                )
        return tuple(checks), created

    async def _evaluate_events(self, asset: Asset, events: tuple[ProviderEvent, ...]) -> int:
        created = 0
        for event in events:
            for rule in self._database.rules.for_asset(asset.id or 0):
                if rule.kind != event.kind:
                    continue
                if not self._allowed_now(rule, event.occurred_at):
                    continue
                fingerprint = self._event_fingerprint(rule, event)
                alert_id = self._database.alerts.create_if_new(
                    fingerprint,
                    asset_id=asset.id,
                    rule_id=rule.id,
                    kind=event.kind.value,
                    title=event.title,
                    detail=event.detail,
                )
                if alert_id is not None:
                    created += 1
                    await self._dispatch(
                        alert_id,
                        rule,
                        NotificationMessage(
                            alert_id=alert_id,
                            title=event.title,
                            body=event.detail or event.title,
                        ),
                    )
        return created

    async def _dispatch(
        self, alert_id: int, rule: AlertRule, message: NotificationMessage
    ) -> None:
        if self._dispatcher is None:
            return
        for result in await self._dispatcher.dispatch(message, channel_ids=rule.channel_ids):
            self._database.deliveries.record(
                alert_id, result.channel_id, result.status.value, result.detail
            )

    def _allowed_now(self, rule: AlertRule, observed_at: datetime) -> bool:
        """Apply quiet hours and per-rule cooldown; both are rule-level controls."""
        local = observed_at.astimezone(self._timezone)
        if not self._quiet_hours_allow(rule, local):
            return False
        latest = self._database.alerts.latest_for_rule(rule.id or 0)
        if latest is not None:
            last_at = datetime.fromisoformat(latest["created_at"])
            if local - last_at < timedelta(minutes=rule.cooldown_minutes):
                return False
        return True

    @staticmethod
    def _resolve_timezone(timezone_name: str) -> timezone | ZoneInfo:
        # Windows lacks the IANA tz database; fall back to fixed UTC+8
        # (Asia/Shanghai has no daylight saving) so the service still runs
        # without the tzdata package.
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return timezone(timedelta(hours=8), name="UTC+08:00")

    @staticmethod
    def _observation_rule_triggered(
        rule: AlertRule, previous: Observation | None, current: Observation
    ) -> bool:
        if rule.kind == AlertKind.PERCENT_CHANGE:
            return MonitoringService._threshold_crossed(rule, previous, current)
        if rule.kind == AlertKind.NAV_CHANGE:
            return MonitoringService._threshold_met_now(rule, current)
        return False

    @staticmethod
    def _threshold_crossed(
        rule: AlertRule, previous: Observation | None, current: Observation
    ) -> bool:
        if rule.threshold is None or current.change_percent is None:
            return False
        if not MonitoringService._threshold_met(current.change_percent, rule.threshold):
            return False
        if previous is None or previous.change_percent is None:
            return False
        return not MonitoringService._threshold_met(previous.change_percent, rule.threshold)

    @staticmethod
    def _threshold_met_now(rule: AlertRule, current: Observation) -> bool:
        if rule.threshold is None or current.change_percent is None:
            return False
        return MonitoringService._threshold_met(current.change_percent, rule.threshold)

    @staticmethod
    def _threshold_met(value: Decimal, threshold: Decimal) -> bool:
        return value <= threshold if threshold < 0 else value >= threshold

    @staticmethod
    def _observation_fingerprint(rule: AlertRule, observation: Observation) -> str:
        day = observation.observed_at.astimezone(timezone.utc).date().isoformat()
        return f"asset:{observation.asset_id}:rule:{rule.id}:kind:{rule.kind.value}:date:{day}"

    @staticmethod
    def _event_fingerprint(rule: AlertRule, event: ProviderEvent) -> str:
        if event.external_id:
            return f"asset:{event.asset_id}:rule:{rule.id}:kind:{event.kind.value}:event:{event.external_id}"
        day = event.occurred_at.astimezone(timezone.utc).date().isoformat()
        return f"asset:{event.asset_id}:rule:{rule.id}:kind:{event.kind.value}:event:{day}:{event.title}"

    @staticmethod
    def _quiet_hours_allow(rule: AlertRule, local: datetime) -> bool:
        if rule.quiet_hours is None:
            return True
        start_text, end_text = rule.quiet_hours
        start = MonitoringService._parse_hhmm(start_text)
        end = MonitoringService._parse_hhmm(end_text)
        now = local.time().replace(second=0, microsecond=0)
        if start <= end:
            return not (start <= now <= end)
        return now < start or now > end

    @staticmethod
    def _parse_hhmm(value: str) -> time:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
