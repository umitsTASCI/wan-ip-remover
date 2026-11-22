@echo off
setlocal
cd /d "%~dp0"

where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "wan_ip_degistirici.pyw"
    exit /b 0
)

where python.exe >nul 2>nul
if not errorlevel 1 (
    start "" python.exe "wan_ip_degistirici.pyw"
    exit /b 0
)

echo.
echo Python bulunamadi.
echo Python 3'u https://www.python.org/downloads/ adresinden kurun.
echo Kurulumda "Add Python to PATH" secenegini isaretleyin.
echo.
pause
exit /b 1
