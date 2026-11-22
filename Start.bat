@echo off
setlocal
cd /d "%~dp0"

where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "wan_ip_remover.pyw"
    exit /b 0
)

where python.exe >nul 2>nul
if not errorlevel 1 (
    start "" python.exe "wan_ip_remover.pyw"
    exit /b 0
)

echo.
echo Python was not found.
echo Install Python 3 from https://www.python.org/downloads/
echo and tick "Add Python to PATH" during setup.
echo.
pause
exit /b 1
