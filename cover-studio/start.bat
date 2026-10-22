@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :fail
)
".venv\Scripts\python.exe" -c "import flask, PIL, fontTools.ttLib, brotli" >nul 2>nul
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :fail
)
".venv\Scripts\python.exe" app.py
goto :eof
:fail
echo.
echo Launch failed. Check Python installation and dependency availability.
pause
exit /b 1
