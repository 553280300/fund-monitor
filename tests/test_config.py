import pytest
from pydantic import ValidationError

from fund_monitor.config import AppSettings, runtime_paths


def test_runtime_paths_uses_explicit_data_directory(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FUND_MONITOR_DATA_DIR", str(tmp_path))

    paths = runtime_paths()

    assert paths.root == tmp_path
    assert paths.database == tmp_path / "fund_monitor.db"


def test_remote_binding_requires_explicit_opt_in() -> None:
    with pytest.raises(ValidationError):
        AppSettings(host="0.0.0.0")
