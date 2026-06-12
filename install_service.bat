@echo off
REM Install and start BiomatrixSync as a Windows Service
REM Must be run as Administrator

set SERVICE_EXE=%~dp0dist\BiomatrixSyncService.exe

if not exist "%SERVICE_EXE%" (
    echo ERROR: %SERVICE_EXE% not found.
    echo Please build the application first with build.bat
    pause
    exit /b 1
)

echo Installing BiomatrixSync service...
"%SERVICE_EXE%" install
if %errorlevel% neq 0 (
    echo ERROR: Service installation failed.
    pause
    exit /b 1
)

echo Configuring service to start automatically at boot...
sc config BiomatrixSync start= auto

echo Starting service...
"%SERVICE_EXE%" start

echo.
sc query BiomatrixSync
echo.
echo Done. Service is running in the background.
echo Logs: %PROGRAMDATA%\BiomatrixSync\service.log
pause
