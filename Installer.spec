# -*- mode: python ; coding: utf-8 -*-
# Installer.spec — PyInstaller build specification for NavTools setup
# Group No. 7 | 8th Semester Major Project 2026

import os
import glob
from pathlib import Path

block_cipher = None
PROJECT = Path(SPECPATH)

# Bundled payload containing the main application
bundled_data = [
    (str(PROJECT / "payload.zip"), "."),
]

a = Analysis(
    ['installer.py'],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=bundled_data,
    hiddenimports=['win32com.client'],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NavTools_Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,                 # <--- Requests Administrator privileges
    icon=str(PROJECT / "navtools.ico"),
)
