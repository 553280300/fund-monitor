from pathlib import Path


def test_pyinstaller_spec_includes_local_web_assets() -> None:
    spec = Path("packaging/fund_monitor.spec").read_text(encoding="utf-8")
    assert "web" in spec
    assert "fund_monitor.launcher" in spec


def test_windows_build_script_uses_project_virtual_environment() -> None:
    script = Path("packaging/build.ps1").read_text(encoding="utf-8")
    assert ".venv\\Scripts\\python.exe" in script
    assert "PyInstaller" in script
