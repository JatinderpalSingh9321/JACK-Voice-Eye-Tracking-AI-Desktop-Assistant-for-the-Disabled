# -*- mode: python ; coding: utf-8 -*-
# NavTools.spec — PyInstaller build specification
# Group No. 7 | 8th Semester Major Project 2026
# =====================================================================
# Build:  pyinstaller NavTools.spec
# Output: dist/NavTools/NavTools.exe
# =====================================================================

import os
import sys
import glob
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

block_cipher = None

PROJECT = Path(SPECPATH)
VENV    = PROJECT / ".venv"
SITELIB = VENV / "Lib" / "site-packages"

# ── Collect package data ───────────────────────────────────────────────
mediapipe_datas   = collect_data_files("mediapipe",   include_py_files=False)
sr_datas          = collect_data_files("speech_recognition")
kokoro_datas      = collect_data_files("kokoro_onnx")

# ── Project data files to bundle ──────────────────────────────────────
project_datas = [
    # Root-level HTML for the orb window
    (str(PROJECT / "orb.html"),                              "."),
    # Orb logo used by gui_app
    (str(PROJECT / "src" / "orb_logo.png"),                  "src"),
    # MediaPipe face landmark model
    (str(PROJECT / "data" / "face_landmarker.task"),         "data"),
    # Kokoro TTS ONNX model + voices
    (str(PROJECT / "models" / "kokoro" / "kokoro-v1.0.onnx"), "models/kokoro"),
    (str(PROJECT / "models" / "kokoro" / "voices-v1.0.bin"), "models/kokoro"),
]

# ── pywin32 system DLLs (pythoncom312.dll, pywintypes312.dll) ─────────
pywin32_dlls = [
    (str(p), ".")
    for p in glob.glob(str(SITELIB / "pywin32_system32" / "*.dll"))
]

# win32 extension DLLs
win32_dlls = [
    (str(p), "win32")
    for p in glob.glob(str(SITELIB / "win32" / "*.pyd"))
]

all_datas   = project_datas + mediapipe_datas + sr_datas + kokoro_datas
all_binaries = pywin32_dlls + win32_dlls

# ── Hidden imports ────────────────────────────────────────────────────
hidden_imports = [
    # PyQt5 WebEngine — must be explicit
    "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebEngineCore",
    "PyQt5.QtWebChannel",
    "PyQt5.QtNetwork",
    "PyQt5.sip",
    # pywin32 COM
    "win32api",
    "win32con",
    "win32com",
    "win32com.client",
    "win32com.server",
    "pythoncom",
    "pywintypes",
    "win32process",
    "win32gui",
    "win32ui",
    # Speech
    "speech_recognition",
    "pyaudio",
    "sounddevice",
    "soundfile",
    # Kokoro / ONNX
    "kokoro_onnx",
    "onnxruntime",
    "onnxruntime.capi",
    # MediaPipe
    "mediapipe",
    "mediapipe.python",
    "mediapipe.tasks",
    "mediapipe.tasks.python",
    "mediapipe.tasks.python.vision",
    # OpenCV
    "cv2",
    # Numpy / Scipy
    "numpy",
    "numpy.core._multiarray_umath",
    "scipy",
    "scipy.signal",
    # PyAutoGUI
    "pyautogui",
    "pygetwindow",
    # Project src package
    "src",
    "src.gui_app",
    "src.voice_assistant",
    "src.gaze_tracker",
    "src.gaze_mouse",
    "src.eye_tracker",
    "src.attention_state",
    "src.utils",
    "src.multimodal_launcher",
    # stdlib used at runtime
    "threading",
    "queue",
    "logging",
    "tkinter",
    "tkinter.ttk",
    "tkinter.scrolledtext",
    "tkinter.messagebox",
]

# ── Excludes — things we definitely don't need ────────────────────────
excludes = [
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "setuptools",
    "pip",
    "docutils",
    "PIL._imagingtk",  # keep PIL but skip Tk image backend
]

a = Analysis(
    [str(PROJECT / "main.py")],
    pathex=[str(PROJECT)],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    exclude_binaries=True,          # onedir mode
    name="NavTools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX causes issues with Qt; leave off
    console=False,                  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT / "navtools.ico"),
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NavTools",
)
