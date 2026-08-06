# Fund Monitor Desktop V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Windows-first, local-first fund and market monitoring application that non-technical users can launch, configure, monitor, and package without a system-wide Python installation.

**Architecture:** A typed Python monitoring core is independent of delivery concerns. Provider and notification adapters normalize external I/O; SQLite persists state; an asyncio scheduler evaluates rules; FastAPI exposes the local API and serves a vanilla-JavaScript management panel. A Windows launcher starts one loopback-only process and opens the panel after health succeeds.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, Uvicorn, SQLite (`sqlite3`), `httpx`, `keyring`, pytest, Playwright, PyInstaller, vanilla HTML/CSS/JavaScript.

## Global Constraints

- Bind the API to `127.0.0.1` only unless the user explicitly opts in to remote access.
- Store runtime state under `%LOCALAPPDATA%\\FundMonitor`; never commit user configuration, databases, credentials, logs, `build/`, or `dist/`.
- Use provider and channel adapters; do not put provider- or channel-specific conditions in monitoring orchestration.
- Do not generate trading instructions, investment advice, or automated orders.
- Every network request has an explicit timeout and produces an observable, non-secret error state on failure.
- All alert deduplication must survive process restarts through SQLite uniqueness constraints.
- Add a failing focused test before every production behavior change, then run the focused and full suites.
- Release acceptance requires a Windows packaged-launch smoke test, not merely a successful build.

---

## Planned File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Dependencies, test configuration, package metadata, PyInstaller entry point metadata. |
| `src/fund_monitor/domain.py` | Domain enums and immutable typed models shared by all layers. |
| `src/fund_monitor/config.py` | Runtime path discovery and validated editable settings. |
| `src/fund_monitor/storage.py` | SQLite schema creation and repositories. |
| `src/fund_monitor/providers/base.py` | Provider protocol and common provider result/error models. |
| `src/fund_monitor/providers/*.py` | Tencent, Eastmoney, Yahoo adapters and registry. |
| `src/fund_monitor/notifications/base.py` | Notification protocol and dispatcher. |
| `src/fund_monitor/notifications/*.py` | Desktop, SMTP, Telegram, webhook, optional Hermes adapters. |
| `src/fund_monitor/monitoring.py` | Provider fallback, alert evaluation, deduplication and dispatch orchestration. |
| `src/fund_monitor/scheduler.py` | Configured asynchronous polling lifecycle. |
| `src/fund_monitor/api.py` | Loopback FastAPI routes and static panel service. |
| `src/fund_monitor/launcher.py` | Single-instance local startup and browser launch. |
| `web/` | Plain browser management panel. |
| `tests/` | Unit, API, fixture, browser and packaging smoke tests. |
| `packaging/` | PyInstaller spec, launcher resources, installer/release scripts. |
| `docs/` | Customer-facing quick start, privacy, troubleshooting and risk documents. |

## Task 1: Create The Reproducible Application Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `src/fund_monitor/__init__.py`
- Create: `src/fund_monitor/__main__.py`
- Create: `tests/test_package.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `fund_monitor.__version__`, `python -m fund_monitor`, and a testable package layout used by all later tasks.

- [ ] **Step 1: Write the failing package test**

```python
from fund_monitor import __version__


def test_package_exposes_a_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest tests/test_package.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'fund_monitor'`.

- [ ] **Step 3: Add the package and development configuration**

```toml
[project]
name = "fund-monitor"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi>=0.115", "uvicorn[standard]>=0.30", "httpx>=0.27", "keyring>=25"]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "playwright>=1.49", "pyinstaller>=6.10"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
```

```python
# src/fund_monitor/__init__.py
__version__ = "0.1.0"
```

```python
# src/fund_monitor/__main__.py
from fund_monitor.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
```

Add `.venv/`, `.pytest_cache/`, `__pycache__/`, `*.db`, `*.log`, `build/`, and `dist/` to `.gitignore`.

- [ ] **Step 4: Install development dependencies and run the focused test**

Run: `python -m pip install -e ".[dev]"; python -m pytest tests/test_package.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml src/fund_monitor tests/test_package.py .gitignore
git commit -m "build: create fund monitor package skeleton"
```

## Task 2: Define Domain Models And Validated Local Settings

**Files:**
- Create: `src/fund_monitor/domain.py`
- Create: `src/fund_monitor/config.py`
- Create: `tests/test_domain.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `AssetKind`, `AlertKind`, `ChannelType`, `Asset`, `Observation`, `ProviderResult`, `AlertRule`, `AppSettings`, and `runtime_paths()`.
- Consumed by: storage, providers, monitoring, API and notification adapters.

