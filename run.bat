@echo off
:: =====================================================
:: Assistant Project Launcher
:: Always uses the .venv Python — guaranteed correct deps
:: =====================================================
SET VENV_PYTHON=%~dp0.venv\Scripts\python.exe

IF NOT EXIST "%VENV_PYTHON%" (
    echo ERROR: .venv not found. Run:  python -m venv .venv
    echo Then:  .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting Assistant with .venv Python...
"%VENV_PYTHON%" -m src.gui_app
