@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Change to repository root
pushd %~dp0\..

REM Configure DeepSeek/Ollama gateway defaults for local Ollama proxy
set "DEEPSEEK_API_URL=http://127.0.0.1:11434/v1/chat/completions"
set "DEEPSEEK_MODEL=gpt-oss:120b-cloud"
set "DEEPSEEK_API_KEY=local"

REM Launch backend WebSocket bridge
python -m backend.ws_bridge
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%
