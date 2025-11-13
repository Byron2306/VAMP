@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

REM Change to the repository root (one level up from scripts directory)
pushd %~dp0\..

REM ---------------------------------------------------------------------------
REM Configuration: update these values to match your accounts if needed.
REM You can also pre-set these variables before running the script to override
REM the defaults below.
REM ---------------------------------------------------------------------------
if not defined VAMP_OUTLOOK_USERNAME set "VAMP_OUTLOOK_USERNAME=byron.bunt@nwu.ac.za"
if not defined VAMP_OUTLOOK_PASSWORD set "VAMP_OUTLOOK_PASSWORD=Byron230686!"
if not defined VAMP_ONEDRIVE_USERNAME set "VAMP_ONEDRIVE_USERNAME=byron.bunt@nwu.ac.za"
if not defined VAMP_ONEDRIVE_PASSWORD set "VAMP_ONEDRIVE_PASSWORD=Byron230686!"
if not defined VAMP_GOOGLE_USERNAME set "VAMP_GOOGLE_USERNAME=20172672@g.nwu.ac.za"
if not defined VAMP_GOOGLE_PASSWORD set "VAMP_GOOGLE_PASSWORD=Byron230686!"

REM Ollama cloud configuration for gpt-oss:120-b model
if not defined OLLAMA_API_URL set "OLLAMA_API_URL=https://cloud.ollama.ai/v1/chat/completions"
if not defined OLLAMA_MODEL set "OLLAMA_MODEL=gpt-oss:120-b"
if not defined OLLAMA_API_KEY set "OLLAMA_API_KEY=local"

REM ---------------------------------------------------------------------------
REM Verify Python availability
REM ---------------------------------------------------------------------------
where python >NUL 2>&1
if errorlevel 1 (
    echo Python is required but was not found on PATH.
    goto :error
)

REM ---------------------------------------------------------------------------
REM Create or reuse the local virtual environment
REM ---------------------------------------------------------------------------
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :error
)

call .venv\Scripts\activate.bat
if errorlevel 1 goto :error

echo Upgrading pip and installing backend requirements...
python -m pip install --upgrade pip
if errorlevel 1 goto :error

if exist requirements.txt (
    python -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

REM Install Playwright browsers used by the application
python -m playwright install
if errorlevel 1 goto :error

REM ---------------------------------------------------------------------------
REM Launch the backend WebSocket bridge
REM ---------------------------------------------------------------------------
python -m backend.ws_bridge
set "EXIT_CODE=%ERRORLEVEL%"

goto :cleanup

:error
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo The setup or launch process failed with exit code %EXIT_CODE%.

:cleanup
REM Attempt to deactivate the virtual environment if it is active
if exist .venv\Scripts\deactivate.bat call .venv\Scripts\deactivate.bat >NUL 2>&1

popd
exit /b %EXIT_CODE%
