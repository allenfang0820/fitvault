param(
    [string]$Python = $env:PYTHON
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

if ([string]::IsNullOrWhiteSpace($Python)) {
    $VenvPython = Join-Path $ProjectRoot ".venv312\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        $Python = $VenvPython
    } else {
        $Python = "python"
    }
}

Write-Host "[packaging-deps] project_root=$ProjectRoot"
Write-Host "[packaging-deps] requested_python=$Python"
& $Python -c "import sys; print(f'[packaging-deps] python_executable={sys.executable}'); print(f'[packaging-deps] python_version={sys.version.split()[0]}')"

& $Python -m pip install -r requirements.txt -c constraints.txt

& $Python -c @"
import importlib
import sys

modules = ("fitparse", "garmin_fit_sdk", "garminconnect", "curl_cffi", "requests")
missing = []
for module in modules:
    try:
        importlib.import_module(module)
    except Exception as exc:
        missing.append(f"{module}: {type(exc).__name__}: {exc}")

if missing:
    print(f"[packaging-deps] smoke_failed python_executable={sys.executable}", file=sys.stderr)
    for item in missing:
        print(f"[packaging-deps] missing_or_broken={item}", file=sys.stderr)
    raise SystemExit(1)

print(f"[packaging-deps] smoke_ok python_executable={sys.executable}")
"@
