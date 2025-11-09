@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Change to the repository root (one level up from this scripts directory)
pushd %~dp0\..

REM Allow overriding host/port before calling the script. Use defaults if not set.
if not defined APP_HOST set "APP_HOST=127.0.0.1"
if not defined APP_PORT set "APP_PORT=8765"

REM Launch the WebSocket bridge that powers the backend API.
python -m backend.ws_bridge
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%
