@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

REM ======================================================================
REM VAMP Complete Setup - Unified Agent Server Launcher
REM This script bootstraps the Python environment and starts the combined
REM REST API + WebSocket backend that the extension and dashboard use.
REM ======================================================================

REM Change to the repository root (one level up from scripts directory)
pushd %~dp0\..
set "REPO_ROOT=%CD%"

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

echo.
echo [Health] Checking connectivity to the Ollama / VAMP Cloud endpoint...
set "OLLAMA_ENV_FILE=%TEMP%\vamp_ollama_env.txt"
if exist "%OLLAMA_ENV_FILE%" del "%OLLAMA_ENV_FILE%" >NUL 2>&1
python scripts\check_ollama.py --env-file "%OLLAMA_ENV_FILE%"
set "OLLAMA_HEALTH_CODE=%ERRORLEVEL%"
if exist "%OLLAMA_ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%OLLAMA_ENV_FILE%") do (
        if /I "%%~A"=="OLLAMA_API_URL" set "OLLAMA_API_URL=%%~B"
        if /I "%%~A"=="OLLAMA_MODEL" set "OLLAMA_MODEL=%%~B"
    )
)
if "%OLLAMA_HEALTH_CODE%"=="0" (
    echo       Ollama endpoint is reachable at %OLLAMA_API_URL%.
) else if "%OLLAMA_HEALTH_CODE%"=="2" (
    echo WARNING: Ollama endpoint could not be reached. Continuing in offline mode.
    set "VAMP_AI_OFFLINE=1"
) else (
    goto :error
)

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

set "VENV_PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo ERROR: Unable to locate the virtual environment interpreter at "%VENV_PYTHON%".
    goto :error
)

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
echo [5/5] Launching VAMP unified backend (REST API + WS bridge)
echo ============================================================
echo   REST API: http://localhost:8080/api/*
echo   WebSocket: ws://localhost:8080
echo   VAMP Cloud Model: %VAMP_MODEL% @ %VAMP_CLOUD_API_URL%
echo ============================================================
echo.
echo   -> Opening a window for the REST API server...
start "VAMP REST API" cmd /k "cd /d %REPO_ROOT% && call .venv\Scripts\activate.bat && python -m backend.app_server"
if errorlevel 1 goto :error

echo   -> Waiting for the REST API to initialize before starting the bridge...
timeout /t 5 /nobreak >NUL

echo   -> Opening a window for the browser/extension bridge...
start "VAMP WS Bridge" cmd /k "cd /d %REPO_ROOT% && call .venv\Scripts\activate.bat && python -m backend.ws_bridge"
if errorlevel 1 goto :error

echo.
echo All backend processes are now running in their own Command Prompt windows.
echo Close those windows (or press CTRL+C inside them) to stop the services.
set "EXIT_CODE=0"
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
if defined OLLAMA_ENV_FILE if exist "%OLLAMA_ENV_FILE%" del "%OLLAMA_ENV_FILE%" >NUL 2>&1
popd
pause
exit /b %EXIT_CODE%
