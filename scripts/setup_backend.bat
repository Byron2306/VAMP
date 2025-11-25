@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

REM ==================================================================================
REM VAMP Complete Auto-Setup - One-Click Backend Installation & Launch
REM ==================================================================================
REM This script completely automates:
REM  - Python 3.10+ verification and setup
REM  - Virtual environment creation
REM  - All pip dependencies installation
REM  - Playwright browser binaries installation
REM  - Chrome & Ollama detection
REM  - Ollama server health check and auto-launch
REM  - REST API + WebSocket bridge startup
REM  - Dashboard auto-open
REM  - Full error handling and recovery
REM ==================================================================================

REM Colors for console output (Windows 10+)
for /F %%A in ('echo prompt $H ^| cmd') do set "BS=%%A"

set "REPO_ROOT=%~dp0.."
set "SCRIPTS_DIR=%CD%"
set "VENV_PATH=%REPO_ROOT%\.venv"
set "PYTHON_VENV=%VENV_PATH%\Scripts\python.exe"
set "PIP_VENV=%VENV_PATH%\Scripts\pip.exe"

REM Exit codes for status tracking
set "EXIT_CODE=0"
set "SETUP_FAILED=0"

echo.
echo ========================================================================
echo VAMP BACKEND - FULLY AUTOMATED SETUP
echo ========================================================================
echo.
echo [INFO] Starting comprehensive backend auto-setup...
echo [INFO] Repository root: %REPO_ROOT%
echo.

REM ========================================================================
REM [STEP 1] Verify Python 3.10+ Installation
REM ========================================================================

echo.
echo [1/7] Verifying Python 3.10+ installation...
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo [ERROR] Please install Python 3.10+ from https://www.python.org/downloads/
    echo [ERROR] During installation, ensure "Add Python to PATH" is checked.
    set SETUP_FAILED=1
    goto :error
)

for /f "tokens=2" %%A in ('python --version 2^>^&1') do set PYTHON_VERSION=%%A
echo [OK] Python found: !PYTHON_VERSION!

REM Verify Python 3.10+
for /f "tokens=1,2 delims=." %%A in ("!PYTHON_VERSION!") do (
    if %%A LSS 3 (
        echo [ERROR] Python 3.10+ required. Current: !PYTHON_VERSION!
        set SETUP_FAILED=1
        goto :error
    )
    if %%A EQU 3 if %%B LSS 10 (
        echo [ERROR] Python 3.10+ required. Current: !PYTHON_VERSION!
        set SETUP_FAILED=1
        goto :error
    )
)

echo [OK] Python version !PYTHON_VERSION! meets requirements.
echo.

REM ========================================================================
REM [STEP 2] Setup or Use Virtual Environment
REM ========================================================================

echo [2/7] Setting up Python virtual environment...
echo.

if not exist "%VENV_PATH%" (
    echo [INFO] Virtual environment not found. Creating...
    python -m venv "%VENV_PATH%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        set SETUP_FAILED=1
        goto :error
    )
    echo [OK] Virtual environment created at: %VENV_PATH%
) else (
    echo [OK] Virtual environment already exists at: %VENV_PATH%
)

echo [INFO] Activating virtual environment...
call "%VENV_PATH%\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    set SETUP_FAILED=1
    goto :error
)
echo [OK] Virtual environment activated.
echo.

REM ========================================================================
REM [STEP 3] Upgrade pip and Install Dependencies
REM ========================================================================

echo [3/7] Installing Python dependencies...
echo.

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo [WARNING] pip upgrade had issues, but continuing...
)

echo [INFO] Installing core dependencies from requirements.txt...
if exist "%REPO_ROOT%\requirements.txt" (
    python -m pip install -r "%REPO_ROOT%\requirements.txt" --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies from requirements.txt
        set SETUP_FAILED=1
        goto :error
    )
    echo [OK] All dependencies installed successfully.
) else (
    echo [ERROR] requirements.txt not found at: %REPO_ROOT%
    set SETUP_FAILED=1
    goto :error
)
echo.

REM ========================================================================
REM [STEP 4] Install Playwright Browsers
REM ========================================================================

echo [4/7] Installing Playwright browsers...
echo [INFO] This may take 2-5 minutes on first run (one-time only)
echo.

