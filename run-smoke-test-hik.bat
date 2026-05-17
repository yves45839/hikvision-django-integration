@echo off
REM Lance le smoke test live de la Hik Gateway et écrit le résultat dans smoke-test-hik.log
cd /d "%~dp0"

REM Activer le venv s'il existe
if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

cd app
python scripts/smoke_test_hik_live.py > ..\smoke-test-hik.log 2>&1
echo Smoke test terminé. Résultat dans smoke-test-hik.log
type ..\smoke-test-hik.log
pause