- [ ] **Step 1: Write failing validation tests**

```python
from pydantic import ValidationError
from fund_monitor.domain import Asset, AssetKind, AlertRule, AlertKind


def test_asset_requires_a_provider_identifier() -> None:
    with pytest.raises(ValidationError):
        Asset(name="Test", kind=AssetKind.FUND, identifiers={})


def test_threshold_rule_rejects_zero_cooldown() -> None:
    with pytest.raises(ValidationError):
        AlertRule(asset_id=1, kind=AlertKind.PERCENT_CHANGE, threshold=1.0, cooldown_minutes=0)
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/test_domain.py tests/test_config.py -q`

Expected: FAIL because domain/config modules do not exist.

- [ ] **Step 3: Implement typed models and local paths**

```python
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


class Asset(BaseModel):
    id: int | None = None
    name: str
    kind: AssetKind
    identifiers: dict[str, str] = Field(min_length=1)
    enabled: bool = True
```

Use `Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "FundMonitor"` as the default runtime root. Allow `FUND_MONITOR_DATA_DIR` for tests and explicit portable deployments. `AppSettings` must reject a non-loopback host unless `allow_remote_access=True`.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_domain.py tests/test_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/fund_monitor/domain.py src/fund_monitor/config.py tests/test_domain.py tests/test_config.py
git commit -m "feat: add typed domain and local settings models"
```

## Task 3: Build SQLite Repositories And Restart-Safe Deduplication

**Files:**
- Create: `src/fund_monitor/storage.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Consumes: domain `Asset`, `AlertRule`, observations, events and delivery models.
- Produces: `Database`, `AssetRepository`, `RuleRepository`, `AlertRepository`, `HealthRepository` and `initialize_database(path)`.

- [ ] **Step 1: Write failing repository tests**

```python
def test_alert_fingerprint_is_unique_after_reopening_database(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    first = initialize_database(db_path)
    assert first.alerts.record_if_new("fund:1:percent:2026-08-05") is True
    first.close()

    second = initialize_database(db_path)
    assert second.alerts.record_if_new("fund:1:percent:2026-08-05") is False
```

- [ ] **Step 2: Run it and verify failure**

Run: `python -m pytest tests/test_storage.py -q`

Expected: FAIL because `initialize_database` does not exist.

- [ ] **Step 3: Implement schema migrations and repositories**

Create tables for `assets`, `alert_rules`, `observations`, `alerts`, `deliveries`, `provider_health`, and `channel_health`. The `alerts.fingerprint` column must have a `UNIQUE` constraint. Repositories must use parameterized SQL and explicit transactions. Store timestamps as UTC ISO-8601 strings.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_storage.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/fund_monitor/storage.py tests/test_storage.py
git commit -m "feat: persist monitoring state in sqlite"
```

## Task 4: Normalize Market Providers And Provider Fallback

**Files:**
- Create: `src/fund_monitor/providers/__init__.py`
- Create: `src/fund_monitor/providers/base.py`
- Create: `src/fund_monitor/providers/tencent.py`
- Create: `src/fund_monitor/providers/eastmoney.py`
- Create: `src/fund_monitor/providers/yahoo.py`
- Create: `src/fund_monitor/providers/registry.py`
- Create: `tests/providers/test_tencent.py`
- Create: `tests/providers/test_eastmoney.py`
- Create: `tests/providers/test_yahoo.py`
- Create: `tests/providers/test_registry.py`
- Create: `tests/fixtures/providers/`

**Interfaces:**
- Produces: `MarketProvider.fetch(asset) -> ProviderResult`, `ProviderRegistry.fetch_with_fallback(asset)`.
- Consumed by: monitoring orchestration and search API.

- [ ] **Step 1: Write failing parsing and fallback tests from fixture files**

```python
@pytest.mark.asyncio
async def test_tencent_fund_fixture_normalizes_estimated_change(httpx_mock) -> None:
    httpx_mock.add_response(text=load_fixture("tencent_fund.txt"), encoding="gbk")
    result = await TencentProvider(httpx.AsyncClient()).fetch(fund_asset())
    assert result.observation.value == Decimal("1.2345")
    assert result.observation.change_percent == Decimal("-1.28")


