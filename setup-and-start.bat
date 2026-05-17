@echo off
REM ============================================================
REM  setup-and-start.bat
REM  1. Crée le venv Python si absent
REM  2. Installe les dépendances
REM  3. Lance les migrations Django
REM  4. Crée le tenant HQ-CASA + comptes de test
REM  5. Ouvre le backend (port 8000) dans une nouvelle fenêtre
REM  6. Ouvre le frontend Next.js (port 3000) dans une nouvelle fenêtre
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo   LR Time - Setup et demarrage local
echo  ============================================================
echo.

REM ── 1. Venv ──────────────────────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo [1/5] Creation du virtualenv Python...
    python -m venv .venv
    if errorlevel 1 (
        echo ERREUR: python -m venv a echoue. Verifie que Python 3.11+ est installe.
        pause
        exit /b 1
    )
    echo       OK.
) else (
    echo [1/5] Virtualenv existant, skip creation.
)

REM ── 2. Dépendances ───────────────────────────────────────────
echo [2/5] Installation des dependances Python...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo ERREUR: pip install a echoue.
    pause
    exit /b 1
)
echo       OK.

REM ── 3. Migrations ────────────────────────────────────────────
echo [3/5] Application des migrations Django...
cd app
set DJANGO_DEBUG=1
set DJANGO_SECRET_KEY=dev-only-secret-key-local
set ALLOWED_HOSTS=127.0.0.1,localhost

REM Charger .env si present
if exist "..\\.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("..\\.env") do (
        if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
    )
)

python manage.py migrate --noinput
if errorlevel 1 (
    echo ERREUR: migrations echouees.
    pause
    exit /b 1
)
echo       OK.

REM ── 4. Tenant demo ───────────────────────────────────────────
echo [4/5] Creation du tenant HQ-CASA et des comptes de test...
python manage.py create_demo_tenant
if errorlevel 1 (
    echo AVERTISSEMENT: create_demo_tenant a retourne une erreur non fatale.
)
echo       OK.

REM ── 5. Backend dans une nouvelle fenetre ─────────────────────
echo [5/5] Lancement des serveurs...
cd ..

start "Backend Django :8000" cmd /k "cd /d %~dp0 && call .venv\Scripts\activate.bat && cd app && set DJANGO_DEBUG=1 && set DJANGO_SECRET_KEY=dev-only-secret-key-local && set ALLOWED_HOSTS=127.0.0.1,localhost && python manage.py runserver 127.0.0.1:8000"

timeout /t 3 /nobreak >nul

REM ── 6. Frontend dans une nouvelle fenetre ────────────────────
start "Frontend Next.js :3000" cmd /k "cd /d %~dp0v0-secure-point-dashboard-design && (where pnpm >nul 2>nul && pnpm install --silent && pnpm dev) || (npm install --legacy-peer-deps --silent && npm run dev)"

echo.
echo  ============================================================
echo.
echo   BACKEND  ^>  http://127.0.0.1:8000/
echo   FRONTEND ^>  http://localhost:3000/
echo.
echo   Compte admin    : admin@hq-casa.test  /  Admin@2024
echo   Compte operateur: operator@hq-casa.test  /  Oper@2024
echo   Tenant code     : HQ-CASA
echo.
echo   Django admin    : http://127.0.0.1:8000/admin/
echo.
echo  ============================================================
echo.
echo  Cette fenetre peut etre fermee. Les deux serveurs tournent
echo  dans leurs propres fenetres.
echo.
timeout /t 15 /nobreak
endlocal
