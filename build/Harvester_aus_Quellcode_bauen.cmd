@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Harvester Deutsch - Aus oeffentlichen Quellen bauen
echo HARVESTER GOG DEUTSCH - QUELLCODE-BUILD
echo.
echo Es werden nur die oeffentlichen Quellcodes, Delta- und Untertitel-
echo ressourcen verwendet. Original-GOG und Spielstaende bleiben unberuehrt.
echo Python 3.13 wird NUR zum Erstellen der EXE benoetigt.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Harvester_aus_Quellcode_bauen.ps1"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo FEHLER: Build nicht abgeschlossen; siehe Meldung oben.
echo.
pause
exit /b %RESULT%