@pytest.mark.asyncio
async def test_registry_uses_next_provider_after_timeout() -> None:
    registry = ProviderRegistry([TimeoutProvider(), SuccessProvider()])
    result = await registry.fetch_with_fallback(fund_asset())
    assert result.source == "success"
```

- [ ] **Step 2: Run provider tests and verify failure**

Run: `python -m pytest tests/providers -q`

Expected: FAIL because providers are not implemented.

- [ ] **Step 3: Implement protocols, source adapters and fixture-backed parsing**

Use `httpx.AsyncClient` with a 15-second default timeout. A `ProviderResult` is either a normalized observation/events or a typed `ProviderError` containing source, error category, user-safe message, and occurrence time. Do not shell out to `curl`; replace the existing scripts with async HTTP adapters. Implement Tencent for funds and Chinese indices, Eastmoney for confirmed NAV/dividends/manager history, Yahoo for global indices. The registry selects compatible providers in priority order and returns the first valid result while retaining failure details for health recording.

- [ ] **Step 4: Run provider tests**

Run: `python -m pytest tests/providers -q`

Expected: PASS with no live-network dependency.

- [ ] **Step 5: Commit**

```powershell
git add src/fund_monitor/providers tests/providers tests/fixtures/providers
git commit -m "feat: add normalized market provider adapters"
```

## Task 5: Implement Alert Evaluation, Quiet Hours, Cooldowns And Manual Checks

**Files:**
- Create: `src/fund_monitor/monitoring.py`
- Create: `tests/test_monitoring.py`

**Interfaces:**
- Consumes: `ProviderRegistry`, repositories, assets and alert rules.
- Produces: `MonitoringService.check_asset(asset_id) -> CheckSummary`, `MonitoringService.run_once() -> RunSummary`.

- [ ] **Step 1: Write failing behavioral tests**

```python
async def test_percent_rule_triggers_once_on_threshold_crossing(service) -> None:
    service.provider.set_changes([Decimal("-0.9"), Decimal("-1.2"), Decimal("-1.3")])
    assert (await service.run_once()).alerts_created == 0
    assert (await service.run_once()).alerts_created == 1
    assert (await service.run_once()).alerts_created == 0


async def test_quiet_hours_records_alert_without_sending(service) -> None:
    service.clock.set("2026-08-05T23:00:00+08:00")
    summary = await service.run_once()
    assert summary.alerts_created == 1
    assert summary.deliveries_attempted == 0
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_monitoring.py -q`

Expected: FAIL because `MonitoringService` does not exist.

- [ ] **Step 3: Implement rule evaluation and event fingerprints**

Compute threshold crossings against the latest stored observation. For dividend and manager-change rules, derive a stable fingerprint from provider event id or canonical `(asset, kind, effective_date, title)` fields. Apply cooldown and quiet-hour decisions before dispatch but persist every detected alert. `check_asset()` must work regardless of the scheduler, enabling panel-driven manual refresh.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_monitoring.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/fund_monitor/monitoring.py tests/test_monitoring.py
git commit -m "feat: evaluate alerts with persistent deduplication"
```

## Task 6: Add Notification Adapters And Secret-Safe Configuration

**Files:**
- Create: `src/fund_monitor/notifications/__init__.py`
- Create: `src/fund_monitor/notifications/base.py`
- Create: `src/fund_monitor/notifications/desktop.py`
- Create: `src/fund_monitor/notifications/email.py`
- Create: `src/fund_monitor/notifications/telegram.py`
- Create: `src/fund_monitor/notifications/webhook.py`
- Create: `src/fund_monitor/notifications/hermes.py`
- Create: `tests/notifications/test_dispatcher.py`
- Create: `tests/notifications/test_secret_redaction.py`

