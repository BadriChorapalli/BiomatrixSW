@echo off
REM Stop and remove the BiomatrixSync Windows Service
REM Must be run as Administrator

set SERVICE_EXE=%~dp0dist\BiomatrixSyncService.exe

echo Stopping service...
sc stop BiomatrixSync 2>nul
timeout /t 3 /nobreak >nul

echo Removing service...
if exist "%SERVICE_EXE%" (
    "%SERVICE_EXE%" remove
) else (
    sc delete BiomatrixSync
)

echo.
echo Service removed.
pause
