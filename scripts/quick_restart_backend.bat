@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

REM ==================================================================================
REM VAMP Quick Restart Backend Services
REM ==================================================================================
REM This lightweight script restarts VAMP backend services without full re-setup
REM Use this if you just need to restart services (e.g., after a crash)
REM For full first-time setup, use: setup_backend.bat
REM ==================================================================================

echo.
echo ========================================================================
echo VAMP QUICK RESTART - Backend Services Only
echo ========================================================================
echo.
echo [INFO] This script restarts services without re-running setup.
echo [INFO] For first-time setup, use: setup_backend.bat
echo.

set "REPO_ROOT=%CD%.."
set "VENV_PATH=%REPO_ROOT%\.venv"

REM Check if venv exists
if not exist "%VENV_PATH%" (
    echo [ERROR] Virtual environment not found.
    echo [ERROR] Please run setup_backend.bat first for initial setup.
    echo.
    pause
    exit /b 1
)

echo [INFO] Activating virtual environment...
call "%VENV_PATH%\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo [OK] Virtual environment activated.
echo.

echo [INFO] Checking for existing services...
echo [INFO] If services are running in other windows, close them first.
echo [INFO] Then restart this script, or use CTRL+C to stop the services.
echo.
timeout /t 3 /nobreak

echo.
echo [INFO] Launching REST API server (port 8000)...
start "VAMP REST API" cmd /k "cd /d %REPO_ROOT% && call %VENV_PATH%\Scripts\activate.bat && python -m backend.app_server"
echo [OK] REST API server launched.

echo [INFO] Waiting 3 seconds...
timeout /t 3 /nobreak

echo [INFO] Launching WebSocket bridge (port 8000)...
start "VAMP WebSocket Bridge" cmd /k "cd /d %REPO_ROOT% && call %VENV_PATH%\Scripts\activate.bat && python -m backend.ws_bridge"
echo [OK] WebSocket bridge launched.

echo.
echo [INFO] Services are starting. Waiting 5 seconds for initialization...
timeout /t 5 /nobreak

echo.
echo [INFO] Running quick health check...
python -c "import requests; r = requests.get('http://localhost:8000/api/health', timeout=5); print('REST API Status: OK' if r.status_code == 200 else 'REST API Status: FAILED')" 2>nul

echo.
echo ========================================================================
echo VAMP Backend Services Restarted
echo ========================================================================
echo.
echo Services are now running in separate Command Prompt windows.
echo Keep these windows open while using VAMP.
echo.
echo Press any key to close this window...
pause
exit /b 0
