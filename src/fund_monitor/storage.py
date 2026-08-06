"""SQLite persistence for local monitoring state."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fund_monitor.domain import AlertKind, AlertRule, Asset, AssetKind, ChannelConfig, ChannelType, Observation


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AssetRepository:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._connection = connection
        self._lock = lock

    def create(self, asset: Asset) -> Asset:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO assets (name, kind, identifiers_json, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.name,
                    asset.kind.value,
                    json.dumps(asset.identifiers, ensure_ascii=False, sort_keys=True),
                    int(asset.enabled),
                    _utc_now(),
                    _utc_now(),
                ),
            )
        return asset.model_copy(update={"id": cursor.lastrowid})

    def get(self, asset_id: int) -> Asset | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT id, name, kind, identifiers_json, enabled FROM assets WHERE id = ?",
                (asset_id,),
            ).fetchone()
        return self._row_to_asset(row) if row else None

    def list(self, *, enabled_only: bool = False) -> list[Asset]:
        query = "SELECT id, name, kind, identifiers_json, enabled FROM assets"
        params: tuple[Any, ...] = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY id"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._row_to_asset(row) for row in rows]

    def update(self, asset_id: int, asset: Asset) -> Asset | None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE assets
                SET name = ?, kind = ?, identifiers_json = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    asset.name,
                    asset.kind.value,
                    json.dumps(asset.identifiers, ensure_ascii=False, sort_keys=True),
                    int(asset.enabled),
                    _utc_now(),
                    asset_id,
                ),
            )
        if cursor.rowcount == 0:
            return None
        return asset.model_copy(update={"id": asset_id})

    def delete(self, asset_id: int) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        return cursor.rowcount == 1

    @staticmethod
    def _row_to_asset(row: sqlite3.Row) -> Asset:
        return Asset(
            id=row["id"],
            name=row["name"],
            kind=AssetKind(row["kind"]),
            identifiers=json.loads(row["identifiers_json"]),
            enabled=bool(row["enabled"]),
        )


class AlertRepository:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._connection = connection
        self._lock = lock

    def record_if_new(
        self,
        fingerprint: str,
        *,
        asset_id: int | None = None,
        rule_id: int | None = None,
        kind: str | None = None,
        title: str | None = None,
        detail: str | None = None,
    ) -> bool:
        return self.create_if_new(
            fingerprint, asset_id=asset_id, rule_id=rule_id, kind=kind, title=title, detail=detail
        ) is not None

    def create_if_new(
        self,
        fingerprint: str,
        *,
        asset_id: int | None = None,
        rule_id: int | None = None,
        kind: str | None = None,
        title: str | None = None,
        detail: str | None = None,
    ) -> int | None:
        try:
            with self._lock, self._connection:
                cursor = self._connection.execute(
                    """
                    INSERT INTO alerts (fingerprint, asset_id, rule_id, kind, title, detail, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (fingerprint, asset_id, rule_id, kind, title, detail, _utc_now()),
                )
        except sqlite3.IntegrityError:
            return None
        return cursor.lastrowid

    def latest_for_rule(self, rule_id: int) -> dict[str, Any] | None:
        """Return the most recent alert created by the given rule, if any."""
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, fingerprint, asset_id, kind, title, detail, created_at
                FROM alerts WHERE rule_id = ? ORDER BY id DESC LIMIT 1
                """,
                (rule_id,),
            ).fetchone()
        return dict(row) if row else None

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, fingerprint, asset_id, kind, title, detail, created_at
                FROM alerts ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


class DeliveryRepository:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._connection = connection
        self._lock = lock

    def record(self, alert_id: int, channel_id: int, status: str, detail: str | None = None) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO deliveries (alert_id, channel_id, status, detail, attempted_at)
                VALUES (?, ?, ?, ?, ?)""",
                (alert_id, channel_id, status, detail, _utc_now()),
            )

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, alert_id, channel_id, status, detail, attempted_at FROM deliveries ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


