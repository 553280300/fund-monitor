# Fund Monitor Desktop Design

## Goal

Build a Windows-first, local-first application that lets non-technical users monitor funds and market instruments, manage alert rules in a browser interface, and receive reliable local or remote notifications without installing Python or Hermes.

## Product Scope

### Included In V1

- Manage monitored assets, thresholds, schedules, and notification channels from a local browser panel.
- Support Chinese public funds, ETFs, A-share indices, and common overseas indices through normalized provider adapters.
- Detect price or estimated-NAV threshold crossings, NAV changes, dividend announcements, and fund-manager changes when an enabled provider supplies the data.
- Persist configuration, current state, alert history, and provider/channel health locally in SQLite.
- Deliver alerts through Windows desktop notifications, SMTP email, Telegram, and generic webhooks. Hermes remains an optional notification adapter.
- Start from a Windows launcher that opens the local panel automatically and runs without a system-wide Python installation.
- Display data timestamps, data-source status, and a non-investment-advice disclaimer.

### Explicitly Excluded From V1

- Trading, portfolio execution, investment recommendations, or return promises.
- User accounts, cloud synchronization, payment processing, and subscription enforcement.
- Mobile applications and a public network-facing API.
- Claims that a third-party market-data endpoint is guaranteed, real-time, or suitable for trading.

## Architecture

The application is split into a reusable monitoring core and a local delivery shell. The core contains typed domain models, provider and notifier interfaces, alert evaluation, deduplication, scheduling, and SQLite persistence. FastAPI only exposes the core to the local panel and starts the scheduler; it does not contain product rules.

```
Windows launcher
  -> Local FastAPI service (127.0.0.1 only)
       -> Panel static files and REST API
       -> Scheduler
            -> Provider adapters -> normalized observations
            -> Alert engine -> SQLite state/history -> notifier adapters
```

### Core Modules

- `domain`: typed asset, observation, event, alert, channel, and health-state models.
- `providers`: adapters that fetch a provider-specific response and normalize it into observations/events. Each adapter declares supported asset kinds and source metadata.
- `monitoring`: coordinates provider fallback, evaluates rules, applies quiet hours and cooldowns, and records outcomes.
- `storage`: SQLite repositories plus schema initialization. Storage is behind repositories so the core does not issue SQL directly.
- `notifications`: adapters with one `send(notification)` contract; channel failures are recorded independently.
- `scheduler`: starts and stops the monitor using the configured interval and trading-window rules.

### Local Delivery Shell

- `api`: FastAPI routes for assets, rules, monitoring status, history, channels, and configuration validation.
- `web`: browser panel served by the local FastAPI application. It has dashboard, assets, rules, channels, and history views.
- `launcher`: starts the packaged process, waits for local health, opens the browser, and handles a second-launch request without starting a duplicate service.

## Extensibility Contracts

Asset support is capability-driven rather than conditional on source names. An asset contains an `asset_kind`, provider identifiers, display metadata, and enabled alert capabilities. A provider advertises the asset kinds and capabilities it supports, then returns normalized results.

```python
class MarketProvider(Protocol):
    name: str
    supported_kinds: set[AssetKind]

    async def fetch(self, asset: Asset) -> ProviderResult: ...

class NotificationChannel(Protocol):
    channel_type: ChannelType

    async def send(self, message: NotificationMessage) -> DeliveryResult: ...
```

The monitoring core consumes only `ProviderResult`, `Event`, and `DeliveryResult`. Adding a stock, bond, commodity, or another channel later requires a new adapter and contract tests, not changes to alert orchestration.

## Data And Privacy Model

- Runtime files live under `%LOCALAPPDATA%\\FundMonitor` by default.
- SQLite stores assets, alert rules, observation snapshots, event fingerprints, delivery records, health records, and application settings.
- Notification secrets are stored outside exported configurations. Exported configurations contain redacted placeholders only.
- The service binds only to `127.0.0.1`; no telemetry or cloud upload exists in v1.
- Every panel view displays data source and last-updated time; a source failure never silently reuses stale data as current data.

## Alert Semantics

- A threshold rule triggers on a crossing, not every polling interval while the value remains beyond the threshold.
- Each alert has a fingerprint derived from asset, rule, source event identity, and effective date. SQLite enforces uniqueness to prevent duplicates after restart.
- Rules support enabled state, cooldown, quiet hours, and per-channel routing.
- A provider failure creates a health record and may generate a rate-limited system notification; it does not generate a price alert.
- A notification failure is retried according to channel policy and shown in the panel. It does not block deliveries to other channels.

## User Experience

- The dashboard answers three questions first: what is being monitored, what changed, and whether monitoring is healthy.
- Asset creation begins with a code or symbol. The server searches supported providers, presents matches with source and asset kind, and validates the final choice before saving.
- The panel provides sensible default thresholds and schedules, but exposes source, schedule, and alert settings without requiring manual JSON editing.
- Plain-language copy distinguishes estimated values from confirmed NAV and includes the investment-risk disclaimer near market data and alert configuration.

## Packaging And Operations

- Development starts with a documented Python command; release distribution uses PyInstaller to produce a Windows executable and launcher.
- The launcher checks the local single-instance lock, starts the local server, polls `/api/health`, and opens the browser only after health succeeds.
- The distribution contains a license, privacy statement, quick-start guide, configuration guide, notification guide, troubleshooting guide, and risk disclaimer.
- Provider adapters use timeouts, response validation, source-specific parsing tests, and explicit error states. No endpoint is presented as guaranteed or real-time.

## Verification Strategy

- Unit tests cover normalization, configuration validation, crossing/cooldown/deduplication behavior, quiet hours, and notification routing.
- Provider fixtures cover successful responses, malformed responses, timeouts, and fallback selection without relying on live endpoints.
- API tests cover CRUD, validation failures, local health, and redaction of secret fields.
- Browser tests cover asset/rule/channel workflows and error states.
- A packaging smoke test verifies first launch, local health, browser opening, persisted data path, and a sample desktop notification on Windows.

## Acceptance Criteria

1. A Windows user can install or extract the release, launch it without Python, and reach the local panel.
2. The user can add each v1 asset kind, set a rule, run a manual check, and see a timestamped result or explicit source error.
3. A threshold crossing creates one persisted alert and delivers it to each enabled channel without duplicate sends after restart.
4. A failed provider or channel is visible in the panel and does not stop unrelated providers or channels.
5. Exported configuration and application logs do not contain notification secrets.
6. The full automated suite and packaging smoke test pass before release.
