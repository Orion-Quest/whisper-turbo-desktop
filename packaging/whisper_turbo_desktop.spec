# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

project_root = Path.cwd()
src_root = project_root / "src"
entry_script = project_root / "main.py"
assets_root = project_root / "assets"
icon_path = assets_root / "app.ico"

datas = []
datas += collect_data_files("whisper")
datas += collect_data_files("tiktoken")
datas += [
    (str(assets_root / "config" / "default_settings.json"), "config"),
    (str(assets_root / "fonts" / "DejaVuSans.ttf"), "fonts"),
]

binaries = []
binaries += collect_dynamic_libs("torch")

hiddenimports = []
hiddenimports += collect_submodules("whisper")
hiddenimports += collect_submodules("tiktoken")

excludes = [
    "IPython",
    "matplotlib",
    "onnxruntime",
    "pandas",
    "pytest",
    "tensorflow",
    "torchvision",
]

a = Analysis(
    [str(entry_script)],
    pathex=[str(src_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name="WhisperTurboDesktop",
)
