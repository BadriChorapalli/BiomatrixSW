@echo off
REM Build BiomatrixSync_Setup.exe using Inno Setup
REM Run this from the BiomatrixSyncPackage folder whenever you rebuild the EXEs

set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"

if not exist %ISCC% (
    echo ERROR: Inno Setup not found. Download from https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

echo Building installer...
%ISCC% setup.iss
if %errorlevel% neq 0 (
    echo ERROR: Installer build failed.
    pause
    exit /b 1
)

echo.
echo Done! Output\BiomatrixSync_Setup.exe is ready.
pause
