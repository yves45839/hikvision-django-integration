# start-local.ps1 — lance le backend Django en local pour tests
# Usage : clic droit > Exécuter avec PowerShell, ou depuis un terminal :
#   powershell -ExecutionPolicy Bypass -File .\start-local.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "=== Activation de la venv ===" -ForegroundColor Cyan
. "$ProjectRoot\.venv\Scripts\Activate.ps1"

Write-Host "=== Variables d'environnement (.env) ===" -ForegroundColor Cyan
if (Test-Path "$ProjectRoot\.env") {
    Get-Content "$ProjectRoot\.env" | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}
# Defaults locaux (SQLite si pas de DATABASE_URL)
if (-not $env:DJANGO_DEBUG)        { $env:DJANGO_DEBUG = "1" }
if (-not $env:DJANGO_SECRET_KEY)   { $env:DJANGO_SECRET_KEY = "dev-only-fallback-key-change-me-in-prod" }
if (-not $env:ALLOWED_HOSTS)       { $env:ALLOWED_HOSTS = "127.0.0.1,localhost" }

Set-Location "$ProjectRoot\app"

Write-Host "=== Application des migrations ===" -ForegroundColor Cyan
python manage.py migrate --noinput

Write-Host "=== collectstatic (silencieux) ===" -ForegroundColor Cyan
python manage.py collectstatic --noinput 2>$null | Out-Null

Write-Host "=== Lancement du serveur sur http://127.0.0.1:8000/ ===" -ForegroundColor Green
Write-Host "Ctrl+C pour arrêter." -ForegroundColor Yellow
python manage.py runserver 127.0.0.1:8000
