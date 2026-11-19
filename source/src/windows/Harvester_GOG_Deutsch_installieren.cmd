@echo off
setlocal
cd /d "%~dp0" || exit /b 1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0Harvester_GOG_Deutsch_installieren.ps1"
set "code=%ERRORLEVEL%"
echo.
if not "%code%"=="0" echo INSTALLATION NICHT ERFOLGREICH. Bitte das INSTALLATIONS_LOG im entpackten Paket pruefen.
if "%code%"=="0" echo Installation beendet. Den Ordner "Harvester GOG Deutsch" oeffnen und einen der 3 Starter ausfuehren.
pause
exit /b %code%
