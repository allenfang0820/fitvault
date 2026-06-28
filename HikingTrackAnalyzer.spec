import os
# Force pyinstaller to use local cache dir to avoid permission error
os.environ["PYINSTALLER_CONFIG_DIR"] = os.path.join(os.getcwd(), ".pyinstaller_cache")
os.environ["PYINSTALLER_STRICT_CACHE_DIR"] = os.path.join(os.getcwd(), ".pyinstaller_cache")
os.environ["XDG_CACHE_HOME"] = os.path.join(os.getcwd(), ".pyinstaller_cache")
os.environ["XDG_CONFIG_HOME"] = os.path.join(os.getcwd(), ".pyinstaller_cache")

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

_hidden = (
    collect_submodules("gpxpy")
    + collect_submodules("fitparse")
    + collect_submodules("garmin_fit_sdk")
    + collect_submodules("watchdog")
    + collect_submodules("webview")
    + ["llm_backend", "track_backend", "profile_backend",
       "requests", "urllib3", "certifi", "charset_normalizer", "idna"]
)

_datas = [
    ("track.html", "."),
    ("lib", "lib"),
    ("assets", "assets"),
    ("skills/garmin-stats.zip", "skills"),
    ("skills/coros-stats.zip", "skills"),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "pandas",
        "pandas.tests",
        "pytest",
        "torch",
        "torchvision",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MaiTu',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MaiTu',
)
app = BUNDLE(
    coll,
    name='脉图.app',
    icon='assets/app_icon.icns',
    bundle_identifier='com.mrfang.maitu',
    info_plist={
        'CFBundleShortVersionString': '1.0.4',
        'CFBundleVersion': '1.0.4',
    },
)
