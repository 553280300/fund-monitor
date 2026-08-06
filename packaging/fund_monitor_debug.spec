from pathlib import Path

project_root = Path(SPECPATH).parent
web_root = project_root / "web"

analysis = Analysis(
    [str(project_root / "src" / "fund_monitor" / "__main__.py")],
    pathex=[str(project_root / "src")],
    datas=[(str(web_root), "web")],
    hiddenimports=["fund_monitor.launcher", "fund_monitor.server"],
    binaries=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, analysis.binaries, analysis.zipfiles, analysis.datas, [], name="FundMonitorDebug", console=True)