**Interfaces:**
- Produces: `NotificationDispatcher.dispatch(alert) -> list[DeliveryResult]`, `SecretStore.get/set/delete(channel_id, secret)`.
- Consumed by: monitoring service and channel API routes.

- [ ] **Step 1: Write failing dispatcher and redaction tests**

```python
async def test_one_failed_channel_does_not_stop_another(dispatcher, alert) -> None:
    results = await dispatcher.dispatch(alert)
    assert [item.status for item in results] == ["failed", "sent"]


def test_channel_export_never_contains_secret(api_client) -> None:
    api_client.put("/api/v1/channels/telegram", json={"chat_id": "1", "token": "super-secret"})
    exported = api_client.get("/api/v1/config/export").json()
    assert "super-secret" not in str(exported)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/notifications -q`

Expected: FAIL because dispatcher and secret handling do not exist.

- [ ] **Step 3: Implement adapters and dispatch isolation**

Use `keyring` for real credentials, while SQLite stores non-secret channel metadata. Implement Windows desktop notification with a supported local library or Windows-native bridge selected during implementation and isolate it behind `DesktopChannel`. For SMTP, Telegram, webhook and Hermes, validate configuration without logging secrets. The dispatcher records one delivery outcome per channel and continues after any failure.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/notifications -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/fund_monitor/notifications tests/notifications
git commit -m "feat: add isolated notification channels"
```

## Task 7: Add Scheduler Lifecycle And Service Health

**Files:**
- Create: `src/fund_monitor/scheduler.py`
- Create: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `MonitoringService`, validated settings, a clock abstraction.
- Produces: `MonitorScheduler.start()`, `MonitorScheduler.stop()`, `MonitorScheduler.status()`.

- [ ] **Step 1: Write failing lifecycle tests**

```python
async def test_scheduler_runs_immediately_then_waits_for_interval(fake_monitor, fake_clock) -> None:
    scheduler = MonitorScheduler(fake_monitor, interval_seconds=60, clock=fake_clock)
    await scheduler.start()
    assert fake_monitor.run_count == 1
    await scheduler.stop()


async def test_scheduler_records_error_and_continues_after_failed_run(fake_monitor) -> None:
    fake_monitor.fail_next_run()
    scheduler = MonitorScheduler(fake_monitor, interval_seconds=1)
    await scheduler.run_cycle()
    await scheduler.run_cycle()
    assert fake_monitor.run_count == 2
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_scheduler.py -q`

Expected: FAIL because scheduler module does not exist.

- [ ] **Step 3: Implement asyncio scheduler**

Use a single `asyncio.Task`, cancellation-safe stop, immediate first run, configurable interval, and a reentrancy lock. The scheduler reports `running`, `last_started_at`, `last_finished_at`, `last_error`, and next due time. Trading-window filtering belongs in a pure function tested for Asia/Shanghai schedules; a manual check bypasses that filter.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_scheduler.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/fund_monitor/scheduler.py tests/test_scheduler.py
git commit -m "feat: schedule resilient local monitoring"
```

## Task 8: Expose A Loopback FastAPI Application

**Files:**
- Create: `src/fund_monitor/api.py`
- Create: `src/fund_monitor/dependencies.py`
- Create: `tests/test_api_health.py`
- Create: `tests/test_api_assets.py`
- Create: `tests/test_api_channels.py`
- Create: `tests/test_api_history.py`

**Interfaces:**
- Produces: `create_app(settings: AppSettings) -> FastAPI`.
- Routes: `GET /api/health`, asset and rule CRUD, manual check, channel configuration/test, history, provider health, configuration export, and static web files.

- [ ] **Step 1: Write failing API contract tests**

```python
def test_health_is_loopback_ready(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] in {"healthy", "degraded"}


def test_asset_create_rejects_unknown_kind(client) -> None:
    response = client.post("/api/v1/assets", json={"name": "bad", "kind": "crypto", "identifiers": {"x": "1"}})
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_api_health.py tests/test_api_assets.py tests/test_api_channels.py tests/test_api_history.py -q`

Expected: FAIL because `create_app` does not exist.

- [ ] **Step 3: Implement local API, lifecycle and redaction**

