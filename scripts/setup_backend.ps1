Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Move to repository root
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))

$venvPath = Join-Path (Get-Location) 'venv'
$venvActivate = Join-Path $venvPath 'Scripts\Activate.ps1'

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating Python virtual environment in $venvPath" -ForegroundColor Cyan
    python -m venv $venvPath
}
else {
    Write-Host "Using existing virtual environment in $venvPath" -ForegroundColor Yellow
}

Write-Host "Activating virtual environment" -ForegroundColor Cyan
. $venvActivate

Write-Host "Upgrading pip and installing backend dependencies" -ForegroundColor Cyan
pip install --upgrade pip
pip install -r requirements.txt

Write-Host "Installing Playwright browsers" -ForegroundColor Cyan
playwright install

if (-not $env:DEEPSEEK_API_URL) {
    $env:DEEPSEEK_API_URL = "http://127.0.0.1:11434/v1/chat/completions"
    Write-Host "Set DEEPSEEK_API_URL to default local Ollama endpoint" -ForegroundColor Green
}
else {
    Write-Host "DEEPSEEK_API_URL already configured: $($env:DEEPSEEK_API_URL)" -ForegroundColor Yellow
}

if (-not $env:DEEPSEEK_MODEL) {
    $env:DEEPSEEK_MODEL = "gpt-oss:120b-cloud"
    Write-Host "Set DEEPSEEK_MODEL to default model" -ForegroundColor Green
}
else {
    Write-Host "DEEPSEEK_MODEL already configured: $($env:DEEPSEEK_MODEL)" -ForegroundColor Yellow
}

Write-Host "Starting backend WebSocket bridge" -ForegroundColor Cyan
python -m backend.ws_bridge
