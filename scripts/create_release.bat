@echo off
title NavTools — Create Release Package
color 0B
echo =================================================================
echo           NAVTOOLS — RELEASE PACKAGE CREATOR
echo =================================================================
echo.

SET ROOT=%~dp0..
SET DIST=%ROOT%\dist\NavTools
SET RELEASE_DIR=%ROOT%\release
SET VERSION=v1.0.0
SET ZIP_NAME=NavTools-%VERSION%-Windows.zip
SET VENV_PYTHON=%ROOT%\.venv\Scripts\python.exe

:: 1. Check the build exists
IF NOT EXIST "%DIST%\NavTools.exe" (
    color 0C
    echo [ERROR] Build not found at: %DIST%\NavTools.exe
    echo Please run build_exe.bat first.
    pause
    exit /b 1
)
echo [OK] Build found.

:: 2. Clean and recreate release folder
IF EXIST "%RELEASE_DIR%" RMDIR /S /Q "%RELEASE_DIR%"
MKDIR "%RELEASE_DIR%"
echo [OK] Release directory created.

:: 3. Copy the dist folder into release
echo [INFO] Copying application files...
XCOPY /E /I /Q "%DIST%" "%RELEASE_DIR%\NavTools"
echo [OK] App files copied.

:: 4. Copy documentation
echo [INFO] Copying documentation files...
COPY /Y "%ROOT%\README.md"  "%RELEASE_DIR%\README.md"  >nul
COPY /Y "%ROOT%\README.pdf" "%RELEASE_DIR%\README.pdf" >nul
COPY /Y "%ROOT%\LICENSE"    "%RELEASE_DIR%\LICENSE"    >nul
echo [OK] Documentation copied.

:: 5. Create a simple launcher README inside the package
(
echo NavTools — Assistive Gaze Tracking ^& Voice Assistant
echo ======================================================
echo.
echo VERSION: %VERSION%
echo.
echo HOW TO RUN:
echo   Double-click NavTools\NavTools.exe
echo.
echo FIRST TIME SETUP:
echo   - Allow webcam access when prompted
echo   - Allow microphone access when prompted
echo   - The floating Orb will appear in the top-right corner
echo.
echo CONTROLS:
echo   - Double-click the Orb  = Open Settings Dashboard
echo   - Right-click the Orb   = Exit the application
echo   - Say "hey Jack"        = Wake the voice assistant
echo.
echo REQUIREMENTS:
echo   - Windows 10 or 11 (64-bit)
echo   - Webcam + Microphone
echo   - Internet connection for first-run speech recognition
echo.
echo For full documentation see README.pdf
) > "%RELEASE_DIR%\HOW_TO_RUN.txt"
echo [OK] HOW_TO_RUN.txt created.

:: 6. Zip it using PowerShell
echo [INFO] Creating zip archive: %ZIP_NAME%
IF EXIST "%ROOT%\%ZIP_NAME%" DEL /F /Q "%ROOT%\%ZIP_NAME%"

powershell -Command "Compress-Archive -Path '%RELEASE_DIR%\*' -DestinationPath '%ROOT%\%ZIP_NAME%' -Force"

IF %errorlevel% neq 0 (
    color 0C
    echo [ERROR] Failed to create zip archive.
    pause
    exit /b 1
)

:: 7. Report
color 0A
echo.
echo =================================================================
echo              RELEASE PACKAGE CREATED SUCCESSFULLY!
echo =================================================================
echo.
echo   Folder:  %RELEASE_DIR%\
echo   Zip:     %ROOT%\%ZIP_NAME%
echo.

:: Show size
"%VENV_PYTHON%" -c "import os; size=os.path.getsize(r'%ROOT%\%ZIP_NAME%'); print(f'   Zip size: {size/1024/1024:.1f} MB')"

echo.
echo   To create a GitHub release:
echo     gh release create %VERSION% %ZIP_NAME% --title "NavTools %VERSION%"
echo.
pause
