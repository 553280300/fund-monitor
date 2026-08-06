# Fund Monitor Project Rules

## Product Boundary

- This is a Windows-first, local-first fund and market monitoring product for non-technical users.
- It provides information and alerts only. It must not generate trading instructions, investment advice, or automated orders.
- The local desktop deployment is the v1 delivery target. Hermes is optional and must not be required for normal operation.

## Repository Layout

- `src/fund_monitor/`: application packages. Keep domain logic independent from FastAPI and browser code.
- `tests/`: automated tests that mirror `src/fund_monitor/`.
- `config/`: versioned examples only. Never commit a real user configuration or credentials.
- `docs/`: user-facing documents and approved technical specifications.
- `scripts/`: developer, packaging, and maintenance scripts only; no product business logic.
- `build/` and `dist/`: generated packaging output; do not hand-edit or commit.

## Architecture Rules

- Use typed Python models at boundaries. Providers return normalized quotes/events; the monitoring core owns rules, deduplication, and persistence.
- New assets, market data sources, and notification channels must be adapters registered through stable interfaces. Do not add source-specific conditions to the monitoring core.
- SQLite stores local state, history, and alert records. Configuration is validated before it is persisted.
- Network failures must be isolated per provider/channel and visible to the user without terminating the scheduler.

## Privacy And Security

- User assets, monitoring history, and notification credentials remain local by default.
- Do not log, commit, display, or transmit passwords, API keys, bot tokens, email authorization codes, or webhook secrets.
- Bind the local API to loopback by default. Any non-local binding requires an explicit opt-in setting.

## Quality Gates

- Add a failing automated test before implementing a behavior change.
- Run the focused tests and the full test suite after changes.
- Validate all configuration examples and run an offline application smoke test before a release build.
- Test the packaged Windows launch flow on a clean environment before claiming it is ready to sell.

## Packaging Rules

- The delivered application must run without a system-wide Python installation.
- Runtime data belongs under the current user's application-data directory, never next to the installed executable.
- A build must include a license, a privacy statement, a user guide, a troubleshooting guide, and an investment-risk disclaimer.
