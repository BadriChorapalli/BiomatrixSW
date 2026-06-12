# -*- mode: python ; coding: utf-8 -*-
import sys

block_cipher = None
IS_MAC = sys.platform == 'darwin'
IS_WIN = sys.platform == 'win32'

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'zk', 'zk.base', 'zk.const', 'zk.exception',
        'schedule', 'customtkinter',
        'tkinter', 'tkinter.ttk',
        'pystray', 'pystray._win32', 'pystray._base',
        'jaraco.functools', 'jaraco.context', 'jaraco.text',
        'pkg_resources._vendor.jaraco.functools',
        'pkg_resources._vendor.jaraco.context',
        'pkg_resources._vendor.jaraco.text',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BiomatrixSync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# Mac: wrap exe into a .app bundle
if IS_MAC:
    app = BUNDLE(
        exe,
        name='BiomatrixSync.app',
        icon=None,
        bundle_identifier='com.bellweather.biomatrixsync',
        entitlements_file='entitlements.plist',
        info_plist={
            'CFBundleName': 'BiomatrixSync',
            'CFBundleDisplayName': 'Biomatrix Sync',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )
