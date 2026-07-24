# Build a self-contained portable desktop app (model + icon embedded).
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\build.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> Ensuring build dependencies..." -ForegroundColor Cyan
python -m pip install -r requirements.txt -r requirements-build.txt
python -m pip install pillow -q

if (-not (Test-Path "models\base\model.bin")) {
    Write-Host "==> Speech model missing - downloading base (needs internet once)..." -ForegroundColor Yellow
    python download_model.py base
}

if (-not (Test-Path "assets\app.ico")) {
    throw "Missing assets\app.ico - generate the icon first."
}

Write-Host "==> Cleaning previous build..." -ForegroundColor Cyan
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist\VideoToScript
Remove-Item -Force -ErrorAction SilentlyContinue dist\VideoToScript-Portable.zip

Write-Host "==> Running PyInstaller (embeds model + icon)..." -ForegroundColor Cyan
python -m PyInstaller --noconfirm VideoToScript.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$dist = Join-Path $PSScriptRoot "dist\VideoToScript"
$exe = Join-Path $dist "VideoToScript.exe"
if (-not (Test-Path $exe)) {
    throw "Build failed: $exe not found"
}

# Verify embedded model landed inside the package (_internal or datas root).
$embedded = @(
    (Join-Path $dist "_internal\models\base\model.bin"),
    (Join-Path $dist "models\base\model.bin")
) | Where-Object { Test-Path $_ }

if (-not $embedded) {
    throw "Model was not embedded into the package."
}

Write-Host "==> Creating portable zip..." -ForegroundColor Cyan
$zip = Join-Path $PSScriptRoot "dist\VideoToScript-Portable.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $dist -DestinationPath $zip -CompressionLevel Optimal

$sizeMb = [math]::Round(((Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB)
Write-Host ""
Write-Host "Done. Self-contained app (~$sizeMb MB):" -ForegroundColor Green
Write-Host "  $exe"
Write-Host "Portable zip (easy to copy):" -ForegroundColor Green
Write-Host "  $zip"
Write-Host ""
Write-Host "Copy the VideoToScript folder OR the zip - everything is inside."
