#!/usr/bin/env python3
from __future__ import annotations

import importlib
import importlib.metadata
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packaging_diagnostics import (  # noqa: E402
    CURL_CFFI_MIN_VERSION,
    GARMINCONNECT_EXPECTED_VERSION,
    GARMIN_FIT_SDK_EXPECTED_VERSION,
    _version_tuple,
)


REQUIRED_DISTRIBUTIONS: tuple[dict[str, str | None], ...] = (
    {"name": "garminconnect", "expected": GARMINCONNECT_EXPECTED_VERSION, "minimum": None},
    {"name": "garmin-fit-sdk", "expected": GARMIN_FIT_SDK_EXPECTED_VERSION, "minimum": None},
    {"name": "curl_cffi", "expected": None, "minimum": CURL_CFFI_MIN_VERSION},
    {"name": "requests", "expected": None, "minimum": None},
    {"name": "urllib3", "expected": None, "minimum": None},
    {"name": "certifi", "expected": None, "minimum": None},
)

REQUIRED_IMPORTS: tuple[str, ...] = (
    "fitparse",
    "garmin_fit_sdk",
    "garminconnect",
    "curl_cffi",
    "requests",
    "pandas",
    "numpy",
    "scipy",
    "webview",
    "gpxpy",
    "watchdog",
)

STARTUP_LAZY_MODULES: tuple[str, ...] = ("garmin_fit_sdk", "fitparse")


def _version_lookup(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def _check_distributions(
    *,
    version_lookup: Callable[[str], str | None] = _version_lookup,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    checked: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for requirement in REQUIRED_DISTRIBUTIONS:
        name = str(requirement["name"])
        expected = requirement.get("expected")
        minimum = requirement.get("minimum")
        version = version_lookup(name)
        status = "ok"
        if not version:
            status = "missing"
            errors.append(f"Missing required distribution: {name}")
        elif expected and version != expected:
            status = "incompatible"
            errors.append(f"Incompatible {name}: detected {version}, expected {expected}")
        elif minimum and _version_tuple(version) < _version_tuple(minimum):
            status = "incompatible"
            errors.append(f"Incompatible {name}: detected {version}, expected >= {minimum}")
        checked[name] = {
            "version": version,
            "expected": expected,
            "minimum": minimum,
            "status": status,
        }
    return checked, errors


def _check_imports(
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> tuple[dict[str, dict[str, str | None]], list[str]]:
    checked: dict[str, dict[str, str | None]] = {}
    errors: list[str] = []
    for module_name in REQUIRED_IMPORTS:
        status = "ok"
        error = None
        try:
            import_module(module_name)
        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            errors.append(f"Cannot import {module_name}: {error}")
        checked[module_name] = {"status": status, "error": error}
    return checked, errors


def _check_startup_lazy_import_subprocess() -> tuple[dict[str, Any], list[str]]:
    code = textwrap.dedent(
        f"""
        import json
        import sys

        watched = {STARTUP_LAZY_MODULES!r}
        before = {{name: name in sys.modules for name in watched}}
        import main
        after = {{name: name in sys.modules for name in watched}}
        print(json.dumps({{"before": before, "after": after}}, sort_keys=True))
        """
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, [
            f"Startup lazy import check failed: {type(exc).__name__}: {exc}"
        ]
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return {"ok": False, "returncode": completed.returncode, "error": detail}, [
            f"Startup lazy import check failed: {detail}"
        ]
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    try:
        payload = json.loads(lines[-1])
    except Exception as exc:
        return {"ok": False, "stdout": completed.stdout, "error": f"{type(exc).__name__}: {exc}"}, [
            f"Startup lazy import check produced invalid JSON: {type(exc).__name__}: {exc}"
        ]
    loaded = {name: bool(payload.get("after", {}).get(name)) for name in STARTUP_LAZY_MODULES}
    errors = [f"Startup import loaded {name}; expected lazy import" for name, is_loaded in loaded.items() if is_loaded]
    return {"ok": not errors, "loaded": loaded, "before": payload.get("before", {})}, errors


def build_runtime_report(
    *,
    version_lookup: Callable[[str], str | None] = _version_lookup,
    import_module: Callable[[str], Any] = importlib.import_module,
    startup_checker: Callable[[], tuple[dict[str, Any], list[str]]] = _check_startup_lazy_import_subprocess,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    version_info = {
        "major": sys.version_info.major,
        "minor": sys.version_info.minor,
        "micro": sys.version_info.micro,
    }
    if (sys.version_info.major, sys.version_info.minor) < (3, 12):
        warnings.append("Release packaging expects Python >= 3.12; reinstall dependencies in the packaging venv.")

    distributions, distribution_errors = _check_distributions(version_lookup=version_lookup)
    imports, import_errors = _check_imports(import_module=import_module)
    startup_lazy_import, startup_errors = startup_checker()
    errors.extend(distribution_errors)
    errors.extend(import_errors)
    errors.extend(startup_errors)

    return {
        "ok": not errors,
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "python_version_info": version_info,
        "errors": errors,
        "warnings": warnings,
        "checked_distributions": distributions,
        "checked_modules": imports,
        "startup_lazy_import_ok": bool(startup_lazy_import.get("ok")),
        "startup_lazy_import": startup_lazy_import,
    }


def main() -> int:
    report = build_runtime_report()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
