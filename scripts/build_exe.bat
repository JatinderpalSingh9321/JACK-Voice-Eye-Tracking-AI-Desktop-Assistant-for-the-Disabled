@echo off
title NavTools — Build Windows EXE
color 0B
echo =================================================================
echo           NAVTOOLS — WINDOWS EXECUTABLE BUILDER
echo =================================================================
echo.

SET VENV_PYTHON=%~dp0..\.venv\Scripts\python.exe
SET VENV_PYINSTALLER=%~dp0..\.venv\Scripts\pyinstaller.exe

:: 1. Check .venv exists
IF NOT EXIST "%VENV_PYTHON%" (
    color 0C
    echo [ERROR] .venv not found. Run install.bat first.
    pause
    exit /b 1
)
echo [OK] Virtual environment found.

:: 2. Check PyInstaller is installed
IF NOT EXIST "%VENV_PYINSTALLER%" (
    echo [INFO] Installing PyInstaller into .venv...
    "%VENV_PYTHON%" -m pip install pyinstaller pyinstaller-hooks-contrib
    IF %errorlevel% neq 0 (
        color 0C
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)
echo [OK] PyInstaller ready.

:: 3. Convert orb logo to .ico if not present
IF NOT EXIST "%~dp0..\navtools.ico" (
    echo [INFO] Converting orb_logo.png to navtools.ico...
    "%VENV_PYTHON%" -c "from PIL import Image; img=Image.open('src/orb_logo.png').convert('RGBA'); sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)]; imgs=[img.resize(s) for s in sizes]; imgs[0].save('navtools.ico', format='ICO', sizes=sizes, append_images=imgs[1:])"
    echo [OK] Icon created.
) ELSE (
    echo [INFO] navtools.ico already exists.
)

:: 4. Clean previous build output
echo [INFO] Cleaning previous build artifacts...
IF EXIST "%~dp0..\build\NavTools" RMDIR /S /Q "%~dp0..\build\NavTools"
IF EXIST "%~dp0..\dist\NavTools"  RMDIR /S /Q "%~dp0..\dist\NavTools"
echo [OK] Clean done.

:: 5. Run PyInstaller
echo.
echo [INFO] Starting PyInstaller build — this may take 5-15 minutes...
echo [INFO] Please wait, do NOT close this window.
echo.
"%VENV_PYINSTALLER%" NavTools.spec --clean --noconfirm

IF %errorlevel% neq 0 (
    color 0C
    echo.
    echo [ERROR] PyInstaller build FAILED. Check output above for errors.
    pause
    exit /b 1
)

color 0A
echo.
echo =================================================================
echo              BUILD SUCCESSFUL!
echo =================================================================
echo.
echo Output location: %~dp0..\dist\NavTools\NavTools.exe
echo.
echo To test the build, run:
echo    %~dp0..\dist\NavTools\NavTools.exe
echo.
echo To create the release zip, run:
echo    scripts\create_release.bat
echo.
pause
