# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


repo_root = Path.cwd().resolve()
resources_root = repo_root / "resources"
datas = [
    (str(path), str(path.parent.relative_to(repo_root)))
    for path in resources_root.rglob("*")
    if path.is_file()
]

a = Analysis(
    [str(repo_root / "tools" / "runtime_entry.py")],
    pathex=[
        str(repo_root / "packages" / "core" / "src"),
        str(repo_root / "apps" / "cli" / "src"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="wechat-studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="wechat-studio",
)
