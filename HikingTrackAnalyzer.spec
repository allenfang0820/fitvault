import os
import platform
import json
import shutil
from scripts.release_version import normalize_release_version
# Force pyinstaller to use local cache dir to avoid permission error
os.environ["PYINSTALLER_CONFIG_DIR"] = os.path.join(os.getcwd(), ".pyinstaller_cache")
os.environ["PYINSTALLER_STRICT_CACHE_DIR"] = os.path.join(os.getcwd(), ".pyinstaller_cache")
os.environ["XDG_CACHE_HOME"] = os.path.join(os.getcwd(), ".pyinstaller_cache")
os.environ["XDG_CONFIG_HOME"] = os.path.join(os.getcwd(), ".pyinstaller_cache")

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from packaging_diagnostics import (
    MANIFEST_FILENAME,
    check_packaging_prerequisites,
    write_dependency_manifest,
)


check_packaging_prerequisites(os.getcwd())
# The manifest is shipped inside the app. Keep diagnostics useful while
# avoiding build-machine absolute paths in the distributable artifact.
# Historical packaging-contract marker: write_dependency_manifest(os.getcwd())
write_dependency_manifest(os.getcwd(), portable=True)

# CI provides FITVAULT_RELEASE_VERSION from the triggering tag. Local V2.0
# builds keep the same value when no release tag is supplied.
RELEASE_VERSION = normalize_release_version(
    os.environ.get("FITVAULT_RELEASE_VERSION", "2.0.0")
)
RELEASE_INFO_FILENAME = "release_info.json"
RELEASE_INFO_DIR = os.path.join(os.getcwd(), "build", "release_info")
os.makedirs(RELEASE_INFO_DIR, exist_ok=True)
RELEASE_INFO_PATH = os.path.join(RELEASE_INFO_DIR, RELEASE_INFO_FILENAME)
with open(RELEASE_INFO_PATH, "w", encoding="utf-8") as release_info_file:
    json.dump(
        {
            "product_version": RELEASE_VERSION,
            "display_version": f"V{RELEASE_VERSION}",
        },
        release_info_file,
        ensure_ascii=False,
        indent=2,
    )

_hidden = (
    collect_submodules("gpxpy")
    + collect_submodules("fitparse")
    + collect_submodules("garmin_fit_sdk")
    + collect_submodules("garminconnect")
    + collect_submodules("curl_cffi")
    + collect_submodules("watchdog")
    + collect_submodules("webview")
    + ["llm_backend", "track_backend", "profile_backend",
       "requests", "urllib3", "certifi", "charset_normalizer", "idna", "pytz"]
)

_datas = [
    ("track.html", "."),
    ("lib", "lib"),
    ("assets", "assets"),
    (RELEASE_INFO_PATH, "."),
    ("skills/garmin-stats", "skills/garmin-stats"),
    ("skills/coros-stats", "skills/coros-stats"),
    ("skills/garmin-stats.zip", "skills"),
    ("skills/coros-stats.zip", "skills"),
    (MANIFEST_FILENAME, "."),
]

# WiX v3/MSI has a legacy code-page boundary on Windows. Keep the Windows
# publish tree ASCII-only so heat/candle/light cannot fail on a Chinese source
# filename even when the user-facing document content remains Chinese.
if platform.system().lower() == "windows":
    WINDOWS_HELP_DIR = os.path.join(os.getcwd(), "build", "windows_resources", "docs")
    os.makedirs(WINDOWS_HELP_DIR, exist_ok=True)
    WINDOWS_HELP_PATH = os.path.join(WINDOWS_HELP_DIR, "help.md")
    shutil.copyfile("docs/脉图帮助说明.md", WINDOWS_HELP_PATH)
    _datas.append((WINDOWS_HELP_PATH, "docs"))
else:
    _datas.append(("docs/脉图帮助说明.md", "docs"))


def _node_runtime_datas():
    """Bundle a per-architecture Node.js runtime when available.

    Preferred input:
      MAITU_NODE_RUNTIME_DIR=/path/to/node-vXX-darwin-arm64

    Fallback local layout:
      runtimes/node-darwin-arm64
      runtimes/node-darwin-x64
      runtimes/node-win-x64

    The runtime is copied to app resources as ./node so COROS MCP scripts can
    run without requiring users to install Node.js separately.
    """
    runtime_dir = os.environ.get("MAITU_NODE_RUNTIME_DIR", "").strip()
    if not runtime_dir:
        system = platform.system().lower()
        machine = platform.machine().lower()
        arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
        if system == "windows":
            runtime_name = "node-win-x64"
        else:
            runtime_name = f"node-darwin-{arch}"
        runtime_dir = os.path.join(os.getcwd(), "runtimes", runtime_name)
    if runtime_dir and os.path.isdir(runtime_dir):
        return [(runtime_dir, "node")]

    node_binary = os.environ.get("MAITU_NODE_BINARY", "").strip()
    if node_binary and os.path.isfile(node_binary):
        return [(node_binary, "node/bin")]
    return []


_datas += _node_runtime_datas()

# Legacy/debug only: the unified Account Connection Center performs Garmin
# login inside the app and does not require FitVaultCLI.exe for normal Windows
# releases. Do not enable this for standard packaging unless explicitly testing
# the old console flow.
_include_legacy_console_helper = (
    os.environ.get("FITVAULT_INCLUDE_LEGACY_CONSOLE_HELPER", "").strip().lower()
    in {"1", "true", "yes", "on"}
)
_windows_icon = "installer/maitu.ico" if platform.system().lower() == "windows" else None

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

gui_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FitVault',
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
    icon=_windows_icon,
)
cli_exe = None
if platform.system().lower() == "windows" and _include_legacy_console_helper:
    cli_exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='FitVaultCLI',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=_windows_icon,
    )
_collect_items = [gui_exe, a.binaries, a.datas]
if cli_exe is not None:
    _collect_items.insert(1, cli_exe)
coll = COLLECT(
    *_collect_items,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FitVault',
)
app = BUNDLE(
    coll,
    name='脉图.app',
    icon='assets/app_icon.icns',
    bundle_identifier='com.mrfang.fitvault',
    info_plist={
        'CFBundleShortVersionString': RELEASE_VERSION,
        'CFBundleVersion': RELEASE_VERSION,
    },
)
