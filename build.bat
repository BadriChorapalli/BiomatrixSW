@echo off
REM Build BiomatrixSync for Windows (.exe + service exe)
REM Builds to a temp path first to avoid Windows Defender locking the output.

set DIST_TMP=C:\Temp\biomatrix_dist

echo Installing dependencies...
py -m pip install -r requirements.txt

echo Building Windows executables...
py -m PyInstaller build.spec --noconfirm --distpath "%DIST_TMP%"

echo.
if exist "%DIST_TMP%\BiomatrixSync.exe" (
    if not exist "dist" mkdir dist
    copy /Y "%DIST_TMP%\BiomatrixSync.exe" "dist\BiomatrixSync.exe"
    copy /Y "%DIST_TMP%\BiomatrixSyncService.exe" "dist\BiomatrixSyncService.exe"
    echo Build successful:
    echo   dist\BiomatrixSync.exe        (GUI app)
    echo   dist\BiomatrixSyncService.exe (Windows Service)
) else (
    echo Build failed. Check output above.
)
pause
