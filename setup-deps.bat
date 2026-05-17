@echo off
REM setup-deps.bat — installe les dependances Python manquantes dans la venv
REM Double-clique ce fichier pour mettre a jour la venv selon requirements.txt

setlocal
cd /d "%~dp0"

echo === Activation de la venv ===
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo Echec de l'activation de la venv. Verifie que .venv existe.
    pause
    exit /b 1
)

echo.
echo === pip install -r requirements.txt ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Echec de l'installation des dependances.
    pause
    exit /b 1
)

echo.
echo === Verification des modules critiques ===
python -c "import axes; import rest_framework; import drf_spectacular; import corsheaders; import dj_database_url; print('OK: tous les modules requis sont importables')"

echo.
echo Termine. Vous pouvez maintenant relancer start-all.bat.
pause
endlocal
