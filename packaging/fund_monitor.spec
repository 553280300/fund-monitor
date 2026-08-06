# PyInstaller specification for the Windows Fund Monitor desktop application.
from pathlib import Path

project_root = Path(SPECPATH).parent
web_root = project_root / "web"

analysis = Analysis(
    [str(project_root / "src" / "fund_monitor" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[(str(web_root), "web")],
    hiddenimports=["fund_monitor.launcher", "fund_monitor.server"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    [],
    name="FundMonitor",
    console=False,
)
