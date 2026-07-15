#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x ".venv312/bin/python" ]]; then
    PYTHON_BIN=".venv312/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

echo "[packaging-deps] project_root=${PROJECT_ROOT}"
echo "[packaging-deps] requested_python=${PYTHON_BIN}"
"${PYTHON_BIN}" - <<'PY'
import sys

print(f"[packaging-deps] python_executable={sys.executable}")
print(f"[packaging-deps] python_version={sys.version.split()[0]}")
PY

"${PYTHON_BIN}" -m pip install -r requirements.txt -c constraints.txt

"${PYTHON_BIN}" - <<'PY'
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
PY
