@echo off
REM start-local.bat — lance le backend Django en local
REM Double-clique ce fichier ou exécute-le dans un cmd

cd /d "%~dp0"

echo === Activation de la venv ===
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo Echec de l'activation de la venv. Verifie que .venv existe.
    pause
    exit /b 1
)

REM Charger .env (lignes KEY=VALUE simples)
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
    )
)

if not defined DJANGO_DEBUG set DJANGO_DEBUG=1
if not defined DJANGO_SECRET_KEY set DJANGO_SECRET_KEY=dev-only-fallback-key-change-me-in-prod
if not defined ALLOWED_HOSTS set ALLOWED_HOSTS=127.0.0.1,localhost

cd app

echo === Application des migrations ===
python manage.py migrate --noinput
if errorlevel 1 (
    echo Echec des migrations.
    pause
    exit /b 1
)

echo === collectstatic (silencieux) ===
python manage.py collectstatic --noinput >nul 2>&1

echo.
echo === Serveur sur http://127.0.0.1:8000/  (Ctrl+C pour arreter) ===
python manage.py runserver 127.0.0.1:8000
pause
