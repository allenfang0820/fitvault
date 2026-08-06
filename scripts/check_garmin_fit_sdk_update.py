#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packaging_diagnostics import GARMIN_FIT_SDK_EXPECTED_VERSION, _version_tuple  # noqa: E402


PACKAGE_NAME = "garmin-fit-sdk"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"


class UpdateCheckError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_stable_numeric_version(version: str) -> bool:
    parts = str(version or "").split(".")
    return len(parts) >= 2 and all(part.isdigit() for part in parts)


def latest_stable_version_from_pypi_payload(payload: dict[str, Any]) -> str:
    releases = payload.get("releases")
    if not isinstance(releases, dict):
        raise UpdateCheckError("bad_response", "PyPI response does not contain a releases object")
    stable_versions = [str(version) for version in releases if _is_stable_numeric_version(str(version))]
    if not stable_versions:
        raise UpdateCheckError("no_stable_versions", "PyPI response contains no stable numeric versions")
    return max(stable_versions, key=_version_tuple)


def fetch_pypi_payload(url: str = PYPI_JSON_URL, *, timeout: float = 15.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "FitVault-Garmin-FIT-SDK-Update-Check"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateCheckError("network_error", f"{type(exc).__name__}: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise UpdateCheckError("bad_response", f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict):
        raise UpdateCheckError("bad_response", "PyPI response is not a JSON object")
    return payload


def build_update_report(
    *,
    current_version: str = GARMIN_FIT_SDK_EXPECTED_VERSION,
    fetcher: Callable[[], dict[str, Any]] = fetch_pypi_payload,
    checked_at: str | None = None,
) -> dict[str, Any]:
    timestamp = checked_at or _utc_now_iso()
    try:
        payload = fetcher()
        latest = latest_stable_version_from_pypi_payload(payload)
    except UpdateCheckError as exc:
        return {
            "ok": False,
            "package": PACKAGE_NAME,
            "current_version": current_version,
            "latest_stable_version": None,
            "update_available": None,
            "source": "pypi",
            "checked_at": timestamp,
            "error_code": exc.code,
            "error": str(exc),
        }
    return {
        "ok": True,
        "package": PACKAGE_NAME,
        "current_version": current_version,
        "latest_stable_version": latest,
        "update_available": _version_tuple(latest) > _version_tuple(current_version),
        "source": "pypi",
        "checked_at": timestamp,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether PyPI has a newer stable garmin-fit-sdk release.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    report = build_update_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    elif report["ok"]:
        marker = "update available" if report["update_available"] else "up to date"
        print(
            f"{PACKAGE_NAME} {marker}: current={report['current_version']} "
            f"latest={report['latest_stable_version']}"
        )
    else:
        print(f"{PACKAGE_NAME} update check failed: {report['error_code']}: {report['error']}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
