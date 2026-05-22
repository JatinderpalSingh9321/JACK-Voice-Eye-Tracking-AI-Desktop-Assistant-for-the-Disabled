@echo off
title NavTools Assistive Suite Installer
color 0B
echo =================================================================
echo             NAVTOOLS ASSISTIVE SUITE AUTO-INSTALLER
echo =================================================================
echo.
echo This script will check for Python, set up a virtual environment,
echo install all required dependencies, and fetch pre-trained assets.
echo.
echo =================================================================
echo.

:: 1. Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo [ERROR] Python was not found on your system!
    echo Please install Python 3.9, 3.10, or 3.11 from python.org and 
    echo ensure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b
)

echo [OK] Python is installed.
echo.

:: 2. Create virtual environment
if not exist ".venv" (
    echo [INFO] Creating Python virtual environment (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        color 0C
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b
    )
) else (
    echo [INFO] Virtual environment (.venv) already exists.
)
echo [OK] Virtual environment ready.
echo.

:: 3. Upgrade pip and install requirements
echo [INFO] Upgrading pip and installing required Python libraries...
call .\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    color 0C
    echo [ERROR] Failed to install dependencies from requirements.txt!
    pause
    exit /b
)
echo [OK] Dependencies installed successfully.
echo.

:: 4. Ensure data folder exists and download face landmarker task
echo [INFO] Ensuring data folder and models are ready...
if not exist "data" (
    mkdir data
)

if not exist "data\face_landmarker.task" (
    echo [INFO] Downloading MediaPipe Face Landmarker model (~80MB)...
    echo Please wait, this may take a moment depending on your network connection...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task' -OutFile 'data\face_landmarker.task'"
    if %errorlevel% neq 0 (
        echo [WARNING] Failed to download Face Landmarker task automatically.
        echo You can manually download it from:
        echo https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
        echo and place it inside the 'data/' directory.
    ) else (
        echo [OK] MediaPipe Face Landmarker model successfully downloaded!
    )
) else (
    echo [INFO] MediaPipe Face Landmarker model already exists in 'data/'.
)
echo.

color 0A
echo =================================================================
echo                  INSTALLATION COMPLETED SUCCESSFULLY!             
echo =================================================================
echo.
echo To launch the Tkinter control settings dashboard, run:
echo    python -m src.gui_app
echo.
echo To launch the CLI launcher directly, run:
echo    python -m src.multimodal_launcher
echo.
echo Enjoy hands-free assistive interaction with NavTools!
echo =================================================================
echo.
pause
