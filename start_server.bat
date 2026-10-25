@echo off
title Accommodation Search Server
echo ============================================
echo   Accommodation Search - Lokaler Server
echo ============================================
echo.

:: Wechsel ins webapp Verzeichnis
cd /d "%~dp0"

:: Prüfe ob Python installiert ist
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python ist nicht installiert!
    echo Bitte installiere Python von https://python.org
    pause
    exit /b 1
)

:: Installiere Dependencies falls nötig
echo Pruefe Dependencies...
pip install fastapi uvicorn[standard] pydantic selenium pandas requests python-multipart aiofiles --quiet 2>nul

echo.
echo Server startet auf: http://localhost:8000
echo.
echo Oeffne deinen Browser und gehe zu:
echo   http://localhost:8000
echo.
echo Druecke Ctrl+C um den Server zu stoppen.
echo ============================================
echo.

:: Öffne Browser automatisch nach 2 Sekunden
start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

:: Starte den Server
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

pause
