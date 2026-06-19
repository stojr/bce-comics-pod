@echo off
REM ============================================================
REM  BCE Legacy Slide Tool — one-click launcher
REM  Starts serve.py (in its own window) and opens the editor.
REM  Double-clicking viewer.html directly does NOT work (browsers
REM  block fetch() over file://) — always launch via this file.
REM ============================================================
cd /d "%~dp0"

REM Prefer 'python'; fall back to the 'py' launcher if needed.
set "PY=python"
where python >nul 2>nul || set "PY=py"

start "BCE Legacy server" %PY% serve.py

REM Give the server a moment to bind before opening the browser.
timeout /t 2 /nobreak >nul

start "" "http://localhost:8000/editor.html"
start "" "http://localhost:8000/viewer.html"

echo.
echo  BCE Legacy tool launched.
echo    Editor :  http://localhost:8000/editor.html
echo    Slide  :  http://localhost:8000/viewer.html
echo.
echo  Close the "BCE Legacy server" window (or press Ctrl+C in it) to stop.
