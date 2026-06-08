#!/bin/bash
# Build BiomatrixSync for Mac (.app)

echo "Installing dependencies..."
pip3 install -r requirements.txt

echo "Building Mac app..."
pyinstaller build.spec --clean --noconfirm

echo ""
if [ -d "dist/BiomatrixSync.app" ]; then
    echo "Build successful: dist/BiomatrixSync.app"
    echo "To run: open dist/BiomatrixSync.app"
else
    echo "Build output: dist/BiomatrixSync"
fi
