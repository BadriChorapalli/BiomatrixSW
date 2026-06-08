@echo off
REM Build BiomatrixSync for Windows (.exe)

echo Installing dependencies...
pip install -r requirements.txt

echo Building Windows exe...
pyinstaller build.spec --clean --noconfirm

echo.
if exist "dist\BiomatrixSync.exe" (
    echo Build successful: dist\BiomatrixSync.exe
) else (
    echo Build failed. Check output above.
)
pause
