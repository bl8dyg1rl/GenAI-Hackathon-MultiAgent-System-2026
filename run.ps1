$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Primero ejecuta .\setup.ps1" -ForegroundColor Yellow
    exit 1
}
& ".\.venv\Scripts\python.exe" -m uvicorn python_app.main:app --host 127.0.0.1 --port 8000
