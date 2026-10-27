$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "No encuentro el lanzador 'py'. Instala Python 3.11+ y marca la opción para añadirlo al PATH."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3 -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    # Generate a per-install secret for short-lived Scout execution contracts.
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    $secret = [System.BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
    $contents = Get-Content ".env" -Raw
    $contents = $contents.Replace("replace-with-a-long-random-secret-before-sharing-or-deploying", $secret)
    Set-Content -Path ".env" -Value $contents -Encoding utf8
    Write-Host "Se creó .env con un secreto local único. Los tokens también pueden configurarse desde Ajustes en el chat." -ForegroundColor Yellow
}

Write-Host "Instalación terminada. Ejecuta .\run.ps1" -ForegroundColor Green
