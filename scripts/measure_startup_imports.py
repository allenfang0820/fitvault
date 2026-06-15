#!/usr/bin/env python3
"""Measure the import-time startup surface without launching the desktop app."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


WATCH_MODULES = (
    "numpy",
    "scipy",
    "scipy.signal",
    "pandas",
    "fitparse",
    "garmin_fit_sdk",
    "webview",
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    started = time.perf_counter()
    import main as app_main  # noqa: F401

    elapsed = time.perf_counter() - started
    payload = {
        "elapsed_sec": round(elapsed, 6),
        "loaded": {name: name in sys.modules for name in WATCH_MODULES},
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
