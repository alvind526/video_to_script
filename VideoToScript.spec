# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — self-contained Video to Script desktop app."""

import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None
ROOT = os.path.abspath(SPECPATH)

datas = []
binaries = []
hiddenimports = []

# Runtime packages (native libs + data files).
for pkg in (
    "faster_whisper",
    "ctranslate2",
    "av",
    "onnxruntime",
    "tokenizers",
    "huggingface_hub",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Embed speech model + app icon inside the package.
model_dir = os.path.join(ROOT, "models", "base")
if not os.path.isfile(os.path.join(model_dir, "model.bin")):
    raise SystemExit(
        "Missing models/base — run: python download_model.py\n"
        f"Expected: {model_dir}"
    )
datas += [(model_dir, os.path.join("models", "base"))]

assets_dir = os.path.join(ROOT, "assets")
for name in ("app.ico", "app.png"):
    path = os.path.join(assets_dir, name)
    if os.path.isfile(path):
        datas += [(path, "assets")]

icon_path = os.path.join(assets_dir, "app.ico")
if not os.path.isfile(icon_path):
    icon_path = None

a = Analysis(
    ["app.py"],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoToScript",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="VideoToScript",
)
