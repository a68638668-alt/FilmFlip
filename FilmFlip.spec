# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os

PROJECT_ROOT = Path.cwd()
ICON_PATH = PROJECT_ROOT / 'assets' / 'icon.icns'

a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FilmFlip',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='universal2',
    codesign_identity=os.environ.get('FILMFLIP_CODESIGN_IDENTITY') or None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='FilmFlip',
)

app = BUNDLE(
    coll,
    name='FilmFlip.app',
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
    bundle_identifier='com.filmflip.app',
    version='2.0.0',
    info_plist={
        'CFBundleDisplayName': 'FilmFlip',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
    },
)
