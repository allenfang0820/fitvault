#!/usr/bin/env python3
"""Remove build-machine prefixes embedded in macOS release binaries.

PyInstaller can bundle a Python/OpenSSL dylib built by pyenv. Those dylibs may
retain the builder's absolute prefix in diagnostic/default-path strings. The
release contract forbids shipping that local path, while the frozen app uses
its own bundle-relative paths at runtime.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _replace_fixed_width(data: bytes, old: bytes, new: bytes) -> tuple[bytes, int]:
    if not old or len(new) > len(old):
        raise ValueError("replacement must not be longer than the source string")
    padded = new + (b"\0" * (len(old) - len(new)))
    count = data.count(old)
    return (data.replace(old, padded), count)


def sanitize_bundle(app_path: str | Path, source_prefix: str) -> int:
    app = Path(app_path)
    prefix = source_prefix.rstrip("/").encode()
    if not app.is_dir() or not prefix:
        raise ValueError("app_path must be an existing .app directory and source_prefix is required")

    replacements = (
        (prefix + b"/openssl/ssl/ct_log_list.cnf", b"./ssl/ct_log_list.cnf"),
        (prefix + b"/openssl/ssl", b"./ssl"),
        (prefix + b"/openssl/lib/engines-3", b"./engines-3"),
        (prefix + b"/openssl/lib/ossl-modules", b"./ossl-modules"),
        (prefix + b"/include", b"./include"),
        (prefix, b"./python"),
    )
    changed = 0
    for path in app.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        updated = data
        file_changed = False
        for old, new in replacements:
            updated, count = _replace_fixed_width(updated, old, new)
            file_changed = file_changed or bool(count)
        if file_changed:
            path.write_bytes(updated)
            changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--source-prefix", required=True)
    args = parser.parse_args()
    changed = sanitize_bundle(args.app, args.source_prefix)
    print(f"sanitized_files={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