class ChannelRepository:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._connection = connection
        self._lock = lock

    def create(self, channel: ChannelConfig) -> ChannelConfig:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """INSERT INTO notification_channels (name, channel_type, enabled, settings_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (channel.name, channel.channel_type.value, int(channel.enabled),
                 json.dumps(channel.settings, ensure_ascii=False, sort_keys=True), _utc_now(), _utc_now()),
            )
        return channel.model_copy(update={"id": cursor.lastrowid})

    def list(self) -> list[ChannelConfig]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, name, channel_type, enabled, settings_json FROM notification_channels ORDER BY id"
            ).fetchall()
        return [ChannelConfig(id=row["id"], name=row["name"], channel_type=ChannelType(row["channel_type"]),
                              enabled=bool(row["enabled"]), settings=json.loads(row["settings_json"])) for row in rows]

    def get(self, channel_id: int) -> ChannelConfig | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT id, name, channel_type, enabled, settings_json FROM notification_channels WHERE id = ?",
                (channel_id,),
            ).fetchone()
        if row is None:
            return None
        return ChannelConfig(id=row["id"], name=row["name"], channel_type=ChannelType(row["channel_type"]),
                             enabled=bool(row["enabled"]), settings=json.loads(row["settings_json"]))

    def delete(self, channel_id: int) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM notification_channels WHERE id = ?", (channel_id,)
            )
        return cursor.rowcount == 1


class RuleRepository:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._connection = connection
        self._lock = lock

    def create(self, rule: AlertRule) -> AlertRule:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO alert_rules
                    (asset_id, kind, threshold, enabled, cooldown_minutes, quiet_hours_json,
                     channel_ids_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.asset_id, rule.kind.value, str(rule.threshold) if rule.threshold is not None else None,
                    int(rule.enabled), rule.cooldown_minutes,
                    json.dumps(rule.quiet_hours) if rule.quiet_hours else None,
                    json.dumps(rule.channel_ids), _utc_now(), _utc_now(),
                ),
            )
        return rule.model_copy(update={"id": cursor.lastrowid})

    def for_asset(self, asset_id: int, *, enabled_only: bool = True) -> list[AlertRule]:
        query = "SELECT * FROM alert_rules WHERE asset_id = ?"
        if enabled_only:
            query += " AND enabled = 1"
        query += " ORDER BY id"
        with self._lock:
            rows = self._connection.execute(query, (asset_id,)).fetchall()
        return [self._row_to_rule(row) for row in rows]

    @staticmethod
    def _row_to_rule(row: sqlite3.Row) -> AlertRule:
        return AlertRule(
            id=row["id"], asset_id=row["asset_id"], kind=AlertKind(row["kind"]),
            threshold=row["threshold"], enabled=bool(row["enabled"]),
            cooldown_minutes=row["cooldown_minutes"],
            quiet_hours=tuple(json.loads(row["quiet_hours_json"])) if row["quiet_hours_json"] else None,
            channel_ids=tuple(json.loads(row["channel_ids_json"])),
        )


class ObservationRepository:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._connection = connection
        self._lock = lock

    def add(self, observation: Observation) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO observations
                    (asset_id, source, observed_at, value, change_percent, confirmed, label)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (observation.asset_id, observation.source, observation.observed_at.isoformat(),
                 str(observation.value) if observation.value is not None else None,
                 str(observation.change_percent) if observation.change_percent is not None else None,
                 int(observation.confirmed), observation.label),
            )

    def latest_for_asset(self, asset_id: int) -> Observation | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM observations WHERE asset_id = ? ORDER BY id DESC LIMIT 1", (asset_id,)
            ).fetchone()
        if row is None:
            return None
        from decimal import Decimal
        return Observation(
            asset_id=row["asset_id"], source=row["source"],
            observed_at=datetime.fromisoformat(row["observed_at"]),
            value=Decimal(row["value"]) if row["value"] is not None else None,
            change_percent=Decimal(row["change_percent"]) if row["change_percent"] is not None else None,
            confirmed=bool(row["confirmed"]), label=row["label"],
        )


class HealthRepository:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._connection = connection
        self._lock = lock

    def record(self, component_type: str, component_name: str, status: str, detail: str | None = None) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO component_health (component_type, component_name, status, detail, checked_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(component_type, component_name) DO UPDATE SET
                    status = excluded.status,
                    detail = excluded.detail,
                    checked_at = excluded.checked_at
                """,
                (component_type, component_name, status, detail, _utc_now()),
            )

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT current.component_type, current.component_name, current.status,
                       current.detail, current.checked_at
                FROM component_health AS current
                WHERE current.rowid = (
                    SELECT latest.rowid
                    FROM component_health AS latest
                    WHERE latest.component_type = current.component_type
                      AND latest.component_name = current.component_name
                    ORDER BY latest.rowid DESC
                    LIMIT 1
                )
                ORDER BY current.component_type, current.component_name
                """
            ).fetchall()
        return [dict(row) for row in rows]


class RunRepository:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._connection = connection
        self._lock = lock

    def save(self, *, ran_at: str, period: str | None, report_json: str, report_text: str) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """INSERT INTO monitor_runs (ran_at, period, report_json, report_text)
                VALUES (?, ?, ?, ?)""",
                (ran_at, period, report_json, report_text),
            )
        return cursor.lastrowid

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, ran_at, period, report_json FROM monitor_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


@dataclass
class Database:
    connection: sqlite3.Connection
    _lock: threading.RLock = field(default_factory=threading.RLock)
    assets: AssetRepository = field(init=False)
    rules: RuleRepository = field(init=False)
    observations: ObservationRepository = field(init=False)
    alerts: AlertRepository = field(init=False)
    deliveries: DeliveryRepository = field(init=False)
    channels: ChannelRepository = field(init=False)
    health: HealthRepository = field(init=False)
    runs: RunRepository = field(init=False)

    def __post_init__(self) -> None:
        self.assets = AssetRepository(self.connection, self._lock)
        self.rules = RuleRepository(self.connection, self._lock)
        self.observations = ObservationRepository(self.connection, self._lock)
        self.alerts = AlertRepository(self.connection, self._lock)
        self.deliveries = DeliveryRepository(self.connection, self._lock)
        self.channels = ChannelRepository(self.connection, self._lock)
        self.health = HealthRepository(self.connection, self._lock)
        self.runs = RunRepository(self.connection, self._lock)

    def close(self) -> None:
        with self._lock:
            self.connection.close()


def initialize_database(path: Path) -> Database:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            identifiers_json TEXT NOT NULL,
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            threshold TEXT,
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            cooldown_minutes INTEGER NOT NULL,
            quiet_hours_json TEXT,
            channel_ids_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            source TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            value TEXT,
            change_percent TEXT,
            confirmed INTEGER NOT NULL CHECK (confirmed IN (0, 1)),
            label TEXT
        );
        CREATE INDEX IF NOT EXISTS observations_asset_time_idx
            ON observations(asset_id, observed_at DESC);

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY,
            fingerprint TEXT NOT NULL UNIQUE,
            asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
            rule_id INTEGER,
            kind TEXT,
            title TEXT,
            detail TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY,
            alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
            channel_id INTEGER,
            status TEXT NOT NULL,
            detail TEXT,
            attempted_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notification_channels (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            channel_type TEXT NOT NULL,
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            settings_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS component_health (
            component_type TEXT NOT NULL,
            component_name TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT,
            checked_at TEXT NOT NULL,
            PRIMARY KEY (component_type, component_name)
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS monitor_runs (
            id INTEGER PRIMARY KEY,
            ran_at TEXT NOT NULL,
            period TEXT,
            report_json TEXT NOT NULL,
            report_text TEXT NOT NULL
        );
        """
    )
    # Lightweight migration for databases created before alerts carried a rule_id.
    try:
        connection.execute("ALTER TABLE alerts ADD COLUMN rule_id INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already present in freshly created databases.
    return Database(connection)