Create the application through a factory. On lifespan start, initialize database and scheduler; on shutdown, stop scheduler and close resources. Serve `web/index.html` for non-API local paths. Mutating routes validate typed payloads; configuration export replaces all credential values with `"***"`; no route returns keyring content. Add CORS only for the loopback panel origin.

- [ ] **Step 4: Run focused API tests**

Run: `python -m pytest tests/test_api_health.py tests/test_api_assets.py tests/test_api_channels.py tests/test_api_history.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/fund_monitor/api.py src/fund_monitor/dependencies.py tests/test_api_*.py
git commit -m "feat: expose local management api"
```

## Task 9: Build The Browser Management Panel

**Files:**
- Create: `web/index.html`
- Create: `web/assets/app.js`
- Create: `web/assets/api.js`
- Create: `web/assets/style.css`
- Create: `tests/browser/panel.spec.ts`
- Modify: `src/fund_monitor/api.py`

**Interfaces:**
- Consumes: local `/api/health` and `/api/v1/*` contracts from Task 8.
- Produces: dashboard, assets, alert rules, channels, history, and visible health/error states.

- [ ] **Step 1: Write failing browser workflow tests**

```typescript
test('user adds a fund and runs a manual check', async ({ page }) => {
  await page.goto('http://127.0.0.1:8420');
  await page.getByRole('link', { name: '资产' }).click();
  await page.getByRole('button', { name: '添加资产' }).click();
  await page.getByLabel('资产代码').fill('019860');
  await page.getByRole('button', { name: '保存' }).click();
  await expect(page.getByText('019860')).toBeVisible();
});
```

- [ ] **Step 2: Run browser test and verify failure**

Run: `npx playwright test tests/browser/panel.spec.ts`

Expected: FAIL because no panel is served.

- [ ] **Step 3: Implement responsive, task-oriented UI**

Build a dense local operations UI: persistent navigation; dashboard health summary; tabular asset management; rule editor; channel settings; alert history; and clear data-source timestamps. Use semantic forms, validation messages, keyboard-accessible controls, loading states, and empty/error states. Do not use remote CDN dependencies so the packaged application works offline except for market and notification requests.

- [ ] **Step 4: Run browser test and inspect screenshots**

Run: `npx playwright test tests/browser/panel.spec.ts --project=chromium`

Expected: PASS and no console errors.

- [ ] **Step 5: Commit**

```powershell
git add web src/fund_monitor/api.py tests/browser
git commit -m "feat: add local monitoring management panel"
```

## Task 10: Add Windows Launch, Single Instance And Packaging

