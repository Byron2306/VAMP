@echo off
setlocal ENABLEDELAYEDEXPANSION

REM VAMP backend bootstrap (Windows)
REM - Creates/activates .venv
REM - Installs requirements and Playwright browsers
REM - Starts the canonical backend (backend.app_server)
REM - Optionally starts the legacy ws_bridge when START_WS_BRIDGE=1

set "REPO_ROOT=%~dp0.."
set "VENV_DIR=%REPO_ROOT%\.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_DIR%" (
    echo [INFO] Creating virtual environment at %VENV_DIR%...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 goto :error
) else (
    echo [INFO] Using existing virtual environment at %VENV_DIR%.
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 goto :error

echo [INFO] Upgrading pip and installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r "%REPO_ROOT%\requirements.txt"
if errorlevel 1 goto :error

echo [INFO] Installing Playwright browsers (one-time download)...
python -m playwright install
if errorlevel 1 (
    echo [WARN] Playwright install reported an issue. You may need to rerun it manually.
)

REM Centralised network defaults
set "VAMP_ENABLED=%VAMP_AGENT_ENABLED%"
if not defined VAMP_ENABLED set "VAMP_ENABLED=1"
set "HOST=%VAMP_AGENT_HOST%"
if not defined HOST set "HOST=127.0.0.1"
set "PORT=%VAMP_AGENT_PORT%"
if not defined PORT set "PORT=8080"
set "LEGACY_WS=%START_WS_BRIDGE%"
if not defined LEGACY_WS set "LEGACY_WS=0"

set "APP_HOST=%APP_HOST%"
if not defined APP_HOST set "APP_HOST=%HOST%"
set "APP_PORT=%APP_PORT%"
if not defined APP_PORT set "APP_PORT=8765"

echo [INFO] Ollama optional: AI insights disabled if not running.

echo [INFO] Starting unified backend on %HOST%:%PORT% ...
start "VAMP Backend" cmd /k "cd /d %REPO_ROOT% && call %VENV_DIR%\Scripts\activate.bat && set VAMP_AGENT_HOST=%HOST% && set VAMP_AGENT_PORT=%PORT% && python -m backend.app_server"
if errorlevel 1 goto :error

if /I "%LEGACY_WS%"=="1" (
    echo [INFO] Starting legacy WebSocket bridge on %APP_HOST%:%APP_PORT% ...
    start "VAMP WebSocket Bridge" cmd /k "cd /d %REPO_ROOT% && call %VENV_DIR%\Scripts\activate.bat && set APP_HOST=%APP_HOST% && set APP_PORT=%APP_PORT% && python -m backend.ws_bridge") else (
    echo [INFO] Legacy ws_bridge not started (set START_WS_BRIDGE=1 to enable).
)

echo [INFO] Waiting for backend to become ready...
timeout /t 5 /nobreak >nul

"%PYTHON_EXE%" -c "import os,sys,requests; host=os.getenv('VAMP_AGENT_HOST','%HOST%'); port=os.getenv('VAMP_AGENT_PORT','%PORT%'); url=f'http://{host}:{port}/api/health';\
print('Health check:', url);\
try: r=requests.get(url, timeout=5); print('Status', r.status_code);\
except Exception as exc: print('Health check warning:', exc); sys.exit(0)"

echo.
echo Backend launch triggered. Keep the opened windows running while you use VAMP.
exit /b 0

:error
echo [ERROR] Setup failed. Check the messages above for details.
exit /b 1
