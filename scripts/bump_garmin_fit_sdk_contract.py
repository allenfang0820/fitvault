#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sync_garmin_fit_sdk_contract import sync_contract  # noqa: E402


VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)+$")
SOURCE_PATTERN = re.compile(r'(?m)^GARMIN_FIT_SDK_EXPECTED_VERSION = "[^"]+"$')


def _validate_version(version: str) -> str:
    normalized = str(version or "").strip()
    if not VERSION_PATTERN.match(normalized):
        raise ValueError(f"Only stable numeric versions are supported: {version!r}")
    return normalized


def bump_contract(root: str | Path = PROJECT_ROOT, *, version: str) -> dict[str, Any]:
    resolved_root = Path(root)
    target_version = _validate_version(version)
    source_path = resolved_root / "packaging_diagnostics.py"
    original = source_path.read_text(encoding="utf-8")
    updated, count = SOURCE_PATTERN.subn(f'GARMIN_FIT_SDK_EXPECTED_VERSION = "{target_version}"', original)
    if count != 1:
        return {
            "ok": False,
            "package": "garmin-fit-sdk",
            "target_version": target_version,
            "error_code": "version_source_not_found",
            "error": "Expected exactly one GARMIN_FIT_SDK_EXPECTED_VERSION assignment",
        }
    if updated != original:
        source_path.write_text(updated, encoding="utf-8")
    sync_result = sync_contract(resolved_root, version=target_version, write=True)
    return {
        "ok": bool(sync_result.get("ok")),
        "package": "garmin-fit-sdk",
        "target_version": target_version,
        "version_source": "packaging_diagnostics.py",
        "files": [{"path": "packaging_diagnostics.py", "changed": updated != original}, *sync_result["files"]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bump the garmin-fit-sdk contract to a stable target version.")
    parser.add_argument("--version", required=True, help="Stable numeric garmin-fit-sdk version to write.")
    parser.add_argument("--root", default=str(PROJECT_ROOT), help="Project root. Defaults to this repository.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        result = bump_contract(args.root, version=args.version)
    except ValueError as exc:
        result = {
            "ok": False,
            "package": "garmin-fit-sdk",
            "target_version": args.version,
            "error_code": "invalid_version",
            "error": str(exc),
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(f"garmin-fit-sdk contract bumped to {result['target_version']}")
    else:
        print(f"garmin-fit-sdk contract bump failed: {result.get('error_code')}: {result.get('error')}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
