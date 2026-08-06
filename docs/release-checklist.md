# Release Checklist

- [ ] Run `python -m pytest -q` in the project virtual environment.
- [ ] Run `powershell -ExecutionPolicy Bypass -File packaging\build.ps1`.
- [ ] Verify `dist\FundMonitor.exe` exists and record its SHA-256.
- [ ] Windows packaged launch: double-click the exe, wait for health, and verify the browser opens the local panel.
- [ ] Add one asset, one threshold rule, and run a manual check.
- [ ] Verify provider failure is visible and does not stop unrelated assets.
- [ ] Verify one alert produces one persisted delivery after restart.
- [ ] Verify each enabled notification channel with a non-production test recipient.
- [ ] Confirm exported files and logs contain no secrets.
- [ ] Ship this checklist with the quick-start, privacy, troubleshooting, and risk documents.
