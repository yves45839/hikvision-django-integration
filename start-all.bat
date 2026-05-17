@echo off
REM start-all.bat — lance backend Django + frontend Next.js en deux fenetres
REM Double-clique ce fichier ou execute-le depuis un cmd.

setlocal
cd /d "%~dp0"

echo === Lancement du BACKEND Django ===
start "Backend Django (8000)" cmd /k "cd /d %~dp0 && call start-local.bat"

REM Petite pause pour laisser le backend demarrer avant le frontend
timeout /t 3 /nobreak >nul

echo === Lancement du FRONTEND Next.js ===
start "Frontend Next.js (3000)" cmd /k "cd /d %~dp0v0-secure-point-dashboard-design && (where pnpm >nul 2>nul && pnpm install --silent && pnpm dev) || (npm install --silent && npm run dev)"

echo.
echo ============================================================
echo   Backend  -> http://127.0.0.1:8000/
echo   Frontend -> http://localhost:3000/planning
echo ============================================================
echo.
echo Deux fenetres ont ete ouvertes. Cette fenetre peut etre fermee.
timeout /t 8 /nobreak
endlocal
