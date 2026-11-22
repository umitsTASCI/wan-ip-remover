@echo off
setlocal
cd /d "%~dp0"

where python.exe >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python bulunamadi.
    echo Python 3'u https://www.python.org/downloads/ adresinden kurun.
    echo.
    pause
    exit /b 1
)

python.exe "wan_ip_degistirici.pyw"
echo.
echo Program kapandi. Yukarida hata mesaji varsa bu pencereyi kapatmayin.
pause
