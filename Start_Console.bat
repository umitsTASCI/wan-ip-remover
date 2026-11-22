@echo off
setlocal
cd /d "%~dp0"

where python.exe >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python was not found.
    echo Install Python 3 from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

python.exe "wan_ip_remover.pyw"
echo.
echo The program has closed. If an error is shown above, keep this window open.
pause
