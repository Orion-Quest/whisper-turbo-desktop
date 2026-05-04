# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path.cwd()
src_root = project_root / "src"
entry_script = project_root / "bootstrap_main.py"
assets_root = project_root / "assets"
icon_path = assets_root / "app.ico"

a = Analysis(
    [str(entry_script)],
    pathex=[str(src_root)],
    binaries=[],
    datas=[],
    hiddenimports=["whisper_turbo_bootstrap.runtime"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(project_root / "packaging" / "bootstrap_runtime_hook.py")],
    excludes=[
        "PySide6",
        "torch",
        "whisper",
        "numpy",
        "numba",
        "scipy",
        "tiktoken",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WhisperTurboDesktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WhisperTurboBootstrap",
)
