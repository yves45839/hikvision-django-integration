@echo off
REM create-demo-tenant.bat
REM Cree le tenant HQ-CASA et les comptes de test dans la DB existante.
REM Lance ce fichier si setup-and-start.bat a deja demarre les serveurs
REM mais que la commande create_demo_tenant n'a pas tourne.

cd /d "%~dp0"

echo.
echo  === Activation du virtualenv ===
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERREUR: venv absent. Lance setup-and-start.bat d'abord.
    pause
    exit /b 1
)

echo  === Chargement des variables d'environnement ===
set DJANGO_DEBUG=1
set DJANGO_SECRET_KEY=dev-only-secret-key-local
set ALLOWED_HOSTS=127.0.0.1,localhost
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
    )
)

echo  === Creation du tenant HQ-CASA ===
cd app
python manage.py create_demo_tenant

echo.
echo  ============================================================
echo   Comptes crees :
echo   Admin    : admin@hq-casa.test  /  Admin@2024
echo   Operateur: operator@hq-casa.test  /  Oper@2024
echo   Tenant   : HQ-CASA
echo  ============================================================
echo.
pause
