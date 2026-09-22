# Run the app using the project .venv.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\run.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "No .venv found. Run setup first:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\setup.ps1"
    exit 1
}

& $venvPython app.py
