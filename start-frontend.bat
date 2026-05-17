@echo off
REM start-frontend.bat — lance le frontend Next.js seul

cd /d "%~dp0v0-secure-point-dashboard-design"

echo === Verification de pnpm/npm ===
where pnpm >nul 2>nul
if %errorlevel%==0 (
    echo pnpm trouve, installation...
    call pnpm install
    if errorlevel 1 (
        echo Echec pnpm install. Tentative avec npm...
        goto NPM
    )
    echo === Demarrage Next.js avec pnpm ===
    call pnpm dev
    goto END
)

:NPM
echo Utilisation de npm...
call npm install --legacy-peer-deps
if errorlevel 1 (
    echo Echec de l'installation des dependances.
    pause
    exit /b 1
)
echo === Demarrage Next.js avec npm ===
call npm run dev

:END
pause