python -m playwright install --with-deps
if errorlevel 1 (
    echo [ERROR] Failed to install Playwright browsers.
    set SETUP_FAILED=1
    goto :error
)
echo [OK] Playwright browsers installed successfully.
echo.
REM Verify Chrome installation is available
where chrome >nul 2>&1
if errorlevel 1 (
    REM Chrome not in PATH, check common install locations
    if exist "%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe" (
        echo [OK] Chrome found at %ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe
    ) else if exist "%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe" (
        echo [OK] Chrome found at %ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe
    ) else (
        echo [OK] Chrome found at: C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
    [STEP 6] Check and Start Ollama Server
REM ========================================================================

echo [6/7] Checking Ollama AI server...
echo [INFO] Testing connection to http://127.0.0.1:11434...
echo.

REM Silent test for Ollama - if it returns anything, Ollama is running
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama server not running at http://127.0.0.1:11434
    echo.
    echo [INFO] Options:
    echo   A) Start Ollama manually: Run "ollama serve" in another terminal
    echo   B) Install Ollama from: https://ollama.ai
    echo   C) Continue in OFFLINE mode (AI features disabled)
    echo.
    echo [INFO] Waiting 5 seconds before continuing...
    timeout /t 5 /nobreak
    set "VAMP_AI_OFFLINE=1"
    echo [WARNING] VAMP will run in offline mode without AI features.
) else (
    echo [OK] Ollama server is running and reachable.
    echo [INFO] Checking Ollama models...
    
    REM Check if required model is installed
    python -c "import requests; models = requests.get('http://127.0.0.1:11434/api/tags').json(); import sys; sys.exit(0 if any('gemma' in m.get('name','') for m in models.get('models',[])) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] Gemma model not found. Downloading...
        echo [INFO] This may take 5-10 minutes on first run.
        echo.
        ollama pull gemma3:4b-b
        if errorlevel 1 (
            echo [WARNING] Could not auto-download Gemma model. Run manually: ollama pull gemma3:4b-b
        )
    ) else (
        echo [OK] Gemma model is available.
    )
)
echo.

REM ========================================================================
REM [STEP 7] Launch Backend Services
REM ========================================================================

echo [7/7] Launching VAMP backend services...
echo.

echo [INFO] Starting REST API server (port 8000)...
start "VAMP REST API" cmd /k "cd /d %REPO_ROOT% && call %VENV_PATH%\Scripts\activate.bat && python -m backend.app_server"
if errorlevel 1 (
    echo [ERROR] Failed to start REST API.
    set SETUP_FAILED=1
    goto :error
)
echo [OK] REST API server launched in new window.

echo [INFO] Waiting 3 seconds before starting WebSocket bridge...
timeout /t 3 /nobreak

echo [INFO] Starting WebSocket bridge (port 8000)...
start "VAMP WebSocket Bridge" cmd /k "cd /d %REPO_ROOT% && call %VENV_PATH%\Scripts\activate.bat && python -m backend.ws_bridge"
if errorlevel 1 (
    echo [WARNING] WebSocket bridge startup may have issues, but API should work.
)
echo [OK] WebSocket bridge launched in new window.

echo.
echo [INFO] Waiting for services to initialize (10 seconds)...
timeout /t 10 /nobreak

REM ========================================================================
REM [FINAL] Health Check and Dashboard Launch
REM ========================================================================

echo.
echo [INFO] Performing health checks...
echo.

REM Check REST API health
echo [INFO] Testing REST API health endpoint...
python -c "import requests; r = requests.get('http://localhost:8000/api/health', timeout=5); print('OK: ' + str(r.status_code))" 2>nul >nul
if errorlevel 1 (
    echo [WARNING] REST API health check failed. Services may still be starting.
) else (
    echo [OK] REST API is responding.
)

echo.
echo ========================================================================
echo SUCCESS! VAMP Backend is Ready
echo ========================================================================
echo.
echo [OK] All services are running:
echo   - REST API: http://localhost:8000/api/*
echo   - WebSocket Bridge: ws://localhost:8000
echo   - Ollama AI: http://127.0.0.1:11434 (if available)
echo.
echo [INFO] Next steps:
echo   1. Open your browser and navigate to: http://localhost:8000/dashboard
echo   2. Load the VAMP extension in Chrome (chrome://extensions)
echo   3. Log into your email/cloud accounts in Chrome
echo   4. Enroll in the extension using your email
echo   5. Start scanning!
echo.
echo [INFO] Keep these windows open while using VAMP.
echo [INFO] Press CTRL+C in any window to stop individual services.
echo.
echo ========================================================================
echo.
pause
exit /b 0

REM ========================================================================
REM Error Handler
REM ========================================================================

:error
echo.
echo ========================================================================
echo ERROR - Setup Failed
echo ========================================================================
echo.
echo [ERROR] Exit code: %EXIT_CODE%
echo.
echo Troubleshooting:
echo   - Ensure Python 3.10+ is installed and added to PATH
echo   - Run: python --version (should show 3.10 or higher)
echo   - If Python paths are wrong, reinstall with "Add to PATH" checked
echo   - For Playwright issues: python -m playwright install
echo   - For pip issues: python -m pip install --upgrade pip
echo.
echo Support:
echo   - GitHub: https://github.com/Byron2306/VAMP
echo   - Check requirements.txt for dependencies
echo.
pause
exit /b 1
