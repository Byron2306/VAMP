@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

REM ======================================================================
REM VAMP Complete Setup - Unified Agent Server Launcher
REM This script bootstraps the Python environment and starts the combined
REM REST API + WebSocket backend that the extension and dashboard use.
REM ======================================================================

REM Change to the repository root (one level up from scripts directory)
pushd %~dp0\..

echo.
echo ============================================================
echo   VAMP - Complete Setup with VAMP Cloud Integration
echo ============================================================
echo.

REM ----------------------------------------------------------------------
REM Configuration: update these values to match your accounts if needed.
REM You can also pre-set these variables before running the script to
REM override the defaults below.
REM ----------------------------------------------------------------------
if not defined VAMP_CLOUD_API_URL set "VAMP_CLOUD_API_URL=https://cloud.ollama.ai/v1/chat/completions"
if not defined VAMP_MODEL set "VAMP_MODEL=gpt-oss:120-b"
if not defined VAMP_API_KEY set "VAMP_API_KEY=d444f50476e4441f9c09264c1613b4b6.NRm41XBwlEv-1aM7OOwwfMsT"
if not defined VAMP_DEVICE_KEY set "VAMP_DEVICE_KEY=ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINiiSC7VfKvBo761Lf5Qfa8/4kYraTVyJWgELAAAmo+D"

REM Backwards compatibility: populate legacy Ollama variables for the Python backend
set "OLLAMA_API_URL=%VAMP_CLOUD_API_URL%"
set "OLLAMA_MODEL=%VAMP_MODEL%"
set "OLLAMA_API_KEY=%VAMP_API_KEY%"

REM Account Credentials (defaults can be overridden through environment)
if not defined VAMP_OUTLOOK_USERNAME set "VAMP_OUTLOOK_USERNAME=byron.bunt@nwu.ac.za"
if not defined VAMP_OUTLOOK_PASSWORD set "VAMP_OUTLOOK_PASSWORD=Byron230686!"
if not defined VAMP_ONEDRIVE_USERNAME set "VAMP_ONEDRIVE_USERNAME=byron.bunt@nwu.ac.za"
if not defined VAMP_ONEDRIVE_PASSWORD set "VAMP_ONEDRIVE_PASSWORD=Byron230686!"
if not defined VAMP_GOOGLE_USERNAME set "VAMP_GOOGLE_USERNAME=20172672@g.nwu.ac.za"
if not defined VAMP_GOOGLE_PASSWORD set "VAMP_GOOGLE_PASSWORD=Byron230686!"

echo [1/5] Verifying Python installation...
where python >NUL 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.10+ is required but not found on PATH.
    goto :error
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo       !PYTHON_VERSION! found.

echo.
echo [2/5] Setting up Python virtual environment...
if not exist .venv (
    python -m venv .venv
    if errorlevel 1 goto :error
)
call .venv\Scripts\activate.bat
if errorlevel 1 goto :error

echo.
echo [3/5] Installing dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :error
if exist requirements.txt (
    python -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

echo.
echo [4/5] Installing Playwright browsers (first time only)...
python -m playwright install
if errorlevel 1 goto :error

echo.
echo [5/5] Launching VAMP unified agent server
echo ============================================================
echo   REST API: http://localhost:8080/api/*
echo   WebSocket: ws://localhost:8080
echo   VAMP Cloud Model: %VAMP_MODEL% @ %VAMP_CLOUD_API_URL%
echo ============================================================
echo.
python -m backend.app_server
set "EXIT_CODE=%ERRORLEVEL%"
goto :cleanup

:error
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo ============================================================
echo ERROR: Setup failed with exit code %EXIT_CODE%
echo ============================================================
echo.
echo Troubleshooting suggestions:
echo   - Ensure Python 3.10+ is installed and on PATH
echo   - Run "python -m pip install --upgrade pip"
echo   - Delete the .venv folder and retry if permission errors occur
echo   - Review project README for manual setup instructions

echo.

:cleanup
if exist .venv\Scripts\deactivate.bat call .venv\Scripts\deactivate.bat >NUL 2>&1
popd
pause
exit /b %EXIT_CODE%