**Files:**
- Create: `src/fund_monitor/launcher.py`
- Create: `packaging/fund_monitor.spec`
- Create: `packaging/build.ps1`
- Create: `tests/test_launcher.py`
- Create: `tests/test_packaging_smoke.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `main(argv: Sequence[str] | None = None) -> int`, `build.ps1`, and `dist/FundMonitor/FundMonitor.exe`.

- [ ] **Step 1: Write failing launch behavior tests**

```python
def test_second_launch_opens_existing_panel_without_starting_server(mocker) -> None:
    lock = mocker.Mock(acquired=False)
    launch = Launcher(lock_factory=lambda _: lock, browser_open=mocker.Mock())
    assert launch.run() == 0
    launch.browser_open.assert_called_once()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_launcher.py tests/test_packaging_smoke.py -q`

Expected: FAIL because launcher and build outputs do not exist.

- [ ] **Step 3: Implement launcher and deterministic PyInstaller build**

Implement a file or named-mutex single-instance guard. The first launch starts Uvicorn bound to loopback, polls `/api/health` with a bounded timeout, then opens the default browser. A second launch only opens the existing local URL. `build.ps1` cleans no user data, builds from the active virtual environment, verifies the executable exists, and writes artifacts under `dist/`. Include `web/` as packaged data.

- [ ] **Step 4: Run focused tests and build**

Run: `python -m pytest tests/test_launcher.py tests/test_packaging_smoke.py -q; powershell -ExecutionPolicy Bypass -File packaging/build.ps1`

Expected: tests PASS and `dist/FundMonitor/FundMonitor.exe` exists.

- [ ] **Step 5: Commit**

```powershell
git add src/fund_monitor/launcher.py packaging tests/test_launcher.py tests/test_packaging_smoke.py pyproject.toml
git commit -m "build: package local windows application"
```

## Task 11: Create Sale-Ready User Documentation And Release Metadata

**Files:**
- Create: `LICENSE`
- Create: `docs/01-product-overview.md`
- Create: `docs/02-quick-start-windows.md`
- Create: `docs/03-asset-and-alert-configuration.md`
- Create: `docs/04-notification-channels.md`
- Create: `docs/05-troubleshooting.md`
- Create: `docs/06-privacy-and-data.md`
- Create: `docs/07-risk-disclaimer.md`
- Modify: `README.md`

**Interfaces:**
- Produces: customer-facing onboarding and legal/operational boundaries shipped in the release package.

- [ ] **Step 1: Write documentation acceptance tests**

```python
def test_release_documents_contain_required_boundaries() -> None:
    text = Path('docs/07-risk-disclaimer.md').read_text(encoding='utf-8')
    assert '不构成投资建议' in text
    assert Path('docs/06-privacy-and-data.md').exists()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_release_docs.py -q`

Expected: FAIL because release documents are incomplete.

- [ ] **Step 3: Write customer documents**

The quick-start must use screenshots generated from the actual panel, state expected startup time and data delays, explain how to configure each channel without exposing credentials, provide recovery steps, and clearly say the product is local-first informational software rather than investment advice. Select an appropriate license before sale; do not copy a license without determining commercial distribution terms.

- [ ] **Step 4: Run documentation tests**

Run: `python -m pytest tests/test_release_docs.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add README.md LICENSE docs tests/test_release_docs.py
git commit -m "docs: add customer onboarding and product boundaries"
```

## Task 12: Run Full Verification And Release Audit

**Files:**
- Create: `docs/release-checklist.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: every earlier task's executable, tests, package artifact, docs and UI.
- Produces: objective release evidence for the v1 acceptance criteria.

- [ ] **Step 1: Add a release checklist test and checklist**

```python
def test_release_checklist_lists_all_v1_acceptance_criteria() -> None:
    checklist = Path('docs/release-checklist.md').read_text(encoding='utf-8')
    assert 'Windows packaged launch' in checklist
    assert 'secrets' in checklist
    assert 'provider failure' in checklist
```

- [ ] **Step 2: Run it and verify failure**

Run: `python -m pytest tests/test_release_checklist.py -q`

Expected: FAIL until the release checklist is added.

- [ ] **Step 3: Execute full automated and visual verification**

Run:

```powershell
python -m pytest -q
npx playwright test --project=chromium
powershell -ExecutionPolicy Bypass -File packaging/build.ps1
```

Then launch the packaged executable on Windows, verify `GET /api/health`, add a sample asset/rule/channel, execute a manual check using fixture or test mode, verify an alert/delivery appears in history, close and relaunch, and verify no duplicate delivery occurs.

- [ ] **Step 4: Record results in the checklist**

Record command outputs, environment, artifact version, checksums, manual smoke observations, known provider limitations, and any excluded channels. Do not claim a source is real-time or guaranteed unless evidence proves it.

- [ ] **Step 5: Commit**

```powershell
git add docs/release-checklist.md README.md tests/test_release_checklist.py
git commit -m "docs: add v1 release verification checklist"
```

## Plan Self-Review

- Spec coverage: Tasks 1-3 establish local domain, configuration and durable state; Tasks 4-7 deliver extensible data, alert, notification and scheduling behavior; Tasks 8-9 deliver the local product experience; Tasks 10-12 deliver packaging, customer documentation and full acceptance evidence.
- Placeholder scan: no task defers implementation with a TODO or refers to an unspecified neighboring task; provider-specific response details are isolated to fixture-backed adapters.
- Type consistency: all later tasks consume the `Asset`, `AlertRule`, `ProviderResult`, `NotificationMessage`, repositories and `MonitoringService` produced by earlier tasks.
- Scope: v1 implements the whole confirmed local desktop product while explicitly excluding payment, cloud accounts, mobile apps and automated trading.
