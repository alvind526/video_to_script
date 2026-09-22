# One-time setup for developers / QA (creates .venv).
# Usage (from this folder):
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvDir = Join-Path $PSScriptRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

Write-Host "==> System Python" -ForegroundColor Cyan
python --version
if ($LASTEXITCODE -ne 0) {
    throw "Python not found. Install Python 3.10+ and ensure it is on PATH."
}

if (-not (Test-Path $venvPython)) {
    Write-Host "==> Creating .venv ..." -ForegroundColor Cyan
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv"
    }
} else {
    Write-Host "==> Reusing existing .venv" -ForegroundColor Cyan
}

Write-Host "==> Upgrading pip in .venv ..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed."
}

Write-Host "==> Installing requirements into .venv ..." -ForegroundColor Cyan
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "pip install failed."
}

Write-Host "==> Ensuring offline speech model (models/base)..." -ForegroundColor Cyan
& $venvPython download_model.py base
if ($LASTEXITCODE -ne 0) {
    throw "Model download failed (needs internet this once)."
}

Write-Host ""
Write-Host "Setup complete. Activate and run:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python app.py"
Write-Host ""
Write-Host "Or without activating:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe app.py"
Write-Host ""
Write-Host "Or:" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File .\run.ps1"
